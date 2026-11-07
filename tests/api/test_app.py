"""Tests for the API starting up with or without a config."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from rlcoach.api.app import create_app, get_config
from rlcoach.db.session import reset_engine


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    yield tmp_path
    reset_engine()


def _write_config(home):
    (home / ".rlcoach").mkdir()
    data_dir = json.dumps((home / "data").as_posix())
    (home / ".rlcoach" / "config.toml").write_text(
        f'[identity]\ndisplay_names = ["Me"]\n[paths]\ndata_dir = {data_dir}\n',
        encoding="utf-8",
    )


def test_starting_opens_your_database_and_loads_the_benchmarks(home):
    _write_config(home)
    with TestClient(create_app()) as client:
        assert get_config().identity.display_names == ["Me"]
        health = client.get("/health").json()
        benchmarks = client.get("/benchmarks").json()["items"]
    assert (home / "data" / "rlcoach.db").exists()
    assert health["status"] == "healthy"
    assert health["checks"] == {"database": "connected"}
    assert {b["playlist"] for b in benchmarks} == {"DOUBLES", "STANDARD"}
    with pytest.raises(RuntimeError):
        get_config()


def test_without_a_config_it_still_answers_from_memory(home):
    with TestClient(create_app()) as client:
        assert client.get("/health").json()["status"] == "healthy"
        assert client.get("/games").json()["total"] == 0
        with pytest.raises(RuntimeError):
            get_config()
