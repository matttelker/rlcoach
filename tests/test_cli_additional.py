"""Additional CLI branch coverage tests."""

from __future__ import annotations

from types import SimpleNamespace

from rlcoach.cli import (
    handle_ingest_command,
    handle_serve_command,
)
from rlcoach.errors import RLCoachError


class _DummyConfig:
    def __init__(self, excluded_names: list[str] | None = None):
        self.identity = SimpleNamespace(excluded_names=excluded_names or [])

    def validate(self):
        return None


def test_handle_ingest_watch_delegates(monkeypatch):
    args = SimpleNamespace(watch=True, process_existing=False)
    monkeypatch.setattr(
        "rlcoach.cli.handle_ingest_watch", lambda a: 9 if a is args else 1
    )
    assert handle_ingest_command(args) == 9


def test_handle_ingest_requires_file_when_not_watching(capsys):
    args = SimpleNamespace(watch=False, replay_file=None, json=False)
    assert handle_ingest_command(args) == 1
    assert "replay_file is required" in capsys.readouterr().out


def test_handle_ingest_json_success(monkeypatch, capsys):
    args = SimpleNamespace(watch=False, replay_file="x.replay", json=True)
    monkeypatch.setattr(
        "rlcoach.cli.ingest_replay",
        lambda _p: {
            "file_path": "x.replay",
            "sha256": "abc",
            "size_human": "1 KB",
            "size_bytes": 1000,
            "bounds_check": {"message": "ok"},
            "format_check": {"message": "ok"},
            "crc_check": {"message": "ok"},
            "warnings": [],
            "status": "ok",
        },
    )
    assert handle_ingest_command(args) == 0
    assert '"sha256": "abc"' in capsys.readouterr().out


def test_handle_ingest_json_rlcoach_error(monkeypatch, capsys):
    args = SimpleNamespace(watch=False, replay_file="x.replay", json=True)
    monkeypatch.setattr(
        "rlcoach.cli.ingest_replay",
        lambda _p: (_ for _ in ()).throw(
            RLCoachError("boom", {"suggested_action": "try again"})
        ),
    )
    assert handle_ingest_command(args) == 1
    assert '"status": "error"' in capsys.readouterr().out


def test_handle_serve_command_missing_config(monkeypatch, capsys):
    args = SimpleNamespace(host="127.0.0.1", port=8000)
    monkeypatch.setattr("rlcoach.cli.get_default_config_path", lambda: "missing.toml")
    monkeypatch.setattr(
        "rlcoach.cli.load_config", lambda _: (_ for _ in ()).throw(FileNotFoundError)
    )
    assert handle_serve_command(args) == 1
    out = capsys.readouterr().out
    assert "config file not found" in out.lower()


def test_handle_serve_command_runs_the_site(monkeypatch, tmp_path):
    from rlcoach import service

    args = SimpleNamespace(host="0.0.0.0", port=9999, no_watch=True)
    monkeypatch.setattr("rlcoach.cli.get_default_config_path", lambda: "ok.toml")
    monkeypatch.setattr("rlcoach.cli.load_config", lambda _: _DummyConfig([]))
    monkeypatch.setattr(service, "home_dir", lambda: tmp_path)
    monkeypatch.setattr("rlcoach.api.create_app", lambda: "api")
    monkeypatch.setattr(
        service, "create_site", lambda api, gui, watcher: ("site", api, watcher)
    )

    called = {}

    def fake_run(app, host, port, **kwargs):
        called.update(app=app, host=host, port=port, **kwargs)
        assert service.pid_path().exists()

    monkeypatch.setattr("uvicorn.run", fake_run)

    assert handle_serve_command(args) == 0
    assert called["app"] == ("site", "api", None)
    assert (called["host"], called["port"]) == ("0.0.0.0", 9999)
    assert called["access_log"] is True
    assert not service.pid_path().exists()
