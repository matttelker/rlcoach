"""Tests for the parser's touches."""

from __future__ import annotations

import pytest

from rlcoach.events.touches import detect_touches
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import ParserTouchEvent
from tests.fixtures.builders import (
    create_test_ball,
    create_test_frame,
    create_test_player,
)

CAR = Vec3(100.0, 200.0, 17.0)
BALL = create_test_ball(
    position=Vec3(150.0, 250.0, 93.15), velocity=Vec3(1000.0, 0.0, 0.0)
)


def _touch(t, player_id):
    return ParserTouchEvent(timestamp=t, player_id=player_id)


def test_a_touch_is_placed_at_the_car_with_the_balls_speed():
    frame = create_test_frame(
        1.0,
        [create_test_player("me", 0, position=CAR)],
        ball=BALL,
        touches=[_touch(1.0, "me")],
    )
    [touch] = detect_touches([frame])
    assert (touch.t, touch.player_id, touch.location) == (1.0, "me", CAR)
    assert touch.ball_speed_kph == pytest.approx(36.0)


def test_a_touch_by_a_car_the_frame_lacks_is_placed_at_the_ball():
    frame = create_test_frame(1.0, [], ball=BALL, touches=[_touch(1.0, "gone")])
    assert detect_touches([frame])[0].location == BALL.position


def test_a_repeated_touch_counts_once_and_touches_come_in_time_order():
    frames = [
        create_test_frame(2.0, [], ball=BALL, touches=[_touch(2.0, "b")]),
        create_test_frame(
            1.0, [], ball=BALL, touches=[_touch(1.0, "a"), _touch(1.0, "a")]
        ),
        create_test_frame(2.1, [], ball=BALL, touches=[_touch(2.0, "b")]),
    ]
    assert [(t.t, t.player_id) for t in detect_touches(frames)] == [
        (1.0, "a"),
        (2.0, "b"),
    ]
