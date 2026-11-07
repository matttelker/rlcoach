"""Your right-or-wrong grades on the mistake review's calls.

You grade a flagged moment, or the verdict on a goal against, while watching
the replay. The tally per rule shows which rules to trust, fix or drop.

A grade applies only while the review still makes the call you graded. If a
detector change moves a moment or changes a goal's verdict, the old grade stays
stored but no longer shows or counts.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import Any

from sqlalchemy.orm import Session

from .models import ReviewGoal, ReviewGrade, ReviewMistake
from .session import create_session

ITEMS = ("mistake", "goal")
GRADES = ("right", "wrong")

# How a goal against was called, for grading the call itself
GOAL_KINDS = {
    "goal_on_you": "Goal put on you",
    "goal_teammate": "Goal put on a teammate",
    "goal_none": "No mistake found",
}

Call = tuple[str, str, str]  # replay_id, item, ref


def mistake_ref(kind: str, t: float) -> str:
    return f"{kind}@{t:.2f}"


def goal_ref(t: float) -> str:
    return f"{t:.2f}"


def goal_kind(on_me: bool | None, summary: str | None) -> str:
    if on_me:
        return "goal_on_you"
    if summary and summary.startswith("A teammate"):
        return "goal_teammate"
    return "goal_none"


def kind_label(kind: str) -> str:
    return GOAL_KINDS.get(kind) or kind.replace("_", " ").capitalize()


def current_calls(
    session: Session, replay_ids: Iterable[str]
) -> dict[Call, tuple[str, str]]:
    """Map each call the stored reviews make now to its (kind, label)."""
    ids = list(replay_ids)
    calls: dict[Call, tuple[str, str]] = {}
    for m in session.query(ReviewMistake).filter(ReviewMistake.replay_id.in_(ids)):
        calls[(m.replay_id, "mistake", mistake_ref(m.kind, m.t))] = (m.kind, m.what)
    goals = session.query(ReviewGoal).filter(
        ReviewGoal.replay_id.in_(ids), ReviewGoal.ours.is_(False)
    )
    for g in goals:
        kind = goal_kind(g.on_me, g.summary)
        calls[(g.replay_id, "goal", goal_ref(g.t))] = (kind, g.summary or "")
    return calls


def _live_grades(session: Session, grades: list[ReviewGrade]) -> list[ReviewGrade]:
    """Keep the grades whose call the review still makes."""
    calls = current_calls(session, {g.replay_id for g in grades})
    return [
        g
        for g in grades
        if (call := calls.get((g.replay_id, g.item, g.ref))) and call[0] == g.kind
    ]


def grades_for(session: Session, replay_id: str) -> dict[tuple[str, str], str]:
    """Map (item, ref) to "right" or "wrong" for one game's current calls."""
    grades = session.query(ReviewGrade).filter(ReviewGrade.replay_id == replay_id)
    return {(g.item, g.ref): g.grade for g in _live_grades(session, grades.all())}


def set_grade(replay_id: str, item: str, ref: str, grade: str | None) -> bool:
    """Grade one call, or clear its grade with None.

    Returns False when the game's review makes no such call.
    """
    if item not in ITEMS or (grade is not None and grade not in GRADES):
        raise ValueError(f"Unknown item {item!r} or grade {grade!r}")
    session = create_session()
    try:
        call = current_calls(session, [replay_id]).get((replay_id, item, ref))
        if call is None:
            return False
        existing = (
            session.query(ReviewGrade)
            .filter_by(replay_id=replay_id, item=item, ref=ref)
            .one_or_none()
        )
        if grade is None:
            if existing is not None:
                session.delete(existing)
        elif existing is None:
            kind, label = call
            session.add(
                ReviewGrade(
                    replay_id=replay_id,
                    item=item,
                    ref=ref,
                    kind=kind,
                    label=label,
                    grade=grade,
                )
            )
        else:
            existing.kind, existing.label = call
            existing.grade = grade
        session.commit()
        return True
    finally:
        session.close()


def summarize_grades() -> list[dict[str, Any]]:
    """Tally right and wrong per rule, most graded first."""
    session = create_session()
    try:
        grades = _live_grades(session, session.query(ReviewGrade).all())
    finally:
        session.close()
    tally = Counter((g.item, g.kind, g.grade) for g in grades)
    rules = {(item, kind) for item, kind, _ in tally}
    summary = [
        {
            "item": item,
            "kind": kind,
            "label": kind_label(kind),
            "right": tally[(item, kind, "right")],
            "wrong": tally[(item, kind, "wrong")],
        }
        for item, kind in rules
    ]
    return sorted(summary, key=lambda r: (-(r["right"] + r["wrong"]), r["label"]))
