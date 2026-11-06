"""FastAPI application setup."""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .. import __version__
from ..benchmarks import seed_default_benchmarks
from ..config import ConfigError, RLCoachConfig, get_default_config_path, load_config
from ..db.session import create_session, init_db
from .routers import (
    analysis_router,
    coach_router,
    dashboard_router,
    games_router,
    players_router,
)

logger = logging.getLogger(__name__)

# Global config - set on startup
_config: RLCoachConfig | None = None

CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]  # Vite dev server


def get_config() -> RLCoachConfig:
    """Get the current configuration."""
    if _config is None:
        raise RuntimeError("Configuration not initialized")
    return _config


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Load the config and open the database for the life of the app."""
    global _config

    try:
        config_path = get_default_config_path()
        _config = load_config(config_path)
        _config.validate()
        init_db(_config.db_path)
        seed_default_benchmarks()
        logger.info(f"Loaded config from {config_path}")
    except (ConfigError, FileNotFoundError) as e:
        logger.warning(f"Config not loaded: {e}")
        logger.warning("Using in-memory database (data will not persist)")
        init_db()

    yield

    _config = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="RLCoach API",
        description="Local API for the rlcoach dashboard",
        version=__version__,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(games_router)
    app.include_router(dashboard_router)
    app.include_router(analysis_router)
    app.include_router(players_router)
    app.include_router(coach_router)

    @app.get("/")
    async def root():
        """API information."""
        return {"name": "RLCoach API", "version": __version__, "docs": "/docs"}

    @app.get("/health")
    async def health():
        """Health check for the dashboard."""
        try:
            create_session().close()
            db_status = "connected"
        except Exception:
            db_status = "disconnected"

        return {
            "status": "healthy" if db_status == "connected" else "degraded",
            "service": "rlcoach-backend",
            "version": __version__,
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {"database": db_status},
        }

    return app


app = create_app()
