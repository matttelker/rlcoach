"""The people you've played with and against, and tagging your teammates."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session

from ...db.models import Player, PlayerGameStats
from ...db.session import create_session
from .sort import sort_by

router = APIRouter(tags=["players"])


class TagRequest(BaseModel):
    tagged: bool = True
    notes: str | None = None  # Left as it was when not given


def _games_each(session: Session) -> Any:
    """How many stored games each player is in, counted fresh each time."""
    return (
        session.query(
            PlayerGameStats.player_id.label("player_id"),
            func.count(distinct(PlayerGameStats.replay_id)).label("games"),
        )
        .group_by(PlayerGameStats.player_id)
        .subquery()
    )


def _player(player: Player, games: int) -> dict[str, Any]:
    return {
        "player_id": player.player_id,
        "display_name": player.display_name,
        "platform": player.platform,
        "is_me": player.is_me,
        "is_tagged_teammate": player.is_tagged_teammate,
        "teammate_notes": player.teammate_notes,
        "games_with_me": 0 if player.is_me else games,
        "first_seen_utc": (
            player.first_seen_utc.isoformat() if player.first_seen_utc else None
        ),
        "last_seen_utc": (
            player.last_seen_utc.isoformat() if player.last_seen_utc else None
        ),
    }


@router.get("/players")
async def list_players(
    tagged: bool | None = None,
    min_games: int = Query(default=0),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="-games_with_me"),
) -> dict[str, Any]:
    """Everyone but you, most games together first unless `sort` says otherwise."""
    with create_session() as session:
        counts = _games_each(session)
        games = func.coalesce(counts.c.games, 0)
        query = (
            session.query(Player, games)
            .outerjoin(counts, counts.c.player_id == Player.player_id)
            .filter(Player.is_me.is_(False))
        )
        if tagged is not None:
            query = query.filter(Player.is_tagged_teammate == tagged)
        if min_games > 0:
            query = query.filter(games >= min_games)
        total = query.count()
        columns = {
            "display_name": Player.display_name,
            "platform": Player.platform,
            "games_with_me": games,
            "first_seen_utc": Player.first_seen_utc,
            "last_seen_utc": Player.last_seen_utc,
            "is_tagged_teammate": Player.is_tagged_teammate,
        }
        rows = sort_by(query, sort, columns).offset(offset).limit(limit).all()
        return {
            "items": [_player(player, n) for player, n in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }


@router.get("/players/{player_id}")
async def get_player(player_id: str) -> dict[str, Any]:
    with create_session() as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        games = (
            session.query(func.count(distinct(PlayerGameStats.replay_id)))
            .filter(PlayerGameStats.player_id == player_id)
            .scalar()
        )
        return _player(player, games or 0)


@router.post("/players/{player_id}/tag")
async def tag_player(player_id: str, request: TagRequest) -> dict[str, Any]:
    """Tag or untag someone as your teammate, with notes if you like."""
    with create_session() as session:
        player = session.get(Player, player_id)
        if player is None:
            raise HTTPException(status_code=404, detail="Player not found")
        player.is_tagged_teammate = request.tagged
        if request.notes is not None:
            player.teammate_notes = request.notes
        session.commit()
        return {
            "player_id": player.player_id,
            "display_name": player.display_name,
            "is_tagged_teammate": player.is_tagged_teammate,
            "teammate_notes": player.teammate_notes,
        }
