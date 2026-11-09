"""The Soccar field: its size, its goals and its boost pads, in Unreal Units.

Blue defends negative y and orange positive y. The origin is the centre spot,
on the floor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple


class Vec3(NamedTuple):
    x: float
    y: float
    z: float

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)


SIDE_WALL_X = 4096.0
BACK_WALL_Y = 5120.0  # The goal lines
CEILING_Z = 2044.0
GOAL_WIDTH = 892.755  # From the centre of the goal to a post
GOAL_HEIGHT = 642.775


@dataclass(frozen=True)
class BoostPad:
    pad_id: int  # The parser numbers pickups by this table, which it is given
    position: Vec3
    is_big: bool


def _pads(is_big: bool, z: float, *spots: tuple[float, float]) -> list[tuple]:
    return [(Vec3(x, y, z), is_big) for x, y in spots]


# The corners and the side pads, then the small pads
# from blue's back wall to orange's
BOOST_PADS = tuple(
    BoostPad(pad_id, position, is_big)
    for pad_id, (position, is_big) in enumerate(
        _pads(
            True,
            73.0,
            (-3072.0, -4096.0),
            (3072.0, -4096.0),
            (-3072.0, 4096.0),
            (3072.0, 4096.0),
            (-3584.0, 0.0),
            (3584.0, 0.0),
        )
        + _pads(
            False,
            70.0,
            (0.0, -4240.0),
            (-1792.0, -4184.0),
            (1792.0, -4184.0),
            (-940.0, -3308.0),
            (940.0, -3308.0),
            (0.0, -2816.0),
            (-3584.0, -2484.0),
            (3584.0, -2484.0),
            (-1788.0, -2300.0),
            (1788.0, -2300.0),
            (-2048.0, -1036.0),
            (0.0, -1024.0),
            (2048.0, -1036.0),
            (-1024.0, 0.0),
            (1024.0, 0.0),
            (-2048.0, 1036.0),
            (0.0, 1024.0),
            (2048.0, 1036.0),
            (-1788.0, 2300.0),
            (1788.0, 2300.0),
            (-3584.0, 2484.0),
            (3584.0, 2484.0),
            (0.0, 2816.0),
            (-940.0, 3310.0),
            (940.0, 3308.0),
            (-1792.0, 4184.0),
            (1792.0, 4184.0),
            (0.0, 4240.0),
        )
    )
)
