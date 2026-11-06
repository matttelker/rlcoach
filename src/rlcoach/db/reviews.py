"""Store the mistake detector's review of each game.

Ingest reviews every new game. `rlcoach reviews` fills in games loaded before
reviews existed, or redoes them all after the detector changes.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from .models import GameReview, Replay, ReviewGoal, ReviewMistake
from .session import create_session

if TYPE_CHECKING:
    from ..analysis.mistakes import MistakeReport

logger = logging.getLogger(__name__)


def save_review(
    replay_id: str,
    player_id: str,
    report: MistakeReport | None = None,
    *,
    status: str = "ok",
    error: str | None = None,
) -> None:
    """Replace a game's stored review with this one."""
    session = create_session()
    try:
        existing = session.get(GameReview, replay_id)
        if existing is not None:
            session.delete(existing)
            session.flush()

        review = GameReview(
            replay_id=replay_id,
            player_id=player_id,
            status=status,
            error=error,
        )
        if report is not None:
            review.clears = report.clears.get("clears", 0)
            review.clears_given_back = report.clears.get("given_back", 0)
            review.mistakes = [
                ReviewMistake(
                    kind=m.kind,
                    category=m.category,
                    t=m.t,
                    seconds_left=m.seconds_left,
                    clock=m.clock,
                    score=m.score,
                    duration=m.duration,
                    what=m.what,
                    instead=m.instead,
                    outcome=m.outcome,
                    cost_goal=m.cost_goal,
                )
                for m in report.mistakes
            ]
            conceded = {g.t: g for g in report.goals}
            goals = []
            for g in report.goal_timeline:
                against = None if g.ours else conceded.get(g.t)
                goals.append(
                    ReviewGoal(
                        t=g.t,
                        seconds_left=g.seconds_left,
                        clock=g.clock,
                        score=g.score,
                        ours=g.ours,
                        scorer=g.scorer,
                        by_me=g.by_you,
                        assist_by_me=g.assist_by_you,
                        winner=g.winner,
                        equalizer=g.equalizer,
                        on_me=against.on_you if against else None,
                        summary=against.summary if against else None,
                        lines=json.dumps(list(against.lines)) if against else None,
                    )
                )
            review.goals = goals
        session.add(review)
        session.commit()
    finally:
        session.close()


def review_game(replay_id: str, path: Path | str, player_id: str) -> str:
    """Review one game and store the result. Returns the stored status."""
    from ..analysis.mistakes import UnsupportedReplayError, analyze_replay

    try:
        report = analyze_replay(Path(path), player_id=player_id)
    except UnsupportedReplayError as e:
        save_review(replay_id, player_id, status="unsupported", error=str(e))
        return "unsupported"
    except Exception as e:  # noqa: BLE001 - one bad replay mustn't stop ingest
        logger.warning("Mistake review failed for %s: %s", path, e)
        save_review(replay_id, player_id, status="error", error=str(e))
        return "error"
    save_review(replay_id, player_id, report)
    return "ok"


def games_to_review(redo: bool = False) -> list[tuple[str, str, str]]:
    """List (replay_id, source_file, my_player_id) for games needing a review."""
    session = create_session()
    try:
        query = session.query(
            Replay.replay_id, Replay.source_file, Replay.my_player_id
        ).filter(Replay.my_player_id.isnot(None))
        if not redo:
            reviewed = session.query(GameReview.replay_id)
            query = query.filter(Replay.replay_id.notin_(reviewed))
        return [tuple(row) for row in query.order_by(Replay.played_at_utc).all()]
    finally:
        session.close()
