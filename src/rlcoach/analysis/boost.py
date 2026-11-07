"""Boost: how much each player picked up and stole, and how full they kept it.

These follow Ballchasing's definitions, which the parity test checks:
- Collected per minute divides by active play, which leaves out goal replays and
  3 s for each kickoff countdown.
- Average boost is the mean of the replicated updates, not a time average.
- A stretch at 0 or 100 counts once the next update ends it. One cut short by a
  goal replay, a demo or the end of the game counts for nothing, nor does one
  that ends during a kickoff countdown.
"""

from __future__ import annotations

from collections.abc import Mapping
from itertools import groupby, pairwise
from typing import Any

from ..events.kickoffs import is_held_for_kickoff
from ..events.types import BoostPickupEvent
from ..parser.types import Frame
from .tracks import PAUSE_GAP_S, Track

COUNTDOWN_S = 3.0  # Of each kickoff countdown, what Ballchasing leaves out
COUNTDOWN_MIN_S = 2.0  # Real countdowns hold for 3.1 s or more, other stops under 1


def active_play_seconds(frames: list[Frame], held: list[bool]) -> float:
    """The seconds Ballchasing's per-minute rates divide by.

    The recording's length, less every goal replay's pause and 3 s for each
    kickoff countdown. A countdown is a run of held frames lasting 2 s or more.
    """
    span = frames[-1].timestamp - frames[0].timestamp
    pauses = sum(
        gap
        for gap in (b.timestamp - a.timestamp for a, b in pairwise(frames))
        if gap > PAUSE_GAP_S
    )
    countdowns = 0
    for is_held, run in groupby(zip(frames, held, strict=True), key=lambda x: x[1]):
        stretch = [frame for frame, _ in run]
        if is_held and stretch[-1].timestamp - stretch[0].timestamp >= COUNTDOWN_MIN_S:
            countdowns += 1
    active = span - pauses - countdowns * COUNTDOWN_S
    return active if active > 0 else span


def _tank(frames: list[Frame], track: Track, held: list[bool]) -> dict[str, float]:
    """Average boost, and time spent at 0 and at 100."""
    total = 0.0
    updates = 0
    at_zero = at_full = 0.0
    stretch = 0.0
    cut_short = False
    previous: float | None = None
    previous_time: float | None = None
    for index, car in track:
        boost = car.boost_amount
        time = frames[index].timestamp
        cut_short = cut_short or car.is_demolished
        if previous_time is not None:
            gap = time - previous_time
            if gap > PAUSE_GAP_S:
                gap = 0.0
                cut_short = True
            stretch += gap
        if boost != previous:
            total += boost
            updates += 1
            if previous is not None and not cut_short and not held[index]:
                if previous <= 0.0:
                    at_zero += stretch
                if previous >= 100.0:
                    at_full += stretch
            stretch = 0.0
            cut_short = car.is_demolished
        previous = boost
        previous_time = time
    return {
        "avg_boost": round(total / updates, 2) if updates else 0.0,
        "time_zero_boost_s": round(at_zero, 2),
        "time_full_boost_s": round(at_full, 2),
    }


def boost_stats(
    frames: list[Frame],
    pickups: list[BoostPickupEvent],
    tracks: Mapping[str, Track],
) -> dict[str, dict[str, Any]]:
    """Each player's boost numbers."""
    held = [is_held_for_kickoff(frame) for frame in frames]
    minutes = max(active_play_seconds(frames, held) / 60.0, 1.0)
    result = {}
    for player_id, track in tracks.items():
        collected = stolen = 0.0
        for pickup in pickups:
            if pickup.player_id != player_id:
                continue
            collected += pickup.boost_gain
            if pickup.stolen:
                stolen += pickup.boost_gain
        result[player_id] = {
            "bcpm": round(collected / minutes, 2),
            "boost_collected": round(collected, 1),
            "boost_stolen": round(stolen, 1),
            **_tank(frames, track, held),
        }
    return result
