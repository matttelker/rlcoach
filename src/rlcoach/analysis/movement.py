"""Movement and speed analysis for Rocket League replay data.

This module computes movement and speed metrics from frame data:
- Speed buckets: time in slow, boost speed, and supersonic ranges
- Ground vs air time analysis with height classifications
- Powerslide detection and duration tracking
- Aerial detection and time accounting
- Average speed calculations

All calculations use deterministic frame-by-frame analysis with
fixed thresholds for consistent results across runs.
"""

from __future__ import annotations

import math
from typing import Any

from ..events.constants import PAUSE_GAP_SECONDS
from ..field_constants import Vec3
from ..parser.types import Frame, Header, PlayerFrame
from ..physics_constants import UU_S_TO_KPH, UU_TO_METERS

# Movement analysis thresholds match Ballchasing's own figures:
# - slow speed: < 1410 uu/s, the top speed without boost
# - boost speed: 1410–2200 uu/s
# - supersonic: >= 2200 uu/s
SLOW_SPEED_MAX_UU_S = 1410.0
BOOST_SPEED_MAX_UU_S = 2200.0
MOVING_SPEED_MIN_UU_S = 10.0  # Average speed leaves out a parked car

# Height thresholds for air/ground classification (from project plan)
GROUND_HEIGHT = 20.0  # Cars rest at 17-18.4uu depending on the body
LOW_AIR_HEIGHT = 200.0
HIGH_AIR_HEIGHT = 840.0  # Ballchasing's "above the crossbar" line

# Powerslide detection thresholds
MIN_POWERSLIDE_DURATION = 0.03  # seconds; real slides average 0.13s

# Aerial detection thresholds (documented in plan)
MIN_AERIAL_HEIGHT = 200.0
MIN_AERIAL_DURATION = 0.5  # seconds

# Frame duration fallbacks
DEFAULT_FRAME_DT = 1.0 / 30.0  # conservative per-replay tick
MIN_FRAME_DT = 1e-3


def analyze_movement(
    frames: list[Frame],
    events: dict[str, list[Any]],
    player_id: str | None = None,
    team: str | None = None,
    header: Header | None = None,
) -> dict[str, Any]:
    """Analyze movement and speed metrics for a player or team.

    Args:
        frames: Normalized frame data for movement analysis
        events: Dictionary containing detected events (not used for movement)
        player_id: If provided, analyze specific player; otherwise team analysis
        team: Team filter ("BLUE" or "ORANGE"), required if player_id not provided
        header: Optional header for match context

    Returns:
        Dictionary matching schema movement definition:
        {
            "avg_speed_kph": float,
            "distance_km": float,
            "max_speed_kph": float,
            "time_slow_s": float,
            "time_boost_speed_s": float,
            "time_supersonic_s": float,
            "time_ground_s": float,
            "time_low_air_s": float,
            "time_high_air_s": float,
            "powerslide_count": int,
            "powerslide_duration_s": float,
            "aerial_count": int,
            "aerial_time_s": float
        }
    """
    if not frames:
        return _empty_movement()

    if player_id:
        return _analyze_player_movement(frames, player_id)
    elif team:
        return _analyze_team_movement(frames, team)
    else:
        return _empty_movement()


def _compute_frame_durations(frames: list[Frame]) -> list[float]:
    """Pre-compute per-frame durations with graceful fallbacks.

    Ballchasing integrates speed buckets using the replay sampling cadence
    (~30 Hz). We follow the normalized timeline timestamps when available and
    fall back to the previous good delta or a conservative default to avoid
    gaps on duplicated timestamps. A goal replay's gap is not play, so it gets
    the fallback too.
    """
    durations: list[float] = []
    prev_dt = DEFAULT_FRAME_DT

    for idx, frame in enumerate(frames):
        dt = prev_dt
        if idx < len(frames) - 1:
            next_dt = frames[idx + 1].timestamp - frame.timestamp
            if MIN_FRAME_DT < next_dt <= PAUSE_GAP_SECONDS:
                dt = next_dt
        durations.append(max(dt, MIN_FRAME_DT))
        prev_dt = durations[-1]

    return durations


