"""Each player's stats for one game: the numbers the database stores.

Every stat is one of the `player_game_stats` columns, under the same name.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from .boost import boost_stats
from .fundamentals import fundamentals
from .movement import movement_stats
from .positioning import positioning_stats
from .tracks import player_tracks

if TYPE_CHECKING:
    from ..game import Game


def player_stats(game: Game, player_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Each player's stats, keyed by player id and then column.

    A player the frames never show gets nothing, since there's nothing to measure.
    """
    wanted = set(player_ids)
    tracks = {
        player_id: track
        for player_id, track in player_tracks(game.frames).items()
        if player_id in wanted
    }
    sections = (
        fundamentals(game.header, game.demos, tracks),
        boost_stats(game.frames, game.boost_pickups, tracks),
        movement_stats(game.frames, tracks),
        positioning_stats(game.frames, tracks),
    )
    return {
        player_id: {
            column: value
            for section in sections
            for column, value in section[player_id].items()
        }
        for player_id in tracks
    }
