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


def test_roles_go_by_distance_to_the_ball():
    ball = create_test_ball(position=Vec3(0.0, 0.0, 93.15))
    frames = [
        create_test_frame(
            t,
            [
                create_test_player("a", 0, position=_at(-500.0 - 1000.0 * t)),
                create_test_player("b", 0, position=_at(-2000.0)),
                create_test_player("c", 0, position=_at(-3000.0)),
                create_test_player("them", 1, position=_at(500.0)),
            ],
            ball=ball,
        )
        for t in (0.0, 1.0, 2.0, 3.0)
    ]
    a = _stats(frames)["a"]
    # Nearest twice, second once, and once behind both teammates
    assert (a["first_man_pct"], a["second_man_pct"], a["third_man_pct"]) == (
        50.0,
        25.0,
        25.0,
    )


def test_a_team_of_two_has_no_third_man_and_one_alone_is_always_first():
    frames = [
        create_test_frame(
            0.0,
            [
                create_test_player("a", 0, position=_at(-500.0)),
                create_test_player("b", 0, position=_at(-2000.0)),
                create_test_player("solo", 1, position=_at(3000.0)),
            ],
        )
    ]
    stats = _stats(frames)
    assert stats["a"]["third_man_pct"] is None
    assert (stats["b"]["first_man_pct"], stats["b"]["second_man_pct"]) == (0.0, 100.0)
    assert stats["solo"]["first_man_pct"] == 100.0
