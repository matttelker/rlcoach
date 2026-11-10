"""Kickoff coaching: how you play kickoffs, and the next thing to learn.

A coach takes kickoffs in steps. First flip into the ball every time you go,
then time that flip. Only then is the speedflip worth learning, the faster
kickoff higher ranks use. The ladder follows that order. Its targets are
judgment about when a step is solid, not benchmarks from other players.

Each step was checked against where the ball went on 41 games, 513 kickoffs by
either team (2026-11-09). With no flip the ball came back at the car's team 56%
of the time, against 28% with a flip on time. A late flip lost the ball no more
often (31%), but a goal against followed within 10 s 14% of the time, against
4%. "Only one of you goes" used to be a step. It isn't one at this rank: two
cars going lost the ball 17% of the time, one car 35%, so it's counted and
shown but not coached.

A kickoff is won or lost by where the ball was a second after the hit. In the
player's games the car there first got the first touch 91% of the time, but
it didn't change where the ball went, while the flip did.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .analysis.mistakes import GOAL_CONSEQUENCE_S, INSTEAD
from .coaching import SituationRow
from .events.kickoffs import (
    KickoffEvent,
    KickoffPlayer,
    flip_timing,
    kickoff_result,
    went_for_ball,
    went_with,
)

MIN_KICKOFFS = 5  # A step needs this many kickoffs to be judged
RACE_LEVEL_S = 0.02  # Closer than this, neither car got there first

# Measured on the six sample replays from much higher-ranked games: speedflips
# got within 1000 uu of the ball in 1.50 s from the diagonal, where standard
# kickoffs in the player's games took 1.66 to 1.68 s
SPEEDFLIP_GAIN_S = 0.17

SPEEDFLIP = (
    "A speedflip is a kickoff where you boost, flip diagonally and cancel the "
    "flip straight away, so the car flies nose first at the ball instead of "
    f"tumbling. It gets you there about {SPEEDFLIP_GAIN_S:.2f} s sooner than a "
    "standard kickoff."
)


@dataclass(frozen=True)
class GameKickoffs:
    """One reviewed game's kickoffs, with its goals as (time, ours)."""

    replay_id: str
    play_date: date
    my_id: str
    kickoffs: list[KickoffEvent]
    goals: list[tuple[float, bool]] = field(default_factory=list)


@dataclass(frozen=True)
class KickoffSeen:
    """One kickoff as you played it."""

    replay_id: str
    play_date: date
    t: float
    role: str
    spot: str | None
    approach: str
    flip: str | None  # ON_TIME, LATE or NONE when you went for the ball
    flip_lead: float | None
    result: str | None  # WON, EVEN or LOST for your team
    first_touch: str | None  # "you", "teammate" or "opponent"
    race_gap: float | None  # Seconds after the opposing GO car, below 0 sooner
    speed_at_contact: float | None
    boost_used: float
    double_commit: bool
    goal_after: str | None  # "for" or "against", within GOAL_CONSEQUENCE_S
    goal_after_s: float | None

    @property
    def going(self) -> bool:
        return self.role == "GO"


def _race_gap(kickoff: KickoffEvent, me: KickoffPlayer) -> float | None:
    """How much later you got near the ball than the opposing GO car.

    Only for a race: both went for the ball from the same kind of spawn.
    """
    if me.role != "GO" or not went_for_ball(me) or me.reach_time is None:
        return None
    rival = next(
        (p for p in kickoff.players if p.team != me.team and p.role == "GO"), None
    )
    if (
        rival is None
        or not went_for_ball(rival)
        or rival.spot != me.spot
        or rival.reach_time is None
    ):
        return None
    return round(me.reach_time - rival.reach_time, 3)


def _first_touch(kickoff: KickoffEvent, me: KickoffPlayer) -> str | None:
    toucher = kickoff.first_touch_player
    if toucher is None:
        return None
    if toucher == me.player_id:
        return "you"
    mate = next((p for p in kickoff.players if p.player_id == toucher), None)
    return "teammate" if mate is not None and mate.team == me.team else "opponent"


