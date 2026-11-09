from rlcoach.field_constants import Vec3
from rlcoach.parser.types import Quaternion

from . import (
    create_simple_replay_frames,
    create_test_frame,
    create_test_player,
    with_flip_at,
)


def test_a_test_car_is_still_at_the_centre_unless_told_otherwise():
    car = create_test_player("player1", 1)
    assert (car.position, car.velocity, car.boost_amount) == (
        Vec3(0.0, 0.0, 17.0),
        Vec3(0.0, 0.0, 0.0),
        50.0,
    )
    assert car.quaternion is None
    turned = create_test_player(
        "player1",
        0,
        angular_velocity=Vec3(1.0, 2.0, 3.0),
        quaternion=Quaternion(0.0, 0.0, 0.0, 1.0),
        is_demolished=True,
    )
    assert turned.angular_velocity == Vec3(1.0, 2.0, 3.0)
    assert turned.quaternion == Quaternion(0.0, 0.0, 0.0, 1.0)
    assert turned.is_demolished


def test_simple_frames_come_at_a_steady_rate():
    frames = create_simple_replay_frames(duration_seconds=1.0, frame_rate=4.0)
    assert [f.timestamp for f in frames] == [0.0, 0.25, 0.5, 0.75]
    assert [p.player_id for p in frames[0].players] == ["player1", "player2"]


def test_with_flip_at_adds_a_dodge_to_the_nearest_frame():
    frames = create_simple_replay_frames(
        duration_seconds=1.0, frame_rate=2.0, players=[("player1", 0)]
    )
    updated = with_flip_at(frames, 0.4, "player1", Vec3(0.0, 1.0, 0.0))
    assert frames[1].dodges == []
    [dodge] = updated[1].dodges
    assert (dodge.timestamp, dodge.player_id, dodge.torque) == (
        0.5,
        "player1",
        Vec3(0.0, 1.0, 0.0),
    )
    assert updated[0] is frames[0]


def test_a_test_frame_carries_the_parsers_events():
    frame = create_test_frame(1.0, [create_test_player("player1", 0)])
    assert (frame.dodges, frame.touch_counts, frame.boost_pad_events) == (
        [],
        [],
        [],
    )
