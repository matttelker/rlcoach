"""Tests for kickoff coaching: your kickoffs, and the ladder of what to learn."""

from __future__ import annotations

from datetime import date

from rlcoach.events.kickoffs import KickoffEvent, KickoffPlayer
from rlcoach.kickoff_coaching import (
    MIN_KICKOFFS,
    GameKickoffs,
    kickoff_situations,
    read_kickoff,
    summarize_kickoffs,
)

ME, MATE, OPP = "me", "mate", "opp"
DAY = date(2026, 11, 6)
BLUE, ORANGE = 0, 1


def _car(player_id=ME, role="GO", approach="STANDARD_DIAGONAL", team=BLUE, **extra):
    extra.setdefault("spot", "DIAGONAL")
    return KickoffPlayer(player_id, role, approach, 33.0, 2.0, team=team, **extra)


def _kickoff(*players, t=4.0, ball_y_after=800.0, first=ME):
    return KickoffEvent(
        t_start=t,
        players=players,
        first_touch_player=first,
        time_to_first_touch=2.0,
        first_touch_team="BLUE",
        ball_y_after=ball_y_after,
    )


def _game(*kickoffs, goals=(), day=DAY, replay_id="r1"):
    return GameKickoffs(replay_id, day, ME, list(kickoffs), list(goals))


def _seen(kickoff, goals=()):
    return read_kickoff(_game(kickoff, goals=goals), kickoff)


# One kickoff


def test_a_kickoff_reads_from_your_seat():
    seen = _seen(
        _kickoff(
            _car(flip_lead=0.1, speed_at_contact=2100.0),
            _car(OPP, team=ORANGE),
            ball_y_after=-800.0,
            first=OPP,
        )
    )
    assert (seen.role, seen.spot, seen.flip, seen.flip_lead) == (
        "GO",
        "DIAGONAL",
        "ON_TIME",
        0.1,
    )
    # Blue attacks +y, so the ball heading for -y went against you
    assert (seen.result, seen.first_touch) == ("LOST", "opponent")
    assert seen.speed_at_contact == 2100.0


def test_a_kickoff_you_werent_in_reads_as_nothing():
    assert _seen(_kickoff(_car(OPP, team=ORANGE))) is None


def test_the_race_compares_you_with_the_opposing_go_from_the_same_spawn():
    me = _car(reach_time=1.70)
    rival = _car(OPP, team=ORANGE, reach_time=1.62)
    assert _seen(_kickoff(me, rival)).race_gap == 0.08
    # A rival from another spawn, or one that faked, is no race
    other_spot = _car(OPP, team=ORANGE, reach_time=1.62, spot="OFF_CENTRE")
    assert _seen(_kickoff(me, other_spot)).race_gap is None
    faked = _car(OPP, "GO", "FAKE_STATIONARY", team=ORANGE, reach_time=1.62)
    assert _seen(_kickoff(me, faked)).race_gap is None


def test_a_goal_soon_after_the_kickoff_is_counted_for_or_against():
    kickoff = _kickoff(_car(), _car(OPP, team=ORANGE))
    # Played 2 s after the release at 4 s
    seen = _seen(kickoff, goals=[(11.0, False)])
    assert (seen.goal_after, seen.goal_after_s) == ("against", 5.0)
    assert _seen(kickoff, goals=[(7.0, True)]).goal_after == "for"
    assert _seen(kickoff, goals=[(30.0, False)]).goal_after is None


def test_going_from_behind_a_teammate_is_a_double_commit():
    me = _car(role="BACK", approach="STANDARD_BOOST", spot="BACK")
    mate = _car(MATE)
    seen = _seen(_kickoff(me, mate, first=MATE))
    assert seen.double_commit is True
    assert seen.first_touch == "teammate"


# Many kickoffs


def _going(flip_lead, approach="STANDARD_DIAGONAL", ball_y_after=800.0, t=4.0):
    return _kickoff(
        _car(approach=approach, flip_lead=flip_lead),
        _car(OPP, team=ORANGE),
        ball_y_after=ball_y_after,
        t=t,
    )


def _support(approach="SUPPORT_HOLD", t=4.0):
    return _kickoff(
        _car(role="BACK", approach=approach, spot="BACK"),
        _car(MATE),
        _car(OPP, team=ORANGE),
        t=t,
    )


def test_your_go_kickoffs_are_split_by_how_you_flipped():
    summary = summarize_kickoffs(
        [
            _game(
                _going(0.1),
                _going(0.12, ball_y_after=-900.0),
                _going(-0.05, ball_y_after=-900.0),
                _going(None, approach="STANDARD_BOOST", ball_y_after=-900.0),
                _going(None, approach="FAKE_STATIONARY"),
            )
        ]
    )
    going = summary["going"]
    assert (going["count"], going["went"], going["fakes"]) == (5, 4, 1)
    assert going["flips"] == {"on_time": 2, "late": 1, "none": 1}
    on_time = next(g for g in going["by_flip"] if g["flip"] == "ON_TIME")
    assert (on_time["count"], on_time["won"], on_time["lost"]) == (2, 1, 1)


def test_support_kickoffs_count_cheats_holds_and_double_commits():
    summary = summarize_kickoffs(
        [
            _game(
                _support(),
                _support("SUPPORT_CHEAT"),
                _support("STANDARD_FRONTFLIP"),
            )
        ]
    )
    support = summary["support"]
    assert (support["count"], support["hold"], support["cheat"]) == (3, 1, 1)
    assert support["double_commits"] == 1


