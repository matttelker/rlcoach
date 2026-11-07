"""Tests for the players list, one player, and tagging teammates."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from rlcoach.api.app import create_app
from rlcoach.db.session import init_db, reset_engine
from tests.api.stored_games import add_game, add_players, make_config, store


@pytest.fixture
def client(tmp_path):
    init_db(tmp_path / "test.db")

    def games(session):
        add_players(
            session, ("steam:1", "Often"), ("epic:2", "Once"), ("psn:3", "Never")
        )
        add_game(session, "a", others={"steam:1": {}, "epic:2": {}})
        add_game(session, "b", others={"steam:1": {}})

    store(games)
    with patch("rlcoach.api.app.get_config", return_value=make_config(tmp_path)):
        yield TestClient(create_app())
    reset_engine()


def _names(body):
    return [p["display_name"] for p in body["items"]]


def test_players_leave_you_out_and_count_games_together(client):
    body = client.get("/players").json()
    assert _names(body) == ["Often", "Once", "Never"]
    assert body["total"] == 3
    assert body["items"][0] == {
        "player_id": "steam:1",
        "display_name": "Often",
        "platform": "steam",
        "is_me": False,
        "is_tagged_teammate": False,
        "teammate_notes": None,
        "games_with_me": 2,
        "first_seen_utc": "2026-01-01T00:00:00",
        "last_seen_utc": "2026-02-01T00:00:00",
    }


def test_players_sort_filter_and_page(client):
    assert _names(client.get("/players?sort=games_with_me").json()) == [
        "Never",
        "Once",
        "Often",
    ]
    assert _names(client.get("/players?min_games=1").json()) == ["Often", "Once"]
    assert _names(client.get("/players?limit=1&offset=1").json()) == ["Once"]
    assert client.get("/players?sort=is_me").status_code == 400


def test_one_player_and_you(client):
    assert client.get("/players/epic:2").json()["games_with_me"] == 1
    me = client.get("/players/epic:me").json()
    assert (me["is_me"], me["games_with_me"]) == (True, 0)
    assert client.get("/players/nobody").status_code == 404


def test_tagging_a_teammate_keeps_notes_unless_given(client):
    tagged = client.post("/players/steam:1/tag", json={"notes": "Duo partner"}).json()
    assert tagged == {
        "player_id": "steam:1",
        "display_name": "Often",
        "is_tagged_teammate": True,
        "teammate_notes": "Duo partner",
    }
    untagged = client.post("/players/steam:1/tag", json={"tagged": False}).json()
    assert (untagged["is_tagged_teammate"], untagged["teammate_notes"]) == (
        False,
        "Duo partner",
    )
    assert client.post("/players/nobody/tag", json={}).status_code == 404


def test_tagged_filter_and_tagging_leaves_last_seen_alone(client):
    client.post("/players/epic:2/tag", json={})
    assert _names(client.get("/players?tagged=true").json()) == ["Once"]
    player = client.get("/players/epic:2").json()
    assert player["last_seen_utc"] == "2026-02-01T00:00:00"
