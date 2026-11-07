"""Grade the review's calls right or wrong, and tally the grades per rule."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...db.grades import goal_ref, mistake_ref, set_grade, summarize_grades

router = APIRouter(tags=["grades"])


class GradeRequest(BaseModel):
    """One call to grade: a flagged moment by kind and time, or a goal by time.

    A grade of null clears it.
    """

    item: Literal["mistake", "goal"]
    t: float
    kind: str | None = None
    grade: Literal["right", "wrong"] | None


@router.put("/replays/{replay_id}/grades")
async def put_grade(replay_id: str, request: GradeRequest) -> dict[str, Any]:
    """Mark one of the review's calls in this game right or wrong."""
    if request.item == "mistake":
        if not request.kind:
            raise HTTPException(status_code=400, detail="A flagged moment needs kind")
        ref = mistake_ref(request.kind, request.t)
    else:
        ref = goal_ref(request.t)

    if not set_grade(replay_id, request.item, ref, request.grade):
        raise HTTPException(
            status_code=404, detail="This game's review makes no such call"
        )
    return {"item": request.item, "ref": ref, "grade": request.grade}


@router.get("/grades")
async def get_grades() -> dict[str, Any]:
    """Right and wrong per rule, from the calls you've graded."""
    return {"rules": summarize_grades()}
