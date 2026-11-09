"""Turn stored game reviews into training targets and highlights.

Targets rank the mistake categories by the goals they cost, then by how often
they came up. A frequent but harmless habit, such as a clear the opponent
collects in midfield, ranks below a rarer one that keeps ending in your net.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .analysis.mistakes import CATEGORIES, INSTEAD

# A category needs this many clean games in a row before it counts as a highlight
CLEAN_STREAK_MIN = 2
# Improvement worth pointing out: the latest session's rate per game against
# every earlier game in the period
IMPROVED_RATIO = 0.6
IMPROVED_MIN_DROP = 0.3
HIGHLIGHTS_PER_KIND = 2


@dataclass(frozen=True)
class FlagRow:
    kind: str
    category: str
    cost_goal: bool


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

    @property
    def conceded(self) -> int:
        return sum(1 for g in self.goals if not g.ours)

    @property
    def goals_on_me(self) -> int:
        return sum(1 for g in self.goals if not g.ours and g.on_me)


def _rate(flags: int, games: int) -> float | None:
    return round(flags / games, 2) if games else None


def summarize_categories(games: list[ReviewedGame]) -> list[dict[str, Any]]:
    """Count each category's flags, goals cost and trend across the games."""
    if not games:
        return []
    latest_date = max(g.play_date for g in games)
    latest = [g for g in games if g.play_date == latest_date]
    before = [g for g in games if g.play_date != latest_date]
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

        summaries.append(
            {
                "category": key,
                "label": label,
                "flags": len(flags),
                "goals_cost": sum(costly.values()),
                "games": len(games),
                "per_game": _rate(len(flags), len(games)),
                "latest_per_game": _rate(count(latest), len(latest)),
                "before_per_game": _rate(count(before), len(before)),
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
    """Rank categories by goals cost, then flags. Clean categories never rank."""
    ranked = sorted(
        (c for c in categories if c["flags"]),
        key=lambda c: (-c["goals_cost"], -c["flags"]),
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
        latest_rate = cat["latest_per_game"]
        before_rate = cat["before_per_game"]
        if (
            len(latest) >= 2
            and latest_rate is not None
            and before_rate is not None
            and latest_rate <= before_rate * IMPROVED_RATIO
            and before_rate - latest_rate >= IMPROVED_MIN_DROP
        ):
            add(
                "improving",
                f"{cat['label']} is improving",
                f"{before_rate:.1f} a game before, {latest_rate:.1f} in your "
                "latest session",
            )
    return highlights
