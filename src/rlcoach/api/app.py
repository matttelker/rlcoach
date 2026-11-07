"""The local API under /api, which the dashboard and Claude read."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from .. import __version__
from ..benchmarks import seed_default_benchmarks
from ..config import ConfigError, RLCoachConfig, get_default_config_path, load_config
from ..db.session import create_session, init_db
from .routers import coach, games, grades, players, stats

logger = logging.getLogger(__name__)

_config: RLCoachConfig | None = None


def get_config() -> RLCoachConfig:
    """The config the API started with. Raises RuntimeError without one."""
    if _config is None:
        raise RuntimeError("Configuration not initialized")
    return _config


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Load the config and open the database while the API runs.

    Without a usable config the API still answers, from an empty database
    held in memory.
    """
    global _config
    path = get_default_config_path()
    try:
        config = load_config(path)
        config.validate()
    except ConfigError as e:
        logger.warning("No usable config, so nothing will be saved: %s", e)
        init_db()
    else:
        init_db(config.db_path)
        seed_default_benchmarks()
        _config = config
        logger.info("Loaded config from %s", path)
    try:
        yield
    finally:
        _config = None


def create_app() -> FastAPI:
    app = FastAPI(
        title="rlcoach API",
        description="Your games, reviews and stats, for the dashboard and Claude",
        version=__version__,
        lifespan=lifespan,
    )
    for module in (games, stats, players, coach, grades):
        app.include_router(module.router)

    @app.get("/health")
    async def health() -> dict[str, object]:
        """Whether the API is up and can reach the database."""
        try:
            create_session().close()
            database = "connected"
        except RuntimeError:
            database = "disconnected"
        return {
            "status": "healthy" if database == "connected" else "degraded",
            "service": "rlcoach-backend",
            "version": __version__,
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {"database": database},
        }

    return app
