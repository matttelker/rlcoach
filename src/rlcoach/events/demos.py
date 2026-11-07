"""Demos: the parser's demolition events, with the game's repeats taken out.

The game can report one demolition more than once, first without the attacker.
A report of the same car within 5 s and 200 uu of the last one is a repeat,
and it fills in the attacker if the first left it out.
"""

from __future__ import annotations

from ..parser.types import Frame, Vec3
from .types import DemoEvent, distance

REPEAT_WINDOW_S = 5.0
REPEAT_REACH_UU = 200.0


def _is_repeat(
    earlier: DemoEvent, where_then: Vec3 | None, later: DemoEvent, where: Vec3 | None
) -> bool:
    if later.t - earlier.t > REPEAT_WINDOW_S:
        return False
    if where_then is None or where is None:
        return True
    return distance(where_then, where) <= REPEAT_REACH_UU


def detect_demos(frames: list[Frame]) -> list[DemoEvent]:
    """Each demolition once, in time order."""
    demos: list[tuple[DemoEvent, Vec3 | None]] = []
    seen: set[tuple[float, str]] = set()
    last_of: dict[str, int] = {}  # Each victim's latest demo, by index in demos
    for frame in frames:
        for event in frame.parser_demo_events:
            key = (round(event.timestamp, 4), event.victim_id)
            if key in seen:
                continue
            seen.add(key)
            demo = DemoEvent(
                t=event.timestamp, victim=event.victim_id, attacker=event.attacker_id
            )
            car = frame.get_player_by_id(event.victim_id)
            where = car.position if car else None
            earlier = last_of.get(demo.victim)
            if earlier is not None and _is_repeat(*demos[earlier], demo, where):
                if demos[earlier][0].attacker is None and demo.attacker is not None:
                    demos[earlier] = (demo, where)
                continue
            last_of[demo.victim] = len(demos)
            demos.append((demo, where))
    return sorted((demo for demo, _ in demos), key=lambda demo: demo.t)
