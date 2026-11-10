"""Tests for situations: each choice a car faced, and whether a goal followed."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from rlcoach.analysis.mistakes import CATEGORIES, review_player
from rlcoach.analysis.situations import (
    KINDS,
    WORDING,
    game_situations,
    situations_for,
)
from rlcoach.events.touches import detect_touches
from rlcoach.events.types import GoalEvent
from rlcoach.game import Game, read_game
from rlcoach.identity import build_player_identities
from rlcoach.parser.types import Header, TouchCount
from tests.analysis import test_mistakes as tm
from tests.fixtures import real_replays

ME, MATE, OPP = tm.ME, tm.MATE, tm.OPP
ORANGE, BLUE = tm.ORANGE, tm.BLUE


def _kinds(ctx, kind):
    return [s for s in situations_for(ctx) if s.kind == kind]


def test_every_kind_belongs_to_a_category_and_is_worded():
    assert set(KINDS.values()) <= set(CATEGORIES)
    assert set(WORDING) == set(KINDS)


# Clears


def test_a_clear_given_straight_back_is_the_bad_choice():
    frames, origin = tm._clear_scene()
    [clear] = _kinds(tm._ctx(frames), "clear")
    assert (clear.player_id, clear.bad, clear.conceded) == (ME, True, False)
    assert clear.t == pytest.approx(origin + 0.5, abs=0.1)
    # The ball was 3000 uu up my end, inside my third
    assert clear.zone == "own_third"
    assert 0 < clear.seconds_left <= tm.GAME_LENGTH_S


def test_a_clear_that_gets_out_of_your_third_is_the_good_choice():
    frames, _ = tm._clear_scene(reply_y=1300.0)
    assert [c.bad for c in _kinds(tm._ctx(frames), "clear")] == [False]


def test_the_clears_match_the_reviews_count():
    for scene in (tm._clear_scene(), tm._clear_scene(returned=False)):
        ctx = tm._ctx(scene[0])
        _, summary = tm.detect_clears_given_back(ctx)
        clears = _kinds(ctx, "clear")
        assert len(clears) == summary["clears"]
        assert sum(c.bad for c in clears) == summary["given_back"]


# A goal after


def test_a_goal_against_with_no_touch_by_your_team_was_conceded():
    ctx, _, _ = tm._clear_into_goal_scene()
    [clear] = _kinds(ctx, "clear")
    assert (clear.bad, clear.conceded) == (True, True)


def test_a_goal_after_your_team_touched_the_ball_was_not_conceded():
    ctx, _, _ = tm._clear_into_goal_scene(mate_touch=True)
    [clear] = _kinds(ctx, "clear")
    assert clear.conceded is False


def test_a_goal_more_than_10_s_later_was_not_conceded():
    ctx, _, _ = tm._clear_into_goal_scene()
    [goal] = ctx.goals
    late = replace(ctx, goals=[replace(goal, t=goal.t + 8.0)])
    assert [c.conceded for c in _kinds(late, "clear")] == [False]


def test_your_own_teams_goal_was_not_conceded():
    ctx, _, _ = tm._clear_into_goal_scene()
    [goal] = ctx.goals
    ours = replace(ctx, goals=[replace(goal, team="ORANGE", scorer=ME)])
    assert [c.conceded for c in _kinds(ours, "clear")] == [False]


# Jumps at the ball


def test_a_jump_that_misses_the_ball_is_the_bad_choice():
    ctx, jumped, _ = tm._whiff_scene()
    [jump] = _kinds(ctx, "jump")
    assert (jump.bad, jump.player_id) == (True, ME)
    assert jump.t == pytest.approx(jumped, abs=tm.DT)
    assert jump.zone == "own_third"


def test_a_jump_that_touches_the_ball_is_the_good_choice():
    ctx, _, _ = tm._whiff_scene(touched=True)
    assert [j.bad for j in _kinds(ctx, "jump")] == [False]


def test_a_miss_is_a_miss_even_when_your_teammate_cleans_up():
    """The review doesn't flag it, but the choice was still a missed jump."""
    ctx, _, _ = tm._whiff_scene(taker=MATE)
    assert tm.detect_whiffs(ctx) == []
    assert [j.bad for j in _kinds(ctx, "jump")] == [True]


