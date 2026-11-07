"""Tests for per-moment mistake detection."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from rlcoach.analysis.mistakes import (
    CATEGORIES,
    CATEGORY,
    GOAL_CHANCES,
    INSTEAD,
    LEAD_IN,
    UnsupportedReplayError,
    build_context,
    check_supported_map,
    detect_caught_upfield,
    detect_clears_given_back,
    detect_double_commits,
    detect_low_boost_challenges,
    find_contacts,
    format_clock,
    game_clock,
    goal_timeline,
    link_goals_to_moments,
    live_mask,
    load_full_frames,
    own_depth,
    review_conceded_goals,
)
from rlcoach.events.types import ChallengeEvent, GoalEvent
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import ParserTouchEvent
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
KICKOFF_S = 0.2
SETTLE_S = 4.0


def _car(pid, team, x, y, vx=0.0, vy=0.0, z=17.0, vz=0.0, boost=50.0, **kwargs):
    return create_test_player(
        pid,
        team,
        position=Vec3(x, y, z),
        velocity=Vec3(vx, vy, vz),
        boost=boost,
        **kwargs,
    )


def _ball(x, y, z=93.15, vx=0.0, vy=0.0, vz=0.0):
    return create_test_ball(position=Vec3(x, y, z), velocity=Vec3(vx, vy, vz))


def _play(seconds, players, ball, start=None):
    """Build a kickoff, a settled spell of play, then the scenario.

    `players` and `ball` take scenario time, so a test only describes the moment
    it cares about. The returned scenario starts at `KICKOFF_S + SETTLE_S`.
    """
    frames = []
    t = 0.0
    while t < KICKOFF_S:
        frames.append(create_test_frame(t, players(0.0), create_test_ball()))
        t += DT
    settle_ball = ball(0.0)
    while t < KICKOFF_S + SETTLE_S:
        frames.append(create_test_frame(t, players(0.0), settle_ball))
        t += DT
    origin = t if start is None else start
    scenario = 0.0
    while scenario <= seconds:
        frames.append(
            create_test_frame(origin + scenario, players(scenario), ball(scenario))
        )
        scenario += DT
    return frames, origin


def _ctx(frames, player=ME, goals=(), challenges=(), team_size=2):
    return build_context(
        frames,
        player_id=player,
        goals=list(goals),
        challenges=list(challenges),
        names={ME: "me", MATE: "mate", OPP: "opp"},
        team_size=team_size,
    )


def test_own_depth_is_positive_towards_each_teams_goal():
    assert own_depth(5000.0, ORANGE) == 5000.0
    assert own_depth(5000.0, BLUE) == -5000.0
    assert own_depth(-5000.0, BLUE) == 5000.0


def test_find_contacts_sees_a_hit_beside_a_car():
    players = [_car(ME, ORANGE, 0.0, 1000.0, z=300.0)]
    frames = [
        create_test_frame(0.0, players, _ball(0.0, 900.0, 300.0, vy=500.0)),
        create_test_frame(DT, players, _ball(0.0, 917.0, 300.0, vy=500.0)),
        create_test_frame(2 * DT, players, _ball(0.0, 900.0, 300.0, vy=-1500.0)),
    ]
    contacts = find_contacts(frames)
    assert [c.player_id for c in contacts] == [ME]


def test_find_contacts_ignores_a_floor_bounce_under_a_car():
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
    assert find_contacts(frames) == []


def test_find_contacts_sees_a_ground_hit_with_the_car_already_past():
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
    assert [c.player_id for c in find_contacts(frames)] == [ME]


def test_find_contacts_credits_the_car_that_can_push_the_ball_that_way():
    """From a real shot: a defender stood nearest, on the far side of the ball."""
    players = [
        _car(MATE, ORANGE, -1042.0, 4715.0, z=140.0),
        _car(OPP, BLUE, -978.0, 4529.0, z=119.0),
    ]
    frames = [
        create_test_frame(
            0.0, players, _ball(-1030.0, 4638.0, 273.0, vx=1142.0, vy=-440.0)
        ),
        create_test_frame(
            DT,
            players,
            _ball(-975.0, 4647.0, 247.0, vx=1060.0, vy=1858.0, vz=1700.0),
        ),
    ]
    assert [c.player_id for c in find_contacts(frames)] == [OPP]


def test_find_contacts_trusts_the_replays_touch_event_over_the_push_fit():
    """The other car only looks right: the replay says who hit the ball."""
    players = [
        _car(MATE, ORANGE, -1042.0, 4715.0, z=140.0),
        _car(OPP, BLUE, -978.0, 4529.0, z=119.0),
    ]
    event = ParserTouchEvent(timestamp=DT, player_id=MATE, team=ORANGE, frame_index=1)
    frames = [
        create_test_frame(
            0.0, players, _ball(-1030.0, 4638.0, 273.0, vx=1142.0, vy=-440.0)
        ),
        replace(
            create_test_frame(
                DT,
                players,
                _ball(-975.0, 4647.0, 247.0, vx=1060.0, vy=1858.0, vz=1700.0),
            ),
            parser_touch_events=[event],
        ),
    ]
    assert [c.player_id for c in find_contacts(frames)] == [MATE]


def test_find_contacts_keeps_the_nearest_car_when_none_fits_the_push():
    """Car positions lag the ball, so a poor fit alone must not lose a touch."""
    players = [_car(ME, ORANGE, 0.0, 800.0, z=300.0)]
    frames = [
        create_test_frame(0.0, players, _ball(0.0, 900.0, 300.0, vy=500.0)),
        create_test_frame(DT, players, _ball(0.0, 917.0, 300.0, vy=-1500.0)),
    ]
    assert [c.player_id for c in find_contacts(frames)] == [ME]


def test_find_contacts_ignores_a_wall_bounce_beside_a_car():
    players = [_car(ME, ORANGE, 3800.0, 1000.0, z=300.0)]
    frames = [
        create_test_frame(0.0, players, _ball(3990.0, 900.0, 300.0, vx=1500.0)),
        create_test_frame(DT, players, _ball(3970.0, 910.0, 300.0, vx=-900.0, vy=20.0)),
    ]
    assert find_contacts(frames) == []


def test_find_contacts_ignores_gravity():
    players = [_car(ME, ORANGE, 0.0, 1000.0, z=300.0)]
    frames = [
        create_test_frame(i * DT, players, _ball(0.0, 950.0, 400.0, vz=-650.0 * i * DT))
        for i in range(5)
    ]
    assert find_contacts(frames) == []


def test_clock_counts_only_live_play():
    players = [_car(ME, ORANGE, 0.0, 3000.0)]
    frames = []
    t = 0.0
    for _ in range(10):
        frames.append(create_test_frame(t, players, create_test_ball()))
        t += DT
    for i in range(300):
        frames.append(create_test_frame(t, players, _ball(0.0, i * 10.0, vy=300.0)))
        t += DT
    goal_t = t
    frames.append(create_test_frame(t, players, _ball(0.0, 5200.0)))
    t += 10.0
    for _ in range(90):
        frames.append(create_test_frame(t, players, create_test_ball()))
        t += DT
    for i in range(150):
        frames.append(create_test_frame(t, players, _ball(0.0, i * 10.0, vy=300.0)))
        t += DT

    live = live_mask(frames, [goal_t])
    clock = game_clock(frames, live)

    assert clock[-1] == pytest.approx(285.0, abs=0.2)


def test_format_clock_shows_minutes_and_overtime():
    assert format_clock(192.4) == "3:12"
    assert format_clock(0.0) == "0:00"
    assert format_clock(-12.0) == "+0:12"


def _double_commit_scene(my_start=1400.0, my_speed=1500.0, opp_wins=True):
    """Mate and I both drive at a ball in our half, then someone hits it."""
    opp_y = 1960.0 if opp_wins else 1000.0

    def players(t):
        return [
            _car(ME, ORANGE, -my_start + my_speed * t, 2000.0, vx=my_speed),
            _car(MATE, ORANGE, 1200.0 - 1500.0 * t, 2000.0, vx=-1500.0),
            _car(OPP, BLUE, -60.0, opp_y),
        ]

    def ball(t):
        if t < 0.7:
            return _ball(0.0, 2000.0, 150.0)
        direction = 1.0 if opp_wins else -1.0
        travelled = 2500.0 * (t - 0.7) * direction
        return _ball(0.0, 2000.0 + travelled, 150.0, vy=2500.0 * direction)

    return _play(1.5, players, ball)


def test_double_commit_blames_the_later_arrival():
    frames, origin = _double_commit_scene()
    flags = detect_double_commits(_ctx(frames))
    assert [f.kind for f in flags] == ["double_commit"]
    assert flags[0].t == pytest.approx(origin, abs=0.3)
    assert "mate" in flags[0].what


def test_double_commit_does_not_blame_the_closer_player():
    frames, _ = _double_commit_scene()
    assert detect_double_commits(_ctx(frames, player=MATE)) == []


def test_double_commit_needs_the_opponent_to_profit():
    frames, _ = _double_commit_scene(opp_wins=False)
    assert detect_double_commits(_ctx(frames)) == []


def test_no_double_commit_when_i_drive_away():
    frames, _ = _double_commit_scene(my_speed=-1500.0)
    assert detect_double_commits(_ctx(frames)) == []


def _upfield_scene(mate_y=-1000.0, seconds=3.0, last_touch=BLUE, **my_kwargs):
    """Ball in my half while I sit in the opponent's half."""

    def players(t):
        return [
            _car(ME, ORANGE, 0.0, -2000.0, **my_kwargs),
            _car(MATE, ORANGE, 500.0, mate_y),
            _car(OPP, BLUE, 2000.0, 2600.0),
        ]

    hitter_x = 2000.0 if last_touch == BLUE else 500.0
    hitter_y = 2600.0 if last_touch == BLUE else mate_y

    def ball(t):
        if t < 0.1:
            return _ball(hitter_x, hitter_y + 130.0, 150.0, vy=0.0)
        return _ball(hitter_x + 400.0 * t, hitter_y + 130.0, 150.0, vx=400.0)

    return _play(seconds, players, ball)


