"""How your stats compare: in wins against losses, and against a rank.

Both measure a gap in standard deviations, so a stat that swings a lot from
game to game needs a bigger gap to count. A stat with no spread at all can't
be measured that way, so it's left out rather than given an infinite gap.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

# The middle half of a normal distribution spans 1.35 standard deviations
IQR_PER_SD = 1.35

# How far past the median, in standard deviations, earns each label. The
# first threshold a stat clears names it, so 0.67 means above about p75.
SEVERITIES = (
    (0.67, "strength"),
    (0.0, "neutral"),
    (-0.5, "low"),
    (-1.0, "medium"),
    (-2.0, "high"),
)
WORST = "critical"
SEVERITY_ORDER = (WORST, "high", "medium", "low", "neutral", "strength")


@dataclass(frozen=True)
class Pattern:
    """A stat that differs between your wins and your losses."""

    metric: str
    win_avg: float
    loss_avg: float
    effect_size: float  # Cohen's d: the gap over the pooled standard deviation

    @property
    def delta(self) -> float:
        return self.win_avg - self.loss_avg

    @property
    def direction(self) -> str:
        return "higher_in_wins" if self.effect_size > 0 else "lower_in_wins"


@dataclass(frozen=True)
class Standing:
    """Your average for one stat against a rank's spread."""

    metric: str
    my_value: float
    median: float
    z_score: float  # Standard deviations above the median
    severity: str  # One of SEVERITY_ORDER


def _mean_and_sd(values: list[float]) -> tuple[float, float]:
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    return mean, math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def win_loss_patterns(
    wins: list[Mapping[str, Any]],
    losses: list[Mapping[str, Any]],
    metrics: Iterable[str],
    *,
    min_games: int = 5,
    min_effect: float = 0.5,
) -> list[Pattern]:
    """Stats whose wins and losses differ by at least `min_effect`, biggest first.

    A stat needs a value in `min_games` wins and as many losses to be measured.
    """
    patterns = []
    for metric in metrics:
        won = [g[metric] for g in wins if g.get(metric) is not None]
        lost = [g[metric] for g in losses if g.get(metric) is not None]
        if not won or not lost or min(len(won), len(lost)) < min_games:
            continue
        (win_avg, win_sd), (loss_avg, loss_sd) = _mean_and_sd(won), _mean_and_sd(lost)
        pooled = math.sqrt((win_sd**2 + loss_sd**2) / 2)
        if pooled == 0:
            continue
        effect = (win_avg - loss_avg) / pooled
        if abs(effect) >= min_effect:
            patterns.append(Pattern(metric, win_avg, loss_avg, effect))
    return sorted(patterns, key=lambda p: -abs(p.effect_size))


def severity(z_score: float, direction: str) -> str:
    """Label a gap, flipping it for stats where lower is better."""
    better = z_score if direction == "higher" else -z_score
    return next((label for floor, label in SEVERITIES if better >= floor), WORST)


def standings(
    averages: Mapping[str, float], benchmarks: Mapping[str, Mapping[str, Any]]
) -> list[Standing]:
    """Your averages against benchmarks of {"p25", "median", "p75", "direction"}.

    The spread comes from the benchmark's p25 to p75. Stats without a
    benchmark are left out.
    """
    results = []
    for metric, value in averages.items():
        bench = benchmarks.get(metric)
        if bench is None:
            continue
        spread = (bench["p75"] - bench["p25"]) / IQR_PER_SD
        if spread == 0:
            continue
        z = (value - bench["median"]) / spread
        label = severity(z, bench.get("direction", "higher"))
        results.append(Standing(metric, value, bench["median"], z, label))
    return results
