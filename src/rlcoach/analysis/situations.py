"""Situations: every time a car faced one of the choices the review judges, the
choice it made, and whether a goal against followed.

A flagged moment says what went wrong once. A situation says how often the
choice came up, so a habit has a rate ("out of position for 35 of 106 shots")
and a measured cost: how much more often a goal followed the bad choice than
the good one. They are found for every car in the game, not only yours, so your
rates can be set beside those of the players you meet, and the cost measured on
six times the games.

Each kind's `bad` choice was checked against outcomes on 41 games, 230 player
games, with intervals from resampling games (2026-11-09). A goal against
followed within 10 s, before the player's team touched the ball again:

| Kind | Bad choice | After bad | After good |
| --- | --- | --- | --- |
| shot_last_back | out of position | 43% of 79 | 28% of 509 |
| jump | missed the ball | 10% of 407 | 3% of 3,008 |
| last_back_challenge | lost the 50/50 | 15% of 105 | 5% of 128 |
| clear | given straight back | 5% of 194 | 2% of 907 |
| commit | went as the second car | 9% of 438 | 5% of 3,016 |
| opp_attack | caught upfield | 13% of 70 | 9% of 3,440 |

The first three hold up after allowing for where on the field they happened.
The last three don't reach that bar on goals, though a clear given back and
being caught upfield both leave the ball deep in your end far more often.

Two rules were dropped on the same evidence. A 50/50 on low boost was lost no
more often than any other (49% against 50%, at every boost level tried), and a
50/50 lost with a teammate behind cost nothing. Two cars going for a kickoff
lost the ball less often than one (17% against 35%).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..events.types import team_name
from . import mistakes as m

if TYPE_CHECKING:
    from ..game import Game

# Each kind of situation, and the mistake category it belongs to
KINDS = {
    "shot_last_back": "last_back",
    "last_back_challenge": "last_back",
    "jump": "whiffs",
    "clear": "clearing",
    "commit": "rotation",
    "opp_attack": "rotation",
}
# What each kind counts, and its bad choice, as the dashboard words them
WORDING = {
    "shot_last_back": ("shots at your goal with you last back", "out of position"),
    "last_back_challenge": ("50/50s as the last player back", "lost"),
    "jump": ("jumps and flips at the ball", "missed"),
    "clear": ("clears from your half", "given straight back"),
    "commit": ("runs at the ball", "with a teammate already going"),
    "opp_attack": ("opponent attacks in your half", "caught upfield"),
}
# The kinds whose bad choice is followed by more goals than chance allows: the
# interval from resampling games stays above zero. The rest are counted and
# shown, and cost nothing until the games show they do
PROVEN = frozenset({"shot_last_back", "last_back_challenge", "jump"})
SHOT_GAP_S = 4.0  # Touches this soon after a shot are the same attack
THIRD_DEPTH = m.CLEARED_DEPTH


@dataclass(frozen=True)
class Situation:
    """One choice a car faced. `bad` is the choice the review warns against."""

    kind: str  # One of KINDS
    player_id: str
    t: float
    seconds_left: float
    zone: str  # Where the ball was: "own_third", "own_half" or "their_half"
    bad: bool
    conceded: bool  # A goal against followed, as a flagged moment counts it


def _zone(depth: float) -> str:
    if depth > THIRD_DEPTH:
        return "own_third"
    return "own_half" if depth > 0 else "their_half"


def _conceded(ctx: m.Context, t: float) -> bool:
    mine = team_name(ctx.team)
    return any(
        goal.team != mine
        and t < goal.t <= t + m.GOAL_CONSEQUENCE_S
        and m._opponents_kept_it(ctx, t, goal.t)
        for goal in ctx.goals
    )


def _situation(
    ctx: m.Context, kind: str, index: int, bad: bool, settled: int | None = None
) -> Situation:
    """A situation at the frame `index`. What followed is judged from the frame
    `settled`, when the choice had played out: a jump's own touch on the ball
    mustn't count as your team winning it back afterwards."""
    t = ctx.times[index]
    after = t if settled is None else ctx.times[settled]
    return Situation(
        kind=kind,
        player_id=ctx.player_id,
        t=round(t, 2),
        seconds_left=round(m._seconds_left_at(ctx, index), 1),
        zone=_zone(ctx.depth(ctx.frames[index].ball.position.y)),
        bad=bad,
        conceded=_conceded(ctx, after),
    )


def _is_closing(ctx: m.Context, player_id: str, index: int) -> bool:
    frame = ctx.frames[index]
    car = frame.get_player_by_id(player_id)
    return (
        car is not None
        and not car.is_demolished
        and m._distance(car.position, frame.ball.position) <= m.DOUBLE_COMMIT_RANGE
        and m._closing_speed(car, frame.ball) >= m.DOUBLE_COMMIT_MIN_CLOSING
    )


def _longest_run(ctx: m.Context, start: int, end: int, holds) -> tuple[float, int]:
    """The longest unbroken time `holds` was true from `start` to `end`, and the
    frame it first held at."""
    run = best = 0.0
    first = start
    seen = False
    for index in range(start + 1, end + 1):
        if holds(index):
            run += ctx.times[index] - ctx.times[index - 1]
            if not seen:
                first, seen = index, True
        else:
            run = 0.0
        best = max(best, run)
    return best, first


