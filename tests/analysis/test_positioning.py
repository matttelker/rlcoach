"""Tests for the positioning stats."""

from __future__ import annotations

from rlcoach.analysis.positioning import positioning_stats
from rlcoach.analysis.tracks import player_tracks
from rlcoach.field_constants import Vec3
from tests.fixtures.builders import (
    create_test_ball,
    create_test_frame,
    create_test_player,
)


def _at(y, x=0.0):
    return Vec3(x, y, 17.0)


def _stats(frames):
    return positioning_stats(frames, player_tracks(frames))


def test_behind_the_ball_is_nearer_your_own_goal():
    ball = create_test_ball(position=Vec3(0.0, 0.0, 93.15))
    frames = [
        create_test_frame(
            0.0,
            [
                create_test_player("blue", 0, position=_at(-1000.0)),
                create_test_player("orange", 1, position=_at(-1000.0)),
            ],
            ball=ball,
        ),
        create_test_frame(
            0.1,
            [
                # Within 50 uu of level counts as neither
                create_test_player("blue", 0, position=_at(-40.0)),
                create_test_player("orange", 1, position=_at(1000.0)),
            ],
            ball=ball,
        ),
    ]
    stats = _stats(frames)
    assert stats["blue"]["behind_ball_pct"] == 50.0
    assert stats["orange"]["behind_ball_pct"] == 50.0
