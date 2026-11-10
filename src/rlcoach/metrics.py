"""The stats a benchmark can be about, and the ranks the benchmarks can name.
The playlists are in modes.py."""

from __future__ import annotations

# Every one is a column of the per-player stats table.
METRICS = frozenset(
    {
        "goals",
        "assists",
        "saves",
        "shots",
        "score",
        "demos_inflicted",
        "demos_taken",
        "epic_saves",
        "clears",
        "centers",
        "aerial_hits",
        "bcpm",
        "avg_boost",
        "time_zero_boost_s",
        "time_full_boost_s",
        "boost_collected",
        "boost_stolen",
        "avg_speed_kph",
        "time_supersonic_s",
        "behind_ball_pct",
    }
)

# The ranks the bundled benchmarks cover, lowest first. Ballchasing groups
# every Grand Champion tier together, so GC is GC1 through SSL.
RANKS = ("G1", "G2", "G3", "P1", "P2", "P3", "D1", "D2", "D3", "C1", "C2", "C3", "GC")


def is_valid_metric(key: str) -> bool:
    """Tell if a stat is one we know."""
    return key in METRICS
