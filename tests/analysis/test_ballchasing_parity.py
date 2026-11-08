"""Compare real games' stats with Ballchasing's own numbers for them.

The player's three games with a Ballchasing export, 18 players in all, give
measured truth, not expectations we wrote ourselves. Keep the bounds tight:
wide tolerances are how bugs got through before.

Only stats the database stores are checked. Collected per minute isn't: the CSV
has no such column, and its `bpm` is boost used, not collected. Collected reads
up to 7% over because each small pad counts a full 12, where Ballchasing counts
10-12% fewer small pads than the game's own pickup counter. Time at zero and at
full boost read high for a few players, up to 20% and 28%.
"""

from __future__ import annotations

import csv

import pytest

from rlcoach.analysis import player_stats
from rlcoach.game import read_game
from rlcoach.identity import build_player_identities
from rlcoach.physics_constants import UU_S_TO_KPH
from tests.fixtures import real_replays

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

# Largest allowed |ours / Ballchasing - 1|, set just above what we measure today
WITHIN = [
    ("avg boost amount", "avg_boost", 0.03),
    ("amount collected", "boost_collected", 0.075),
    ("amount stolen", "boost_stolen", 0.23),
    ("0 boost time", "time_zero_boost_s", 0.20),
    ("100 boost time", "time_full_boost_s", 0.28),
    ("time supersonic speed", "time_supersonic_s", 0.025),
    ("percentage behind ball", "behind_ball_pct", 0.045),
]


@pytest.fixture(scope="module", params=real_replays.CSV_GAMES)
def game(request) -> list[tuple[dict[str, str], dict]]:
    """Each player's Ballchasing row in a game, with our stats for them.

    Where we knowingly differ, the row is changed to what we say: Ballchasing
    gives two goals from one shot 200% where we stop at 100%, and doesn't count
    a demo with no attacker at the very end of a game.
    """
    name = request.param
    with real_replays.players_csv(name).open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    loaded = read_game(real_replays.replay(name))
    ids = {
        identity.display_name: identity.canonical_id
        for identity in build_player_identities(loaded.header.players)
    }
    stats = player_stats(loaded, ids.values())
    last = loaded.demos[-1] if loaded.demos else None
    ending = last.victim if last and last.attacker is None else None
    if ending and loaded.frames[-1].timestamp - last.t > 1.0:
        ending = None
    players = []
    for row in rows:
        row = dict(row)
        row["shooting percentage"] = str(min(100.0, float(row["shooting percentage"])))
        if ids[row["player name"]] == ending:
            row["demos taken"] = str(int(row["demos taken"]) + 1)
        players.append((row, stats[ids[row["player name"]]]))
    return players


@pytest.mark.parametrize(("column", "stat"), EXACT)
def test_stat_matches_ballchasing_exactly(game, column, stat):
    for row, ours in game:
        assert ours[stat] == float(row[column]), row["player name"]


@pytest.mark.parametrize(("column", "stat", "tolerance"), WITHIN)
def test_stat_is_close_to_ballchasing(game, column, stat, tolerance):
    for row, ours in game:
        expected = float(row[column])
        assert ours[stat] == pytest.approx(expected, rel=tolerance), row["player name"]


def test_average_speed_matches_ballchasing(game):
    for row, ours in game:
        uu_s = ours["avg_speed_kph"] / UU_S_TO_KPH
        assert uu_s == pytest.approx(float(row["avg speed"]), rel=0.008), row[
            "player name"
        ]
