"""Positioning: the share of the frames a player is in, out of 100, that they
are behind the ball: more than 50 uu nearer their own goal than the ball.

Who is last back at the moments that matter is the review's job
(`analysis/situations.py`). A share of time as first, second or third man by
distance says nothing a player can act on, so it isn't kept.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..parser.types import Frame
from .tracks import Track

BEHIND_BALL_UU = 50.0


def positioning_stats(
    frames: list[Frame], tracks: Mapping[str, Track]
) -> dict[str, dict[str, Any]]:
    """Each player's share of time behind the ball."""
    result = {}
    for player_id, track in tracks.items():
        team = track[0][1].team
        behind = 0
        for index, car in track:
            ball = frames[index].ball.position
            if team == 0:
                behind += car.position.y < ball.y - BEHIND_BALL_UU
            else:
                behind += car.position.y > ball.y + BEHIND_BALL_UU
        result[player_id] = {"behind_ball_pct": round(behind / len(track) * 100.0, 2)}
    return result
