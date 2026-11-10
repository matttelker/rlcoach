"""Tests for storing one game from its report."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError

from rlcoach.config import IdentityConfig, PathsConfig, PreferencesConfig, RLCoachConfig
from rlcoach.db.games import (
    ReplayExistsError,
    is_stored,
    played_at,
    store_game,
)
from rlcoach.db.models import Player, PlayerGameStats, Replay
from rlcoach.db.session import create_session, init_db, reset_engine

CONFIG = RLCoachConfig(
    identity=IdentityConfig(platform_ids=["steam:1"], display_names=["Me"]),
    paths=PathsConfig(watch_folder=None, data_dir=None),
    preferences=PreferencesConfig(timezone="America/New_York"),
)


@pytest.fixture(autouse=True)
def db():
    init_db()
    yield
    reset_engine()


def make_report(
    replay_id="r1",
    *,
    started="2026-03-01T03:00:00Z",
    blue=3,
    orange=1,
    rival_name="Rival",
    stats=None,
):
    players = [
        {"player_id": "steam:1", "display_name": "Me", "team": "BLUE"},
        {"player_id": "epic:2", "display_name": rival_name, "team": "ORANGE"},
        {"player_id": "slug:bot", "display_name": "Bot", "team": "ORANGE"},
    ]
    return {
        "replay_id": replay_id,
        "source_file": f"C:/replays/{replay_id}.replay",
        "metadata": {
            "playlist": "DOUBLES",
            "map": "Stadium_P",
            "team_size": 2,
            "overtime": True,
            "started_at_utc": started,
            "duration_seconds": 345.5,
        },
        "score": {"BLUE": blue, "ORANGE": orange},
        "players": players,
        "stats": stats or {},
    }


def _get(model, key):
    with create_session() as session:
        return session.get(model, key)


def _stats(replay_id, player_id):
    with create_session() as session:
        return (
            session.query(PlayerGameStats)
            .filter_by(replay_id=replay_id, player_id=player_id)
            .one()
        )


def test_the_game_is_stored_from_your_side():
    store_game(make_report(), "hash1", "steam:1", CONFIG)
    replay = _get(Replay, "r1")
    assert (replay.my_team, replay.my_score, replay.opponent_score) == ("BLUE", 3, 1)
    assert replay.result == "WIN"
    assert (replay.overtime, replay.team_size, replay.duration_seconds) == (
        True,
        2,
        345.5,
    )
    assert replay.file_hash == "hash1"
    # 03:00 UTC is still the day before in New York
    assert replay.play_date == date(2026, 2, 28)
    assert is_stored("hash1") and not is_stored("other")


@pytest.mark.parametrize(
    ("blue", "orange", "me_on", "result"),
    [(1, 2, "steam:1", "LOSS"), (2, 2, "steam:1", "DRAW"), (1, 2, "epic:2", "WIN")],
)
def test_the_result_is_yours(blue, orange, me_on, result):
    store_game(make_report(blue=blue, orange=orange), "h", me_on, CONFIG)
    assert _get(Replay, "r1").result == result


def test_each_player_gets_their_stats_with_missing_counts_zero_and_others_empty():
    stats = {
        "steam:1": {
            "goals": 2,
            "bcpm": 410.0,
            "behind_ball_pct": 33.3,
            "clears": 3,
        }
    }
    store_game(make_report(stats=stats), "h", "steam:1", CONFIG)
    mine = _stats("r1", "steam:1")
    assert (mine.goals, mine.bcpm, mine.behind_ball_pct) == (
        2,
        410.0,
        33.3,
    )
    assert (mine.is_me, mine.team, mine.saves, mine.avg_speed_kph) == (
        True,
        "BLUE",
        0,
        None,
    )
    # The game's counts are empty for a replay that carries none
    assert (mine.clears, mine.epic_saves) == (3, None)
    theirs = _stats("r1", "epic:2")
    assert (theirs.is_me, theirs.team, theirs.goals, theirs.bcpm) == (
        False,
        "ORANGE",
        0,
        None,
    )


def test_new_players_get_their_platform_and_whether_they_are_you():
    store_game(make_report(), "h", "steam:1", CONFIG)
    me, rival, bot = (_get(Player, p) for p in ("steam:1", "epic:2", "slug:bot"))
    assert (me.is_me, me.platform) == (True, "steam")
    assert (rival.is_me, rival.platform) == (False, "epic")
    assert bot.platform == "slug"
    seen = datetime(2026, 3, 1, 3, tzinfo=UTC)
    assert rival.first_seen_utc.replace(tzinfo=UTC) == seen


def test_games_loaded_out_of_order_widen_when_players_were_seen():
    middle = make_report("b", started="2026-03-02T00:00:00Z", rival_name="Middle")
    store_game(middle, "hb", "steam:1", CONFIG)
    newest = make_report("c", started="2026-03-03T00:00:00Z", rival_name="Newest")
    store_game(newest, "hc", "steam:1", CONFIG)
    oldest = make_report("a", started="2026-03-01T00:00:00Z", rival_name="Oldest")
    store_game(oldest, "ha", "steam:1", CONFIG)
    rival = _get(Player, "epic:2")
    assert rival.display_name == "Newest"
    assert rival.first_seen_utc.day == 1 and rival.last_seen_utc.day == 3


def test_storing_leaves_teammate_tags_alone():
    store_game(make_report("a"), "ha", "steam:1", CONFIG)
    with create_session() as session:
        rival = session.get(Player, "epic:2")
        rival.is_tagged_teammate, rival.teammate_notes = True, "duo"
        session.commit()
    store_game(
        make_report("b", started="2026-04-01T00:00:00Z"), "hb", "steam:1", CONFIG
    )
    rival = _get(Player, "epic:2")
    assert (rival.is_tagged_teammate, rival.teammate_notes) == (True, "duo")


def test_a_stored_game_is_refused_by_id_or_hash_and_nothing_changes():
    store_game(make_report(), "h", "steam:1", CONFIG)
    with pytest.raises(ReplayExistsError):
        store_game(make_report(rival_name="Changed"), "other", "steam:1", CONFIG)
    with pytest.raises(ReplayExistsError):
        store_game(make_report("r2", rival_name="Changed"), "h", "steam:1", CONFIG)
    assert _get(Player, "epic:2").display_name == "Rival"


def test_a_failure_leaves_nothing_behind():
    report = make_report()
    # The same player twice breaks the stats table's one-row-per-player rule
    report["players"].append(report["players"][1])
    with pytest.raises(IntegrityError):
        store_game(report, "h", "steam:1", CONFIG)
    with create_session() as session:
        assert session.query(Replay).count() == 0
        assert session.query(Player).count() == 0


def test_played_at_reads_the_header_time_or_falls_back_to_now():
    assert played_at(make_report()) == datetime(2026, 3, 1, 3, tzinfo=UTC)
    before = datetime.now(UTC)
    assert played_at(make_report(started=None)) >= before
