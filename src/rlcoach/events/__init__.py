"""The events in a game: goals, touches, 50/50s, demos, kickoffs and pickups."""

from .boost import detect_boost_pickups
from .challenges import detect_challenges
from .demos import detect_demos
from .goals import detect_goals
from .kickoffs import KickoffEvent, KickoffPlayer, detect_kickoffs
from .touches import detect_touches
from .types import (
    BoostPickupEvent,
    ChallengeEvent,
    DemoEvent,
    GoalEvent,
    TouchEvent,
)

__all__ = [
    "BoostPickupEvent",
    "ChallengeEvent",
    "DemoEvent",
    "GoalEvent",
    "KickoffEvent",
    "KickoffPlayer",
    "TouchEvent",
    "detect_boost_pickups",
    "detect_challenges",
    "detect_demos",
    "detect_goals",
    "detect_kickoffs",
    "detect_touches",
]
