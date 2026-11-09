"""The events found in a game's frames, as the stats and the review read them."""

from __future__ import annotations

import math
from dataclasses import dataclass

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
    """A touch the game counted, where the car was, and how fast the ball went."""

    t: float
    player_id: str
    location: Vec3
    ball_speed_kph: float = 0.0
    frame: int = 0  # The frame it's placed at
    team: int | None = None


@dataclass(frozen=True)
class ChallengeEvent:
    """Two opponents touching the ball one after the other: a 50/50.

    The winner is the team of the second touch, or of the last in a scramble of
    touches straight after it. The location is midway between the two cars at
    their touches.
    """

    t: float
    first_player: str
    second_player: str
    winner_team: str | None
    location: Vec3 | None = None


@dataclass(frozen=True)
class DemoEvent:
    """A demolition, and where the victim's car was. The game doesn't always say
    who did it."""

    t: float
    victim: str
    attacker: str | None = None
    location: Vec3 | None = None
