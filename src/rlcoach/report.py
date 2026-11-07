"""Analyze one replay end to end.

Runs the analyzers over a loaded game and returns the result as a dict that
the database writer stores. Nothing is written to disk.
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any

from .analysis import aggregate_analysis
from .config import IdentityConfig
from .events import KickoffEvent
from .game import Game, read_game
from .identity import Me, build_player_identities
from .modes import playlist_of
from .normalize import measure_frame_rate
from .replay_file import file_hash


def _utc_now_iso() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _went_to_overtime(header: Any, kickoffs: list[KickoffEvent]) -> bool:
    """Tell if the match went to overtime.

    Current replay headers carry no overtime flag, so the overtime kickoff decides.
    An older header that does say so still counts.
    """
    return bool(getattr(header, "overtime", None)) or any(
        kickoff.phase == "OT" for kickoff in kickoffs
    )


def generate_report(
    replay_path: Path, *, identity_config: IdentityConfig | None = None
) -> dict[str, Any]:
    """Read a replay and report on it. See report_for."""
    game = read_game(replay_path)
    return report_for(game, file_hash(replay_path), identity_config=identity_config)


def report_for(
    game: Game,
    replay_id: str,
    *,
    identity_config: IdentityConfig | None = None,
) -> dict[str, Any]:
    """Report one loaded game: what it was, who played, and each player's stats.

    A player the frames never show still gets an entry in "players", with no
    stats in "analysis".
    """
    header, frames = game.header, game.frames
    analysis = aggregate_analysis(frames, game.events, header)
    me = Me(identity_config) if identity_config is not None else None

    players = []
    team_players: dict[str, list[str]] = {"BLUE": [], "ORANGE": []}
    for identity in build_player_identities(header.players):
        team_players[identity.team].append(identity.canonical_id)
        player = {
            "player_id": identity.canonical_id,
            "display_name": identity.display_name,
            "team": identity.team,
        }
        if me is not None:
            player["is_me"] = me.is_me(identity.canonical_id, identity.display_name)
        players.append(player)

    return {
        "replay_id": replay_id,
        "source_file": str(game.path),
        "metadata": {
            "playlist": playlist_of(header),
            "map": header.map_name or "unknown",
            "team_size": max(1, int(header.team_size or 1)),
            "overtime": _went_to_overtime(header, game.kickoffs),
            "started_at_utc": header.started_at_utc or _utc_now_iso(),
            # Frames start at 0, so the last one's time is the recording's length
            "duration_seconds": float(frames[-1].timestamp if frames else 0.0),
            "recorded_frame_hz": float(measure_frame_rate(frames)),
            "total_frames": len(frames),
        },
        "teams": {
            "blue": {
                "score": int(header.team0_score or 0),
                "players": team_players["BLUE"],
            },
            "orange": {
                "score": int(header.team1_score or 0),
                "players": team_players["ORANGE"],
            },
        },
        "players": players,
        "analysis": {
            "per_team": analysis["per_team"],
            "per_player": {str(p["player_id"]): p for p in analysis["per_player"]},
        },
    }