def test_a_jump_that_never_came_near_the_ball_is_no_situation():
    ctx, _, _ = tm._whiff_scene(beside=600.0)
    assert _kinds(ctx, "jump") == []


# 50/50s as the last player back


def _challenge_ctx(winner, **kwargs):
    frames, event = tm._challenge(winner, **kwargs)
    return tm._ctx(frames, challenges=[event])


def test_a_lost_5050_as_the_last_player_back_is_the_bad_choice():
    [challenge] = _kinds(_challenge_ctx("BLUE"), "last_back_challenge")
    assert challenge.bad is True
    # The ball was on halfway
    assert challenge.zone == "their_half"


def test_a_won_5050_as_the_last_player_back_is_the_good_choice():
    [challenge] = _kinds(_challenge_ctx("ORANGE"), "last_back_challenge")
    assert challenge.bad is False


def test_a_5050_with_a_teammate_deeper_is_no_situation():
    ctx = _challenge_ctx("BLUE", mate_y=4000.0)
    assert _kinds(ctx, "last_back_challenge") == []


def test_a_5050_on_the_kickoff_is_no_situation():
    frames, event = tm._challenge("BLUE")
    # Live, but inside the kickoff grace
    event = replace(event, t=2.0)
    ctx = tm._ctx(frames, challenges=[event])
    assert _kinds(ctx, "last_back_challenge") == []


# Runs at the ball


def _solo_run():
    """I drive at a still ball in my half with nobody else near it."""

    def players(t):
        return [
            tm._car(ME, ORANGE, -1400.0 + 1500.0 * t, 2000.0, vx=1500.0),
            tm._car(MATE, ORANGE, -3000.0, 5000.0),
            tm._car(OPP, BLUE, 3000.0, -3000.0),
        ]

    def ball(t):
        if t < 0.95:
            return tm._ball(0.0, 2000.0, 150.0)
        return tm._ball(0.0, 2000.0 - 2500.0 * (t - 0.95), 150.0, vy=-2500.0)

    return tm._play(1.5, players, ball)


def test_a_run_at_the_ball_after_a_nearer_teammate_is_the_bad_choice():
    frames, origin = tm._double_commit_scene()
    [commit] = _kinds(tm._ctx(frames), "commit")
    assert commit.bad is True
    assert commit.t == pytest.approx(origin, abs=0.3)
    assert commit.zone == "own_third"


def test_the_nearer_teammate_has_no_commit_to_judge():
    frames, _ = tm._double_commit_scene()
    assert _kinds(tm._ctx(frames, player=MATE), "commit") == []


def test_a_run_at_the_ball_on_your_own_is_the_good_choice():
    frames, origin = _solo_run()
    [commit] = _kinds(tm._ctx(frames), "commit")
    assert commit.bad is False
    assert commit.t == pytest.approx(origin, abs=0.3)


# Opponent attacks


def test_being_upfield_with_nobody_back_during_an_attack_is_the_bad_choice():
    frames, _ = tm._upfield_scene()
    [attack] = _kinds(tm._ctx(frames), "opp_attack")
    assert attack.bad is True
    assert attack.zone == "own_third"


def test_an_attack_with_a_teammate_back_is_the_good_choice():
    frames, _ = tm._upfield_scene(mate_y=4500.0)
    assert [a.bad for a in _kinds(tm._ctx(frames), "opp_attack")] == [False]


def test_your_team_on_the_ball_is_no_attack():
    frames, _ = tm._upfield_scene(mate_y=2000.0, last_touch=ORANGE)
    assert _kinds(tm._ctx(frames), "opp_attack") == []


# Shots with you last back


