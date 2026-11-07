"""Run rlcoach as one always-on local site.

`rlcoach serve` puts the dashboard and the API behind one address and keeps
the replay watcher running in the same process. `rlcoach start` runs that in
the background, and `rlcoach autostart on` starts it when you sign in to
Windows, so nothing depends on a terminal staying open.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

if TYPE_CHECKING:
    from starlette.responses import Response
    from starlette.types import Scope

    from .config import RLCoachConfig
    from .watcher import ReplayWatcher

GUI_DIST = Path(__file__).resolve().parents[2] / "gui" / "dist"
DEFAULT_PORT = 8000
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "rlcoach"
LOG_ROTATE_BYTES = 2_000_000
START_TIMEOUT_S = 30.0
STOP_TIMEOUT_S = 10.0


def home_dir() -> Path:
    return Path.home() / ".rlcoach"


def log_path() -> Path:
    return home_dir() / "serve.log"


def pid_path() -> Path:
    return home_dir() / "serve.pid"


def site_url(port: int = DEFAULT_PORT) -> str:
    return f"http://localhost:{port}"


# The site


class Watcher(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class DashboardFiles(StaticFiles):
    """Serve the built dashboard, sending its own page paths to index.html.

    The dashboard routes pages like /games/abc in the browser, so reloading one
    must get index.html. A missing file such as an old script still gets a 404,
    so the browser doesn't run a page as code.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            last = path.rstrip("/").rsplit("/", 1)[-1]
            if exc.status_code != 404 or "." in last:
                raise
            return await super().get_response("index.html", scope)


def create_site(
    api: FastAPI, gui_dir: Path | None = None, watcher: Watcher | None = None
) -> FastAPI:
    """Put the API under /api and the dashboard at /, with the watcher alongside.

    The API's own startup, which loads the config and opens the database, runs
    first, because Starlette doesn't run a mounted app's lifespan. The watcher
    starts after it and stops before it.
    """

    @asynccontextmanager
    async def lifespan(_site: FastAPI) -> AsyncGenerator[None]:
        async with api.router.lifespan_context(api):
            if watcher is not None:
                watcher.start()
            try:
                yield
            finally:
                if watcher is not None:
                    watcher.stop()

    site = FastAPI(
        title="rlcoach",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # The root mount takes every path, so the API goes first
    site.mount("/api", api)
    if gui_dir is not None and (gui_dir / "index.html").exists():
        site.mount("/", DashboardFiles(directory=gui_dir, html=True), name="gui")
    return site


def ingest_watcher(
    config: RLCoachConfig,
    *,
    process_existing: bool,
    stats: dict[str, int] | None = None,
) -> ReplayWatcher:
    """Watch the replay folder and load each new game, printing one line each."""
    from .pipeline import IngestionStatus, process_replay_file
    from .watcher import ReplayWatcher

    counts = stats if stats is not None else {}

    def process(path: Path) -> None:
        result = process_replay_file(path, config)
        stamp = datetime.now().strftime("%H:%M:%S")
        status = result.status
        counts[status.value] = counts.get(status.value, 0) + 1
        if status == IngestionStatus.SUCCESS:
            print(f"{stamp} ✓ {path.name} -> {result.replay_id}", flush=True)
        elif status in (IngestionStatus.DUPLICATE, IngestionStatus.EXCLUDED):
            print(f"{stamp} ⊘ {path.name} ({status.value})", flush=True)
        else:
            print(f"{stamp} ✗ {path.name}: {result.error}", flush=True)

    return ReplayWatcher(
        watch_dir=config.paths.watch_folder,
        callback=process,
        poll_interval=2.0,
        stability_seconds=2.0,
        process_existing=process_existing,
    )


def redirect_output(log: Path) -> None:
    """Send print and logging output to a file.

    The background server runs under pythonw, which has no console, so
    sys.stdout and sys.stderr start out as None.
    """
    log.parent.mkdir(parents=True, exist_ok=True)
    if log.exists() and log.stat().st_size > LOG_ROTATE_BYTES:
        log.replace(log.with_name(log.name + ".1"))
    stream = open(log, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stderr = stream
    started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"--- {started} rlcoach serve, pid {os.getpid()}")


def claim_pid_file() -> None:
    pid_path().parent.mkdir(parents=True, exist_ok=True)
    pid_path().write_text(str(os.getpid()))


def release_pid_file() -> None:
    try:
        if pid_path().read_text().strip() == str(os.getpid()):
            pid_path().unlink()
    except OSError:
        pass


# Finding, starting and stopping the background server


def process_command_line(pid: int) -> str | None:
    """Return a running process's command line, or None if nothing runs as pid.

    Never probes with os.kill: on Windows any signal but Ctrl+C ends the
    process.
    """
    if sys.platform == "win32":
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}')"
                ".CommandLine",
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        line = result.stdout.strip()
        return line or None
    try:
        raw = Path(f"/proc/{int(pid)}/cmdline").read_bytes()
    except OSError:
        return None
    return raw.replace(b"\0", b" ").decode(errors="replace").strip() or None


