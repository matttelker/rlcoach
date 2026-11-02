"""Kickoff detection for Rocket League replays.

Detects kickoff events with enriched per-player metrics including
roles, approach types, and timing analysis.
"""

from __future__ import annotations

import math
import statistics
from itertools import groupby
from typing import Any

from ..field_constants import Vec3
from ..parser.types import BallFrame, Frame, Header, PlayerFrame
from .constants import (
    BALL_STATIONARY_THRESHOLD,
    DODGE_MIN_PITCH_TORQUE,
    DODGE_SPIN_RATE,
    KICKOFF_ARRIVAL_MAX_S,
    KICKOFF_CAR_STILL_SPEED,
    KICKOFF_CENTER_POSITION,
    KICKOFF_CHEAT_MIN_ADVANCE,
    KICKOFF_CONTACT_REACH,
    KICKOFF_FRONTFLIP_MAX_ANGLE,
    KICKOFF_HOLD_MIN_S,
    KICKOFF_MAX_DURATION,
    KICKOFF_MIN_COOLDOWN,
    KICKOFF_POSITION_TOLERANCE,
    KICKOFF_RESET_LEAD_S,
    KICKOFF_ROLE_TIE_TOLERANCE,
    SPEEDFLIP_MAX_PITCH_SHARE,
    SPEEDFLIP_SPIN_WINDOW_S,
    TOUCH_PROXIMITY_THRESHOLD,
)
from .types import KickoffEvent
from .utils import distance_3d, vector_magnitude


def detect_kickoffs(
    frames: list[Frame], header: Header | None = None
) -> list[KickoffEvent]:
    """Detect kickoff events with enriched per-player metrics.

    The detector tracks the kickoff window (cars released -> ball first played),
    so ``t_start`` and every time in the event count from the release. It records:
    - Player roles (GO/CHEAT/WING/BACK) inferred from spawn positions, with GO
      going to whichever car took the kickoff when spawns are level
    - Boost consumption prior to the first meaningful action
    - How each car played the kickoff, read from its own dodges and movement
    - Time-to-first-touch per player and overall first possession outcome

    The contact time is exact to a frame. ``first_touch_player`` is the car the ball
    leaves away from, so in a 50/50 it names who won the ball, which is what the
    outcome means, and may not be who reached it first.
    """
    if not frames:
        return []

    heuristic_kickoffs = _detect_heuristic_kickoffs(frames, header)
    parser_kickoffs = _kickoffs_from_parser_markers(frames)
    if parser_kickoffs:
        return _merge_kickoff_sources(heuristic_kickoffs, parser_kickoffs)
    return heuristic_kickoffs


def _is_ball_on_spot(ball: BallFrame) -> bool:
    """True while the ball sits on the centre spot."""
    return (
        abs(ball.position.x - KICKOFF_CENTER_POSITION.x) <= KICKOFF_POSITION_TOLERANCE
        and abs(ball.position.y - KICKOFF_CENTER_POSITION.y)
        <= KICKOFF_POSITION_TOLERANCE
        and abs(ball.position.z - KICKOFF_CENTER_POSITION.z) <= 60.0
    )


def _is_held_for_countdown(frame: Frame) -> bool:
    """True while the ball is at rest and every car waits for the countdown."""
    return (
        vector_magnitude(frame.ball.velocity) < BALL_STATIONARY_THRESHOLD
        and bool(frame.players)
        and all(
            vector_magnitude(player.velocity) < KICKOFF_CAR_STILL_SPEED
            for player in frame.players
        )
    )


