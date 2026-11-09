"""Touches: the game's own count of each player's touches, placed in time by the ball.

The game counts every player's touches, and the replay carries the count. It says
who touched the ball and how often, but reaches the replay up to a second after the
touch (a median 0.44 s on your games). The ball says when: it sends the team that
touched it last on the very frame of a touch that changes it. So touches are placed
in two passes:

1. Each change of the ball's team is a touch on that frame, by the player of that
   team whose count rose next and whose car was nearest the ball.
2. Every other touch the count says happened goes at a kick: a frame where the
   ball's speed changed by more than gravity explains, with the player's car in
   reach. A kick where the ball says the other team touched it last comes last, as
   does one that fits a bounce off a wall or the floor, or one another player's
   touch took. A touch too soft to kick the ball goes at the frame where the car
   came nearest to it.

Two touches by opposing players inside one frame show as one change of team. The
touch of the team the ball doesn't name goes on that frame too, before the other.

Replays from before the game counted touches (net version 11 and older) get their
touches from the kicks alone: the car in reach that could push the ball the way it
went, preferring the team the ball names.
"""

from __future__ import annotations

import math
from bisect import bisect_right, insort
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from functools import partial

from ..field_constants import BACK_WALL_Y, CEILING_Z, SIDE_WALL_X
from ..parser.types import BallFrame, Frame, PlayerFrame
from ..physics_constants import BALL_RADIUS_UU, UU_S_TO_KPH
from .types import TouchEvent, speed

COUNTER_LAG_S = 1.1  # The count rises up to this long after the touch
COUNTER_EARLY_S = 0.05  # The ball can show a touch a frame after the count rises
REACH_UU = 350.0  # A car this close to the ball at a kick can have made it
KICKER_REACH_UU = 300.0  # Without the count, a kick needs a car this close
BOUNCE_REACH_UU = 165.0  # and a bounce-shaped one a car right there
PUSH_MIN_FIT = 0.7  # 1 means the ball's speed changed straight away from the car
KICK_MIN_SPEED_CHANGE = 200.0  # uu/s beyond what gravity adds
SAME_TOUCH_S = 0.15  # One player's touches are at least this far apart
MAX_FRAME_GAP_S = 0.5  # Longer gaps are goal replays
GRAVITY_UU_S2 = 650.0
BOUNCE_GAP_SLOP = 30.0
BOUNCE_SPEED_SLOP = 100.0


@dataclass
class _Rise:
    """A player's count rose: `left` more touches to place between start and end."""

    player: str
    left: int
    start: float
    end: float
    chosen: list[int] = field(default_factory=list)


def detect_touches(frames: Sequence[Frame]) -> list[TouchEvent]:
    """Every touch the game counted that the frames can place, in time order.

    On one frame, the touch by the team the ball names comes last.
    """
    rises = list(_rises(frames))
    if not rises:
        return _kick_touches(frames)
    placer = _Placer(frames)
    placer.anchor(rises)
    for rise in rises:
        placer.fill(rise)
    touches = [
        _touch(frames, index, rise.player) for rise in rises for index in rise.chosen
    ]
    return sorted(touches, key=partial(_order, frames))


def _order(frames: Sequence[Frame], touch: TouchEvent) -> tuple[float, bool, str]:
    named = frames[touch.frame].hit_team == touch.team
    return (touch.t, named, touch.player_id)


def _rises(frames: Sequence[Frame]) -> Iterable[_Rise]:
    last: dict[str, float] = {}
    for frame in frames:
        t = frame.timestamp
        for rise in frame.touch_counts:
            start = t - COUNTER_LAG_S
            if rise.player_id in last:
                # Touches before the last rise were in that count
                start = max(start, last[rise.player_id] - COUNTER_EARLY_S)
            last[rise.player_id] = t
            yield _Rise(rise.player_id, rise.count, start, t + COUNTER_EARLY_S)


