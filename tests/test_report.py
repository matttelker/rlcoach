"""Tests for reporting one loaded game."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from rlcoach.db.games import STAT_COLUMNS
from rlcoach.events import KickoffEvent
from rlcoach.game import game_from_frames
from rlcoach.identity import build_player_identities
from rlcoach.parser.types import Header, PlayerInfo
from rlcoach.report import _went_to_overtime, report_for
from tests.fixtures.builders import create_simple_replay_frames

PLAYERS = [
    PlayerInfo(name="Me", platform_ids={"epic": "me"}, team=0, stats={"Goals": 3}),
    PlayerInfo(name="Them", platform_ids={"steam": "1"}, team=1, stats={"Goals": 1}),
    PlayerInfo(name="Ghost", platform_ids={"steam": "2"}, team=1),
]


def _game(**header):
    header = Header(
        **{
            "match_type": "Online",
            "map_name": "Stadium_P",
            "team_size": 2,
            "started_at_utc": "2026-03-01T03:00:00Z",
            "team0_score": 3,
            "team1_score": 1,
            "players": PLAYERS,
            **header,
        }
    )
    ids = [p.canonical_id for p in build_player_identities(header.players)]
    # The ghost is in the header but never in the frames
    frames = create_simple_replay_frames(
        duration_seconds=3.0, players=[(ids[0], 0), (ids[1], 1)]
    )
    return game_from_frames(Path("C:/replays/x.replay"), header, frames)


def test_a_report_says_what_the_game_was():
    report = report_for(_game(), "abc")
    assert report["replay_id"] == "abc"
    assert report["source_file"] == str(Path("C:/replays/x.replay"))
    metadata = report["metadata"]
    assert metadata["playlist"] == "DOUBLES"
    assert (metadata["map"], metadata["team_size"], metadata["overtime"]) == (
        "Stadium_P",
        2,
        False,
    )
    assert metadata["started_at_utc"] == "2026-03-01T03:00:00Z"
    # Frames start at 0, so the last one's time is the length
    assert metadata["duration_seconds"] == pytest.approx(89 / 30)
    assert report["score"] == {"BLUE": 3, "ORANGE": 1}


def test_a_report_lists_the_players_and_the_stats_of_those_the_frames_show():
    report = report_for(_game(), "abc")
    assert report["players"] == [
        {"player_id": "epic:me", "display_name": "Me", "team": "BLUE"},
        {"player_id": "steam:1", "display_name": "Them", "team": "ORANGE"},
        {"player_id": "steam:2", "display_name": "Ghost", "team": "ORANGE"},
    ]
    stats = report["stats"]
    assert set(stats) == {"epic:me", "steam:1"}
    # Every stat is named for the column that stores it
    assert set(stats["epic:me"]) == set(STAT_COLUMNS)
    assert (stats["epic:me"]["goals"], stats["steam:1"]["goals"]) == (3, 1)


def test_missing_header_fields_fall_back():
    report = report_for(_game(map_name=None, team_size=0, started_at_utc=None), "a")
    metadata = report["metadata"]
    assert (metadata["map"], metadata["team_size"]) == ("unknown", 1)
    assert metadata["started_at_utc"].endswith("Z")


def _kickoff(phase):
    return KickoffEvent(t_start=0.0, phase=phase)


def test_an_overtime_kickoff_means_overtime():
    game = _game()
    assert _went_to_overtime(
        replace(game, kickoffs=[_kickoff("INITIAL"), _kickoff("OT")])
    )
    assert not _went_to_overtime(replace(game, kickoffs=[_kickoff("INITIAL")] * 2))
    assert not _went_to_overtime(replace(game, kickoffs=[]))


def test_a_frame_in_overtime_means_overtime():
    game = replace(_game(), kickoffs=[])
    frames = [replace(frame, overtime=True) if i == 50 else frame
              for i, frame in enumerate(game.frames)]  # fmt: skip
    assert _went_to_overtime(replace(game, frames=frames))
    assert report_for(replace(game, frames=frames), "a")["metadata"]["overtime"]


def test_the_games_playlist_number_beats_the_header():
    # The header says doubles; the game says casual
    assert report_for(_game(), "a")["metadata"]["playlist"] == "DOUBLES"
    casual = replace(_game(), playlist_id=2)
    assert report_for(casual, "a")["metadata"]["playlist"] == "CASUAL"
