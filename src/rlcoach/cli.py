"""Command-line interface for rlcoach."""

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, get_default_config_path, load_config
from .config_templates import CONFIG_TEMPLATE
from .errors import RLCoachError


def handle_ingest_command(args) -> int:
    """Store each replay and its review, the way the watcher does."""
    from .pipeline import IngestionStatus
    from .service import load_replay

    config_path = get_default_config_path()
    try:
        config = load_config(config_path)
        config.validate()
    except (ConfigError, FileNotFoundError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    fine = (
        IngestionStatus.SUCCESS,
        IngestionStatus.DUPLICATE,
        IngestionStatus.EXCLUDED,
    )
    failed = 0
    for name in args.replay_files:
        if load_replay(Path(name), config) not in fine:
            failed += 1
    return 1 if failed else 0


def handle_config_command(args) -> int:
    """Handle the config subcommand."""
    config_path = get_default_config_path()

    if args.init:
        if config_path.exists() and not args.force:
            print(f"Config already exists at {config_path}")
            print("Use --force to overwrite")
            return 1

        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(CONFIG_TEMPLATE)
        print(f"Created config template at {config_path}")
        print("Edit this file with your player info before running RLCoach.")
        return 0

    if args.validate:
        try:
            config = load_config(config_path)
            config.validate()
            print(f"Configuration is valid: {config_path}")
            print(f"  Platform IDs: {len(config.identity.platform_ids)}")
            print(f"  Display names: {len(config.identity.display_names)}")
            print(f"  Target rank: {config.preferences.target_rank}")
            print(f"  Timezone: {config.preferences.timezone or '(system default)'}")
            return 0
        except ConfigError as e:
            print(f"Configuration error: {e}")
            return 1
        except FileNotFoundError:
            print(f"Config file not found: {config_path}")
            print("Run 'rlcoach config --init' to create one.")
            return 1
        except Exception as e:
            print(f"Error loading config: {e}")
            return 1

    if args.show:
        try:
            print(config_path.read_text())
            return 0
        except FileNotFoundError:
            print(f"Config file not found: {config_path}")
            return 1

    print("Use --init, --validate, or --show")
    return 1


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point.

    Args:
        argv: Command line arguments. If None, uses sys.argv[1:].
    """
    # Windows writes piped output in its ANSI code page, which has no ✓ or ✗
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        prog="rlcoach",
        description="All-local Rocket League replay analysis tool for coaching",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"rlcoach {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    ingest_parser = subparsers.add_parser(
        "ingest", help="Load replays from anywhere, and review them"
    )
    ingest_parser.add_argument(
        "replay_files", nargs="+", help="The .replay files to load"
    )

    mistakes_parser = subparsers.add_parser(
        "mistakes",
        help="List one player's mistakes in a replay and what to do instead",
    )
    mistakes_parser.add_argument(
        "replay_file", type=str, help="Path to the .replay file"
    )
    mistakes_parser.add_argument(
        "--player",
        type=str,
        help="Player to review (default: whoever saved the replay)",
    )
    mistakes_parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON instead of plain text",
    )

    reviews_parser = subparsers.add_parser(
        "reviews",
        help="Review your mistakes in loaded games that don't have a review yet",
    )
    reviews_parser.add_argument(
        "--redo",
        action="store_true",
        help="Review every loaded game again, for after the detector changes",
    )

    config_parser = subparsers.add_parser("config", help="Manage RLCoach configuration")
    config_parser.add_argument(
        "--init", action="store_true", help="Create template config file"
    )
    config_parser.add_argument(
        "--validate", action="store_true", help="Validate current config"
    )
    config_parser.add_argument(
        "--show", action="store_true", help="Display current config"
    )
    config_parser.add_argument(
        "--force", action="store_true", help="Force overwrite existing config"
    )

    serve_parser = subparsers.add_parser(
        "serve",
        help="Serve the dashboard and API on one port, and load new replays",
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    serve_parser.add_argument(
        "--no-watch",
        action="store_true",
        dest="no_watch",
        help="Don't watch the replay folder",
    )
    serve_parser.add_argument(
        "--log-file",
        type=str,
        dest="log_file",
        help="Write output to this file instead of the console",
    )

    start_parser = subparsers.add_parser(
        "start", help="Run serve in the background, with no window"
    )
    start_parser.add_argument("--port", type=int, default=8000)

    subparsers.add_parser("stop", help="Stop the background server")

    autostart_parser = subparsers.add_parser(
        "autostart", help="Start the background server when you sign in to Windows"
    )
    autostart_parser.add_argument("action", choices=["on", "off", "status"])
    autostart_parser.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)

    if args.command == "ingest":
        return handle_ingest_command(args)
    elif args.command == "mistakes":
        return handle_mistakes_command(args)
    elif args.command == "reviews":
        return handle_reviews_command(args)
    elif args.command == "config":
        return handle_config_command(args)
    elif args.command == "serve":
        return handle_serve_command(args)
    elif args.command == "start":
        return handle_start_command(args)
    elif args.command == "stop":
        return handle_stop_command(args)
    elif args.command == "autostart":
        return handle_autostart_command(args)
    else:
        parser.print_help()
        return 0


def handle_mistakes_command(args) -> int:
    """Handle the mistakes subcommand."""
    from .analysis.mistakes import analyze_replay, format_report

    try:
        report = analyze_replay(Path(args.replay_file), player=args.player)
    except (RLCoachError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report(report))
    return 0


def handle_reviews_command(args) -> int:
    """Review loaded games that have no stored mistake review."""
    from .db.reviews import games_to_review, review_game
    from .db.session import init_db

    config_path = get_default_config_path()
    try:
        config = load_config(config_path)
        config.validate()
    except (ConfigError, FileNotFoundError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    init_db(config.db_path)
    games = games_to_review(redo=args.redo)
    if not games:
        print("Every loaded game already has a review.")
        return 0

    counts: dict[str, int] = {}
    for number, (replay_id, source_file, player_id) in enumerate(games, start=1):
        if not Path(source_file).exists():
            status = "missing file"
        else:
            status = review_game(replay_id, source_file, player_id)
        counts[status] = counts.get(status, 0) + 1
        print(f"[{number}/{len(games)}] {Path(source_file).name}: {status}")

    summary = ", ".join(f"{n} {status}" for status, n in sorted(counts.items()))
    print(f"Reviewed {len(games)} games: {summary}")
    return 0


def handle_serve_command(args) -> int:
    """Serve the dashboard and API on one port, with the replay watcher."""
    import uvicorn

    from . import service
    from .api import create_app

    log_file = getattr(args, "log_file", None)
    if log_file:
        service.redirect_output(Path(log_file))

    config_path = get_default_config_path()
    try:
        config = load_config(config_path)
        config.validate()
    except ConfigError as e:
        print(f"Configuration error: {e}")
        return 1
    except FileNotFoundError:
        print(f"Config file not found: {config_path}")
        print("Run 'rlcoach config --init' to create one.")
        return 1

    host = args.host
    port = args.port

    watcher = None
    if not getattr(args, "no_watch", False):
        watch_dir = config.paths.watch_folder
        if not watch_dir.exists():
            # OneDrive may not be ready yet at sign-in, and the watcher keeps
            # looking, so start it anyway.
            print(f"Watch folder not found yet, will keep checking: {watch_dir}")
        print(f"Loading new replays from {watch_dir}")
        watcher = service.ingest_watcher(config, process_existing=True)

    gui_dir = service.GUI_DIST
    if not (gui_dir / "index.html").exists():
        print("No built dashboard, so serving the API only.")
        print("Build it with: npm --prefix gui run build")
        gui_dir = None

    shown = "localhost" if host in ("127.0.0.1", "0.0.0.0") else host
    print(f"rlcoach is at http://{shown}:{port} (API under /api)")
    if not log_file:
        print("Press Ctrl+C to stop")

    app = service.create_site(create_app(), gui_dir, watcher)
    service.claim_pid_file()
    try:
        # The dashboard polls every 30 seconds, which would fill the log
        uvicorn.run(
            app, host=host, port=port, log_level="info", access_log=not log_file
        )
    finally:
        service.release_pid_file()

    return 0


def handle_start_command(args) -> int:
    """Run the server in the background and wait until it answers."""
    from . import service

    url = service.site_url(args.port)
    if service.start_background(args.port):
        print(f"rlcoach is running at {url}")
        return 0
    print(f"rlcoach didn't answer at {url}. See {service.log_path()}")
    return 1


def handle_stop_command(args) -> int:
    """Stop the background server."""
    from . import service

    if service.stop_background():
        print("Stopped rlcoach.")
    else:
        print("rlcoach wasn't running in the background.")
    return 0


def handle_autostart_command(args) -> int:
    """Turn starting at Windows sign-in on or off, or show whether it's on."""
    from . import service

    if sys.platform != "win32":
        print("Starting at sign-in is only set up for Windows.")
        return 1

    if args.action == "on":
        service.enable_autostart(args.port)
        print("rlcoach will start when you sign in to Windows.")
        return handle_start_command(args)
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
    running = f"yes, pid {pid}" if pid is not None else "no"
    print(f"Running in the background: {running}")
    print(f"Log: {service.log_path()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
