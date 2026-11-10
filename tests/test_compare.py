"""Tests for comparing wins with losses, and you with a rank."""

from __future__ import annotations

import math

import pytest

from rlcoach.compare import (
    BELOW_LADDER,
    FROM_BALLCHASING,
    MARGIN_SE,
    MIN_GAMES,
    RANK_STATS,
    place,
    win_loss_patterns,
)
from rlcoach.metrics import METRICS as KNOWN_STATS

METRICS = ("goals", "saves", "bcpm")


def _games(**columns: list[float | None]) -> list[dict]:
    count = len(next(iter(columns.values())))
    return [{name: values[n] for name, values in columns.items()} for n in range(count)]


def test_a_stat_much_higher_in_wins_is_a_pattern():
    wins = _games(goals=[2, 3, 2, 3, 2], saves=[1, 1, 2, 1, 2])
    losses = _games(goals=[0, 1, 0, 1, 0], saves=[1, 2, 1, 2, 1])
    [pattern] = win_loss_patterns(wins, losses, METRICS)
    assert pattern.metric == "goals"
    assert (pattern.win_avg, pattern.loss_avg) == (2.4, 0.4)
    assert pattern.delta == pytest.approx(2.0)
    # Both groups have a sample standard deviation of sqrt(0.3)
    assert pattern.effect_size == pytest.approx(2.0 / math.sqrt(0.3))
    assert pattern.direction == "higher_in_wins"


def test_a_stat_lower_in_wins_says_so():
    wins = _games(bcpm=[300, 310, 305, 300, 310])
    losses = _games(bcpm=[400, 390, 410, 400, 395])
    [pattern] = win_loss_patterns(wins, losses, METRICS)
    assert pattern.direction == "lower_in_wins"
    assert pattern.delta < 0


def test_patterns_need_enough_games_with_the_stat():
    wins = _games(goals=[3, 3, 3, 4, None])
    losses = _games(goals=[0, 0, 1, 0, 0])
    assert win_loss_patterns(wins, losses, METRICS) == []
    assert win_loss_patterns(wins, losses, METRICS, min_games=4)
    assert win_loss_patterns([], [], METRICS, min_games=0) == []


def test_small_gaps_and_no_spread_are_left_out():
    close = win_loss_patterns(
        _games(goals=[1, 2, 1, 2, 1]), _games(goals=[1, 2, 2, 1, 2]), METRICS
    )
    flat = win_loss_patterns(
        _games(goals=[2, 2, 2, 2, 2]), _games(goals=[0, 0, 0, 0, 0]), METRICS
    )
    assert close == flat == []


def test_patterns_come_biggest_first():
    wins = _games(goals=[2, 3, 2, 3, 2], saves=[5, 6, 5, 6, 5])
    losses = _games(goals=[1, 2, 1, 2, 2], saves=[0, 1, 0, 1, 0])
    assert [p.metric for p in win_loss_patterns(wins, losses, METRICS)] == [
        "saves",
        "goals",
    ]


def test_rank_stats_are_known_stats():
    assert set(RANK_STATS) <= KNOWN_STATS
    assert set(FROM_BALLCHASING) <= set(RANK_STATS)


TWOS_AND_THREES = [2.0, 3.0] * 5  # Mean 2.5 over 10 games
# Two standard errors of their mean: the sd is sqrt(2.5 / 9)
MARGIN = MARGIN_SE * math.sqrt(2.5 / 9) / math.sqrt(10)


def test_under_min_games_says_too_few_and_gives_no_margin_or_level():
    placed = place("saves", [3.0] * (MIN_GAMES - 1), {"GC": 1.0}, "GC")
    assert (placed.verdict, placed.margin) == ("too_few", None)
    assert (placed.level_low, placed.level_high) == (None, None)
    assert (placed.games, placed.gap) == (MIN_GAMES - 1, 2.0)


@pytest.mark.parametrize(
    ("target_average", "verdict"),
    [(2.5 - MARGIN - 0.01, "above"), (2.5 + MARGIN + 0.01, "below"), (2.3, "level")],
)
def test_the_gap_to_the_target_is_judged_against_its_margin(target_average, verdict):
    placed = place("saves", TWOS_AND_THREES, {"P1": target_average}, "P1")
    assert placed.margin == pytest.approx(MARGIN)
    assert placed.gap == pytest.approx(2.5 - target_average)
    assert placed.verdict == verdict


def test_a_gap_just_inside_the_margin_is_level():
    placed = place("saves", TWOS_AND_THREES, {"P1": 2.5 - MARGIN + 0.01}, "P1")
    assert placed.verdict == "level"


def test_identical_games_have_no_margin_so_any_gap_is_real():
    placed = place("saves", [2.0] * MIN_GAMES, {"GC": 1.5}, "GC")
    assert (placed.margin, placed.verdict) == (0.0, "above")
    assert place("saves", [2.0] * MIN_GAMES, {"GC": 2.0}, "GC").verdict == "level"


LADDER = {"G1": 1.0, "P1": 2.0, "GC": 3.0}


def _span(values, averages=LADDER):
    placed = place("saves", values, averages, "GC")
    return placed.level_low, placed.level_high


def test_a_steady_stat_reaches_one_rank_at_both_ends_of_its_margin():
    # 2.5 give or take 0.33 sits between P1's 2.0 and GC's 3.0 either way
    assert _span(TWOS_AND_THREES) == ("P1", "P1")
    # Reaching an average exactly counts
    assert _span([2.0] * MIN_GAMES) == ("P1", "P1")
    assert _span([5.0] * MIN_GAMES) == ("GC", "GC")


def test_a_noisy_stat_spans_several_ranks():
    # 2.5 give or take about 1.67
    assert _span([0.0, 5.0] * 5) == (BELOW_LADDER, "GC")


def test_under_the_lowest_rank_is_below_the_ladder():
    assert _span([0.5] * MIN_GAMES) == (BELOW_LADDER, BELOW_LADDER)
    assert BELOW_LADDER == "below G1"


def test_ranks_without_an_average_are_skipped():
    # G2 to D3 are missing, and G1 is the highest present that 2.5 reaches
    assert _span(TWOS_AND_THREES, {"G1": 1.0, "GC": 3.0}) == ("G1", "G1")


def test_the_ranks_boost_collected_is_put_in_our_units():
    values = [380.0, 400.0] * 5  # Ours average 390
    placed = place("bcpm", values, {"GC": 350.0}, "GC")
    assert placed.scaled
    assert placed.my_value == pytest.approx(390.0)
    assert placed.target_average == pytest.approx(350.0 * 1.051)
    assert placed.gap == pytest.approx(390.0 - 350.0 * 1.051)
    sd = math.sqrt(sum((v - 390.0) ** 2 for v in values) / 9)
    assert placed.margin == pytest.approx(MARGIN_SE * sd / math.sqrt(10))
    # Ballchasing's 380 is 399 as we count, which 390 give or take 7 doesn't
    # reach, though it would reach a bare 380
    ladder = place("bcpm", values, {"P1": 360.0, "GC": 380.0}, "GC")
    assert (ladder.level_low, ladder.level_high) == ("P1", "P1")


def test_other_stats_are_compared_as_they_are():
    placed = place("saves", TWOS_AND_THREES, {"GC": 2.0}, "GC")
    assert not placed.scaled
    assert (placed.my_value, placed.target_average) == (2.5, 2.0)


def test_nothing_is_placed_without_games_or_a_target_average():
    assert place("saves", [], LADDER, "GC") is None
    assert place("saves", TWOS_AND_THREES, LADDER, "D1") is None
    assert place("saves", TWOS_AND_THREES, {}, "GC") is None
