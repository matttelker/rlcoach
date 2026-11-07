"""Kickoffs: when each countdown released the cars, and how every car played it.

A kickoff runs from the release until the ball is first played, or 5 s at most.
For each car it records:
- its role. The car nearest the centre spot on each team goes (GO), and the
  rest are WING, CHEAT or BACK by where they spawned. Teammates on level spawns
  agree between them who goes, so GO moves to the one that got nearer the ball.
- how it played the kickoff, read from its own dodges and movement
- the boost it used, and how soon it reached the ball
And for the kickoff, who touched the ball first and when. The game's own
first-touch counter names the player where the replay has one. Otherwise it's
the car the ball leaves away from, which in a 50/50 is the one that won it.

What real replays show, measured on 17 to 19 of them:
- The ball resets, drops onto the spot, and the cars are released about 4 s
  later. Only a countdown holds the ball and every car still for 2 s or more.
- Car positions refresh every 2 or 3 frames, so at contact cars read 150 to
  300 uu from the ball. After a countdown only a car moves the ball sideways,
  while Hoops launches it straight up, so sideways speed marks the contact.
- The first-touch counter arrives up to a second after the contact.
- A flip spins the car about its dodge torque at 5.5 rad/s. A speedflip's cancel
  takes the pitch out of that spin while the roll carries on, so the roof comes
  round with the nose level. Some cars' rotation replicates 0.2 s late, so the
  spin is judged by its median.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field, replace
from itertools import groupby

from ..parser.types import BallFrame, Frame, ParserTouchEvent, PlayerFrame, Vec3
from .types import GoalEvent, distance, speed, team_name

SPOT = Vec3(0.0, 0.0, 93.15)
SPOT_REACH = 120.0  # Ball this close to the spot across the field
SPOT_HEIGHT_REACH = 60.0  # The ball drops onto the spot after a reset
STILL_UU_S = 50.0  # Ball and cars move slower than this while held
COUNTDOWN_MIN_S = 2.0  # Real countdowns hold 3.1 s or more, other stops under 1
LONGEST_S = 5.0
SHORTEST_S = 0.05
PLAYED_UU_S = 75.0  # Sideways ball speed once a car has hit it

NEAR_BALL_UU = 180.0  # A car this close is touching the ball
CONTACT_REACH_UU = 400.0  # A car this close as the ball is played is contesting
COUNTER_LAG_S = 1.5  # Allowed for the first-touch counter to arrive
ARRIVING_S = 1.0  # A GO car this far out as the ball is played was still racing

LEVEL_SPAWN_UU = 100.0  # Spawns this close to level are equal
WING_X, WING_Y = 1700.0, 3600.0  # Spawns out wide, and not too deep
CHEAT_Y = 3200.0  # Spawns nearer the centre than this, not wide
CHEAT_ADVANCE_UU = 750.0  # A support car that moved this far toward the spot
STATIONARY_UU = 300.0  # A GO car that went no further than this, without boost
STATIONARY_BOOST = 5.0
BOOST_APPROACH = 10.0  # A car that used more boost reached the ball on it
MOVED_UU = 150.0

FRONTFLIP_MAX_DEG = 15.0  # A dodge this close to straight ahead
PITCH_TORQUE_MIN = 0.4  # Weaker pitch torque than this can't show a cancel
SPIN_RATE = 5.5  # Rad/s about the dodge torque
SPIN_WINDOW_S = (0.08, 0.5)  # After the dodge, where the cancel shows
CANCELLED_PITCH_SHARE = 0.5  # Of the flip's expected pitch rate, at most


@dataclass(frozen=True)
class KickoffPlayer:
    """How one car played one kickoff."""

    player_id: str
    role: str  # "GO", "CHEAT", "WING" or "BACK"
    # How it got to the ball: SPEEDFLIP, STANDARD_FRONTFLIP, STANDARD_DIAGONAL,
    # STANDARD_BOOST or STANDARD. A GO car that didn't contest it faked:
    # FAKE_HALFFLIP, FAKE_STATIONARY or FAKE_AGGRESSIVE. Another car that
    # didn't is support: SUPPORT_CHEAT or SUPPORT_HOLD. UNKNOWN if it never moved.
    approach: str
    boost_used: float
    time_to_ball: float | None  # Seconds from the release, if it got there


@dataclass(frozen=True)
class KickoffEvent:
    """One kickoff, from the release of the cars."""

    t_start: float
    phase: str = "INITIAL"  # "OT" for the kickoff that starts overtime
    players: tuple[KickoffPlayer, ...] = ()
    first_touch_player: str | None = None
    time_to_first_touch: float | None = None  # From the release
    first_touch_team: str | None = None  # "BLUE" or "ORANGE"


def ball_on_spot(ball: BallFrame) -> bool:
    return (
        abs(ball.position.x - SPOT.x) <= SPOT_REACH
        and abs(ball.position.y - SPOT.y) <= SPOT_REACH
        and abs(ball.position.z - SPOT.z) <= SPOT_HEIGHT_REACH
    )


def held_still(frame: Frame) -> bool:
    """The ball is at rest and every car waits."""
    return (
        speed(frame.ball.velocity) < STILL_UU_S
        and bool(frame.players)
        and all(speed(car.velocity) < STILL_UU_S for car in frame.players)
    )


def is_held_for_kickoff(frame: Frame) -> bool:
    """The ball waits on the centre spot and every car is held still."""
    return ball_on_spot(frame.ball) and held_still(frame)


def releases(frames: list[Frame]) -> set[int]:
    """The frame where each countdown releases the cars.

    The hold runs from the first still frame on the spot to the last, so a car
    that twitches mid-countdown can't end it early. The ball settling after a
    reset, passing over the spot, or a placeholder frame never holds for 2 s.
    """
    found = set()
    for on_spot, run in groupby(
        range(len(frames)), key=lambda i: ball_on_spot(frames[i].ball)
    ):
        held = [i for i in run if on_spot and held_still(frames[i])]
        if (
            held
            and frames[held[-1]].timestamp - frames[held[0]].timestamp
            >= COUNTDOWN_MIN_S
        ):
            found.add(held[-1])
    return found


def _spawn_reach(spawn: Vec3) -> float:
    """How far a spawn is from the centre spot, across the field."""
    return distance(spawn, Vec3(0.0, 0.0, spawn.z))


def _spin(car: PlayerFrame) -> tuple[float, float] | None:
    """The car's pitch rate in its own frame, and how far its roof points up."""
    quaternion = getattr(car.rotation, "quaternion", None)
    spin = car.angular_velocity
    if quaternion is None or spin is None:
        return None
    x, y, z, w = quaternion
    pitch_rate = (
        spin.x * 2.0 * (x * y - z * w)
        + spin.y * (1.0 - 2.0 * (x * x + z * z))
        + spin.z * 2.0 * (y * z + x * w)
    )
    return pitch_rate, 1.0 - 2.0 * (x * x + y * y)


