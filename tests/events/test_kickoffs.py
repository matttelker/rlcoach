"""Tests for finding kickoffs and reading how each car played them."""

from __future__ import annotations

from dataclasses import replace

import pytest

from rlcoach.events.kickoffs import (
    detect_kickoffs,
    is_held_for_kickoff,
    releases,
)
from rlcoach.events.types import GoalEvent
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import ParserTouchEvent, Quaternion
from tests.fixtures.builders import (
    create_test_ball,
    create_test_frame,
    create_test_player,
    with_flip_at,
)

STEP = 0.05
STILL = Vec3(0.0, 0.0, 0.0)
HIT = Vec3(0.0, 600.0, 0.0)  # The ball leaves toward orange's goal
DIAGONAL = Vec3(-2048.0, -2560.0, 17.0)
OTHER_DIAGONAL = Vec3(2048.0, -2560.0, 17.0)
OFFSET = Vec3(-256.0, -3840.0, 17.0)
ORANGE_DIAGONAL = Vec3(2048.0, 2560.0, 17.0)
BESIDE_BALL = Vec3(-60.0, -200.0, 17.0)  # In reach, on blue's side of it
ORANGE_BESIDE = Vec3(60.0, 200.0, 17.0)
UPSIDE_DOWN = Quaternion(1.0, 0.0, 0.0, 0.0)
LEVEL = Quaternion(0.0, 0.0, 0.0, 1.0)


def drive(spawn, target, arrive_s=2.0, boost_used=0.0, **extra):
    """A car going from its spawn to `target`, there by `arrive_s`.

    By default it gets there as the ball is played. A car that stops beside the
    ball first would hold the kickoff still, which real kickoffs never do.
    """

    def at(elapsed):
        share = min(1.0, elapsed / arrive_s)
        moving = share < 1.0
        return {
            "position": spawn + (target - spawn) * share,
            "velocity": (target - spawn) * (1.0 / arrive_s) if moving else STILL,
            "boost": 33.0 - boost_used * share,
            **{k: v(elapsed) if callable(v) else v for k, v in extra.items()},
        }

    return at


def stay(spawn):
    return lambda elapsed: {"position": spawn, "boost": 33.0}


def kickoff(cars, *, hit_s=2.0, hit=HIT, hold_s=3.0, play_s=2.5):
    """A countdown, then the cars released. `cars` is (id, team, spawn, path)."""
    frames = []
    for i in range(int(round(hold_s / STEP)) + 1):
        players = [
            create_test_player(pid, team, position=spawn, boost=33.0)
            for pid, team, spawn, _ in cars
        ]
        frames.append(create_test_frame(i * STEP, players))
    release = frames[-1].timestamp
    for k in range(1, int(round(play_s / STEP)) + 1):
        elapsed = k * STEP
        players = [
            create_test_player(pid, team, **path(elapsed))
            for pid, team, _, path in cars
        ]
        ball = create_test_ball()
        if hit_s is not None and elapsed >= hit_s - 1e-9:
            # Played, and gone from the spot a frame later
            gone = ball.position + hit * (elapsed - hit_s + STEP)
            ball = create_test_ball(position=gone, velocity=hit)
        frames.append(create_test_frame(release + elapsed, players, ball=ball))
    return frames, release


def _one(frames, goals=()):
    [found] = detect_kickoffs(frames, list(goals))
    return found


def _player(found, player_id):
    return next(p for p in found.players if p.player_id == player_id)


def _go_against(blue_path, orange_path=None, **options):
    """Blue's GO car against an orange one, waiting at its spawn by default."""
    return kickoff(
        [
            ("blue", 0, DIAGONAL, blue_path),
            ("orange", 1, ORANGE_DIAGONAL, orange_path or stay(ORANGE_DIAGONAL)),
        ],
        **options,
    )


def _fake(blue_path, **options):
    """Blue's GO car not going, and orange's taking the ball."""
    orange = drive(ORANGE_DIAGONAL, ORANGE_BESIDE)
    return _go_against(blue_path, orange, hit=Vec3(0.0, -600.0, 0.0), **options)


