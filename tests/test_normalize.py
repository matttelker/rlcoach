"""Tests for turning the parser's frames into Frames."""

from __future__ import annotations

from rlcoach.field_constants import Vec3
from rlcoach.normalize import X_LIMIT, Y_LIMIT, Z_RANGE, build_timeline
from rlcoach.parser.types import Header, PlayerInfo, Quaternion

HEADER = Header(
    players=[
        PlayerInfo(name="Me", platform_ids={"epic": "me"}, team=0),
        PlayerInfo(name="Them", platform_ids={"steam": "1"}, team=1),
    ]
)
ME, THEM = "epic:me", "steam:1"
LEVEL = (0.0, 0.0, 0.0, 1.0)
STILL = (0.0, 0.0, 0.0)


def _car(row=0, team=0, *, position=(0.0, 0.0, 17.0), velocity=STILL, spin=STILL,
         rotation=LEVEL, boost=33, demolished=False):  # fmt: skip
    return (row, team, position, velocity, spin, rotation, boost, demolished)


def _frame(t, cars=(), ball=((0.0, 0.0, 93.15), STILL), **events):
    return {
        "time": t,
        "ball": ball,
        "cars": list(cars),
        "pickups": [],
        "dodges": [],
        "touches": [],
        "first_touches": [],
        "demos": [],
        **events,
    }


def _one(*cars, header=HEADER, **events):
    [frame] = build_timeline(header, [_frame(5.0, cars, **events)])
    return frame


def test_times_count_from_the_first_frame_in_time_order():
    frames = build_timeline(HEADER, [_frame(12.5, [_car()]), _frame(10.0, [_car()])])
    assert [f.timestamp for f in frames] == [0.0, 2.5]
    # A clock a hair off the first frame reads 0
    frames = build_timeline(HEADER, [_frame(10.0), _frame(10.0000001)])
    assert [f.timestamp for f in frames] == [0.0, 0.0]


def test_cars_take_their_header_players_ids_and_leavers_keep_the_parsers():
    frame = _one(_car(0), _car(1, team=1), _car(7))
    assert [car.player_id for car in frame.players] == [ME, THEM, "player_7"]


def test_a_car_listed_twice_keeps_its_last_state():
    frame = _one(_car(boost=10), _car(1, 1), _car(boost=40))
    assert [(c.player_id, c.boost_amount) for c in frame.players] == [
        (ME, 40),
        (THEM, 33),
    ]


def test_the_headers_orange_stands_and_otherwise_the_frame_says():
    frames = build_timeline(
        HEADER,
        [_frame(0.0, [_car(0, 1), _car(1, 0)]), _frame(1.0, [_car(0, 0), _car(1, 0)])],
    )
    assert [[c.team for c in f.players] for f in frames] == [[1, 1], [0, 1]]


def test_someone_the_header_misses_keeps_orange_from_their_first_frame():
    frames = build_timeline(
        HEADER,
        [_frame(0.0, [_car(7, 1), _car(8, 0)]), _frame(1.0, [_car(7, 0), _car(8, 1)])],
    )
    assert [[c.team for c in f.players] for f in frames] == [[1, 0], [1, 1]]


def test_positions_are_held_to_the_field_but_speeds_are_not():
    far = (9000.0, -9000.0, 9000.0)
    car = _one(_car(position=far, velocity=far)).players[0]
    assert car.position == Vec3(X_LIMIT, -Y_LIMIT, Z_RANGE[1])
    assert car.velocity == Vec3(*far)
    low = _one(_car(position=(-9000.0, 9000.0, -500.0))).players[0]
    assert low.position == Vec3(-X_LIMIT, Y_LIMIT, Z_RANGE[0])
    frame = _one(ball=(far, far))
    assert frame.ball.position == Vec3(X_LIMIT, -Y_LIMIT, Z_RANGE[1])
    assert frame.ball.velocity == Vec3(*far)


def test_boost_is_held_from_0_to_100():
    boosts = [_one(_car(boost=raw)).players[0].boost_amount for raw in (-5, 33, 250)]
    assert boosts == [0, 33, 100]


def test_a_car_keeps_its_spin_and_rotation_and_whether_its_demolished():
    car = _one(_car(spin=(1.0, -2.0, 3.0), demolished=True)).players[0]
    assert car.angular_velocity == Vec3(1.0, -2.0, 3.0)
    assert car.quaternion == Quaternion(0.0, 0.0, 0.0, 1.0)
    assert car.is_demolished
    plain = _one(_car(rotation=None)).players[0]
    assert plain.quaternion is None
    assert not plain.is_demolished


def test_touches_on_one_frame_come_in_player_order_at_the_frames_time():
    frame = _one(touches=[1, 0], first_touches=[0])
    assert [(e.player_id, e.timestamp) for e in frame.parser_touch_events] == [
        (ME, 0.0),
        (THEM, 0.0),
    ]
    [first] = frame.parser_first_touch_events
    assert first.player_id == ME


def test_demos_name_their_players_and_may_have_no_attacker():
    frame = _one(demos=[(0, 1), (1, None)])
    assert [(e.victim_id, e.attacker_id) for e in frame.parser_demo_events] == [
        (ME, THEM),
        (THEM, None),
    ]


def test_dodges_keep_their_torque_and_player():
    [dodge] = _one(dodges=[(1, (0.0, 2.24, 0.0))]).dodges
    assert (dodge.player_id, dodge.torque) == (THEM, Vec3(0.0, 2.24, 0.0))


def test_pickups_keep_their_own_time_and_team():
    frames = build_timeline(
        HEADER, [_frame(5.0), _frame(6.0, pickups=[(3, 1, None, 5.25)])]
    )
    [pad] = frames[1].boost_pad_events
    assert (pad.pad_id, pad.player_id, pad.player_team, pad.timestamp) == (
        3,
        THEM,
        None,
        0.25,
    )
