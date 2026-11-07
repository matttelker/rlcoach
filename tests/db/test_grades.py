"""Tests for grading the mistake review's calls."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from rlcoach.analysis.mistakes import GoalMoment, GoalReview, Mistake, MistakeReport
from rlcoach.db.grades import (
    goal_kind,
    goal_ref,
    grades_for,
    mistake_ref,
    set_grade,
    summarize_grades,
)
from rlcoach.db.models import Player, Replay, ReviewGrade
from rlcoach.db.reviews import save_review
from rlcoach.db.session import create_session, init_db, reset_engine

FLAG_T = 200.0
GOAL_T = 204.0
FLAG = ("mistake", mistake_ref("last_back_upfield", FLAG_T))
GOAL = ("goal", goal_ref(GOAL_T))


@pytest.fixture(autouse=True)
def db(tmp_path):
    init_db(tmp_path / "test.db")
    session = create_session()
    session.add(Player(player_id="epic:me", display_name="Me", is_me=True))
    session.add(
        Replay(
            replay_id="r0",
            source_file=str(tmp_path / "r0.replay"),
            file_hash="h0",
            played_at_utc=datetime(2026, 11, 5, 23, tzinfo=UTC),
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
    save_review("r0", "epic:me", _report())
    yield
    reset_engine()


def _report(flag_t: float = FLAG_T, on_you: bool = True) -> MistakeReport:
    flag = Mistake(
        kind="last_back_upfield",
        t=flag_t,
        frame=5000,
        clock="2:27",
        score="3-1",
        duration=0.0,
        what="You were 20 m into their half.",
        instead="Go no further than halfway.",
        category="last_back",
        seconds_left=147.0,
        cost_goal=True,
    )
    against = GoalReview(
        t=GOAL_T,
        clock="2:23",
        score="3-1",
        scorer="hezekkia",
        on_you=on_you,
        summary="You were the last one back." if on_you else "No mistake found.",
        lines=(),
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
                GOAL_T,
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


def _grades() -> dict:
    session = create_session()
    try:
        return grades_for(session, "r0")
    finally:
        session.close()


def test_grading_a_flag_and_a_goal_verdict():
    assert set_grade("r0", *FLAG, "right")
    assert set_grade("r0", *GOAL, "wrong")

    assert _grades() == {FLAG: "right", GOAL: "wrong"}
    assert summarize_grades() == [
        {
            "item": "goal",
            "kind": "goal_on_you",
            "label": "Goal put on you",
            "right": 0,
            "wrong": 1,
        },
        {
            "item": "mistake",
            "kind": "last_back_upfield",
            "label": "Last back upfield",
            "right": 1,
            "wrong": 0,
        },
    ]


def test_grading_again_changes_the_grade_and_none_clears_it():
    set_grade("r0", *FLAG, "right")
    set_grade("r0", *FLAG, "wrong")
    assert _grades() == {FLAG: "wrong"}

    set_grade("r0", *FLAG, None)
    assert _grades() == {}
    session = create_session()
    assert session.query(ReviewGrade).count() == 0
    session.close()


def test_the_grade_keeps_what_the_review_said():
    set_grade("r0", *FLAG, "right")

    session = create_session()
    grade = session.query(ReviewGrade).one()
    assert (grade.kind, grade.label) == (
        "last_back_upfield",
        "You were 20 m into their half.",
    )
    session.close()


def test_grades_survive_redoing_the_review():
    set_grade("r0", *FLAG, "right")
    save_review("r0", "epic:me", _report())

    assert _grades() == {FLAG: "right"}


def test_a_grade_stops_counting_when_the_review_changes_its_call():
    set_grade("r0", *FLAG, "wrong")
    set_grade("r0", *GOAL, "wrong")

    # A detector change moves the flag and clears you of the goal
    save_review("r0", "epic:me", _report(flag_t=FLAG_T + 1, on_you=False))
    assert _grades() == {}
    assert summarize_grades() == []

    # The grades are kept, so they come back if the call does
    save_review("r0", "epic:me", _report())
    assert _grades() == {FLAG: "wrong", GOAL: "wrong"}


def test_a_call_the_review_doesnt_make_cant_be_graded():
    assert not set_grade("r0", "mistake", mistake_ref("ball_chase", FLAG_T), "right")
    assert not set_grade("r0", "goal", goal_ref(99.0), "right")  # your own goal
    assert not set_grade("nope", *FLAG, "right")


def test_bad_items_and_grades_are_refused():
    with pytest.raises(ValueError):
        set_grade("r0", "kickoff", "x", "right")
    with pytest.raises(ValueError):
        set_grade("r0", *FLAG, "maybe")


@pytest.mark.parametrize(
    "on_me, summary, kind",
    [
        (True, "You were the last one back.", "goal_on_you"),
        (False, "A teammate had the chance to stop this.", "goal_teammate"),
        (False, "No mistake found.", "goal_none"),
        (None, None, "goal_none"),
    ],
)
def test_goal_kind(on_me, summary, kind):
    assert goal_kind(on_me, summary) == kind
