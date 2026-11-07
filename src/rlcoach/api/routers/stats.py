"""Your stats over time and against benchmarks, for the Trends, Compare and
Benchmarks pages."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from ...compare import SEVERITY_ORDER, standings, win_loss_patterns
from ...db.models import Benchmark, PlayerGameStats, Replay
from ...db.session import create_session
from ...metrics import MetricDirection, metric_direction

router = APIRouter(tags=["stats"])

TREND_METRICS = (
    "bcpm",
    "avg_boost",
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
)
# The stats that have benchmarks
COMPARED_METRICS = ("bcpm", "avg_boost", "goals", "assists", "saves", "shots")
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


def direction(metric: str) -> str:
    """Which way is better for a stat: "lower" or "higher"."""
    if metric_direction(metric) is MetricDirection.LOWER_BETTER:
        return MetricDirection.LOWER_BETTER.value
    return MetricDirection.HIGHER_BETTER.value


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


def _benchmarks(session: Session, playlist: str, rank: str) -> list[Benchmark]:
    return (
        session.query(Benchmark)
        .filter(Benchmark.playlist == playlist, Benchmark.rank_tier == rank)
        .all()
    )


@router.get("/trends")
async def get_trends(
    metric: str = Query(..., description="Stat to trend, such as bcpm or goals"),
    period: str = Query(default="30d", description="7d, 30d, 90d or all"),
    playlist: str | None = None,
) -> dict[str, Any]:
    """One stat of yours game by game, oldest first."""
    if metric not in TREND_METRICS:
        raise HTTPException(
            status_code=400, detail=f"Invalid metric. Allowed: {sorted(TREND_METRICS)}"
        )
    if period not in TREND_PERIODS:
        raise HTTPException(
            status_code=400, detail=f"Invalid period. Allowed: {sorted(TREND_PERIODS)}"
        )
    playlist = resolve_playlist(playlist)
    with create_session() as session:
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
        "values": [
            {"date": day.isoformat() if day else None, "value": value}
            for day, value in rows
            if value is not None
        ],
    }


@router.get("/benchmarks")
async def list_benchmarks(
    metric: str | None = None, playlist: str | None = None, rank: str | None = None
) -> dict[str, Any]:
    """The bundled rank benchmarks, filtered by any of stat, playlist and rank."""
    with create_session() as session:
        query = session.query(Benchmark)
        if metric:
            query = query.filter(Benchmark.metric == metric)
        if playlist:
            query = query.filter(Benchmark.playlist == playlist)
        if rank:
            query = query.filter(Benchmark.rank_tier == rank)
        rows = query.order_by(Benchmark.metric, Benchmark.rank_tier).all()
    return {
        "items": [
            {
                "metric": b.metric,
                "playlist": b.playlist,
                "rank_tier": b.rank_tier,
                "median_value": b.median_value,
                "p25_value": b.p25_value,
                "p75_value": b.p75_value,
                "elite_threshold": b.elite_threshold,
                "source": b.source,
            }
            for b in rows
        ]
    }


@router.get("/compare")
async def get_comparison(
    rank: str = Query(..., description="Rank to compare with, such as GC1"),
    playlist: str | None = None,
    period: str = Query(default="30d"),
) -> dict[str, Any]:
    """Your averages next to a rank's medians."""
    playlist = resolve_playlist(playlist)
    with create_session() as session:
        rows = _my_stats(session, playlist, period).all()
        if not rows:
            return {
                "target_rank": rank,
                "playlist": playlist,
                "comparisons": [],
                "game_count": 0,
            }
        medians = {
            b.metric: b.median_value for b in _benchmarks(session, playlist, rank)
        }
    comparisons = []
    for metric, mine in _averages(rows, COMPARED_METRICS).items():
        median = medians.get(metric)
        gap = None if median is None else mine - median
        comparisons.append(
            {
                "metric": metric,
                "my_value": round(mine, 2),
                "target_median": median,
                "difference": None if gap is None else round(gap, 2),
                "difference_pct": (
                    None
                    if gap is None
                    else round(gap / median * 100 if median else 0, 1)
                ),
                "direction": direction(metric),
            }
        )
    return {
        "target_rank": rank,
        "playlist": playlist,
        "comparisons": comparisons,
        "game_count": len(rows),
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


@router.get("/weaknesses")
async def get_weaknesses(
    playlist: str | None = None,
    rank: str = Query(default="GC1"),
    period: str = Query(default="30d"),
) -> dict[str, Any]:
    """Your stats furthest below a rank's spread, and the ones well above it."""
    playlist = resolve_playlist(playlist)
    with create_session() as session:
        rows = _my_stats(session, playlist, period).all()
        if not rows:
            return {
                "weaknesses": [],
                "strengths": [],
                "game_count": 0,
                "playlist": playlist,
                "has_benchmarks": False,
            }
        benchmarks = _benchmarks(session, playlist, rank)
    spreads = {
        b.metric: {
            "p25": b.p25_value,
            "median": b.median_value,
            "p75": b.p75_value,
            "direction": direction(b.metric),
        }
        for b in benchmarks
    }
    items = [
        {
            "metric": s.metric,
            "my_value": round(s.my_value, 2),
            "target_median": round(s.median, 2),
            "z_score": round(s.z_score, 2),
            "severity": s.severity,
        }
        for s in standings(_averages(rows, COMPARED_METRICS), spreads)
    ]
    weaknesses = [i for i in items if i["severity"] not in ("strength", "neutral")]
    return {
        "weaknesses": sorted(
            weaknesses,
            key=lambda i: (-abs(i["z_score"]), SEVERITY_ORDER.index(i["severity"])),
        ),
        "strengths": sorted(
            (i for i in items if i["severity"] == "strength"),
            key=lambda i: -i["z_score"],
        ),
        "game_count": len(rows),
        "playlist": playlist,
        "has_benchmarks": bool(benchmarks),
    }