def _find_kickoff_releases(frames: list[Frame]) -> set[int]:
    """Find the frame index where each kickoff countdown releases the cars.

    Only a countdown keeps the ball on the spot with every car still for this long.
    The ball settles and the cars land just after a reset, so the hold is judged
    between its first and last still frames, and a car that twitches mid-countdown
    can't end it early. Passing through the spot, or a placeholder frame with the
    ball at its default position, never adds up to a hold.
    """
    releases: set[int] = set()
    for on_spot, stretch in groupby(
        range(len(frames)), key=lambda index: _is_ball_on_spot(frames[index].ball)
    ):
        if not on_spot:
            continue
        held = [index for index in stretch if _is_held_for_countdown(frames[index])]
        if not held:
            continue
        hold_length = frames[held[-1]].timestamp - frames[held[0]].timestamp
        if hold_length >= KICKOFF_HOLD_MIN_S:
            releases.add(held[-1])
    return releases


def _detect_heuristic_kickoffs(
    frames: list[Frame], header: Header | None = None
) -> list[KickoffEvent]:
    """Detect kickoff windows from gameplay state alone."""

    kickoffs: list[KickoffEvent] = []
    kickoff_state: dict[str, Any] | None = None
    last_kickoff_end_time = -KICKOFF_MIN_COOLDOWN
    releases = _find_kickoff_releases(frames)

    for index, frame in enumerate(frames):
        ball = frame.ball

        at_center = _is_ball_on_spot(ball)
        ball_speed = vector_magnitude(ball.velocity)
        is_stationary = ball_speed < BALL_STATIONARY_THRESHOLD

        # A kickoff starts when the countdown releases the cars. Frames that never
        # show a countdown fall back to the ball being reset to centre once the
        # previous kickoff has fully completed.
        if releases:
            starts_kickoff = index in releases
        else:
            starts_kickoff = (
                at_center
                and is_stationary
                and (frame.timestamp - last_kickoff_end_time) >= KICKOFF_MIN_COOLDOWN
            )

        if kickoff_state is None and starts_kickoff:
            kickoff_state = _start_kickoff(frame)
            continue

        if kickoff_state is None:
            continue

        _update_kickoff_state(kickoff_state, frame)

        # After a countdown only a car moves the ball sideways, while Hoops launches
        # it straight up at the release. Other frames only show it leave the spot.
        if releases:
            ball_played = (
                math.hypot(ball.velocity.x, ball.velocity.y)
                > BALL_STATIONARY_THRESHOLD * 1.5
            )
            if ball_played:
                _record_contact(kickoff_state, frame)
        else:
            ball_played = not at_center or ball_speed > BALL_STATIONARY_THRESHOLD * 1.5

        elapsed = frame.timestamp - kickoff_state["t_start"]
        duration_exceeded = elapsed >= KICKOFF_MAX_DURATION

        if ball_played or duration_exceeded:
            kickoff_event = _finalize_kickoff(kickoff_state, frame, header)
            if kickoff_event is not None:
                kickoffs.append(kickoff_event)
                last_kickoff_end_time = frame.timestamp
            kickoff_state = None

    # Handle dangling kickoff if replay ends while still at center
    if kickoff_state is not None:
        kickoff_event = _finalize_kickoff(kickoff_state, frames[-1], header)
        if kickoff_event is not None:
            kickoffs.append(kickoff_event)

    return kickoffs


def _kickoffs_from_parser_markers(frames: list[Frame]) -> list[KickoffEvent]:
    """Convert parser kickoff markers, populating players from frame data."""
    events: list[KickoffEvent] = []
    seen: set[tuple[float, str]] = set()
    for frame in frames:
        for marker in frame.parser_kickoff_markers:
            phase = str(marker.phase or "INITIAL").upper()
            key = (round(float(marker.timestamp), 4), phase)
            if key in seen:
                continue
            seen.add(key)

            player_states: dict[str, dict[str, Any]] = {}
            for p in frame.players:
                player_states[p.player_id] = {
                    "team": p.team,
                    "start_pos": p.position,
                }

            # Infer kickoff roles (GO/CHEAT/WING/BACK) from positions
            _assign_kickoff_roles(player_states)

            players = [
                {
                    "player_id": pid,
                    "role": state["role"],
                    "boost_used": 0.0,
                    "approach_type": "UNKNOWN",
                    "time_to_first_touch": None,
                }
                for pid, state in player_states.items()
            ]
            events.append(
                KickoffEvent(
                    phase=phase,
                    t_start=float(marker.timestamp),
                    players=players,
                    outcome="NEUTRAL",
                    first_touch_player=None,
                    time_to_first_touch=None,
                    source=marker.source or "parser",
                )
            )
    events.sort(key=lambda kickoff: kickoff.t_start)
    return events


