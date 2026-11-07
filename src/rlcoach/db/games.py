"""Store one game: the replay seen from your side, its players and their stats.

A game goes in as one transaction, so a failure leaves none of it behind.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..config import RLCoachConfig, compute_play_date
from ..identity import Me
from .models import Player, PlayerGameStats, Replay
from .session import create_session

# Stats columns, and where each comes from in a report's per-player analysis
STAT_SOURCES = {
    "goals": ("fundamentals", "goals"),
    "assists": ("fundamentals", "assists"),
    "saves": ("fundamentals", "saves"),
    "shots": ("fundamentals", "shots"),
    "shooting_pct": ("fundamentals", "shooting_percentage"),
    "score": ("fundamentals", "score"),
    "demos_inflicted": ("fundamentals", "demos_inflicted"),
    "demos_taken": ("fundamentals", "demos_taken"),
    "bcpm": ("boost", "bpm"),
    "avg_boost": ("boost", "avg_boost"),
    "time_zero_boost_s": ("boost", "time_zero_boost_s"),
    "time_full_boost_s": ("boost", "time_full_boost_s"),
    "boost_collected": ("boost", "boost_collected"),
    "boost_stolen": ("boost", "boost_stolen"),
    "avg_speed_kph": ("movement", "avg_speed_kph"),
    "time_supersonic_s": ("movement", "time_supersonic_s"),
    "behind_ball_pct": ("positioning", "behind_ball_pct"),
    "first_man_pct": ("positioning", "first_man_pct"),
    "second_man_pct": ("positioning", "second_man_pct"),
    "third_man_pct": ("positioning", "third_man_pct"),
}


class ReplayExistsError(Exception):
    """The replay is already stored."""


def _as_utc(value: datetime) -> datetime:
    """SQLite hands datetimes back without their zone, which is always UTC."""
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _stored(session: Session, replay_id: str, file_hash: str) -> bool:
    match = or_(Replay.replay_id == replay_id, Replay.file_hash == file_hash)
    return session.query(Replay.replay_id).filter(match).first() is not None


def is_stored(file_hash: str) -> bool:
    """Whether a replay file is in the database, by its hash, which is its id."""
    with create_session() as session:
        return _stored(session, file_hash, file_hash)


def played_at(report: dict[str, Any]) -> datetime:
    """When the game was played, or now if the replay doesn't say."""
    started = report["metadata"].get("started_at_utc")
    if not started:
        return datetime.now(UTC)
    return datetime.fromisoformat(started.replace("Z", "+00:00"))


def _see_player(
    session: Session, me: Me, player: dict[str, Any], seen_at: datetime
) -> None:
    """Add a player, or widen when they were seen to include this game.

    Games can load in any order, so the name kept is the one from their most
    recently played game.
    """
    stored = session.get(Player, player["player_id"])
    if stored is None:
        player_id = player["player_id"]
        session.add(
            Player(
                player_id=player_id,
                display_name=player["display_name"],
                platform=player_id.split(":")[0] if ":" in player_id else None,
                is_me=me.is_me(player_id, player["display_name"]),
                first_seen_utc=seen_at,
                last_seen_utc=seen_at,
            )
        )
        return
    first, last = stored.first_seen_utc, stored.last_seen_utc
    if last is None or seen_at >= _as_utc(last):
        stored.display_name = player["display_name"]
    stored.first_seen_utc = min(_as_utc(first), seen_at) if first else seen_at
    stored.last_seen_utc = max(_as_utc(last), seen_at) if last else seen_at


def _result(mine: int, theirs: int) -> str:
    return "WIN" if mine > theirs else "LOSS" if mine < theirs else "DRAW"


def store_game(
    report: dict[str, Any], file_hash: str, my_player_id: str, config: RLCoachConfig
) -> str:
    """Store a report from report.report_for, and return the replay's id.

    Raises ReplayExistsError if it's already stored.
    """
    replay_id = report["replay_id"]
    metadata, players = report["metadata"], report["players"]
    analysis = report["analysis"]["per_player"]
    my_team = next(p["team"] for p in players if p["player_id"] == my_player_id)
    scores = {"BLUE": report["teams"]["blue"], "ORANGE": report["teams"]["orange"]}
    mine = scores[my_team]["score"]
    theirs = scores["ORANGE" if my_team == "BLUE" else "BLUE"]["score"]
    seen_at = played_at(report)
    me = Me(config.identity)

    with create_session() as session, session.begin():
        if _stored(session, replay_id, file_hash):
            raise ReplayExistsError(f"Replay {replay_id} is already stored")
        for player in players:
            _see_player(session, me, player, seen_at)
        session.add(
            Replay(
                replay_id=replay_id,
                source_file=report["source_file"],
                file_hash=file_hash,
                played_at_utc=seen_at,
                play_date=compute_play_date(seen_at, config.preferences.timezone),
                map=metadata["map"],
                playlist=metadata["playlist"],
                team_size=metadata["team_size"],
                duration_seconds=metadata["duration_seconds"],
                overtime=metadata["overtime"],
                my_player_id=my_player_id,
                my_team=my_team,
                my_score=mine,
                opponent_score=theirs,
                result=_result(mine, theirs),
            )
        )
        # Players must exist before stats that point at them
        session.flush()
        for player in players:
            numbers = analysis.get(player["player_id"], {})
            session.add(
                PlayerGameStats(
                    replay_id=replay_id,
                    player_id=player["player_id"],
                    team=player["team"],
                    is_me=player["player_id"] == my_player_id,
                    **{
                        column: numbers.get(section, {}).get(key)
                        for column, (section, key) in STAT_SOURCES.items()
                    },
                )
            )
    return replay_id