def _analyze_player_movement(frames: list[Frame], player_id: str) -> dict[str, Any]:
    """Analyze movement metrics for a specific player."""

    frame_durations = _compute_frame_durations(frames)

    total_distance_uu = 0.0
    moving_time = 0.0
    max_speed_uu_s = 0.0

    time_slow = 0.0
    time_boost_speed = 0.0
    time_supersonic = 0.0
    time_ground = 0.0
    time_low_air = 0.0
    time_high_air = 0.0

    powerslide_count = 0
    powerslide_duration = 0.0
    slide_time = 0.0
    aerial_count = 0
    aerial_time = 0.0

    prev_timestamp = None
    in_aerial = False
    aerial_start = 0.0

    for idx, frame in enumerate(frames):
        player_frame = frame.get_player_by_id(player_id)
        if not player_frame:
            continue

        # Speed comes from replicated velocity, never position deltas: car
        # positions only refresh every 2-3 frames, so a delta over one frame
        # reads 2-3x the true speed on the frames where they do change, and a
        # kickoff or a respawn teleports the car.
        speed = _calculate_speed(player_frame.velocity)
        height = player_frame.position.z
        frame_dt = frame_durations[idx]

        max_speed_uu_s = max(max_speed_uu_s, speed)

        # A demolished car is off the field, so its time goes in no bucket
        if not player_frame.is_demolished:
            total_distance_uu += speed * frame_dt
            if speed >= MOVING_SPEED_MIN_UU_S:
                moving_time += frame_dt

            # Speed bucket classification using current frame's state
            if speed < SLOW_SPEED_MAX_UU_S:
                time_slow += frame_dt
            elif speed < BOOST_SPEED_MAX_UU_S:
                time_boost_speed += frame_dt
            else:
                time_supersonic += frame_dt

            # Height classification using current frame's state
            if _is_on_ground(player_frame):
                time_ground += frame_dt
            elif height <= HIGH_AIR_HEIGHT:
                time_low_air += frame_dt
            else:
                time_high_air += frame_dt

        # Powerslide detection
        if _detect_powerslide(player_frame):
            slide_time += frame_dt
        elif slide_time:
            if slide_time >= MIN_POWERSLIDE_DURATION:
                powerslide_count += 1
                powerslide_duration += slide_time
            slide_time = 0.0

        # Aerial detection
        is_aerial = height >= MIN_AERIAL_HEIGHT and not player_frame.is_on_ground
        if is_aerial and not in_aerial:
            # Starting aerial
            in_aerial = True
            aerial_start = frame.timestamp
        elif not is_aerial and in_aerial:
            aerial_count, aerial_time, in_aerial = _close_aerial(
                frame.timestamp,
                aerial_start,
                aerial_count,
                aerial_time,
            )

        prev_timestamp = frame.timestamp

    if slide_time >= MIN_POWERSLIDE_DURATION:
        powerslide_count += 1
        powerslide_duration += slide_time

    if in_aerial and prev_timestamp is not None:
        aerial_count, aerial_time, _ = _close_aerial(
            prev_timestamp,
            aerial_start,
            aerial_count,
            aerial_time,
        )

    avg_speed_kph = 0.0
    if moving_time > 0:
        avg_speed_kph = _uu_s_to_kph(total_distance_uu / moving_time)

    distance_km = _uu_to_km(total_distance_uu)
    max_speed_kph = _uu_s_to_kph(max_speed_uu_s)

    return {
        "avg_speed_kph": round(avg_speed_kph, 2),
        "distance_km": round(distance_km, 2),
        "max_speed_kph": round(max_speed_kph, 2),
        "time_slow_s": round(time_slow, 2),
        "time_boost_speed_s": round(time_boost_speed, 2),
        "time_supersonic_s": round(time_supersonic, 2),
        "time_ground_s": round(time_ground, 2),
        "time_low_air_s": round(time_low_air, 2),
        "time_high_air_s": round(time_high_air, 2),
        "powerslide_count": powerslide_count,
        "powerslide_duration_s": round(powerslide_duration, 2),
        "aerial_count": aerial_count,
        "aerial_time_s": round(aerial_time, 2),
    }


