"""Tests for the grades endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from rlcoach.analysis.mistakes import GoalMoment, GoalReview, Mistake, MistakeReport


@pytest.fixture
def client(tmp_path):
    from rlcoach.config import (
        IdentityConfig,
        PathsConfig,
        PreferencesConfig,
        RLCoachConfig,
    )
    from rlcoach.db.models import Player, Replay
    from rlcoach.db.reviews import save_review
    from rlcoach.db.session import create_session, init_db, reset_engine

    config = RLCoachConfig(
        identity=IdentityConfig(platform_ids=["epic:me"], display_names=["Me"]),
        paths=PathsConfig(
            watch_folder=tmp_path / "replays",
            data_dir=tmp_path / "data",
            reports_dir=tmp_path / "reports",
        ),
        preferences=PreferencesConfig(primary_playlist="STANDARD", target_rank="GC1"),
    )
    config.paths.data_dir.mkdir(parents=True, exist_ok=True)
    init_db(config.db_path)
    session = create_session()
    session.add(Player(player_id="epic:me", display_name="Me", is_me=True))
    session.add(
        Replay(
            replay_id="g1",
            source_file="/replays/g1.replay",
            file_hash="g1",
            played_at_utc=datetime(2026, 11, 5, tzinfo=UTC),
            play_date=date(2026, 11, 5),
            map="Stadium_P",
            playlist="STANDARD",
            team_size=3,
            duration_seconds=300.0,
            my_player_id="epic:me",
            my_team="ORANGE",
        )
    )
    session.commit()
    session.close()
    save_review(
        "g1",
        "epic:me",
        MistakeReport(
            player="Me",
            team="ORANGE",
            map_name="Stadium_P",
            final_score="0-1",
            goals=[
                GoalReview(
                    120.0, "3:00", "0-0", "Them", True, "You were beaten.", (), 180.0
                )
            ],
            mistakes=[
                Mistake(
                    kind="clear_given_back",
                    t=110.5,
                    frame=0,
                    clock="3:09",
                    score="0-0",
                    duration=0.0,
                    what="Your clear went to an opponent.",
                    instead="Clear to the side wall.",
                    category="clearing",
                    seconds_left=189.5,
                )
            ],
            clears={"clears": 1, "given_back": 1},
            player_id="epic:me",
            goal_timeline=[
                GoalMoment(
                    120.0,
                    "3:00",
                    180.0,
                    "0-0",
                    False,
                    "Them",
                    False,
                    False,
                    False,
                    False,
                )
            ],
        ),
    )

    with patch("rlcoach.api.app.get_config", return_value=config):
        from rlcoach.api.app import create_app

        yield TestClient(create_app())
    reset_engine()


FLAG = {"item": "mistake", "kind": "clear_given_back", "t": 110.5}
GOAL = {"item": "goal", "t": 120.0}


def test_grading_a_flag_shows_on_the_review_and_in_the_tally(client):
    response = client.put("/replays/g1/grades", json={**FLAG, "grade": "right"})
    assert response.status_code == 200
    assert response.json() == {
        "item": "mistake",
        "ref": "clear_given_back@110.50",
        "grade": "right",
    }

    review = client.get("/replays/g1/review").json()
    assert review["mistakes"][0]["grade"] == "right"
    assert review["goals"][0]["grade"] is None

    rules = client.get("/grades").json()["rules"]
    assert rules == [
        {
            "item": "mistake",
            "kind": "clear_given_back",
            "label": "Clear given back",
            "right": 1,
            "wrong": 0,
        }
    ]


def test_grading_a_goal_verdict_and_clearing_it(client):
    client.put("/replays/g1/grades", json={**GOAL, "grade": "wrong"})
    assert client.get("/replays/g1/review").json()["goals"][0]["grade"] == "wrong"
    assert client.get("/grades").json()["rules"][0]["label"] == "Goal put on you"

    client.put("/replays/g1/grades", json={**GOAL, "grade": None})
    assert client.get("/replays/g1/review").json()["goals"][0]["grade"] is None
    assert client.get("/grades").json() == {"rules": []}


def test_a_flag_needs_its_kind(client):
    response = client.put(
        "/replays/g1/grades", json={"item": "mistake", "t": 110.5, "grade": "right"}
    )
    assert response.status_code == 400


def test_a_call_the_review_doesnt_make_404s(client):
    response = client.put(
        "/replays/g1/grades", json={**FLAG, "t": 50.0, "grade": "right"}
    )
    assert response.status_code == 404
    response = client.put("/replays/nope/grades", json={**FLAG, "grade": "right"})
    assert response.status_code == 404


def test_an_unknown_grade_is_rejected(client):
    response = client.put("/replays/g1/grades", json={**FLAG, "grade": "maybe"})
    assert response.status_code == 422
