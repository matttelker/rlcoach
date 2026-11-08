"""Tests for finding who took each boost pad and what it gave them."""

from __future__ import annotations

import pytest

from rlcoach.events.boost import detect_boost_pickups, is_stolen
from rlcoach.field_constants import BOOST_PADS, Vec3
from rlcoach.parser.types import BoostPadEventFrame
from tests.fixtures.builders import create_test_frame, create_test_player

STEP = 1 / 30


def _pad(x, y):
    return next(p for p in BOOST_PADS if (p.position.x, p.position.y) == (x, y))


BLUE_CORNER = _pad(-3072.0, -4096.0)  # Big, on blue's half
ORANGE_CORNER = _pad(3072.0, 4096.0)  # Big, on orange's half
MIDFIELD_BIG = _pad(-3584.0, 0.0)
BLUE_SMALL = _pad(0.0, -2816.0)
ORANGE_SMALL = _pad(0.0, 2816.0)


def _at(pad):
    return Vec3(pad.position.x, pad.position.y, 17.0)


def _taken(pad, player_id="me", t=None, team=None, status="COLLECTED"):
    return BoostPadEventFrame(
        pad_id=pad.pad_id,
        status=status,
        is_big=pad.is_big,
        player_id=player_id,
        player_team=team,
        timestamp=t,
    )


def _frames(boosts, *, team=0, where=None, events=None, demolished=()):
    """One car's frames: its boost on each, and pad events keyed by index."""
    events = events or {}
    frames = []
    for i, boost in enumerate(boosts):
        position = where(i) if callable(where) else where
        car = create_test_player(
            "me",
            team,
            position=position or Vec3(0.0, -1500.0, 17.0),
            boost=boost,
            is_demolished=i in demolished,
        )
        frames.append(create_test_frame(i * STEP, [car], pad_events=events.get(i, [])))
    return frames


# From pad events


def test_a_pad_event_gives_what_the_tank_shows():
    frames = _frames([20, 32, 32], events={1: [_taken(BLUE_SMALL)]})
    [pickup] = detect_boost_pickups(frames)
    assert (pickup.player_id, pickup.pad_id) == ("me", BLUE_SMALL.pad_id)
    assert pickup.boost_gain == 12.0
    assert pickup.t == pytest.approx(STEP)
    assert not pickup.stolen


def test_a_tank_that_hasnt_caught_up_gets_what_the_pad_holds():
    # The tank fills a frame later, or not at all for a full car
    frames = _frames([20, 20, 32], events={1: [_taken(BLUE_SMALL)]})
    assert [p.boost_gain for p in detect_boost_pickups(frames)] == [12.0]
    frames = _frames([95, 95, 95], events={1: [_taken(BLUE_CORNER)]})
    assert [p.boost_gain for p in detect_boost_pickups(frames)] == [5.0]
    frames = _frames([100, 100], events={1: [_taken(BLUE_CORNER)]})
    assert [p.boost_gain for p in detect_boost_pickups(frames)] == [0.0]


def test_a_car_missing_from_the_frame_gets_what_the_pad_holds():
    frames = _frames([90, 90])
    frames[1] = create_test_frame(STEP, [], pad_events=[_taken(BLUE_CORNER, t=STEP)])
    assert [p.boost_gain for p in detect_boost_pickups(frames)] == [10.0]


def test_two_pickups_on_one_frame_share_the_rise():
    frames = _frames(
        [20, 44], events={1: [_taken(BLUE_SMALL), _taken(_pad(940.0, -3308.0))]}
    )
    assert [p.boost_gain for p in detect_boost_pickups(frames)] == [24.0, 12.0]


def test_a_pad_replicated_again_before_it_respawns_is_one_pickup():
    boosts = [20] * 400
    events = {
        1: [_taken(BLUE_SMALL, t=1.0)],
        2: [_taken(BLUE_SMALL, t=4.8)],  # Inside the 4 s respawn, with tolerance
        3: [_taken(BLUE_SMALL, t=4.9)],
        4: [_taken(BLUE_CORNER, t=5.0)],
        5: [_taken(BLUE_CORNER, t=14.8)],
        6: [_taken(BLUE_CORNER, t=14.9)],
    }
    frames = _frames(boosts, events=events)
    taken = [(p.pad_id, p.t) for p in detect_boost_pickups(frames)]
    assert taken == [
        (BLUE_SMALL.pad_id, 1.0),
        (BLUE_SMALL.pad_id, 4.9),
        (BLUE_CORNER.pad_id, 5.0),
        (BLUE_CORNER.pad_id, 14.9),
    ]


def test_pickups_come_in_the_order_the_events_happened():
    events = {1: [_taken(BLUE_SMALL, t=0.5), _taken(BLUE_CORNER, t=0.2)]}
    frames = _frames([20, 20], events=events)
    assert [p.t for p in detect_boost_pickups(frames)] == [0.2, 0.5]