def _merge_kickoff_sources(
    heuristic_kickoffs: list[KickoffEvent],
    parser_kickoffs: list[KickoffEvent],
) -> list[KickoffEvent]:
    """Prefer parser phase while preserving heuristic timing and enrichment.

    Markers fire on every ball reset, usually twice as the ball settles, and on
    placeholder frames during a goal. So they confirm a kickoff the heuristic pass
    found, and only stand alone when it found nothing at all.
    """
    if not heuristic_kickoffs:
        return parser_kickoffs
    if not parser_kickoffs:
        return heuristic_kickoffs

    merged: list[KickoffEvent] = []
    used_heuristics: set[int] = set()

    for parser_kickoff in parser_kickoffs:
        match_index = _find_matching_kickoff(
            parser_kickoff,
            heuristic_kickoffs,
            used_heuristics,
        )
        if match_index is None:
            continue

        used_heuristics.add(match_index)
        heuristic = heuristic_kickoffs[match_index]
        merged.append(
            KickoffEvent(
                phase=parser_kickoff.phase or heuristic.phase,
                t_start=heuristic.t_start,
                players=heuristic.players,
                outcome=heuristic.outcome,
                first_touch_player=heuristic.first_touch_player,
                time_to_first_touch=heuristic.time_to_first_touch,
                source=parser_kickoff.source or heuristic.source,
            )
        )

    for index, heuristic in enumerate(heuristic_kickoffs):
        if index not in used_heuristics:
            merged.append(heuristic)

    merged.sort(key=lambda kickoff: kickoff.t_start)
    return merged


def _find_matching_kickoff(
    parser_kickoff: KickoffEvent,
    heuristic_kickoffs: list[KickoffEvent],
    used_heuristics: set[int],
) -> int | None:
    """Match a parser kickoff marker to the nearest heuristic kickoff.

    A marker fires at the ball reset, so on a replay with a countdown it comes
    ``KICKOFF_RESET_LEAD_S`` before the kickoff it belongs to.
    """
    best_index: int | None = None
    best_delta: float | None = None
    max_delta = 1.0

    for index, heuristic in enumerate(heuristic_kickoffs):
        if index in used_heuristics:
            continue
        lead = heuristic.t_start - parser_kickoff.t_start
        if not -max_delta <= lead <= KICKOFF_RESET_LEAD_S + max_delta:
            continue
        delta = abs(lead)
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_index = index

    return best_index


def _start_kickoff(frame: Frame) -> dict[str, Any]:
    """Initialize kickoff tracking state from the kickoff start frame."""
    player_states: dict[str, dict[str, Any]] = {}
    players_order: list[str] = []

    for player in frame.players:
        players_order.append(player.player_id)
        player_states[player.player_id] = {
            "team": player.team,
            "start_pos": player.position,
            "last_pos": player.position,
            "start_boost": float(player.boost_amount),
            "min_boost": float(player.boost_amount),
            "movement_start_time": None,
            "max_distance": 0.0,
            "first_touch_time": None,
            "contact_time": None,  # Set when in reach as the ball was played
            "arrival_eta": float("inf"),  # Seconds out as the ball was played
            "role": "BACK",  # Placeholder until assigned from spawn ordering
            "speed_at_contact": 0.0,
            "positions": [],  # List of (t, Vec3) for path analysis
            "distance_to_ball_min": float("inf"),
            "dodges": [],  # List of (t, torque_x, torque_y), in the car's own frame
            "flip_motion": [],  # List of (t, pitch_rate, roof_height)
        }

    _assign_kickoff_roles(player_states)

    return {
        "t_start": frame.timestamp,
        "players": player_states,
        "player_order": players_order,
        "first_touch": None,
    }


