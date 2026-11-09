"""The stats the dashboard can chart or compare, which way is better for each,
and the ranks the benchmarks can name. The playlists are in modes.py."""

from __future__ import annotations

from enum import Enum


class MetricDirection(Enum):
    """Which way a stat should move."""

    HIGHER_BETTER = "higher"
    LOWER_BETTER = "lower"
    # Neither way is better, such as the share of time as first man
    CONTEXT_DEPENDENT = "context"


_HIGHER = MetricDirection.HIGHER_BETTER
_LOWER = MetricDirection.LOWER_BETTER
_CONTEXT = MetricDirection.CONTEXT_DEPENDENT

# Every key is a column of the per-player stats table.
DIRECTIONS: dict[str, MetricDirection] = {
    "goals": _HIGHER,
    "assists": _HIGHER,
    "saves": _HIGHER,
    "shots": _HIGHER,
    "shooting_pct": _HIGHER,
    "score": _HIGHER,
    "demos_inflicted": _HIGHER,
    "demos_taken": _LOWER,
    "bcpm": _HIGHER,
    "avg_boost": _LOWER,
    "time_zero_boost_s": _LOWER,
    "time_full_boost_s": _LOWER,
    "boost_collected": _HIGHER,
    "boost_stolen": _HIGHER,
    "avg_speed_kph": _HIGHER,
    "time_supersonic_s": _HIGHER,
    "behind_ball_pct": _HIGHER,
    "first_man_pct": _CONTEXT,
    "second_man_pct": _CONTEXT,
    "third_man_pct": _CONTEXT,
}

# The ranks the bundled benchmarks cover, lowest first. Ballchasing groups
# every Grand Champion tier together, so GC is GC1 through SSL.
RANKS = ("G1", "G2", "G3", "P1", "P2", "P3", "D1", "D2", "D3", "C1", "C2", "C3", "GC")


def is_valid_metric(key: str) -> bool:
    """Tell if a stat is one we know."""
    return key in DIRECTIONS


def metric_direction(key: str) -> MetricDirection | None:
    """Which way is better for a stat, or None for a stat we don't know."""
    return DIRECTIONS.get(key)
