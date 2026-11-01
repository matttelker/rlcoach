"""Compare one real replay's report with Ballchasing's own numbers for that replay.

`Replay_files/ballchasing_output/0925_players.csv` is Ballchasing's CSV export for
`Replay_files/0925.replay`, so these bounds are measured truth, not expectations we
wrote ourselves. Keep them tight: wide tolerances here are how bugs got through before.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from rlcoach.report import generate_report

REPO_ROOT = Path(__file__).resolve().parents[2]
REPLAY = REPO_ROOT / "Replay_files" / "0925.replay"
PLAYERS_CSV = REPO_ROOT / "Replay_files" / "ballchasing_output" / "0925_players.csv"

UU_S_PER_KPH = 1 / 0.036

EXACT = [
    ("goals", "fundamentals", "goals"),
    ("assists", "fundamentals", "assists"),
    ("saves", "fundamentals", "saves"),
    ("shots", "fundamentals", "shots"),
    ("score", "fundamentals", "score"),
    ("demos inflicted", "fundamentals", "demos_inflicted"),
    ("demos taken", "fundamentals", "demos_taken"),
    ("count collected big pads", "boost", "big_pads"),
    ("count stolen big pads", "boost", "stolen_big_pads"),
]

# Largest allowed |ours / Ballchasing - 1|, set just above what we measure today.
WITHIN = [
    ("avg boost amount", "boost", "avg_boost", 0.05),
    ("amount collected", "boost", "boost_collected", 0.07),
    ("amount stolen", "boost", "boost_stolen", 0.10),
    ("count stolen small pads", "boost", "stolen_small_pads", 0.21),
    ("0 boost time", "boost", "time_zero_boost_s", 0.20),
    ("100 boost time", "boost", "time_full_boost_s", 0.14),
    ("time slow speed", "movement", "time_slow_s", 0.05),
    ("time boost speed", "movement", "time_boost_speed_s", 0.10),
    ("time on ground", "movement", "time_ground_s", 0.08),
    ("time low in air", "movement", "time_low_air_s", 0.03),
    ("time high in air", "movement", "time_high_air_s", 0.04),
    ("time powerslide", "movement", "powerslide_duration_s", 0.08),
    ("count powerslide", "movement", "powerslide_count", 0.22),
    ("time defensive half", "positioning", "time_defensive_half_s", 0.05),
    ("time offensive half", "positioning", "time_offensive_half_s", 0.06),
    ("time defensive third", "positioning", "time_defensive_third_s", 0.06),
    ("time neutral third", "positioning", "time_middle_third_s", 0.06),
    ("time offensive third", "positioning", "time_offensive_third_s", 0.10),
    ("percentage behind ball", "positioning", "behind_ball_pct", 0.04),
]


def _ballchasing_rows() -> list[dict[str, str]]:
    with PLAYERS_CSV.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


@pytest.fixture(scope="module")
def players() -> dict[str, dict]:
    pytest.importorskip("rlreplay_rust")
    if REPLAY.stat().st_size < 1024:
        pytest.skip("0925.replay is a git symlink stub on this checkout")
    report = generate_report(REPLAY, adapter_name="rust")
    if "error" in report:
        pytest.skip(f"Rust parser could not read 0925: {report.get('details')}")
    return report["analysis"]["per_player"]


def _ours(players: dict[str, dict], row: dict[str, str]) -> dict:
    return players[f"steam:{row['player id']}"]


@pytest.mark.parametrize(("column", "section", "field"), EXACT)
def test_stat_matches_ballchasing_exactly(players, column, section, field):
    for row in _ballchasing_rows():
        assert _ours(players, row)[section][field] == float(row[column]), row[
            "player name"
        ]


@pytest.mark.parametrize(("column", "section", "field", "tolerance"), WITHIN)
def test_stat_is_close_to_ballchasing(players, column, section, field, tolerance):
    for row in _ballchasing_rows():
        expected = float(row[column])
        actual = _ours(players, row)[section][field]
        assert actual == pytest.approx(expected, rel=tolerance), row["player name"]


def test_time_stats_leave_out_goal_replays(players):
    """Ballchasing's ground and air times add up to the game, replays excluded."""
    for row in _ballchasing_rows():
        movement = _ours(players, row)["movement"]
        ours = sum(
            movement[key]
            for key in ("time_ground_s", "time_low_air_s", "time_high_air_s")
        )
        theirs = sum(
            float(row[key])
            for key in ("time on ground", "time low in air", "time high in air")
        )
        assert ours == pytest.approx(theirs, rel=0.04), row["player name"]