def is_server_command(command_line: str | None) -> bool:
    if not command_line:
        return False
    lowered = command_line.lower()
    return "rlcoach" in lowered and "serve" in lowered


def running_pid(
    probe: Callable[[int], str | None] = process_command_line,
) -> int | None:
    """Return the pid of the running server, if the pid file names one.

    The command line has to be an rlcoach server, so a stale pid file that a
    new, unrelated process has reused never gets that process stopped.
    """
    try:
        pid = int(pid_path().read_text().strip())
    except OSError, ValueError:
        return None
    return pid if is_server_command(probe(pid)) else None


def server_command(port: int = DEFAULT_PORT) -> list[str]:
    """The command that runs the site in the background, with no window."""
    python = Path(sys.executable)
    windowless = python.with_name("pythonw.exe")
    if windowless.exists():
        python = windowless
    return [
        str(python),
        "-m",
        "rlcoach",
        "serve",
        "--port",
        str(port),
        "--log-file",
        str(log_path()),
    ]


def _spawn_detached(command: list[str]) -> None:
    kwargs: dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "cwd": str(Path.home()),
        "close_fds": True,
    }
    if sys.platform != "win32":
        subprocess.Popen(command, start_new_session=True, **kwargs)
        return
    detached = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        # A terminal tab can hold its commands in a job that ends them all
        # when the tab closes, so leave that job if it allows it.
        subprocess.Popen(
            command,
            creationflags=detached | subprocess.CREATE_BREAKAWAY_FROM_JOB,
            **kwargs,
        )
    except PermissionError:
        subprocess.Popen(command, creationflags=detached, **kwargs)


def site_is_up(port: int = DEFAULT_PORT) -> bool:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=2
        ) as response:
            return response.status == 200
    except urllib.error.URLError, OSError:
        return False


def start_background(port: int = DEFAULT_PORT) -> bool:
    """Start the server in the background and wait until it answers.

    Returns True once the site is up, or straight away if it already runs.
    """
    if running_pid() is not None and site_is_up(port):
        return True
    _spawn_detached(server_command(port))
    deadline = time.monotonic() + START_TIMEOUT_S
    while time.monotonic() < deadline:
        if site_is_up(port):
            return True
        time.sleep(0.5)
    return False


def stop_background(
    probe: Callable[[int], str | None] = process_command_line,
) -> bool:
    """Stop the background server. Returns False if none was running."""
    pid = running_pid(probe)
    if pid is None:
        pid_path().unlink(missing_ok=True)
        return False
    # On Windows this ends the process at once. SQLite rolls back any write
    # that was in progress, and the next start loads that replay again.
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + STOP_TIMEOUT_S
    while time.monotonic() < deadline and is_server_command(probe(pid)):
        time.sleep(0.25)
    pid_path().unlink(missing_ok=True)
    return True


# Starting at Windows sign-in


def _registry() -> Any:
    import winreg

    return winreg


def autostart_entry(registry: Any = None) -> str | None:
    """Return the sign-in command registered for rlcoach, if there is one."""
    reg = registry or _registry()
    with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY) as key:
        try:
            return reg.QueryValueEx(key, RUN_VALUE)[0]
        except FileNotFoundError:
            return None


def enable_autostart(port: int = DEFAULT_PORT, registry: Any = None) -> str:
    """Register the background server to start when you sign in to Windows.

    It goes under the current user's Run key, which needs no admin rights and
    shows up in Task Manager's Startup apps.
    """
    reg = registry or _registry()
    command = subprocess.list2cmdline(server_command(port))
    with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
        reg.SetValueEx(key, RUN_VALUE, 0, reg.REG_SZ, command)
    return command


def disable_autostart(registry: Any = None) -> bool:
    """Remove the sign-in entry. Returns False if there was none."""
    reg = registry or _registry()
    with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
        try:
            reg.DeleteValue(key, RUN_VALUE)
        except FileNotFoundError:
            return False
    return True
