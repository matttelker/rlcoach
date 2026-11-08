"""Boost pickups: who took a pad, how much boost it gave, and whose half it was on.

Replays record each pickup as a pad event. A replay with no pad events, or with
fewer than half as many as its cars' boost rises, gets its pickups read from the
rises instead. Hoops is one: its pads aren't Soccar's, so its steals are guesses.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from ..field_constants import BOOST_PADS, BoostPad, Vec3
from ..parser.types import Frame
from .types import distance

BIG_PAD_BOOST = 100.0
SMALL_PAD_BOOST = 12.0
BIG_RESPAWN_S = 10.0
SMALL_RESPAWN_S = 4.0
RESPAWN_TOLERANCE_S = 0.15  # A pad's events can repeat just inside its respawn
MIDFIELD_UU = 100.0  # The halfway pads are on nobody's half
PAD_EVENT_COVERAGE = 0.5  # Share of the tanks' rises the pad events must show

# Reading pickups from the tanks
SMALLEST_RISE = 1.0
RESET_BOOST = 33.0  # What a car holds at each kickoff and respawn
RESET_TOLERANCE = 2.0
FAR_FROM_PADS_UU = 800.0  # A reset rise this far from every pad took no pad
RESPAWN_FILL_MAX = 35.0
RECENT_S = 0.45  # How far back to look for the pad a car drove over
# A steal needs the car this close to the pad. Generous, since cars cut corners
SMALL_REACH_UU = 730.0
BIG_REACH_UU = 1120.0


@dataclass(frozen=True)
class BoostPickupEvent:
    """One pad taken. `pad_id` indexes `BOOST_PADS`."""

    t: float
    player_id: str
    pad_id: int
    boost_gain: float
    stolen: bool = False  # The pad was on the other team's half


def detect_boost_pickups(frames: list[Frame]) -> list[BoostPickupEvent]:
    """Every pad taken, from the pad events when they're complete enough."""
    from_tanks = _from_tanks(frames)
    if any(frame.boost_pad_events for frame in frames):
        from_pads = _from_pad_events(frames)
        if from_pads and len(from_pads) >= len(from_tanks) * PAD_EVENT_COVERAGE:
            return from_pads
    return from_tanks


def is_stolen(pad: BoostPad, team: int | None) -> bool:
    """The pad is on the other team's half. Blue defends negative y."""
    if team == 0:
        return pad.position.y > MIDFIELD_UU
    if team == 1:
        return pad.position.y < -MIDFIELD_UU
    return False


def _capacity(pad: BoostPad) -> float:
    return BIG_PAD_BOOST if pad.is_big else SMALL_PAD_BOOST


def _pad_gain(
    pad: BoostPad, before: float | None, after: float | None
) -> tuple[float, float]:
    """The boost a pickup gave, and the tank after it.

    The tank shows it, unless the car was already full or the replay hasn't
    caught up yet. Then the pad gave what it holds, as far as the tank had room.
    """
    capacity = _capacity(pad)
    if before is None:
        before = 0.0 if after is None else max(0.0, after - capacity)
    if after is None:
        after = min(100.0, before + capacity)
    gain = max(0.0, after - before)
    if gain < 0.5:
        room = 100.0 - before
        gain = min(capacity, room) if room > 0.5 else 0.0
        after = min(100.0, before + gain)
    return gain, after


def _from_pad_events(frames: list[Frame]) -> list[BoostPickupEvent]:
    pickups = []
    tanks: dict[str, float] = {}  # Each car's boost after its last frame or pickup
    taken_at: dict[int, float] = {}
    for frame in frames:
        cars = {car.player_id: car for car in frame.players}
        for event in frame.boost_pad_events:
            if (
                event.status != "COLLECTED"
                or event.player_id is None
                or not 0 <= event.pad_id < len(BOOST_PADS)
            ):
                continue
            pad = BOOST_PADS[event.pad_id]
            t = frame.timestamp if event.timestamp is None else event.timestamp
            respawn = BIG_RESPAWN_S if pad.is_big else SMALL_RESPAWN_S
            last = taken_at.get(pad.pad_id)
            if last is not None and t - last < respawn - RESPAWN_TOLERANCE_S:
                continue  # The same pickup replicated again
            car = cars.get(event.player_id)
            gain, after = _pad_gain(
                pad,
                tanks.get(event.player_id),
                None if car is None else float(car.boost_amount),
            )
            team = event.player_team
            if team not in (0, 1):
                team = None if car is None else car.team
            pickups.append(
                BoostPickupEvent(
                    t=t,
                    player_id=event.player_id,
                    pad_id=pad.pad_id,
                    boost_gain=round(gain, 3),
                    stolen=is_stolen(pad, team),
                )
            )
            tanks[event.player_id] = after
            taken_at[pad.pad_id] = t
        for car in frame.players:
            tanks[car.player_id] = float(car.boost_amount)
    pickups.sort(key=lambda pickup: pickup.t)
    return pickups


@dataclass
class _Tank:
    boost: float
    recent: deque[tuple[float, Vec3]] = field(default_factory=deque)
    demolished: bool = False
    awaiting_respawn: bool = False  # Its next rise is the respawn's fill


def _nearest_pad(
    positions: list[Vec3], big: bool | None = None
) -> tuple[BoostPad, float]:
    """The pad a car passed closest to, and how close. `big` picks a pad size."""
    return min(
        (
            (pad, min(distance(position, pad.position) for position in positions))
            for pad in BOOST_PADS
            if big is None or pad.is_big == big
        ),
        key=lambda item: item[1],
    )


def _from_tanks(frames: list[Frame]) -> list[BoostPickupEvent]:
    """A pickup for each rise in a car's boost, except the resets.

    The pad is the one of its size the car passed closest to just before: a big
    pad for a rise more than a small one gives.
    """
    pickups = []
    tanks: dict[str, _Tank] = {}
    for frame in frames:
        now = frame.timestamp
        for car in frame.players:
            boost = float(car.boost_amount)
            tank = tanks.get(car.player_id)
            if tank is None:
                tank = tanks[car.player_id] = _Tank(boost)
            tank.recent.append((now, car.position))
            while now - tank.recent[0][0] > RECENT_S:
                tank.recent.popleft()
            if car.is_demolished:
                tank.demolished = tank.awaiting_respawn = True
            elif tank.demolished:
                tank.demolished = False
                tank.awaiting_respawn = True
            rise, tank.boost = boost - tank.boost, boost
            if abs(rise - RESET_BOOST) <= RESET_TOLERANCE:
                if _nearest_pad([car.position])[1] > FAR_FROM_PADS_UU:
                    continue  # A kickoff or respawn
            if tank.awaiting_respawn:
                if rise <= 0.0:
                    continue
                tank.awaiting_respawn = False
                if boost <= RESPAWN_FILL_MAX:
                    continue
            if rise < SMALLEST_RISE:
                continue
            pad, gap = _nearest_pad(
                [position for _, position in tank.recent],
                big=rise > SMALL_PAD_BOOST + SMALLEST_RISE,
            )
            reach = BIG_REACH_UU if pad.is_big else SMALL_REACH_UU
            pickups.append(
                BoostPickupEvent(
                    t=now,
                    player_id=car.player_id,
                    pad_id=pad.pad_id,
                    boost_gain=rise,
                    stolen=is_stolen(pad, car.team) and gap <= reach,
                )
            )
    return pickups
