"""Tests for loading the bundled rank benchmarks."""

from __future__ import annotations

import json

import pytest

from rlcoach.benchmarks import (
    BUNDLED_BENCHMARKS,
    BenchmarkValidationError,
    load_benchmarks,
    problems,
    seed_default_benchmarks,
)
from rlcoach.db.models import Benchmark
from rlcoach.db.session import create_session, init_db, reset_engine


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
            {"metric": "goals", "playlist": "DOUBLES", "rank_tier": "GC1", "median": 1},
            {"metric": "vibes", "playlist": "HOOPS", "rank_tier": "GC9"},
        ]
    }
    assert problems(data) == [
        "benchmarks[1]: unknown metric 'vibes'",
        "benchmarks[1]: unknown playlist 'HOOPS'",
        "benchmarks[1]: unknown rank 'GC9'",
        "benchmarks[1]: no median",
    ]
    assert problems({}) == ["no 'benchmarks' list"]


def test_seeding_loads_each_playlist_once(db):
    loaded = seed_default_benchmarks()
    assert loaded == len(_rows()) > 0
    assert {row.playlist for row in _rows()} == {"DOUBLES", "STANDARD"}
    assert seed_default_benchmarks() == 0


def test_seeding_keeps_a_playlist_that_already_has_rows(db, tmp_path):
    mine = tmp_path / "mine.json"
    mine.write_text(
        json.dumps(
            {
                "metadata": {"source": "me", "collected_date": "2026-01-02"},
                "benchmarks": [
                    {
                        "metric": "goals",
                        "playlist": "DOUBLES",
                        "rank_tier": "GC1",
                        "median": 9.0,
                        "p25": 8.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert load_benchmarks(mine) == 1
    seed_default_benchmarks()
    doubles = [row for row in _rows() if row.playlist == "DOUBLES"]
    assert [(row.metric, row.median_value, row.source) for row in doubles] == [
        ("goals", 9.0, "me")
    ]
    assert doubles[0].source_date.isoformat() == "2026-01-02"
    assert doubles[0].p75_value is None


def test_loading_again_updates_rows_in_place(db, tmp_path):
    path = tmp_path / "b.json"
    row = {"metric": "saves", "playlist": "DUEL", "rank_tier": "C3", "median": 1.0}
    path.write_text(json.dumps({"benchmarks": [row]}), encoding="utf-8")
    load_benchmarks(path)
    path.write_text(
        json.dumps({"benchmarks": [{**row, "median": 2.0}]}), encoding="utf-8"
    )
    load_benchmarks(path)
    assert [(r.median_value, r.source) for r in _rows()] == [(2.0, "unknown")]


def test_a_bad_file_loads_nothing(db, tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(
        json.dumps({"benchmarks": [{"metric": "nope", "median": 1}]}),
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkValidationError, match="bad.json: .*unknown metric"):
        load_benchmarks(path)
    assert _rows() == []
