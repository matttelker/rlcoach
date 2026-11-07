"""The rlcoach command.

`serve` runs the dashboard, the API and the replay watcher. `start`, `stop`
and `autostart` run it in the background. `ingest`, `mistakes` and `reviews`
are what Claude uses in chat to load games and look at them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import (
    CONFIG_TEMPLATE,
    ConfigError,
    RLCoachConfig,
    get_default_config_path,
    load_config,
)

DEFAULT_PORT = 8000


def _config() -> RLCoachConfig | None:
    """Your config, or None after saying what's wrong with it."""
    path = get_default_config_path()
    try:
        config = load_config(path)
        config.validate()
    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        if not path.exists():
            print("Run 'rlcoach config --init' to create one.", file=sys.stderr)
        return None
    return config


def ingest(args: argparse.Namespace) -> int:
    """Load and review replays from anywhere, as the watcher does."""
    from .db.session import init_db
    from .pipeline import IngestionStatus
    from .service import load_replay

    config = _config()
    if config is None:
        return 1
    init_db(config.db_path)
    fine = {
        IngestionStatus.SUCCESS,
        IngestionStatus.DUPLICATE,
        IngestionStatus.EXCLUDED,
    }
    failed = [
        name
        for name in args.replay_files
        if load_replay(Path(name), config) not in fine
    ]
    return 1 if failed else 0


