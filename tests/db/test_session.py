"""Tests for opening the database."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect

from rlcoach.db.models import Player
from rlcoach.db.session import create_session, get_session, init_db, reset_engine


@pytest.fixture(autouse=True)
def closed():
    reset_engine()
    yield
    reset_engine()


def test_sessions_need_an_open_database():
    with pytest.raises(RuntimeError, match="init_db"):
        create_session()


def test_opening_a_file_creates_its_folder_and_tables(tmp_path):
    path = tmp_path / "nested" / "rlcoach.db"
    engine = init_db(path)
    assert path.exists()
    assert {"replays", "players", "player_game_stats", "benchmarks"} <= set(
        inspect(engine).get_table_names()
    )


def test_rows_outlive_the_session_and_the_engine(tmp_path):
    path = tmp_path / "rlcoach.db"
    init_db(path)
    with create_session() as session:
        player = Player(player_id="epic:a", display_name="A")
        session.add(player)
        session.commit()
    # Objects stay readable after commit, since the API returns them
    assert player.display_name == "A"
    reset_engine()
    init_db(path)
    with create_session() as session:
        assert session.get(Player, "epic:a").display_name == "A"


def test_a_missing_table_appears_in_an_existing_database(tmp_path):
    path = tmp_path / "rlcoach.db"
    engine = init_db(path)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TABLE benchmarks")
    reset_engine()
    assert "benchmarks" in inspect(init_db(path)).get_table_names()


def test_the_request_session_closes_after_the_request():
    init_db()
    sessions = get_session()
    session = next(sessions)
    session.add(Player(player_id="epic:b", display_name="B"))
    with pytest.raises(StopIteration):
        next(sessions)
    # Closing dropped the uncommitted row
    with create_session() as fresh:
        assert fresh.get(Player, "epic:b") is None
