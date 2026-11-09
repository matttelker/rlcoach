"""Tests for storing mistake reviews."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from rlcoach.analysis.mistakes import (
    ChallengeMoment,
    DemoMoment,
    GoalMoment,
    GoalReview,
    KickoffMoment,
    Mistake,
    MistakeReport,
    TouchMoment,
)
from rlcoach.db.models import (
    GameReview,
    Player,
    Replay,
    ReviewChallenge,
    ReviewDemo,
    ReviewGoal,
    ReviewKickoff,
    ReviewKickoffCar,
    ReviewMistake,
    ReviewTouch,
)
from rlcoach.db.reviews import games_to_review, review_game, save_review
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.events.kickoffs import KickoffEvent, KickoffPlayer
from rlcoach.events.types import ChallengeEvent, DemoEvent, TouchEvent
from rlcoach.field_constants import Vec3


@pytest.fixture(autouse=True)
def db(tmp_path):
    init_db(tmp_path / "test.db")
    session = create_session()
    session.add(Player(player_id="epic:me", display_name="Me", is_me=True))
    for n in range(2):
        session.add(
            Replay(
                replay_id=f"r{n}",
                source_file=str(tmp_path / f"r{n}.replay"),
                file_hash=f"h{n}",
                played_at_utc=datetime(2026, 11, 5, 23, n, tzinfo=UTC),
                play_date=date(2026, 11, 5),
                map="Stadium_P",
                playlist="STANDARD",
                team_size=3,
                duration_seconds=400.0,
                my_player_id="epic:me",
                my_team="ORANGE",
            )
        )
    session.commit()
    session.close()
    yield
    reset_engine()


def _report() -> MistakeReport:
    flag = Mistake(
        kind="last_back_upfield",
        t=200.0,
        frame=5000,
        clock="2:27",
        score="3-1",
        duration=0.0,
        what="You were too far upfield.",
        instead="Hold near halfway.",
        outcome="You conceded 4 s later.",
        category="last_back",
        seconds_left=147.0,
        cost_goal=True,
    )
    against = GoalReview(
        t=204.0,
        clock="2:23",
        score="3-1",
        scorer="hezekkia",
        on_you=True,
        summary="You were the last one back.",
        lines=("You were beaten by the shot (73 boost)",),
        seconds_left=143.0,
    )
    return MistakeReport(
        player="Me",
        team="ORANGE",
        map_name="Stadium_P",
        final_score="5-4",
        goals=[against],
        mistakes=[flag],
        clears={"clears": 3, "given_back": 1},
        player_id="epic:me",
        goal_timeline=[
            GoalMoment(
                99.0, "3:45", 225.0, "1-0", True, "You", True, False, False, False
            ),
            GoalMoment(
                204.0,
                "2:23",
                143.0,
                "3-1",
                False,
                "hezekkia",
                False,
                False,
                False,
                False,
            ),
        ],
    )


def test_save_review_stores_flags_and_both_teams_goals():
    save_review("r0", "epic:me", _report())

    session = create_session()
    review = session.get(GameReview, "r0")
    assert review.status == "ok"
    assert (review.clears, review.clears_given_back) == (3, 1)
    assert [(m.kind, m.category, m.cost_goal) for m in review.mistakes] == [
        ("last_back_upfield", "last_back", True)
    ]
    ours, theirs = review.goals
    assert ours.by_me and ours.on_me is None
    assert theirs.on_me is True
    assert theirs.summary == "You were the last one back."
    assert json.loads(theirs.lines) == ["You were beaten by the shot (73 boost)"]
    session.close()


def test_saving_again_replaces_the_old_review():
    save_review("r0", "epic:me", _report())
    save_review("r0", "epic:me", status="error", error="parser failed")

    session = create_session()
    review = session.get(GameReview, "r0")
    assert review.status == "error"
    assert session.query(ReviewMistake).count() == 0
    assert session.query(ReviewGoal).count() == 0
    session.close()


def test_games_to_review_skips_reviewed_games_unless_redoing():
    save_review("r0", "epic:me", _report())
    assert [g[0] for g in games_to_review()] == ["r1"]
    assert [g[0] for g in games_to_review(redo=True)] == ["r0", "r1"]


def test_review_game_records_a_failure_instead_of_raising(tmp_path):
    status = review_game("r1", tmp_path / "missing.replay", "epic:me")

    assert status == "error"
    session = create_session()
    assert session.get(GameReview, "r1").status == "error"
    session.close()


def _with_kickoff() -> MistakeReport:
    me = KickoffPlayer(
        "epic:me",
        "GO",
        "STANDARD_DIAGONAL",
        33.0,
        2.1,
        team=1,
        spot="DIAGONAL",
        flip_lead=0.12,
        reach_time=1.66,
        speed_at_contact=2080.0,
    )
    them = KickoffPlayer("epic:them", "GO", "SPEEDFLIP", 30.0, 2.1, team=0)
    kickoff = KickoffEvent(
        t_start=4.1,
        players=(me, them),
        first_touch_player="epic:them",
        time_to_first_touch=2.1,
        first_touch_team="BLUE",
        ball_y_after=-900.0,
    )
    return replace(
        _report(), kickoffs=[KickoffMoment(4.1, "5:00", 300.0, "0-0", kickoff)]
    )


def test_save_review_stores_every_car_of_every_kickoff():
    save_review("r0", "epic:me", _with_kickoff())

    session = create_session()
    [kickoff] = session.get(GameReview, "r0").kickoffs
    assert (kickoff.t, kickoff.clock, kickoff.score, kickoff.phase) == (
        4.1,
        "5:00",
        "0-0",
        "INITIAL",
    )
    assert (kickoff.first_touch_team, kickoff.ball_y_after) == ("BLUE", -900.0)
    cars = {car.player_id: car for car in kickoff.cars}
    mine = cars["epic:me"]
    assert mine.is_me and not cars["epic:them"].is_me
    assert (mine.team, mine.role, mine.spot, mine.approach) == (
        1,
        "GO",
        "DIAGONAL",
        "STANDARD_DIAGONAL",
    )
    assert (mine.flip_lead, mine.reach_time, mine.speed_at_contact) == (
        0.12,
        1.66,
        2080.0,
    )
    session.close()


def test_saving_again_replaces_the_kickoffs_too():
    save_review("r0", "epic:me", _with_kickoff())
    save_review("r0", "epic:me", _with_kickoff())
    session = create_session()
    assert session.query(ReviewKickoff).count() == 1
    assert session.query(ReviewKickoffCar).count() == 2
    save_review("r0", "epic:me", status="error", error="parser failed")
    assert session.query(ReviewKickoff).count() == 0
    assert session.query(ReviewKickoffCar).count() == 0
    session.close()


def _with_events() -> MistakeReport:
    mine = TouchEvent(10.0, "epic:me", Vec3(100.0, 2000.0, 17.0), 55.5, 300, 1)
    theirs = TouchEvent(10.4, "epic:them", Vec3(300.0, 2400.0, 17.0), 40.0, 312, 0)
    challenge = ChallengeEvent(
        10.2, "epic:me", "epic:them", "BLUE", Vec3(200.0, 2200.0, 17.0)
    )
    demo = DemoEvent(50.0, "epic:them", "epic:me", Vec3(-500.0, -3000.0, 17.0))
    unseen = DemoEvent(60.0, "epic:me")
    return replace(
        _report(),
        touches=[TouchMoment(290.0, mine), TouchMoment(289.6, theirs)],
        challenges=[ChallengeMoment(289.8, challenge, True, None)],
        demos=[DemoMoment(250.0, demo), DemoMoment(240.0, unseen)],
    )


def test_save_review_stores_every_touch_5050_and_demo():
    save_review("r0", "epic:me", _with_events())

    session = create_session()
    review = session.get(GameReview, "r0")
    assert [
        (t.t, t.seconds_left, t.player_id, t.team, t.is_me, t.x, t.y, t.z)
        for t in review.touches
    ] == [
        (10.0, 290.0, "epic:me", 1, True, 100.0, 2000.0, 17.0),
        (10.4, 289.6, "epic:them", 0, False, 300.0, 2400.0, 17.0),
    ]
    assert [t.ball_speed_kph for t in review.touches] == [55.5, 40.0]
    [challenge] = review.challenges
    assert (challenge.t, challenge.seconds_left, challenge.winner_team) == (
        10.2,
        289.8,
        "BLUE",
    )
    assert (challenge.first_player, challenge.second_player) == (
        "epic:me",
        "epic:them",
    )
    assert (challenge.x, challenge.y, challenge.z) == (200.0, 2200.0, 17.0)
    assert (challenge.first_last_back, challenge.second_last_back) == (True, None)
    seen, unseen = review.demos
    assert (seen.victim, seen.attacker, seen.x, seen.y) == (
        "epic:them",
        "epic:me",
        -500.0,
        -3000.0,
    )
    assert (unseen.t, unseen.seconds_left, unseen.attacker, unseen.y) == (
        60.0,
        240.0,
        None,
        None,
    )
    session.close()


def test_saving_again_replaces_the_events_too():
    save_review("r0", "epic:me", _with_events())
    save_review("r0", "epic:me", _with_events())
    session = create_session()
    counts = (ReviewTouch, ReviewChallenge, ReviewDemo)
    assert [session.query(table).count() for table in counts] == [2, 1, 2]
    save_review("r0", "epic:me", status="unsupported", error="Hoops")
    assert [session.query(table).count() for table in counts] == [0, 0, 0]
    session.close()


def test_a_database_from_before_the_events_gets_them_on_the_next_review(tmp_path):
    save_review("r0", "epic:me", _report())
    session = create_session()
    engine = session.get_bind()
    session.close()
    with engine.begin() as connection:
        for table in ("review_touches", "review_challenges", "review_demos"):
            connection.exec_driver_sql(f"DROP TABLE {table}")
    reset_engine()

    init_db(tmp_path / "test.db")
    save_review("r0", "epic:me", _with_events())
    session = create_session()
    review = session.get(GameReview, "r0")
    assert (len(review.touches), len(review.challenges), len(review.demos)) == (
        2,
        1,
        2,
    )
    session.close()