def read_kickoff(game: GameKickoffs, kickoff: KickoffEvent) -> KickoffSeen | None:
    """One kickoff from your seat, or None if you weren't in it."""
    me = next((p for p in kickoff.players if p.player_id == game.my_id), None)
    if me is None or me.team is None:
        return None
    contact = kickoff.t_start + (kickoff.time_to_first_touch or 0.0)
    goal = next(
        (
            (t, ours)
            for t, ours in sorted(game.goals)
            if contact <= t <= contact + GOAL_CONSEQUENCE_S
        ),
        None,
    )
    return KickoffSeen(
        replay_id=game.replay_id,
        play_date=game.play_date,
        t=kickoff.t_start,
        role=me.role,
        spot=me.spot,
        approach=me.approach,
        flip=flip_timing(me),
        flip_lead=me.flip_lead,
        result=kickoff_result(kickoff, me.team),
        first_touch=_first_touch(kickoff, me),
        race_gap=_race_gap(kickoff, me),
        speed_at_contact=me.speed_at_contact,
        boost_used=me.boost_used,
        double_commit=bool(went_with(kickoff, me)),
        goal_after=None if goal is None else ("for" if goal[1] else "against"),
        goal_after_s=None if goal is None else round(goal[0] - contact, 1),
    )


def kickoff_situations(game: GameKickoffs) -> list[SituationRow]:
    """Each kickoff a car went for as its team's GO car, as a situation: bad
    without a flip on time, and whether a goal against its team followed.

    Every car's, yours marked, so the cost of a late or missing flip is
    measured like any other habit's.
    """
    rows = []
    for kickoff in game.kickoffs:
        me = next((p for p in kickoff.players if p.player_id == game.my_id), None)
        if me is None or me.team is None:
            continue
        contact = kickoff.t_start + (kickoff.time_to_first_touch or 0.0)
        soon = [
            ours
            for t, ours in game.goals
            if contact <= t <= contact + GOAL_CONSEQUENCE_S
        ]
        for car in kickoff.players:
            timing = flip_timing(car)
            if car.role != "GO" or timing is None:
                continue
            with_me = car.team == me.team
            rows.append(
                SituationRow(
                    kind="kickoff",
                    zone="",
                    bad=timing != "ON_TIME",
                    conceded=any(ours != with_me for ours in soon),
                    mine=car.player_id == game.my_id,
                )
            )
    return rows


def _results(seen: list[KickoffSeen]) -> dict[str, int]:
    counts = Counter(k.result for k in seen if k.result)
    return {"won": counts["WON"], "even": counts["EVEN"], "lost": counts["LOST"]}


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole >= MIN_KICKOFFS else None


def _going_summary(going: list[KickoffSeen]) -> dict[str, Any]:
    went = [k for k in going if k.flip is not None]
    flips = Counter(k.flip for k in went)
    by_flip = []
    for timing in ("ON_TIME", "LATE", "NONE"):
        group = [k for k in went if k.flip == timing]
        by_flip.append({"flip": timing, "count": len(group), **_results(group)})
    races = [k.race_gap for k in going if k.race_gap is not None]
    speeds = [k.speed_at_contact for k in went if k.speed_at_contact is not None]
    return {
        "count": len(going),
        "went": len(went),
        "fakes": sum(1 for k in going if k.approach.startswith("FAKE")),
        "results": _results(going),
        "flips": {
            "on_time": flips["ON_TIME"],
            "late": flips["LATE"],
            "none": flips["NONE"],
        },
        "by_flip": by_flip,
        "speedflips": sum(1 for k in went if k.approach == "SPEEDFLIP"),
        "race": {
            "compared": len(races),
            "sooner": sum(1 for g in races if g < -RACE_LEVEL_S),
            "later": sum(1 for g in races if g > RACE_LEVEL_S),
            "median_gap": round(statistics.median(races), 3) if races else None,
        },
        "median_speed": round(statistics.median(speeds)) if speeds else None,
        "goals_for": sum(1 for k in going if k.goal_after == "for"),
        "goals_against": sum(1 for k in going if k.goal_after == "against"),
    }


def _support_summary(support: list[KickoffSeen]) -> dict[str, Any]:
    approaches = Counter(k.approach for k in support)
    return {
        "count": len(support),
        "results": _results(support),
        "double_commits": sum(1 for k in support if k.double_commit),
        "cheat": approaches["SUPPORT_CHEAT"],
        "hold": approaches["SUPPORT_HOLD"],
        "goals_for": sum(1 for k in support if k.goal_after == "for"),
        "goals_against": sum(1 for k in support if k.goal_after == "against"),
    }