def _commits(ctx: m.Context) -> Iterator[Situation]:
    """Each run at the ball that got there. Bad if a teammate who was nearer the
    ball was going for it too."""
    mates = m._teammate_ids(ctx)

    def going(index: int) -> bool:
        return m._past_kickoff(ctx, index) and _is_closing(ctx, ctx.player_id, index)

    for start, end in m._spells(ctx, going):
        if ctx.times[end] - ctx.times[start] < m.DOUBLE_COMMIT_MIN_S:
            continue
        last = ctx.frames[end]
        me = last.get_player_by_id(ctx.player_id)
        if m._distance(me.position, last.ball.position) > m.DOUBLE_COMMIT_END_RANGE:
            continue
        second = first = False
        for mate in mates:

            def mate_going(index: int, mate: str = mate) -> bool:
                return _is_closing(ctx, mate, index)

            together, since = _longest_run(ctx, start, end, mate_going)
            if together < m.DOUBLE_COMMIT_MIN_S:
                continue
            frame = ctx.frames[since]
            mine = m._distance(
                frame.get_player_by_id(ctx.player_id).position, frame.ball.position
            )
            theirs = m._distance(
                frame.get_player_by_id(mate).position, frame.ball.position
            )
            if mine > theirs:
                second = True
            else:
                first = True
        if first and not second:
            continue  # The teammate came in behind you: their choice, not yours
        yield _situation(ctx, "commit", start, second, settled=end)


def _opp_attacks(ctx: m.Context) -> Iterator[Situation]:
    """Each spell of 2 s or more with the opponents on the ball in your half. Bad
    if you spent 2 s of it upfield with too few teammates back."""
    allowed_back = max(ctx.team_size - 2, 0)

    def attack(index: int) -> bool:
        frame = ctx.frames[index]
        me = frame.get_player_by_id(ctx.player_id)
        if me is None or me.is_demolished or m._chasing_late(ctx, index):
            return False
        if ctx.depth(frame.ball.position.y) <= 0:
            return False
        last_touch = ctx.last_touch_team[index]
        return last_touch is not None and last_touch != ctx.team

    def caught(index: int) -> bool:
        frame = ctx.frames[index]
        me = frame.get_player_by_id(ctx.player_id)
        ball_depth = ctx.depth(frame.ball.position.y)
        if ctx.depth(me.position.y) >= -m.UPFIELD_DEPTH:
            return False
        if ctx.depth(me.velocity.y) >= m.RETURN_SPEED:
            return False
        back = sum(
            1
            for car in m._active_cars(frame)
            if car.team == ctx.team
            and car.player_id != ctx.player_id
            and ctx.depth(car.position.y) > ball_depth
        )
        return back <= allowed_back

    for start, end in m._spells(ctx, attack):
        if ctx.times[end] - ctx.times[start] < m.UPFIELD_MIN_S:
            continue
        upfield, _ = _longest_run(ctx, start, end, caught)
        yield _situation(ctx, "opp_attack", start, upfield >= m.UPFIELD_MIN_S)


def _shots_last_back(ctx: m.Context) -> Iterator[Situation]:
    """Each opponent touch that sent the ball at your goal while you were your
    team's last player back. Bad if the ball was already past you, or you were
    in their half.

    Not while your team chases a late goal, when the last player back should
    be up too.
    """
    last_shot = -m.math.inf
    for contact in ctx.contacts:
        index = contact.index
        if contact.team == ctx.team or not ctx.live[index]:
            continue
        frame = ctx.frames[index]
        if not m._past_kickoff(ctx, index):
            continue
        if not m._heading_into_goal(ctx, frame.ball):
            continue
        if contact.t - last_shot < SHOT_GAP_S:
            continue
        last_shot = contact.t
        if m._chasing_late(ctx, index):
            continue
        back = m.last_back_car(frame, ctx.team)
        if back is None or back.player_id != ctx.player_id:
            continue
        depth = ctx.depth(back.position.y)
        ball_depth = ctx.depth(frame.ball.position.y)
        out = depth < ball_depth or depth < -m.UPFIELD_DEPTH
        yield _situation(ctx, "shot_last_back", index, out)


def situations_for(ctx: m.Context) -> list[Situation]:
    """One player's situations in a game, in time order."""
    found = [
        *(_situation(ctx, "clear", c.index, back) for c, _, back in m.clears(ctx)),
        *(
            _situation(ctx, "jump", first, not hit, settled=nearest)
            for first, nearest, _, hit in m.jumps_at_ball(ctx)
        ),
        *(
            _situation(
                ctx,
                "last_back_challenge",
                index,
                lost,
                settled=ctx.index_at(challenge.t + m.CHALLENGE_SETTLE_S),
            )
            for index, challenge, lost in m.last_back_challenges(ctx)
        ),
        *_commits(ctx),
        *_opp_attacks(ctx),
        *_shots_last_back(ctx),
    ]
    return sorted(found, key=lambda s: (s.t, s.kind))


def game_situations(game: Game, names: dict[str, str]) -> list[Situation]:
    """Every car's situations in a game. A player the frames never show has none."""
    found: list[Situation] = []
    for player_id in names:
        try:
            ctx = m.build_context(
                game.frames,
                player_id=player_id,
                goals=game.goals,
                challenges=game.challenges,
                names=names,
                team_size=game.header.team_size,
                touches=game.touches,
            )
        except ValueError:
            continue
        found.extend(situations_for(ctx))
    return sorted(found, key=lambda s: (s.t, s.player_id, s.kind))
