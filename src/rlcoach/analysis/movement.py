"""Movement: average speed and time at supersonic, as Ballchasing counts them.

Speed is the replicated velocity, never a change in position: car positions
refresh only every 2 or 3 frames, and kickoffs and respawns teleport the car.
A demolished car is off the field, so its time counts for neither stat.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from ..parser.types import Frame
from ..physics_constants import UU_S_TO_KPH
from .tracks import PAUSE_GAP_S, Track

SUPERSONIC_UU_S = 2200.0
MOVING_UU_S = 10.0  # Average speed leaves out a parked car
FALLBACK_FRAME_S = 1.0 / 30.0
SHORTEST_FRAME_S = 1e-3


def frame_durations(frames: list[Frame]) -> list[float]:
    """How long each frame lasts: until the next one.

    A goal replay's gap isn't play, and two frames can share a time, so either
    one lasts as long as the frame before it.
    """
    durations = []
    last = FALLBACK_FRAME_S
    for frame, after in zip(frames, [*frames[1:], None], strict=True):
        if after is not None and (
            SHORTEST_FRAME_S < after.timestamp - frame.timestamp <= PAUSE_GAP_S
        ):
            last = after.timestamp - frame.timestamp
        last = max(last, SHORTEST_FRAME_S)
        durations.append(last)
    return durations


def movement_stats(
    frames: list[Frame], tracks: Mapping[str, Track]
) -> dict[str, dict[str, Any]]:
    """Each player's average speed and seconds at supersonic."""
    durations = frame_durations(frames)
    result = {}
    for player_id, track in tracks.items():
        distance = moving = supersonic = 0.0
        for index, car in track:
            if car.is_demolished:
                continue
            v = car.velocity
            speed = math.sqrt(v.x**2 + v.y**2 + v.z**2)
            seconds = durations[index]
            distance += speed * seconds
            if speed >= MOVING_UU_S:
                moving += seconds
            if speed >= SUPERSONIC_UU_S:
                supersonic += seconds
        average = (distance / moving) * UU_S_TO_KPH if moving > 0 else 0.0
        result[player_id] = {
            "avg_speed_kph": round(average, 2),
            "time_supersonic_s": round(supersonic, 2),
        }
    return result
