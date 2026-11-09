"""Tests for loading the bundled rank benchmarks."""

from __future__ import annotations

import json

import pytest

from rlcoach.api.routers.stats import COMPARED_METRICS
from rlcoach.benchmarks import (
    BUNDLED_BENCHMARKS,
    BenchmarkValidationError,
    problems,
    read_benchmarks,
    seed_benchmarks,
)
from rlcoach.db.models import Benchmark
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.metrics import RANKS


@pytest.fixture
def db():
    init_db()
    yield
    reset_engine()


def _rows():
    with create_session() as session:
        return session.query(Benchmark).all()


@pytest.mark.parametrize("playlist", sorted(BUNDLED_BENCHMARKS))
def test_the_bundled_files_name_only_known_stats_and_ranks(playlist):
    data = json.loads(BUNDLED_BENCHMARKS[playlist].read_text(encoding="utf-8"))
    assert problems(data) == []
    assert {row["playlist"] for row in data["benchmarks"]} == {playlist}


def test_problems_name_each_bad_row():
    data = {
        "benchmarks": [
            {"metric": "goals", "playlist": "DOUBLES", "rank_tier": "GC", "median": 1},
            {"metric": "vibes", "playlist": "HOOPS", "rank_tier": "GC1"},
        ]
    }
    assert problems(data) == [
        "benchmarks[1]: unknown metric 'vibes'",
        "benchmarks[1]: unknown playlist 'HOOPS'",
        "benchmarks[1]: unknown rank 'GC1'",
        "benchmarks[1]: no median",
    ]
    assert problems({}) == ["no 'benchmarks' list"]


@pytest.mark.parametrize("playlist", sorted(BUNDLED_BENCHMARKS))
def test_the_bundled_files_cover_every_rank_and_compared_stat(playlist):
    data = json.loads(BUNDLED_BENCHMARKS[playlist].read_text(encoding="utf-8"))
    pairs = [(row["metric"], row["rank_tier"]) for row in data["benchmarks"]]
    assert sorted(pairs) == sorted((m, r) for m in COMPARED_METRICS for r in RANKS)


@pytest.mark.parametrize("playlist", sorted(BUNDLED_BENCHMARKS))
def test_the_bundled_medians_rise_with_rank_where_more_is_better(playlist):
    data = json.loads(BUNDLED_BENCHMARKS[playlist].read_text(encoding="utf-8"))
    for metric in ("bcpm", "saves", "shots"):
        medians = {
            row["rank_tier"]: row["median"]
            for row in data["benchmarks"]
            if row["metric"] == metric
        }
        climb = [medians[rank] for rank in RANKS]
        assert climb == sorted(climb), metric


def test_seeding_loads_every_bundled_row_each_time(db):
    loaded = seed_benchmarks()
    assert loaded == len(_rows()) == 2 * len(RANKS) * len(COMPARED_METRICS)
    assert {row.playlist for row in _rows()} == {"DOUBLES", "STANDARD"}
    assert seed_benchmarks() == loaded == len(_rows())


def test_seeding_replaces_rows_from_older_files(db):
    with create_session() as session, session.begin():
        session.add(
            Benchmark(
                metric="goals",
                playlist="DOUBLES",
                rank_tier="GC1",
                median_value=9.0,
                source="old",
            )
        )
    seed_benchmarks()
    assert not [row for row in _rows() if row.rank_tier == "GC1"]
    g3 = [row for row in _rows() if row.rank_tier == "G3" and row.metric == "goals"]
    assert {row.playlist for row in g3} == {"DOUBLES", "STANDARD"}
    assert {row.source for row in _rows()} == {"ballchasing.com population statistics"}


def test_reading_a_file_keeps_its_source_and_date(tmp_path):
    path = tmp_path / "b.json"
    path.write_text(
        json.dumps(
            {
                "metadata": {"source": "me", "collected_date": "2026-01-02"},
                "benchmarks": [
                    {
                        "metric": "saves",
                        "playlist": "DUEL",
                        "rank_tier": "C3",
                        "median": 1,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    [row] = read_benchmarks(path)
    assert (row.metric, row.median_value, row.source) == ("saves", 1, "me")
    assert row.source_date.isoformat() == "2026-01-02"
    assert row.p75_value is None


def test_a_bad_file_reads_nothing(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps({"benchmarks": [{"metric": "nope", "median": 1}]}),
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkValidationError, match="bad.json: .*unknown metric"):
        read_benchmarks(path)
