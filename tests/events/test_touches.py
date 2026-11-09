"""Tests for placing the game's counted touches, and for touches from kicks alone."""

from __future__ import annotations

from dataclasses import replace

import pytest

from rlcoach.events.touches import detect_touches
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import TouchCount
from tests.fixtures.builders import (
    create_test_ball,
    create_test_frame,
    create_test_player,
)

DT = 1 / 30
ME = "me"
MATE = "mate"
OPP = "opp"
ORANGE = 1
BLUE = 0


def _car(pid, team, x, y, z=17.0):
    return create_test_player(pid, team, position=Vec3(x, y, z))


def _ball(x, y, z=93.15, vx=0.0, vy=0.0, vz=0.0):
    return create_test_ball(position=Vec3(x, y, z), velocity=Vec3(vx, vy, vz))


def _rolling(n, kicks=(), cars=None, hit_team=None):
    """`n` frames of the ball rolling up the field at 500 uu/s, past my car at
    frame 15 and the opponent's at frame 45. Each frame in `kicks` turns it round."""
    frames = []
    vy = 500.0
    for i in range(n):
        if i in kicks:
            vy = -vy
        players = (
            cars(i)
            if cars
            else [_car(ME, BLUE, 0.0, 0.0), _car(OPP, ORANGE, 0.0, 500.0)]
        )
        team = hit_team(i) if hit_team else None
        frames.append(
            create_test_frame(
                i * DT,
                players,
                _ball(0.0, -250.0 + 500.0 * i * DT, vy=vy),
                hit_team=team,
            )
        )
    return frames


def _count(frames, index, player, n=1):
    frames[index] = replace(frames[index], touch_counts=[TouchCount(player, n)])
    return frames


def _placed(frames):
    return [(touch.frame, touch.player_id) for touch in detect_touches(frames)]


def test_a_counted_touch_goes_at_the_kick_beside_the_player_before_the_count_rose():
    frames = _count(_rolling(40, kicks={15}), 30, ME)
    [touch] = detect_touches(frames)
    assert (touch.frame, touch.player_id, touch.team) == (15, ME, BLUE)
    assert touch.location == Vec3(0.0, 0.0, 17.0)
    assert touch.ball_speed_kph == pytest.approx(18.0)


def test_a_kick_nobody_counted_is_no_touch():
    frames = _count(_rolling(40, kicks={15, 25}), 20, ME)
    assert _placed(frames) == [(15, ME)]


def test_a_count_that_skips_places_every_touch_apart():
    frames = _count(_rolling(40, kicks={13, 15, 25}), 30, ME, n=2)
    # The two nearest the car, but 13 is too close behind 15 to be another touch
    assert _placed(frames) == [(15, ME), (25, ME)]


def test_a_touch_too_soft_to_kick_the_ball_goes_where_the_car_came_nearest():
    frames = _count(_rolling(40), 30, ME)
    assert _placed(frames) == [(15, ME)]


def test_a_change_of_the_balls_team_is_a_touch_on_that_frame():
    # The ball says orange touched it at 44, a frame before the kick shows
    frames = _rolling(60, kicks={45}, hit_team=lambda i: ORANGE if i >= 44 else None)
    frames = _count(frames, 58, OPP)
    assert _placed(frames) == [(44, OPP)]


def test_a_kick_where_the_ball_names_the_other_team_comes_last():
    # My count rose, and the ball's team is mine at 15 but orange's by 25
    frames = _rolling(40, kicks={15, 25}, hit_team=lambda i: BLUE if i < 25 else ORANGE)
    cars = [_car(ME, BLUE, 0.0, 0.0), _car(OPP, ORANGE, 0.0, -250.0 + 500.0 * 25 * DT)]
    frames = [replace(f, players=cars) for f in frames]
    frames = _count(frames, 30, ME)
    assert _placed(frames) == [(15, ME)]


def test_in_a_5050_inside_one_frame_the_team_the_ball_names_touches_last():
    both = [_car(ME, BLUE, 0.0, -150.0), _car(OPP, ORANGE, 0.0, 150.0)]
    frames = _rolling(
        40,
        kicks={10},
        cars=lambda i: both,
        hit_team=lambda i: ORANGE if i >= 10 else None,
    )
    frames = _count(_count(frames, 20, OPP), 25, ME)
    assert _placed(frames) == [(10, ME), (10, OPP)]


