"""Tests for working out a game's playlist and mode from its header."""

from __future__ import annotations

import pytest

from rlcoach.modes import COACHED_PLAYLISTS, MODES, SOCCAR, mode_of, playlist_of
from rlcoach.parser.types import Header


def _header(match_type: str | None, team_size: int, map_name: str = "Stadium_P"):
    return Header(match_type=match_type, team_size=team_size, map_name=map_name)


@pytest.mark.parametrize(
    ("team_size", "playlist"),
    [(1, "DUEL"), (2, "DOUBLES"), (3, "STANDARD"), (4, "CHAOS"), (0, "UNKNOWN")],
)
def test_online_games_are_filed_by_team_size(team_size, playlist):
    assert playlist_of(_header("Online", team_size)) == playlist


def test_tournaments_are_filed_by_team_size():
    assert playlist_of(_header("Tournament", 3)) == "STANDARD"
    assert playlist_of(_header("Tournament", 2)) == "DOUBLES"


def test_private_and_offline_matches_stay_private_on_any_arena():
    assert playlist_of(_header("Private", 3)) == "PRIVATE"
    assert playlist_of(_header("Offline", 1)) == "PRIVATE"
    assert playlist_of(_header("Private", 2, "HoopsStadium_P")) == "PRIVATE"


@pytest.mark.parametrize("match_type", [None, "", "Lan", "Season"])
def test_other_match_types_are_unknown(match_type):
    assert playlist_of(_header(match_type, 2)) == "UNKNOWN"


@pytest.mark.parametrize(
    "map_name", ["HoopsStadium_P", "HoopsStreet_P", "ShatterShot_P", "Knockout_Arena"]
)
def test_extra_mode_arenas_leave_the_team_size_playlists(map_name):
    assert playlist_of(_header("Online", 2, map_name)) == "EXTRA_MODE"


def test_rocket_labs_arenas_keep_their_playlist_but_get_no_review():
    labs = "Labs_Octagon_02_P"
    assert playlist_of(_header("Online", 2, labs)) == "DOUBLES"
    assert mode_of(labs).reviewed is False


@pytest.mark.parametrize("map_name", ["Stadium_P", "UtopiaStadium_Dusk_P", None, ""])
def test_standard_arenas_are_soccar_and_reviewed(map_name):
    assert mode_of(map_name) is SOCCAR
    assert SOCCAR.reviewed


def test_only_soccar_is_reviewed():
    assert not any(mode.reviewed for mode in MODES)


def test_the_coached_playlists_are_soccars_team_sizes():
    assert set(COACHED_PLAYLISTS) == {"DUEL", "DOUBLES", "STANDARD"}


@pytest.mark.parametrize(
    ("map_name", "pads"),
    [
        ("Stadium_P", True),
        ("Labs_Octagon_02_P", True),
        ("HoopsStadium_P", False),
        ("ShatterShot_P", False),
    ],
)
def test_hoops_and_dropshot_have_pads_of_their_own(map_name, pads):
    assert mode_of(map_name).soccar_pads is pads
