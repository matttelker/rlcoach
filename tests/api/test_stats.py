"""Tests for trends, benchmarks, and comparing your stats."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from rlcoach.api.app import create_app
from rlcoach.db.session import init_db, reset_engine
from tests.api.stored_games import (
    TODAY,
    add_benchmark,
    add_game,
    add_players,
    make_config,
    store,
)

WIN_STATS = {"goals": 3, "saves": 1, "epic_saves": 1, "bcpm": 400.0, "avg_boost": 60.0}
LOSS_STATS = {"goals": 0, "saves": 1, "epic_saves": 0, "bcpm": 300.0, "avg_boost": 60.0}


def _games(session):
    add_players(session)
    for n in range(6):
        wins = {**WIN_STATS, "goals": 3 + n % 2}
        add_game(session, f"w{n}", days_ago=n, me=wins)
        add_game(session, f"l{n}", days_ago=n, result="LOSS", me=LOSS_STATS)
    add_game(session, "two", days_ago=1, playlist="DOUBLES", me={"goals": 5})
    add_game(session, "ancient", days_ago=200, me={"goals": 9})
    add_benchmark(session, "goals", 1.0, 0.5, 1.5)
    add_benchmark(session, "avg_boost", 40.0, 30.0, 50.0)
    add_benchmark(session, "goals", 0.8, 0.4, 1.2, rank="C3")
    add_benchmark(session, "bcpm", 290.0, 250.0, 330.0)
    add_benchmark(session, "bcpm", 250.0, 210.0, 290.0, rank="C1")
    add_benchmark(session, "saves", 1.0, 0.5, 1.5)


@pytest.fixture
def client(tmp_path):
    init_db(tmp_path / "test.db")
    store(_games)
    with patch("rlcoach.api.app.get_config", return_value=make_config(tmp_path)):
        yield TestClient(create_app())
    reset_engine()


def test_trends_list_your_games_oldest_first_in_your_playlist(client):
    body = client.get("/trends?metric=goals").json()
    assert (body["metric"], body["period"], body["playlist"]) == (
        "goals",
        "30d",
        "STANDARD",
    )
    assert len(body["values"]) == 12
    assert body["values"][0]["date"] == (TODAY - timedelta(days=5)).isoformat()
    today = [v["value"] for v in body["values"] if v["date"] == TODAY.isoformat()]
    assert sorted(today) == [0, 3]
    assert len(client.get("/trends?metric=goals&period=all").json()["values"]) == 13
    doubles = client.get("/trends?metric=goals&playlist=DOUBLES").json()
    assert doubles["values"] == [{"date": doubles["values"][0]["date"], "value": 5}]


def test_trends_carry_your_ranks_average_when_it_has_one(client):
    goals = client.get("/trends?metric=goals").json()
    assert (goals["rank"], goals["rank_average"]) == ("GC", 1.0)
    assert "rank_median" not in goals
    assert client.get("/trends?metric=shots").json()["rank_average"] is None
    doubles = client.get("/trends?metric=goals&playlist=DOUBLES").json()
    assert doubles["rank_average"] is None


def test_trends_put_the_ranks_boost_collected_in_your_units(client):
    # Ballchasing counts about 5% less boost collected than we do
    body = client.get("/trends?metric=bcpm").json()
    assert body["rank_average"] == pytest.approx(290.0 * 1.051)


def test_trends_chart_the_games_own_counts_without_a_rank_average(client):
    body = client.get("/trends?metric=epic_saves").json()
    assert sorted(v["value"] for v in body["values"]) == [0] * 6 + [1] * 6
    assert body["rank_average"] is None


def test_trends_skip_games_without_the_stat_and_refuse_unknown_ones(client):
    assert client.get("/trends?metric=avg_speed_kph").json()["values"] == []
    assert client.get("/trends?metric=source_file").status_code == 400
    assert client.get("/trends?metric=goals&period=14d").status_code == 400


def test_compare_places_the_stats_that_rise_with_rank(client):
    body = client.get("/compare").json()
    assert (body["game_count"], body["target_rank"], body["playlist"]) == (
        12,
        "GC",
        "STANDARD",
    )
    assert body["min_games"] == 10
    # No game has shots, so they aren't placed
    by_metric = {p["metric"]: p for p in body["placements"]}
    assert list(by_metric) == ["bcpm", "saves"]
    # Ballchasing's 290 is 304.79 as we count, and the games swing 300 to 400
    assert by_metric["bcpm"] == {
        "metric": "bcpm",
        "games": 12,
        "my_value": 350.0,
        "target_average": 304.79,
        "gap": 45.21,
        "margin": 30.15,
        "verdict": "above",
        "level_low": "GC",
        "level_high": "GC",
        "scaled": True,
    }
    # One save every game, the GC average exactly
    saves = by_metric["saves"]
    assert (saves["gap"], saves["margin"], saves["verdict"]) == (0.0, 0.0, "level")
    assert saves["scaled"] is False


def test_compare_shows_flat_stats_beside_the_ranks_average_only(client):
    context = client.get("/compare").json()["context"]
    # No game has assists
    assert context == [
        {"metric": "avg_boost", "my_value": 60.0, "target_average": 40.0},
        {"metric": "goals", "my_value": 1.75, "target_average": 1.0},
    ]


def test_compare_without_games_and_with_a_bad_period(client):
    empty = client.get("/compare?playlist=DUEL").json()
    assert (empty["placements"], empty["context"], empty["game_count"]) == (
        [],
        [],
        0,
    )
    assert client.get("/compare?period=soon").status_code == 400


def test_compare_takes_another_rank(client):
    compare = client.get("/compare?rank=C3").json()
    assert compare["target_rank"] == "C3"
    # Only goals have a C3 average, and goals aren't placed
    assert compare["placements"] == []
    assert compare["context"] == [
        {"metric": "goals", "my_value": 1.75, "target_average": 0.8}
    ]


def test_too_few_games_place_a_stat_without_a_verdict(client):
    [bcpm, _] = client.get("/compare?period=3d").json()["placements"]
    assert (bcpm["games"], bcpm["verdict"]) == (8, "too_few")
    assert (bcpm["margin"], bcpm["level_low"], bcpm["level_high"]) == (
        None,
        None,
        None,
    )


def test_weaknesses_are_gone(client):
    assert client.get("/weaknesses").status_code == 404


def test_patterns_find_what_differs_in_wins(client):
    body = client.get("/patterns").json()
    assert (body["win_count"], body["loss_count"], body["min_games"]) == (6, 6, 5)
    assert [p["metric"] for p in body["patterns"]] == ["goals"]
    goals = body["patterns"][0]
    assert goals["direction"] == "higher_in_wins"
    assert (goals["win_avg"], goals["loss_avg"], goals["delta"]) == (3.5, 0.0, 3.5)
    assert client.get("/patterns?min_games=7").json()["patterns"] == []


def test_playlist_and_rank_fall_back_to_defaults_without_a_config(tmp_path):
    init_db(tmp_path / "test.db")
    try:
        body = TestClient(create_app()).get("/compare").json()
    finally:
        reset_engine()
    assert (body["playlist"], body["target_rank"]) == ("DOUBLES", "P1")
