"""Turn the parser's frames into the Frames that events and stats read.

Each car gets its player's id from the header, positions are held to the field,
and times count from the first frame. Only what something downstream reads is
kept: where the ball and cars are and how they move, each car's boost, team and
whether it's demolished, and the parser's touch, first-touch, demo, dodge and
boost pad events.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .field_constants import BACK_WALL_Y, CEILING_Z, SIDE_WALL_X, Vec3
from .identity import build_alias_lookup, build_player_identities
from .parser.types import (
    BallFrame,
    BoostPadEventFrame,
    Frame,
    Header,
    ParserComponentEvent,
    ParserDemoEvent,
    ParserTouchEvent,
    PlayerFrame,
    Quaternion,
    Rotation,
)

# How far past the walls a position may read. Cars and the ball go inside the
# goals, past the back wall
X_LIMIT = SIDE_WALL_X * 1.1
Y_LIMIT = BACK_WALL_Y * 1.1
Z_RANGE = (-100.0, CEILING_Z * 2.0)

Raw = dict[str, Any]


def build_timeline(header: Header, raw_frames: list[Raw]) -> list[Frame]:
    """The parser's frames, which must not be empty, in time order from 0.

    The parser calls cars player_<n> after their row in the header. Someone who
    left before the end has no row, and keeps the parser's id.
    """
    identities = build_player_identities(header.players)
    ids = build_alias_lookup(identities)
    # The header's orange stands. Otherwise each frame says, and someone the
    # header misses takes orange from the first frame they're in
    orange = {i.canonical_id: i.team == "ORANGE" for i in identities}
    ordered = sorted(raw_frames, key=lambda raw: float(raw["timestamp"]))
    start = float(ordered[0]["timestamp"])

    def player(raw_id: Any) -> str | None:
        return ids.get(raw_id, raw_id) if raw_id else None

    return [_frame(raw, start, player, orange) for raw in ordered]


def _since(timestamp: Any, start: float) -> float:
    shifted = float(timestamp) - start
    return 0.0 if abs(shifted) < 1e-6 else shifted


def _vec(raw: Raw) -> Vec3:
    return Vec3(float(raw["x"]), float(raw["y"]), float(raw["z"]))


def _on_field(raw: Raw) -> Vec3:
    x, y, z = _vec(raw)
    return Vec3(
        max(-X_LIMIT, min(X_LIMIT, x)),
        max(-Y_LIMIT, min(Y_LIMIT, y)),
        max(Z_RANGE[0], min(Z_RANGE[1], z)),
    )


def _rotation(raw: Raw) -> Rotation:
    quaternion = raw.get("quaternion")
    return Rotation(
        pitch=float(raw["pitch"]),
        yaw=float(raw["yaw"]),
        roll=float(raw["roll"]),
        quaternion=(
            Quaternion(*map(float, (quaternion[k] for k in "xyzw")))
            if quaternion
            else None
        ),
    )


def _car(raw: Raw, player: Callable, orange: dict[str, bool]) -> PlayerFrame:
    player_id = player(raw["player_id"])
    team = int(raw["team"])
    return PlayerFrame(
        player_id=player_id,
        team=1 if orange.setdefault(player_id, team == 1) else team,
        position=_on_field(raw["position"]),
        velocity=_vec(raw["velocity"]),
        rotation=_rotation(raw["rotation"]),
        boost_amount=max(0, min(100, int(raw["boost_amount"]))),
        angular_velocity=_vec(raw["angular_velocity"]),
        is_demolished=bool(raw.get("is_demolished", False)),
    )


def _touch(event: Raw, start: float, player: Callable) -> ParserTouchEvent:
    return ParserTouchEvent(
        timestamp=_since(event["timestamp"], start),
        player_id=player(event["player_id"]),
        team=int(event["team"]),
    )


def _pad_event(event: Raw, start: float, player: Callable) -> BoostPadEventFrame:
    raw_id = event.get("player_id")
    if not raw_id and event.get("player_index") is not None:
        raw_id = f"player_{int(event['player_index'])}"
    timestamp = event.get("timestamp")
    return BoostPadEventFrame(
        pad_id=int(event["pad_id"]),
        status=str(event["status"]).upper(),
        is_big=bool(event["is_big"]),
        player_id=player(raw_id),
        player_team=event.get("player_team"),
        timestamp=None if timestamp is None else _since(timestamp, start),
    )


def _frame(raw: Raw, start: float, player: Callable, orange: dict[str, bool]) -> Frame:
    cars: dict[str, PlayerFrame] = {}
    for raw_car in raw["players"]:
        car = _car(raw_car, player, orange)
        cars[car.player_id] = car  # A car listed twice keeps its last state
    ball = raw["ball"]
    return Frame(
        timestamp=_since(raw["timestamp"], start),
        ball=BallFrame(
            position=_on_field(ball["position"]),
            velocity=_vec(ball["velocity"]),
            angular_velocity=_vec(ball["angular_velocity"]),
        ),
        players=list(cars.values()),
        boost_pad_events=[
            _pad_event(event, start, player) for event in raw["boost_pad_events"]
        ],
        component_events=[
            ParserComponentEvent(
                timestamp=_since(event["timestamp"], start),
                kind=event["kind"],
                component=event["component"],
                player_id=player(event.get("player_id")),
                vector=_vec(event["vector"]) if event.get("vector") else None,
            )
            for event in raw["component_events"]
        ],
        # The parser lists one frame's touches in hash map order, which changes
        # between parses and would change who touched first
        parser_touch_events=sorted(
            (_touch(event, start, player) for event in raw["parser_touch_events"]),
            key=lambda event: event.player_id,
        ),
        parser_first_touch_events=[
            _touch(event, start, player) for event in raw["parser_first_touch_events"]
        ],
        parser_demo_events=[
            ParserDemoEvent(
                timestamp=_since(event["timestamp"], start),
                victim_id=player(event["victim_id"]),
                attacker_id=player(event.get("attacker_id")),
            )
            for event in raw["parser_demo_events"]
        ],
    )