# Countdowns


def test_a_countdown_releases_on_its_last_held_frame():
    frames, release = _go_against(drive(DIAGONAL, BESIDE_BALL))
    [index] = releases(frames)
    assert frames[index].timestamp == release


def test_a_short_stop_on_the_spot_is_no_countdown():
    frames, _ = _go_against(drive(DIAGONAL, BESIDE_BALL), hold_s=1.0)
    assert releases(frames) == set()
    assert detect_kickoffs(frames, []) == []


def test_a_car_twitching_mid_countdown_keeps_the_release():
    frames, release = _go_against(drive(DIAGONAL, BESIDE_BALL))
    twitch = create_test_player("blue", 0, position=DIAGONAL, velocity=HIT)
    frames[30] = replace(frames[30], players=[twitch, frames[30].players[1]])
    assert [frames[i].timestamp for i in releases(frames)] == [release]


def test_held_means_the_ball_on_the_spot_and_every_car_still():
    car = create_test_player("me", 0)
    assert is_held_for_kickoff(create_test_frame(0.0, [car]))
    away = create_test_ball(position=Vec3(0.0, 2000.0, 93.15))
    assert not is_held_for_kickoff(create_test_frame(0.0, [car], ball=away))
    moving = create_test_player("them", 1, velocity=HIT)
    assert not is_held_for_kickoff(create_test_frame(0.0, [car, moving]))
    assert not is_held_for_kickoff(create_test_frame(0.0, []))


# The first touch


def test_times_count_from_the_release_to_the_frame_the_ball_was_played():
    frames, release = _go_against(drive(DIAGONAL, BESIDE_BALL))
    found = _one(frames)
    assert found.t_start == release
    assert found.time_to_first_touch == pytest.approx(2.0)
    assert (found.first_touch_player, found.first_touch_team) == ("blue", "BLUE")
    assert _player(found, "blue").time_to_ball == pytest.approx(2.0)


def test_the_ball_leaving_away_from_a_car_says_who_won_a_5050():
    frames, _ = kickoff(
        [
            ("blue", 0, DIAGONAL, drive(DIAGONAL, BESIDE_BALL)),
            ("orange", 1, ORANGE_DIAGONAL, drive(ORANGE_DIAGONAL, ORANGE_BESIDE)),
        ],
        hit=Vec3(0.0, -600.0, 0.0),
    )
    found = _one(frames)
    assert found.first_touch_player == "orange"
    # Both were in reach, so both reached the ball
    assert _player(found, "blue").time_to_ball == pytest.approx(2.0)


def _with_counter(frames, at, player_id):
    index = min(range(len(frames)), key=lambda i: abs(frames[i].timestamp - at))
    event = ParserTouchEvent(timestamp=at, player_id=player_id, team=0)
    frames[index] = replace(frames[index], parser_first_touch_events=[event])
    return frames


def test_the_games_counter_names_the_first_touch_but_the_frames_time_it():
    frames, release = kickoff(
        [
            ("blue", 0, DIAGONAL, drive(DIAGONAL, BESIDE_BALL)),
            ("orange", 1, ORANGE_DIAGONAL, drive(ORANGE_DIAGONAL, ORANGE_BESIDE)),
        ],
        hit=Vec3(0.0, -600.0, 0.0),
    )
    # The counter arrives up to a second after the contact
    found = _one(_with_counter(frames, release + 2.9, "blue"))
    assert (found.first_touch_player, found.first_touch_team) == ("blue", "BLUE")
    assert found.time_to_first_touch == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("late", "player_id"),
    [(3.6, "blue"), (-0.5, "blue"), (2.9, "joined_late")],
)
def test_a_counter_outside_the_kickoff_or_for_someone_else_is_ignored(late, player_id):
    frames, release = kickoff(
        [
            ("blue", 0, DIAGONAL, drive(DIAGONAL, BESIDE_BALL)),
            ("orange", 1, ORANGE_DIAGONAL, drive(ORANGE_DIAGONAL, ORANGE_BESIDE)),
        ],
        hit=Vec3(0.0, -600.0, 0.0),
        play_s=4.0,
    )
    found = _one(_with_counter(frames, release + late, player_id))
    assert found.first_touch_player == "orange"


