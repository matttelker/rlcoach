"""Turn stored game reviews into training targets and highlights.

Targets rank the mistake categories by what they cost you in goals a game. For a
habit with situations (see `analysis.situations`) that is measured: how often
you made the bad choice, times how much more often a goal followed it than the
good choice, across every player in your games. A category with no situations
is ranked by half the goals the review put on it, which only counts the times it
went wrong.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .analysis.mistakes import CATEGORIES, INSTEAD
from .analysis.situations import KINDS, PROVEN, WORDING

# A category needs this many clean games in a row before it counts as a highlight
CLEAN_STREAK_MIN = 2
# A trend compares your last games with as many before them: 10 of each when
# you have them, and never fewer than 5, since a couple of games say nothing
TREND_GAMES = 10
TREND_MIN_GAMES = 5
# Improvement worth pointing out, in flags a game
IMPROVED_RATIO = 0.6
IMPROVED_MIN_DROP = 0.3
HIGHLIGHTS_PER_KIND = 2
# A cost is measured only from this many bad choices and as many good ones
MIN_POOL = 30
# A category with no situations is costed from the goals the review put on it.
# Not every one of those would have been stopped: on the measured habits, the
# extra goals came to about half of the goals that followed the bad choice
# (0.42 against 0.78 a game on 41 games), so the unmeasured ones count half
UNMEASURED_SHARE = 0.5

# The flagged kinds whose cost the situations measure. A goal the review put
# on any other kind is counted on top, at UNMEASURED_SHARE
MEASURED_KINDS = frozenset(
    {
        "last_back_upfield",
        "last_back_challenge",
        "whiff",
        "clear_given_back",
        "double_commit",
        "caught_upfield",
        "kickoff_no_flip",
        "kickoff_late_flip",
    }
)
# Going for a kickoff is a situation too, read from the stored kickoffs
SITUATION_CATEGORY = {**KINDS, "kickoff": "kickoffs"}
# Going without a flip on time is proven too: a goal against followed 10% of
# 166 such kickoffs and 4% of 342 with one (2026-11-09)
PROVEN_KINDS = PROVEN | {"kickoff"}
SITUATION_WORDING = {
    **WORDING,
    "kickoff": ("kickoffs you went for", "without a flip on time"),
}


@dataclass(frozen=True)
class FlagRow:
    kind: str
    category: str
    cost_goal: bool


@dataclass(frozen=True)
class SituationRow:
    """One choice a car faced: yours, or another player's in your games."""

    kind: str
    zone: str
    bad: bool
    conceded: bool
    mine: bool


@dataclass(frozen=True)
class GoalRow:
    clock: str
    ours: bool
    by_me: bool
    winner: bool
    equalizer: bool
    on_me: bool | None


@dataclass
class ReviewedGame:
    """One reviewed game, oldest first in every list this module takes."""

    replay_id: str
    play_date: date
    result: str | None
    my_score: int | None
    opponent_score: int | None
    map: str
    flags: list[FlagRow] = field(default_factory=list)
    goals: list[GoalRow] = field(default_factory=list)
    epic_saves: int = 0  # As the game counted them
    situations: list[SituationRow] = field(default_factory=list)  # Every car's

    @property
    def conceded(self) -> int:
        return sum(1 for g in self.goals if not g.ours)

    @property
    def goals_on_me(self) -> int:
        return sum(1 for g in self.goals if not g.ours and g.on_me)


def _rate(flags: int, games: int) -> float | None:
    return round(flags / games, 2) if games else None