def test_events_without_a_car_a_known_pad_or_a_pickup_are_skipped():
    unknown_pad = BoostPadEventFrame(
        pad_id=len(BOOST_PADS), status="COLLECTED", is_big=False, player_id="me"
    )
    events = {
        1: [
            _taken(BLUE_SMALL, player_id=None),
            _taken(ORANGE_SMALL, status="RESPAWNED"),
            unknown_pad,
            _taken(BLUE_CORNER),
        ]
    }
    frames = _frames([20, 20], events=events)
    assert [p.pad_id for p in detect_boost_pickups(frames)] == [BLUE_CORNER.pad_id]


@pytest.mark.parametrize(
    ("pad", "team", "stolen"),
    [
        (ORANGE_CORNER, 0, True),
        (BLUE_CORNER, 0, False),
        (BLUE_SMALL, 1, True),
        (ORANGE_SMALL, 1, False),
        (MIDFIELD_BIG, 0, False),  # Halfway pads are nobody's
        (MIDFIELD_BIG, 1, False),
        (ORANGE_CORNER, None, False),
    ],
)
def test_a_pad_on_the_other_teams_half_is_stolen(pad, team, stolen):
    assert is_stolen(pad, team) is stolen


def test_the_events_team_decides_a_steal_and_the_cars_stands_in():
    frames = _frames([20, 32], events={1: [_taken(ORANGE_SMALL, team=1)]})
    assert not detect_boost_pickups(frames)[0].stolen
    frames = _frames([20, 32], events={1: [_taken(ORANGE_SMALL)]})
    assert detect_boost_pickups(frames)[0].stolen


# From the tanks


def test_without_pad_events_each_rise_is_a_pickup_at_the_pad_driven_over():
    frames = _frames([10, 10, 22, 22, 100], where=_at(BLUE_SMALL))
    frames[4] = create_test_frame(
        4 * STEP, [create_test_player("me", 0, position=_at(ORANGE_CORNER), boost=100)]
    )
    pickups = detect_boost_pickups(frames)
    assert [(p.pad_id, p.boost_gain) for p in pickups] == [
        (BLUE_SMALL.pad_id, 12.0),
        (ORANGE_CORNER.pad_id, 78.0),
    ]
    assert [p.stolen for p in pickups] == [False, True]
    assert pickups[0].t == pytest.approx(2 * STEP)


def test_the_pad_is_the_one_passed_closest_to_just_before():
    # The rise shows up two frames after the car drove over the pad
    path = [_at(BLUE_SMALL), Vec3(300.0, -2600.0, 17.0), Vec3(600.0, -2400.0, 17.0)]
    frames = _frames([10, 10, 22], where=lambda i: path[i])
    [pickup] = detect_boost_pickups(frames)
    assert pickup.pad_id == BLUE_SMALL.pad_id


def test_the_pad_is_one_of_the_size_the_rise_fits():
    # Nearer the big corner pad than any small one
    between = Vec3(-2700.0, -3600.0, 17.0)
    small = detect_boost_pickups(_frames([10, 22], where=between))
    big = detect_boost_pickups(_frames([10, 50], where=between))
    assert small[0].pad_id == _pad(-1792.0, -4184.0).pad_id
    assert big[0].pad_id == BLUE_CORNER.pad_id


def test_a_steal_needs_the_car_to_have_come_within_reach_of_the_pad():
    near = detect_boost_pickups(_frames([10, 22], where=Vec3(0.0, 1100.0, 17.0)))
    far = detect_boost_pickups(_frames([10, 22], where=Vec3(0.0, 1800.0, 17.0)))
    assert near[0].pad_id == far[0].pad_id == _pad(0.0, 1024.0).pad_id
    assert (near[0].stolen, far[0].stolen) == (True, False)


def test_a_kickoff_or_respawn_reset_far_from_the_pads_is_no_pickup():
    far = Vec3(0.0, 0.0, 17.0)  # Over 1000 uu from every pad
    assert detect_boost_pickups(_frames([0, 33], where=far)) == []
    assert detect_boost_pickups(_frames([0, 35], where=far)) == []
    # The same rise beside a pad is a pickup
    assert len(detect_boost_pickups(_frames([0, 33], where=_at(BLUE_CORNER)))) == 1


def test_the_respawn_fill_after_a_demolition_is_no_pickup():
    near = _at(BLUE_SMALL)
    frames = _frames([40, 40, 0, 0, 33, 45], where=near, demolished={2, 3})
    assert [p.boost_gain for p in detect_boost_pickups(frames)] == [12.0]
    # A first rise past what a respawn gives is a pickup after all
    frames = _frames([40, 40, 0, 50], where=near, demolished={2})
    assert [p.boost_gain for p in detect_boost_pickups(frames)] == [50.0]


def test_drops_and_rises_under_one_are_no_pickups():
    assert detect_boost_pickups(_frames([50, 40, 40.5, 30])) == []


def test_sparse_pad_events_give_way_to_the_tanks():
    rises = [10, 22, 34, 46, 58]
    near = _at(BLUE_SMALL)
    sparse = _frames(rises, where=near, events={1: [_taken(BLUE_SMALL)]})
    assert len(detect_boost_pickups(sparse)) == 4
    complete = _frames(
        rises,
        where=near,
        events={1: [_taken(BLUE_SMALL, t=0.0)], 3: [_taken(BLUE_SMALL, t=5.0)]},
    )
    assert [p.t for p in detect_boost_pickups(complete)] == [0.0, 5.0]