def _arrival(car: PlayerFrame, ball: BallFrame) -> float:
    """Seconds until a car reaches the ball at the speed it's closing at."""
    offset = Vec3(*(b - c for b, c in zip(ball.position, car.position, strict=True)))
    reach = math.hypot(*offset)
    if reach == 0.0:
        return 0.0
    closing = sum(o * v for o, v in zip(offset, car.velocity, strict=True)) / reach
    return reach / closing if closing > 0.0 else math.inf


def _departure(car: PlayerFrame, ball: BallFrame) -> float:
    """How directly the ball is leaving away from a car, 1 down to -1."""
    offset = [b - c for b, c in zip(ball.position, car.position, strict=True)]
    scale = math.hypot(*offset) * speed(ball.velocity)
    if scale == 0.0:
        return 0.0
    return sum(o * v for o, v in zip(offset, ball.velocity, strict=True)) / scale


def _role(spawn: Vec3, order: int) -> str:
    if order == 0:
        return "GO"
    if abs(spawn.x) >= WING_X and abs(spawn.y) <= WING_Y:
        return "WING"
    if abs(spawn.y) <= CHEAT_Y:
        return "CHEAT"
    return "BACK"


@dataclass
class _Car:
    """What one car did so far in a kickoff, times counted from the release."""

    team: int
    spawn: Vec3
    start_boost: float
    role: str = "BACK"
    last: Vec3 = Vec3(0.0, 0.0, 0.0)
    least_boost: float = 0.0
    farthest: float = 0.0  # From its spawn
    nearest: float = math.inf  # To the ball
    touched: float | None = None  # First within touching distance of the ball
    contact: float | None = None  # In reach as the ball was played
    arrival: float = math.inf  # Seconds out as the ball was played
    dodges: list[tuple[float, float, float]] = field(default_factory=list)
    spins: list[tuple[float, float, float]] = field(default_factory=list)

    @property
    def boost_used(self) -> float:
        return max(0.0, self.start_boost - self.least_boost)

    def is_contesting(self) -> bool:
        """It went for the ball: it was in reach, or as GO, still closing on it.

        Other roles get no credit for closing, because they pass the ball at
        every range on their way upfield.
        """
        if self.contact is not None or self.touched is not None:
            return True
        return self.role == "GO" and self.arrival <= ARRIVING_S

    def cancelled(self, dodge: tuple[float, float, float]) -> bool:
        """A forward dodge whose pitch stopped while the car rolled over."""
        at, torque_x, torque_y = dodge
        if torque_y < PITCH_TORQUE_MIN:
            return False
        start, end = at + SPIN_WINDOW_S[0], at + SPIN_WINDOW_S[1]
        window = [s for s in self.spins if start <= s[0] <= end]
        # A dodge this close to the end of the kickoff is the flip into the ball
        if not window or self.spins[-1][0] < end:
            return False
        expected = SPIN_RATE * torque_y / math.hypot(torque_x, torque_y)
        share = statistics.median(rate for _, rate, _ in window) / expected
        return share < CANCELLED_PITCH_SHARE and min(r for _, _, r in window) < 0.0

    def approach(self) -> str:
        boost = self.boost_used
        if not self.is_contesting():
            if self.role == "GO":
                if any(ty <= -PITCH_TORQUE_MIN for _, _, ty in self.dodges):
                    return "FAKE_HALFFLIP"
                if self.farthest < STATIONARY_UU and boost < STATIONARY_BOOST:
                    return "FAKE_STATIONARY"
                return "FAKE_AGGRESSIVE"
            advance = distance(self.spawn, SPOT) - distance(self.last, SPOT)
            return "SUPPORT_CHEAT" if advance >= CHEAT_ADVANCE_UU else "SUPPORT_HOLD"
        if any(self.cancelled(dodge) for dodge in self.dodges):
            return "SPEEDFLIP"
        if self.dodges:
            _, torque_x, torque_y = self.dodges[0]
            angle = math.degrees(math.atan2(abs(torque_x), torque_y))
            return (
                "STANDARD_FRONTFLIP"
                if angle <= FRONTFLIP_MAX_DEG
                else "STANDARD_DIAGONAL"
            )
        if boost > BOOST_APPROACH:
            return "STANDARD_BOOST"
        return "STANDARD" if boost > 0.0 or self.farthest > MOVED_UU else "UNKNOWN"


