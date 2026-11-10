"""Tests for reading a replay into memory once."""

from __future__ import annotations

from pathlib import Path

import pytest

import rlcoach.game as game_module
from rlcoach.events import detect_touches
from rlcoach.game import NoFramesError, game_from_frames, read_game
from rlcoach.modes import EXTRA_MODE, playlist_of
from rlcoach.parser.types import Header, PlayerInfo
from rlcoach.report import _went_to_overtime
from tests.fixtures import real_replays
from tests.fixtures.builders import create_simple_replay_frames


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
        network = Counting(game_module.read_frames)
        patch.setattr(game_module, "read_header", header)
        patch.setattr(game_module, "read_frames", network)
        game = read_game(real_replays.replay(real_replays.OVERTIME))
    return game, header.calls, network.calls


def test_a_real_replay_is_parsed_once_into_frames_and_events(counted):
    game, header_reads, network_reads = counted
    assert (header_reads, network_reads) == (1, 1)
    assert game.header.map_name == "EuroStadium_Rainy_P"
    assert game.frames[0].timestamp == 0.0
    # 2-1 on the scoreboard
    assert len(game.goals) == 3
    assert game.touches and game.kickoffs and game.boost_pickups


def test_a_header_already_read_is_not_read_again(monkeypatch):
    header = Header(map_name="Stadium_P", team_size=1)
    frames = create_simple_replay_frames(duration_seconds=1.0)
    raw = [{"playlist": None}, {"playlist": 11}, {"playlist": 13}]
    monkeypatch.setattr(
        game_module, "read_header", lambda path: pytest.fail("read the header")
    )
    monkeypatch.setattr(game_module, "read_frames", lambda path, pads: raw)
    monkeypatch.setattr(game_module, "build_timeline", lambda header, raw: frames)
    game = read_game(Path("x.replay"), header)
    assert game.header is header and game.frames == frames
    # The first playlist the game sends
    assert game.playlist_id == 11


def test_a_replay_without_a_playlist_has_no_id(monkeypatch):
    frames = create_simple_replay_frames(duration_seconds=1.0)
    monkeypatch.setattr(game_module, "read_frames", lambda path, pads: [{}])
    monkeypatch.setattr(game_module, "build_timeline", lambda header, raw: frames)
    assert read_game(Path("x.replay"), Header()).playlist_id is None


def test_a_replay_without_frames_is_an_error(monkeypatch):
    monkeypatch.setattr(game_module, "read_frames", lambda path, pads: [])
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


@pytest.fixture(scope="module")
def regulation():
    return read_game(real_replays.replay(real_replays.REGULATION))


def test_touches_are_repeatable_between_parses(regulation):
    """Regression: same-frame touches swapped, which changed passing stats."""
    path = real_replays.replay(real_replays.REGULATION)
    assert read_game(path, regulation.header).touches == regulation.touches


def test_real_games_show_whether_they_went_to_overtime(counted, regulation):
    """Regression: current headers carry no overtime flag, so every game said no."""
    # 2-1, settled by an overtime goal
    game = counted[0]
    assert _went_to_overtime(game) is True
    assert any(frame.overtime for frame in game.frames)
    # 1-4 in regulation
    assert _went_to_overtime(regulation) is False
    assert not any(frame.overtime for frame in regulation.frames)


def test_real_games_carry_the_games_own_clock(counted, regulation):
    for game in (counted[0], regulation):
        assert game.frames[0].seconds_remaining == 300


def test_real_games_name_their_playlist(regulation):
    # Ranked standard
    assert regulation.playlist_id == 13
    assert playlist_of(regulation.header, regulation.playlist_id) == "STANDARD"
    hoops = read_game(real_replays.replay(real_replays.HOOPS))
    # Hoops has a number of its own, so it stays an extra mode
    assert hoops.playlist_id == 27
    assert playlist_of(hoops.header, hoops.playlist_id) == EXTRA_MODE
