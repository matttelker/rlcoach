"""Games and replays API endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ...db.models import Player, PlayerGameStats, Replay
from ...db.session import create_session
from ._sorting import apply_sort

router = APIRouter(tags=["games"])

# Allowlist of sortable fields for security (prevents schema enumeration)
ALLOWED_SORT_FIELDS = {
    "played_at_utc",
    "play_date",
    "playlist",
    "result",
    "duration_seconds",
    "team_size",
    "map",
}


@router.get("/games")
async def list_games(
    playlist: str | None = None,
    result: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="-played_at_utc"),
) -> dict[str, Any]:
    """List games with filtering and pagination.

    Args:
        playlist: Filter by playlist (e.g., DOUBLES, STANDARD)
        result: Filter by result (WIN, LOSS, DRAW)
        date_from: Filter games from this date
        date_to: Filter games up to this date
        limit: Maximum number of games to return
        offset: Number of games to skip
        sort: Sort field (prefix with - for descending)
    """
    session = create_session()
    try:
        query = session.query(Replay)

        # Apply filters
        if playlist:
            query = query.filter(Replay.playlist == playlist)
        if result:
            query = query.filter(Replay.result == result)
        if date_from:
            query = query.filter(Replay.play_date >= date_from)
        if date_to:
            query = query.filter(Replay.play_date <= date_to)

        # Get total count before pagination
        total = query.count()

        query = apply_sort(query, Replay, sort, ALLOWED_SORT_FIELDS)

        # Apply pagination
        replays = query.offset(offset).limit(limit).all()

        items = []
        for r in replays:
            items.append(
                {
                    "replay_id": r.replay_id,
                    "played_at_utc": (
                        r.played_at_utc.isoformat() if r.played_at_utc else None
                    ),
                    "play_date": r.play_date.isoformat() if r.play_date else None,
                    "playlist": r.playlist,
                    "result": r.result,
                    "my_score": r.my_score,
                    "opponent_score": r.opponent_score,
                    "map": r.map,
                    "duration_seconds": r.duration_seconds,
                    "overtime": r.overtime,
                }
            )

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    finally:
        session.close()


@router.get("/replays/{replay_id}")
async def get_replay(replay_id: str) -> dict[str, Any]:
    """Get replay details by ID.

    Args:
        replay_id: The replay ID
    """
    session = create_session()
    try:
        replay = session.get(Replay, replay_id)
        if not replay:
            raise HTTPException(status_code=404, detail="Replay not found")

        # Get player stats
        rows = (
            session.query(PlayerGameStats, Player.display_name)
            .join(Player, Player.player_id == PlayerGameStats.player_id)
            .filter(PlayerGameStats.replay_id == replay_id)
            .all()
        )

        player_stats = []
        for s, display_name in rows:
            player_stats.append(
                {
                    "player_id": s.player_id,
                    "display_name": display_name,
                    "team": s.team,
                    "is_me": s.is_me,
                    "goals": s.goals,
                    "assists": s.assists,
                    "saves": s.saves,
                    "shots": s.shots,
                    "bcpm": s.bcpm,
                    "avg_boost": s.avg_boost,
                }
            )

        return {
            "replay_id": replay.replay_id,
            "played_at_utc": (
                replay.played_at_utc.isoformat() if replay.played_at_utc else None
            ),
            "play_date": replay.play_date.isoformat() if replay.play_date else None,
            "playlist": replay.playlist,
            "result": replay.result,
            "my_score": replay.my_score,
            "opponent_score": replay.opponent_score,
            "map": replay.map,
            "duration_seconds": replay.duration_seconds,
            "overtime": replay.overtime,
            "my_team": replay.my_team,
            "player_stats": player_stats,
        }

    finally:
        session.close()
