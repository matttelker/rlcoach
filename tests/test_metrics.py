from rlcoach.db.models import PlayerGameStats
from rlcoach.metrics import METRICS, RANKS, is_valid_metric


def test_every_metric_is_a_stats_column():
    columns = set(PlayerGameStats.__table__.columns.keys())
    assert METRICS <= columns


def test_ranks_run_from_gold_to_grand_champion():
    assert (RANKS[0], RANKS[-1]) == ("G1", "GC")
    assert len(set(RANKS)) == len(RANKS) == 13


def test_unknown_metrics_are_not_valid():
    assert not is_valid_metric("wavedash_count")
    assert is_valid_metric("goals")