# Without the game's count: kicks alone


def test_without_the_count_a_kick_beside_a_car_is_its_touch():
    players = [_car(ME, ORANGE, 0.0, 1000.0, z=300.0)]
    frames = [
        create_test_frame(0.0, players, _ball(0.0, 900.0, 300.0, vy=500.0)),
        create_test_frame(DT, players, _ball(0.0, 917.0, 300.0, vy=500.0)),
        create_test_frame(2 * DT, players, _ball(0.0, 900.0, 300.0, vy=-1500.0)),
    ]
    assert _placed(frames) == [(2, ME)]


def test_without_the_count_a_floor_bounce_under_a_car_is_no_touch():
    players = [_car(ME, ORANGE, 150.0, 1000.0, z=240.0)]
    frames = [
        create_test_frame(
            0.0, players, _ball(0.0, 900.0, 110.0, vy=1700.0, vz=-1100.0)
        ),
        create_test_frame(DT, players, _ball(0.0, 957.0, 100.0, vy=1700.0, vz=-1140.0)),
        create_test_frame(
            2 * DT, players, _ball(0.0, 993.0, 130.0, vy=1085.0, vz=650.0)
        ),
    ]
    assert _placed(frames) == []


def test_without_the_count_a_ground_hit_with_the_car_already_past_is_a_touch():
    """From a real clear: the hit left the car 193 uu from a ball at z=100."""
    players = [_car(ME, ORANGE, 1500.0, -2820.0)]
    frames = [
        create_test_frame(
            0.0, players, _ball(1460.0, -2700.0, 100.0, vx=-790.0, vy=-1150.0)
        ),
        create_test_frame(
            DT, players, _ball(1430.0, -2640.0, 120.0, vx=-330.0, vy=1950.0, vz=900.0)
        ),
    ]
    assert _placed(frames) == [(1, ME)]


SHOT = [
    _car(MATE, ORANGE, -1042.0, 4715.0, z=140.0),
    _car(OPP, BLUE, -978.0, 4529.0, z=119.0),
]
SHOT_BEFORE = _ball(-1030.0, 4638.0, 273.0, vx=1142.0, vy=-440.0)
SHOT_AFTER = _ball(-975.0, 4647.0, 247.0, vx=1060.0, vy=1858.0, vz=1700.0)


def test_without_the_count_the_car_that_can_push_the_ball_that_way_kicked_it():
    """From a real shot: a defender stood nearest, on the far side of the ball."""
    frames = [
        create_test_frame(0.0, SHOT, SHOT_BEFORE),
        create_test_frame(DT, SHOT, SHOT_AFTER),
    ]
    assert _placed(frames) == [(1, OPP)]


def test_without_the_count_the_team_the_ball_names_kicked_it():
    """The other car only looks right: the ball says which team hit it."""
    frames = [
        create_test_frame(0.0, SHOT, SHOT_BEFORE),
        create_test_frame(DT, SHOT, SHOT_AFTER, hit_team=ORANGE),
    ]
    assert _placed(frames) == [(1, MATE)]


def test_without_the_count_the_nearest_car_keeps_a_kick_none_fits():
    """Car positions lag the ball, so a poor fit alone must not lose a touch."""
    players = [_car(ME, ORANGE, 0.0, 800.0, z=300.0)]
    frames = [
        create_test_frame(0.0, players, _ball(0.0, 900.0, 300.0, vy=500.0)),
        create_test_frame(DT, players, _ball(0.0, 917.0, 300.0, vy=-1500.0)),
    ]
    assert _placed(frames) == [(1, ME)]


def test_without_the_count_a_wall_bounce_beside_a_car_is_no_touch():
    players = [_car(ME, ORANGE, 3800.0, 1000.0, z=300.0)]
    frames = [
        create_test_frame(0.0, players, _ball(3990.0, 900.0, 300.0, vx=1500.0)),
        create_test_frame(DT, players, _ball(3970.0, 910.0, 300.0, vx=-900.0, vy=20.0)),
    ]
    assert _placed(frames) == []


def test_gravity_is_no_kick():
    players = [_car(ME, ORANGE, 0.0, 1000.0, z=300.0)]
    frames = [
        create_test_frame(i * DT, players, _ball(0.0, 950.0, 400.0, vz=-650.0 * i * DT))
        for i in range(5)
    ]
    assert _placed(frames) == []
