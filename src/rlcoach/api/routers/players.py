"""Players API endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import distinct, func

from ...db.models import Player, PlayerGameStats
from ...db.session import create_session
from ._sorting import apply_sort

router = APIRouter(tags=["players"])

# Allowlist of sortable fields for security (prevents schema enumeration)
ALLOWED_SORT_FIELDS = {
    "display_name",
    "platform",
    "games_with_me",
    "first_seen_utc",
    "last_seen_utc",
    "is_tagged_teammate",
}


class TagRequest(BaseModel):
    """Request body for tagging a player."""

    tagged: bool = True
    notes: str | None = None


def _games_per_player(session):
    """Count the stored games each player appears in, as a subquery.

    Counting stored games, rather than keeping a running total at ingest, stays
    right when an ingest fails partway or a replay is loaded again.
    """
    return (
        session.query(
            PlayerGameStats.player_id.label("player_id"),
            func.count(distinct(PlayerGameStats.replay_id)).label("games"),
        )
        .group_by(PlayerGameStats.player_id)
        .subquery()
    )


def _player_dict(player: Player, games: int) -> dict[str, Any]:
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
    """List players (excluding self).

    Args:
        tagged: Filter by tagged status
        min_games: Minimum games played with me
        limit: Maximum number of players to return
        offset: Number of players to skip
        sort: Sort field (prefix with - for descending)
    """
    session = create_session()
    try:
        counts = _games_per_player(session)
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

        query = apply_sort(
            query,
            Player,
            sort,
            ALLOWED_SORT_FIELDS,
            computed={"games_with_me": games},
        )

        rows = query.offset(offset).limit(limit).all()

        return {
            "items": [_player_dict(player, count) for player, count in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    finally:
        session.close()


@router.get("/players/{player_id}")
async def get_player(player_id: str) -> dict[str, Any]:
    """Get player details by ID.

    Args:
        player_id: The player ID (e.g., steam:123456)
    """
    session = create_session()
    try:
        player = session.get(Player, player_id)
        if not player:
            raise HTTPException(status_code=404, detail="Player not found")

        games = (
            session.query(func.count(distinct(PlayerGameStats.replay_id)))
            .filter(PlayerGameStats.player_id == player_id)
            .scalar()
        )
        return _player_dict(player, games or 0)

    finally:
        session.close()


@router.post("/players/{player_id}/tag")
async def tag_player(player_id: str, request: TagRequest) -> dict[str, Any]:
    """Tag or untag a player as a teammate.

    Args:
        player_id: The player ID
        request: Tag request with notes
    """
    session = create_session()
    try:
        player = session.get(Player, player_id)
        if not player:
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

    finally:
        session.close()
