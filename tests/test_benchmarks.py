import json

import pytest

from rlcoach.benchmarks import (
    BUNDLED_BENCHMARKS,
    import_benchmarks,
    seed_default_benchmarks,
    validate_benchmark_data,
)
from rlcoach.db.models import Benchmark
from rlcoach.db.session import create_session, init_db, reset_engine


@pytest.fixture(autouse=True)
def reset_db():
    yield
    reset_engine()


def test_validate_uses_metric_catalog():
    """Validation should use the metric catalog, not a hardcoded list."""

    data = {
        "metadata": {"source": "test"},
        "benchmarks": [
            {
                "metric": "bcpm",
                "playlist": "DOUBLES",
                "rank_tier": "GC1",
                "median": 380,
            }
        ],
    }
    errors = validate_benchmark_data(data)
    assert errors == []


def test_validate_rejects_invalid_metric():
    """Should reject metrics not in the catalog."""
    data = {
        "metadata": {"source": "test"},
        "benchmarks": [
            {
                "metric": "made_up_metric",
                "playlist": "DOUBLES",
                "rank_tier": "GC1",
                "median": 100,
            }
        ],
    }
    errors = validate_benchmark_data(data)
    assert any("metric" in e.lower() for e in errors)


def test_import_benchmarks_success(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    benchmark_file = tmp_path / "benchmarks.json"
    benchmark_file.write_text(
        json.dumps(
            {
                "metadata": {
                    "source": "Test Source",
                    "collected_date": "2024-12-01",
                    "notes": "Test data",
                },
                "benchmarks": [
                    {
                        "metric": "bcpm",
                        "playlist": "DOUBLES",
                        "rank_tier": "GC1",
                        "median": 380,
                        "p25": 330,
                        "p75": 420,
                        "elite": 420,
                    },
                    {
                        "metric": "avg_boost",
                        "playlist": "DOUBLES",
                        "rank_tier": "GC1",
                        "median": 30,
                        "p25": 25,
                        "p75": 34,
                        "elite": 20,
                    },
                ],
            }
        )
    )

    count = import_benchmarks(benchmark_file)
    assert count == 2

    session = create_session()
    try:
        benchmark = (
            session.query(Benchmark).filter_by(metric="bcpm", rank_tier="GC1").first()
        )
        assert benchmark is not None
        assert benchmark.median_value == 380
        assert benchmark.source == "Test Source"
    finally:
        session.close()


def test_import_benchmarks_upserts(tmp_path):
    """Re-importing should update existing records."""
    db_path = tmp_path / "test.db"
    init_db(db_path)

    benchmark_file = tmp_path / "benchmarks.json"

    benchmark_file.write_text(
        json.dumps(
            {
                "metadata": {"source": "v1"},
                "benchmarks": [
                    {
                        "metric": "bcpm",
                        "playlist": "DOUBLES",
                        "rank_tier": "GC1",
                        "median": 100,
                    }
                ],
            }
        )
    )
    import_benchmarks(benchmark_file)

    benchmark_file.write_text(
        json.dumps(
            {
                "metadata": {"source": "v2"},
                "benchmarks": [
                    {
                        "metric": "bcpm",
                        "playlist": "DOUBLES",
                        "rank_tier": "GC1",
                        "median": 200,
                    }
                ],
            }
        )
    )
    import_benchmarks(benchmark_file)

    session = create_session()
    try:
        benchmarks = (
            session.query(Benchmark).filter_by(metric="bcpm", rank_tier="GC1").all()
        )
        assert len(benchmarks) == 1
        assert benchmarks[0].median_value == 200
        assert benchmarks[0].source == "v2"
    finally:
        session.close()


@pytest.mark.parametrize("playlist", sorted(BUNDLED_BENCHMARKS))
def test_bundled_benchmarks_pass_validation(playlist):
    text = BUNDLED_BENCHMARKS[playlist].read_text(encoding="utf-8")
    data = json.loads(text)

    assert validate_benchmark_data(data) == []
    assert {b["playlist"] for b in data["benchmarks"]} == {playlist}


@pytest.mark.parametrize("playlist", sorted(BUNDLED_BENCHMARKS))
def test_bundled_benchmarks_are_ordered(playlist):
    text = BUNDLED_BENCHMARKS[playlist].read_text(encoding="utf-8")

    for b in json.loads(text)["benchmarks"]:
        assert b["p25"] <= b["median"] <= b["p75"], b


def test_seed_default_benchmarks_only_loads_once(tmp_path):
    init_db(tmp_path / "test.db")

    assert seed_default_benchmarks() == 36
    assert seed_default_benchmarks() == 0


def test_seed_default_benchmarks_keeps_imported_rows(tmp_path):
    init_db(tmp_path / "test.db")
    session = create_session()
    session.add(
        Benchmark(
            metric="bcpm",
            playlist="STANDARD",
            rank_tier="GC1",
            median_value=999.0,
            source="mine",
        )
    )
    session.commit()
    session.close()

    # Standard already has rows, so only Doubles is loaded
    assert seed_default_benchmarks() == 18

    session = create_session()
    standard = session.query(Benchmark).filter_by(playlist="STANDARD").all()
    assert [b.median_value for b in standard] == [999.0]
    assert session.query(Benchmark).filter_by(playlist="DOUBLES").count() == 18
    session.close()
