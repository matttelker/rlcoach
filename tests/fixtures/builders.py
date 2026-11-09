"""Synthetic frames for tests: cars, the ball, and the parser's events on a frame."""

from __future__ import annotations

from dataclasses import replace

from rlcoach.field_constants import Vec3
from rlcoach.parser.types import (
    BallFrame,
    BoostPadEventFrame,
    Dodge,
    Frame,
    ParserDemoEvent,
    PlayerFrame,
    Quaternion,
    StatCount,
    TouchCount,
)

STILL = Vec3(0.0, 0.0, 0.0)


def create_test_player(
    player_id: str,
    team: int,
    position: Vec3 | None = None,
    velocity: Vec3 | None = None,
    angular_velocity: Vec3 | None = None,
    quaternion: Quaternion | None = None,
    boost: float = 50.0,
    is_demolished: bool = False,
    is_jumping: bool = False,
    is_double_jumping: bool = False,
    is_dodging: bool = False,
) -> PlayerFrame:
    """A car, still on the ground at the centre spot unless told otherwise."""
    return PlayerFrame(
        player_id=player_id,
        team=team,
        position=position or Vec3(0.0, 0.0, 17.0),
        velocity=velocity or STILL,
        boost_amount=boost,
        angular_velocity=angular_velocity or STILL,
        quaternion=quaternion,
        is_demolished=is_demolished,
        is_jumping=is_jumping,
        is_double_jumping=is_double_jumping,
        is_dodging=is_dodging,
    )


def create_test_ball(
    position: Vec3 | None = None, velocity: Vec3 | None = None
) -> BallFrame:
    """The ball, at rest on the centre spot unless told otherwise."""
    return BallFrame(
        position=position or Vec3(0.0, 0.0, 93.15), velocity=velocity or STILL
    )


def create_test_frame(
    timestamp: float,
    players: list[PlayerFrame],
    ball: BallFrame | None = None,
    *,
    dodges: list[Dodge] | None = None,
    touches: list[TouchCount] | None = None,
    hit_team: int | None = None,
    demos: list[ParserDemoEvent] | None = None,
    pad_events: list[BoostPadEventFrame] | None = None,
    stat_counts: list[StatCount] | None = None,
) -> Frame:
    """A frame with these cars and the parser's events on it."""
    return Frame(
        timestamp=timestamp,
        ball=ball or create_test_ball(),
        hit_team=hit_team,
        players=players,
        dodges=dodges or [],
        touch_counts=touches or [],
        parser_demo_events=demos or [],
        boost_pad_events=pad_events or [],
        stat_counts=stat_counts or [],
    )


def with_flip_at(
    frames: list[Frame],
    timestamp: float,
    player_id: str,
    direction: Vec3 | None = None,
) -> list[Frame]:
    """The frames with a flip by `player_id` on the one nearest `timestamp`."""
    if not frames:
        return frames
    nearest = min(
        range(len(frames)), key=lambda i: abs(frames[i].timestamp - timestamp)
    )
    frame = frames[nearest]
    dodge = Dodge(frame.timestamp, player_id, direction or Vec3(1.0, 0.0, 0.0))
    updated = list(frames)
    updated[nearest] = replace(frame, dodges=[*frame.dodges, dodge])
    return updated


def create_simple_replay_frames(
    duration_seconds: float = 60.0,
    frame_rate: float = 30.0,
    players: list[tuple[str, int]] | None = None,
) -> list[Frame]:
    """Frames at a steady rate with every car still at the centre spot.

    `players` is (player_id, team) for each car, two by default.
    """
    players = players or [("player1", 0), ("player2", 1)]
    return [
        create_test_frame(i / frame_rate, [create_test_player(*p) for p in players])
        for i in range(int(duration_seconds * frame_rate))
    ]
