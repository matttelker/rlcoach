"""Dashboard API endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter

from ...db.models import DailyStats, PlayerGameStats, Replay
from ...db.session import create_session

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
async def get_dashboard() -> dict[str, Any]:
    """Get dashboard summary data.

    Returns today's stats, recent games, and quick stats.
    """
    today = date.today()

    session = create_session()
    try:
        # Get today's stats across every playlist
        daily_rows = session.query(DailyStats).filter_by(play_date=today).all()

        games_played = sum(d.games_played or 0 for d in daily_rows)
        wins = sum(d.wins or 0 for d in daily_rows)
        today_stats = {
            "games_played": games_played,
            "wins": wins,
            "losses": sum(d.losses or 0 for d in daily_rows),
            "draws": sum(d.draws or 0 for d in daily_rows),
            "win_rate": (wins / games_played * 100) if games_played else None,
        }

        # Get recent games (last 10)
        recent_replays = (
            session.query(Replay).order_by(Replay.played_at_utc.desc()).limit(10).all()
        )

        recent_games = []
        for r in recent_replays:
            recent_games.append(
                {
                    "replay_id": r.replay_id,
                    "played_at_utc": (
                        r.played_at_utc.isoformat() if r.played_at_utc else None
                    ),
                    "playlist": r.playlist,
                    "result": r.result,
                    "my_score": r.my_score,
                    "opponent_score": r.opponent_score,
                    "map": r.map,
                }
            )

        # Quick stats (last 7 days average)
        quick_stats = {
            "avg_goals": 0.0,
            "avg_saves": 0.0,
            "avg_assists": 0.0,
            "avg_bcpm": None,
        }

        # Get average stats from recent games
        if recent_replays:
            replay_ids = [r.replay_id for r in recent_replays]
            my_stats = (
                session.query(PlayerGameStats)
                .filter(
                    PlayerGameStats.replay_id.in_(replay_ids),
                    PlayerGameStats.is_me,
                )
                .all()
            )

            if my_stats:
                quick_stats["avg_goals"] = sum(s.goals or 0 for s in my_stats) / len(
                    my_stats
                )
                quick_stats["avg_saves"] = sum(s.saves or 0 for s in my_stats) / len(
                    my_stats
                )
                quick_stats["avg_assists"] = sum(
                    s.assists or 0 for s in my_stats
                ) / len(my_stats)

                bcpm_values = [s.bcpm for s in my_stats if s.bcpm is not None]
                if bcpm_values:
                    quick_stats["avg_bcpm"] = sum(bcpm_values) / len(bcpm_values)

        return {
            "today": today_stats,
            "recent_games": recent_games,
            "quick_stats": quick_stats,
        }

    finally:
        session.close()
