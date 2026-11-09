"""Read one replay into memory once: its header, frames and events.

Loading a game used to parse and normalize the replay twice, once for the
stats and again for the mistake review. Both now start from one Game.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .events import (
    BoostPickupEvent,
    ChallengeEvent,
    DemoEvent,
    GoalEvent,
    KickoffEvent,
    TouchEvent,
    detect_boost_pickups,
    detect_challenges,
    detect_demos,
    detect_goals,
    detect_kickoffs,
    detect_touches,
)
from .field_constants import BOOST_PADS
from .modes import mode_of
from .normalize import build_timeline
from .parser import read_frames, read_header
from .parser.types import Frame, Header


class NoFramesError(ValueError):
    """The parser read the header but no frames, so there's nothing to analyze."""


@dataclass(frozen=True)
class Game:
    """One replay's header, its frames from kickoff to the end, and its events."""

    path: Path
    header: Header
    frames: list[Frame]
    goals: list[GoalEvent]
    touches: list[TouchEvent]
    challenges: list[ChallengeEvent]
    demos: list[DemoEvent]
    kickoffs: list[KickoffEvent]
    boost_pickups: list[BoostPickupEvent]


def game_from_frames(path: Path, header: Header, frames: list[Frame]) -> Game:
    """Find the events in normalized frames."""
    goals = detect_goals(frames, header)
    touches = detect_touches(frames)
    return Game(
        path=path,
        header=header,
        frames=frames,
        goals=goals,
        touches=touches,
        challenges=detect_challenges(frames, touches),
        demos=detect_demos(frames),
        kickoffs=detect_kickoffs(frames, goals),
        boost_pickups=detect_boost_pickups(frames),
    )


def read_game(path: Path, header: Header | None = None) -> Game:
    """Parse a replay once. Pass the header if you've already read it."""
    header = header or read_header(path)
    pads = BOOST_PADS if mode_of(header.map_name).soccar_pads else []
    raw_frames = read_frames(path, [pad.position for pad in pads])
    if not raw_frames:
        raise NoFramesError(
            f"No frame data could be read from {path.name}. The replay parser may "
            "need updating for this game build."
        )
    return game_from_frames(path, header, build_timeline(header, raw_frames))