def test_sessions_count_each_days_on_time_flips():
    summary = summarize_kickoffs(
        [
            _game(_going(0.1), _going(None), day=date(2026, 11, 5)),
            _game(_going(0.1), day=DAY, replay_id="r2"),
        ]
    )
    assert summary["sessions"] == [
        {"play_date": "2026-11-05", "went": 2, "on_time": 1, "double_commits": 0},
        {"play_date": "2026-11-06", "went": 1, "on_time": 1, "double_commits": 0},
    ]


def _ladder(*kickoffs):
    return {s["key"]: s for s in summarize_kickoffs([_game(*kickoffs)])["ladder"]}


def test_the_ladder_goes_in_a_coachs_order():
    keys = [s["key"] for s in summarize_kickoffs([])["ladder"]]
    assert keys == ["flip_in", "on_time", "speedflip"]


def test_the_first_step_you_havent_got_is_the_focus():
    # Always flipping into the ball, but late more often than not
    ladder = _ladder(
        *[_going(-0.05, t=float(n)) for n in range(4)],
        *[_going(0.1, t=10.0 + n) for n in range(2)],
        *[_support(t=20.0 + n) for n in range(MIN_KICKOFFS)],
    )
    assert ladder["flip_in"]["status"] == "solid"
    assert ladder["on_time"]["status"] == "focus"
    assert (ladder["on_time"]["count"], ladder["on_time"]["of"]) == (2, 6)
    assert ladder["speedflip"]["status"] == "later"


def _going_with_a_teammate(t):
    return _kickoff(
        _car(role="BACK", approach="STANDARD_BOOST", spot="BACK"),
        _car(MATE),
        _car(OPP, team=ORANGE),
        t=t,
    )


def test_every_step_with_too_few_kickoffs_you_went_for_is_unknown():
    # Too few GO kickoffs to judge the flip, though enough kickoffs in all
    ladder = _ladder(
        *[_going(0.1, t=float(n)) for n in range(MIN_KICKOFFS - 1)],
        *[_going_with_a_teammate(10.0 + n) for n in range(3)],
    )
    assert [s["status"] for s in ladder.values()] == ["unknown"] * 3


def test_the_speedflip_step_says_what_one_is():
    ladder = _ladder(*[_going(0.1, t=float(n)) for n in range(MIN_KICKOFFS)])
    assert ladder["speedflip"]["status"] == "focus"
    assert "speedflip is a kickoff" in ladder["speedflip"]["why"]


def test_a_double_commit_from_level_spawns_is_still_counted():
    """No longer a ladder step, but still counted and shown."""
    level = _kickoff(
        _car(flip_lead=0.1),
        _car(MATE, "WING", "STANDARD_BOOST"),
        _car(OPP, team=ORANGE),
    )
    summary = summarize_kickoffs([_game(level)])
    assert summary["double_commits"] == 1
    assert summary["support"]["double_commits"] == 0


def test_the_why_quotes_your_own_kickoffs():
    ladder = _ladder(
        *[
            _going(None, approach="STANDARD_BOOST", ball_y_after=-900.0, t=n)
            for n in range(2)
        ],
        *[_going(0.1, t=10.0 + n) for n in range(3)],
    )
    assert "2 of 2 (100%) kickoffs with no flip" in ladder["flip_in"]["why"]
    assert "0 of 3 (0%) with one on time" in ladder["flip_in"]["why"]


# Kickoffs as situations


def _situations(*kickoffs, goals=()):
    return kickoff_situations(_game(*kickoffs, goals=goals))


def test_each_go_car_that_went_is_a_situation_and_yours_is_marked():
    kickoff = _kickoff(
        _car(flip_lead=0.1),
        _car(MATE, role="BACK", approach="SUPPORT_HOLD", spot="BACK"),
        _car(OPP, team=ORANGE, flip_lead=-0.05),
    )
    rows = _situations(kickoff)
    assert [(r.kind, r.zone, r.mine, r.bad) for r in rows] == [
        ("kickoff", "", True, False),
        ("kickoff", "", False, True),
    ]


def test_a_kickoff_without_a_flip_on_time_is_the_bad_choice():
    for lead, bad in ((None, True), (-0.05, True), (0.1, False)):
        [row] = _situations(_kickoff(_car(flip_lead=lead)))
        assert row.bad is bad


def test_a_fake_or_a_kickoff_you_werent_in_is_no_situation():
    faked = _car(OPP, "GO", "FAKE_STATIONARY", team=ORANGE)
    assert [r.mine for r in _situations(_kickoff(_car(flip_lead=0.1), faked))] == [True]
    assert _situations(_kickoff(_car(OPP, team=ORANGE, flip_lead=0.1))) == []


def test_a_goal_soon_after_counts_against_the_team_that_conceded_it():
    kickoff = _kickoff(_car(flip_lead=0.1), _car(OPP, team=ORANGE, flip_lead=0.1))
    # Played 2 s after the release at 4 s, so 6 s; a goal against you at 11 s
    mine, theirs = _situations(kickoff, goals=[(11.0, False)])
    assert (mine.conceded, theirs.conceded) == (True, False)
    mine, theirs = _situations(kickoff, goals=[(11.0, True)])
    assert (mine.conceded, theirs.conceded) == (False, True)
    # Past the 10 s, or before the ball was played, it followed from nothing
    for t in (17.0, 5.0):
        assert not any(r.conceded for r in _situations(kickoff, goals=[(t, False)]))
