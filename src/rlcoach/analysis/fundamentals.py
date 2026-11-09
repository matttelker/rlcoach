"""The scoreboard: goals, assists, saves, shots, score and demos, and the game's
other counts: epic saves, clears, centers and aerial hits.

The game records the scoreboard in the replay header, so those numbers are the
game's own. Demos aren't on it, so they're counted from the demo events. The other
counts come from the game too, as they rise during the match.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from ..events.types import DemoEvent
from ..identity import build_player_identities
from ..parser.types import Frame, Header

# Each column, and the header stat that holds it
SCOREBOARD = {
    "goals": "Goals",
    "assists": "Assists",
    "saves": "Saves",
    "shots": "Shots",
    "score": "Score",
}
# Each column, and the game's count that holds it. The game's clear is a touch
# from deep in front of your goal, much narrower than the review's clears from
# your half
GAME_COUNTS = {
    "epic_saves": "epic_save",
    "clears": "clear",
    "centers": "center",
    "aerial_hits": "aerial_hit",
}


def _whole(value: Any) -> int:
    try:
        return int(value or 0)
    except TypeError, ValueError:
        return 0


def shooting_pct(goals: int, shots: int) -> float:
    """Goals as a share of shots, out of 100.

    A goal can count without a shot on the scoreboard, so it's capped at 100.
    """
    if shots <= 0:
        return 0.0
    return round(min(goals / shots * 100.0, 100.0), 2)


def fundamentals(
    header: Header, demos: list[DemoEvent], player_ids: Mapping[str, Any]
) -> dict[str, dict[str, Any]]:
    """Each player's scoreboard. A player with no header row scores nothing."""
    header_stats = {
        identity.canonical_id: header.players[identity.header_index].stats or {}
        for identity in build_player_identities(header.players)
    }
    result = {}
    for player_id in player_ids:
        stats = header_stats.get(player_id, {})
        row: dict[str, Any] = {
            column: _whole(stats.get(key)) for column, key in SCOREBOARD.items()
        }
        row["shooting_pct"] = shooting_pct(row["goals"], row["shots"])
        row["demos_inflicted"] = sum(1 for d in demos if d.attacker == player_id)
        row["demos_taken"] = sum(1 for d in demos if d.victim == player_id)
        result[player_id] = row
    return result


def game_counts(
    frames: Sequence[Frame], player_ids: Mapping[str, Any]
) -> dict[str, dict[str, int | None]]:
    """Each player's epic saves, clears, centers and aerial hits, as the game
    counted them.

    Some older replays carry none of these counts (three of your 42 games, from
    2022 and October 2024). A full game always has some, so a game with none
    gets no value rather than zeros.
    """
    totals: Counter[tuple[str, str]] = Counter()
    for frame in frames:
        for count in frame.stat_counts:
            totals[count.player_id, count.stat] += count.count
    return {
        player_id: {
            column: totals[player_id, stat] if totals else None
            for column, stat in GAME_COUNTS.items()
        }
        for player_id in player_ids
    }