def _lost_share(going: dict[str, Any], timing: str) -> str:
    """'9 of 20 (45%)': how often the ball came back at you with this flip."""
    group = next(g for g in going["by_flip"] if g["flip"] == timing)
    if not group["count"]:
        return "none of 0"
    share = round(100 * group["lost"] / group["count"])
    return f"{group['lost']} of {group['count']} ({share}%)"


def _ladder(going: dict[str, Any]) -> list[dict[str, Any]]:
    """The steps in order, each with your measure and whether it's solid."""
    went = going["went"]
    flips = going["flips"]
    race = going["race"]
    steps = [
        {
            "key": "flip_in",
            "title": "Flip into the ball every time",
            "level": "Gold to Platinum",
            "measure": "Kickoffs you went for with a flip into the ball",
            "count": flips["on_time"] + flips["late"],
            "of": went,
            "value": _share(flips["on_time"] + flips["late"], went),
            "target": 0.9,
            "why": (
                "Without a flip your bumper meets their flip. The ball came back "
                f"at you in {_lost_share(going, 'NONE')} kickoffs with no flip "
                f"into it, against {_lost_share(going, 'ON_TIME')} with one on "
                "time."
            ),
            "how": INSTEAD["kickoff_no_flip"],
        },
        {
            "key": "on_time",
            "title": "Flip on time",
            "level": "Platinum",
            "measure": "Kickoffs you went for with the flip on time",
            "count": flips["on_time"],
            "of": went,
            "value": _share(flips["on_time"], went),
            "target": 0.85,
            "why": (
                "A flip that starts as you reach the ball has no power left for "
                f"the hit. The ball came back at you in {_lost_share(going, 'LATE')}"
                " kickoffs when the flip came late."
            ),
            "how": INSTEAD["kickoff_late_flip"],
        },
        {
            "key": "speedflip",
            "title": "Learn the speedflip",
            "level": "Diamond to Champion",
            "measure": "Kickoffs you went for with a speedflip",
            "count": going["speedflips"],
            "of": went,
            "value": _share(going["speedflips"], went),
            "target": 0.5,
            "why": (
                f"{SPEEDFLIP} You got near the ball after the opposing car in "
                f"{race['later']} of {race['compared']} races and before it in "
                f"{race['sooner']}. Getting there first wins the first touch, "
                "but in your games it hasn't changed where the ball goes, so "
                "this pays off once your flip timing is solid."
            ),
            "how": (
                "Learn the motion in Free Play from a speedflip tutorial, then "
                "use it on kickoffs from each spawn, still flipping into the ball "
                "at the end."
            ),
        },
    ]
    focused = False
    for step in steps:
        if step["value"] is None:
            step["status"] = "unknown"
        elif step["value"] >= step["target"]:
            step["status"] = "solid"
        elif not focused:
            step["status"] = "focus"
            focused = True
        else:
            step["status"] = "later"
    return steps


def summarize_kickoffs(games: list[GameKickoffs]) -> dict[str, Any]:
    """Your kickoffs across the games: as GO, as support, by day, and the ladder."""
    seen = [
        k
        for game in games
        for kickoff in game.kickoffs
        if (k := read_kickoff(game, kickoff)) is not None
    ]
    going = [k for k in seen if k.going]
    support = [k for k in seen if not k.going]
    going_summary = _going_summary(going)
    double_commits = sum(1 for k in seen if k.double_commit)
    days = sorted({k.play_date for k in seen})
    return {
        "games": len(games),
        "count": len(seen),
        "double_commits": double_commits,
        "going": going_summary,
        "support": _support_summary(support),
        "sessions": [
            {
                "play_date": day.isoformat(),
                "went": sum(1 for k in going if k.play_date == day and k.flip),
                "on_time": sum(
                    1 for k in going if k.play_date == day and k.flip == "ON_TIME"
                ),
                "double_commits": sum(
                    1 for k in seen if k.play_date == day and k.double_commit
                ),
            }
            for day in days
        ],
        "ladder": _ladder(going_summary),
    }
