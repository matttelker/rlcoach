"""Tests for running rlcoach as one always-on local site."""

from __future__ import annotations

import contextlib
import signal
import sys
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from rlcoach import service


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "home_dir", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def gui_dir(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=root></div>")
    (dist / "assets" / "app.js").write_text("console.log('app')")
    return dist


@pytest.fixture
def api(tmp_path, monkeypatch):
    """The real API, on an in-memory database since there's no config."""
    from rlcoach.api.app import create_app
    from rlcoach.db.session import reset_engine

    monkeypatch.setattr(
        "rlcoach.api.app.get_default_config_path", lambda: tmp_path / "none.toml"
    )
    yield create_app()
    reset_engine()


class RecordingWatcher:
    def __init__(self, events):
        self.events = events

    def start(self):
        self.events.append("watcher started")

    def stop(self):
        self.events.append("watcher stopped")


def test_site_serves_the_dashboard_and_its_page_paths(api, gui_dir):
    with TestClient(service.create_site(api, gui_dir)) as client:
        home = client.get("/")
        assert home.status_code == 200
        assert "id=root" in home.text
        # A reload on a dashboard page gets the dashboard, not a 404
        page = client.get("/games/abc123")
        assert page.status_code == 200
        assert "id=root" in page.text
        assert client.get("/assets/app.js").text == "console.log('app')"


def test_site_gives_a_404_for_a_missing_file_rather_than_the_page(api, gui_dir):
    with TestClient(service.create_site(api, gui_dir)) as client:
        assert client.get("/assets/old-build.js").status_code == 404


def test_site_puts_the_api_under_api(api, gui_dir):
    with TestClient(service.create_site(api, gui_dir)) as client:
        assert client.get("/api/health").json()["status"] == "healthy"
        missing = client.get("/api/no-such-endpoint")
        assert missing.status_code == 404
        assert missing.json() == {"detail": "Not Found"}


def test_site_without_a_built_dashboard_serves_the_api_only(api, tmp_path):
    with TestClient(service.create_site(api, tmp_path / "missing")) as client:
        assert client.get("/").status_code == 404
        assert client.get("/api/health").status_code == 200


def test_watcher_runs_inside_the_apis_startup_and_shutdown():
    events = []

    @asynccontextmanager
    async def lifespan(_app):
        events.append("database open")
        yield
        events.append("database closed")

    api = FastAPI(lifespan=lifespan)
    site = service.create_site(api, None, RecordingWatcher(events))
    with TestClient(site):
        assert events == ["database open", "watcher started"]
    assert events == [
        "database open",
        "watcher started",
        "watcher stopped",
        "database closed",
    ]


def test_ingest_watcher_loads_each_replay_and_counts_it(monkeypatch, tmp_path, capsys):
    from types import SimpleNamespace

    from rlcoach.pipeline import IngestionResult, IngestionStatus

    results = iter(
        [
            IngestionResult(IngestionStatus.SUCCESS, tmp_path, replay_id="abc"),
            IngestionResult(IngestionStatus.DUPLICATE, tmp_path),
            IngestionResult(IngestionStatus.ERROR, tmp_path, error="bad file"),
        ]
    )
    monkeypatch.setattr(
        "rlcoach.pipeline.process_replay_file", lambda path, config: next(results)
    )
    config = SimpleNamespace(paths=SimpleNamespace(watch_folder=tmp_path))
    stats = {}
    watcher = service.ingest_watcher(config, process_existing=True, stats=stats)
    for name in ("a", "b", "c"):
        watcher.callback(tmp_path / f"{name}.replay")

    assert stats == {"success": 1, "duplicate": 1, "error": 1}
    out = capsys.readouterr().out
    assert "✓ a.replay -> abc" in out
    assert "⊘ b.replay (duplicate)" in out
    assert "✗ c.replay: bad file" in out


SERVER = "C:\\py\\pythonw.exe -m rlcoach serve --port 8000"


def test_running_pid_reads_the_pid_file(home):
    service.pid_path().write_text("1234")
    assert service.running_pid(lambda pid: SERVER if pid == 1234 else None) == 1234


def test_running_pid_ignores_a_pid_reused_by_another_program(home):
    service.pid_path().write_text("1234")
    assert service.running_pid(lambda pid: "python other_script.py") is None


@pytest.mark.parametrize("contents", [None, "", "not a pid"])
def test_running_pid_without_a_usable_pid_file(home, contents):
    if contents is not None:
        service.pid_path().write_text(contents)
    assert service.running_pid(lambda pid: SERVER) is None


def test_stop_ends_the_server_and_clears_the_pid_file(home, monkeypatch):
    service.pid_path().write_text("1234")
    killed = []
    monkeypatch.setattr(service.os, "kill", lambda pid, sig: killed.append((pid, sig)))

    def probe(pid):
        return None if killed else SERVER

    assert service.stop_background(probe) is True
    assert killed == [(1234, signal.SIGTERM)]
    assert not service.pid_path().exists()


def test_stop_never_ends_a_process_it_cant_name(home, monkeypatch):
    service.pid_path().write_text("1234")
    monkeypatch.setattr(
        service.os, "kill", lambda pid, sig: pytest.fail("ended a stranger")
    )
    assert service.stop_background(lambda pid: "notepad.exe") is False
    assert not service.pid_path().exists()


def test_pid_file_is_only_released_by_its_own_server(home):
    service.claim_pid_file()
    service.pid_path().write_text("1")
    service.release_pid_file()
    assert service.pid_path().read_text() == "1"

    service.claim_pid_file()
    service.release_pid_file()
    assert not service.pid_path().exists()


def test_server_command_runs_serve_with_its_log(home):
    command = service.server_command(8123)
    assert command[1:6] == ["-m", "rlcoach", "serve", "--port", "8123"]
    assert command[6:] == ["--log-file", str(home / "serve.log")]


def test_redirect_output_starts_a_new_log_when_the_old_one_is_big(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(sys, "stdout", sys.stdout)
    monkeypatch.setattr(sys, "stderr", sys.stderr)
    monkeypatch.setattr(service, "LOG_ROTATE_BYTES", 10)
    log = tmp_path / "serve.log"
    log.write_text("old output, longer than ten bytes")

    service.redirect_output(log)
    print("✓ a replay")
    sys.stdout.close()

    assert (tmp_path / "serve.log.1").read_text().startswith("old output")
    assert "✓ a replay" in log.read_text(encoding="utf-8")


class FakeRegistry:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}

    def OpenKey(self, root, path, reserved=0, access=0):  # noqa: N802
        assert (root, path) == ("HKCU", service.RUN_KEY)
        return contextlib.nullcontext(self.values)

    def QueryValueEx(self, key, name):  # noqa: N802
        if name not in key:
            raise FileNotFoundError(name)
        return key[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        key[name] = value

    def DeleteValue(self, key, name):  # noqa: N802
        if name not in key:
            raise FileNotFoundError(name)
        del key[name]


def test_autostart_registers_the_background_server(home):
    registry = FakeRegistry()
    assert service.autostart_entry(registry) is None

    command = service.enable_autostart(8000, registry)
    assert registry.values == {"rlcoach": command}
    assert "rlcoach serve --port 8000 --log-file" in command
    assert service.autostart_entry(registry) == command


def test_autostart_off_removes_the_entry_once(home):
    registry = FakeRegistry()
    service.enable_autostart(8000, registry)
    assert service.disable_autostart(registry) is True
    assert service.disable_autostart(registry) is False
    assert service.autostart_entry(registry) is None