class _Placer:
    def __init__(self, frames: Sequence[Frame]):
        self.frames = frames
        self.times = [frame.timestamp for frame in frames]
        self.kicks = _kicks(frames)
        self.kick_times = [self.times[index] for index, _ in self.kicks]
        self.taken: dict[int, set[str]] = defaultdict(set)  # Whose touch each frame is
        self.placed: dict[str, list[float]] = defaultdict(list)  # In time order

    def anchor(self, rises: list[_Rise]) -> None:
        """Pass 1: give each change of the ball's team to a player of that team."""
        for index in range(1, len(self.frames)):
            frame = self.frames[index]
            team = frame.hit_team
            if team is None or team == self.frames[index - 1].hit_team:
                continue
            best: tuple[float, _Rise] | None = None
            for rise in rises:
                if not (rise.left and rise.start < frame.timestamp <= rise.end):
                    continue
                car = frame.get_player_by_id(rise.player)
                gap = _gap(frame, rise.player)
                if car is None or car.team != team or gap is None:
                    continue
                if self._apart(rise.player, index) and (best is None or gap < best[0]):
                    best = (gap, rise)
            if best is not None:
                self._choose(best[1], index)

    def fill(self, rise: _Rise) -> None:
        """Pass 2: place the rest of the rise's touches."""
        for index in self._kicks_in_reach(rise) + self._nearest(rise):
            if not rise.left:
                break
            if self._apart(rise.player, index):
                self._choose(rise, index)

    def _choose(self, rise: _Rise, index: int) -> None:
        rise.chosen.append(index)
        rise.left -= 1
        self.taken[index].add(rise.player)
        insort(self.placed[rise.player], self.times[index])

    def _kicks_in_reach(self, rise: _Rise) -> list[int]:
        """Kicks with the player's car in reach, best first."""
        first = bisect_right(self.kick_times, rise.start)
        last = bisect_right(self.kick_times, rise.end)
        ranked = []
        for index, rebound in self.kicks[first:last]:
            gap = _gap(self.frames[index], rise.player)
            if gap is not None and gap <= REACH_UU:
                others = bool(self.taken[index] - {rise.player})
                fits = self._fits(rise.player, index)
                # Where the ball names the other team, its change of team is
                # likeliest: a 50/50 inside one frame
                change = fits or self._changes(index)
                ranked.append(((not fits, not change, rebound, others, gap), index))
        return [index for _, index in sorted(ranked)]

    def _changes(self, index: int) -> bool:
        """Whether the ball changed team on this frame."""
        team = self.frames[index].hit_team
        return team is not None and team != self.frames[index - 1].hit_team

    def _nearest(self, rise: _Rise) -> list[int]:
        """Frames with the player's car on the field, nearest the ball first."""
        first = bisect_right(self.times, rise.start)
        last = bisect_right(self.times, rise.end)
        ranked = []
        for index in range(first, last):
            gap = _gap(self.frames[index], rise.player)
            if gap is not None:
                ranked.append(((not self._fits(rise.player, index), gap), index))
        return [index for _, index in sorted(ranked)]

    def _fits(self, player: str, index: int) -> bool:
        """Whether the ball says the player's team touched it last. A replay whose
        ball doesn't say fits anywhere."""
        frame = self.frames[index]
        car = frame.get_player_by_id(player)
        return car is None or frame.hit_team in (None, car.team)

    def _apart(self, player: str, index: int) -> bool:
        """Whether a touch at this frame is apart from the player's others."""
        placed, t = self.placed[player], self.times[index]
        i = bisect_right(placed, t - SAME_TOUCH_S)
        return i == len(placed) or placed[i] >= t + SAME_TOUCH_S


def _gap(frame: Frame, player_id: str) -> float | None:
    """How far the player's car is from the ball, or None if it's not on the field."""
    car = frame.get_player_by_id(player_id)
    if car is None or car.is_demolished:
        return None
    return math.dist(car.position, frame.ball.position)


def _touch(frames: Sequence[Frame], index: int, player_id: str) -> TouchEvent:
    frame = frames[index]
    car = frame.get_player_by_id(player_id)
    return TouchEvent(
        t=frame.timestamp,
        player_id=player_id,
        location=car.position if car else frame.ball.position,
        ball_speed_kph=round(speed(frame.ball.velocity) * UU_S_TO_KPH, 2),
        frame=index,
        team=car.team if car else None,
    )


