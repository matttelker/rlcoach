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
from rlcoach.identity import build_player_identities
from rlcoach.parser import read_header
from rlcoach.parser.types import Header, PlayerInfo
from rlcoach.pipeline import IngestionStatus, process_replay_file
from tests.fixtures import real_replays
from tests.fixtures.builders import create_simple_replay_frames

ME = "steam:1"


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


@pytest.fixture
def real() -> Path:
    return real_replays.replay(real_replays.REGULATION)


def test_a_real_replay_is_stored_and_reviewed_from_one_parse(db, monkeypatch, real):
    # Whoever is first in the header plays me
    me = build_player_identities(read_header(real).players)[0]
    scores = {"BLUE": 1, "ORANGE": 4}
    header = Counting(pipeline.read_header)
    network = Counting(game_module.read_frames)
    monkeypatch.setattr(pipeline, "read_header", header)
    monkeypatch.setattr(game_module, "read_frames", network)
    config = _config(platform_ids=[me.canonical_id])

    result = process_replay_file(real, config)

    assert result.status == IngestionStatus.SUCCESS, result.error
    assert result.replay_id == result.file_hash
    assert (header.calls, network.calls) == (1, 1)
    with create_session() as session:
        replay = session.get(Replay, result.replay_id)
        review = session.get(GameReview, result.replay_id)
        mine = session.query(PlayerGameStats).filter_by(is_me=True).one()
        player = session.get(Player, me.canonical_id)
    assert (replay.playlist, replay.map, replay.my_team) == (
        "STANDARD",
        "street_p",
        me.team,
    )
    theirs = "ORANGE" if me.team == "BLUE" else "BLUE"
    assert (replay.my_score, replay.opponent_score) == (scores[me.team], scores[theirs])
    assert replay.result == ("WIN" if me.team == "ORANGE" else "LOSS")
    assert replay.source_file == str(real)
    assert (_count(Player), _count(PlayerGameStats)) == (6, 6)
    assert (mine.player_id, player.display_name, player.is_me) == (
        me.canonical_id,
        me.display_name,
        True,
    )
    assert (review.status, review.player_id) == ("ok", me.canonical_id)

    # Loading it again stops at the hash, before checking or parsing the file
    monkeypatch.setattr(pipeline, "check_replay_file", lambda p: pytest.fail("checked"))
    again = process_replay_file(real, config)
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
        match_type="Online",
        map_name="Stadium_P",
        team_size=1,
        started_at_utc="2026-03-01T03:00:00Z",
        team0_score=2,
        players=[
            PlayerInfo(name="Me", platform_ids={"epic": "me"}, team=0),
            PlayerInfo(name="Smurf", platform_ids={"steam": "9"}, team=1),
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


def test_a_damaged_replay_is_an_error_before_parsing(db, tmp_path, monkeypatch, real):
    damaged = tmp_path / "damaged.replay"
    shutil.copy(real, damaged)
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
