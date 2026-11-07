"""Watch the replay folder and hand each new replay to a callback.

Rocket League writes a replay about 30 seconds after the match, and OneDrive
may still be syncing it, so a file is only handed over once its size and
modified time have held still between scans for a couple of seconds. Polling
works the same on synced and local folders, where file events don't.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class ReplayWatcher:
    """Calls `callback(path)` once for each replay that settles in `folder`.

    A replay that fails isn't retried until the watcher restarts, when every
    file is offered again and stored ones are skipped by their hash.
    """

    def __init__(
        self,
        folder: Path,
        callback: Callable[[Path], object],
        *,
        poll_seconds: float = 2.0,
        settle_seconds: float = 2.0,
        process_existing: bool = True,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.folder = folder
        self.callback = callback
        self.poll_seconds = poll_seconds
        self.settle_seconds = settle_seconds
        self.process_existing = process_existing
        self._clock = clock
        self._done: set[Path] = set()
        # Each unsettled file's last (size, mtime), and when that was first seen
        self._pending: dict[Path, tuple[tuple[int, int], float]] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _replays(self) -> list[Path]:
        """The folder's replays, oldest first, so games load in the order played."""
        found = []
        for path in self.folder.glob("*.replay"):
            try:
                found.append((path.stat().st_mtime_ns, path))
            except OSError:
                continue
        return [path for _, path in sorted(found)]

    def scan(self) -> None:
        """Hand over every replay that has settled since the last scan."""
        if not self.folder.is_dir():
            return
        now = self._clock()
        for path in self._replays():
            if self._stop.is_set():
                return
            if path in self._done:
                continue
            try:
                stat = path.stat()
            except OSError:
                continue
            state = (stat.st_size, stat.st_mtime_ns)
            last = self._pending.get(path)
            if last is None or last[0] != state:
                self._pending[path] = (state, now)
                continue
            if now - last[1] < self.settle_seconds:
                continue
            del self._pending[path]
            self._done.add(path)
            try:
                self.callback(path)
            except Exception:
                logger.exception("Couldn't load %s", path)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.scan()
            except Exception:
                logger.exception("Couldn't scan %s", self.folder)
            self._stop.wait(self.poll_seconds)

    def start(self) -> None:
        """Start watching on a background thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        if not self.process_existing and self.folder.is_dir():
            self._done.update(self._replays())
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("Watching %s", self.folder)

    def stop(self) -> None:
        """Stop watching, after the replay being loaded, if any, finishes."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._thread = None
