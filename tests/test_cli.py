"""Tests for the rlcoach command."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from rlcoach import __version__, cli
from rlcoach.config import CONFIG_TEMPLATE
from rlcoach.db.session import reset_engine
from rlcoach.pipeline import IngestionStatus


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    yield tmp_path
    reset_engine()


def _write_config(home):
    folder = home / ".rlcoach"
    folder.mkdir(exist_ok=True)
    data_dir = json.dumps((home / "data").as_posix())
    (folder / "config.toml").write_text(
        f'[identity]\ndisplay_names = ["Me"]\n[paths]\ndata_dir = {data_dir}\n',
        encoding="utf-8",
    )


def test_no_command_prints_help(capsys):
    assert cli.main([]) == 0
    assert "ingest" in capsys.readouterr().out


def test_version(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--version"])
    assert capsys.readouterr().out.strip() == f"rlcoach {__version__}"


def test_config_init_writes_the_template_once(home, capsys):
    assert cli.main(["config", "--init"]) == 0
    path = home / ".rlcoach" / "config.toml"
    assert path.read_text(encoding="utf-8") == CONFIG_TEMPLATE
    assert cli.main(["config", "--init"]) == 1
    assert "--force" in capsys.readouterr().out
    path.write_text("changed", encoding="utf-8")
    assert cli.main(["config", "--init", "--force"]) == 0
    assert path.read_text(encoding="utf-8") == CONFIG_TEMPLATE


def test_config_validate_and_show(home, capsys):
    assert cli.main(["config", "--validate"]) == 1
    assert "config --init" in capsys.readouterr().err
    assert cli.main(["config", "--show"]) == 1
    _write_config(home)
    assert cli.main(["config", "--validate"]) == 0
    out = capsys.readouterr().out
    assert "Configuration is valid" in out and "Display names: 1" in out
    assert cli.main(["config", "--show"]) == 0
    assert 'display_names = ["Me"]' in capsys.readouterr().out
    assert cli.main(["config"]) == 1


def test_ingest_needs_a_config(home, capsys):
    assert cli.main(["ingest", "a.replay"]) == 1
    assert "Configuration error" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("statuses", "code"),
    [
        ([IngestionStatus.SUCCESS, IngestionStatus.DUPLICATE], 0),
        ([IngestionStatus.EXCLUDED], 0),
        ([IngestionStatus.SUCCESS, IngestionStatus.ERROR], 1),
        ([IngestionStatus.PLAYER_NOT_FOUND], 1),
    ],
)
def test_ingest_fails_only_when_a_replay_could_not_load(
    home, monkeypatch, statuses, code
):
    _write_config(home)
    given = []

    def load(path, config):
        given.append(path)
        return statuses[len(given) - 1]

    monkeypatch.setattr("rlcoach.service.load_replay", load)
    names = [f"{n}.replay" for n in range(len(statuses))]
    assert cli.main(["ingest", *names]) == code
    assert given == [Path(name) for name in names]
    assert (home / "data" / "rlcoach.db").exists()


def test_mistakes_reports_a_bad_file(tmp_path, capsys):
    path = tmp_path / "x.replay"
    path.write_bytes(b"not a replay")
    assert cli.main(["mistakes", str(path)]) == 1
    assert capsys.readouterr().err.startswith("Error: ")


def test_serve_runs_the_site_with_the_watcher(home, monkeypatch):
    _write_config(home)
    ran = {}
    monkeypatch.setattr("rlcoach.service.create_site", lambda *a: ("site", a))
    monkeypatch.setattr("rlcoach.service.ingest_watcher", lambda c, **k: "watcher")
    monkeypatch.setattr("rlcoach.service.claim_pid_file", lambda: None)
    monkeypatch.setattr("rlcoach.service.release_pid_file", lambda: None)
    monkeypatch.setattr("uvicorn.run", lambda site, **kw: ran.update(site=site, **kw))
    assert cli.main(["serve", "--port", "8123"]) == 0
    site, (app, _gui, watcher) = ran["site"]
    assert (site, watcher, ran["port"]) == ("site", "watcher", 8123)
    assert ran["access_log"] is True
    assert cli.main(["serve", "--no-watch"]) == 0
    assert ran["site"][1][2] is None


def test_serve_stops_without_a_config(home, monkeypatch):
    monkeypatch.setattr("uvicorn.run", lambda *a, **k: pytest.fail("ran"))
    assert cli.main(["serve"]) == 1


def test_piped_output_is_utf8(tmp_path):
    result = subprocess.run(
        [sys.executable, "-m", "rlcoach", "mistakes", str(tmp_path / "✓.replay")],
        capture_output=True,
        env={**_env(), "PYTHONIOENCODING": "cp1252"},
        check=False,
    )
    assert result.returncode == 1
    assert "✓" in result.stderr.decode("utf-8")


def _env():
    import os

    src = str(Path(__file__).resolve().parents[1] / "src")
    return {**os.environ, "PYTHONPATH": src}
