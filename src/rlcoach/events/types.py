"""The events found in a game's frames, as the stats and the review read them."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from ..field_constants import Vec3

TEAM_NAMES = {0: "BLUE", 1: "ORANGE"}


def team_name(team: int | None) -> str:
    """ "BLUE" for team 0, "ORANGE" for team 1, "UNKNOWN" for anything else."""
    return TEAM_NAMES.get(team, "UNKNOWN")


def distance(a: Vec3, b: Vec3) -> float:
    dx, dy, dz = a.x - b.x, a.y - b.y, a.z - b.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def speed(v: Vec3) -> float:
    return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)


@dataclass(frozen=True)
class GoalEvent:
    """A goal, the team that scored it, its scorer and their likely assist."""

    t: float
    team: str  # "BLUE" or "ORANGE"
    scorer: str | None = None
    assist: str | None = None


@dataclass(frozen=True)
class TouchEvent:
    """A touch the parser saw, where the car was, and how fast the ball went."""

    t: float
    player_id: str
    location: Vec3
    ball_speed_kph: float = 0.0


@dataclass(frozen=True)
class ChallengeEvent:
    """Two opponents touching the ball one after the other: a 50/50.

    The winner is the team of the second touch, unless a third came straight
    after, which makes it nobody's.
    """

    t: float
    first_player: str
    second_player: str
    winner_team: str | None


@dataclass(frozen=True)
class DemoEvent:
    """A demolition. The game doesn't always say who did it."""

    t: float
    victim: str
    attacker: str | None = None


@dataclass(frozen=True)
class KickoffEvent:
    """Kickoff event with player analysis."""

    phase: str  # "INITIAL" or "OT"
    t_start: float  # Cars released; the ball reset if frames show no countdown
    players: list[dict[str, Any]]  # Player kickoff analysis
    outcome: str = "NEUTRAL"  # Simplified outcome
    first_touch_player: str | None = None
    time_to_first_touch: float | None = None
    source: str = "inferred"


@dataclass(frozen=True)
class BoostPickupEvent:
    """Boost pad pickup event."""

    t: float
    player_id: str
    pad_type: str  # "SMALL" or "BIG"
    stolen: bool = False  # True if on opponent half
    pad_id: int = -1  # Index in boost pad arrays
    location: Vec3 | None = None
    frame: int | None = None
    boost_before: float | None = None
    boost_after: float | None = None
    boost_gain: float = 0.0


@dataclass
class PadState:
    """Runtime tracking for boost pad availability."""

    available_at: float = 0.0
    last_pickup: float | None = None


@dataclass(frozen=True)
class PadEnvelope:
    """Spatial heuristics for matching a player to a boost pad."""

    radius: float
    max_distance: float
    height_tolerance: float