def _assign_kickoff_roles(player_states: dict[str, dict[str, Any]]) -> None:
    """Assign kickoff roles per team using spawn proximity."""
    by_team: dict[int, list[tuple[str, dict[str, Any]]]] = {0: [], 1: []}
    for pid, state in player_states.items():
        by_team.setdefault(state["team"], []).append((pid, state))

    for team, entries in by_team.items():
        if not entries:
            continue
        # Sort by distance to centre spot (closer players are the goers)
        entries.sort(key=lambda item: _spawn_distance(item[1]))

        for index, (_pid, state) in enumerate(entries):
            role = _classify_kickoff_role(state["start_pos"], team, index)
            state["role"] = role


def _spawn_distance(state: dict[str, Any]) -> float:
    """Distance from a car's spawn to the centre spot."""
    start_pos = state["start_pos"]
    return distance_3d(start_pos, Vec3(0.0, 0.0, start_pos.z))


def _settle_level_spawns(player_states: dict[str, dict[str, Any]]) -> None:
    """Give GO to the car that took the kickoff when spawns can't separate them.

    A team's cars often start level on mirrored spawns and agree between them who
    goes, so spawn order alone can name the wrong car.
    """
    states = list(player_states.values())
    for go in [state for state in states if state["role"] == "GO"]:
        level = [
            state
            for state in states
            if state["team"] == go["team"]
            and abs(_spawn_distance(state) - _spawn_distance(go))
            <= KICKOFF_ROLE_TIE_TOLERANCE
        ]
        taker = min(level, key=lambda state: state["distance_to_ball_min"])
        if taker["distance_to_ball_min"] < go["distance_to_ball_min"]:
            go["role"], taker["role"] = taker["role"], go["role"]


def _update_kickoff_state(state: dict[str, Any], frame: Frame) -> None:
    """Update kickoff tracking state with the latest frame data."""
    ball = frame.ball
    t = frame.timestamp
    t_start = state["t_start"]
    rel_time = t - t_start

    for player in frame.players:
        pid = player.player_id
        if pid not in state["players"]:
            # Ignore substitute players appearing mid-kickoff; rare but safe.
            continue

        pdata = state["players"][pid]
        pdata["last_pos"] = player.position
        pdata["min_boost"] = min(pdata["min_boost"], float(player.boost_amount))
        distance_from_start = distance_3d(player.position, pdata["start_pos"])
        pdata["max_distance"] = max(pdata["max_distance"], distance_from_start)

        if pdata["movement_start_time"] is None and distance_from_start > 150.0:
            pdata["movement_start_time"] = t

        speed = vector_magnitude(player.velocity)

        pdata["positions"].append((rel_time, player.position))

        flip_motion = _flip_motion(player)
        if flip_motion is not None:
            pdata["flip_motion"].append((rel_time, *flip_motion))

        separation = distance_3d(player.position, ball.position)
        pdata["distance_to_ball_min"] = min(pdata["distance_to_ball_min"], separation)

        # Detect per-player first touch during kickoff window
        if separation < TOUCH_PROXIMITY_THRESHOLD * 0.9:
            if pdata["first_touch_time"] is None:
                pdata["first_touch_time"] = rel_time
                pdata["speed_at_contact"] = speed

            first_touch = state.get("first_touch")
            if first_touch is None or rel_time < first_touch["time"]:
                state["first_touch"] = {
                    "player_id": pid,
                    "team": pdata["team"],
                    "time": rel_time,
                }

    for event in frame.component_events:
        if event.kind != "dodge_torque" or event.vector is None:
            continue
        if event.player_id in state["players"]:
            state["players"][event.player_id]["dodges"].append(
                (rel_time, event.vector.x, event.vector.y)
            )


