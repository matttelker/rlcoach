"""Kickoffs: when each countdown released the cars, and how every car played it.

A kickoff runs from the release until the ball is first played, or 5 s at most.
For each car it records:
- its role. The car nearest the centre spot on each team goes (GO), and the
  rest are WING, CHEAT or BACK by where they spawned. Teammates on level spawns
  agree between them who goes, so GO moves to the one that got nearer the ball.
- its spawn: diagonal, off-centre or back
- how it played the kickoff, read from its own dodges and movement
- the boost it used, and how soon it reached the ball
- for a car that went for the ball, when its flip into it began, how soon it
  got within 1000 uu, and how fast it was going as the ball was played
And for the kickoff, who touched the ball first and when, and where the ball
was a second later. The game's own first-touch counter names the player where
the replay has one. Otherwise it's the car the ball leaves away from, which in
a 50/50 is the one that won it.

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
- On 42 of one player's games (540 GO cars), the flips into the ball that won
  the first touch began a median 0.11 s before the ball was played. One that
  shows up to 0.15 s after it was the flip into the ball, too late.
- The car that got within 1000 uu first won the first touch 91% of the time.
  Where the ball went is another matter. A second after the hit it had come
  back past 500 uu toward the car's own goal 28% of the time with a flip on
  time, 31% when it came late, 50% with no flip, and 60% when the last flip
  was long before contact. Getting there first made no difference to that.
"""

from __future__ import annotations

import bisect
import math
import statistics
from collections.abc import Sequence
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

LATE_FLIP_S = 0.15  # A dodge this soon after the ball was played was into it
ON_TIME_MAX_S = 0.45  # A flip further ahead of the ball was for speed, not into it
REACH_UU = 1000.0  # How near the ball, across the field, a car has got there
RESULT_AFTER_S = 1.0  # Where the ball is this long after the hit
RESULT_REACH_UU = 500.0  # Past this toward a goal, the ball went that team's way
DIAGONAL_DEPTH = 3200.0  # Spawns nearer their goal line than this are diagonal
OFF_CENTRE_DEPTH = 4200.0  # And nearer than this off-centre, behind it back

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
    team: int | None = None  # 0 blue, 1 orange
    spot: str | None = None  # Its spawn: DIAGONAL, OFF_CENTRE or BACK
    # For a car that went for the ball: seconds before the ball was played that
    # its flip into it began, below 0 if after. None if it didn't flip into it.
    flip_lead: float | None = None
    reach_time: float | None = None  # Seconds from the release to REACH_UU
    speed_at_contact: float | None = None  # uu/s as the ball was played


@dataclass(frozen=True)
class KickoffEvent:
    """One kickoff, from the release of the cars."""

    t_start: float
    phase: str = "INITIAL"  # "OT" for the kickoff that starts overtime
    players: tuple[KickoffPlayer, ...] = ()
    first_touch_player: str | None = None
    time_to_first_touch: float | None = None  # From the release
    first_touch_team: str | None = None  # "BLUE" or "ORANGE"
    # The ball's y a second after it was played. Blue attacks toward +y.
    ball_y_after: float | None = None


WENT_FOR_BALL = frozenset(
    {
        "SPEEDFLIP",
        "STANDARD_FRONTFLIP",
        "STANDARD_DIAGONAL",
        "STANDARD_BOOST",
        "STANDARD",
    }
)


def went_for_ball(player: KickoffPlayer) -> bool:
    """The car contested the ball, rather than faking or supporting."""
    return player.approach in WENT_FOR_BALL


def flip_timing(player: KickoffPlayer) -> str | None:
    """How a car that went for the ball flipped into it: ON_TIME, LATE or NONE.

    None for a car that didn't go for it. A flip that began after the ball was
    played came LATE. One that began long before was for speed, so NONE.
    """
    if not went_for_ball(player):
        return None
    lead = player.flip_lead
    if lead is None or lead > ON_TIME_MAX_S:
        return "NONE"
    return "LATE" if lead < 0.0 else "ON_TIME"


def went_with(kickoff: KickoffEvent, player: KickoffPlayer) -> list[KickoffPlayer]:
    """Teammates who went for the ball along with `player`: a double commit.

    A teammate who came from behind `player` going is their mistake alone, but
    from level spawns it's on both of them.
    """
    if not went_for_ball(player):
        return []
    return [
        mate
        for mate in kickoff.players
        if mate.team == player.team
        and mate.player_id != player.player_id
        and went_for_ball(mate)
        and (player.role != "GO" or mate.spot == player.spot)
    ]


