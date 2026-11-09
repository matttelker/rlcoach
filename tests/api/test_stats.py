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
LOSS_STATS = {"goals": 0, "saves": 1, "bcpm": 300.0, "avg_boost": 60.0}


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


def test_trends_carry_your_ranks_median_when_it_has_one(client):
    goals = client.get("/trends?metric=goals").json()
    assert (goals["rank"], goals["rank_median"]) == ("GC", 1.0)
    assert client.get("/trends?metric=saves").json()["rank_median"] is None
    doubles = client.get("/trends?metric=goals&playlist=DOUBLES").json()
    assert doubles["rank_median"] is None


def test_trends_chart_the_games_own_counts_without_a_rank_median(client):
    body = client.get("/trends?metric=epic_saves").json()
    assert sorted(v["value"] for v in body["values"]) == [0] * 6 + [1] * 6
    assert body["rank_median"] is None


def test_trends_skip_games_without_the_stat_and_refuse_unknown_ones(client):
    assert client.get("/trends?metric=avg_speed_kph").json()["values"] == []
    assert client.get("/trends?metric=source_file").status_code == 400
    assert client.get("/trends?metric=goals&period=14d").status_code == 400


def test_benchmarks_filter_by_rank(client):
    items = client.get("/benchmarks?rank=GC").json()["items"]
    assert [b["metric"] for b in items] == ["avg_boost", "goals"]
    assert items[1] == {
        "metric": "goals",
        "playlist": "STANDARD",
        "rank_tier": "GC",
        "median_value": 1.0,
        "p25_value": 0.5,
        "p75_value": 1.5,
        "elite_threshold": pytest.approx(1.8),
        "source": "test",
    }


def test_compare_gives_each_stats_gap_and_which_way_is_better(client):
    body = client.get("/compare").json()
    assert (body["game_count"], body["target_rank"]) == (12, "GC")
    by_metric = {c["metric"]: c for c in body["comparisons"]}
    assert list(by_metric) == [
        "bcpm",
        "avg_boost",
        "goals",
        "assists",
        "saves",
        "shots",
    ]
    assert by_metric["goals"] == {
        "metric": "goals",
        "my_value": 1.75,
        "target_median": 1.0,
        "difference": 0.75,
        "difference_pct": 75.0,
        "direction": "higher",
    }
    assert by_metric["avg_boost"]["direction"] == "lower"
    assert by_metric["bcpm"]["target_median"] is None
    assert by_metric["bcpm"]["difference_pct"] is None


def test_compare_without_games_and_with_a_bad_period(client):
    empty = client.get("/compare?playlist=DUEL").json()
    assert (empty["comparisons"], empty["game_count"]) == ([], 0)
    assert client.get("/compare?period=soon").status_code == 400


def test_compare_and_weaknesses_take_another_rank(client):
    compare = client.get("/compare?rank=C3").json()
    goals = next(c for c in compare["comparisons"] if c["metric"] == "goals")
    assert (compare["target_rank"], goals["target_median"]) == ("C3", 0.8)
    weaknesses = client.get("/weaknesses?rank=C3").json()
    assert (weaknesses["rank"], weaknesses["has_benchmarks"]) == ("C3", True)
    assert [s["target_median"] for s in weaknesses["strengths"]] == [0.8]


def test_patterns_find_what_differs_in_wins(client):
    body = client.get("/patterns").json()
    assert (body["win_count"], body["loss_count"], body["min_games"]) == (6, 6, 5)
    assert [p["metric"] for p in body["patterns"]] == ["goals"]
    goals = body["patterns"][0]
    assert goals["direction"] == "higher_in_wins"
    assert (goals["win_avg"], goals["loss_avg"], goals["delta"]) == (3.5, 0.0, 3.5)
    assert client.get("/patterns?min_games=7").json()["patterns"] == []


def test_holding_too_much_boost_is_a_weakness_and_goals_a_strength(client):
    body = client.get("/weaknesses").json()
    assert (body["rank"], body["has_benchmarks"]) == ("GC", True)
    assert [w["metric"] for w in body["weaknesses"]] == ["avg_boost"]
    assert body["weaknesses"][0]["severity"] == "high"
    assert body["strengths"] == [
        {
            "metric": "goals",
            "my_value": 1.75,
            "target_median": 1.0,
            "z_score": 1.01,
            "severity": "strength",
        }
    ]


def test_weaknesses_say_when_there_are_no_benchmarks(client):
    assert client.get("/weaknesses?rank=G1").json()["has_benchmarks"] is False
    empty = client.get("/weaknesses?playlist=DUEL").json()
    assert (empty["game_count"], empty["has_benchmarks"]) == (0, False)


def test_playlist_and_rank_fall_back_to_defaults_without_a_config(tmp_path):
    init_db(tmp_path / "test.db")
    try:
        body = TestClient(create_app()).get("/compare").json()
    finally:
        reset_engine()
    assert (body["playlist"], body["target_rank"]) == ("DOUBLES", "P1")