def test_caught_upfield_flags_a_long_spell_with_nobody_back():
    frames, _ = _upfield_scene()
    flags = detect_caught_upfield(_ctx(frames))
    assert [f.kind for f in flags] == ["caught_upfield"]
    assert flags[0].duration >= 2.0


def test_not_caught_upfield_when_a_teammate_is_back():
    frames, _ = _upfield_scene(mate_y=4500.0)
    assert detect_caught_upfield(_ctx(frames)) == []


def test_not_caught_upfield_when_my_team_has_the_ball():
    frames, _ = _upfield_scene(mate_y=2000.0, last_touch=ORANGE)
    assert detect_caught_upfield(_ctx(frames)) == []


def test_not_caught_upfield_while_demolished():
    frames, _ = _upfield_scene(is_demolished=True)
    assert detect_caught_upfield(_ctx(frames)) == []


def test_not_caught_upfield_while_driving_home():
    frames, _ = _upfield_scene(vy=2000.0)
    assert detect_caught_upfield(_ctx(frames)) == []


def test_frame_gap_breaks_an_upfield_spell():
    first, origin = _upfield_scene(seconds=1.5)
    second = [
        create_test_frame(f.timestamp + 12.0, f.players, f.ball)
        for f in first
        if f.timestamp >= origin
    ]
    assert detect_caught_upfield(_ctx(first + second)) == []


