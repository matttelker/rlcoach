"""What a replay holds once read: its header, and its frames as normalize makes them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from ..field_constants import Vec3

__all__ = [
    "BallFrame",
    "BoostPadEventFrame",
    "Dodge",
    "Frame",
    "GoalHeader",
    "Header",
    "ParserDemoEvent",
    "ParserTouchEvent",
    "PlayerFrame",
    "PlayerInfo",
    "Quaternion",
    "TouchCount",
    "Vec3",
]


class Quaternion(NamedTuple):
    x: float
    y: float
    z: float
    w: float


@dataclass(frozen=True)
class PlayerInfo:
    """One row of the header's player list: someone who finished the match."""

    name: str
    team: int = 0  # 0 blue, 1 orange
    # Their accounts, such as {"epic": "abc123"}. See header.py for which
    platform_ids: dict[str, str] = field(default_factory=dict)
    # The scoreboard: Score, Goals, Assists, Saves and Shots
    stats: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class GoalHeader:
    """A goal as the header lists it: the frame it was scored on and the scorer."""

    frame: int | None = None
    player_name: str | None = None
    player_team: int | None = None


@dataclass(frozen=True)
class Header:
    """What the replay says about its match before any frame is read."""

    match_type: str | None = None  # "Online", "Tournament", "Private" and so on
    map_name: str | None = None
    team_size: int = 0
    team0_score: int = 0
    team1_score: int = 0
    started_at_utc: str | None = None
    recorded_by: str | None = None  # The player whose game saved the replay
    players: list[PlayerInfo] = field(default_factory=list)
    goals: list[GoalHeader] = field(default_factory=list)


@dataclass(frozen=True)
class PlayerFrame:
    """One car in one frame."""

    player_id: str
    team: int
    position: Vec3
    velocity: Vec3
    boost_amount: int  # 0 to 100
    angular_velocity: Vec3 = Vec3(0.0, 0.0, 0.0)  # Radians a second
    quaternion: Quaternion | None = None  # None until the car sends its rotation
    is_demolished: bool = False
    # Whether the car is jumping or flipping, from the game itself. A jump lasts
    # about 0.1 s and a flip, from its start until it's done, about 0.7 s
    is_jumping: bool = False
    is_double_jumping: bool = False
    is_dodging: bool = False


@dataclass(frozen=True)
class BallFrame:
    position: Vec3
    velocity: Vec3


@dataclass(frozen=True)
class BoostPadEventFrame:
    """A boost pad taken. `pad_id` indexes `field_constants.BOOST_PADS`."""

    pad_id: int
    player_id: str
    player_team: int | None = None
    # When it was taken, which can be before the frame that reports it
    timestamp: float | None = None


@dataclass(frozen=True)
class Dodge:
    """A flip. `torque` is in the car's own axes and points the way the stick did."""

    timestamp: float
    player_id: str
    torque: Vec3


@dataclass(frozen=True)
class ParserTouchEvent:
    """The game's first-touch counter rising for a player."""

    timestamp: float
    player_id: str


@dataclass(frozen=True)
class TouchCount:
    """The game's touch counter rising for a player: they touched the ball `count`
    times since it last rose. It rises up to a second after a touch."""

    player_id: str
    count: int


@dataclass(frozen=True)
class ParserDemoEvent:
    timestamp: float
    victim_id: str
    attacker_id: str | None = None


@dataclass(frozen=True)
class Frame:
    """The ball and every car at one moment, and what the replay says happened then."""

    timestamp: float  # Seconds from the first frame
    ball: BallFrame
    # The team that touched the ball last, from the ball itself, which sends it on
    # the frame of a touch that changes it. None before a kickoff's first touch
    hit_team: int | None = None
    players: list[PlayerFrame] = field(default_factory=list)
    boost_pad_events: list[BoostPadEventFrame] = field(default_factory=list)
    dodges: list[Dodge] = field(default_factory=list)
    touch_counts: list[TouchCount] = field(default_factory=list)
    # When the game's first-touch counter rose, up to a second after the touch itself
    parser_first_touch_events: list[ParserTouchEvent] = field(default_factory=list)
    parser_demo_events: list[ParserDemoEvent] = field(default_factory=list)

    def get_player_by_id(self, player_id: str) -> PlayerFrame | None:
        return next((p for p in self.players if p.player_id == player_id), None)