def test_a_kickoff_nobody_plays_ends_after_5_s_with_no_first_touch():
    # Still driving when the recording stops, so nothing holds still again
    wandering = drive(DIAGONAL, Vec3(-3000.0, -3000.0, 17.0), arrive_s=10.0)
    frames, _ = _go_against(wandering, hit_s=None, play_s=6.0)
    found = _one(frames)
    assert found.first_touch_player is found.first_touch_team is None
    assert _player(found, "blue").time_to_ball is None


# Roles


def test_the_car_nearest_the_spot_goes_and_the_rest_take_their_spawns_roles():
    # Further from the ball than GO but not as far back as BACK
    cheat = Vec3(1600.0, 3100.0, 17.0)
    frames, _ = kickoff(
        [
            ("go", 0, DIAGONAL, drive(DIAGONAL, BESIDE_BALL)),
            ("wing", 0, OTHER_DIAGONAL, stay(OTHER_DIAGONAL)),
            ("back", 0, OFFSET, stay(OFFSET)),
            ("cheat", 1, cheat, stay(cheat)),
            ("orange_go", 1, ORANGE_DIAGONAL, stay(ORANGE_DIAGONAL)),
        ]
    )
    roles = {p.player_id: p.role for p in _one(frames).players}
    assert roles == {
        "go": "GO",
        "wing": "WING",
        "back": "BACK",
        "orange_go": "GO",
        "cheat": "CHEAT",
    }


def test_level_spawns_give_go_to_the_teammate_who_went():
    frames, _ = kickoff(
        [
            ("left", 0, DIAGONAL, stay(DIAGONAL)),
            ("right", 0, OTHER_DIAGONAL, drive(OTHER_DIAGONAL, BESIDE_BALL)),
            ("orange", 1, ORANGE_DIAGONAL, stay(ORANGE_DIAGONAL)),
        ]
    )
    found = _one(frames)
    assert (_player(found, "right").role, _player(found, "left").role) == ("GO", "WING")


def test_a_spawn_further_back_never_takes_go():
    frames, _ = kickoff(
        [
            ("go", 0, DIAGONAL, stay(DIAGONAL)),
            ("back", 0, OFFSET, drive(OFFSET, BESIDE_BALL)),
            ("orange", 1, ORANGE_DIAGONAL, stay(ORANGE_DIAGONAL)),
        ]
    )
    assert _player(_one(frames), "go").role == "GO"


# Approaches


def _approach(path, *, dodge=None, against=_go_against):
    frames, release = against(path)
    if dodge is not None:
        at, torque = dodge
        frames = with_flip_at(frames, release + at, "blue", torque)
    return _player(_one(frames), "blue").approach


def test_a_cancelled_forward_dodge_is_a_speedflip():
    spin = drive(
        DIAGONAL,
        BESIDE_BALL,
        quaternion=lambda e: UPSIDE_DOWN if e >= 0.5 else LEVEL,
        rotation=STILL,
        angular_velocity=STILL,
    )
    assert _approach(spin, dodge=(0.5, Vec3(0.0, 2.24, 0.0))) == "SPEEDFLIP"


def test_a_flip_that_keeps_its_pitch_is_a_frontflip():
    spin = drive(
        DIAGONAL,
        BESIDE_BALL,
        quaternion=LEVEL,
        rotation=STILL,
        angular_velocity=Vec3(0.0, 5.5, 0.0),
    )
    assert _approach(spin, dodge=(0.5, Vec3(0.0, 2.24, 0.0))) == "STANDARD_FRONTFLIP"


def test_a_dodge_at_an_angle_is_diagonal():
    path = drive(DIAGONAL, BESIDE_BALL)
    assert _approach(path, dodge=(0.5, Vec3(1.8, 1.4, 0.0))) == "STANDARD_DIAGONAL"


def test_without_a_dodge_the_boost_decides():
    assert _approach(drive(DIAGONAL, BESIDE_BALL, boost_used=20.0)) == "STANDARD_BOOST"
    assert _approach(drive(DIAGONAL, BESIDE_BALL)) == "STANDARD"