def _challenge(winner, my_boost, ball_vy=1500.0):
    """A 50/50 at halfway. The ball leaves at `ball_vy`, towards my goal by default."""

    def players(t):
        return [
            _car(ME, ORANGE, 0.0, 0.0, boost=my_boost),
            _car(OPP, BLUE, 200.0, 0.0),
        ]

    def ball(t):
        if t < 0.5:
            return _ball(500.0, 0.0, 300.0)
        return _ball(500.0, ball_vy * (t - 0.5), 300.0, vy=ball_vy)

    frames, origin = _play(1.2, players, ball)
    event = ChallengeEvent(
        t=origin + 0.5,
        first_player=ME,
        second_player=OPP,
        first_team="ORANGE",
        second_team="BLUE",
        outcome="LOSS" if winner == "BLUE" else "WIN",
        winner_team=winner,
        location=Vec3(0.0, 0.0, 300.0),
        depth_m=0.0,
        duration=0.2,
        risk_first=0.5,
        risk_second=0.5,
    )
    return frames, event


def test_lost_challenge_on_low_boost_is_flagged():
    frames, event = _challenge("BLUE", 10.0)
    flags = detect_low_boost_challenges(_ctx(frames, challenges=[event]))
    assert [f.kind for f in flags] == ["low_boost_challenge"]


def test_challenge_that_sends_the_ball_upfield_was_not_lost():
    """From a real game: the event said lost, but the ball flew at their goal."""
    frames, event = _challenge("BLUE", 10.0, ball_vy=-2400.0)
    assert detect_low_boost_challenges(_ctx(frames, challenges=[event])) == []


def test_lost_kickoff_is_not_a_low_boost_challenge():
    """Boost reads 0 on kickoff frames, which must not look like being empty."""
    frames, event = _challenge("BLUE", 0.0)
    event = replace(event, t=frames[12].timestamp)
    assert detect_low_boost_challenges(_ctx(frames, challenges=[event])) == []


def test_won_challenge_on_low_boost_is_not_flagged():
    frames, event = _challenge("ORANGE", 10.0)
    assert detect_low_boost_challenges(_ctx(frames, challenges=[event])) == []


def test_lost_challenge_with_boost_is_not_flagged():
    frames, event = _challenge("BLUE", 60.0)
    assert detect_low_boost_challenges(_ctx(frames, challenges=[event])) == []


def _clear_scene(returned=True, reply_y=2300.0):
    """I hit the ball upfield and Blue either returns it at `reply_y` or doesn't."""
    speed = 3000.0 - reply_y

    def players(t):
        return [
            _car(ME, ORANGE, 0.0, 3100.0),
            _car(OPP, BLUE, 0.0, reply_y - 100.0),
        ]

    def ball(t):
        if t < 0.5:
            return _ball(0.0, 3000.0, 150.0, vy=-100.0)
        if t < 1.5 or not returned:
            return _ball(0.0, 3000.0 - speed * (t - 0.5), 150.0, vy=-speed)
        return _ball(0.0, reply_y + 2800.0 * (t - 1.5), 150.0, vy=2800.0)

    return _play(3.0, players, ball)


def test_clear_returned_to_my_end_is_flagged():
    frames, _ = _clear_scene()
    flags, summary = detect_clears_given_back(_ctx(frames))
    assert [f.kind for f in flags] == ["clear_given_back"]
    assert summary == {"clears": 1, "given_back": 1}


def test_clear_collected_past_my_third_is_a_job_done():
    frames, _ = _clear_scene(reply_y=1300.0)
    flags, summary = detect_clears_given_back(_ctx(frames))
    assert flags == []
    assert summary == {"clears": 1, "given_back": 0}


