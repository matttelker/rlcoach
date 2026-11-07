"""Run the per-player and per-team analyzers whose numbers the database stores."""

from __future__ import annotations

from typing import Any

from ..parser.types import Frame, Header
from .boost import analyze_boost
from .fundamentals import analyze_fundamentals
from .movement import analyze_movement
from .positioning import analyze_positioning


def aggregate_analysis(
    frames: list[Frame], events: dict[str, list[Any]], header: Header | None = None
) -> dict[str, Any]:
    """Analyze every player and both teams.

    Returns:
        {
            "per_team": {"blue": {...}, "orange": {...}},
            "per_player": [{"player_id": "...", "fundamentals": {...}, ...}],
            "warnings": [...],
        }
    """
    warnings = []

    if not frames:
        warnings.append("no_frame_data_available")
    if not events:
        warnings.append("no_events_detected")

    per_team = {
        "blue": _analyze(frames, events, header, team="BLUE"),
        "orange": _analyze(frames, events, header, team="ORANGE"),
    }

    per_player = [
        {
            "player_id": player_id,
            **_analyze(frames, events, header, player_id=player_id),
        }
        for player_id in _extract_players_from_frames(frames)
    ]

    if not frames and events:
        warnings.append("header_only_mode_limited_metrics")

    return {"per_team": per_team, "per_player": per_player, "warnings": warnings}


def _analyze(
    frames: list[Frame],
    events: dict[str, list[Any]],
    header: Header | None,
    **who: str,
) -> dict[str, Any]:
    """Run each analyzer for one team (team=...) or one player (player_id=...)."""
    return {
        "fundamentals": analyze_fundamentals(frames, events, header=header, **who),
        "boost": analyze_boost(frames, events, header=header, **who),
        "movement": analyze_movement(frames, events, header=header, **who),
        "positioning": analyze_positioning(frames, events, header=header, **who),
    }


def _extract_players_from_frames(frames: list[Frame]) -> dict[str, str]:
    """Map each player id to its team name ("BLUE" or "ORANGE")."""
    players = {}

    for frame in frames:
        for player in frame.players:
            if player.player_id not in players:
                players[player.player_id] = "BLUE" if player.team == 0 else "ORANGE"

    return players
