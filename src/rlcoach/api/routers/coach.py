"""Coaching endpoints: training targets, highlights and per-game reviews."""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import selectinload

from ...analysis.mistakes import CATEGORIES
from ...analysis.weaknesses import detect_weaknesses
from ...coaching import (
    FlagRow,
    GoalRow,
    ReviewedGame,
    find_highlights,
    pick_targets,
    summarize_categories,
)
from ...db.models import Benchmark, GameReview, PlayerGameStats, Replay
from ...db.session import create_session
from .analysis import _metric_direction, _resolve_playlist

router = APIRouter(tags=["coach"])

# Per-game counts that read naturally as "more goals than GC1 players"
STRENGTH_METRICS = ("goals", "assists", "saves", "shots")


def _date_from(period: str) -> date | None:
    if period == "all":
        return None
    try:
        days = int(period.removesuffix("d"))
    except ValueError:
        raise HTTPException(
            status_code=400, detail="period must be 'all' or a number of days like 30d"
        ) from None
    return date.today() - timedelta(days=days)


def _target_rank() -> str:
    from ..app import get_config

    try:
        return get_config().preferences.target_rank
    except RuntimeError:
        return "GC1"


def _benchmark_strengths(session, stats: list[PlayerGameStats], playlist: str, rank):
    """Stats where your average beats the target rank's spread."""
    if not stats:
        return []
    averages = {}
    for metric in STRENGTH_METRICS:
        values = [getattr(s, metric) for s in stats if getattr(s, metric) is not None]
        if values:
            averages[metric] = sum(values) / len(values)
    benchmarks = {
        b.metric: {
            "p25": b.p25_value,
            "median": b.median_value,
            "p75": b.p75_value,
            "direction": _metric_direction(b.metric),
        }
        for b in session.query(Benchmark)
        .filter(Benchmark.playlist == playlist, Benchmark.rank_tier == rank)
        .all()
        if b.metric in STRENGTH_METRICS
    }
    results = detect_weaknesses(averages, benchmarks)
    return [
        {
            "kind": "benchmark",
            "title": f"More {r.metric} than {rank} players",
            "detail": (
                f"{r.my_value:.1f} a game, {rank} average {r.benchmark_median:.1f}"
            ),
            "replay_id": None,
        }
        for r in sorted(results, key=lambda r: -r.z_score)
        if r.severity.value == "strength"
    ]