def test_a_scrum_on_the_wall_is_not_a_clear():
    """Touches a tenth of a second apart are a 50/50, not a clear given back."""

    def players(t):
        return [
            _car(ME, ORANGE, 0.0, 3100.0),
            _car(OPP, BLUE, 0.0, 2800.0),
        ]

    def ball(t):
        if t < 0.5:
            return _ball(0.0, 3000.0, 150.0, vy=-100.0)
        if t < 0.6:
            return _ball(0.0, 3000.0 - 1700.0 * (t - 0.5), 150.0, vy=-1700.0)
        return _ball(0.0, 2830.0 + 1700.0 * (t - 0.6), 150.0, vy=1700.0)

    frames, _ = _play(2.0, players, ball)
    flags, summary = detect_clears_given_back(_ctx(frames))
    assert flags == []
    assert summary == {"clears": 0, "given_back": 0}


def test_clear_that_gets_out_is_not_flagged():
    frames, _ = _clear_scene(returned=False)
    flags, summary = detect_clears_given_back(_ctx(frames))
    assert flags == []
    assert summary == {"clears": 1, "given_back": 0}


def _goal_scene(me, mate, ball_z=440.0):
    """Blue hits a slow lob at my goal from just inside my half.

    `me` and `mate` are functions of scenario time. The shot leaves at 0.5 s and
    crosses the line just under 3.5 s later.
    """

    def players(t):
        return [me(t), mate(t), _car(OPP, BLUE, 0.0, 1500.0, z=300.0)]

    def ball(t):
        if t < 0.5:
            return _ball(0.0, 1400.0, ball_z, vy=-50.0)
        return _ball(0.0, 1400.0 + 1070.0 * (t - 0.5), ball_z, vy=1070.0)

    frames, origin = _play(4.1, players, ball)
    goal = GoalEvent(t=origin + 4.05, scorer=OPP, team="BLUE")
    return frames, goal


def test_goal_is_not_on_me_with_a_teammate_back():
    frames, goal = _goal_scene(
        me=lambda t: _car(ME, ORANGE, 0.0, -3000.0),
        mate=lambda t: _car(MATE, ORANGE, 3000.0, 4500.0),
    )
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert len(reviews) == 1
    assert reviews[0].on_you is False
    assert reviews[0].summary == "No mistake found."
    assert flags == []


def test_grounded_defender_under_the_ball_made_no_save_attempt():
    frames, goal = _goal_scene(
        me=lambda t: _car(ME, ORANGE, 100.0, 5150.0, z=40.0),
        mate=lambda t: _car(MATE, ORANGE, 3000.0, -3000.0),
    )
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is True
    assert [f.kind for f in flags] == ["no_save_attempt"]


def test_teammate_who_never_jumped_is_named_in_my_review():
    frames, goal = _goal_scene(
        me=lambda t: _car(ME, ORANGE, 0.0, -3000.0),
        mate=lambda t: _car(MATE, ORANGE, 100.0, 5150.0, z=40.0),
    )
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is False
    assert flags == []
    assert any("mate" in line and "never jumped" in line for line in reviews[0].lines)
    assert reviews[0].summary == "A teammate had the chance to stop this."


def test_the_distance_line_gives_my_closest_distance_not_my_distance_at_the_goal():
    """From a real goal: the report said 6 m when the car was 23 m from the net."""

    def players(t):
        return [
            _car(ME, ORANGE, 0.0, 1000.0),
            _car(MATE, ORANGE, 3000.0, -3000.0),
            _car(OPP, BLUE, 3000.0, -2000.0),
        ]

    def ball(t):
        return _ball(600.0, -200.0 + 2000.0 * t, vy=2000.0)

    frames, origin = _play(2.7, players, ball)
    goal = GoalEvent(t=origin + 2.65, scorer=OPP, team="BLUE")
    reviews, _ = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].lines[0] == (
        "You got no closer than 6 m to the ball in the last 2 s (50 boost)"
    )


def _own_touch_scene(toucher, opp_follows=False):
    """A cross runs across my goal, then `toucher` hits it towards the net.

    With `opp_follows`, an opponent touches the ball again on its way in.
    """
    other = MATE if toucher == ME else ME
    opp_x, opp_y = (-310.0, 4650.0) if opp_follows else (3000.0, -2000.0)

    def players(t):
        return [
            _car(toucher, ORANGE, -400.0, 4330.0, z=100.0),
            _car(other, ORANGE, 3000.0, -3000.0),
            _car(OPP, BLUE, opp_x, opp_y, z=100.0),
        ]

    def ball(t):
        if t < 0.5:
            return _ball(
                -1350.0 + 1900.0 * t, 4530.0 - 100.0 * t, 110.0, vx=1900.0, vy=-100.0
            )
        if opp_follows and t >= 0.8:
            moved = t - 0.8
            return _ball(
                -310.0 - 100.0 * moved,
                4750.0 + 1200.0 * moved,
                110.0,
                vx=-100.0,
                vy=1200.0,
            )
        moved = t - 0.5
        return _ball(
            -400.0 + 300.0 * moved,
            4480.0 + 900.0 * moved,
            110.0,
            vx=300.0,
            vy=900.0,
        )

    frames, origin = _play(1.3, players, ball)
    goal = GoalEvent(t=origin + 1.25, scorer=OPP, team="BLUE")
    return frames, goal


def test_my_touch_that_turns_a_cross_into_my_net_is_on_me():
    """From a real overtime goal: the cross was going past until it was hit."""
    frames, goal = _own_touch_scene(ME)
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is True
    assert reviews[0].summary == "Your touch turned it in."
    assert [f.kind for f in flags] == ["own_touch_in"]


