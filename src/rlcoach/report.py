"""One loaded game as the database stores it: what it was, who played, their stats."""

from __future__ import annotations

import datetime as _dt
from typing import Any

from .analysis import player_stats
from .game import Game
from .identity import build_player_identities
from .modes import playlist_of


def _utc_now_iso() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _went_to_overtime(game: Game) -> bool:
    """Tell if the match went to overtime: the game said so in its frames, or
    failing that it had an overtime kickoff.

    Replay headers carry no overtime flag.
    """
    return any(frame.overtime for frame in game.frames) or any(
        kickoff.phase == "OT" for kickoff in game.kickoffs
    )


def report_for(game: Game, replay_id: str) -> dict[str, Any]:
    """Report one loaded game: what it was, who played, and each player's stats.

    A player the frames never show still gets an entry in "players", and no stats.
    """
    header = game.header
    players = [
        {
            "player_id": identity.canonical_id,
            "display_name": identity.display_name,
            "team": identity.team,
        }
        for identity in build_player_identities(header.players)
    ]
    return {
        "replay_id": replay_id,
        "source_file": str(game.path),
        "metadata": {
            "playlist": playlist_of(header, game.playlist_id),
            "map": header.map_name or "unknown",
            "team_size": max(1, int(header.team_size or 1)),
            "overtime": _went_to_overtime(game),
            "started_at_utc": header.started_at_utc or _utc_now_iso(),
            # Frames start at 0, so the last one's time is the recording's length
            "duration_seconds": float(game.frames[-1].timestamp),
        },
        "score": {"BLUE": int(header.team0_score), "ORANGE": int(header.team1_score)},
        "players": players,
        "stats": player_stats(game, [p["player_id"] for p in players]),
    }