@router.get("/coach")
async def get_coach(
    playlist: str | None = None,
    period: str = Query(default="30d", description="7d, 30d, 90d or all"),
) -> dict[str, Any]:
    """Training targets, mistakes by category, the latest session and highlights."""
    playlist = _resolve_playlist(playlist)
    date_from = _date_from(period)
    rank = _target_rank()

    session = create_session()
    try:
        query = (
            session.query(Replay, PlayerGameStats)
            .outerjoin(
                PlayerGameStats,
                and_(
                    PlayerGameStats.replay_id == Replay.replay_id,
                    PlayerGameStats.is_me.is_(True),
                ),
            )
            .options(
                selectinload(Replay.review).selectinload(GameReview.mistakes),
                selectinload(Replay.review).selectinload(GameReview.goals),
            )
            .filter(Replay.playlist == playlist)
        )
        if date_from is not None:
            query = query.filter(Replay.play_date >= date_from)
        rows = query.order_by(Replay.played_at_utc).all()

        reviewed: list[ReviewedGame] = []
        by_id: dict[str, ReviewedGame] = {}
        for replay, _ in rows:
            review = replay.review
            if review is None or review.status != "ok":
                continue
            game = ReviewedGame(
                replay_id=replay.replay_id,
                play_date=replay.play_date,
                result=replay.result,
                my_score=replay.my_score,
                opponent_score=replay.opponent_score,
                map=replay.map,
                flags=[
                    FlagRow(m.kind, m.category, bool(m.cost_goal))
                    for m in review.mistakes
                ],
                goals=[
                    GoalRow(
                        g.clock,
                        bool(g.ours),
                        bool(g.by_me),
                        bool(g.winner),
                        bool(g.equalizer),
                        g.on_me,
                    )
                    for g in review.goals
                ],
            )
            reviewed.append(game)
            by_id[game.replay_id] = game

        categories = summarize_categories(reviewed)
        highlights = find_highlights(reviewed, categories)
        highlights += _benchmark_strengths(
            session, [s for _, s in rows if s is not None], playlist, rank
        )

        latest_session = None
        if rows:
            latest_date = max(replay.play_date for replay, _ in rows)
            session_rows = [(r, s) for r, s in rows if r.play_date == latest_date]
            latest_session = {
                "play_date": latest_date.isoformat(),
                "wins": sum(1 for r, _ in session_rows if r.result == "WIN"),
                "losses": sum(1 for r, _ in session_rows if r.result == "LOSS"),
                "draws": sum(1 for r, _ in session_rows if r.result == "DRAW"),
                "games": [
                    {
                        "replay_id": r.replay_id,
                        "played_at_utc": r.played_at_utc.isoformat(),
                        "result": r.result,
                        "my_score": r.my_score,
                        "opponent_score": r.opponent_score,
                        "map": r.map,
                        "goals": s.goals if s else None,
                        "assists": s.assists if s else None,
                        "saves": s.saves if s else None,
                        "shots": s.shots if s else None,
                        "reviewed": r.replay_id in by_id,
                        "flags": (
                            len(by_id[r.replay_id].flags)
                            if r.replay_id in by_id
                            else None
                        ),
                        "goals_on_me": (
                            by_id[r.replay_id].goals_on_me
                            if r.replay_id in by_id
                            else None
                        ),
                    }
                    for r, s in reversed(session_rows)
                ],
            }

        return {
            "playlist": playlist,
            "period": period,
            "rank": rank,
            "game_count": len(rows),
            "reviewed_count": len(reviewed),
            "session": latest_session,
            "targets": pick_targets(categories),
            "categories": categories,
            "highlights": highlights,
        }
    finally:
        session.close()


@router.get("/replays/{replay_id}/review")
async def get_replay_review(replay_id: str) -> dict[str, Any]:
    """Your flagged moments and every goal in one game, on the game clock."""
    session = create_session()
    try:
        replay = session.get(Replay, replay_id)
        if replay is None:
            raise HTTPException(status_code=404, detail="Replay not found")
        review = replay.review
        if review is None:
            return {
                "replay_id": replay_id,
                "status": "missing",
                "error": None,
                "clears": 0,
                "clears_given_back": 0,
                "mistakes": [],
                "goals": [],
            }
        return {
            "replay_id": replay_id,
            "status": review.status,
            "error": review.error,
            "clears": review.clears,
            "clears_given_back": review.clears_given_back,
            "mistakes": [
                {
                    "kind": m.kind,
                    "label": m.kind.replace("_", " ").capitalize(),
                    "category": m.category,
                    "category_label": CATEGORIES.get(m.category, m.category),
                    "t": m.t,
                    "seconds_left": m.seconds_left,
                    "clock": m.clock,
                    "score": m.score,
                    "duration": m.duration,
                    "what": m.what,
                    "instead": m.instead,
                    "outcome": m.outcome,
                    "cost_goal": bool(m.cost_goal),
                }
                for m in review.mistakes
            ],
            "goals": [
                {
                    "t": g.t,
                    "seconds_left": g.seconds_left,
                    "clock": g.clock,
                    "score": g.score,
                    "ours": bool(g.ours),
                    "scorer": g.scorer,
                    "by_me": bool(g.by_me),
                    "assist_by_me": bool(g.assist_by_me),
                    "winner": bool(g.winner),
                    "equalizer": bool(g.equalizer),
                    "on_me": g.on_me,
                    "summary": g.summary,
                    "lines": json.loads(g.lines) if g.lines else [],
                }
                for g in review.goals
            ],
        }
    finally:
        session.close()
