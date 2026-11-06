"""Tests for games and replays endpoints."""

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_config(tmp_path):
    """Create a mock config for testing."""
    from rlcoach.config import (
        IdentityConfig,
        PathsConfig,
        PreferencesConfig,
        RLCoachConfig,
    )

    config = RLCoachConfig(
        identity=IdentityConfig(
            platform_ids=["steam:me123"],
            display_names=["TestPlayer"],
        ),
        paths=PathsConfig(
            watch_folder=tmp_path / "replays",
            data_dir=tmp_path / "data",
            reports_dir=tmp_path / "reports",
        ),
        preferences=PreferencesConfig(
            primary_playlist="DOUBLES",
            target_rank="GC1",
        ),
    )
    config.paths.data_dir.mkdir(parents=True, exist_ok=True)
    return config


@pytest.fixture
def db_with_data(mock_config):
    """Initialize database with test data."""
    from rlcoach.db.models import Player, PlayerGameStats, Replay
    from rlcoach.db.session import create_session, init_db, reset_engine

    init_db(mock_config.db_path)
    session = create_session()

    session.add(Player(player_id="steam:me123", display_name="TestPlayer", is_me=True))

    for i in range(5):
        result = "WIN" if i % 2 == 0 else "LOSS"
        session.add(
            Replay(
                replay_id=f"replay_{i}",
                source_file=f"/path/replay_{i}.replay",
                file_hash=f"hash_{i}",
                played_at_utc=datetime(2024, 12, 23, 10 + i, 0, 0, tzinfo=UTC),
                play_date=date(2024, 12, 23),
                map="DFH Stadium",
                playlist="DOUBLES",
                team_size=2,
                duration_seconds=300.0,
                my_player_id="steam:me123",
                my_team="BLUE",
                my_score=2 if result == "WIN" else 1,
                opponent_score=1 if result == "WIN" else 2,
                result=result,
                json_report_path=f"/path/replay_{i}.json",
            )
        )
        session.add(
            PlayerGameStats(
                replay_id=f"replay_{i}",
                player_id="steam:me123",
                team="BLUE",
                is_me=True,
                goals=i,
                assists=1,
                saves=2,
                bcpm=350.0 + i * 10,
            )
        )

    session.commit()
    session.close()

    yield mock_config

    reset_engine()


@pytest.fixture
def client(db_with_data):
    """Create a test client with database data."""
    with patch("rlcoach.api.app.get_config", return_value=db_with_data):
        from rlcoach.api.app import create_app

        yield TestClient(create_app())


class TestGamesEndpoint:
    """Tests for GET /games."""

    def test_games_list_returns_paginated(self, client):
        """Should return paginated list of games."""
        response = client.get("/games")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert len(data["items"]) <= data["limit"]

    def test_games_list_filter_by_playlist(self, client):
        """Should filter by playlist."""
        response = client.get("/games?playlist=DOUBLES")
        assert response.status_code == 200
        data = response.json()

        for game in data["items"]:
            assert game["playlist"] == "DOUBLES"

    def test_games_list_filter_by_result(self, client):
        """Should filter by result."""
        response = client.get("/games?result=WIN")
        assert response.status_code == 200
        data = response.json()

        for game in data["items"]:
            assert game["result"] == "WIN"

    def test_games_list_pagination(self, client):
        """Should support pagination."""
        response = client.get("/games?limit=2&offset=0")
        assert response.status_code == 200
        data = response.json()

        assert len(data["items"]) <= 2
        assert data["limit"] == 2
        assert data["offset"] == 0

    def test_games_list_sorting(self, client):
        """Should support sorting."""
        response = client.get("/games?sort=-played_at_utc")
        assert response.status_code == 200
        data = response.json()

        # Should be sorted by date descending
        if len(data["items"]) >= 2:
            assert (
                data["items"][0]["played_at_utc"] >= data["items"][1]["played_at_utc"]
            )

    def test_games_list_rejects_unknown_sort_field(self, client):
        response = client.get("/games?sort=password_hash")

        assert response.status_code == 400
        assert response.json()["detail"].startswith("Invalid sort field.")


class TestReplayEndpoint:
    """Tests for GET /replays/{id}."""

    def test_replay_get_by_id(self, client):
        """Should return replay details."""
        response = client.get("/replays/replay_0")
        assert response.status_code == 200
        data = response.json()

        assert data["replay_id"] == "replay_0"
        assert "map" in data
        assert "playlist" in data
        assert "result" in data

    def test_replay_not_found(self, client):
        """Should return 404 for nonexistent replay."""
        response = client.get("/replays/nonexistent")
        assert response.status_code == 404

    def test_replay_includes_player_stats(self, client):
        """Should include player stats."""
        response = client.get("/replays/replay_0")
        data = response.json()

        assert "player_stats" in data
        assert len(data["player_stats"]) > 0


class TestReplayFullEndpoint:
    """Tests for GET /replays/{id}/full."""

    def test_replay_full_returns_complete_data(self, client):
        """Should return complete replay data."""
        response = client.get("/replays/replay_0/full")
        assert response.status_code == 200
        data = response.json()

        assert "replay" in data
        assert "player_stats" in data


class TestReplayPlayerNames:
    """Game detail needs a name to show for each player."""

    def test_replay_player_stats_include_display_name(self, client):
        player = client.get("/replays/replay_0").json()["player_stats"][0]

        assert player["display_name"] == "TestPlayer"