def _kick_touches(frames: Sequence[Frame]) -> list[TouchEvent]:
    """Touches from the kicks alone, for a replay without the game's count."""
    touches: list[TouchEvent] = []
    last: dict[str, float] = {}
    for index, rebound in _kicks(frames):
        before, frame = frames[index - 1], frames[index]
        reach = BOUNCE_REACH_UU if rebound else KICKER_REACH_UU
        car = _kicker(frame, before.ball, reach)
        if car is None or frame.timestamp - last.get(car.player_id, -1e9) < 0.2:
            continue
        last[car.player_id] = frame.timestamp
        touches.append(_touch(frames, index, car.player_id))
    return touches


def _kicker(frame: Frame, before: BallFrame, reach: float) -> PlayerFrame | None:
    """The car in reach that kicked the ball.

    Of the team the ball names, if it does, the nearest car that could push the ball
    the way it went, because the nearest car can be a bystander beside the real hit.
    Car positions lag the ball, so if no car fits the push, the nearest one has it.
    """
    after = frame.ball

    def gap(car: PlayerFrame) -> float:
        return math.dist(car.position, after.position)

    cars = (car for car in frame.players if not car.is_demolished)
    in_reach = sorted((car for car in cars if gap(car) <= reach), key=gap)
    pool = [c for c in in_reach if c.team == frame.hit_team] or in_reach
    pushers = (c for c in pool if _push_fit(c, before, after) >= PUSH_MIN_FIT)
    return next(pushers, pool[0] if pool else None)


def _push_fit(car: PlayerFrame, before: BallFrame, after: BallFrame) -> float:
    """How well a ball's velocity change points away from a car, -1 to 1."""
    away = (
        after.position.x - car.position.x,
        after.position.y - car.position.y,
        after.position.z - car.position.z,
    )
    change = (
        after.velocity.x - before.velocity.x,
        after.velocity.y - before.velocity.y,
        after.velocity.z - before.velocity.z,
    )
    size = math.hypot(*away) * math.hypot(*change)
    if not size:
        return 0.0
    return sum(a * c for a, c in zip(away, change, strict=True)) / size


def _kicks(frames: Sequence[Frame]) -> list[tuple[int, bool]]:
    """Frames where the ball's speed changed by more than gravity explains, and
    whether the change fits a bounce."""
    kicks = []
    for index in range(1, len(frames)):
        before, after = frames[index - 1].ball, frames[index].ball
        dt = frames[index].timestamp - frames[index - 1].timestamp
        if 0 < dt <= MAX_FRAME_GAP_S and speed_change(before, after, dt) >= (
            KICK_MIN_SPEED_CHANGE
        ):
            kicks.append((index, is_rebound(before, after, dt)))
    return kicks


def speed_change(before: BallFrame, after: BallFrame, dt: float) -> float:
    """How much the ball's velocity changed beyond what gravity did, in uu/s."""
    return math.dist(
        (before.velocity.x, before.velocity.y, before.velocity.z - GRAVITY_UU_S2 * dt),
        (after.velocity.x, after.velocity.y, after.velocity.z),
    )


def is_rebound(before: BallFrame, after: BallFrame, dt: float) -> bool:
    """Check whether a velocity change fits the ball bouncing off a surface.

    A rebound reverses the speed into the surface, loses some of it, and adds
    nothing along the surface. A hit from a car rarely does all of that.
    """
    old = (before.velocity.x, before.velocity.y, before.velocity.z)
    new = (after.velocity.x, after.velocity.y, after.velocity.z)
    # Z is measured from mid height, so the floor and ceiling act like two walls.
    spot = (before.position.x, before.position.y, before.position.z - CEILING_Z / 2)
    extents = (SIDE_WALL_X, BACK_WALL_Y, CEILING_Z / 2)
    for axis, extent in enumerate(extents):
        if old[axis] * new[axis] >= 0 or abs(new[axis]) > abs(old[axis]):
            continue
        if old[axis] * spot[axis] <= 0:
            continue
        gap = extent - abs(spot[axis]) - BALL_RADIUS_UU
        if gap > abs(old[axis]) * dt + BOUNCE_GAP_SLOP:
            continue
        along_old = math.hypot(*(v for i, v in enumerate(old) if i != axis))
        along_new = math.hypot(*(v for i, v in enumerate(new) if i != axis))
        if along_new <= along_old + BOUNCE_SPEED_SLOP:
            return True
    return False
