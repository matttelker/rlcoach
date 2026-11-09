"""Tests for the Rust parser's frames, on your replays."""

from __future__ import annotations

import math
from functools import cache

import pytest

from rlcoach.field_constants import BOOST_PADS
from rlcoach.parser import read_frames, read_header
from tests.fixtures import real_replays

SPOTS = [pad.position for pad in BOOST_PADS]


@cache
def _frames(name, pads=True):
    return read_frames(real_replays.replay(name), SPOTS if pads else [])


def _all(name, key, pads=True):
    return [item for frame in _frames(name, pads) for item in frame[key]]


def test_every_header_player_has_a_car_in_every_frame():
    frames = _frames(real_replays.REGULATION)
    assert all(
        sorted(car[0] for car in frame["cars"]) == list(range(6)) for frame in frames
    )
    times = [frame["time"] for frame in frames]
    assert times == sorted(times) and times[0] >= 0.0


def test_a_car_has_its_team_motion_rotation_and_boost():
    row, team, position, velocity, spin, rotation, boost, demolished = _frames(
        real_replays.REGULATION
    )[3000]["cars"][0]
    assert (row, team) == (0, 1)
    assert all(len(v) == 3 for v in (position, velocity, spin))
    assert math.isclose(sum(q * q for q in rotation), 1.0, abs_tol=1e-3)
    assert 0 <= boost <= 100 and isinstance(demolished, bool)


def test_spin_is_in_radians_a_second():
    spins = [
        math.hypot(*car[4]) for f in _frames(real_replays.OVERTIME) for car in f["cars"]
    ]
    # A car's spin is capped at 5.5 rad/s
    assert 1.0 < max(spins) <= 5.6


def test_pickups_name_the_pad_and_the_player():
    pickups = _all(real_replays.REGULATION, "pickups")
    assert len(pickups) == 285
    assert {pad for pad, *_ in pickups} == set(range(34))
    assert all(row < 6 and team in (0, 1) for _, row, team, _ in pickups)


def test_a_pickup_waiting_to_be_placed_keeps_its_own_time():
    frames = _frames(real_replays.REGULATION)
    assert all(
        when <= frame["time"] for frame in frames for *_, when in frame["pickups"]
    )


def test_an_arena_without_known_pads_has_no_pickups():
    assert _all(real_replays.HOOPS, "pickups", pads=False) == []


def test_flips_carry_the_stick_direction():
    dodges = _all(real_replays.REGULATION, "dodges")
    assert len(dodges) == 294
    # (x / 2.6, y / 2.24) is the stick, which is pushed all the way to flip
    assert all(
        math.isclose(math.hypot(x / 2.6, y / 2.24), 1.0, abs_tol=0.01)
        for _, (x, y, _) in dodges
    )


def test_the_games_counter_names_each_kickoffs_first_touch():
    # 5 goals, so 6 kickoffs, the last of which the recording ends before
    assert len(_all(real_replays.REGULATION, "first_touches")) == 5


def test_a_replay_from_before_the_counter_has_no_first_touches():
    assert _all(real_replays.WITH_LEAVERS, "first_touches") == []


def test_leavers_get_rows_past_the_header():
    header = read_header(real_replays.replay(real_replays.WITH_LEAVERS))
    rows = {
        car[0] for frame in _frames(real_replays.WITH_LEAVERS) for car in frame["cars"]
    }
    assert rows == set(range(len(header.players) + 5))


def test_touches_are_the_games_count_by_player():
    touches = _all(real_replays.REGULATION, "touches")
    assert sum(count for _, count in touches) == 107
    assert {row for row, _ in touches} == set(range(6))
    assert all(count >= 1 for _, count in touches)


def test_a_replay_from_before_the_touch_count_has_none():
    assert _all(real_replays.WITH_LEAVERS, "touches") == []


def test_the_ball_names_the_team_that_touched_it_last():
    teams = [frame["hit_team"] for frame in _frames(real_replays.REGULATION)]
    assert set(teams) == {None, 0, 1}
    pairs = zip(teams, teams[1:], strict=False)
    changes = sum(1 for a, b in pairs if b is not None and a != b)
    assert changes == 57


def test_demos_name_players():
    assert _all(real_replays.REGULATION, "demos") == [(3, 5), (5, 0)]
    # The last demo in E8D9 came at the end, with no attacker
    assert _all(real_replays.OVERTIME, "demos")[-1] == (5, None)


def test_a_file_that_isnt_a_replay_raises(tmp_path):
    path = tmp_path / "x.replay"
    path.write_bytes(b"not a replay")
    with pytest.raises(ValueError, match="couldn't read the frames"):
        read_frames(path, SPOTS)