def _share(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def extra_risk(rows: Iterable[SituationRow]) -> float | None:
    """How much more often a goal against followed the bad choice than the good
    one, as a share of the bad choices. None without enough of both.

    The two are compared where the ball was in the same part of the field, and
    the gaps averaged by where the bad choices happened, because any choice
    near your own net is followed by more goals.
    """
    by_zone: dict[str, tuple[list[bool], list[bool]]] = {}
    for row in rows:
        bad, good = by_zone.setdefault(row.zone, ([], []))
        (bad if row.bad else good).append(row.conceded)
    if (
        sum(len(bad) for bad, _ in by_zone.values()) < MIN_POOL
        or sum(len(good) for _, good in by_zone.values()) < MIN_POOL
    ):
        return None
    gap = weight = 0.0
    for bad, good in by_zone.values():
        if bad and good:
            gap += len(bad) * (sum(bad) / len(bad) - sum(good) / len(good))
            weight += len(bad)
    return round(gap / weight, 4) if weight else None


def measure_risks(rows: Iterable[SituationRow]) -> dict[str, float | None]:
    """Each kind of situation's extra risk, from every car's situations."""
    by_kind: dict[str, list[SituationRow]] = {}
    for row in rows:
        by_kind.setdefault(row.kind, []).append(row)
    return {kind: extra_risk(found) for kind, found in by_kind.items()}


def _situation_summaries(
    games: list[ReviewedGame], category: str, risks: Mapping[str, float | None]
) -> list[dict[str, Any]]:
    """Each of a category's situations: how often it came up for you, how often
    you made the bad choice, the same for the players you met, and its cost."""
    summaries = []
    for kind, owner in SITUATION_CATEGORY.items():
        if owner != category:
            continue
        rows = [s for g in games for s in g.situations if s.kind == kind]
        mine = [s for s in rows if s.mine]
        others = [s for s in rows if not s.mine]
        bad = sum(1 for s in mine if s.bad)
        risk = risks.get(kind)
        what, bad_label = SITUATION_WORDING[kind]
        summaries.append(
            {
                "kind": kind,
                "what": what,
                "bad_label": bad_label,
                "count": len(mine),
                "bad": bad,
                "bad_share": _share(bad, len(mine)),
                "others_bad_share": _share(
                    sum(1 for s in others if s.bad), len(others)
                ),
                "conceded_after_bad": sum(1 for s in mine if s.bad and s.conceded),
                "extra_risk": risk,
                # Whether the games have shown this choice costs goals. One that
                # hasn't been shown to costs nothing yet
                "proven": kind in PROVEN_KINDS,
                "goals_per_game": (
                    None
                    if risk is None
                    else (
                        round(bad / len(games) * max(risk, 0), 3)
                        if kind in PROVEN_KINDS
                        else 0.0
                    )
                ),
            }
        )
    return summaries


def _trend_split(
    games: list[ReviewedGame],
) -> tuple[list[ReviewedGame], list[ReviewedGame]]:
    """Your last games and as many before them, or nothing to compare."""
    size = min(TREND_GAMES, len(games) // 2)
    if size < TREND_MIN_GAMES:
        return [], []
    return games[-size:], games[-2 * size : -size]


def summarize_categories(
    games: list[ReviewedGame], risks: Mapping[str, float | None] | None = None
) -> list[dict[str, Any]]:
    """Count each category's flags, cost and trend across the games.

    `risks` is each situation's extra risk from `measure_risks`, measured on as
    many games as there are. Without it the games given measure it.
    """
    if not games:
        return []
    if risks is None:
        risks = measure_risks(s for g in games for s in g.situations)
    latest, before = _trend_split(games)
    dates = sorted({g.play_date for g in games})

    summaries = []
    for key, label in CATEGORIES.items():

        def count(subset: list[ReviewedGame], key: str = key) -> int:
            return sum(1 for g in subset for f in g.flags if f.category == key)

        flags = [f for g in games for f in g.flags if f.category == key]
        kinds = Counter(f.kind for f in flags)
        costly = Counter(f.kind for f in flags if f.cost_goal)
        top_kind = max(kinds, key=lambda k: (costly[k], kinds[k]), default=None)

        streak = 0
        for game in reversed(games):
            if any(f.category == key for f in game.flags):
                break
            streak += 1

        situations = _situation_summaries(games, key, risks)
        measured = [
            s["goals_per_game"] for s in situations if s["goals_per_game"] is not None
        ]
        goals_cost = sum(costly.values())
        summaries.append(
            {
                "category": key,
                "label": label,
                "flags": len(flags),
                "goals_cost": goals_cost,
                "games": len(games),
                "per_game": _rate(len(flags), len(games)),
                "recent_per_game": _rate(count(latest), len(latest)),
                "earlier_per_game": _rate(count(before), len(before)),
                "trend_games": len(latest),
                "situations": situations,
                # Goals a game this habit costs you: measured from its situations,
                # plus half the goals the review put on kinds they don't cover
                "cost_per_game": round(
                    sum(measured)
                    + sum(
                        goals
                        for kind, goals in costly.items()
                        if not measured or kind not in MEASURED_KINDS
                    )
                    / len(games)
                    * UNMEASURED_SHARE,
                    3,
                ),
                "cost_measured": bool(measured),
                "sessions": [
                    {
                        "play_date": day.isoformat(),
                        "games": sum(1 for g in games if g.play_date == day),
                        "flags": count([g for g in games if g.play_date == day]),
                    }
                    for day in dates
                ],
                "kinds": dict(kinds.most_common()),
                "top_kind": top_kind,
                "cue": INSTEAD[top_kind] if top_kind else None,
                "clean_streak": streak,
            }
        )
    return summaries


def pick_targets(
    categories: list[dict[str, Any]], limit: int = 3
) -> list[dict[str, Any]]:
    """Rank categories by what they cost you a game, then flags. A category
    that costs nothing and has no flags never ranks."""
    ranked = sorted(
        (c for c in categories if c["flags"] or c["cost_per_game"] > 0),
        key=lambda c: (-c["cost_per_game"], -c["goals_cost"], -c["flags"]),
    )
    return ranked[:limit]


def _score(game: ReviewedGame) -> str:
    return f"{game.my_score}–{game.opponent_score}"


def _pretty_map(name: str) -> str:
    return name.removesuffix("_P").replace("_", " ")


def find_highlights(
    games: list[ReviewedGame], categories: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Pick out what went well, newest session first."""
    if not games:
        return []
    latest_date = max(g.play_date for g in games)
    latest = [g for g in games if g.play_date == latest_date]
    highlights: list[dict[str, Any]] = []
    recent_games = len(_trend_split(games)[0])

    def add(kind: str, title: str, detail: str, replay_id: str | None = None):
        if sum(1 for h in highlights if h["kind"] == kind) < HIGHLIGHTS_PER_KIND:
            highlights.append(
                {"kind": kind, "title": title, "detail": detail, "replay_id": replay_id}
            )

    for game in reversed(latest):
        where = f"{_score(game)} on {_pretty_map(game.map)}"
        for goal in game.goals:
            if goal.by_me and goal.winner:
                add(
                    "winner",
                    "Scored the winner",
                    f"{where}, with {goal.clock} left",
                    game.replay_id,
                )
            elif goal.by_me and goal.equalizer:
                add(
                    "equalizer",
                    "Tied it up",
                    f"{where}, with {goal.clock} left",
                    game.replay_id,
                )

    for game in reversed(latest):
        if game.epic_saves:
            add(
                "epic_save",
                (
                    "Epic save"
                    if game.epic_saves == 1
                    else f"{game.epic_saves} epic saves"
                ),
                f"In the {_score(game)} on {_pretty_map(game.map)}",
                game.replay_id,
            )

    for game in reversed(latest):
        if game.conceded and not game.goals_on_me:
            add(
                "clean",
                "No goals on you",
                f"{game.conceded} conceded in the {_score(game)} on "
                f"{_pretty_map(game.map)}, none on you",
                game.replay_id,
            )
        elif not game.conceded and game.result == "WIN":
            add(
                "clean",
                "Clean sheet",
                f"{_score(game)} on {_pretty_map(game.map)}",
                game.replay_id,
            )

    for cat in categories:
        earlier_flags = cat["flags"]
        if cat["clean_streak"] >= CLEAN_STREAK_MIN and earlier_flags:
            add(
                "streak",
                f"Clean on {cat['label'].lower()}",
                f"No {cat['label'].lower()} mistakes in your last "
                f"{cat['clean_streak']} games",
            )
            continue
        latest_rate = cat["recent_per_game"]
        before_rate = cat["earlier_per_game"]
        if (
            latest_rate is not None
            and before_rate is not None
            and latest_rate <= before_rate * IMPROVED_RATIO
            and before_rate - latest_rate >= IMPROVED_MIN_DROP
        ):
            add(
                "improving",
                f"{cat['label']} is improving",
                f"{latest_rate:.1f} a game over your last {recent_games} games, "
                f"{before_rate:.1f} over the {recent_games} before",
            )
    return highlights
