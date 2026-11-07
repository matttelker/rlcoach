"""Your games: the list, and one game with everyone's stats."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from ...db.models import Player, PlayerGameStats, Replay
from ...db.session import create_session
from .sort import sort_by

router = APIRouter(tags=["games"])

SORTS = {
    name: getattr(Replay, name)
    for name in (
        "played_at_utc",
        "play_date",
        "playlist",
        "result",
        "duration_seconds",
        "team_size",
        "map",
    )
}


def _summary(replay: Replay) -> dict[str, Any]:
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
    """Your games, newest first unless `sort` says otherwise."""
    with create_session() as session:
        query = session.query(Replay)
        if playlist:
            query = query.filter(Replay.playlist == playlist)
        if result:
            query = query.filter(Replay.result == result)
        if date_from:
            query = query.filter(Replay.play_date >= date_from)
        if date_to:
            query = query.filter(Replay.play_date <= date_to)
        total = query.count()
        page = sort_by(query, sort, SORTS).offset(offset).limit(limit).all()
        return {
            "items": [_summary(replay) for replay in page],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/replays/{replay_id}")
async def get_replay(replay_id: str) -> dict[str, Any]:
    """One game, with each player's main stats."""
    with create_session() as session:
        replay = session.get(Replay, replay_id)
        if replay is None:
            raise HTTPException(status_code=404, detail="Replay not found")
        rows = (
            session.query(PlayerGameStats, Player.display_name)
            .join(Player, Player.player_id == PlayerGameStats.player_id)
            .filter(PlayerGameStats.replay_id == replay_id)
            .all()
        )
        return {
            **_summary(replay),
            "my_team": replay.my_team,
            "player_stats": [
                {
                    "player_id": stats.player_id,
                    "display_name": name,
                    "team": stats.team,
                    "is_me": stats.is_me,
                    "goals": stats.goals,
                    "assists": stats.assists,
                    "saves": stats.saves,
                    "shots": stats.shots,
                    "bcpm": stats.bcpm,
                    "avg_boost": stats.avg_boost,
                }
                for stats, name in rows
            ],
        }
