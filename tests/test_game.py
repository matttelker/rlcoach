"""Tests for reading a replay into memory once."""

from __future__ import annotations

from pathlib import Path

import pytest

import rlcoach.game as game_module
from rlcoach.events import detect_touches
from rlcoach.game import NoFramesError, game_from_frames, read_game
from rlcoach.parser.types import Header, NetworkFrames, PlayerInfo
from rlcoach.report import _went_to_overtime
from tests.fixtures.builders import create_simple_replay_frames

REPLAY = Path("Replay_files/testing_replay.replay")


class Counting:
    """Wraps a function and counts its calls."""

    def __init__(self, function):
        self.function, self.calls = function, 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.function(*args, **kwargs)


@pytest.fixture(scope="module")
def counted():
    with pytest.MonkeyPatch.context() as patch:
        header = Counting(game_module.read_header)
        network = Counting(game_module.read_network)
        patch.setattr(game_module, "read_header", header)
        patch.setattr(game_module, "read_network", network)
        game = read_game(REPLAY)
    return game, header.calls, network.calls


@pytest.mark.skipif(not REPLAY.exists(), reason="replay fixture missing")
def test_a_real_replay_is_parsed_once_into_frames_and_events(counted):
    game, header_reads, network_reads = counted
    assert (header_reads, network_reads) == (1, 1)
    assert game.header.map_name == "EuroStadium_Dusk_P"
    assert game.frames[0].timestamp == 0.0
    # 5-4 on the scoreboard
    assert len(game.goals) == 9
    assert game.touches and game.kickoffs and game.boost_pickups
    assert game.events["touches"] is game.touches


def test_a_header_already_read_is_not_read_again(monkeypatch):
    header = Header(map_name="Stadium_P", team_size=1)
    frames = create_simple_replay_frames(duration_seconds=1.0)
    monkeypatch.setattr(
        game_module, "read_header", lambda path: pytest.fail("read the header")
    )
    monkeypatch.setattr(
        game_module,
        "read_network",
        lambda path: NetworkFrames(frame_count=len(frames), frames=frames),
    )
    monkeypatch.setattr(game_module, "build_timeline", lambda header, raw: raw)
    game = read_game(Path("x.replay"), header)
    assert game.header is header and game.frames == frames


def test_a_replay_without_frames_is_an_error(monkeypatch):
    monkeypatch.setattr(
        game_module, "read_network", lambda path: NetworkFrames(frame_count=0)
    )
    with pytest.raises(NoFramesError, match="No frame data could be read from x"):
        read_game(Path("x.replay"), Header())


def test_events_come_from_the_frames_given():
    header = Header(
        map_name="Stadium_P",
        team_size=1,
        players=[PlayerInfo(name="A", team=0), PlayerInfo(name="B", team=1)],
    )
    frames = create_simple_replay_frames(duration_seconds=2.0)
    game = game_from_frames(Path("x.replay"), header, frames)
    assert game.frames is frames
    assert game.touches == detect_touches(frames)
    assert game.goals == [] and game.demos == []
    assert set(game.events) == {
        "goals",
        "demos",
        "kickoffs",
        "boost_pickups",
        "touches",
        "challenges",
    }


TIED = Path("Replay_files/70c0e78e-ea32-4722-a951-937baa40efc9.replay")


@pytest.fixture(scope="module")
def tied():
    return read_game(TIED)


@pytest.mark.skipif(not TIED.exists(), reason="replay fixture missing")
def test_touches_are_repeatable_between_parses(tied):
    """Regression: same-frame touches swapped, which changed passing stats."""
    assert read_game(TIED, tied.header).touches == tied.touches


@pytest.mark.skipif(
    not (REPLAY.exists() and TIED.exists()), reason="replay fixture missing"
)
def test_real_games_show_whether_they_went_to_overtime(counted, tied):
    """Regression: current headers carry no overtime flag, so every game said no."""
    # 5-4, settled by an overtime goal
    game = counted[0]
    assert _went_to_overtime(game.header, game.kickoffs) is True
    # 3-2, the last goal 3 s before the end of regulation
    assert _went_to_overtime(tied.header, tied.kickoffs) is False
