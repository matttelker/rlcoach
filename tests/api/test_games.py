"""Tests for the games list and one game's page."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from rlcoach.api.app import create_app
from rlcoach.db.session import init_db, reset_engine
from tests.api.stored_games import TODAY, add_game, add_players, make_config, store


@pytest.fixture
def client(tmp_path):
    init_db(tmp_path / "test.db")

    def games(session):
        add_players(session, ("steam:1", "Rival"))
        add_game(session, "old", days_ago=5, playlist="DOUBLES", result="LOSS")
        add_game(session, "mid", days_ago=2, map_name="Arc_P")
        add_game(
            session,
            "new",
            me={"goals": 2, "assists": 1, "saves": 3, "shots": 4, "bcpm": 380.5},
            others={"steam:1": {"goals": 1, "avg_boost": 40.0}},
        )

    store(games)
    with patch("rlcoach.api.app.get_config", return_value=make_config(tmp_path)):
        yield TestClient(create_app())
    reset_engine()


def test_games_list_newest_first_with_every_field(client):
    body = client.get("/games").json()
    assert (body["total"], body["limit"], body["offset"]) == (3, 20, 0)
    assert [g["replay_id"] for g in body["items"]] == ["new", "mid", "old"]
    assert body["items"][0] == {
        "replay_id": "new",
        "played_at_utc": "2026-04-11T12:00:00",
        "play_date": TODAY.isoformat(),
        "playlist": "STANDARD",
        "result": "WIN",
        "my_score": 2,
        "opponent_score": 1,
        "map": "Stadium_P",
        "duration_seconds": 320.5,
        "overtime": False,
    }


def test_games_filter_and_page(client):
    assert [
        g["replay_id"] for g in client.get("/games?playlist=DOUBLES").json()["items"]
    ] == ["old"]
    assert client.get("/games?result=LOSS").json()["total"] == 1
    since = client.get(f"/games?date_from={TODAY.isoformat()}").json()
    assert [g["replay_id"] for g in since["items"]] == ["new"]
    page = client.get("/games?limit=1&offset=1").json()
    assert ([g["replay_id"] for g in page["items"]], page["total"]) == (["mid"], 3)


def test_games_sort_by_any_allowed_field(client):
    by_map = client.get("/games?sort=map").json()["items"]
    assert [g["map"] for g in by_map] == ["Arc_P", "Stadium_P", "Stadium_P"]
    assert (
        client.get("/games?sort=played_at_utc").json()["items"][0]["replay_id"] == "old"
    )


def test_games_refuse_unknown_sorts_and_bad_limits(client):
    assert client.get("/games?sort=-source_file").status_code == 400
    assert client.get("/games?limit=0").status_code == 422
    assert client.get("/games?limit=101").status_code == 422


def test_one_game_has_everyones_stats_with_their_names(client):
    body = client.get("/replays/new").json()
    assert body["my_team"] == "BLUE"
    assert body["overtime"] is False
    assert body["player_stats"] == [
        {
            "player_id": "epic:me",
            "display_name": "Me",
            "team": "BLUE",
            "is_me": True,
            "goals": 2,
            "assists": 1,
            "saves": 3,
            "shots": 4,
            "bcpm": 380.5,
            "avg_boost": None,
        },
        {
            "player_id": "steam:1",
            "display_name": "Rival",
            "team": "ORANGE",
            "is_me": False,
            "goals": 1,
            "assists": 0,
            "saves": 0,
            "shots": 0,
            "bcpm": None,
            "avg_boost": 40.0,
        },
    ]


def test_an_unknown_game_is_404(client):
    assert client.get("/replays/nope").status_code == 404
