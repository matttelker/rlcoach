"""Load one replay into the database: its game, its stats and your review.

The replay is parsed once. The stats and the mistake review both read the
same frames and events, so a game costs one parse and one normalize.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .config import RLCoachConfig
from .db.games import ReplayExistsError, is_stored, store_game
from .db.reviews import store_review
from .game import read_game
from .identity import Me, build_player_identities
from .parser import read_header
from .replay_file import check_replay_file, file_hash
from .report import report_for

logger = logging.getLogger(__name__)


class IngestionStatus(Enum):
    SUCCESS = "success"
    DUPLICATE = "duplicate"  # Already stored
    EXCLUDED = "excluded"  # One of the accounts your config leaves out
    PLAYER_NOT_FOUND = "player_not_found"  # You aren't in it
    ERROR = "error"


@dataclass
class IngestionResult:
    status: IngestionStatus
    path: Path
    replay_id: str | None = None
    file_hash: str | None = None
    error: str | None = None


def process_replay_file(path: Path, config: RLCoachConfig) -> IngestionResult:
    """Store a replay and review you in it. Call init_db first.

    A stored replay stops at its hash, which takes milliseconds, so restarting
    the watcher on a full folder costs nothing.
    """
    try:
        digest = file_hash(path)
        if is_stored(digest):
            return IngestionResult(IngestionStatus.DUPLICATE, path, file_hash=digest)
        check_replay_file(path)

        header = read_header(path)
        players = build_player_identities(header.players)
        matcher = Me(config.identity)
        me = matcher.find(players)
        if me is None:
            if any(matcher.is_excluded(p.display_name) for p in players):
                return IngestionResult(IngestionStatus.EXCLUDED, path)
            return IngestionResult(
                IngestionStatus.PLAYER_NOT_FOUND,
                path,
                error="None of the players is you. Check [identity] in your config.",
            )

        game = read_game(path, header)
        replay_id = store_game(
            report_for(game, digest), digest, me.canonical_id, config
        )
    except ReplayExistsError:
        return IngestionResult(IngestionStatus.DUPLICATE, path)
    except Exception as e:  # noqa: BLE001 - one bad replay mustn't stop the rest
        logger.error("Couldn't load %s: %s", path, e)
        return IngestionResult(IngestionStatus.ERROR, path, error=str(e))
    try:
        store_review(replay_id, me.canonical_id, game)
    except Exception as e:  # noqa: BLE001 - the game itself is stored
        logger.warning("Couldn't store the review of %s: %s", path, e)
    logger.info("Loaded %s as %s", path, replay_id)
    return IngestionResult(
        IngestionStatus.SUCCESS, path, replay_id=replay_id, file_hash=digest
    )
