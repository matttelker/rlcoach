"""Tests for the scoreboard stats."""

from __future__ import annotations

from rlcoach.analysis.fundamentals import fundamentals, game_counts, shooting_pct
from rlcoach.events.types import DemoEvent
from rlcoach.parser.types import Header, PlayerInfo, StatCount
from tests.fixtures.builders import create_test_frame

HEADER = Header(
    players=[
        PlayerInfo(
            name="Me",
            platform_ids={"epic": "me"},
            team=0,
            stats={"Goals": 2, "Assists": 1, "Saves": 3, "Shots": 4, "Score": 512},
        ),
        PlayerInfo(
            name="Them", platform_ids={"steam": "1"}, team=1, stats={"Shots": 1}
        ),
    ]
)


def test_the_scoreboard_is_the_headers():
    stats = fundamentals(HEADER, [], {"epic:me": None})["epic:me"]
    assert stats == {
        "goals": 2,
        "assists": 1,
        "saves": 3,
        "shots": 4,
        "score": 512,
        "shooting_pct": 50.0,
        "demos_inflicted": 0,
        "demos_taken": 0,
    }


def test_a_stat_the_header_leaves_out_is_zero():
    stats = fundamentals(HEADER, [], {"steam:1": None})["steam:1"]
    assert (stats["goals"], stats["shots"], stats["score"]) == (0, 1, 0)


def test_a_player_with_no_header_row_scores_nothing():
    """Leavers and replaced bots are in the frames but not in the header."""
    stats = fundamentals(HEADER, [], {"player_5": None})["player_5"]
    assert stats["goals"] == stats["score"] == stats["shooting_pct"] == 0


def test_demos_count_for_the_attacker_and_against_the_victim():
    demos = [
        DemoEvent(t=10.0, victim="steam:1", attacker="epic:me"),
        DemoEvent(t=20.0, victim="steam:1", attacker="epic:me"),
        DemoEvent(t=30.0, victim="epic:me", attacker="steam:1"),
        # The game names no attacker for some demos
        DemoEvent(t=40.0, victim="epic:me", attacker=None),
    ]
    stats = fundamentals(HEADER, demos, {"epic:me": None, "steam:1": None})
    assert (stats["epic:me"]["demos_inflicted"], stats["epic:me"]["demos_taken"]) == (
        2,
        2,
    )
    assert (stats["steam:1"]["demos_inflicted"], stats["steam:1"]["demos_taken"]) == (
        1,
        2,
    )


def test_shooting_pct_is_a_share_of_shots_capped_at_100():
    assert shooting_pct(1, 3) == 33.33
    assert shooting_pct(0, 0) == 0.0
    # A goal can count without a shot on the scoreboard
    assert shooting_pct(2, 1) == 100.0


def test_the_games_counts_add_up_each_rise():
    frames = [
        create_test_frame(1.0, [], stat_counts=[StatCount("epic:me", "clear", 1)]),
        create_test_frame(
            2.0,
            [],
            stat_counts=[
                StatCount("epic:me", "clear", 2),
                StatCount("epic:me", "epic_save", 1),
                StatCount("steam:1", "aerial_hit", 1),
            ],
        ),
    ]
    counts = game_counts(frames, {"epic:me": None, "steam:1": None})
    assert counts["epic:me"] == {
        "epic_saves": 1,
        "clears": 3,
        "centers": 0,
        "aerial_hits": 0,
    }
    assert counts["steam:1"]["aerial_hits"] == 1


def test_a_replay_without_the_games_counts_has_no_value_for_them():
    counts = game_counts([create_test_frame(1.0, [])], {"epic:me": None})
    assert counts["epic:me"] == dict.fromkeys(
        ("epic_saves", "clears", "centers", "aerial_hits")
    )
