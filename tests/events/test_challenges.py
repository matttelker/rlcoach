"""Tests for finding 50/50s."""

from __future__ import annotations

from rlcoach.events.challenges import detect_challenges
from rlcoach.events.types import TouchEvent
from rlcoach.field_constants import Vec3
from tests.fixtures.builders import create_test_frame, create_test_player

FRAMES = [
    create_test_frame(
        0.0,
        [
            create_test_player("blue", 0),
            create_test_player("mate", 0),
            create_test_player("orange", 1),
        ],
    )
]


def _touch(t, player_id, x, speed=50.0):
    return TouchEvent(
        t=t, player_id=player_id, location=Vec3(x, 0.0, 17.0), ball_speed_kph=speed
    )


def _found(*touches):
    return [
        (c.t, c.first_player, c.second_player, c.winner_team)
        for c in detect_challenges(FRAMES, list(touches))
    ]


def test_opponents_touching_one_after_the_other_is_a_5050_won_by_the_second():
    assert _found(_touch(1.0, "blue", 0.0), _touch(1.4, "orange", 500.0)) == [
        (1.2, "blue", "orange", "ORANGE")
    ]


def test_touches_straight_after_are_one_scramble_won_by_the_last():
    found = _found(
        _touch(1.0, "blue", 0.0),
        _touch(1.4, "orange", 500.0),
        _touch(1.6, "blue", 400.0),
        _touch(1.7, "orange", 0.0),
        # Too late to be in it, so it starts none of its own with the scramble
        _touch(2.5, "blue", 400.0),
    )
    assert found == [(1.2, "blue", "orange", "ORANGE")]


def test_teammates_too_late_too_close_too_far_or_too_slow_are_no_5050():
    assert _found(_touch(1.0, "blue", 0.0), _touch(1.4, "mate", 500.0)) == []
    assert _found(_touch(1.0, "blue", 0.0), _touch(2.3, "orange", 500.0)) == []
    assert _found(_touch(1.0, "blue", 0.0), _touch(1.4, "orange", 150.0)) == []
    assert _found(_touch(1.0, "blue", 0.0), _touch(1.4, "orange", 1100.0)) == []
    slow = (_touch(1.0, "blue", 0.0, speed=10.0), _touch(1.4, "orange", 500.0, 10.0))
    assert _found(*slow) == []


def test_a_player_the_frames_never_show_is_in_no_5050():
    assert _found(_touch(1.0, "blue", 0.0), _touch(1.4, "ghost", 500.0)) == []


def test_a_5050_is_midway_between_the_two_cars():
    [challenge] = detect_challenges(
        FRAMES, [_touch(1.0, "blue", 0.0), _touch(1.4, "orange", 500.0)]
    )
    assert challenge.location == Vec3(250.0, 0.0, 17.0)