def _flip_motion(player: PlayerFrame) -> tuple[float, float] | None:
    """Pitch rate in the car's own frame, and how far its roof points up."""
    quaternion = getattr(player.rotation, "quaternion", None)
    spin = player.angular_velocity
    if quaternion is None or spin is None:
        return None
    x, y, z, w = quaternion
    pitch_rate = (
        spin.x * 2.0 * (x * y - z * w)
        + spin.y * (1.0 - 2.0 * (x * x + z * z))
        + spin.z * 2.0 * (y * z + x * w)
    )
    return pitch_rate, 1.0 - 2.0 * (x * x + y * y)


def _ball_departure_alignment(car: PlayerFrame, ball: BallFrame) -> float:
    """How directly the ball is leaving away from a car, from 1.0 down to -1.0."""
    offset_x = ball.position.x - car.position.x
    offset_y = ball.position.y - car.position.y
    offset_z = ball.position.z - car.position.z
    scale = math.hypot(offset_x, offset_y, offset_z) * vector_magnitude(ball.velocity)
    if scale == 0.0:
        return 0.0
    return (
        offset_x * ball.velocity.x
        + offset_y * ball.velocity.y
        + offset_z * ball.velocity.z
    ) / scale


def _arrival_eta(car: PlayerFrame, ball: BallFrame) -> float:
    """Seconds until a car reaches the ball at its current closing speed."""
    offset_x = ball.position.x - car.position.x
    offset_y = ball.position.y - car.position.y
    offset_z = ball.position.z - car.position.z
    distance = math.hypot(offset_x, offset_y, offset_z)
    if distance == 0.0:
        return 0.0
    closing_speed = (
        offset_x * car.velocity.x
        + offset_y * car.velocity.y
        + offset_z * car.velocity.z
    ) / distance
    return distance / closing_speed if closing_speed > 0.0 else float("inf")


def _record_contact(state: dict[str, Any], frame: Frame) -> None:
    """Credit the contact that moved the ball, on the frame it happened.

    Car positions refresh every few frames, so at contact the two cars are seen
    150-300uu out and distance can't separate them. The ball can: it leaves away
    from whoever played it. A car in reach is contesting the ball even if it lost.
    """
    ball = frame.ball
    cars = [player for player in frame.players if player.player_id in state["players"]]
    if not cars:
        return

    def distance_to_ball(car: PlayerFrame) -> float:
        return distance_3d(car.position, ball.position)

    contesting = [
        car for car in cars if distance_to_ball(car) <= KICKOFF_CONTACT_REACH
    ] or [min(cars, key=distance_to_ball)]

    rel_time = frame.timestamp - state["t_start"]
    for car in contesting:
        state["players"][car.player_id]["contact_time"] = rel_time
    for car in cars:
        state["players"][car.player_id]["arrival_eta"] = _arrival_eta(car, ball)

    toucher = max(contesting, key=lambda car: _ball_departure_alignment(car, ball))
    state["first_touch"] = {
        "player_id": toucher.player_id,
        "team": state["players"][toucher.player_id]["team"],
        "time": rel_time,
    }


def _finalize_kickoff(
    state: dict[str, Any], frame: Frame, header: Header | None
) -> KickoffEvent | None:
    """Produce the KickoffEvent dataclass from tracked state."""
    t_start = state["t_start"]
    elapsed = frame.timestamp - t_start
    if elapsed < 0.05:  # Ignore degenerate kickoffs
        return None

    first_touch = state.get("first_touch")
    first_touch_player = first_touch.get("player_id") if first_touch else None
    time_to_first_touch = first_touch.get("time") if first_touch else None

    _settle_level_spawns(state["players"])

    players_payload = []
    for pid in state["player_order"]:
        pdata = state["players"].get(pid)
        if pdata is None:
            continue

        boost_used = max(0.0, pdata["start_boost"] - pdata["min_boost"])
        time_to_contact = pdata["contact_time"]
        if time_to_contact is None:
            time_to_contact = pdata["first_touch_time"]
        approach_type = _classify_approach_type(pdata)

        players_payload.append(
            {
                "player_id": pid,
                "role": pdata["role"],
                "boost_used": round(boost_used, 2),
                "approach_type": approach_type,
                "time_to_first_touch": (
                    None if time_to_contact is None else round(time_to_contact, 3)
                ),
            }
        )

    phase = _determine_kickoff_phase(t_start, header)
    outcome = _classify_kickoff_outcome(first_touch)

    return KickoffEvent(
        phase=phase,
        t_start=t_start,
        players=players_payload,
        outcome=outcome,
        first_touch_player=first_touch_player,
        time_to_first_touch=(
            None if time_to_first_touch is None else round(time_to_first_touch, 3)
        ),
        source="inferred",
    )


