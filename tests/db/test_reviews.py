"""Tests for storing mistake reviews."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from rlcoach.analysis.mistakes import GoalMoment, GoalReview, Mistake, MistakeReport
from rlcoach.db.models import GameReview, Player, Replay, ReviewGoal, ReviewMistake
from rlcoach.db.reviews import games_to_review, review_game, save_review
from rlcoach.db.session import create_session, init_db, reset_engine


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
