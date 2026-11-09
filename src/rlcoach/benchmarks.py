"""The rank benchmarks bundled with rlcoach, loaded into the database.

They come from ballchasing.com's population stats (see each file's notes). The
server reloads them every time it starts, so a changed file reaches the
dashboard after a restart.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .db.models import Benchmark
from .db.session import create_session
from .metrics import RANKS, is_valid_metric
from .modes import COACHED_PLAYLISTS

DATA_DIR = Path(__file__).parent / "data"
BUNDLED_BENCHMARKS = {
    "DOUBLES": DATA_DIR / "benchmarks_doubles.json",
    "STANDARD": DATA_DIR / "benchmarks_standard.json",
}


class BenchmarkValidationError(ValueError):
    """A benchmark file names a stat, playlist or rank rlcoach doesn't know."""


def problems(data: dict[str, Any]) -> list[str]:
    """What's wrong with a benchmark file's contents, if anything."""
    if "benchmarks" not in data:
        return ["no 'benchmarks' list"]
    found = []
    for n, row in enumerate(data["benchmarks"]):
        where = f"benchmarks[{n}]"
        if not is_valid_metric(row.get("metric", "")):
            found.append(f"{where}: unknown metric {row.get('metric')!r}")
        if row.get("playlist") not in COACHED_PLAYLISTS:
            found.append(f"{where}: unknown playlist {row.get('playlist')!r}")
        if row.get("rank_tier") not in RANKS:
            found.append(f"{where}: unknown rank {row.get('rank_tier')!r}")
        if "median" not in row:
            found.append(f"{where}: no median")
    return found


def read_benchmarks(path: Path) -> list[Benchmark]:
    """A benchmark file's rows, unsaved. Raises if any row is bad."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if found := problems(data):
        raise BenchmarkValidationError(f"{path.name}: " + "; ".join(found))
    about = data.get("metadata", {})
    collected = about.get("collected_date")
    return [
        Benchmark(
            metric=row["metric"],
            playlist=row["playlist"],
            rank_tier=row["rank_tier"],
            median_value=row["median"],
            p25_value=row.get("p25"),
            p75_value=row.get("p75"),
            elite_threshold=row.get("elite"),
            source=about.get("source", "unknown"),
            source_date=date.fromisoformat(collected) if collected else None,
            notes=row.get("notes") or about.get("notes"),
            imported_at=datetime.now(UTC),
        )
        for row in data["benchmarks"]
    ]


def seed_benchmarks() -> int:
    """Replace the stored benchmarks with the bundled ones. Returns how many."""
    rows = [r for path in BUNDLED_BENCHMARKS.values() for r in read_benchmarks(path)]
    with create_session() as session, session.begin():
        session.query(Benchmark).delete()
        session.add_all(rows)
    return len(rows)
