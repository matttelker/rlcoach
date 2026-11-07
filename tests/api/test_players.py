"""Tests for players API endpoints."""

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
        ),
        preferences=PreferencesConfig(
            primary_playlist="DOUBLES",
            target_rank="GC1",
        ),
    )
    config.paths.data_dir.mkdir(parents=True, exist_ok=True)
    return config


@pytest.fixture
def db_with_players(mock_config):
    """Initialize database with player test data."""
    from rlcoach.db.models import Player, PlayerGameStats, Replay
    from rlcoach.db.session import create_session, init_db, reset_engine

    init_db(mock_config.db_path)
    session = create_session()

    session.add(
        Player(
            player_id="steam:me123",
            display_name="TestPlayer",
            is_me=True,
        )
    )
    session.add(
        Player(
            player_id="steam:teammate1",
            display_name="Teammate1",
            is_me=False,
            is_tagged_teammate=True,
            teammate_notes="Good rotation",
        )
    )
    session.add(
        Player(
            player_id="steam:teammate2",
            display_name="Teammate2",
            is_me=False,
        )
    )
    session.add(
        Player(
            player_id="epic:opponent1",
            display_name="Opponent1",
            is_me=False,
        )
    )
    # Seen once, but the game didn't load, so it isn't a game with me
    session.add(
        Player(
            player_id="epic:failed_ingest",
            display_name="FailedIngest",
            is_me=False,
        )
    )

    for i in range(5):
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
                my_score=2,
                opponent_score=1,
                result="WIN",
            )
        )
        session.add(
            PlayerGameStats(
                replay_id=f"replay_{i}",
                player_id="steam:teammate1",
                team="BLUE",
                is_me=False,
                is_teammate=True,
                goals=1,
                assists=1,
                saves=2,
                shots=3,
                first_man_pct=40.0,
                second_man_pct=35.0,
                third_man_pct=25.0,
                bcpm=360.0,
                avg_boost=35.0,
                behind_ball_pct=55.0,
                time_last_defender_s=60.0,
            )
        )
        # Teammate2 played the first 3 games, Opponent1 the first 2
        for player_id, team, games in (
            ("steam:teammate2", "BLUE", 3),
            ("epic:opponent1", "ORANGE", 2),
        ):
            if i < games:
                session.add(
                    PlayerGameStats(
                        replay_id=f"replay_{i}",
                        player_id=player_id,
                        team=team,
                        is_me=False,
                        is_teammate=team == "BLUE",
                    )
                )

    session.commit()
    session.close()

    yield mock_config

    reset_engine()


@pytest.fixture
def client(db_with_players):
    """Create a test client with player data."""
    with patch("rlcoach.api.app.get_config", return_value=db_with_players):
        from rlcoach.api.app import create_app

        app = create_app()
        yield TestClient(app)


class TestPlayersListEndpoint:
    """Tests for GET /players."""

    def test_players_list_returns_paginated(self, client):
        """Should return paginated list of players."""
        response = client.get("/players")
        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert len(data["items"]) > 0

    def test_players_filter_by_tagged(self, client):
        """Should filter by tagged status."""
        response = client.get("/players?tagged=true")
        assert response.status_code == 200
        data = response.json()

        for player in data["items"]:
            assert player["is_tagged_teammate"]

    def test_players_filter_by_min_games(self, client):
        """Should filter by minimum games."""
        response = client.get("/players?min_games=3")
        assert response.status_code == 200
        data = response.json()

        assert [p["display_name"] for p in data["items"]] == ["Teammate1", "Teammate2"]

    def test_players_count_the_games_stored_with_them(self, client):
        """Most games first, counted from stored games, not ingest attempts."""
        data = client.get("/players").json()
        counts = [(p["display_name"], p["games_with_me"]) for p in data["items"]]
        assert counts == [
            ("Teammate1", 5),
            ("Teammate2", 3),
            ("Opponent1", 2),
            ("FailedIngest", 0),
        ]

    def test_players_sort_by_fewest_games(self, client):
        data = client.get("/players?sort=games_with_me").json()
        assert [p["games_with_me"] for p in data["items"]] == [0, 2, 3, 5]

    def test_players_excludes_me(self, client):
        """Should exclude the 'me' player by default."""
        response = client.get("/players")
        data = response.json()

        for player in data["items"]:
            assert not player["is_me"]


class TestPlayerDetailEndpoint:
    """Tests for GET /players/{id}."""

    def test_player_get_by_id(self, client):
        """Should return player details."""
        response = client.get("/players/steam:teammate1")
        assert response.status_code == 200
        data = response.json()

        assert data["player_id"] == "steam:teammate1"
        assert data["display_name"] == "Teammate1"
        assert data["games_with_me"] == 5

    def test_player_not_found(self, client):
        """Should return 404 for nonexistent player."""
        response = client.get("/players/nonexistent")
        assert response.status_code == 404


class TestPlayerTagEndpoint:
    """Tests for POST /players/{id}/tag."""

    def test_tag_player(self, client):
        """Should tag a player as teammate."""
        response = client.post(
            "/players/steam:teammate2/tag", json={"notes": "Great passes"}
        )
        assert response.status_code == 200
        data = response.json()

        assert data["is_tagged_teammate"]
        assert data["teammate_notes"] == "Great passes"

    def test_untag_player(self, client):
        """Should untag a player."""
        response = client.post("/players/steam:teammate1/tag", json={"tagged": False})
        assert response.status_code == 200
        data = response.json()

        assert not data["is_tagged_teammate"]

    def test_tag_nonexistent_player(self, client):
        """Should return 404 for nonexistent player."""
        response = client.post("/players/nonexistent/tag", json={"notes": "test"})
        assert response.status_code == 404
