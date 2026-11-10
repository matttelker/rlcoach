"""Your stats over time and against the ranks, for the Trends and Compare
pages."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from ...compare import (
    MIN_GAMES,
    RANK_STATS,
    in_our_units,
    place,
    win_loss_patterns,
)
from ...config import DEFAULT_RANK
from ...db.models import Benchmark, PlayerGameStats, Replay
from ...db.session import create_session

router = APIRouter(tags=["stats"])

TREND_METRICS = (
    "bcpm",
    "avg_boost",
    "time_zero_boost_s",
    "boost_stolen",
    "goals",
    "assists",
    "saves",
    "shots",
    "score",
    "avg_speed_kph",
    "time_supersonic_s",
    "behind_ball_pct",
    "demos_inflicted",
    "demos_taken",
    "epic_saves",
    "clears",
    "centers",
    "aerial_hits",
)
# The stats that have benchmarks
COMPARED_METRICS = ("bcpm", "avg_boost", "goals", "assists", "saves", "shots")
# The ones that don't rise with rank, shown beside the rank's average and no more
CONTEXT_METRICS = tuple(m for m in COMPARED_METRICS if m not in RANK_STATS)
TREND_PERIODS = ("7d", "30d", "90d", "all")


def resolve_playlist(playlist: str | None) -> str:
    """The playlist asked for, or the one your config opens on."""
    if playlist:
        return playlist
    from ..app import get_config

    try:
        return get_config().preferences.primary_playlist
    except RuntimeError:
        return "DOUBLES"


def resolve_rank(rank: str | None) -> str:
    """The rank asked for, or the one your config compares you with."""
    if rank:
        return rank
    from ..app import get_config

    try:
        return get_config().preferences.target_rank
    except RuntimeError:
        return DEFAULT_RANK


def _since(period: str) -> date | None:
    """The first day of a period like "30d", or None for "all"."""
    if period == "all":
        return None
    try:
        return date.today() - timedelta(days=int(period.removesuffix("d")))
    except ValueError:
        raise HTTPException(
            status_code=400, detail="period must be 'all' or a number of days like 30d"
        ) from None


def _my_stats(session: Session, playlist: str, period: str) -> Any:
    """Your stats rows in one playlist over a period, as a query."""
    query = (
        session.query(PlayerGameStats)
        .join(Replay, Replay.replay_id == PlayerGameStats.replay_id)
        .filter(PlayerGameStats.is_me)
        .filter(Replay.playlist == playlist)
    )
    since = _since(period)
    return query if since is None else query.filter(Replay.play_date >= since)


def _averages(rows: list[PlayerGameStats], metrics: tuple[str, ...]) -> dict:
    """Each stat's average over the games that have it."""
    averages = {}
    for metric in metrics:
        values = [getattr(r, metric) for r in rows if getattr(r, metric) is not None]
        if values:
            averages[metric] = sum(values) / len(values)
    return averages


def rank_averages(session: Session, playlist: str) -> dict[str, dict[str, float]]:
    """Each benchmarked stat's average at every rank, in one playlist.

    The benchmark table calls it a median, but Ballchasing publishes each
    rank's average.
    """
    averages: dict[str, dict[str, float]] = {}
    for b in session.query(Benchmark).filter(Benchmark.playlist == playlist):
        averages.setdefault(b.metric, {})[b.rank_tier] = b.median_value
    return averages


def _values(rows: list[PlayerGameStats], metric: str) -> list[float]:
    return [getattr(r, metric) for r in rows if getattr(r, metric) is not None]


