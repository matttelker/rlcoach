"""Additional CLI branch coverage tests."""

from __future__ import annotations

from types import SimpleNamespace

from rlcoach.cli import (
    handle_ingest_command,
    handle_serve_command,
)


class _DummyConfig:
    def __init__(self, excluded_names: list[str] | None = None):
        self.identity = SimpleNamespace(excluded_names=excluded_names or [])

    def validate(self):
        return None


def test_ingest_loads_every_file_and_fails_if_one_does(monkeypatch):
    from rlcoach.pipeline import IngestionStatus

    seen = []
    statuses = {"a.replay": IngestionStatus.SUCCESS, "b.replay": IngestionStatus.ERROR}

    def load(path, config):
        seen.append(path.name)
        return statuses[path.name]

    monkeypatch.setattr("rlcoach.cli.get_default_config_path", lambda: "ok.toml")
    monkeypatch.setattr("rlcoach.cli.load_config", lambda _: _DummyConfig([]))
    monkeypatch.setattr("rlcoach.service.load_replay", load)

    args = SimpleNamespace(replay_files=["a.replay", "b.replay"])
    assert handle_ingest_command(args) == 1
    assert seen == ["a.replay", "b.replay"]


def test_ingest_counts_duplicates_as_fine(monkeypatch):
    from rlcoach.pipeline import IngestionStatus

    monkeypatch.setattr("rlcoach.cli.get_default_config_path", lambda: "ok.toml")
    monkeypatch.setattr("rlcoach.cli.load_config", lambda _: _DummyConfig([]))
    monkeypatch.setattr(
        "rlcoach.service.load_replay", lambda *_: IngestionStatus.DUPLICATE
    )

    assert handle_ingest_command(SimpleNamespace(replay_files=["a.replay"])) == 0


def test_ingest_without_a_config_says_so(monkeypatch, capsys):
    monkeypatch.setattr("rlcoach.cli.get_default_config_path", lambda: "missing.toml")
    monkeypatch.setattr(
        "rlcoach.cli.load_config", lambda _: (_ for _ in ()).throw(FileNotFoundError)
    )

    assert handle_ingest_command(SimpleNamespace(replay_files=["a.replay"])) == 1
    assert "Configuration error" in capsys.readouterr().err


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


def test_main_writes_utf8_when_output_is_piped(monkeypatch):
    import io
    import sys

    from rlcoach.cli import main

    raw = io.BytesIO()
    piped = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", piped)

    main([])
    print("✓ ✗")
    piped.flush()

    assert "✓ ✗" in raw.getvalue().decode("utf-8")
