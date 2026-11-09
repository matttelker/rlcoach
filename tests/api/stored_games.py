"""A small database of games for the API tests, and a config to go with it."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from rlcoach.config import IdentityConfig, PathsConfig, PreferencesConfig, RLCoachConfig
from rlcoach.db.models import Benchmark, Player, PlayerGameStats, Replay
from rlcoach.db.session import create_session

TODAY = date.today()


def make_config(tmp_path: Path, playlist: str = "STANDARD") -> RLCoachConfig:
    return RLCoachConfig(
        identity=IdentityConfig(platform_ids=["epic:me"]),
        paths=PathsConfig(watch_folder=tmp_path / "replays", data_dir=tmp_path),
        preferences=PreferencesConfig(primary_playlist=playlist, target_rank="GC"),
    )


def add_game(
    session,
    replay_id: str,
    *,
    days_ago: int = 0,
    playlist: str = "STANDARD",
    result: str = "WIN",
    score: tuple[int, int] = (2, 1),
    map_name: str = "Stadium_P",
    me: dict | None = None,
    others: dict[str, dict] | None = None,
) -> None:
    """One game with you and anyone in `others`, by player id, with their stats."""
    played = datetime(2026, 1, 1, 12, tzinfo=UTC) + timedelta(days=100 - days_ago)
    session.add(
        Replay(
            replay_id=replay_id,
            source_file=f"C:/replays/{replay_id}.replay",
            file_hash=replay_id,
            played_at_utc=played,
            play_date=TODAY - timedelta(days=days_ago),
            map=map_name,
            playlist=playlist,
            team_size=3,
            duration_seconds=320.5,
            overtime=False,
            my_player_id="epic:me",
            my_team="BLUE",
            my_score=score[0],
            opponent_score=score[1],
            result=result,
        )
    )
    rows = {"epic:me": me or {}, **(others or {})}
    for player_id, stats in rows.items():
        session.add(
            PlayerGameStats(
                replay_id=replay_id,
                player_id=player_id,
                team="BLUE" if player_id == "epic:me" else "ORANGE",
                is_me=player_id == "epic:me",
                **stats,
            )
        )


def add_players(session, *players: tuple[str, str]) -> None:
    session.add(Player(player_id="epic:me", display_name="Me", is_me=True))
    for player_id, name in players:
        session.add(
            Player(
                player_id=player_id,
                display_name=name,
                platform=player_id.split(":")[0],
                is_me=False,
                first_seen_utc=datetime(2026, 1, 1, tzinfo=UTC),
                last_seen_utc=datetime(2026, 2, 1, tzinfo=UTC),
            )
        )


def add_benchmark(session, metric, median, p25, p75, playlist="STANDARD", rank="GC"):
    session.add(
        Benchmark(
            metric=metric,
            playlist=playlist,
            rank_tier=rank,
            median_value=median,
            p25_value=p25,
            p75_value=p75,
            elite_threshold=p75 * 1.2,
            source="test",
        )
    )


def store(*steps) -> None:
    """Run each step with one session, then commit."""
    with create_session() as session:
        for step in steps:
            step(session)
        session.commit()
