from rlcoach.db.models import PlayerGameStats
from rlcoach.metrics import (
    DIRECTIONS,
    MetricDirection,
    is_valid_metric,
    metric_direction,
)


def test_every_metric_is_a_stats_column():
    columns = set(PlayerGameStats.__table__.columns.keys())
    assert set(DIRECTIONS) <= columns


def test_directions_say_which_way_is_better():
    assert metric_direction("bcpm") is MetricDirection.HIGHER_BETTER
    assert metric_direction("demos_taken") is MetricDirection.LOWER_BETTER
    assert metric_direction("first_man_pct") is MetricDirection.CONTEXT_DEPENDENT


def test_unknown_metrics_are_not_valid():
    assert metric_direction("wavedash_count") is None
    assert not is_valid_metric("wavedash_count")
    assert is_valid_metric("goals")
