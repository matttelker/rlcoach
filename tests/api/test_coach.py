"""Tests for the coaching endpoints."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from rlcoach.analysis.mistakes import (
    GoalMoment,
    GoalReview,
    KickoffMoment,
    Mistake,
    MistakeReport,
)
from rlcoach.analysis.situations import Situation
from rlcoach.events.kickoffs import KickoffEvent, KickoffPlayer


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
        ),
        preferences=PreferencesConfig(primary_playlist="STANDARD", target_rank="GC"),
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


def _no_flip_kickoff():
    """You went at 86 s without a flip, and they scored 2 s after the hit."""
    me = KickoffPlayer(
        "epic:me", "GO", "STANDARD_BOOST", 33.0, 2.0, team=1, spot="DIAGONAL"
    )
    them = KickoffPlayer(
        "epic:them", "GO", "STANDARD_DIAGONAL", 33.0, 2.0, team=0, spot="DIAGONAL"
    )
    kickoff = KickoffEvent(
        t_start=86.0,
        players=(me, them),
        first_touch_player="epic:them",
        time_to_first_touch=2.0,
        first_touch_team="BLUE",
        ball_y_after=900.0,  # Toward orange's net
    )
    return KickoffMoment(86.0, "3:34", 214.0, "1-0", kickoff)


def _review(flags, timeline, against=(), kickoffs=()):
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
        kickoffs=list(kickoffs),
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
                epic_saves=1 if replay_id == "win" else 0,
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
            [_no_flip_kickoff()],
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
        "kickoffs",
        "whiffs",
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


def test_coach_highlights_an_epic_save(client):
    highlights = client.get("/coach").json()["highlights"]
    [save] = [h for h in highlights if h["kind"] == "epic_save"]
    assert (save["title"], save["replay_id"]) == ("Epic save", "win")


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


def test_coach_shows_several_playlists_together(client):
    _add_newer_game("doubles", "DOUBLES")
    data = client.get("/coach", params={"playlist": "DOUBLES,STANDARD"}).json()
    assert data["playlist"] == "DOUBLES,STANDARD"
    assert data["game_count"] == 4
    games = data["session"]["games"]
    assert [g["replay_id"] for g in games] == ["doubles", "unreviewed", "win"]
    assert [g["playlist"] for g in games] == ["DOUBLES", "STANDARD", "STANDARD"]


def test_coach_rejects_an_empty_playlist_list(client):
    assert client.get("/coach", params={"playlist": ","}).status_code == 400


def _add_benchmark(metric, playlist, average):
    from rlcoach.db.session import create_session
    from tests.api.stored_games import add_benchmark

    with create_session() as session:
        add_benchmark(session, metric, average, average / 2, average * 1.5, playlist)
        session.commit()


def _add_games_with(playlist, saves, goals=5):
    """Games of yours in a playlist, one for each count of saves."""
    from rlcoach.db.session import create_session
    from tests.api.stored_games import add_game

    with create_session() as session:
        for n, count in enumerate(saves):
            add_game(
                session,
                f"{playlist}{n}",
                playlist=playlist,
                me={"saves": count, "goals": goals},
            )
        session.commit()


def _benchmark_highlights(client, playlist):
    highlights = client.get("/coach", params={"playlist": playlist}).json()[
        "highlights"
    ]
    return [h for h in highlights if h["kind"] == "benchmark"]


def _benchmark_titles(client, playlist):
    return [h["title"] for h in _benchmark_highlights(client, playlist)]


def test_coach_names_a_benchmark_strength_with_enough_games_and_a_real_gap(client):
    _add_games_with("DOUBLES", [2, 3] * 5)
    _add_benchmark("saves", "DOUBLES", 1.5)
    [strength] = _benchmark_highlights(client, "DOUBLES")
    assert strength == {
        "kind": "benchmark",
        "title": "More saves than GC players",
        "detail": "2.5 a game over 10 games, GC average 1.5",
        "replay_id": None,
    }


def test_coach_names_no_benchmark_strength_from_too_few_games(client):
    _add_games_with("DOUBLES", [3] * 9)
    _add_benchmark("saves", "DOUBLES", 1.0)
    assert _benchmark_titles(client, "DOUBLES") == []


def test_coach_names_no_benchmark_strength_from_a_gap_inside_the_margin(client):
    # 2.5 a game, give or take 1.0 over ten games that swing from 1 to 4
    _add_games_with("DOUBLES", [1, 4] * 5)
    _add_benchmark("saves", "DOUBLES", 2.0)
    assert _benchmark_titles(client, "DOUBLES") == []


def test_coach_never_names_goals_or_assists_as_benchmark_strengths(client):
    # Goals and assists are flat across the ranks, however far above you are
    _add_games_with("DOUBLES", [1] * 10, goals=5)
    _add_benchmark("goals", "DOUBLES", 0.5)
    _add_benchmark("assists", "DOUBLES", 0.1)
    assert _benchmark_titles(client, "DOUBLES") == []


def test_coach_benchmark_strengths_name_the_playlist_only_when_mixed(client):
    _add_games_with("DOUBLES", [2, 3] * 5)
    _add_benchmark("saves", "DOUBLES", 1.5)
    _add_benchmark("saves", "STANDARD", 0.1)  # The fixture's games have no saves
    assert _benchmark_titles(client, "DOUBLES") == ["More saves than GC players"]
    assert _benchmark_titles(client, "DOUBLES,STANDARD") == [
        "More saves than GC players in Doubles"
    ]


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
    assert data["kickoffs"] == []


def test_replay_review_lists_your_kickoffs_on_the_clock(client):
    [kickoff] = client.get("/replays/win/review").json()["kickoffs"]
    assert (kickoff["clock"], kickoff["score"], kickoff["phase"]) == (
        "3:34",
        "1-0",
        "INITIAL",
    )
    assert (kickoff["role"], kickoff["approach"], kickoff["flip"]) == (
        "GO",
        "STANDARD_BOOST",
        "NONE",
    )
    assert (kickoff["result"], kickoff["first_touch"]) == ("LOST", "opponent")
    assert (kickoff["goal_after"], kickoff["goal_after_s"]) == ("against", 2.0)
    assert kickoff["race_gap"] is None


def test_coach_summarizes_your_kickoffs_and_the_ladder(client):
    kickoffs = client.get("/coach").json()["kickoffs"]
    assert (kickoffs["games"], kickoffs["count"]) == (2, 1)
    going = kickoffs["going"]
    assert going["flips"] == {"on_time": 0, "late": 0, "none": 1}
    assert (going["results"]["lost"], going["goals_against"]) == (1, 1)
    ladder = kickoffs["ladder"]
    assert [s["key"] for s in ladder] == ["flip_in", "on_time", "speedflip"]
    # One kickoff is too few to judge any step
    assert {s["status"] for s in ladder} == {"unknown"}


def test_replay_review_404s_for_an_unknown_game(client):
    assert client.get("/replays/nope/review").status_code == 404


def test_coach_categories_carry_the_trend_situations_and_cost(client):
    categories = client.get("/coach").json()["categories"]
    last_back = next(c for c in categories if c["category"] == "last_back")
    # Two reviewed games are too few for a trend
    assert (last_back["trend_games"], last_back["recent_per_game"]) == (0, None)
    assert last_back["earlier_per_game"] is None
    assert "latest_per_game" not in last_back and "before_per_game" not in last_back
    assert [s["kind"] for s in last_back["situations"]] == [
        "shot_last_back",
        "last_back_challenge",
    ]
    # Nothing measured, so half its one goal over two games
    assert (last_back["cost_per_game"], last_back["cost_measured"]) == (0.25, False)
    kickoffs = next(c for c in categories if c["category"] == "kickoffs")
    [kickoff] = kickoffs["situations"]
    # The one kickoff you went for, without a flip
    assert (kickoff["count"], kickoff["bad"], kickoff["conceded_after_bad"]) == (
        1,
        1,
        1,
    )


def _add_reviewed_game_with_situations(replay_id, playlist, situations):
    """A reviewed game long ago in another playlist, with these situations."""
    from rlcoach.db.models import Replay
    from rlcoach.db.reviews import save_review
    from rlcoach.db.session import create_session

    session = create_session()
    session.add(
        Replay(
            replay_id=replay_id,
            source_file=f"/replays/{replay_id}.replay",
            file_hash=replay_id,
            played_at_utc=datetime(2025, 1, 1, tzinfo=UTC),
            play_date=date.today() - timedelta(days=400),
            map="Stadium_P",
            playlist=playlist,
            team_size=2,
            duration_seconds=300.0,
            my_player_id="epic:me",
            my_team="ORANGE",
            my_score=1,
            opponent_score=0,
            result="WIN",
        )
    )
    session.commit()
    session.close()
    save_review(replay_id, "epic:me", replace(_review([], []), situations=situations))


def test_coach_measures_risks_over_every_reviewed_game(client):
    # Other players' jumps in an old Doubles game: 9 of 30 misses and 3 of 30
    # hits were followed by a goal against
    jumps = [
        Situation("jump", "epic:them", float(n), 200.0, "own_half", n < 30, False)
        for n in range(60)
    ]
    jumps = [replace(s, conceded=(s.t < 9 or 30 <= s.t < 33)) for s in jumps]
    _add_reviewed_game_with_situations("doubles_old", "DOUBLES", jumps)

    data = client.get("/coach", params={"playlist": "STANDARD"}).json()
    assert data["reviewed_count"] == 2
    whiffs = next(c for c in data["categories"] if c["category"] == "whiffs")
    [jump] = whiffs["situations"]
    assert jump["extra_risk"] == pytest.approx(0.2)
    # None of them yours, and none in this view
    assert (jump["count"], jump["others_bad_share"]) == (0, None)
    assert (whiffs["cost_per_game"], whiffs["cost_measured"]) == (0, True)