def test_a_teammates_touch_that_turns_it_in_is_named_but_not_on_me():
    frames, goal = _own_touch_scene(MATE)
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is False
    assert flags == []
    assert any("mate" in line and "turned" in line for line in reviews[0].lines)


def test_an_opponent_touch_after_mine_means_i_did_not_turn_it_in():
    frames, goal = _own_touch_scene(ME, opp_follows=True)
    _, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert "own_touch_in" not in [f.kind for f in flags]


def test_turning_a_ball_on_target_far_from_my_net_is_not_an_own_touch():
    """From a real goal: the touch came in the other half, with 2 s left to save."""

    def players(t):
        return [
            _car(ME, ORANGE, -2330.0, -1180.0, z=124.0),
            _car(MATE, ORANGE, 3000.0, -3000.0),
            _car(OPP, BLUE, 3000.0, -2000.0),
        ]

    def ball(t):
        if t < 0.5:
            return _ball(-2278.0, -2000.0 + 1800.0 * t, 139.0, vy=1800.0)
        moved = t - 0.5
        return _ball(
            -2270.0 + 760.0 * moved,
            -1100.0 + 2950.0 * moved,
            139.0,
            vx=760.0,
            vy=2950.0,
        )

    frames, origin = _play(2.7, players, ball)
    goal = GoalEvent(t=origin + 2.6, scorer=OPP, team="BLUE")
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert "own_touch_in" not in [f.kind for f in flags]
    assert not any("turned" in line for line in reviews[0].lines)


def _behind_line_scene(car=ME, end_y=5632.0, shot_s=0.5, shot_speed=1000.0):
    """A ball rolls in at one post while `car` backs into the far corner."""
    other = MATE if car == ME else ME
    flight_s = 2420.0 / shot_speed

    def players(t):
        return [
            _car(car, ORANGE, -100.0 - 240.0 * t, min(4000.0 + 650.0 * t, end_y)),
            _car(other, ORANGE, 3000.0, -3000.0),
            _car(OPP, BLUE, -600.0, 2600.0),
        ]

    def ball(t):
        if t < shot_s:
            return _ball(-554.0, 2650.0, vy=60.0)
        moved = t - shot_s
        return _ball(
            -450.0 + 0.4 * shot_speed * moved,
            2700.0 + shot_speed * moved,
            vx=0.4 * shot_speed,
            vy=shot_speed,
        )

    seconds = shot_s + flight_s + 0.1
    frames, origin = _play(seconds, players, ball)
    goal = GoalEvent(t=origin + seconds - 0.05, scorer=OPP, team="BLUE")
    return frames, goal


def test_being_behind_my_line_with_time_to_react_is_on_me():
    """From a real goal: reversing into the net as a slow ball rolled in."""
    frames, goal = _behind_line_scene()
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is True
    assert reviews[0].summary == "You had the chance to stop this."
    assert (
        reviews[0].lines[0].startswith("You were behind your goal line as it went in")
    )
    assert [f.kind for f in flags] == ["behind_line"]


def test_a_teammate_behind_the_line_is_named_but_not_on_me():
    frames, goal = _behind_line_scene(car=MATE)
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is False
    assert reviews[0].summary == "A teammate had the chance to stop this."
    assert flags == []


def test_a_keeper_on_the_line_is_not_behind_it():
    frames, goal = _behind_line_scene(end_y=5180.0)
    _, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert "behind_line" not in [f.kind for f in flags]


def test_being_behind_my_line_with_no_time_to_react_is_not_on_me():
    frames, goal = _behind_line_scene(shot_s=2.0, shot_speed=2700.0)
    _, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert "behind_line" not in [f.kind for f in flags]


def test_touching_a_ball_already_going_in_is_not_an_own_touch():
    def players(t):
        return [
            _car(ME, ORANGE, -400.0, 4330.0, z=100.0),
            _car(MATE, ORANGE, 3000.0, -3000.0),
            _car(OPP, BLUE, 3000.0, -2000.0),
        ]

    def ball(t):
        if t < 0.5:
            return _ball(-400.0, 4000.0 + 900.0 * t, 110.0, vy=900.0)
        return _ball(-400.0, 4450.0 + 500.0 * (t - 0.5), 110.0, vy=500.0)

    frames, origin = _play(1.9, players, ball)
    goal = GoalEvent(t=origin + 1.85, scorer=OPP, team="BLUE")
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert flags == []
    assert any("got a touch" in line for line in reviews[0].lines)


def test_defender_who_jumped_and_missed_is_flagged_for_the_miss():
    def jumping(t):
        z = 40.0 if t < 3.0 else 40.0 + 500.0 * (t - 3.0)
        return _car(ME, ORANGE, 100.0, 5150.0, z=z, vz=500.0)

    frames, goal = _goal_scene(
        me=jumping,
        mate=lambda t: _car(MATE, ORANGE, 3000.0, -3000.0),
    )
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is True
    assert [f.kind for f in flags] == ["missed_save"]


