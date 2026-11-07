"""API routers for RLCoach."""

from .analysis import router as analysis_router
from .coach import router as coach_router
from .games import router as games_router
from .grades import router as grades_router
from .players import router as players_router

__all__ = [
    "analysis_router",
    "coach_router",
    "games_router",
    "grades_router",
    "players_router",
]
