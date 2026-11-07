"""Tests for watching the replay folder."""

from __future__ import annotations

import os
import time

from rlcoach.watcher import ReplayWatcher


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def _replay(folder, name, mtime, size=100):
    path = folder / name
    path.write_bytes(b"x" * size)
    os.utime(path, ns=(mtime, mtime))
    return path


def _watcher(folder, seen, **kwargs):
    clock = Clock()
    watcher = ReplayWatcher(folder, seen.append, clock=clock, **kwargs)
    return watcher, clock


def test_a_replay_is_handed_over_once_after_it_settles(tmp_path):
    seen = []
    watcher, clock = _watcher(tmp_path, seen, settle_seconds=2.0)
    path = _replay(tmp_path, "a.replay", 1_000_000_000)
    watcher.scan()
    clock.now = 1.0
    watcher.scan()
    assert seen == []
    clock.now = 2.5
    watcher.scan()
    clock.now = 10.0
    watcher.scan()
    assert seen == [path]


def test_a_growing_file_waits_until_it_stops_changing(tmp_path):
    seen = []
    watcher, clock = _watcher(tmp_path, seen, settle_seconds=2.0)
    path = _replay(tmp_path, "a.replay", 1_000_000_000, size=10)
    watcher.scan()
    clock.now = 3.0
    _replay(tmp_path, "a.replay", 2_000_000_000, size=20)
    watcher.scan()
    assert seen == []
    clock.now = 4.0
    watcher.scan()
    assert seen == []
    clock.now = 5.0
    watcher.scan()
    assert seen == [path]


def test_replays_go_oldest_first_and_other_files_are_ignored(tmp_path):
    seen = []
    watcher, clock = _watcher(tmp_path, seen, settle_seconds=0)
    newer = _replay(tmp_path, "a.replay", 3_000_000_000)
    older = _replay(tmp_path, "b.replay", 1_000_000_000)
    _replay(tmp_path, "notes.txt", 2_000_000_000)
    watcher.scan()
    watcher.scan()
    assert seen == [older, newer]


def test_a_failing_callback_is_logged_and_not_retried(tmp_path, caplog):
    calls = []

    def fail(path):
        calls.append(path)
        raise RuntimeError("bad replay")

    watcher = ReplayWatcher(tmp_path, fail, settle_seconds=0, clock=Clock())
    _replay(tmp_path, "a.replay", 1_000_000_000)
    good = _replay(tmp_path, "b.replay", 2_000_000_000)
    watcher.scan()
    watcher.scan()
    watcher.scan()
    assert len(calls) == 2 and calls[1] == good
    assert "Couldn't load" in caplog.text


def test_a_missing_folder_is_waited_for(tmp_path):
    seen = []
    folder = tmp_path / "Demos"
    watcher, _ = _watcher(folder, seen, settle_seconds=0)
    watcher.scan()
    folder.mkdir()
    path = _replay(folder, "a.replay", 1_000_000_000)
    watcher.scan()
    watcher.scan()
    assert seen == [path]


def _wait_for(condition, seconds=5.0):
    deadline = time.monotonic() + seconds
    while not condition() and time.monotonic() < deadline:
        time.sleep(0.01)
    return condition()


def test_the_thread_loads_existing_replays_and_stops(tmp_path):
    seen = []
    path = _replay(tmp_path, "a.replay", 1_000_000_000)
    watcher = ReplayWatcher(tmp_path, seen.append, poll_seconds=0.01, settle_seconds=0)
    watcher.start()
    try:
        assert _wait_for(lambda: seen == [path])
    finally:
        watcher.stop()
    assert watcher._thread is None


def test_existing_replays_can_be_skipped(tmp_path):
    seen = []
    _replay(tmp_path, "old.replay", 1_000_000_000)
    watcher = ReplayWatcher(
        tmp_path,
        seen.append,
        poll_seconds=0.01,
        settle_seconds=0,
        process_existing=False,
    )
    watcher.start()
    try:
        new = _replay(tmp_path, "new.replay", 2_000_000_000)
        assert _wait_for(lambda: seen == [new])
    finally:
        watcher.stop()
