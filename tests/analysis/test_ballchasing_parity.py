"""Compare one real replay's stored stats with Ballchasing's own numbers for it.

`Replay_files/ballchasing_output/0925_players.csv` is Ballchasing's CSV export for
`Replay_files/0925.replay`, so these bounds are measured truth, not expectations we
wrote ourselves. Keep them tight: wide tolerances here are how bugs got through before.

Only stats the database stores are checked. Collected per minute isn't: the CSV has
no such column, and its `bpm` is boost used, not collected. Collected boost reads
about 5% over because each small pad counts a full 12, where Ballchasing counts
10-12% fewer small pads than the game's own pickup counter.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from rlcoach.analysis import player_stats
from rlcoach.game import read_game

REPO_ROOT = Path(__file__).resolve().parents[2]
REPLAY = REPO_ROOT / "Replay_files" / "0925.replay"
PLAYERS_CSV = REPO_ROOT / "Replay_files" / "ballchasing_output" / "0925_players.csv"

UU_S_PER_KPH = 1 / 0.036

EXACT = [
    ("goals", "goals"),
    ("assists", "assists"),
    ("saves", "saves"),
    ("shots", "shots"),
    ("score", "score"),
    ("shooting percentage", "shooting_pct"),
    ("demos inflicted", "demos_inflicted"),
    ("demos taken", "demos_taken"),
]

# Largest allowed |ours / Ballchasing - 1|, set just above what we measure today.
WITHIN = [
    ("avg boost amount", "avg_boost", 0.03),
    ("amount collected", "boost_collected", 0.07),
    ("amount stolen", "boost_stolen", 0.10),
    ("0 boost time", "time_zero_boost_s", 0.08),
    ("100 boost time", "time_full_boost_s", 0.12),
    ("time supersonic speed", "time_supersonic_s", 0.04),
    ("percentage behind ball", "behind_ball_pct", 0.04),
]


def _ballchasing_rows() -> list[dict[str, str]]:
    with PLAYERS_CSV.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


@pytest.fixture(scope="module")
def players() -> dict[str, dict]:
    pytest.importorskip("rlreplay_rust")
    if REPLAY.stat().st_size < 1024:
        pytest.skip("0925.replay is a git symlink stub on this checkout")
    rows = _ballchasing_rows()
    return player_stats(read_game(REPLAY), [f"steam:{r['player id']}" for r in rows])


def _ours(players: dict[str, dict], row: dict[str, str]) -> dict:
    return players[f"steam:{row['player id']}"]


@pytest.mark.parametrize(("column", "stat"), EXACT)
def test_stat_matches_ballchasing_exactly(players, column, stat):
    for row in _ballchasing_rows():
        assert _ours(players, row)[stat] == float(row[column]), row["player name"]


@pytest.mark.parametrize(("column", "stat", "tolerance"), WITHIN)
def test_stat_is_close_to_ballchasing(players, column, stat, tolerance):
    for row in _ballchasing_rows():
        expected = float(row[column])
        actual = _ours(players, row)[stat]
        assert actual == pytest.approx(expected, rel=tolerance), row["player name"]


def test_average_speed_matches_ballchasing(players):
    for row in _ballchasing_rows():
        actual = _ours(players, row)["avg_speed_kph"] * UU_S_PER_KPH
        assert actual == pytest.approx(float(row["avg speed"]), rel=0.02), row[
            "player name"
        ]