def _classify_kickoff_role(position: Vec3, team: int, ordinal: int) -> str:
    """Classify kickoff role (GO/CHEAT/WING/BACK) using spawn layout heuristics."""
    x_abs = abs(position.x)
    y_abs = abs(position.y)

    # Primary goer: closest to centre regardless of ordinal
    if ordinal == 0:
        return "GO"

    if x_abs >= 1700.0 and y_abs <= 3600.0:
        return "WING"

    if y_abs <= 3200.0:
        return "CHEAT"

    return "BACK"


def _is_cancelled_dodge(
    pdata: dict[str, Any], dodge: tuple[float, float, float]
) -> bool:
    """True when a forward dodge's pitch stopped while the car rolled through.

    A flip spins about its dodge torque at a fixed rate, so the torque says what
    pitch rate to expect. A cancel takes that pitch out and leaves the roll, so the
    nose stays level as the roof comes round. A dodge that lands first keeps its
    roof up and is a wavedash. Spin is judged by its median because some cars'
    rotation replicates up to 0.2s behind the dodge.
    """
    dodge_time, torque_x, torque_y = dodge
    if torque_y < DODGE_MIN_PITCH_TORQUE:
        return False

    motion = pdata["flip_motion"]
    window_start = dodge_time + SPEEDFLIP_SPIN_WINDOW_S[0]
    window_end = dodge_time + SPEEDFLIP_SPIN_WINDOW_S[1]
    window = [sample for sample in motion if window_start <= sample[0] <= window_end]
    # A dodge this close to contact is the flip into the ball, not an approach.
    if not window or motion[-1][0] < window_end:
        return False

    expected_pitch = DODGE_SPIN_RATE * torque_y / math.hypot(torque_x, torque_y)
    pitch_share = statistics.median(rate for _, rate, _ in window) / expected_pitch
    rolled_over = min(roof for _, _, roof in window) < 0.0
    return pitch_share < SPEEDFLIP_MAX_PITCH_SHARE and rolled_over


def _is_speedflip_kickoff(pdata: dict[str, Any]) -> bool:
    """Detect a speedflip from the car's own flip.

    Cars that cancel a forward dodge reach 1000uu from the centre spot about 0.2s
    ahead of cars from the same spawn that don't, measured apart from this rule.
    """
    return any(_is_cancelled_dodge(pdata, dodge) for dodge in pdata["dodges"])


def _is_contesting(pdata: dict[str, Any]) -> bool:
    """True if a car went for the ball.

    A car in reach as the ball is played is contesting it. So is a GO car still
    closing on it, which lost the race instead of declining it. Other roles get no
    such credit, because their cars pass through at every range on the way upfield.
    """
    if pdata["contact_time"] is not None or pdata["first_touch_time"] is not None:
        return True
    return pdata["role"] == "GO" and pdata["arrival_eta"] <= KICKOFF_ARRIVAL_MAX_S


