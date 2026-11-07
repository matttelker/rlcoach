"""Integrated ingestion pipeline for processing replay files.

This module provides the complete pipeline for:
1. Ingesting replay files (validation, hashing)
2. Generating analysis reports
3. Writing to database
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .config import RLCoachConfig
from .db.reviews import review_game
from .db.session import init_db
from .db.writer import (
    PlayerNotFoundError,
    ReplayExistsError,
    check_not_stored,
    write_report,
)
from .identity import PlayerIdentityResolver
from .ingest import file_sha256, ingest_replay
from .report import generate_report

logger = logging.getLogger(__name__)


class IngestionStatus(Enum):
    """Status of replay ingestion."""

    SUCCESS = "success"
    DUPLICATE = "duplicate"
    ERROR = "error"
    PLAYER_NOT_FOUND = "player_not_found"
    EXCLUDED = "excluded"


@dataclass
class IngestionResult:
    """Result of processing a replay file."""

    status: IngestionStatus
    path: Path
    replay_id: str | None = None
    file_hash: str | None = None
    error: str | None = None

    def __str__(self) -> str:
        if self.status == IngestionStatus.SUCCESS:
            return f"✓ {self.path.name} -> {self.replay_id}"
        elif self.status == IngestionStatus.DUPLICATE:
            return f"⊘ {self.path.name} (duplicate)"
        elif self.status == IngestionStatus.EXCLUDED:
            return f"⊘ {self.path.name} (excluded)"
        else:
            return f"✗ {self.path.name}: {self.error}"


def process_replay_file(
    path: Path,
    config: RLCoachConfig,
    *,
    adapter_name: str = "rust",
    header_only: bool = False,
) -> IngestionResult:
    """Process a single replay file through the full pipeline.

    This function:
    1. Initializes the database if needed
    2. Hashes the file and stops with DUPLICATE if it is already stored, then
       validates it (size, format, CRC)
    3. Generates the analysis report
    4. Writes to database (players, replay, stats)

    Args:
        path: Path to the .replay file
        config: RLCoach configuration
        adapter_name: Parser adapter to use
        header_only: Whether to use header-only mode

    Returns:
        IngestionResult with status and details
    """
    try:
        init_db(config.db_path)

        # Stored replays stop here, on a hash that takes milliseconds, so a
        # watcher restart skips the slow CRC check and the parse for every
        # game already in the folder. insert_replay checks again.
        file_hash = file_sha256(path)
        check_not_stored(file_hash)

        ingest_replay(path)  # validates size, format and CRC

        report = generate_report(
            path,
            header_only=header_only,
            adapter_name=adapter_name,
            identity_config=config.identity,
        )

        if "error" in report:
            return IngestionResult(
                status=IngestionStatus.ERROR,
                path=path,
                error=report.get("error", "Unknown error"),
            )

        # Excluded names are accounts the user does not want analyzed.
        # If find_me succeeds -> that's "me", can't be excluded (validation
        # prevents overlap).
        # If find_me fails -> check if any player matches excluded_names (that
        # would be "me").
        resolver = PlayerIdentityResolver(config.identity)
        players = report.get("players", [])
        me = resolver.find_me(players)
        if me is None:
            for player in players:
                display_name = player.get("display_name", "")
                if resolver.should_exclude(display_name):
                    logger.debug(f"Excluded replay (account: {display_name}): {path}")
                    return IngestionResult(
                        status=IngestionStatus.EXCLUDED,
                        path=path,
                    )

        report["source_file"] = str(path)

        replay_id = write_report(report, file_hash, config)

        if me is not None:
            try:
                review_game(replay_id, path, me["player_id"])
            except Exception as e:  # noqa: BLE001 - the game itself is stored
                logger.warning(f"Could not store the mistake review for {path}: {e}")

        logger.info(f"Processed {path} -> {replay_id}")

        return IngestionResult(
            status=IngestionStatus.SUCCESS,
            path=path,
            replay_id=replay_id,
            file_hash=file_hash,
        )

    except ReplayExistsError as e:
        logger.debug(f"Duplicate replay: {path}")
        return IngestionResult(
            status=IngestionStatus.DUPLICATE,
            path=path,
            error=str(e),
        )

    except PlayerNotFoundError as e:
        logger.warning(f"Player not found in replay: {path}")
        return IngestionResult(
            status=IngestionStatus.PLAYER_NOT_FOUND,
            path=path,
            error=str(e),
        )

    except Exception as e:
        logger.error(f"Error processing {path}: {e}")
        return IngestionResult(
            status=IngestionStatus.ERROR,
            path=path,
            error=str(e),
        )


def process_batch(
    paths: list[Path],
    config: RLCoachConfig,
    *,
    adapter_name: str = "rust",
    header_only: bool = False,
    on_progress: callable | None = None,
) -> list[IngestionResult]:
    """Process multiple replay files.

    Args:
        paths: List of paths to replay files
        config: RLCoach configuration
        adapter_name: Parser adapter to use
        header_only: Whether to use header-only mode
        on_progress: Optional callback(index, total, result) for progress

    Returns:
        List of IngestionResults
    """
    results = []
    total = len(paths)

    for i, path in enumerate(paths):
        result = process_replay_file(
            path,
            config,
            adapter_name=adapter_name,
            header_only=header_only,
        )
        results.append(result)

        if on_progress:
            on_progress(i + 1, total, result)

    return results
