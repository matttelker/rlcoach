"""Transform JSON reports into database records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..config import IdentityConfig, RLCoachConfig, compute_play_date
from ..identity import PlayerIdentityResolver
from .models import Player, PlayerGameStats, Replay
from .session import create_session


class ReplayExistsError(Exception):
    """Raised when trying to insert a duplicate replay."""

    pass


class PlayerNotFoundError(Exception):
    """Raised when player identity cannot be resolved."""

    pass


def _as_utc(value: datetime | None) -> datetime | None:
    """Attach UTC to the offset-less datetimes SQLite returns."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _played_at_utc(metadata: dict[str, Any]) -> datetime:
    """Return when a report's game was played, or now if it is unknown."""
    played_at_str = metadata.get("started_at_utc", "")
    if played_at_str:
        return datetime.fromisoformat(played_at_str.replace("Z", "+00:00"))
    return datetime.now(UTC)


def _record_sighting(player: Player, seen_at: datetime) -> None:
    """Widen a player's first and last seen range to include a game.

    Replays can be ingested in any order, so the newest game is not always last.
    """
    first_seen = _as_utc(player.first_seen_utc)
    last_seen = _as_utc(player.last_seen_utc)
    player.first_seen_utc = min(first_seen, seen_at) if first_seen else seen_at
    player.last_seen_utc = max(last_seen, seen_at) if last_seen else seen_at


def upsert_players(
    players: list[dict[str, Any]],
    identity_config: IdentityConfig,
    seen_at: datetime | None = None,
) -> None:
    """Create or update player records.

    Args:
        players: List of player dicts with 'player_id' and 'display_name'
        identity_config: Config for determining who is "me"
        seen_at: When the game was played (default: now)
    """
    resolver = PlayerIdentityResolver(identity_config)
    seen_at = seen_at or datetime.now(UTC)

    session = create_session()
    try:
        for p in players:
            pid = p["player_id"]
            display_name = p["display_name"]
            is_me = resolver.is_me(pid, display_name)
            platform = pid.split(":")[0] if ":" in pid else None

            existing = session.get(Player, pid)

            if existing:
                # Update
                existing.display_name = display_name
                _record_sighting(existing, seen_at)
            else:
                # Create
                player = Player(
                    player_id=pid,
                    display_name=display_name,
                    platform=platform,
                    is_me=is_me,
                    first_seen_utc=seen_at,
                    last_seen_utc=seen_at,
                )
                session.add(player)

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _check_not_stored(session: Session, replay_id: str, file_hash: str) -> None:
    if session.get(Replay, replay_id):
        raise ReplayExistsError(f"Replay with replay_id '{replay_id}' already exists")
    if session.query(Replay).filter_by(file_hash=file_hash).first():
        raise ReplayExistsError(f"Replay with file_hash '{file_hash}' already exists")


def check_not_stored(file_hash: str) -> None:
    """Raise ReplayExistsError if this replay file is already stored.

    A report's replay_id is the file's SHA256 (see generate_report), so the
    file hash alone runs both of insert_replay's duplicate checks, before the
    replay is parsed.
    """
    session = create_session()
    try:
        _check_not_stored(session, replay_id=file_hash, file_hash=file_hash)
    finally:
        session.close()