def kickoff_result(kickoff: KickoffEvent, team: int) -> str | None:
    """WON, EVEN or LOST for a team, by where the ball was a second after the hit.

    That says more than the first touch: the car there first gets it, but a flip
    arriving a moment later often sends the ball back the other way.
    """
    if kickoff.ball_y_after is None:
        return None
    forward = kickoff.ball_y_after if team == 0 else -kickoff.ball_y_after
    if forward > RESULT_REACH_UU:
        return "WON"
    return "LOST" if forward < -RESULT_REACH_UU else "EVEN"


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


def _across(a: Vec3, b: Vec3) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _spot(spawn: Vec3) -> str:
    depth = abs(spawn.y)
    if depth < DIAGONAL_DEPTH:
        return "DIAGONAL"
    return "OFF_CENTRE" if depth < OFF_CENTRE_DEPTH else "BACK"


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
    late_dodges: list[float] = field(default_factory=list)  # After the play
    spins: list[tuple[float, float, float]] = field(default_factory=list)
    reach_time: float | None = None
    # (seconds out, distance across the field) at its last position update
    fresh: tuple[float, float] | None = None
    speed_at_contact: float | None = None

    @property
    def boost_used(self) -> float:
        return max(0.0, self.start_boost - self.least_boost)

    def track_reach(self, now: float, position: Vec3, ball: Vec3) -> None:
        """Time the car crossing REACH_UU, between its position updates.

        Positions refresh every 2 or 3 frames and repeat in between, so a
        repeated position is no update.
        """
        if self.reach_time is not None or position == self.last:
            return
        gap = _across(position, ball)
        if gap <= REACH_UU:
            if self.fresh is None or self.fresh[1] <= REACH_UU:
                self.reach_time = now
            else:
                then, before = self.fresh
                share = (before - REACH_UU) / (before - gap)
                self.reach_time = then + (now - then) * share
        self.fresh = (now, gap)

    def flip_lead(self, contact: float | None) -> float | None:
        """Seconds before `contact` its flip into the ball began, if it went."""
        if contact is None or not self.is_contesting():
            return None
        into = [
            at
            for at in [at for at, _, _ in self.dodges] + self.late_dodges
            if at - contact <= LATE_FLIP_S
        ]
        return round(contact - max(into), 3) if into else None

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
                fresh=(0.0, _across(car.position, release.ball.position)),
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
            state.track_reach(now, car.position, ball)
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
            self.cars[car.player_id].speed_at_contact = round(speed(car.velocity), 1)
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
        self,
        frame: Frame,
        counter: list[ParserTouchEvent],
        after: Sequence[Frame] = (),
    ) -> KickoffEvent | None:
        """Finish the kickoff on `frame`, given the frames up to a second later.

        Those later frames show a flip into the ball that came too late, and
        where the ball went.
        """
        if frame.timestamp - self.start < SHORTEST_S:
            return None
        self._credit_counter(frame, counter)
        self._settle_level_spawns()
        for later in after:
            for event in later.component_events:
                if event.kind == "dodge_torque" and event.player_id in self.cars:
                    self.cars[event.player_id].late_dodges.append(
                        later.timestamp - self.start
                    )
        toucher, team, at = self.first_touch or (None, None, None)
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
                    team=car.team,
                    spot=_spot(car.spawn),
                    flip_lead=car.flip_lead(at),
                    reach_time=(
                        None if car.reach_time is None else round(car.reach_time, 3)
                    ),
                    speed_at_contact=car.speed_at_contact,
                )
            )
        result_at = frame.timestamp + RESULT_AFTER_S
        settled = [f for f in after if f.timestamp >= result_at - 1e-6]
        return KickoffEvent(
            t_start=self.start,
            players=tuple(players),
            first_touch_player=toucher,
            time_to_first_touch=None if at is None else round(at, 3),
            first_touch_team=None if team is None else team_name(team),
            ball_y_after=round(settled[0].ball.position.y, 1) if settled else None,
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
    times = [frame.timestamp for frame in frames]
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
            # Up to and including the first frame a second on
            end = bisect.bisect_left(times, frame.timestamp + RESULT_AFTER_S - 1e-6)
            kickoffs.append(current.close(frame, counter, frames[index + 1 : end + 1]))
            current = None
        elif frame.timestamp - current.start >= LONGEST_S:
            kickoffs.append(current.close(frame, counter))
            current = None
    if current is not None:
        kickoffs.append(current.close(frames[-1], counter))
    return _mark_overtime([k for k in kickoffs if k is not None], goals)
