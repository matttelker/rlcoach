"""Tests for turning the parser's frames into Frames."""

from __future__ import annotations

import pytest

from rlcoach.field_constants import Vec3
from rlcoach.normalize import X_LIMIT, Y_LIMIT, Z_RANGE, build_timeline
from rlcoach.parser.types import Header, PlayerInfo, Quaternion

HEADER = Header(
    players=[
        PlayerInfo(name="Me", platform_id="Epic|me", team=0),
        PlayerInfo(name="Them", platform_id="Steam|1", team=1),
    ]
)
ME, THEM = "epic:me", "steam:1"


def _xyz(x=0.0, y=0.0, z=0.0):
    return {"x": x, "y": y, "z": z}


def _car(player_id="player_0", team=0, **fields):
    return {
        "player_id": player_id,
        "team": team,
        "position": _xyz(z=17.0),
        "velocity": _xyz(),
        "angular_velocity": _xyz(),
        "rotation": {
            "pitch": 0.0,
            "yaw": 0.0,
            "roll": 0.0,
            "quaternion": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        },
        "boost_amount": 33,
        **fields,
    }


def _frame(t, cars=(), ball=None, **events):
    return {
        "timestamp": t,
        "ball": ball
        or {
            "position": _xyz(z=93.15),
            "velocity": _xyz(),
            "angular_velocity": _xyz(),
        },
        "players": list(cars),
        "boost_pad_events": [],
        "component_events": [],
        "parser_touch_events": [],
        "parser_first_touch_events": [],
        "parser_demo_events": [],
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
    frame = _one(_car("player_0"), _car("player_1", team=1), _car("player_7"))
    assert [car.player_id for car in frame.players] == [ME, THEM, "player_7"]


def test_a_car_listed_twice_keeps_its_last_state():
    frame = _one(_car(boost_amount=10), _car("player_1", 1), _car(boost_amount=40))
    assert [(c.player_id, c.boost_amount) for c in frame.players] == [
        (ME, 40),
        (THEM, 33),
    ]


def test_the_headers_orange_stands_and_otherwise_the_frame_says():
    frames = build_timeline(
        HEADER,
        [
            _frame(0.0, [_car("player_0", 1), _car("player_1", 0)]),
            _frame(1.0, [_car("player_0", 0), _car("player_1", 0)]),
        ],
    )
    assert [[c.team for c in f.players] for f in frames] == [[1, 1], [0, 1]]


def test_someone_the_header_misses_keeps_orange_from_their_first_frame():
    frames = build_timeline(
        HEADER,
        [
            _frame(0.0, [_car("player_7", 1), _car("player_8", 0)]),
            _frame(1.0, [_car("player_7", 0), _car("player_8", 1)]),
        ],
    )
    assert [[c.team for c in f.players] for f in frames] == [[1, 0], [1, 1]]


def test_positions_are_held_to_the_field_but_speeds_are_not():
    far = _xyz(9000.0, -9000.0, 9000.0)
    car = _one(_car(position=far, velocity=far)).players[0]
    assert car.position == Vec3(X_LIMIT, -Y_LIMIT, Z_RANGE[1])
    assert car.velocity == Vec3(9000.0, -9000.0, 9000.0)
    low = _one(_car(position=_xyz(-9000.0, 9000.0, -500.0))).players[0]
    assert low.position == Vec3(-X_LIMIT, Y_LIMIT, Z_RANGE[0])
    ball = {"position": far, "velocity": far, "angular_velocity": _xyz(1.0, 2.0, 3.0)}
    frame = _one(ball=ball)
    assert frame.ball.position == Vec3(X_LIMIT, -Y_LIMIT, Z_RANGE[1])
    assert frame.ball.velocity == Vec3(9000.0, -9000.0, 9000.0)
    assert frame.ball.angular_velocity == Vec3(1.0, 2.0, 3.0)


def test_boost_is_a_whole_number_from_0_to_100():
    boosts = [
        _one(_car(boost_amount=raw)).players[0].boost_amount for raw in (-5, 33.9, 250)
    ]
    assert boosts == [0, 33, 100]


def test_a_car_keeps_its_spin_and_orientation_and_whether_its_demolished():
    car = _one(_car(angular_velocity=_xyz(1.0, -2.0, 3.0), is_demolished=True)).players[
        0
    ]
    assert car.angular_velocity == Vec3(1.0, -2.0, 3.0)
    assert car.rotation.quaternion == Quaternion(0.0, 0.0, 0.0, 1.0)
    assert car.is_demolished
    rotation = {"pitch": 0.1, "yaw": 0.2, "roll": 0.3}
    plain = _one(_car(rotation=rotation)).players[0]
    assert (plain.rotation.yaw, plain.rotation.quaternion) == (0.2, None)
    assert not plain.is_demolished


def _touch(player_id, t=5.5, team=0):
    return {"timestamp": t, "player_id": player_id, "team": team}


def test_touches_on_one_frame_come_in_player_order_at_shifted_times():
    frame = _one(
        parser_touch_events=[_touch("player_1", team=1), _touch("player_0")],
        parser_first_touch_events=[_touch("player_0", t=6.0)],
    )
    assert [(e.player_id, e.timestamp) for e in frame.parser_touch_events] == [
        (ME, 0.5),
        (THEM, 0.5),
    ]
    [first] = frame.parser_first_touch_events
    assert (first.player_id, first.timestamp, first.team) == (ME, 1.0, 0)


def test_demos_name_their_players_and_may_have_no_attacker():
    demos = [
        {"timestamp": 6.0, "victim_id": "player_0", "attacker_id": "player_1"},
        {"timestamp": 7.0, "victim_id": "player_1", "attacker_id": None},
    ]
    frame = _one(parser_demo_events=demos)
    assert [
        (e.timestamp, e.victim_id, e.attacker_id) for e in frame.parser_demo_events
    ] == [(1.0, ME, THEM), (2.0, THEM, None)]


def test_dodges_keep_their_torque_and_player():
    events = [
        {
            "timestamp": 5.5,
            "kind": "dodge_torque",
            "component": "dodge",
            "player_id": "player_1",
            "vector": _xyz(0.0, 1.0, 0.0),
        },
        {"timestamp": 5.5, "kind": "active", "component": "jump"},
    ]
    torque, jump = _one(component_events=events).component_events
    assert (torque.player_id, torque.vector, torque.timestamp) == (
        THEM,
        Vec3(0.0, 1.0, 0.0),
        0.5,
    )
    assert (jump.kind, jump.component, jump.player_id, jump.vector) == (
        "active",
        "jump",
        None,
        None,
    )


@pytest.mark.parametrize(
    ("named", "player_id"),
    [
        ({"player_id": "player_1"}, THEM),
        ({"player_index": 0}, ME),
        ({}, None),
    ],
)
def test_pad_events_name_the_player_by_id_or_by_row(named, player_id):
    event = {"pad_id": 3, "status": "collected", "is_big": True, **named}
    [pad] = _one(boost_pad_events=[{**event, "timestamp": 5.25}]).boost_pad_events
    assert (pad.pad_id, pad.status, pad.is_big) == (3, "COLLECTED", True)
    assert (pad.player_id, pad.timestamp) == (player_id, 0.25)
    [untimed] = _one(boost_pad_events=[event]).boost_pad_events
    assert untimed.timestamp is None
