"""Tests for reading a replay's header from its properties."""

from __future__ import annotations

import pytest

from rlcoach.parser import read_header
from rlcoach.parser.header import accounts, header_from_properties
from tests.fixtures import real_replays


def _row(name, team, **fields):
    return {"Name": name, "Team": team, "Score": 100, "Goals": 1, **fields}


PROPERTIES = {
    "MatchType": "Online",
    "MapName": "Stadium_P",
    "TeamSize": 2,
    "Team0Score": 2,
    "Date": "2026-10-31 23-56-53",
    "PlayerName": "Me",
    "PlayerStats": [_row("Me", 0), _row("Mate", 0), _row("Them", 1)],
    "Goals": [
        {"frame": 812, "PlayerName": "Me", "PlayerTeam": 0},
        {"frame": 2400, "PlayerName": "Them", "PlayerTeam": 1},
    ],
}


def test_the_header_says_what_the_match_was():
    header = header_from_properties(PROPERTIES)
    assert (header.match_type, header.map_name) == ("Online", "Stadium_P")
    assert (header.team0_score, header.team1_score) == (2, 0)
    assert header.recorded_by == "Me"
    assert header.started_at_utc is not None and header.started_at_utc.endswith("Z")
    assert [(g.frame, g.player_name, g.player_team) for g in header.goals] == [
        (812, "Me", 0),
        (2400, "Them", 1),
    ]


def test_players_keep_their_team_and_scoreboard():
    them = header_from_properties(PROPERTIES).players[2]
    assert (them.name, them.team) == ("Them", 1)
    assert them.stats == {"Score": 100, "Goals": 1}


def test_the_team_size_is_the_bigger_teams_rows():
    # A team a player left counts the rows that finished
    assert header_from_properties(PROPERTIES).team_size == 2
    alone = {**PROPERTIES, "PlayerStats": [_row("Me", 0)]}
    assert header_from_properties(alone).team_size == 1
    nobody = {**PROPERTIES, "PlayerStats": []}
    assert header_from_properties(nobody).team_size == 2


def test_a_row_without_a_name_is_no_player():
    rows = [_row("Me", 0), {"Team": 1, "Score": 5}]
    header = header_from_properties({**PROPERTIES, "PlayerStats": rows})
    assert [p.name for p in header.players] == ["Me"]


def test_a_header_missing_fields_reads_as_empty():
    header = header_from_properties({})
    assert (header.match_type, header.team_size, header.team0_score) == (None, 0, 0)
    assert (header.players, header.goals, header.started_at_utc) == ([], [], None)


EPIC = {"Uid": 0, "EpicAccountId": "abc", "Platform": "OnlinePlatform_Epic"}


@pytest.mark.parametrize(
    ("row", "found"),
    [
        ({"Platform": "OnlinePlatform_Epic", "PlayerID": EPIC}, {"epic": "abc"}),
        ({"Platform": "OnlinePlatform_Steam", "OnlineID": 7656}, {"steam": "7656"}),
        (
            {
                "Platform": "OnlinePlatform_PS4",
                "OnlineID": 76,
                "PlayerID": {"Uid": 76, "NpId": {"Handle": {"Data": "kev"}}},
            },
            {"psn": "76"},
        ),
        ({"Platform": "OnlinePlatform_Dingo", "PlayerID": {"Uid": 25}}, {"xbox": "25"}),
        # Without PlayerID, OnlineID has the same number
        ({"Platform": "OnlinePlatform_Dingo", "OnlineID": 25}, {"xbox": "25"}),
        ({"Platform": "OnlinePlatform_NNX", "OnlineID": 15}, {"switch": "15"}),
        ({"Platform": "OnlinePlatform_PS5", "OnlineID": 9}, {"ps5": "9"}),
        ({"Platform": "OnlinePlatform_Epic", "OnlineID": 0}, {}),
        ({"Platform": "OnlinePlatform_Unknown", "OnlineID": 0, "bBot": True}, {}),
    ],
)
def test_an_account_is_filed_under_its_own_platform(row, found):
    assert accounts(row) == found


def test_a_real_header():
    header = read_header(real_replays.replay(real_replays.REGULATION))
    assert (header.match_type, header.map_name, header.team_size) == (
        "Online",
        "street_p",
        3,
    )
    assert (header.team0_score, header.team1_score) == (1, 4)
    assert header.recorded_by == "midnightmelker"
    assert len(header.players) == 6 and len(header.goals) == 5
    me = header.players[0]
    assert me.platform_ids == {"epic": "58b9e63f25b249678aa291dffa407f6b"}
    assert set(me.stats) == {"Score", "Goals", "Assists", "Saves", "Shots"}


def test_a_file_that_isnt_a_replay_raises(tmp_path):
    path = tmp_path / "x.replay"
    path.write_bytes(b"not a replay")
    with pytest.raises(ValueError, match="couldn't read the header"):
        read_header(path)
    with pytest.raises(OSError):
        read_header(tmp_path / "missing.replay")