class _Kickoff:
    """A kickoff in progress, from the frame that released the cars."""

    def __init__(self, release: Frame):
        self.start = release.timestamp
        self.cars = {
            car.player_id: _Car(
                team=car.team,
                spawn=car.position,
                start_boost=float(car.boost_amount),
                last=car.position,
                least_boost=float(car.boost_amount),
            )
            for car in release.players
        }
        # (player, team, seconds from the release) of the first touch so far
        self.first_touch: tuple[str, int, float | None] | None = None
        for team in {car.team for car in self.cars.values()}:
            mates = sorted(
                (car for car in self.cars.values() if car.team == team),
                key=lambda car: _spawn_reach(car.spawn),
            )
            for order, car in enumerate(mates):
                car.role = _role(car.spawn, order)

    def watch(self, frame: Frame) -> None:
        now = frame.timestamp - self.start
        ball = frame.ball.position
        for car in frame.players:
            state = self.cars.get(car.player_id)
            if state is None:  # Someone who joined mid-kickoff
                continue
            state.last = car.position
            state.least_boost = min(state.least_boost, float(car.boost_amount))
            state.farthest = max(state.farthest, distance(car.position, state.spawn))
            spin = _spin(car)
            if spin is not None:
                state.spins.append((now, *spin))
            gap = distance(car.position, ball)
            state.nearest = min(state.nearest, gap)
            if gap < NEAR_BALL_UU:
                if state.touched is None:
                    state.touched = now
                if self.first_touch is None or now < self.first_touch[2]:
                    self.first_touch = (car.player_id, state.team, now)
        for event in frame.component_events:
            if event.kind == "dodge_torque" and event.vector is not None:
                state = self.cars.get(event.player_id)
                if state is not None:
                    state.dodges.append((now, event.vector.x, event.vector.y))

    def played(self, frame: Frame) -> None:
        """The ball was played on this frame: credit the car it left away from.

        A car in reach is contesting the ball even if it lost it.
        """
        ball = frame.ball
        cars = [car for car in frame.players if car.player_id in self.cars]
        if not cars:
            return
        contesting = [
            car
            for car in cars
            if distance(car.position, ball.position) <= CONTACT_REACH_UU
        ] or [min(cars, key=lambda car: distance(car.position, ball.position))]
        now = frame.timestamp - self.start
        for car in contesting:
            self.cars[car.player_id].contact = now
        for car in cars:
            self.cars[car.player_id].arrival = _arrival(car, ball)
        toucher = max(contesting, key=lambda car: _departure(car, ball))
        self.first_touch = (toucher.player_id, self.cars[toucher.player_id].team, now)

    def _credit_counter(self, closing: Frame, counter: list[ParserTouchEvent]) -> None:
        """Name the player the game's counter did. The time stays the frames'."""
        latest = closing.timestamp + COUNTER_LAG_S
        for event in counter:
            state = self.cars.get(event.player_id)
            if state is None or not self.start <= event.timestamp <= latest:
                continue
            at = self.first_touch[2] if self.first_touch else None
            if at is not None:
                state.contact = at
            self.first_touch = (event.player_id, state.team, at)
            return

    def _settle_level_spawns(self) -> None:
        """Give GO to the teammate on a level spawn who got nearer the ball."""
        for go in [car for car in self.cars.values() if car.role == "GO"]:
            level = [
                car
                for car in self.cars.values()
                if car.team == go.team
                and abs(_spawn_reach(car.spawn) - _spawn_reach(go.spawn))
                <= LEVEL_SPAWN_UU
            ]
            taker = min(level, key=lambda car: car.nearest)
            if taker.nearest < go.nearest:
                go.role, taker.role = taker.role, go.role

    def close(
        self, frame: Frame, counter: list[ParserTouchEvent]
    ) -> KickoffEvent | None:
        if frame.timestamp - self.start < SHORTEST_S:
            return None
        self._credit_counter(frame, counter)
        self._settle_level_spawns()
        players = []
        for player_id, car in self.cars.items():
            reached = car.contact if car.contact is not None else car.touched
            players.append(
                KickoffPlayer(
                    player_id=player_id,
                    role=car.role,
                    approach=car.approach(),
                    boost_used=round(car.boost_used, 2),
                    time_to_ball=None if reached is None else round(reached, 3),
                )
            )
        toucher, team, at = self.first_touch or (None, None, None)
        return KickoffEvent(
            t_start=self.start,
            players=tuple(players),
            first_touch_player=toucher,
            time_to_first_touch=None if at is None else round(at, 3),
            first_touch_team=None if team is None else team_name(team),
        )