def test_slow_ball_i_fail_to_clear_is_on_me():
    """From a real goal: a 24 km/h ball rolled in past a lone keeper."""

    def players(t):
        z = 17.0 if t < 1.2 else 125.0
        return [
            _car(ME, ORANGE, 240.0, 5000.0, z=z),
            _car(MATE, ORANGE, 300.0, 3900.0),
            _car(OPP, BLUE, 1500.0, 3000.0),
        ]

    frames, origin = _play(
        1.8, players, lambda t: _ball(0.0, 4000.0 + 660.0 * t, 250.0, vy=660.0)
    )
    goal = GoalEvent(t=origin + 1.75, scorer=OPP, team="BLUE")
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is True
    assert [f.kind for f in flags] == ["missed_clear"]
    assert "24 km/h" in flags[0].what


def test_a_hard_shot_with_no_time_to_react_is_not_on_me():
    def players(t):
        return [
            _car(ME, ORANGE, 350.0, 5000.0),
            _car(MATE, ORANGE, 3000.0, -3000.0),
            _car(OPP, BLUE, 0.0, 2800.0, z=300.0),
        ]

    def ball(t):
        if t < 0.2:
            return _ball(0.0, 2900.0, 150.0, vy=-50.0)
        return _ball(0.0, 2900.0 + 2800.0 * (t - 0.2), 150.0, vy=2800.0)

    frames, origin = _play(1.1, players, ball)
    goal = GoalEvent(t=origin + 1.05, scorer=OPP, team="BLUE")
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is False
    assert flags == []
    assert any("beaten" in line for line in reviews[0].lines)


def test_sitting_in_goal_while_a_shot_goes_past_me_is_no_save_attempt():
    """From a real goal: 1.2 s of warning, and it went in 5.5 m to one side."""

    def players(t):
        return [
            _car(ME, ORANGE, 0.0, 5150.0),
            _car(MATE, ORANGE, 3000.0, -3000.0),
            _car(OPP, BLUE, 2650.0, 3250.0, z=300.0),
        ]

    def ball(t):
        if t < 0.2:
            return _ball(2550.0, 3340.0, 440.0, vx=20.0, vy=-50.0)
        vx, vy = -1680.0, 1500.0
        moved = t - 0.2
        return _ball(2550.0 + vx * moved, 3340.0 + vy * moved, 440.0, vx=vx, vy=vy)

    frames, origin = _play(1.4, players, ball)
    goal = GoalEvent(t=origin + 1.35, scorer=OPP, team="BLUE")
    _, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert [f.kind for f in flags] == ["no_save_attempt"]


def test_leaving_the_net_as_last_back_is_on_me_when_the_ball_gets_past():
    """From a real goal: all three went out at the ball and it beat them all."""

    def players(t):
        return [
            _car(ME, ORANGE, 0.0, 4820.0 - 1800.0 * t, vy=-1800.0, z=170.0),
            _car(MATE, ORANGE, 900.0, 4000.0),
            _car(OPP, BLUE, 700.0, 3900.0, z=300.0),
        ]

    def ball(t):
        if t < 0.2:
            return _ball(700.0, 4000.0, 400.0, vy=-50.0)
        return _ball(
            700.0 - 450.0 * (t - 0.2),
            4000.0 + 900.0 * (t - 0.2),
            400.0,
            vx=-450.0,
            vy=900.0,
        )

    frames, origin = _play(1.5, players, ball)
    goal = GoalEvent(t=origin + 1.45, scorer=OPP, team="BLUE")
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is True
    assert [f.kind for f in flags] == ["last_back_overcommit"]


def test_going_wide_for_boost_is_not_leaving_the_net_for_the_ball():
    """From a pro game: the last player back was collecting corner boost."""

    def players(t):
        return [
            _car(ME, ORANGE, -3100.0, 4220.0, vx=-700.0, vy=-950.0),
            _car(MATE, ORANGE, 3200.0, 3780.0),
            _car(OPP, BLUE, -600.0, 3050.0, z=300.0),
        ]

    def ball(t):
        if t < 0.2:
            return _ball(-570.0, 3140.0, 220.0, vy=-50.0)
        return _ball(-570.0, 3140.0 + 2660.0 * (t - 0.2), 220.0, vy=2660.0)

    frames, origin = _play(1.0, players, ball)
    goal = GoalEvent(t=origin + 0.95, scorer=OPP, team="BLUE")
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is False
    assert flags == []


def test_a_goal_straight_from_kickoff_is_not_a_last_back_mistake():
    players = [
        _car(ME, ORANGE, 0.0, 4800.0, vy=-1400.0),
        _car(MATE, ORANGE, 900.0, 4400.0),
        _car(OPP, BLUE, 2000.0, 3900.0, z=300.0),
    ]
    frames = [
        create_test_frame(i * DT, players, create_test_ball()) for i in range(3)
    ] + [
        create_test_frame(
            (i + 3) * DT, players, _ball(0.0, 100.0 + 170.0 * i, 400.0, vy=5000.0)
        )
        for i in range(32)
    ]
    goal = GoalEvent(t=frames[-1].timestamp, scorer=OPP, team="BLUE")
    _, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert [f.kind for f in flags if f.kind.startswith("last_back")] == []