def _analyze_team_movement(frames: list[Frame], team: str) -> dict[str, Any]:
    """Analyze movement metrics for a team (aggregate all players)."""

    team_players = set()
    team_id = 0 if team == "BLUE" else 1

    for frame in frames:
        team_players.update(
            player.player_id for player in frame.get_players_by_team(team_id)
        )

    if not team_players:
        return _empty_movement()

    team_metrics = _empty_movement()
    player_count = len(team_players)

    for player_id in team_players:
        player_metrics = _analyze_player_movement(frames, player_id)

        # Sum time-based metrics
        team_metrics["time_slow_s"] += player_metrics["time_slow_s"]
        team_metrics["time_boost_speed_s"] += player_metrics["time_boost_speed_s"]
        team_metrics["time_supersonic_s"] += player_metrics["time_supersonic_s"]
        team_metrics["time_ground_s"] += player_metrics["time_ground_s"]
        team_metrics["time_low_air_s"] += player_metrics["time_low_air_s"]
        team_metrics["time_high_air_s"] += player_metrics["time_high_air_s"]
        team_metrics["powerslide_duration_s"] += player_metrics["powerslide_duration_s"]
        team_metrics["aerial_time_s"] += player_metrics["aerial_time_s"]
        team_metrics["distance_km"] += player_metrics["distance_km"]

        team_metrics["max_speed_kph"] = max(
            team_metrics["max_speed_kph"], player_metrics["max_speed_kph"]
        )

        # Sum count metrics
        team_metrics["powerslide_count"] += player_metrics["powerslide_count"]
        team_metrics["aerial_count"] += player_metrics["aerial_count"]

        # Average speed calculation
        team_metrics["avg_speed_kph"] += player_metrics["avg_speed_kph"]

    if player_count > 0:
        team_metrics["avg_speed_kph"] = round(
            team_metrics["avg_speed_kph"] / player_count, 2
        )

    return team_metrics


def _calculate_speed(velocity: Vec3) -> float:
    """Calculate speed magnitude from velocity vector."""
    return math.sqrt(velocity.x**2 + velocity.y**2 + velocity.z**2)


def _is_on_ground(player: PlayerFrame) -> bool:
    """Judge by height: the parser's flag stops at 18uu, under some cars at rest."""
    return player.position.z <= GROUND_HEIGHT or player.sleeping


def _detect_powerslide(current: PlayerFrame) -> bool:
    """A powerslide is the handbrake held on the ground; held in the air it's not."""
    return bool(current.handbrake) and _is_on_ground(current)


def _close_aerial(
    end_timestamp: float,
    start_timestamp: float,
    aerial_count: int,
    aerial_time: float,
) -> tuple[int, float, bool]:
    """Finalize aerial bookkeeping if minimum duration satisfied."""
    air_duration = end_timestamp - start_timestamp
    if air_duration >= MIN_AERIAL_DURATION:
        aerial_count += 1
        aerial_time += air_duration
    return aerial_count, aerial_time, False


def _uu_s_to_kph(speed_uu_s: float) -> float:
    """Convert Unreal Units per second to kilometers per hour."""
    return speed_uu_s * UU_S_TO_KPH


def _uu_to_km(distance_uu: float) -> float:
    """Convert Unreal Units to kilometers."""
    return distance_uu * UU_TO_METERS / 1000.0


def _empty_movement() -> dict[str, Any]:
    """Return empty movement dict for degraded scenarios."""
    return {
        "avg_speed_kph": 0.0,
        "distance_km": 0.0,
        "max_speed_kph": 0.0,
        "time_slow_s": 0.0,
        "time_boost_speed_s": 0.0,
        "time_supersonic_s": 0.0,
        "time_ground_s": 0.0,
        "time_low_air_s": 0.0,
        "time_high_air_s": 0.0,
        "powerslide_count": 0,
        "powerslide_duration_s": 0.0,
        "aerial_count": 0,
        "aerial_time_s": 0.0,
    }
