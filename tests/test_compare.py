"""Tests for comparing wins with losses, and you with a rank."""

from __future__ import annotations

import math

import pytest

from rlcoach.compare import severity, standings, win_loss_patterns

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


@pytest.mark.parametrize(
    ("z", "label"),
    [
        (0.67, "strength"),
        (0.66, "neutral"),
        (0.0, "neutral"),
        (-0.5, "low"),
        (-0.51, "medium"),
        (-1.0, "medium"),
        (-2.0, "high"),
        (-2.01, "critical"),
    ],
)
def test_severity_steps(z, label):
    assert severity(z, "higher") == label
    assert severity(-z, "lower") == label


BENCH = {"p25": 1.0, "median": 2.0, "p75": 3.7, "direction": "higher"}


def test_standings_measure_in_the_benchmarks_spread():
    [standing] = standings({"goals": 4.0, "assists": 1.0}, {"goals": BENCH})
    # p25 to p75 spans 2.7, which is 1.35 standard deviations, so one is 2.0
    assert standing.z_score == pytest.approx(1.0)
    assert (standing.metric, standing.median, standing.severity) == (
        "goals",
        2.0,
        "strength",
    )


def test_holding_more_boost_than_the_rank_is_a_weakness():
    bench = {"p25": 30.0, "median": 40.0, "p75": 50.0, "direction": "lower"}
    [standing] = standings({"avg_boost": 60.0}, {"avg_boost": bench})
    assert standing.z_score > 0
    assert standing.severity == "high"


def test_a_benchmark_with_no_spread_is_left_out():
    flat = {"p25": 2.0, "median": 2.0, "p75": 2.0}
    assert standings({"goals": 3.0}, {"goals": flat}) == []
