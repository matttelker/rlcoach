"""Touches: the parser's touch events, placed at the car that touched the ball.

The parser only records a touch when the ball changes team, so a run of touches
by one team shows as its first. The mistake review finds contacts on its own.
"""

from __future__ import annotations

from ..parser.types import Frame
from ..physics_constants import UU_S_TO_KPH
from .types import TouchEvent, speed


def detect_touches(frames: list[Frame]) -> list[TouchEvent]:
    """One touch per player and moment, in time order.

    A touch by a car the frame doesn't show is placed at the ball.
    """
    touches: list[TouchEvent] = []
    seen: set[tuple[float, str]] = set()
    for frame in frames:
        for event in frame.parser_touch_events:
            key = (round(event.timestamp, 4), event.player_id)
            if key in seen:
                continue
            seen.add(key)
            car = frame.get_player_by_id(event.player_id)
            touches.append(
                TouchEvent(
                    t=event.timestamp,
                    player_id=event.player_id,
                    location=car.position if car else frame.ball.position,
                    ball_speed_kph=round(speed(frame.ball.velocity) * UU_S_TO_KPH, 2),
                )
            )
    touches.sort(key=lambda touch: touch.t)
    return touches