def test_a_teammates_late_deflection_leaves_no_time_to_react():
    def players(t):
        return [
            _car(ME, ORANGE, 100.0, 5150.0),
            _car(MATE, ORANGE, 0.0, 4700.0, z=400.0),
            _car(OPP, BLUE, 0.0, -2000.0),
        ]

    def ball(t):
        if t < 0.5:
            return _ball(0.0, 4600.0, 440.0, vy=300.0)
        return _ball(0.0, 4600.0 + 1400.0 * (t - 0.5), 440.0, vy=1400.0)

    frames, origin = _play(0.9, players, ball)
    goal = GoalEvent(t=origin + 0.87, scorer=OPP, team="BLUE")
    _, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert flags == []


def test_last_back_in_their_half_is_on_me_even_with_the_ball_further_up():
    """From a real goal: everyone was past halfway when a long shot came."""

    def players(t):
        return [
            _car(ME, ORANGE, 2760.0, -850.0),
            _car(MATE, ORANGE, 3850.0, -3250.0),
            _car(OPP, BLUE, 2400.0, -1700.0, z=150.0),
        ]

    def ball(t):
        if t < 0.2:
            return _ball(2350.0, -1620.0, 230.0, vy=-50.0)
        return _ball(2350.0, -1620.0 + 2800.0 * (t - 0.2), 230.0, vy=2800.0)

    frames, origin = _play(2.7, players, ball)
    goal = GoalEvent(t=origin + 2.65, scorer=OPP, team="BLUE")
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is True
    assert [f.kind for f in flags] == ["last_back_upfield"]


def test_last_back_and_upfield_of_the_ball_is_on_me():
    frames, goal = _goal_scene(
        me=lambda t: _car(ME, ORANGE, 0.0, 400.0),
        mate=lambda t: _car(MATE, ORANGE, 3000.0, -3000.0),
    )
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert reviews[0].on_you is True
    assert [f.kind for f in flags] == ["last_back_upfield"]


def test_goal_review_ignores_the_ball_left_in_the_net_by_the_last_goal():
    frames, goal = _goal_scene(
        me=lambda t: _car(ME, ORANGE, 0.0, 4500.0),
        mate=lambda t: _car(MATE, ORANGE, 3000.0, -3000.0),
    )
    still_in_net = [
        create_test_frame(-1.0 + i * DT, frames[0].players, _ball(0.0, 5212.0, 94.0))
        for i in range(20)
    ]
    earlier = GoalEvent(t=-1.0, scorer=OPP, team="BLUE")
    reviews, _ = review_conceded_goals(
        _ctx(still_in_net + frames, goals=[earlier, goal])
    )
    assert reviews[1].on_you is False


def test_a_deflection_at_the_line_is_not_a_missed_save():
    def players(t):
        return [
            _car(ME, ORANGE, 100.0, 5150.0, z=40.0),
            _car(MATE, ORANGE, 3000.0, -3000.0),
            _car(OPP, BLUE, 0.0, 4900.0, z=300.0),
        ]

    def ball(t):
        if t < 0.5:
            return _ball(0.0, 4800.0, 440.0, vy=-50.0)
        return _ball(0.0, 4800.0 + 2000.0 * (t - 0.5), 440.0, vy=2000.0)

    frames, origin = _play(0.8, players, ball)
    goal = GoalEvent(t=origin + 0.75, scorer=OPP, team="BLUE")
    _, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert flags == []


def test_my_own_teams_goal_is_not_reviewed():
    frames, goal = _goal_scene(
        me=lambda t: _car(ME, ORANGE, 0.0, 400.0),
        mate=lambda t: _car(MATE, ORANGE, 3000.0, -3000.0),
    )
    scored = GoalEvent(t=goal.t, scorer=ME, team="ORANGE")
    assert review_conceded_goals(_ctx(frames, goals=[scored])) == ([], [])


@pytest.mark.parametrize(
    "map_name", ["HoopsStadium_P", "ShatterShot_P", "Labs_Octagon_02_P"]
)
def test_non_standard_arenas_are_refused(map_name):
    with pytest.raises(UnsupportedReplayError):
        check_supported_map(map_name)


def test_standard_arena_is_accepted():
    check_supported_map("UtopiaStadium_Dusk_P")


@pytest.mark.skipif(
    not Path("Replay_files/0925.replay").exists(), reason="replay fixture missing"
)
def test_load_full_frames_keeps_the_end_of_the_game():
    """The default timeline cuts replays at NumFrames/30 seconds."""
    _, frames = load_full_frames(Path("Replay_files/0925.replay"))
    assert frames[-1].timestamp == pytest.approx(323.09, abs=0.5)


def test_every_mistake_kind_has_a_category():
    assert set(CATEGORY) == set(INSTEAD)
    assert set(CATEGORY.values()) == set(CATEGORIES)


def test_a_goal_on_me_is_flagged_as_costing_a_goal():
    frames, goal = _goal_scene(
        me=lambda t: _car(ME, ORANGE, 0.0, 400.0),
        mate=lambda t: _car(MATE, ORANGE, 3000.0, -3000.0),
    )
    reviews, flags = review_conceded_goals(_ctx(frames, goals=[goal]))
    assert flags[0].cost_goal is True
    assert flags[0].category == "last_back"
    assert reviews[0].seconds_left == pytest.approx(flags[0].seconds_left, abs=5.0)


