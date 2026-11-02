"""API routers for RLCoach."""

from .analysis import router as analysis_router
from .dashboard import router as dashboard_router
from .games import router as games_router
from .players import router as players_router

__all__ = [
    "analysis_router",
    "dashboard_router",
    "games_router",
    "players_router",
]