def test_a_go_car_that_never_goes_is_a_stationary_fake():
    assert _approach(stay(DIAGONAL), against=_fake) == "FAKE_STATIONARY"


def test_a_go_car_driving_elsewhere_is_an_aggressive_fake():
    away = drive(DIAGONAL, Vec3(-3500.0, -1000.0, 17.0))
    assert _approach(away, against=_fake) == "FAKE_AGGRESSIVE"


def test_a_go_car_flipping_backward_is_a_halfflip_fake():
    path = drive(DIAGONAL, Vec3(-2500.0, -3200.0, 17.0))
    halfflip = (0.3, Vec3(0.0, -2.24, 0.0))
    assert _approach(path, dodge=halfflip, against=_fake) == "FAKE_HALFFLIP"


def test_a_go_car_beaten_to_the_ball_while_closing_is_no_fake():
    # Out of reach as orange plays the ball, but 0.8 s out and closing
    path = drive(DIAGONAL, BESIDE_BALL, arrive_s=2.8)
    assert _approach(path, against=_fake) == "STANDARD"
    # Still out of reach and further out than a second
    path = drive(DIAGONAL, BESIDE_BALL, arrive_s=3.5)
    assert _approach(path, against=_fake) == "FAKE_AGGRESSIVE"


def test_support_cars_hold_or_cheat_up():
    frames, _ = kickoff(
        [
            ("go", 0, DIAGONAL, drive(DIAGONAL, BESIDE_BALL)),
            ("holds", 0, OFFSET, stay(OFFSET)),
            (
                "cheats",
                0,
                Vec3(0.0, -4608.0, 17.0),
                drive(Vec3(0.0, -4608.0, 17.0), Vec3(0.0, -2500.0, 17.0)),
            ),
            ("orange", 1, ORANGE_DIAGONAL, stay(ORANGE_DIAGONAL)),
        ]
    )
    found = _one(frames)
    assert _player(found, "holds").approach == "SUPPORT_HOLD"
    assert _player(found, "cheats").approach == "SUPPORT_CHEAT"


# Overtime


def _goal(t, team):
    return GoalEvent(t=t, team=team)


def _two_kickoffs():
    first, release = _go_against(drive(DIAGONAL, BESIDE_BALL))
    second, _ = _go_against(drive(DIAGONAL, BESIDE_BALL))
    offset = first[-1].timestamp + 30.0
    later = [replace(f, timestamp=f.timestamp + offset) for f in second]
    return first + later, release + offset


def test_the_last_kickoff_at_a_level_score_with_no_goal_since_is_overtime():
    frames, second = _two_kickoffs()
    found = detect_kickoffs(frames, [_goal(1.0, "BLUE"), _goal(2.0, "ORANGE")])
    assert [k.phase for k in found] == ["INITIAL", "OT"]
    # The overtime goal comes after it
    found = detect_kickoffs(frames, [_goal(1.0, "BLUE"), _goal(second + 5.0, "ORANGE")])
    assert [k.phase for k in found] == ["INITIAL", "INITIAL"]


def test_a_kickoff_after_a_goal_or_at_an_uneven_score_is_not_overtime():
    frames, second = _two_kickoffs()
    after_goal = [_goal(second - 10.0, "BLUE"), _goal(second - 5.0, "ORANGE")]
    assert [k.phase for k in detect_kickoffs(frames, after_goal)] == ["INITIAL"] * 2
    uneven = [_goal(1.0, "BLUE")]
    assert [k.phase for k in detect_kickoffs(frames, uneven)] == ["INITIAL"] * 2


def test_without_goals_or_with_one_kickoff_nothing_is_overtime():
    frames, _ = _two_kickoffs()
    assert [k.phase for k in detect_kickoffs(frames, [])] == ["INITIAL"] * 2
    single, _ = _go_against(drive(DIAGONAL, BESIDE_BALL))
    assert _one(single, [_goal(-1.0, "BLUE"), _goal(-0.5, "ORANGE")]).phase == "INITIAL"