def _shot(my_y, goal_s=None):
    """Blue shoots from 1000 uu up my half at 0.5 s, with me last back at
    `my_y` and my teammate upfield."""

    def players(t):
        return [
            tm._car(ME, ORANGE, 300.0, my_y),
            tm._car(MATE, ORANGE, 0.0, -2000.0),
            tm._car(OPP, BLUE, 0.0, 880.0, vy=1000.0),
        ]

    # The ball's frame at the touch already carries the shot's speed
    def ball(t):
        if t < 0.5 - tm.DT / 2:
            return tm._ball(0.0, 1000.0)
        return tm._ball(0.0, 1000.0 + 2000.0 * (t - 0.5), vy=2000.0)

    frames, origin = tm._play(2.0, players, ball)
    shot = min(
        range(len(frames)), key=lambda i: abs(frames[i].timestamp - origin - 0.5)
    )
    frames[shot] = replace(frames[shot], touch_counts=[TouchCount(OPP, 1)])
    for i in range(shot, len(frames)):
        frames[i] = replace(frames[i], hit_team=BLUE)
    goals = [] if goal_s is None else [GoalEvent(origin + goal_s, OPP, "BLUE")]
    return tm._ctx(frames, goals=goals), origin


def test_a_shot_with_you_last_back_and_in_goal_is_the_good_choice():
    ctx, origin = _shot(4800.0)
    [shot] = _kinds(ctx, "shot_last_back")
    assert (shot.player_id, shot.bad) == (ME, False)
    assert shot.t == pytest.approx(origin + 0.5, abs=tm.DT)
    assert shot.zone == "own_half"


def test_a_shot_with_the_ball_already_past_you_is_the_bad_choice():
    ctx, _ = _shot(500.0)
    [shot] = _kinds(ctx, "shot_last_back")
    assert shot.bad is True


def test_a_shot_is_only_the_last_player_backs():
    ctx, _ = _shot(4800.0)
    mate = replace(ctx, player_id=MATE)
    assert _kinds(mate, "shot_last_back") == []


def test_a_shot_that_goes_in_was_conceded():
    ctx, _ = _shot(500.0, goal_s=1.9)
    [shot] = _kinds(ctx, "shot_last_back")
    assert (shot.bad, shot.conceded) == (True, True)


# A whole game


def _game(frames, goals=(), challenges=()):
    return Game(
        path=Path("synthetic.replay"),
        header=Header(team_size=2),
        frames=frames,
        goals=list(goals),
        touches=[],
        challenges=list(challenges),
        demos=[],
        kickoffs=[],
        boost_pickups=[],
    )


def test_a_game_has_every_cars_situations_and_skips_a_car_never_seen():
    # Each of us is our team's last back in the 50/50, and Blue won it
    frames, event = tm._challenge("BLUE")
    game = replace(_game(frames, challenges=[event]), touches=detect_touches(frames))
    names = {ME: "me", OPP: "opp", "ghost": "left at once"}
    found = game_situations(game, names)

    challenges = [s for s in found if s.kind == "last_back_challenge"]
    assert [(s.player_id, s.bad) for s in sorted(challenges, key=_order)] == [
        (ME, True),
        (OPP, False),
    ]
    expected = [
        s
        for player in (ME, OPP)
        for s in situations_for(tm._ctx(frames, player, challenges=[event]))
    ]
    assert sorted(found, key=_order) == sorted(expected, key=_order)
    assert found == sorted(found, key=lambda s: (s.t, s.player_id, s.kind))
    assert "ghost" not in {s.player_id for s in found}


def _order(s):
    return (s.player_id, s.t, s.kind)


@pytest.fixture(scope="module")
def regulation():
    """A real game and the review of the player who saved it."""
    game = read_game(real_replays.replay(real_replays.REGULATION))
    identities = build_player_identities(game.header.players)
    return game, identities, review_player(game, player_id=identities[0].canonical_id)


def test_a_real_game_has_situations_for_every_player(regulation):
    game, identities, report = regulation
    players = {s.player_id for s in report.situations}
    assert {i.canonical_id for i in identities} <= players
    assert {s.kind for s in report.situations} == set(KINDS)
    assert {s.zone for s in report.situations} == {
        "own_third",
        "own_half",
        "their_half",
    }
    assert any(s.conceded for s in report.situations)


def test_a_real_games_clears_match_the_review(regulation):
    _, identities, report = regulation
    mine = [
        s
        for s in report.situations
        if s.kind == "clear" and s.player_id == identities[0].canonical_id
    ]
    assert len(mine) == report.clears["clears"]
    assert sum(s.bad for s in mine) == report.clears["given_back"]
