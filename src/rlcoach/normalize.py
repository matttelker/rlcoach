"""Turn the parser's frames into the Frames that events and stats read.

Each car gets its player's id from the header, positions are held to the field,
and times count from the first frame. See `parser.read_frames` for what the
parser hands over.
"""

from __future__ import annotations

from typing import Any

from .field_constants import BACK_WALL_Y, CEILING_Z, SIDE_WALL_X, Vec3
from .identity import build_alias_lookup, build_player_identities
from .parser.types import (
    BallFrame,
    BoostPadEventFrame,
    Dodge,
    Frame,
    Header,
    ParserDemoEvent,
    ParserTouchEvent,
    PlayerFrame,
    Quaternion,
    TouchCount,
)

# How far past the walls a position may read. Cars and the ball go inside the
# goals, past the back wall
X_LIMIT = SIDE_WALL_X * 1.1
Y_LIMIT = BACK_WALL_Y * 1.1
Z_RANGE = (-100.0, CEILING_Z * 2.0)

Raw = dict[str, Any]


def build_timeline(header: Header, raw_frames: list[Raw]) -> list[Frame]:
    """The parser's frames, which must not be empty, in time order from 0."""
    return _Timeline(header).frames(raw_frames)


def _on_field(xyz: tuple[float, float, float]) -> Vec3:
    x, y, z = xyz
    return Vec3(
        max(-X_LIMIT, min(X_LIMIT, x)),
        max(-Y_LIMIT, min(Y_LIMIT, y)),
        max(Z_RANGE[0], min(Z_RANGE[1], z)),
    )


class _Timeline:
    def __init__(self, header: Header):
        identities = build_player_identities(header.players)
        self.ids = build_alias_lookup(identities)
        self.by_row: dict[int, str] = {}
        # The header's orange stands. Otherwise each frame says, and someone the
        # header misses takes the team of the first frame they're in
        self.orange = {i.canonical_id: i.team == "ORANGE" for i in identities}

    def player(self, row: int) -> str:
        """The id of the player in this header row. Someone who left has no row,
        and keeps the parser's name for them."""
        if row not in self.by_row:
            raw = f"player_{row}"
            self.by_row[row] = self.ids.get(raw, raw)
        return self.by_row[row]

    def frames(self, raw_frames: list[Raw]) -> list[Frame]:
        ordered = sorted(raw_frames, key=lambda raw: raw["time"])
        self.start = ordered[0]["time"]
        return [self.frame(raw) for raw in ordered]

    def since(self, time: float) -> float:
        shifted = time - self.start
        return 0.0 if abs(shifted) < 1e-6 else shifted

    def car(self, raw: tuple) -> PlayerFrame:
        row, team, position, velocity, spin, rotation, boost, demolished, using = raw
        jumping, double_jumping, dodging = using
        player_id = self.player(row)
        return PlayerFrame(
            player_id=player_id,
            team=1 if self.orange.setdefault(player_id, team == 1) else team,
            position=_on_field(position),
            velocity=Vec3(*velocity),
            boost_amount=max(0, min(100, boost)),
            angular_velocity=Vec3(*spin),
            quaternion=None if rotation is None else Quaternion(*rotation),
            is_demolished=demolished,
            is_jumping=jumping,
            is_double_jumping=double_jumping,
            is_dodging=dodging,
        )

    def frame(self, raw: Raw) -> Frame:
        t = self.since(raw["time"])
        player = self.player
        cars: dict[str, PlayerFrame] = {}
        for raw_car in raw["cars"]:
            car = self.car(raw_car)
            cars[car.player_id] = car  # A car listed twice keeps its last state
        position, velocity = raw["ball"]
        return Frame(
            timestamp=t,
            ball=BallFrame(position=_on_field(position), velocity=Vec3(*velocity)),
            hit_team=raw["hit_team"],
            players=list(cars.values()),
            boost_pad_events=[
                BoostPadEventFrame(
                    pad_id=pad,
                    player_id=player(row),
                    player_team=team,
                    timestamp=self.since(when),
                )
                for pad, row, team, when in raw["pickups"]
            ],
            dodges=[
                Dodge(timestamp=t, player_id=player(row), torque=Vec3(*torque))
                for row, torque in raw["dodges"]
            ],
            touch_counts=[TouchCount(player(row), n) for row, n in raw["touches"]],
            parser_first_touch_events=[
                ParserTouchEvent(t, player(row)) for row in raw["first_touches"]
            ],
            parser_demo_events=[
                ParserDemoEvent(
                    timestamp=t,
                    victim_id=player(victim),
                    attacker_id=None if attacker is None else player(attacker),
                )
                for victim, attacker in raw["demos"]
            ],
        )
