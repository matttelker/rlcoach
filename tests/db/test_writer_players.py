from datetime import datetime, timezone

import pytest

from rlcoach.config import IdentityConfig
from rlcoach.db.models import Player
from rlcoach.db.session import create_session, init_db, reset_engine
from rlcoach.db.writer import upsert_players


@pytest.fixture(autouse=True)
def reset_db():
    yield
    reset_engine()


def test_upsert_players_creates_new(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    identity = IdentityConfig(platform_ids=["steam:me123"])
    players = [
        {"player_id": "steam:me123", "display_name": "MePlayer", "team": "BLUE"},
        {
            "player_id": "steam:other456",
            "display_name": "OtherPlayer",
            "team": "ORANGE",
        },
    ]

    upsert_players(players, identity)

    session = create_session()
    try:
        me = session.get(Player, "steam:me123")
        assert me is not None
        assert me.is_me is True
        assert me.games_with_me == 0  # I don't count as game with myself

        other = session.get(Player, "steam:other456")
        assert other is not None
        assert other.is_me is False
        assert other.games_with_me == 1  # This player was in a game with me
    finally:
        session.close()


def test_upsert_players_updates_existing(tmp_path):
    db_path = tmp_path / "test.db"
    init_db(db_path)

    identity = IdentityConfig(platform_ids=["steam:me123"])

    # First call
    upsert_players(
        [
            {"player_id": "steam:other456", "display_name": "OldName", "team": "BLUE"},
        ],
        identity,
    )

    # Second call with new name
    upsert_players(
        [
            {"player_id": "steam:other456", "display_name": "NewName", "team": "BLUE"},
        ],
        identity,
    )

    session = create_session()
    try:
        player = session.get(Player, "steam:other456")
        assert player.display_name == "NewName"
        assert player.games_with_me == 2  # Appeared in 2 games
    finally:
        session.close()


def test_upsert_players_records_when_the_game_was_played(tmp_path):
    init_db(tmp_path / "test.db")
    identity = IdentityConfig(display_names=["Me"])
    played_at = datetime(2024, 10, 25, 2, 49, tzinfo=timezone.utc)

    upsert_players(
        [{"player_id": "steam:123", "display_name": "Other"}],
        identity,
        seen_at=played_at,
    )

    session = create_session()
    player = session.get(Player, "steam:123")
    assert player.first_seen_utc.replace(tzinfo=timezone.utc) == played_at
    assert player.last_seen_utc.replace(tzinfo=timezone.utc) == played_at
    session.close()


def test_upsert_players_keeps_seen_range_for_out_of_order_ingest(tmp_path):
    init_db(tmp_path / "test.db")
    identity = IdentityConfig(display_names=["Me"])
    newest = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
    oldest = datetime(2022, 12, 24, 12, tzinfo=timezone.utc)
    players = [{"player_id": "steam:123", "display_name": "Other"}]

    upsert_players(players, identity, seen_at=newest)
    upsert_players(players, identity, seen_at=oldest)

    session = create_session()
    player = session.get(Player, "steam:123")
    assert player.first_seen_utc.replace(tzinfo=timezone.utc) == oldest
    assert player.last_seen_utc.replace(tzinfo=timezone.utc) == newest
    assert player.games_with_me == 2
    session.close()


def test_tagging_a_player_does_not_change_last_seen(tmp_path):
    init_db(tmp_path / "test.db")
    identity = IdentityConfig(display_names=["Me"])
    played_at = datetime(2024, 10, 25, 2, 49, tzinfo=timezone.utc)
    upsert_players(
        [{"player_id": "steam:123", "display_name": "Other"}],
        identity,
        seen_at=played_at,
    )

    session = create_session()
    session.get(Player, "steam:123").is_tagged_teammate = True
    session.commit()
    session.close()

    session = create_session()
    last_seen = session.get(Player, "steam:123").last_seen_utc
    assert last_seen.replace(tzinfo=timezone.utc) == played_at
    session.close()
