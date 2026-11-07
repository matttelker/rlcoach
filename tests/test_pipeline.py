"""Tests for loading one replay into the database."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import rlcoach.game as game_module
import rlcoach.pipeline as pipeline
from rlcoach.config import IdentityConfig, PathsConfig, PreferencesConfig, RLCoachConfig
from rlcoach.db.models import GameReview, Player, PlayerGameStats, Replay
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.game import game_from_frames
from rlcoach.parser.types import Header, PlayerInfo
from rlcoach.pipeline import IngestionStatus, process_replay_file
from tests.fixtures.builders import create_simple_replay_frames

REPLAY = Path("Replay_files/6804bd43-5415-49f4-b7d0-31b168c871ed.replay")
ME = "steam:76561199836440914"


def _config(**identity):
    return RLCoachConfig(
        identity=IdentityConfig(**identity),
        paths=PathsConfig(watch_folder=Path("w"), data_dir=Path("d")),
        preferences=PreferencesConfig(timezone="UTC"),
    )


def _count(model):
    with create_session() as session:
        return session.query(model).count()


@pytest.fixture
def db():
    init_db()
    yield
    reset_engine()


class Counting:
    def __init__(self, function):
        self.function, self.calls = function, 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self.function(*args, **kwargs)


@pytest.mark.skipif(not REPLAY.exists(), reason="replay fixture missing")
def test_a_real_replay_is_stored_and_reviewed_from_one_parse(db, monkeypatch):
    header = Counting(pipeline.read_header)
    network = Counting(game_module.read_network)
    monkeypatch.setattr(pipeline, "read_header", header)
    monkeypatch.setattr(game_module, "read_network", network)
    config = _config(platform_ids=[ME])

    result = process_replay_file(REPLAY, config)

    assert result.status == IngestionStatus.SUCCESS, result.error
    assert result.replay_id == result.file_hash
    assert (header.calls, network.calls) == (1, 1)
    with create_session() as session:
        replay = session.get(Replay, result.replay_id)
        review = session.get(GameReview, result.replay_id)
        mine = session.query(PlayerGameStats).filter_by(is_me=True).one()
        me = session.get(Player, ME)
    assert (replay.playlist, replay.map, replay.my_team) == (
        "DOUBLES",
        "Wasteland_GRS_P",
        "BLUE",
    )
    assert (replay.my_score, replay.opponent_score, replay.result) == (1, 5, "LOSS")
    assert replay.source_file == str(REPLAY)
    assert (_count(Player), _count(PlayerGameStats)) == (4, 4)
    assert (mine.player_id, me.display_name, me.is_me) == (ME, "tlsc.", True)
    assert (review.status, review.player_id) == ("ok", ME)

    # Loading it again stops at the hash, before checking or parsing the file
    monkeypatch.setattr(pipeline, "check_replay_file", lambda p: pytest.fail("checked"))
    again = process_replay_file(REPLAY, config)
    assert (again.status, again.file_hash) == (
        IngestionStatus.DUPLICATE,
        result.file_hash,
    )
    assert header.calls == 1


@pytest.fixture
def fake_replay(tmp_path, monkeypatch):
    """A file whose header and game are made up, so no parsing happens."""
    path = tmp_path / "fake.replay"
    path.write_bytes(b"fake replay bytes")
    header = Header(
        playlist_id="inferred_1",
        map_name="Stadium_P",
        team_size=1,
        started_at_utc="2026-03-01T03:00:00Z",
        team0_score=2,
        players=[
            PlayerInfo(name="Me", platform_id="Epic|me", team=0),
            PlayerInfo(name="Smurf", platform_id="Steam|9", team=1),
        ],
    )
    frames = create_simple_replay_frames(
        duration_seconds=2.0, players=[("epic:me", 0), ("steam:9", 1)]
    )
    monkeypatch.setattr(pipeline, "check_replay_file", lambda p: None)
    monkeypatch.setattr(pipeline, "read_header", lambda p: header)
    monkeypatch.setattr(
        pipeline, "read_game", lambda p, h: game_from_frames(p, h, frames)
    )
    return path


def test_a_game_with_an_excluded_account_is_skipped(db, fake_replay):
    config = _config(display_names=["Nobody"], excluded_names=["smurf"])
    result = process_replay_file(fake_replay, config)
    assert result.status == IngestionStatus.EXCLUDED
    assert _count(Replay) == 0


def test_a_game_without_you_stores_nothing(db, fake_replay):
    result = process_replay_file(fake_replay, _config(display_names=["Nobody"]))
    assert result.status == IngestionStatus.PLAYER_NOT_FOUND
    assert "[identity]" in result.error
    assert (_count(Replay), _count(Player)) == (0, 0)


def test_a_failed_review_still_stores_the_game(db, fake_replay, monkeypatch):
    def broken(*args):
        raise RuntimeError("review broke")

    monkeypatch.setattr(pipeline, "store_review", broken)
    result = process_replay_file(fake_replay, _config(platform_ids=["epic:me"]))
    assert result.status == IngestionStatus.SUCCESS
    assert (_count(Replay), _count(GameReview)) == (1, 0)


def test_a_failed_load_is_an_error_with_the_reason(db, fake_replay, monkeypatch):
    def broken(*args):
        raise ValueError("parser broke")

    monkeypatch.setattr(pipeline, "read_game", broken)
    result = process_replay_file(fake_replay, _config(platform_ids=["epic:me"]))
    assert (result.status, result.error) == (IngestionStatus.ERROR, "parser broke")
    assert _count(Replay) == 0


@pytest.mark.skipif(not REPLAY.exists(), reason="replay fixture missing")
def test_a_damaged_replay_is_an_error_before_parsing(db, tmp_path, monkeypatch):
    damaged = tmp_path / "damaged.replay"
    shutil.copy(REPLAY, damaged)
    data = bytearray(damaged.read_bytes())
    data[len(data) // 2] ^= 0xFF
    damaged.write_bytes(bytes(data))
    monkeypatch.setattr(pipeline, "read_header", lambda p: pytest.fail("parsed"))
    result = process_replay_file(damaged, _config(platform_ids=[ME]))
    assert result.status == IngestionStatus.ERROR
    assert "checksum is wrong" in result.error


def test_a_missing_file_is_an_error(db, tmp_path):
    result = process_replay_file(tmp_path / "gone.replay", _config(platform_ids=[ME]))
    assert result.status == IngestionStatus.ERROR
    assert "not found" in result.error
