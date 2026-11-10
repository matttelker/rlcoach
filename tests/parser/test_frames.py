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


def test_every_header_player_has_a_car_but_while_it_respawns():
    frames = _frames(real_replays.REGULATION)
    rows = [sorted(car[0] for car in frame["cars"]) for frame in frames]
    assert rows[0] == list(range(6))
    assert all(set(frame_rows) <= set(range(6)) for frame_rows in rows)
    # A car is gone for a frame or few after a goal or its own demo, until the
    # new one sends where it is
    for row in range(6):
        gap = longest = 0
        for frame_rows in rows:
            gap = 0 if row in frame_rows else gap + 1
            longest = max(longest, gap)
        assert longest <= 3
    times = [frame["time"] for frame in frames]
    assert times == sorted(times) and times[0] >= 0.0


def test_no_car_is_listed_before_it_sends_a_position():
    """Regression: a car with only a team or boost was put at (0, 0, 17)."""
    for name in (real_replays.REGULATION, real_replays.WITH_LEAVERS):
        assert not any(
            tuple(car[2]) == (0.0, 0.0, 17.0)
            for frame in _frames(name)
            for car in frame["cars"]
        )


def test_the_clock_starts_at_five_minutes_and_never_rises_in_regulation():
    for name in (real_replays.REGULATION, real_replays.OVERTIME):
        frames = _frames(name)
        assert frames[0]["seconds_remaining"] == 300
        clock = [f["seconds_remaining"] for f in frames if not f["overtime"]]
        assert all(b <= a for a, b in zip(clock, clock[1:], strict=False))


def test_overtime_frames_are_flagged_and_count_up():
    overtime = [f for f in _frames(real_replays.OVERTIME) if f["overtime"]]
    assert overtime and overtime[0]["seconds_remaining"] == 0
    clock = [f["seconds_remaining"] for f in overtime]
    assert clock == sorted(clock) and clock[-1] > 0
    assert not any(f["overtime"] for f in _frames(real_replays.REGULATION))


def test_the_game_names_its_playlist():
    assert {f["playlist"] for f in _frames(real_replays.REGULATION)} == {13}
    assert {f["playlist"] for f in _frames(real_replays.HOOPS, pads=False)} == {27}


def test_a_car_has_its_team_motion_rotation_and_boost():
    row, team, position, velocity, spin, rotation, boost, demolished, using = _frames(
        real_replays.REGULATION
    )[3000]["cars"][0]
    assert (row, team) == (0, 1)
    assert all(len(v) == 3 for v in (position, velocity, spin))
    assert math.isclose(sum(q * q for q in rotation), 1.0, abs_tol=1e-3)
    assert 0 <= boost <= 100 and isinstance(demolished, bool)
    assert len(using) == 3 and all(isinstance(state, bool) for state in using)


def test_cars_say_when_they_jump_double_jump_and_flip():
    frames = _frames(real_replays.REGULATION)
    starts = [0, 0, 0]
    flips_seen = 0
    last: dict[int, tuple[bool, ...]] = {}
    for index, frame in enumerate(frames):
        for car in frame["cars"]:
            row, using = car[0], car[8]
            was = last.get(row, (False, False, False))
            for state in range(3):
                starts[state] += using[state] and not was[state]
            if using[2] and not was[2]:
                nearby = frames[max(0, index - 2) : index + 3]
                flips_seen += any(r == row for f in nearby for r, _ in f["dodges"])
            last[row] = using
    assert starts == [246, 29, 179]  # Jumps, double jumps and flips
    # A flip's start comes with the flip the game sends, but for five
    assert flips_seen == 174


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


def test_the_games_counts_rise_by_player():
    counts = _all(real_replays.REGULATION, "counts")
    assert {name for _, name, _ in counts} <= {
        "epic_save",
        "clear",
        "center",
        "aerial_hit",
    }
    assert all(rise >= 1 for _, _, rise in counts)
    assert sum(rise for _, name, rise in counts if name == "aerial_hit") > 0


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
