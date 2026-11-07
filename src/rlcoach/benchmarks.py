"""The rank benchmarks bundled with rlcoach, loaded into the database.

They come from ballchasing.com's population stats (see each file's notes). A
playlist that already has rows keeps them, so loading runs once per playlist.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .db.models import Benchmark
from .db.session import create_session
from .metrics import VALID_RANKS, is_valid_metric
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
        if row.get("rank_tier") not in VALID_RANKS:
            found.append(f"{where}: unknown rank {row.get('rank_tier')!r}")
        if "median" not in row:
            found.append(f"{where}: no median")
    return found


def load_benchmarks(path: Path) -> int:
    """Add or update every benchmark in a file. Returns how many it holds."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if found := problems(data):
        raise BenchmarkValidationError(f"{path.name}: " + "; ".join(found))
    about = data.get("metadata", {})
    collected = about.get("collected_date")
    with create_session() as session, session.begin():
        for row in data["benchmarks"]:
            key = {
                "metric": row["metric"],
                "playlist": row["playlist"],
                "rank_tier": row["rank_tier"],
            }
            stored = session.query(Benchmark).filter_by(**key).first()
            if stored is None:
                stored = Benchmark(**key)
                session.add(stored)
            stored.median_value = row["median"]
            stored.p25_value = row.get("p25")
            stored.p75_value = row.get("p75")
            stored.elite_threshold = row.get("elite")
            stored.source = about.get("source", "unknown")
            stored.source_date = date.fromisoformat(collected) if collected else None
            stored.notes = row.get("notes") or about.get("notes")
            stored.imported_at = datetime.now(UTC)
    return len(data["benchmarks"])


def seed_default_benchmarks() -> int:
    """Load the bundled benchmarks for each playlist that has none yet."""
    with create_session() as session:
        stocked = {
            playlist for (playlist,) in session.query(Benchmark.playlist).distinct()
        }
    return sum(
        load_benchmarks(path)
        for playlist, path in BUNDLED_BENCHMARKS.items()
        if playlist not in stocked
    )