@router.get("/trends")
async def get_trends(
    metric: str = Query(..., description="Stat to trend, such as bcpm or goals"),
    period: str = Query(default="30d", description="7d, 30d, 90d or all"),
    playlist: str | None = None,
) -> dict[str, Any]:
    """One stat of yours game by game, oldest first, and the target rank's
    average in the same units as yours."""
    if metric not in TREND_METRICS:
        raise HTTPException(
            status_code=400, detail=f"Invalid metric. Allowed: {sorted(TREND_METRICS)}"
        )
    if period not in TREND_PERIODS:
        raise HTTPException(
            status_code=400, detail=f"Invalid period. Allowed: {sorted(TREND_PERIODS)}"
        )
    playlist = resolve_playlist(playlist)
    rank = resolve_rank(None)
    with create_session() as session:
        benchmark = (
            session.query(Benchmark)
            .filter_by(metric=metric, playlist=playlist, rank_tier=rank)
            .first()
        )
        query = (
            session.query(Replay.play_date, getattr(PlayerGameStats, metric))
            .join(PlayerGameStats, Replay.replay_id == PlayerGameStats.replay_id)
            .filter(PlayerGameStats.is_me.is_(True))
            .filter(Replay.playlist == playlist)
        )
        since = _since(period)
        if since is not None:
            query = query.filter(Replay.play_date >= since)
        rows = query.order_by(Replay.play_date, Replay.played_at_utc).all()
    return {
        "metric": metric,
        "period": period,
        "playlist": playlist,
        "rank": rank,
        "rank_average": (
            in_our_units(metric, benchmark.median_value) if benchmark else None
        ),
        "values": [
            {"date": day.isoformat() if day else None, "value": value}
            for day, value in rows
            if value is not None
        ],
    }


@router.get("/compare")
async def get_comparison(
    rank: str | None = Query(default=None, description="Such as P1. Default: config"),
    playlist: str | None = None,
    period: str = Query(default="30d"),
) -> dict[str, Any]:
    """Where your stats sit among the ranks.

    `placements` are the stats that rise with rank, each with the span of ranks
    your average sits among and whether the gap to the target is more than
    chance. `context` are the benchmarked stats that don't separate ranks.
    """
    playlist = resolve_playlist(playlist)
    rank = resolve_rank(rank)
    with create_session() as session:
        rows = _my_stats(session, playlist, period).all()
        averages = rank_averages(session, playlist)
    placements = []
    for metric in RANK_STATS:
        placed = place(metric, _values(rows, metric), averages.get(metric, {}), rank)
        if placed is None:
            continue
        placements.append(
            {
                "metric": metric,
                "games": placed.games,
                "my_value": round(placed.my_value, 2),
                "target_average": round(placed.target_average, 2),
                "gap": round(placed.gap, 2),
                "margin": None if placed.margin is None else round(placed.margin, 2),
                "verdict": placed.verdict,
                "level_low": placed.level_low,
                "level_high": placed.level_high,
                "scaled": placed.scaled,
            }
        )
    context = []
    for metric in CONTEXT_METRICS:
        values = _values(rows, metric)
        target = averages.get(metric, {}).get(rank)
        if values and target is not None:
            context.append(
                {
                    "metric": metric,
                    "my_value": round(sum(values) / len(values), 2),
                    "target_average": round(in_our_units(metric, target), 2),
                }
            )
    return {
        "target_rank": rank,
        "playlist": playlist,
        "game_count": len(rows),
        "min_games": MIN_GAMES,
        "placements": placements,
        "context": context,
    }


@router.get("/patterns")
async def get_patterns(
    playlist: str | None = None,
    period: str = Query(default="30d"),
    min_games: int = Query(default=5),
) -> dict[str, Any]:
    """Stats that clearly differ between your wins and losses (Cohen's d)."""
    playlist = resolve_playlist(playlist)
    with create_session() as session:
        rows = _my_stats(session, playlist, period).add_columns(Replay.result).all()
    games = {"WIN": [], "LOSS": []}
    for stats, result in rows:
        if result in games:
            games[result].append({m: getattr(stats, m) for m in COMPARED_METRICS})
    found = win_loss_patterns(
        games["WIN"], games["LOSS"], COMPARED_METRICS, min_games=min_games
    )
    return {
        "patterns": [
            {
                "metric": p.metric,
                "win_avg": round(p.win_avg, 2),
                "loss_avg": round(p.loss_avg, 2),
                "delta": round(p.delta, 2),
                "effect_size": round(p.effect_size, 3),
                "direction": p.direction,
            }
            for p in found
        ],
        "playlist": playlist,
        "win_count": len(games["WIN"]),
        "loss_count": len(games["LOSS"]),
        "min_games": min_games,
    }
