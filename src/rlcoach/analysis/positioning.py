"""Positioning: time behind the ball, and time as first, second or third man.

Each is a share of the frames the player is in, out of 100. Behind the ball
means more than 50 uu nearer your own goal than the ball. The first man is
the nearest to the ball on the team, the second has one teammate nearer, and
so on. A team of fewer than three has no third man.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ..parser.types import Frame, Vec3
from .tracks import Track

BEHIND_BALL_UU = 50.0


def _distance(a: Vec3, b: Vec3) -> float:
    return math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2 + (a.z - b.z) ** 2)


def positioning_stats(
    frames: list[Frame], tracks: Mapping[str, Track]
) -> dict[str, dict[str, Any]]:
    """Each player's shares of time behind the ball and in each role."""
    result = {}
    for player_id, track in tracks.items():
        first_index, first_car = track[0]
        team = first_car.team
        # The team's size as the player first appears, bots included
        team_size = sum(1 for car in frames[first_index].players if car.team == team)
        behind = 0
        roles = [0, 0, 0]
        for index, car in track:
            frame = frames[index]
            ball = frame.ball.position
            if team == 0:
                behind += car.position.y < ball.y - BEHIND_BALL_UU
            else:
                behind += car.position.y > ball.y + BEHIND_BALL_UU
            mine = _distance(car.position, ball)
            nearer = sum(
                1
                for other in frame.players
                if other.team == team
                and other.player_id != player_id
                and _distance(other.position, ball) < mine
            )
            roles[min(nearer, 2)] += 1
        frames_in = len(track)
        result[player_id] = {
            "behind_ball_pct": round(behind / frames_in * 100.0, 2),
            "first_man_pct": round(roles[0] / frames_in * 100.0, 2),
            "second_man_pct": round(roles[1] / frames_in * 100.0, 2),
            "third_man_pct": (
                round(roles[2] / frames_in * 100.0, 2) if team_size >= 3 else None
            ),
        }
    return result
