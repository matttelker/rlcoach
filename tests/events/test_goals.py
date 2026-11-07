"""Tests for finding goals."""

from __future__ import annotations

from rlcoach.events.goals import detect_goals
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import GoalHeader, Header, PlayerInfo
from tests.fixtures.builders import (
    create_test_ball,
    create_test_frame,
    create_test_player,
)

PLAYERS = [
    PlayerInfo(name="Me", platform_id="Epic|me", team=0),
    PlayerInfo(name="Mate", platform_id="Epic|mate", team=0),
    PlayerInfo(name="Them", platform_id="Steam|1", team=1),
]
FAR = Vec3(3000.0, -3000.0, 17.0)
BALL = create_test_ball(position=Vec3(0.0, 0.0, 93.15))


def _frames(count, near=None, step=1.0):
    """`near` maps a frame index to the players beside the ball then."""
    near = near or {}
    return [
        create_test_frame(
            index * step,
            [
                create_test_player(
                    player_id,
                    team,
                    position=(
                        Vec3(0.0, 100.0, 17.0)
                        if player_id in near.get(index, ())
                        else FAR
                    ),
                )
                for player_id, team in (
                    ("epic:me", 0),
                    ("epic:mate", 0),
                    ("steam:1", 1),
                )
            ],
            ball=BALL,
        )
        for index in range(count)
    ]


def _goal(frame, name, team):
    return GoalHeader(frame=frame, player_name=name, player_team=team)


def test_each_header_goal_is_timed_by_its_frame():
    header = Header(players=PLAYERS, goals=[_goal(2, "Me", 0), _goal(5, "Them", 1)])
    goals = detect_goals(_frames(8, step=0.5), header)
    assert [(g.t, g.team, g.scorer) for g in goals] == [
        (1.0, "BLUE", "epic:me"),
        (2.5, "ORANGE", "steam:1"),
    ]


def test_a_renamed_scorer_goes_by_their_teams_first_player():
    header = Header(players=PLAYERS, goals=[_goal(1, "Renamed", 0)])
    assert detect_goals(_frames(3), header)[0].scorer == "epic:me"


def test_the_assist_is_the_teammate_last_near_the_ball():
    header = Header(players=PLAYERS, goals=[_goal(9, "Me", 0)])
    # The mate was near at 4 s, the opponent later, the scorer last
    frames = _frames(10, near={4: {"epic:mate"}, 7: {"steam:1"}, 9: {"epic:me"}})
    assert detect_goals(frames, header)[0].assist == "epic:mate"


def test_a_teammate_near_the_ball_more_than_6_s_before_gets_no_assist():
    header = Header(players=PLAYERS, goals=[_goal(9, "Me", 0)])
    frames = _frames(10, near={2: {"epic:mate"}})
    assert detect_goals(frames, header)[0].assist is None


def test_a_goal_with_no_frame_is_left_out_and_one_past_the_end_goes_last():
    header = Header(
        players=PLAYERS,
        goals=[_goal(None, "Me", 0), _goal(1, "Me", 0), _goal(50, "Them", 1)],
    )
    goals = detect_goals(_frames(4, near={0: {"epic:mate"}}), header)
    assert [(g.t, g.scorer, g.assist) for g in goals] == [
        (1.0, "epic:me", "epic:mate"),
        (3.0, "steam:1", None),
    ]


def test_a_header_without_goals_has_none():
    assert detect_goals(_frames(3), Header(players=PLAYERS)) == []
