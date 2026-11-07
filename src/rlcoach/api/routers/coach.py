"""Coaching endpoints: training targets, highlights and per-game reviews."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import and_
from sqlalchemy.orm import selectinload

from ...analysis.mistakes import CATEGORIES
from ...coaching import (
    FlagRow,
    GoalRow,
    ReviewedGame,
    find_highlights,
    pick_targets,
    summarize_categories,
)
from ...compare import standings
from ...db.grades import goal_ref, grades_for, mistake_ref
from ...db.models import Benchmark, GameReview, PlayerGameStats, Replay
from ...db.session import create_session
from ...modes import COACHED_PLAYLISTS
from .stats import direction, resolve_playlist

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


def _latest_playlist(session) -> str | None:
    """The playlist of your most recent game, skipping ones like Hoops."""
    latest = (
        session.query(Replay.playlist)
        .filter(Replay.playlist.in_(COACHED_PLAYLISTS))
        .order_by(Replay.played_at_utc.desc())
        .first()
    )
    return latest.playlist if latest else None


def _playlists(value: str) -> list[str]:
    """One playlist, or several joined by commas such as "DOUBLES,STANDARD"."""
    names = dict.fromkeys(p.strip().upper() for p in value.split(",") if p.strip())
    if not names:
        raise HTTPException(status_code=400, detail="playlist is empty")
    return list(names)


def _benchmark_strengths(
    session,
    stats: list[PlayerGameStats],
    playlist: str,
    rank,
    *,
    say_playlist: bool = False,
):
    """Stats where your average beats the target rank's spread.

    Benchmarks are per playlist, so a view of several playlists compares each
    one on its own and names it.
    """
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
            "direction": direction(b.metric),
        }
        for b in session.query(Benchmark)
        .filter(Benchmark.playlist == playlist, Benchmark.rank_tier == rank)
        .all()
        if b.metric in STRENGTH_METRICS
    }
    results = standings(averages, benchmarks)
    return [
        {
            "kind": "benchmark",
            "title": f"More {r.metric} than {rank} players"
            + (f" in {playlist.capitalize()}" if say_playlist else ""),
            "detail": (f"{r.my_value:.1f} a game, {rank} average {r.median:.1f}"),
            "replay_id": None,
        }
        for r in sorted(results, key=lambda r: -r.z_score)
        if r.severity == "strength"
    ]


@router.get("/coach")
async def get_coach(
    playlist: str | None = None,
    period: str = Query(default="30d", description="7d, 30d, 90d or all"),
) -> dict[str, Any]:
    """Training targets, mistakes by category, the latest session and highlights.

    Without a playlist it shows the one you played last, so a new session shows
    up whichever playlist it's in. List several, such as "DOUBLES,STANDARD", to
    see them together.
    """
    date_from = _date_from(period)
    rank = _target_rank()

    session = create_session()
    try:
        playlists = _playlists(resolve_playlist(playlist or _latest_playlist(session)))
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
            .filter(Replay.playlist.in_(playlists))
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
        stats_by_playlist: dict[str, list[PlayerGameStats]] = defaultdict(list)
        for replay, stats in rows:
            if stats is not None:
                stats_by_playlist[replay.playlist].append(stats)
        for name in playlists:
            highlights += _benchmark_strengths(
                session,
                stats_by_playlist[name],
                name,
                rank,
                say_playlist=len(playlists) > 1,
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
                        "playlist": r.playlist,
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
            "playlist": ",".join(playlists),
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
        grades = grades_for(session, replay_id)
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
                    "grade": grades.get(("mistake", mistake_ref(m.kind, m.t))),
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
                    "grade": (None if g.ours else grades.get(("goal", goal_ref(g.t)))),
                }
                for g in review.goals
            ],
        }
    finally:
        session.close()
