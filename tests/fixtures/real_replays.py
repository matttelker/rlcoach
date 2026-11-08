"""The player's own replays and Ballchasing exports, which stay out of git.

Tests read them from the folder that RLCOACH_TEST_REPLAYS names. Each replay is
there under its own file name, and Ballchasing's player CSV for it beside it as
`<replay name>.players.csv`. A test whose files aren't there skips, so CI runs
none of these.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

FOLDER_ENV = "RLCOACH_TEST_REPLAYS"

# Each game, and what makes it useful
REGULATION = "3DAA0E6446F8DD4F36F4AB87C9E41656"  # 3v3 on street_p, 1-4
LOPSIDED = "E5619443445BFAD0C075EDABC52AABB8"  # 3v3 on CHN_Stadium_P, 4-1
OVERTIME = "E8D9E35E41662D444CD8A599DB4C9865"  # 3v3, 2-1 in overtime
HOOPS = "B76ACC804F4524C9A52B928B34A99358"  # 2v2 Hoops, with no pad events
# 3v3 from 2022: five players left and were replaced, and it's from before the
# game counted first touches
WITH_LEAVERS = "D5B70C2E45BD70FA520EEDB17484A8C4"

# The games with a Ballchasing export
CSV_GAMES = (REGULATION, LOPSIDED, OVERTIME)


def find(name: str, suffix: str = ".replay") -> Path | None:
    """The test file called `name`, if this computer has it."""
    folder = os.environ.get(FOLDER_ENV)
    if not folder:
        return None
    path = Path(folder) / f"{name}{suffix}"
    return path if path.is_file() else None


def replay(name: str) -> Path:
    """The replay called `name`, or skip the test."""
    path = find(name)
    if path is None:
        pytest.skip(f"{name}.replay isn't in {FOLDER_ENV}")
    return path


def players_csv(name: str) -> Path:
    """Ballchasing's player CSV for the replay called `name`, or skip the test."""
    path = find(name, ".players.csv")
    if path is None:
        pytest.skip(f"{name}.players.csv isn't in {FOLDER_ENV}")
    return path
