"""How your stats compare: in wins against losses, and against the ranks.

Against the ranks, only the stats that rise from rank to rank say anything:
boost collected per minute, saves and shots. Goals and assists a game are
nearly flat from Gold to Grand Champion, because everyone plays their own
rank, and average boost rises to Diamond and falls again. So those three are
the ones placed on the ladder.

A placement says which ranks' averages yours has reached, and whether the gap
to the rank you're aiming at is real. Your average over a handful of games
moves by chance, so both are judged with its margin: twice the standard error
of your average, from how much the stat swings between your games. The level
is a span of ranks, from the one your average less the margin reaches to the
one your average plus the margin does. Saves and shots rise so little from
rank to rank that 30 games span most of the ladder, and the span says so
instead of naming one rank. Under `MIN_GAMES` games nothing is said.

The benchmarks are Ballchasing's, so where it counts a stat differently its
averages are put in our units first, and every page shows one number for a
rank. It counts about 5% less boost collected than the
game does: on three games and 18 players ours read 0.8% to 7.4% over, 5.1% on
average, all of it in small pads, where ours matches the game's own pickup
counter and Ballchasing's count is 15% lower.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .metrics import RANKS

# The stats that rise with rank, which a placement means something for
RANK_STATS = ("bcpm", "saves", "shots")
# What to multiply Ballchasing's figure for a stat by to put it in our units
FROM_BALLCHASING = {"bcpm": 1.051}
# Fewer games than this say too little about your average
MIN_GAMES = 10
# How many standard errors the gap to the target must clear to be called real
MARGIN_SE = 2.0
BELOW_LADDER = "below " + RANKS[0]


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
class Placement:
    """Your average for one stat, placed among the ranks' averages."""

    metric: str
    games: int
    my_value: float
    target_average: float  # In our units, as is everything here
    gap: float  # my_value less target_average
    margin: float | None  # The gap has to clear this to be real. None under MIN_GAMES
    # "above", "below" or "level" with the target, or "too_few" games to say
    verdict: str
    # The highest ranks whose averages yours reaches at the bottom and the top
    # of its margin, each a rank or "below G1". None under MIN_GAMES
    level_low: str | None
    level_high: str | None

    @property
    def scaled(self) -> bool:
        """Whether the rank's average was converted from Ballchasing's units."""
        return self.metric in FROM_BALLCHASING


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


def in_our_units(metric: str, value: float) -> float:
    """A Ballchasing figure for a stat, as we count the stat."""
    return value * FROM_BALLCHASING.get(metric, 1.0)


def place(
    metric: str, values: Sequence[float], averages: Mapping[str, float], target: str
) -> Placement | None:
    """Place one stat's games among the ranks. `averages` is each rank's
    average as Ballchasing publishes it.

    None without any games, or without an average for the target rank.
    """
    if not values or target not in averages:
        return None
    averages = {rank: in_our_units(metric, a) for rank, a in averages.items()}
    mine, sd = _mean_and_sd(list(values))
    gap = mine - averages[target]

    def reached(value: float) -> str:
        ranks = [r for r in RANKS if r in averages and averages[r] <= value]
        return ranks[-1] if ranks else BELOW_LADDER

    if len(values) < MIN_GAMES:
        margin, verdict, low, high = None, "too_few", None, None
    else:
        margin = MARGIN_SE * sd / math.sqrt(len(values))
        verdict = "level" if abs(gap) <= margin else "above" if gap > 0 else "below"
        low, high = reached(mine - margin), reached(mine + margin)
    return Placement(
        metric=metric,
        games=len(values),
        my_value=mine,
        target_average=averages[target],
        gap=gap,
        margin=margin,
        verdict=verdict,
        level_low=low,
        level_high=high,
    )