def _classify_fake_kickoff(pdata: dict[str, Any]) -> str:
    """Name what a GO car did instead of contesting the ball.

    Fake types:
    1. FAKE_HALFFLIP: Flipped backward, usually to grab corner boost
    2. FAKE_STATIONARY: Barely moved
    3. FAKE_AGGRESSIVE: Moved, but somewhere other than the ball
    """
    if any(torque_y <= -DODGE_MIN_PITCH_TORQUE for _, _, torque_y in pdata["dodges"]):
        return "FAKE_HALFFLIP"

    boost_used = max(0.0, pdata["start_boost"] - pdata["min_boost"])
    if pdata["max_distance"] < 300.0 and boost_used < 5.0:
        return "FAKE_STATIONARY"

    return "FAKE_AGGRESSIVE"


def _classify_support_kickoff(pdata: dict[str, Any]) -> str:
    """Name the job of a car that left the ball to its teammate.

    - SUPPORT_CHEAT: Moved up toward the play
    - SUPPORT_HOLD: Stayed back, or went for boost
    """
    center = KICKOFF_CENTER_POSITION
    advance = distance_3d(pdata["start_pos"], center) - distance_3d(
        pdata["last_pos"], center
    )
    if advance >= KICKOFF_CHEAT_MIN_ADVANCE:
        return "SUPPORT_CHEAT"
    return "SUPPORT_HOLD"


def _classify_standard_kickoff(pdata: dict[str, Any]) -> str:
    """Classify a contested kickoff with no speedflip by the car's first dodge.

    Subtypes:
    - STANDARD_FRONTFLIP: Dodged straight ahead
    - STANDARD_DIAGONAL: Dodged at an angle, side flips included
    - STANDARD_BOOST: Reached contact without dodging, on boost
    - STANDARD: Reached contact without dodging or boost

    STANDARD_WAVEDASH is reserved: no contesting car has shown one to calibrate on.
    """
    if pdata["dodges"]:
        _, torque_x, torque_y = pdata["dodges"][0]
        angle = math.degrees(math.atan2(abs(torque_x), torque_y))
        if angle <= KICKOFF_FRONTFLIP_MAX_ANGLE:
            return "STANDARD_FRONTFLIP"
        return "STANDARD_DIAGONAL"

    boost_used = max(0.0, pdata["start_boost"] - pdata["min_boost"])
    if boost_used > 10.0:
        return "STANDARD_BOOST"
    return "STANDARD"


def _classify_approach_type(pdata: dict[str, Any]) -> str:
    """Classify how a car played the kickoff.

    A car that left the ball alone reports its job: only a GO car was meant to go,
    so only a GO car can fake. A car that went for the ball reports how it got there.

    DELAY is reserved: no car has been seen braking before contact, so nothing
    calibrates a rule for it.
    """
    if not _is_contesting(pdata):
        if pdata["role"] == "GO":
            return _classify_fake_kickoff(pdata)
        return _classify_support_kickoff(pdata)

    if _is_speedflip_kickoff(pdata):
        return "SPEEDFLIP"

    standard_type = _classify_standard_kickoff(pdata)
    if standard_type != "STANDARD":
        return standard_type

    # Fallback
    boost_used = max(0.0, pdata["start_boost"] - pdata["min_boost"])
    if boost_used > 0.0 or pdata["max_distance"] > 150.0:
        return "STANDARD"

    return "UNKNOWN"


def _determine_kickoff_phase(kickoff_start: float, header: Header | None) -> str:
    """Determine kickoff phase (INITIAL vs OT)."""
    if header:
        match_length = float(getattr(header, "match_length", 0.0) or 0.0)
        if getattr(header, "overtime", False) and kickoff_start >= max(
            300.0, match_length
        ):
            return "OT"
    if kickoff_start >= 300.0:
        return "OT"
    return "INITIAL"


def _classify_kickoff_outcome(first_touch: dict[str, Any] | None) -> str:
    """Map first touch info to schema outcome classification."""
    if not first_touch:
        return "NEUTRAL"

    team = first_touch.get("team")
    if team == 0:
        return "FIRST_POSSESSION_BLUE"
    if team == 1:
        return "FIRST_POSSESSION_ORANGE"
    return "NEUTRAL"
