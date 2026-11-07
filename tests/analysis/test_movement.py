"""Tests for the movement stats."""

from __future__ import annotations

import pytest

from rlcoach.analysis.movement import frame_durations, movement_stats
from rlcoach.analysis.tracks import player_tracks
from rlcoach.field_constants import Vec3
from tests.fixtures.builders import create_test_frame, create_test_player


def _frames(speeds, *, step=0.5, demolished=()):
    return [
        create_test_frame(
            index * step,
            [
                create_test_player(
                    "me",
                    0,
                    velocity=Vec3(0.0, speed, 0.0),
                    is_demolished=index in demolished,
                )
            ],
        )
        for index, speed in enumerate(speeds)
    ]


def _stats(frames):
    return movement_stats(frames, player_tracks(frames))["me"]


def test_average_speed_leaves_out_time_parked():
    frames = _frames([1000.0, 1000.0, 0.0, 0.0, 1000.0])
    assert _stats(frames)["avg_speed_kph"] == 36.0  # 1000 uu/s


def test_a_demolished_car_counts_for_neither_stat():
    frames = _frames([2300.0, 2300.0, 2300.0, 500.0], demolished={1, 2})
    stats = _stats(frames)
    assert stats["time_supersonic_s"] == 0.5
    assert stats["avg_speed_kph"] == pytest.approx((2300 + 500) / 2 * 0.036, abs=0.01)


def test_supersonic_starts_at_2200():
    frames = _frames([2199.9, 2200.0, 2300.0, 1000.0])
    assert _stats(frames)["time_supersonic_s"] == 1.0


def test_a_frame_lasts_until_the_next_one():
    times = [0.0, 0.03, 0.06, 0.06, 5.0, 5.04]
    frames = [create_test_frame(t, []) for t in times]
    # A repeated time and a goal replay's gap last as long as the frame before
    assert frame_durations(frames) == pytest.approx(
        [0.03, 0.03, 0.03, 0.03, 0.04, 0.04]
    )
    assert frame_durations(frames[:1]) == pytest.approx([1 / 30])