def insert_replay(
    report: dict[str, Any],
    file_hash: str,
    config: RLCoachConfig,
) -> str:
    """Insert a replay record into the database.

    Args:
        report: Parsed JSON report from generate_report()
        file_hash: SHA256 hash of the replay file
        config: RLCoach configuration

    Returns:
        The replay_id

    Raises:
        ReplayExistsError: If replay_id or file_hash already exists
        PlayerNotFoundError: If player identity cannot be resolved
    """
    replay_id = report["replay_id"]
    metadata = report["metadata"]
    teams = report["teams"]
    players = report["players"]

    session = create_session()
    try:
        _check_not_stored(session, replay_id, file_hash)

        resolver = PlayerIdentityResolver(config.identity)
        my_player = resolver.find_me(players)
        if not my_player:
            raise PlayerNotFoundError(
                f"Could not identify player in replay. "
                f"Config platform_ids: {config.identity.platform_ids}, "
                f"display_names: {config.identity.display_names}"
            )

        my_player_id = my_player["player_id"]
        my_team = my_player["team"]

        my_score = (
            teams["blue"]["score"] if my_team == "BLUE" else teams["orange"]["score"]
        )
        opp_score = (
            teams["orange"]["score"] if my_team == "BLUE" else teams["blue"]["score"]
        )

        if my_score > opp_score:
            result = "WIN"
        elif my_score < opp_score:
            result = "LOSS"
        else:
            result = "DRAW"

        # Parse timestamp and compute play_date with timezone
        played_at_str = metadata.get("started_at_utc", "")
        if played_at_str:
            played_at_str = played_at_str.replace("Z", "+00:00")
            played_at_utc = datetime.fromisoformat(played_at_str)
        else:
            played_at_utc = datetime.now(UTC)

        play_date = compute_play_date(played_at_utc, config.preferences.timezone)

        replay = Replay(
            replay_id=replay_id,
            source_file=report.get("source_file", ""),
            file_hash=file_hash,
            played_at_utc=played_at_utc,
            play_date=play_date,
            map=metadata.get("map", "unknown"),
            playlist=metadata.get("playlist", "UNKNOWN"),
            team_size=metadata.get("team_size", 2),
            duration_seconds=metadata.get("duration_seconds", 0),
            overtime=metadata.get("overtime", False),
            my_player_id=my_player_id,
            my_team=my_team,
            my_score=my_score,
            opponent_score=opp_score,
            result=result,
        )
        session.add(replay)
        session.commit()

        return replay_id

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def insert_player_stats(report: dict[str, Any], config: RLCoachConfig) -> None:
    """Insert player game stats from a report.

    Args:
        report: Parsed JSON report with 'analysis.per_player' data
        config: RLCoach configuration for identity resolution
    """
    replay_id = report["replay_id"]
    players = report["players"]
    per_player = report.get("analysis", {}).get("per_player", {})

    resolver = PlayerIdentityResolver(config.identity)
    my_player = resolver.find_me(players)
    my_player_id = my_player["player_id"] if my_player else None
    my_team = my_player["team"] if my_player else None

    session = create_session()
    try:
        for p in players:
            pid = p["player_id"]
            team = p["team"]
            player_data = per_player.get(pid, {})

            fundamentals = player_data.get("fundamentals", {})
            boost = player_data.get("boost", {})
            movement = player_data.get("movement", {})
            positioning = player_data.get("positioning", {})
            challenges = player_data.get("challenges", {})
            kickoffs = player_data.get("kickoffs", {})
            mechanics = player_data.get("mechanics", {})
            recovery = player_data.get("recovery", {})
            defense = player_data.get("defense", {})
            xg = player_data.get("xg", {})

            is_me = pid == my_player_id
            is_teammate = not is_me and team == my_team
            is_opponent = team != my_team

            stats = PlayerGameStats(
                replay_id=replay_id,
                player_id=pid,
                team=team,
                is_me=is_me,
                is_teammate=is_teammate,
                is_opponent=is_opponent,
                # Fundamentals
                goals=fundamentals.get("goals"),
                assists=fundamentals.get("assists"),
                saves=fundamentals.get("saves"),
                shots=fundamentals.get("shots"),
                shooting_pct=fundamentals.get("shooting_percentage"),
                score=fundamentals.get("score"),
                demos_inflicted=fundamentals.get("demos_inflicted"),
                demos_taken=fundamentals.get("demos_taken"),
                bcpm=boost.get(
                    "bpm"
                ),  # Boost amount per minute (industry-standard BCPM)
                avg_boost=boost.get("avg_boost"),
                time_zero_boost_s=boost.get("time_zero_boost_s"),
                time_full_boost_s=boost.get("time_full_boost_s"),
                boost_collected=boost.get("boost_collected"),
                boost_stolen=boost.get("boost_stolen"),
                small_pads=boost.get("small_pads"),
                big_pads=boost.get("big_pads"),
                # Movement
                avg_speed_kph=movement.get("avg_speed_kph"),
                distance_km=movement.get("distance_km"),
                max_speed_kph=movement.get("max_speed_kph"),
                time_supersonic_s=movement.get("time_supersonic_s"),
                time_slow_s=movement.get("time_slow_s"),
                time_ground_s=movement.get("time_ground_s"),
                time_low_air_s=movement.get("time_low_air_s"),
                time_high_air_s=movement.get("time_high_air_s"),
                # Positioning
                behind_ball_pct=positioning.get("behind_ball_pct"),
                time_offensive_third_s=positioning.get("time_offensive_third_s"),
                time_middle_third_s=positioning.get("time_middle_third_s"),
                time_defensive_third_s=positioning.get("time_defensive_third_s"),
                avg_distance_to_ball_m=positioning.get("avg_distance_to_ball_m"),
                avg_distance_to_teammate_m=positioning.get(
                    "avg_distance_to_teammate_m"
                ),
                first_man_pct=positioning.get("first_man_pct"),
                second_man_pct=positioning.get("second_man_pct"),
                third_man_pct=positioning.get("third_man_pct"),
                # Challenges - Map from analysis keys (wins/losses/neutral)
                challenge_wins=challenges.get("wins"),
                challenge_losses=challenges.get("losses"),
                challenge_neutral=challenges.get("neutral"),
                first_to_ball_pct=challenges.get("first_to_ball_pct"),
                # Kickoffs - Map from analysis keys
                kickoffs_participated=kickoffs.get("count"),
                kickoff_first_touches=kickoffs.get(
                    "first_possession"
                ),  # Closest available metric
                # Mechanics
                wavedash_count=mechanics.get("wavedash_count"),
                halfflip_count=mechanics.get("halfflip_count"),
                speedflip_count=mechanics.get("speedflip_count"),
                aerial_count=mechanics.get("aerial_count"),
                flip_cancel_count=mechanics.get("flip_cancel_count"),
                # Recovery - Map from analysis keys
                total_recoveries=recovery.get("total_recoveries"),
                avg_recovery_momentum=recovery.get("average_momentum_retained"),
                # Defense - Map from analysis keys
                time_last_defender_s=defense.get("time_as_last_defender"),
                time_shadow_defense_s=defense.get("time_shadowing"),
                # xG
                total_xg=xg.get("total_xg"),
            )
            session.add(stats)

        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def write_report(
    report: dict[str, Any],
    file_hash: str,
    config: RLCoachConfig,
) -> str:
    """Write a complete report to the database.

    This is the main entry point for persisting replay data. It:
    1. Upserts all players
    2. Inserts the replay record
    3. Inserts player stats

    Args:
        report: Parsed JSON report from generate_report()
        file_hash: SHA256 hash of the replay file
        config: RLCoach configuration

    Returns:
        The replay_id

    Raises:
        ReplayExistsError: If replay already exists
        PlayerNotFoundError: If player identity cannot be resolved
    """
    # Step 1: Upsert players
    upsert_players(
        report["players"],
        config.identity,
        seen_at=_played_at_utc(report.get("metadata", {})),
    )

    # Step 2: Insert replay record
    replay_id = insert_replay(report, file_hash, config)

    # Step 3: Insert player stats (with role flags)
    insert_player_stats(report, config)

    return replay_id
