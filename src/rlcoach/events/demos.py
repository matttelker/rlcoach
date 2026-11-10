"""Demos: the parser's demolition events, with the game's repeats taken out.

The game can report one demolition more than once, first without the attacker.
A report of the same car within 5 s and 200 uu of the last one is a repeat,
and it fills in the attacker if the first left it out.

A car can also be destroyed with nobody demolishing it: several at once just
after a goal, or a leaver's car where it stood. Those never name an attacker
and aren't demos: the scoreboard doesn't count them, nor does Ballchasing. On
42 games they were 30 of 144.
"""

from __future__ import annotations

from ..parser.types import Frame
from .types import DemoEvent, distance

REPEAT_WINDOW_S = 5.0
REPEAT_REACH_UU = 200.0


def _is_repeat(earlier: DemoEvent, later: DemoEvent) -> bool:
    if later.t - earlier.t > REPEAT_WINDOW_S:
        return False
    if earlier.location is None or later.location is None:
        return True
    return distance(earlier.location, later.location) <= REPEAT_REACH_UU


def detect_demos(frames: list[Frame]) -> list[DemoEvent]:
    """Each demolition once, in time order, where the victim's car was."""
    demos: list[DemoEvent] = []
    seen: set[tuple[float, str]] = set()
    last_of: dict[str, int] = {}  # Each victim's latest demo, by index in demos
    for frame in frames:
        for event in frame.parser_demo_events:
            key = (round(event.timestamp, 4), event.victim_id)
            if key in seen:
                continue
            seen.add(key)
            car = frame.get_player_by_id(event.victim_id)
            demo = DemoEvent(
                t=event.timestamp,
                victim=event.victim_id,
                attacker=event.attacker_id,
                location=car.position if car else None,
            )
            earlier = last_of.get(demo.victim)
            if earlier is not None and _is_repeat(demos[earlier], demo):
                if demos[earlier].attacker is None and demo.attacker is not None:
                    demos[earlier] = demo
                continue
            last_of[demo.victim] = len(demos)
            demos.append(demo)
    return sorted(
        (demo for demo in demos if demo.attacker is not None), key=lambda demo: demo.t
    )
