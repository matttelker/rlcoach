"""Tests for the coaching endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from rlcoach.analysis.mistakes import GoalMoment, GoalReview, Mistake, MistakeReport


@pytest.fixture
def config(tmp_path):
    from rlcoach.config import (
        IdentityConfig,
        PathsConfig,
        PreferencesConfig,
        RLCoachConfig,
    )

    config = RLCoachConfig(
        identity=IdentityConfig(platform_ids=["epic:me"], display_names=["Me"]),
        paths=PathsConfig(
            watch_folder=tmp_path / "replays",
            data_dir=tmp_path / "data",
            reports_dir=tmp_path / "reports",
        ),
        preferences=PreferencesConfig(primary_playlist="STANDARD", target_rank="GC1"),
    )
    config.paths.data_dir.mkdir(parents=True, exist_ok=True)
    return config


def _flag(kind, category, seconds_left, cost_goal=False):
    return Mistake(
        kind=kind,
        t=300.0 - seconds_left,
        frame=0,
        clock=f"{int(seconds_left) // 60}:{int(seconds_left) % 60:02d}",
        score="0-0",
        duration=0.0,
        what="What happened.",
        instead="What to do.",
        category=category,
        seconds_left=seconds_left,
        cost_goal=cost_goal,
    )


def _review(flags, timeline, against=()):
    return MistakeReport(
        player="Me",
        team="ORANGE",
        map_name="Stadium_P",
        final_score="",
        goals=list(against),
        mistakes=list(flags),
        clears={"clears": 2, "given_back": 1},
        player_id="epic:me",
        goal_timeline=list(timeline),
    )


@pytest.fixture
def client(config):
    from rlcoach.db.models import Player, PlayerGameStats, Replay
    from rlcoach.db.reviews import save_review
    from rlcoach.db.session import create_session, init_db, reset_engine

    init_db(config.db_path)
    session = create_session()
    session.add(Player(player_id="epic:me", display_name="Me", is_me=True))
    today = date.today()
    games = [
        # replay_id, play_date, result, score
        ("old", today - timedelta(days=3), "LOSS", (1, 2)),
        ("win", today, "WIN", (2, 1)),
        ("unreviewed", today, "LOSS", (0, 3)),
    ]
    for n, (replay_id, day, result, (mine, theirs)) in enumerate(games):
        session.add(
            Replay(
                replay_id=replay_id,
                source_file=f"/replays/{replay_id}.replay",
                file_hash=replay_id,
                played_at_utc=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=n),
                play_date=day,
                map="Stadium_P",
                playlist="STANDARD",
                team_size=3,
                duration_seconds=400.0,
                my_player_id="epic:me",
                my_team="ORANGE",
                my_score=mine,
                opponent_score=theirs,
                result=result,
            )
        )
        session.add(
            PlayerGameStats(
                replay_id=replay_id,
                player_id="epic:me",
                team="ORANGE",
                is_me=True,
                goals=mine,
            )
        )
    session.commit()
    session.close()

    against = GoalReview(
        t=200.0,
        clock="1:40",
        score="1-1",
        scorer="Them",
        on_you=True,
        summary="You were the last one back.",
        lines=("You were beaten by the shot (10 boost)",),
        seconds_left=100.0,
    )
    save_review(
        "old",
        "epic:me",
        _review(
            [
                _flag("last_back_upfield", "last_back", 101.0, cost_goal=True),
                _flag("clear_given_back", "clearing", 200.0),
                _flag("clear_given_back", "clearing", 150.0),
            ],
            [
                GoalMoment(
                    200.0,
                    "1:40",
                    100.0,
                    "1-1",
                    False,
                    "Them",
                    False,
                    False,
                    False,
                    False,
                )
            ],
            [against],
        ),
    )
    save_review(
        "win",
        "epic:me",
        _review(
            [_flag("caught_upfield", "rotation", 250.0)],
            [
                GoalMoment(
                    50.0, "4:10", 250.0, "0-0", True, "You", True, False, False, False
                ),
                GoalMoment(
                    90.0,
                    "3:30",
                    210.0,
                    "1-0",
                    False,
                    "Them",
                    False,
                    False,
                    False,
                    False,
                ),
                GoalMoment(
                    250.0, "0:50", 50.0, "1-1", True, "You", True, False, True, False
                ),
            ],
            [
                GoalReview(
                    90.0, "3:30", "1-0", "Them", False, "No mistake found.", (), 210.0
                ),
            ],
        ),
    )

    with patch("rlcoach.api.app.get_config", return_value=config):
        from rlcoach.api.app import create_app

        yield TestClient(create_app())
    reset_engine()


def test_coach_counts_reviewed_and_unreviewed_games(client):
    data = client.get("/coach").json()
    assert data["playlist"] == "STANDARD"
    assert data["game_count"] == 3
    assert data["reviewed_count"] == 2


def test_coach_ranks_targets_by_goals_cost(client):
    targets = client.get("/coach").json()["targets"]
    assert [t["category"] for t in targets] == ["last_back", "clearing", "rotation"]
    assert targets[0]["goals_cost"] == 1
    assert targets[0]["cue"]


def test_coach_lists_every_category(client):
    categories = client.get("/coach").json()["categories"]
    assert [c["category"] for c in categories] == [
        "last_back",
        "rotation",
        "clearing",
        "goalkeeping",
        "boost",
    ]


def test_coach_session_is_the_latest_day_newest_game_first(client):
    session = client.get("/coach").json()["session"]
    assert session["play_date"] == date.today().isoformat()
    assert (session["wins"], session["losses"]) == (1, 1)
    games = session["games"]
    assert [g["replay_id"] for g in games] == ["unreviewed", "win"]
    assert games[0]["reviewed"] is False and games[0]["flags"] is None
    assert games[1]["flags"] == 1 and games[1]["goals_on_me"] == 0


def test_coach_highlights_the_winner(client):
    highlights = client.get("/coach").json()["highlights"]
    winner = next(h for h in highlights if h["kind"] == "winner")
    assert winner["replay_id"] == "win"
    assert "0:50 left" in winner["detail"]


def test_coach_period_filters_old_games(client):
    data = client.get("/coach", params={"period": "1d"}).json()
    assert data["game_count"] == 2


def test_coach_rejects_a_bad_period(client):
    assert client.get("/coach", params={"period": "soon"}).status_code == 400


def _add_newer_game(replay_id, playlist, day=1):
    """A game played after every game in the fixture, on February ``day``."""
    from rlcoach.db.models import Replay
    from rlcoach.db.session import create_session

    session = create_session()
    session.add(
        Replay(
            replay_id=replay_id,
            source_file=f"/replays/{replay_id}.replay",
            file_hash=replay_id,
            played_at_utc=datetime(2026, 2, day, tzinfo=UTC),
            play_date=date.today(),
            map="Stadium_P",
            playlist=playlist,
            team_size=2,
            duration_seconds=300.0,
            my_player_id="epic:me",
            my_team="BLUE",
            my_score=3,
            opponent_score=1,
            result="WIN",
        )
    )
    session.commit()
    session.close()


def test_coach_follows_the_playlist_of_your_latest_game(client):
    _add_newer_game("doubles", "DOUBLES")
    data = client.get("/coach").json()
    assert data["playlist"] == "DOUBLES"
    assert [g["replay_id"] for g in data["session"]["games"]] == ["doubles"]


def test_coach_keeps_the_playlist_you_ask_for(client):
    _add_newer_game("doubles", "DOUBLES")
    data = client.get("/coach", params={"playlist": "STANDARD"}).json()
    assert data["playlist"] == "STANDARD"


def test_coach_skips_a_latest_game_the_dashboard_has_no_view_for(client):
    _add_newer_game("doubles", "DOUBLES", day=1)
    _add_newer_game("hoops", "EXTRA_MODE", day=2)
    assert client.get("/coach").json()["playlist"] == "DOUBLES"


def test_coach_falls_back_to_the_configured_playlist_with_no_games(config):
    from rlcoach.db.session import init_db, reset_engine

    config.preferences.primary_playlist = "DUEL"
    init_db(config.db_path)
    with patch("rlcoach.api.app.get_config", return_value=config):
        from rlcoach.api.app import create_app

        data = TestClient(create_app()).get("/coach").json()
    reset_engine()
    assert data["playlist"] == "DUEL"
    assert data["game_count"] == 0


def test_replay_review_returns_flags_and_goals_on_the_clock(client):
    data = client.get("/replays/old/review").json()
    assert data["status"] == "ok"
    assert (data["clears"], data["clears_given_back"]) == (2, 1)
    assert [m["category_label"] for m in data["mistakes"]] == [
        "Clearing",
        "Clearing",
        "Last back",
    ]
    assert data["mistakes"][-1]["label"] == "Last back upfield"
    assert data["goals"][0]["on_me"] is True
    assert data["goals"][0]["lines"] == ["You were beaten by the shot (10 boost)"]


def test_replay_review_reports_a_missing_review(client):
    data = client.get("/replays/unreviewed/review").json()
    assert data["status"] == "missing"
    assert data["mistakes"] == []


def test_replay_review_404s_for_an_unknown_game(client):
    assert client.get("/replays/nope/review").status_code == 404