def mistakes(args: argparse.Namespace) -> int:
    """Print one player's mistakes in a replay."""
    from .analysis.mistakes import analyze_replay, format_report

    try:
        report = analyze_replay(Path(args.replay_file), player=args.player)
    except (ValueError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    print(
        json.dumps(report.to_dict(), indent=2) if args.json else format_report(report)
    )
    return 0


def reviews(args: argparse.Namespace) -> int:
    """Review loaded games that have no review, or all of them with --redo."""
    from .db.reviews import games_to_review, review_game
    from .db.session import init_db

    config = _config()
    if config is None:
        return 1
    init_db(config.db_path)
    games = games_to_review(redo=args.redo)
    if not games:
        print("Every loaded game already has a review.")
        return 0
    counts: dict[str, int] = {}
    for number, (replay_id, source_file, player_id) in enumerate(games, start=1):
        if Path(source_file).exists():
            status = review_game(replay_id, source_file, player_id)
        else:
            status = "missing file"
        counts[status] = counts.get(status, 0) + 1
        print(f"[{number}/{len(games)}] {Path(source_file).name}: {status}")
    summary = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
    print(f"Reviewed {len(games)} games: {summary}")
    return 0


def config_command(args: argparse.Namespace) -> int:
    """Create, check or show the config file."""
    path = get_default_config_path()
    if args.init:
        if path.exists() and not args.force:
            print(f"Config already exists at {path}. Use --force to overwrite it.")
            return 1
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
        print(f"Created {path}. Put your accounts and replay folder in it.")
        return 0
    if args.validate:
        config = _config()
        if config is None:
            return 1
        prefs = config.preferences
        print(f"Configuration is valid: {path}")
        print(f"  Platform IDs: {len(config.identity.platform_ids)}")
        print(f"  Display names: {len(config.identity.display_names)}")
        print(f"  Target rank: {prefs.target_rank}")
        print(f"  Timezone: {prefs.timezone or '(system default)'}")
        return 0
    if args.show:
        if not path.exists():
            print(f"Config file not found: {path}")
            return 1
        print(path.read_text(encoding="utf-8"))
        return 0
    print("Use --init, --validate or --show")
    return 1


def serve(args: argparse.Namespace) -> int:
    """Serve the dashboard and API on one port, and load new replays."""
    import uvicorn

    from . import service
    from .api import create_app

    if args.log_file:
        service.redirect_output(Path(args.log_file))
    config = _config()
    if config is None:
        return 1

    watcher = None
    if not args.no_watch:
        folder = config.paths.watch_folder
        if not folder.exists():
            # OneDrive may not be ready yet at sign-in, and the watcher keeps
            # looking, so start it anyway.
            print(f"Watch folder not found yet, will keep checking: {folder}")
        print(f"Loading new replays from {folder}")
        watcher = service.ingest_watcher(config, process_existing=True)

    gui = service.GUI_DIST
    if not (gui / "index.html").exists():
        print("No built dashboard, so serving the API only.")
        print("Build it with: npm --prefix gui run build")
        gui = None

    shown = "localhost" if args.host in ("127.0.0.1", "0.0.0.0") else args.host
    print(f"rlcoach is at http://{shown}:{args.port} (API under /api)")
    if not args.log_file:
        print("Press Ctrl+C to stop")

    site = service.create_site(create_app(), gui, watcher)
    service.claim_pid_file()
    try:
        # The dashboard polls every 30 seconds, which would fill the log
        uvicorn.run(
            site,
            host=args.host,
            port=args.port,
            log_level="info",
            access_log=not args.log_file,
        )
    finally:
        service.release_pid_file()
    return 0


def start(args: argparse.Namespace) -> int:
    """Run the server in the background and wait until it answers."""
    from . import service

    url = service.site_url(args.port)
    if service.start_background(args.port):
        print(f"rlcoach is running at {url}")
        return 0
    print(f"rlcoach didn't answer at {url}. See {service.log_path()}")
    return 1


def stop(args: argparse.Namespace) -> int:
    from . import service

    if service.stop_background():
        print("Stopped rlcoach.")
    else:
        print("rlcoach wasn't running in the background.")
    return 0


def autostart(args: argparse.Namespace) -> int:
    """Turn starting at Windows sign-in on or off, or say whether it's on."""
    from . import service

    if sys.platform != "win32":
        print("Starting at sign-in is only set up for Windows.")
        return 1
    if args.action == "on":
        service.enable_autostart(args.port)
        print("rlcoach will start when you sign in to Windows.")
        return start(args)
    if args.action == "off":
        if service.disable_autostart():
            print("rlcoach won't start at sign-in any more.")
        else:
            print("rlcoach wasn't set to start at sign-in.")
        return 0
    entry = service.autostart_entry()
    print(f"Starts at sign-in: {'yes' if entry else 'no'}")
    if entry:
        print(f"  {entry}")
    pid = service.running_pid()
    print(f"Running in the background: {f'yes, pid {pid}' if pid else 'no'}")
    print(f"Log: {service.log_path()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rlcoach", description="Local Rocket League replay coach"
    )
    parser.add_argument("--version", action="version", version=f"rlcoach {__version__}")
    commands = parser.add_subparsers(dest="command")

    cmd = commands.add_parser(
        "ingest", help="Load replays from anywhere, and review them"
    )
    cmd.add_argument("replay_files", nargs="+", help="The .replay files to load")
    cmd.set_defaults(run=ingest)

    cmd = commands.add_parser(
        "mistakes", help="List one player's mistakes in a replay and what to do instead"
    )
    cmd.add_argument("replay_file", help="Path to the .replay file")
    cmd.add_argument(
        "--player", help="Player to review (default: whoever saved the replay)"
    )
    cmd.add_argument("--json", action="store_true", help="Print JSON, not plain text")
    cmd.set_defaults(run=mistakes)

    cmd = commands.add_parser(
        "reviews", help="Review loaded games that don't have a review yet"
    )
    cmd.add_argument(
        "--redo",
        action="store_true",
        help="Review every loaded game again, for after the detector changes",
    )
    cmd.set_defaults(run=reviews)

    cmd = commands.add_parser("config", help="Create, check or show your config")
    cmd.add_argument("--init", action="store_true", help="Create a config to fill in")
    cmd.add_argument("--validate", action="store_true", help="Check your config")
    cmd.add_argument("--show", action="store_true", help="Print your config")
    cmd.add_argument("--force", action="store_true", help="Let --init overwrite it")
    cmd.set_defaults(run=config_command)

    cmd = commands.add_parser(
        "serve", help="Serve the dashboard and API on one port, and load new replays"
    )
    cmd.add_argument("--host", default="127.0.0.1", help="Default: 127.0.0.1")
    cmd.add_argument("--port", type=int, default=DEFAULT_PORT, help="Default: 8000")
    cmd.add_argument(
        "--no-watch", action="store_true", help="Don't watch the replay folder"
    )
    cmd.add_argument("--log-file", help="Write output to this file, not the console")
    cmd.set_defaults(run=serve)

    cmd = commands.add_parser(
        "start", help="Run serve in the background, with no window"
    )
    cmd.add_argument("--port", type=int, default=DEFAULT_PORT)
    cmd.set_defaults(run=start)

    cmd = commands.add_parser("stop", help="Stop the background server")
    cmd.set_defaults(run=stop)

    cmd = commands.add_parser(
        "autostart", help="Start the background server when you sign in to Windows"
    )
    cmd.add_argument("action", choices=["on", "off", "status"])
    cmd.add_argument("--port", type=int, default=DEFAULT_PORT)
    cmd.set_defaults(run=autostart)
    return parser


def main(argv: list[str] | None = None) -> int:
    # Windows writes piped output in its ANSI code page, which has no ✓ or ✗
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "run"):
        parser.print_help()
        return 0
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
