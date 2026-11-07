"""Tests for the boost stats."""

from __future__ import annotations

import pytest

from rlcoach.analysis.boost import active_play_seconds, boost_stats, is_held_for_kickoff
from rlcoach.analysis.tracks import player_tracks
from rlcoach.events.types import BoostPickupEvent
from rlcoach.field_constants import Vec3
from tests.fixtures.builders import (
    create_test_ball,
    create_test_frame,
    create_test_player,
)

MOVING = Vec3(1000.0, 0.0, 0.0)
OFF_SPOT = create_test_ball(position=Vec3(0.0, 2000.0, 93.15))


def _frames(boosts, *, step=0.5, demolished=(), still=(), gap_after=None):
    """One car whose boost reads `boosts`, a frame every `step` seconds."""
    frames = []
    t = 0.0
    for index, boost in enumerate(boosts):
        held = index in still
        car = create_test_player(
            "me",
            0,
            velocity=Vec3(0.0, 0.0, 0.0) if held else MOVING,
            boost=boost,
            is_demolished=index in demolished,
        )
        frames.append(
            create_test_frame(t, [car], ball=create_test_ball() if held else OFF_SPOT)
        )
        t += 10.0 if index == gap_after else step
    return frames


def _stats(frames, pickups=()):
    return boost_stats(frames, list(pickups), player_tracks(frames))["me"]


def test_average_boost_is_the_mean_of_updates_not_of_time():
    # 0 for one frame, then 100 for nine: a time average would be 90
    frames = _frames([0, *[100] * 9])
    assert _stats(frames)["avg_boost"] == 50.0


def test_time_at_zero_counts_once_the_next_update_ends_it():
    frames = _frames([50, 0, 0, 0, 0, 20])
    assert _stats(frames)["time_zero_boost_s"] == 2.0


def test_time_at_zero_cut_short_by_a_demo_counts_for_nothing():
    frames = _frames([50, 0, 0, 0, 0, 33], demolished={3})
    assert _stats(frames)["time_zero_boost_s"] == 0.0


def test_time_at_zero_cut_short_by_a_goal_replay_counts_for_nothing():
    frames = _frames([50, 0, 0, 0, 0, 33], gap_after=2)
    assert _stats(frames)["time_zero_boost_s"] == 0.0


def test_time_at_full_ending_in_a_kickoff_countdown_counts_for_nothing():
    frames = _frames([50, 100, 100, 100, 33], still={4})
    assert _stats(frames)["time_full_boost_s"] == 0.0
    frames = _frames([50, 100, 100, 100, 33])
    assert _stats(frames)["time_full_boost_s"] == 1.5


def test_a_stretch_still_open_at_the_end_counts_for_nothing():
    frames = _frames([50, 0, 0, 0])
    assert _stats(frames)["time_zero_boost_s"] == 0.0


def _pickup(player_id, gain, stolen=False):
    return BoostPickupEvent(
        t=1.0, player_id=player_id, pad_type="SMALL", stolen=stolen, boost_gain=gain
    )


def test_collected_and_stolen_add_up_each_players_pickups():
    frames = _frames([33] * 3)
    pickups = [
        _pickup("me", 12.0),
        _pickup("me", 67.0, stolen=True),
        _pickup("them", 100.0),
    ]
    stats = _stats(frames, pickups)
    assert (stats["boost_collected"], stats["boost_stolen"]) == (79.0, 67.0)


def test_collected_per_minute_divides_by_active_play():
    # Three minutes of play, a goal replay's 10 s pause, then a 3 s countdown
    frames = _frames([33] * 361, gap_after=200, still=set(range(300, 308)))
    assert active_play_seconds(
        frames, [is_held_for_kickoff(f) for f in frames]
    ) == pytest.approx(frames[-1].timestamp - 10.0 - 3.0)
    stats = _stats(frames, [_pickup("me", 100.0), _pickup("me", 74.0)])
    assert stats["bcpm"] == round(174.0 / ((frames[-1].timestamp - 13.0) / 60), 2)


def test_a_short_game_divides_by_one_minute_at_least():
    frames = _frames([33] * 21)
    assert _stats(frames, [_pickup("me", 50.0)])["bcpm"] == 50.0


def test_a_short_stop_on_the_spot_is_not_a_countdown():
    frames = _frames([33] * 20, still={5, 6, 7})
    held = [is_held_for_kickoff(f) for f in frames]
    assert sum(held) == 3
    assert active_play_seconds(frames, held) == frames[-1].timestamp


def test_a_ball_off_the_spot_or_a_moving_car_is_not_held():
    car = create_test_player("me", 0)
    assert is_held_for_kickoff(create_test_frame(0.0, [car]))
    assert not is_held_for_kickoff(create_test_frame(0.0, [car], ball=OFF_SPOT))
    moving = create_test_player("me", 0, velocity=MOVING)
    assert not is_held_for_kickoff(create_test_frame(0.0, [car, moving]))
    assert not is_held_for_kickoff(create_test_frame(0.0, []))