def test_moments_away_from_goals_do_not_cost_one():
    frames, _ = _upfield_scene()
    flags = detect_caught_upfield(_ctx(frames))
    assert flags[0].cost_goal is False
    assert flags[0].category == "rotation"
    assert 0 < flags[0].seconds_left <= 300


def _clear_into_goal_scene(mate_touch=False):
    """My clear goes straight back to Blue, who scores past nobody.

    I clear at 0.5 s and leave for the far side, Blue returns it at 2.5 s, and it
    crosses my line just before 3.7 s. With `mate_touch`, my teammate gets a
    touch on it at 3.0 s that doesn't stop it.
    """

    def players(t):
        me = _car(ME, ORANGE, 0.0 if t < 1.0 else -3000.0, 3100.0)
        mate = _car(MATE, ORANGE, -200.0 if mate_touch else 3000.0, 3150.0)
        return [me, mate, _car(OPP, BLUE, 0.0, 1700.0)]

    def ball(t):
        if t < 0.5:
            return _ball(0.0, 3000.0, 150.0, vy=-100.0)
        if t < 2.5:
            return _ball(0.0, 3000.0 - 600.0 * (t - 0.5), 150.0, vy=-600.0)
        if t < 3.0 or not mate_touch:
            return _ball(0.0, 1800.0 + 2800.0 * (t - 2.5), 150.0, vy=2800.0)
        after = t - 3.0
        return _ball(300.0 * after, 3200.0 + 2800.0 * after, 150.0, 300.0, 2800.0)

    frames, origin = _play(4.2, players, ball)
    goal = GoalEvent(t=origin + 3.75, scorer=OPP, team="BLUE")
    ctx = _ctx(frames, goals=[goal])
    reviews, _ = review_conceded_goals(ctx)
    clears, _ = detect_clears_given_back(ctx)
    return ctx, reviews, clears


def test_a_clear_that_goes_straight_back_in_costs_the_goal():
    ctx, reviews, clears = _clear_into_goal_scene()
    assert reviews[0].summary == "No mistake found."
    assert clears[0].outcome == "You conceded 3 s later."

    reviews, flags = link_goals_to_moments(ctx, reviews, clears)
    assert flags[0].cost_goal is True
    assert reviews[0].on_you is True
    assert reviews[0].summary == "Your clear went straight back to them 3 s before."


def test_a_clear_my_team_won_back_before_the_goal_costs_nothing():
    ctx, reviews, clears = _clear_into_goal_scene(mate_touch=True)
    assert clears[0].outcome == "The ball reached your end."

    reviews, flags = link_goals_to_moments(ctx, reviews, clears)
    assert flags[0].cost_goal is False
    assert reviews[0].on_you is False


def test_a_goal_already_on_me_keeps_its_own_verdict():
    ctx, reviews, clears = _clear_into_goal_scene()
    blamed = [replace(reviews[0], on_you=True, summary="You were the last one back.")]

    reviews, flags = link_goals_to_moments(ctx, blamed, clears)
    assert flags[0].cost_goal is False
    assert reviews[0].summary == "You were the last one back."


def test_every_moment_before_a_goal_can_lead_to_one():
    """Goal reviews flag their own kinds, so every other kind needs a lead-in."""
    from_goal_reviews = {*GOAL_CHANCES, "last_back_upfield", "last_back_overcommit"}
    assert set(LEAD_IN) == set(CATEGORY) - from_goal_reviews


def _scored(*teams):
    """A quiet game with goals by the given teams, one second apart."""

    def players(t):
        return [_car(ME, ORANGE, 0.0, 3000.0), _car(OPP, BLUE, 0.0, -3000.0)]

    frames, origin = _play(len(teams) + 1.0, players, lambda t: _ball(0.0, 0.0))
    goals = [
        GoalEvent(
            t=origin + i + 0.5,
            scorer=ME if team == "ORANGE" else OPP,
            team=team,
        )
        for i, team in enumerate(teams)
    ]
    return _ctx(frames, goals=goals)


def test_goal_timeline_marks_the_winner_and_equalizers():
    # Down 0-1, level at 1-1, behind 1-2, level 2-2, then win 3-2
    ctx = _scored("BLUE", "ORANGE", "BLUE", "ORANGE", "ORANGE")
    timeline = goal_timeline(ctx)

    assert [g.score for g in timeline] == ["0-0", "0-1", "1-1", "1-2", "2-2"]
    assert [g.ours for g in timeline] == [False, True, False, True, True]
    assert [g.equalizer for g in timeline] == [False, True, False, True, False]
    assert [g.winner for g in timeline] == [False, False, False, False, True]
    assert all(g.by_you == g.ours for g in timeline)
    assert timeline[1].scorer == "You"


def test_goal_timeline_has_no_winner_in_a_loss():
    ctx = _scored("ORANGE", "BLUE", "BLUE")
    assert not any(g.winner for g in goal_timeline(ctx))


def test_the_first_goal_of_a_one_nil_win_is_the_winner():
    ctx = _scored("ORANGE")
    assert goal_timeline(ctx)[0].winner is True