def _mark_overtime(
    kickoffs: list[KickoffEvent], goals: list[GoalEvent]
) -> list[KickoffEvent]:
    """Label the kickoff that starts overtime, if the game had one.

    Replay time can't show this: the clock stops for countdowns and after goals,
    so regulation kickoffs land well past 300 s. The rules can. Every kickoff
    after the first follows a goal, except the one that starts overtime. That one
    comes at a level score, and it's the last, since the next goal ends the game.
    With no goals nothing proves overtime.
    """
    if not goals or len(kickoffs) < 2:
        return kickoffs
    last, previous = kickoffs[-1].t_start, kickoffs[-2].t_start
    before = [goal for goal in goals if goal.t < last]
    blue = sum(1 for goal in before if goal.team == "BLUE")
    if any(goal.t >= previous for goal in before) or blue * 2 != len(before):
        return kickoffs
    return [*kickoffs[:-1], replace(kickoffs[-1], phase="OT")]


def detect_kickoffs(frames: list[Frame], goals: list[GoalEvent]) -> list[KickoffEvent]:
    """Every kickoff that followed a countdown, in order.

    A replay whose frames show no countdown has no kickoffs.
    """
    released = releases(frames)
    counter = [event for frame in frames for event in frame.parser_first_touch_events]
    kickoffs = []
    current: _Kickoff | None = None
    for index, frame in enumerate(frames):
        if current is None:
            if index in released:
                current = _Kickoff(frame)
            continue
        current.watch(frame)
        played = math.hypot(frame.ball.velocity.x, frame.ball.velocity.y) > PLAYED_UU_S
        if played:
            current.played(frame)
        if played or frame.timestamp - current.start >= LONGEST_S:
            kickoffs.append(current.close(frame, counter))
            current = None
    if current is not None:
        kickoffs.append(current.close(frames[-1], counter))
    return _mark_overtime([k for k in kickoffs if k is not None], goals)
