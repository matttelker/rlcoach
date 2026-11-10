"""Per-moment mistake detection.

The other analyzers describe a whole game. This one lists the moments that cost
one player: what happened, when, and what to do instead.

It works from the game's own touches (see `events.touches`) and from frames.
"""

from __future__ import annotations

import math
from bisect import bisect_left
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import asdict, dataclass, field, replace
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..events.kickoffs import (
    KickoffEvent,
    KickoffPlayer,
    flip_timing,
    kickoff_result,
    went_for_ball,
)
from ..events.touches import detect_touches
from ..events.types import (
    ChallengeEvent,
    DemoEvent,
    GoalEvent,
    TouchEvent,
    team_name,
)
from ..field_constants import (
    BACK_WALL_Y,
    GOAL_HEIGHT,
    GOAL_WIDTH,
)
from ..game import Game, read_game
from ..identity import build_player_identities
from ..modes import mode_of
from ..parser.types import BallFrame, Frame, PlayerFrame

if TYPE_CHECKING:
    from .situations import Situation

GOAL_LINE_Y = BACK_WALL_Y

GAME_LENGTH_S = 300.0
MAX_FRAME_GAP_S = 0.5  # Longer gaps are goal replays, and they end any episode
KICKOFF_GRACE_S = 3.0  # Everyone converges on a kickoff, so skip this window

DANGER_DEPTH = 3500.0  # Ball this deep in your half threatens the net
DANGER_WINDOW_S = 5.0
GOAL_CONSEQUENCE_S = 10.0
MOMENT_TOUCH_S = 0.5  # A flagged moment's own touch, such as the clear or the 50/50

DOUBLE_COMMIT_RANGE = 1200.0
DOUBLE_COMMIT_MIN_CLOSING = 500.0
DOUBLE_COMMIT_MIN_S = 0.4
DOUBLE_COMMIT_END_RANGE = 500.0
DOUBLE_COMMIT_FOLLOW_UP_S = 2.0

UPFIELD_DEPTH = 500.0  # Past this point in the opponent's half
UPFIELD_MIN_S = 2.0
RETURN_SPEED = 1000.0  # Driving home this fast is already the right response
# Behind with this little time left, the whole team should push for a goal.
# Being caught upfield is then the price of the right play, not a mistake. It
# also covers the clock reading 0:00 while the ball stays in the air.
CHASE_WINDOW_S = 30.0

CHALLENGE_SETTLE_S = 0.5  # When the ball's direction shows who won a 50/50
CLEAR_MIN_SPEED = 500.0  # Speed upfield that makes a touch a clear
CLEAR_MIN_FLIGHT_S = 0.6  # A quicker reply from an opponent is a 50/50
CLEAR_RETURN_WINDOW_S = 3.0
CLEARED_DEPTH = 1700.0  # Out of your third is a job done, whoever collects it

GOAL_LOOKBACK_S = 15.0
GOAL_DECISION_S = 4.0  # A long shot covers the field in about this time
GOAL_REVIEW_WINDOW_S = 2.0
GOAL_CHANCES = (
    "own_touch_in",
    "no_save_attempt",
    "missed_clear",
    "missed_save",
    "behind_line",
)
BEHIND_LINE_MARGIN = 200.0  # A keeper on the line is fine, so ask for a clear gap
HEADING_MIN_SPEED = 100.0  # Slower than this towards goal is not going in yet
# Height gain that proves a car left the ground, for replays that don't say when
# cars jump. Driving up a wall gains height too
JUMP_RISE = 60.0
# A jump that starts later than this before the ball goes in can't save it. A car
# has risen about 60 uu by then
JUMP_LEAD_S = 0.2
# A jump or flip this long before the goal review's window still has the car in
# the air during it. A flip lasts about 0.7 s
JUMP_LOOKBACK_S = 1.0
SAVE_REACH = 350.0  # Horizontal distance a jump can cover at the goal line
SAVE_TRAVEL = 700.0  # Extra reach for each second of warning
SAVE_REACH_MAX = 900.0
SAVE_REACTION_S = 1.0  # Nobody can answer a late deflection
IN_GOAL_DEPTH = 600.0
IN_GOAL_MARGIN = 300.0
OVERCOMMIT_SPEED = 800.0  # Leaving the net this fast is a commitment
MISS_RANGE = 400.0  # Closer than this in the last seconds counts as a chance
SLOW_BALL_SPEED = 1000.0
UU_S_TO_KPH = 0.036

# A whiff: you jumped or flipped at the ball, got within reach of it, and nobody
# touched it. Of the jumps and flips on your games that came this near the ball,
# 86% touched it
WHIFF_REACH = 300.0
WHIFF_MIN_CLOSING = 500.0  # Driving at the ball this fast as you leave the ground
WHIFF_SAME_GO_S = 1.5  # A flip or double jump this soon after a jump is the same go
WHIFF_WINDOW_S = 1.2  # After the go's last jump or flip
TOUCH_SLOP_S = 0.05  # The game can place a touch a frame early

INSTEAD = {
    "double_commit": (
        "Leave it to the closer teammate. Peel to the back post or grab boost, "
        "so you are ready for the next touch."
    ),
    "caught_upfield": (
        "Turn back as soon as the ball passes you. Drive to your back post and "
        "take boost on the way."
    ),
    # On your games a clear up the middle came back less often than one to the
    # side, because it travels further. What matters is that it leaves your third
    "clear_given_back": (
        "A clear isn't done until it's out of your third. Hit it hard enough to "
        "reach halfway, or take a touch and carry it out, instead of a soft "
        "hit to the next opponent."
    ),
    "own_touch_in": (
        "Near your net, don't hit the ball while you face your own goal. Go "
        "around so you are between the ball and your net before you touch it."
    ),
    "no_save_attempt": (
        "Jump for any ball you can reach on the line, even if it looks high. "
        "A late jump beats watching it go in."
    ),
    "missed_clear": (
        "A slow ball by your net needs a calm touch. Slow down, line it up, and "
        "hit it firmly away from your net before anyone else arrives."
    ),
    "missed_save": (
        "Get to the line early and square up to the shooter, so you only need a "
        "small move to meet the ball."
    ),
    "behind_line": (
        "Stop at the line and face the ball. Don't reverse into your net: turn "
        "and drive forward, or powerslide around, so you can still reach it."
    ),
    "last_back_upfield": (
        "As the last player back, keep the ball in front of you. Go no further "
        "than halfway, and only when your team has the ball deep in their end. "
        "When it comes loose, drop toward your back post before it gets past you."
    ),
    # Losing a 50/50 with a teammate behind you cost nothing on your games.
    # Losing one as the last player back was followed by a goal 15% of the
    # time, against 5% for one won
    "last_back_challenge": (
        "As the last player back, don't dive into a 50/50 you can lose. Stay "
        "between the ball and your net, give ground, and challenge once a "
        "teammate is back behind you or the ball is yours to win."
    ),
    "last_back_overcommit": (
        "When teammates are already challenging, stay in goal. Be the save "
        "behind them, not one more car going for the same ball."
    ),
    # Flips into the ball that won the kickoff began about 0.1 s before it was
    # played, which at kickoff speed is about two car lengths out
    "kickoff_no_flip": (
        "On a kickoff you go for, boost all the way in and flip into the ball "
        "when you're about two car lengths from it, so your flip hits the ball, "
        "not your bumper."
    ),
    "kickoff_late_flip": (
        "Start your flip a moment sooner, about two car lengths from the ball. "
        "A flip that starts as you reach the ball puts no power into the hit."
    ),
    "whiff": (
        "Line it up before you leave the ground. Get to where the ball is going, "
        "then jump or flip when it's in reach, not on the way to it. If you can't "
        "get there cleanly, don't go: shadow it and wait for a better touch."
    ),
}

# Each kind belongs to one habit to train. The dashboard groups by these.
CATEGORIES = {
    "last_back": "Last back",
    "rotation": "Rotation",
    "clearing": "Clearing",
    "goalkeeping": "Goalkeeping",
    "kickoffs": "Kickoffs",
    "whiffs": "Whiffs",
}
CATEGORY = {
    "last_back_upfield": "last_back",
    "last_back_overcommit": "last_back",
    "caught_upfield": "rotation",
    "double_commit": "rotation",
    "clear_given_back": "clearing",
    "missed_clear": "clearing",
    "own_touch_in": "clearing",
    "missed_save": "goalkeeping",
    "no_save_attempt": "goalkeeping",
    "behind_line": "goalkeeping",
    "last_back_challenge": "last_back",
    "kickoff_no_flip": "kickoffs",
    "kickoff_late_flip": "kickoffs",
    "whiff": "whiffs",
}
SPOT_NAMES = {
    "DIAGONAL": "the diagonal",
    "OFF_CENTRE": "off-centre",
    "BACK": "the back",
}


class UnsupportedReplayError(ValueError):
    """Raised for modes whose arena or rules break the detector's assumptions."""


@dataclass(frozen=True)
class Contact:
    """A touch the game counted, at the frame `index`."""

    t: float
    index: int
    player_id: str
    team: int


@dataclass(frozen=True)
class Mistake:
    """One flagged moment for the reviewed player."""

    kind: str
    t: float
    frame: int
    clock: str
    score: str
    duration: float
    what: str
    instead: str
    outcome: str = ""
    category: str = ""
    seconds_left: float = 0.0
    cost_goal: bool = False  # This moment led to a goal against


@dataclass(frozen=True)
class GoalReview:
    """Who was where when a goal went in."""

    t: float
    clock: str
    score: str
    scorer: str
    on_you: bool
    summary: str
    lines: tuple[str, ...]
    seconds_left: float = 0.0


@dataclass(frozen=True)
class GoalMoment:
    """One goal by either team, placed on the game clock."""

    t: float
    clock: str
    seconds_left: float
    score: str  # Before the goal, your team first
    ours: bool
    scorer: str
    by_you: bool
    assist_by_you: bool
    winner: bool  # Gave your team the lead it kept
    equalizer: bool


@dataclass(frozen=True)
class KickoffMoment:
    """One kickoff placed on the game clock, with how every car played it."""

    t: float  # When the cars were released
    clock: str
    seconds_left: float
    score: str  # Before the kickoff, your team first
    kickoff: KickoffEvent


@dataclass(frozen=True)
class TouchMoment:
    """One touch by any car, on the game clock."""

    seconds_left: float
    touch: TouchEvent


@dataclass(frozen=True)
class ChallengeMoment:
    """One 50/50 on the game clock, and whether each of its two players was their
    team's last back then (None for a car that wasn't on the field)."""

    seconds_left: float
    challenge: ChallengeEvent
    first_last_back: bool | None
    second_last_back: bool | None


@dataclass(frozen=True)
class DemoMoment:
    """One demo on the game clock."""

    seconds_left: float
    demo: DemoEvent


@dataclass(frozen=True)
class DefenderRole:
    """What one defender did about a goal."""

    label: str
    text: str
    index: int
    gap: float = 0.0
    ball_speed: float = 0.0
    late_jump: bool = False  # Jumped only as the ball went in


@dataclass
class Context:
    """Everything the detectors share for one player in one replay."""

    frames: Sequence[Frame]
    player_id: str
    team: int
    team_size: int
    names: dict[str, str]
    goals: list[GoalEvent]
    challenges: list[ChallengeEvent]
    contacts: list[Contact]
    live: list[bool]
    clock: list[float]
    times: list[float] = field(default_factory=list)
    last_touch_team: list[int | None] = field(default_factory=list)
    kickoff_start: list[float] = field(default_factory=list)
    reports_jumps: bool = False  # The replay says when each car jumps and flips

    def name(self, player_id: str | None) -> str:
        if player_id == self.player_id:
            return "You"
        if player_id is None:
            return "Unknown"
        return self.names.get(player_id, player_id)

    def depth(self, y: float) -> float:
        return own_depth(y, self.team)

    def index_at(self, t: float) -> int:
        return min(bisect_left(self.times, t), len(self.times) - 1)


@dataclass
class MistakeReport:
    """Full review of one player in one replay."""

    player: str
    team: str
    map_name: str
    final_score: str
    goals: list[GoalReview]
    mistakes: list[Mistake]
    clears: dict[str, int]
    player_id: str = ""
    goal_timeline: list[GoalMoment] = field(default_factory=list)
    kickoffs: list[KickoffMoment] = field(default_factory=list)
    # The game's events, every car's, which the database keeps with the review
    touches: list[TouchMoment] = field(default_factory=list)
    challenges: list[ChallengeMoment] = field(default_factory=list)
    demos: list[DemoMoment] = field(default_factory=list)
    # Every car's situations (see analysis.situations)
    situations: list[Situation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """The review, without the game's events."""
        events = ("touches", "challenges", "demos", "situations")
        trimmed = asdict(replace(self, **{name: [] for name in events}))
        return {key: value for key, value in trimmed.items() if key not in events}


def own_depth(y: float, team: int) -> float:
    """Distance towards a team's own goal: positive in their half.

    Orange (team 1) defends +Y and blue (team 0) defends -Y.
    """
    return y if team == 1 else -y


def check_supported_map(map_name: str | None) -> None:
    """Refuse arenas where goal positions and rotation rules don't apply."""
    if not mode_of(map_name).reviewed:
        raise UnsupportedReplayError(
            f"{map_name} is not a standard arena, so the mistake rules don't apply."
        )


def _distance(a: Any, b: Any) -> float:
    return math.dist((a.x, a.y, a.z), (b.x, b.y, b.z))


def _flat_distance(a: Any, b: Any) -> float:
    return math.dist((a.x, a.y), (b.x, b.y))


def _active_cars(frame: Frame) -> list[PlayerFrame]:
    return [p for p in frame.players if not p.is_demolished]


def _ball_is_parked(ball: BallFrame) -> bool:
    velocity = ball.velocity
    return (
        abs(ball.position.x) < 10.0
        and abs(ball.position.y) < 10.0
        and math.hypot(velocity.x, velocity.y) < 10.0
    )


def live_mask(frames: Sequence[Frame], goal_times: Iterable[float]) -> list[bool]:
    """Mark frames in open play: after a kickoff starts, before the next goal."""
    goals = sorted(goal_times)
    next_goal = 0
    in_play = False
    parked = False
    mask: list[bool] = []
    for frame in frames:
        while next_goal < len(goals) and frame.timestamp >= goals[next_goal]:
            in_play = False
            parked = False
            next_goal += 1
        if not in_play:
            if _ball_is_parked(frame.ball):
                parked = True
            elif parked:
                in_play = True
        mask.append(in_play)
    return mask


def game_clock(frames: Sequence[Frame], live: Sequence[bool]) -> list[float]:
    """Estimate seconds left at each frame. Overtime goes negative."""
    elapsed = 0.0
    clock: list[float] = []
    previous: float | None = None
    for frame, is_live in zip(frames, live, strict=False):
        if is_live and previous is not None:
            dt = frame.timestamp - previous
            if 0 < dt <= MAX_FRAME_GAP_S:
                elapsed += dt
        previous = frame.timestamp
        clock.append(GAME_LENGTH_S - elapsed)
    return clock


def format_clock(seconds_left: float) -> str:
    """Show a clock reading the way the game does, with + for overtime."""
    prefix = "+" if seconds_left < 0 else ""
    total = int(round(abs(seconds_left)))
    return f"{prefix}{total // 60}:{total % 60:02d}"


def _last_touch_by_frame(
    frames: Sequence[Frame], contacts: Sequence[Contact], live: Sequence[bool]
) -> list[int | None]:
    """The team that touched the ball last at each frame, or None while it's dead
    and until a kickoff's first touch. The ball says, on any replay that has it."""
    if any(frame.hit_team is not None for frame in frames):
        return [
            frame.hit_team if is_live else None
            for frame, is_live in zip(frames, live, strict=True)
        ]
    result: list[int | None] = []
    position = 0
    team: int | None = None
    for index in range(len(frames)):
        if not live[index]:
            team = None
        while position < len(contacts) and contacts[position].index <= index:
            if live[contacts[position].index]:
                team = contacts[position].team
            position += 1
        result.append(team)
    return result


def _kickoff_starts(live: Sequence[bool], frames: Sequence[Frame]) -> list[float]:
    starts: list[float] = []
    current = 0.0
    previous = False
    for frame, is_live in zip(frames, live, strict=False):
        if is_live and not previous:
            current = frame.timestamp
        starts.append(current)
        previous = is_live
    return starts


def build_context(
    frames: Sequence[Frame],
    player_id: str,
    goals: list[GoalEvent],
    challenges: list[ChallengeEvent],
    names: dict[str, str],
    team_size: int | None = None,
    touches: Sequence[TouchEvent] | None = None,
) -> Context:
    """Prepare the shared timeline for one reviewed player. `touches` are the
    game's (see `events.touches`), found from the frames if not given."""
    team = next(
        (p.team for frame in frames for p in frame.players if p.player_id == player_id),
        None,
    )
    if team is None:
        raise ValueError(f"{player_id} does not appear in this replay")
    if team_size is None:
        team_size = sum(1 for p in frames[0].players if p.team == team)
    live = live_mask(frames, [g.t for g in goals])
    if touches is None:
        touches = detect_touches(frames)
    contacts = [
        Contact(touch.t, touch.frame, touch.player_id, touch.team)
        for touch in touches
        if touch.team is not None
    ]
    return Context(
        frames=frames,
        player_id=player_id,
        team=team,
        team_size=team_size,
        names=names,
        goals=goals,
        challenges=challenges,
        contacts=contacts,
        live=live,
        clock=game_clock(frames, live),
        times=[f.timestamp for f in frames],
        last_touch_team=_last_touch_by_frame(frames, contacts, live),
        kickoff_start=_kickoff_starts(live, frames),
        reports_jumps=any(_left_the_ground(p) for f in frames for p in f.players),
    )


def _tally(ctx: Context, t: float) -> tuple[int, int]:
    mine = team_name(ctx.team)
    ours = sum(1 for g in ctx.goals if g.t < t and g.team == mine)
    theirs = sum(1 for g in ctx.goals if g.t < t and g.team != mine)
    return ours, theirs


def _score_at(ctx: Context, t: float) -> str:
    ours, theirs = _tally(ctx, t)
    return f"{ours}-{theirs}"


def _seconds_left_at(ctx: Context, index: int) -> float:
    """Read the clock at a frame. Only a tied game runs past zero.

    In any other game the clock sits at 0:00 until the ball next touches the
    floor, so those extra seconds are not overtime.
    """
    ours, theirs = _tally(ctx, ctx.times[index])
    seconds = ctx.clock[index]
    return seconds if ours == theirs else max(seconds, 0.0)


def _clock_at(ctx: Context, index: int) -> str:
    return format_clock(_seconds_left_at(ctx, index))


def _chasing_late(ctx: Context, index: int) -> bool:
    """Check your team is behind with little regulation time left.

    A tied overtime has no "behind", so it never counts.
    """
    ours, theirs = _tally(ctx, ctx.times[index])
    return ours < theirs and _seconds_left_at(ctx, index) <= CHASE_WINDOW_S


def _conceded(delay: float) -> str:
    if delay < 1.0:
        return "You conceded right after."
    return f"You conceded {delay:.0f} s later."


def _opponents_kept_it(ctx: Context, t: float, goal_t: float) -> bool:
    """Check your team never touched the ball between a moment and a goal."""
    return not any(
        c.team == ctx.team and t + MOMENT_TOUCH_S < c.t <= goal_t for c in ctx.contacts
    )


def _outcome_after(ctx: Context, t: float, *, cost_goal: bool = False) -> str:
    """Describe what the moment led to, so the worst ones can be ranked first.

    A goal only follows from the moment if your team never got the ball back
    before it went in, unless the goal review already blamed this moment.
    """
    mine = team_name(ctx.team)
    for goal in ctx.goals:
        if goal.team != mine and t <= goal.t <= t + GOAL_CONSEQUENCE_S:
            if cost_goal or _opponents_kept_it(ctx, t, goal.t):
                return _conceded(goal.t - t)
            break
    start = ctx.index_at(t)
    end = ctx.index_at(t + DANGER_WINDOW_S)
    for index in range(start, end + 1):
        if ctx.live[index] and ctx.depth(ctx.frames[index].ball.position.y) > (
            DANGER_DEPTH
        ):
            return "The ball reached your end."
    return ""


def _flag(
    ctx: Context,
    kind: str,
    index: int,
    duration: float,
    what: str,
    *,
    cost_goal: bool = False,
) -> Mistake:
    t = ctx.times[index]
    return Mistake(
        kind=kind,
        t=round(t, 2),
        frame=index,
        clock=_clock_at(ctx, index),
        score=_score_at(ctx, t),
        duration=round(duration, 1),
        what=what,
        instead=INSTEAD[kind],
        outcome=_outcome_after(ctx, t, cost_goal=cost_goal),
        category=CATEGORY[kind],
        seconds_left=round(_seconds_left_at(ctx, index), 1),
        cost_goal=cost_goal,
    )


def _past_kickoff(ctx: Context, index: int) -> bool:
    return ctx.times[index] - ctx.kickoff_start[index] >= KICKOFF_GRACE_S


def _closing_speed(car: PlayerFrame, ball: BallFrame) -> float:
    dx = ball.position.x - car.position.x
    dy = ball.position.y - car.position.y
    dz = ball.position.z - car.position.z
    length = math.sqrt(dx * dx + dy * dy + dz * dz) or 1.0
    return (car.velocity.x * dx + car.velocity.y * dy + car.velocity.z * dz) / length


def _spells(ctx: Context, holds: Any) -> list[tuple[int, int]]:
    """Find unbroken runs of frames where `holds(index)` is true."""
    spells: list[tuple[int, int]] = []
    start: int | None = None
    previous: int | None = None
    for index in range(len(ctx.frames)):
        ok = ctx.live[index] and holds(index)
        if (
            ok
            and start is not None
            and ctx.times[index] - ctx.times[index - 1] > MAX_FRAME_GAP_S
        ):
            spells.append((start, previous))
            start = None
        if ok:
            start = index if start is None else start
            previous = index
        elif start is not None:
            spells.append((start, previous))
            start = None
    if start is not None:
        spells.append((start, previous))
    return spells


def _teammate_ids(ctx: Context) -> list[str]:
    seen: dict[str, None] = {}
    for frame in ctx.frames:
        for car in frame.players:
            if car.team == ctx.team and car.player_id != ctx.player_id:
                seen[car.player_id] = None
    return list(seen)


def _next_contact_after(ctx: Context, t: float) -> Contact | None:
    for contact in ctx.contacts:
        if contact.t > t:
            return contact
    return None


def _both_closing(ctx: Context, mate_id: str, index: int) -> bool:
    frame = ctx.frames[index]
    me = frame.get_player_by_id(ctx.player_id)
    mate = frame.get_player_by_id(mate_id)
    if me is None or mate is None or me.is_demolished or mate.is_demolished:
        return False
    if not _past_kickoff(ctx, index):
        return False
    for car in (me, mate):
        if _distance(car.position, frame.ball.position) > DOUBLE_COMMIT_RANGE:
            return False
        if _closing_speed(car, frame.ball) < DOUBLE_COMMIT_MIN_CLOSING:
            return False
    return True


def detect_double_commits(ctx: Context) -> list[Mistake]:
    """Flag going for a ball a closer teammate is already taking.

    Only the later arrival is flagged, and only when an opponent got the ball.
    """
    flags: list[Mistake] = []
    for mate_id in _teammate_ids(ctx):
        for start, end in _spells(ctx, partial(_both_closing, ctx, mate_id)):
            duration = ctx.times[end] - ctx.times[start]
            if duration < DOUBLE_COMMIT_MIN_S:
                continue
            first = ctx.frames[start]
            last = ctx.frames[end]
            ball_start = first.ball.position
            me_start = first.get_player_by_id(ctx.player_id)
            mate_start = first.get_player_by_id(mate_id)
            if _distance(me_start.position, ball_start) <= _distance(
                mate_start.position, ball_start
            ):
                continue
            me_end = last.get_player_by_id(ctx.player_id)
            mate_end = last.get_player_by_id(mate_id)
            if (
                max(
                    _distance(me_end.position, last.ball.position),
                    _distance(mate_end.position, last.ball.position),
                )
                > DOUBLE_COMMIT_END_RANGE
            ):
                continue
            contact = _next_contact_after(ctx, ctx.times[start])
            if (
                contact is None
                or contact.team == ctx.team
                or contact.t > ctx.times[end] + DOUBLE_COMMIT_FOLLOW_UP_S
            ):
                continue
            flags.append(
                _flag(
                    ctx,
                    "double_commit",
                    start,
                    duration,
                    f"You and {ctx.name(mate_id)} both drove at the ball. They were "
                    f"closer, and {ctx.name(contact.player_id)} took it from you both.",
                )
            )
    return sorted(flags, key=lambda m: m.t)


def detect_caught_upfield(ctx: Context) -> list[Mistake]:
    """Flag staying in the opponent's half while they attack an undefended net.

    Not while your team chases a late goal, when everyone should be up.
    """
    allowed_back = max(ctx.team_size - 2, 0)

    def caught(index: int) -> bool:
        frame = ctx.frames[index]
        me = frame.get_player_by_id(ctx.player_id)
        if me is None or me.is_demolished or _chasing_late(ctx, index):
            return False
        ball_depth = ctx.depth(frame.ball.position.y)
        if ball_depth <= 0 or ctx.depth(me.position.y) >= -UPFIELD_DEPTH:
            return False
        if ctx.depth(me.velocity.y) >= RETURN_SPEED:
            return False
        last_touch = ctx.last_touch_team[index]
        if last_touch is None or last_touch == ctx.team:
            return False
        back = sum(
            1
            for car in _active_cars(frame)
            if car.team == ctx.team
            and car.player_id != ctx.player_id
            and ctx.depth(car.position.y) > ball_depth
        )
        return back <= allowed_back

    flags: list[Mistake] = []
    for start, end in _spells(ctx, caught):
        duration = ctx.times[end] - ctx.times[start]
        if duration < UPFIELD_MIN_S:
            continue
        flags.append(
            _flag(
                ctx,
                "caught_upfield",
                start,
                duration,
                f"The opponent had the ball in your half for {duration:.1f} s while "
                "you stayed in theirs, with too few teammates back.",
            )
        )
    return flags


def last_back_challenges(ctx: Context) -> Iterator[tuple[int, ChallengeEvent, bool]]:
    """Your 50/50s in open play as your team's last player back: the frame just
    before it, the 50/50, and whether you lost it."""
    mine = team_name(ctx.team)
    for challenge in ctx.challenges:
        if ctx.player_id not in (challenge.first_player, challenge.second_player):
            continue
        if challenge.winner_team is None:
            continue
        index = ctx.index_at(challenge.t - 0.3)
        if not ctx.live[index] or not _past_kickoff(ctx, index):
            continue
        if is_last_back(ctx.frames[index], ctx.player_id):
            yield index, challenge, challenge.winner_team != mine


def detect_last_back_challenges(ctx: Context) -> list[Mistake]:
    """Flag 50/50s lost as the last player back, with the ball then coming at
    your goal.

    Not while your team chases a late goal, when the last player back should
    be up too.
    """
    flags: list[Mistake] = []
    for index, challenge, lost in last_back_challenges(ctx):
        if not lost or _chasing_late(ctx, index):
            continue
        # The event names whoever touched last, even if the ball went forward.
        after = ctx.frames[ctx.index_at(challenge.t + CHALLENGE_SETTLE_S)]
        if ctx.depth(after.ball.velocity.y) <= 0:
            continue
        opponent = (
            challenge.second_player
            if challenge.first_player == ctx.player_id
            else challenge.first_player
        )
        flags.append(
            _flag(
                ctx,
                "last_back_challenge",
                index,
                0.0,
                f"You went into a 50/50 with {ctx.name(opponent)} as your team's "
                "last player back and lost it, with nobody behind you.",
            )
        )
    return flags


def clears(ctx: Context) -> Iterator[tuple[Contact, Contact | None, bool]]:
    """Each of your clears: the touch, the next touch by anyone, and whether an
    opponent won the ball back before it left your third.

    A clear is your touch in your own half in open play that sends the ball
    upfield, unless you touch it again next or an opponent blocks it at once.
    """
    for position, contact in enumerate(ctx.contacts):
        if contact.player_id != ctx.player_id or not ctx.live[contact.index]:
            continue
        ball = ctx.frames[contact.index].ball
        if ctx.depth(ball.position.y) <= 0 or not _past_kickoff(ctx, contact.index):
            continue
        if -ctx.depth(ball.velocity.y) < CLEAR_MIN_SPEED:
            continue
        following = (
            ctx.contacts[position + 1] if position + 1 < len(ctx.contacts) else None
        )
        if following is not None and (
            following.player_id == ctx.player_id
            or (
                following.team != ctx.team
                and following.t - contact.t < CLEAR_MIN_FLIGHT_S
            )
        ):
            continue
        given_back = not (
            following is None
            or following.team == ctx.team
            or following.t - contact.t > CLEAR_RETURN_WINDOW_S
            or ctx.depth(ctx.frames[following.index].ball.position.y) <= CLEARED_DEPTH
        )
        yield contact, following, given_back


def detect_clears_given_back(ctx: Context) -> tuple[list[Mistake], dict[str, int]]:
    """Count clears the opponent won back, and flag the ones that hurt."""
    flags: list[Mistake] = []
    summary = {"clears": 0, "given_back": 0}
    for contact, following, given_back in clears(ctx):
        summary["clears"] += 1
        if not given_back:
            continue
        summary["given_back"] += 1
        flag = _flag(
            ctx,
            "clear_given_back",
            contact.index,
            following.t - contact.t,
            f"Your clear went straight to {ctx.name(following.player_id)}, still "
            "in your third.",
        )
        if flag.outcome:
            flags.append(flag)
    return flags, summary


def _left_the_ground(car: PlayerFrame) -> bool:
    """The game says the car is jumping, double jumping or flipping."""
    return car.is_jumping or car.is_double_jumping or car.is_dodging


def _jumps_before(
    ctx: Context, car_id: str, first: int, cross: int
) -> tuple[bool, bool]:
    """Whether a car jumped in time for the ball crossing at `cross`, from the
    window that starts at `first`, and whether it only jumped too late.

    A jump counts from when it starts, so a state the replay never ends says
    nothing.
    """
    start = ctx.index_at(ctx.times[first] - JUMP_LOOKBACK_S)
    before = ctx.frames[start - 1].get_player_by_id(car_id) if start else None
    was_up = before is not None and _left_the_ground(before)
    jumped = late = False
    for index in range(start, cross + 1):
        car = ctx.frames[index].get_player_by_id(car_id)
        if car is None:
            continue
        up = _left_the_ground(car)
        if up and not was_up:
            if ctx.times[cross] - ctx.times[index] >= JUMP_LEAD_S:
                jumped = True
            else:
                late = True
        was_up = up
    return jumped, late


def _goes(ctx: Context) -> list[tuple[int, int]]:
    """Each time you left the ground in play: the frames where its first and last
    jump or flip started. A flip or double jump soon after a jump is the same go."""
    goes: list[tuple[int, int]] = []
    was_up = False
    for index, frame in enumerate(ctx.frames):
        car = frame.get_player_by_id(ctx.player_id)
        up = car is not None and _left_the_ground(car)
        if up and not was_up and ctx.live[index]:
            if goes and ctx.times[index] - ctx.times[goes[-1][1]] < WHIFF_SAME_GO_S:
                goes[-1] = (goes[-1][0], index)
            else:
                goes.append((index, index))
        was_up = up
    return goes


def _nearest_approach(ctx: Context, first: int, end_t: float) -> tuple[float, int]:
    """How near your car came to the ball from frame `first` until `end_t`."""
    best, best_index = math.inf, first
    index = first
    while index < len(ctx.frames) and ctx.times[index] <= end_t:
        car = ctx.frames[index].get_player_by_id(ctx.player_id)
        if car is not None and not car.is_demolished:
            gap = _distance(car.position, ctx.frames[index].ball.position)
            if gap < best:
                best, best_index = gap, index
        index += 1
    return best, best_index


def _lost_it(ctx: Context, t: float) -> tuple[bool, str | None]:
    """Whether the opponents had the ball next after `t`, before your team touched
    it, and who took it. A goal against with no touch before it means they did,
    with nobody to name."""
    mine = team_name(ctx.team)
    goal = next((g for g in ctx.goals if g.team != mine and g.t > t), None)
    following = _next_contact_after(ctx, t)
    if goal is not None and (following is None or goal.t < following.t):
        return True, None
    if following is None or following.team == ctx.team:
        return False, None
    return True, following.player_id


def jumps_at_ball(ctx: Context) -> Iterator[tuple[int, int, float, bool]]:
    """Each time you jumped or flipped at the ball in open play: the frame you
    left the ground, the frame you came nearest the ball, how near, and whether
    you hit it.

    A miss is a go that came within reach with nobody touching the ball. One
    where someone else got the touch, or that never came near, is neither.
    """
    for first, last in _goes(ctx):
        if not _past_kickoff(ctx, first):
            continue
        frame = ctx.frames[first]
        me = frame.get_player_by_id(ctx.player_id)
        if me is None or _closing_speed(me, frame.ball) < WHIFF_MIN_CLOSING:
            continue
        start, end = ctx.times[first], ctx.times[last] + WHIFF_WINDOW_S
        touches = [c for c in ctx.contacts if start - TOUCH_SLOP_S <= c.t <= end]
        gap, nearest = _nearest_approach(ctx, first, end)
        if any(c.player_id == ctx.player_id for c in touches):
            yield first, nearest, gap, True
        elif not touches and gap < WHIFF_REACH:
            yield first, nearest, gap, False


def detect_whiffs(ctx: Context) -> list[Mistake]:
    """Flag jumping or flipping at the ball and missing it, when the opponents
    took it and it led somewhere.

    The goal review already judges a miss in the last seconds before a goal
    against, so those are left to it.
    """
    flags: list[Mistake] = []
    mine = team_name(ctx.team)
    for first, nearest, gap, hit in jumps_at_ball(ctx):
        if hit:
            continue
        start = ctx.times[first]
        t = ctx.times[nearest]
        if any(
            g.team != mine and 0.0 <= g.t - t <= GOAL_REVIEW_WINDOW_S for g in ctx.goals
        ):
            continue
        lost, taker = _lost_it(ctx, t)
        if not lost:
            continue
        flipped = any(
            car is not None and car.is_dodging
            for car in (
                ctx.frames[i].get_player_by_id(ctx.player_id)
                for i in range(first, nearest + 1)
            )
        )
        where = (
            "your" if ctx.depth(ctx.frames[nearest].ball.position.y) > 0 else "their"
        )
        flag = _flag(
            ctx,
            "whiff",
            first,
            t - start,
            f"You {'flipped' if flipped else 'jumped'} at the ball in {where} half "
            f"and missed it, {gap / 100:.1f} m away at the closest."
            + (f" {ctx.name(taker)} got it next." if taker else ""),
        )
        if flag.outcome:
            flags.append(flag)
    return flags


def _cars_on_my_team(frame: Frame, team: int) -> list[PlayerFrame]:
    return [p for p in frame.players if p.team == team]


def last_back_car(frame: Frame, team: int) -> PlayerFrame | None:
    """The team's last player back: its car nearest its own goal, of those not
    demolished."""
    standing = [c for c in _cars_on_my_team(frame, team) if not c.is_demolished]
    return max(standing, key=lambda c: own_depth(c.position.y, team), default=None)


def is_last_back(frame: Frame, player_id: str) -> bool | None:
    """Whether a player was their team's last back, or None if their car wasn't
    on the field."""
    car = frame.get_player_by_id(player_id)
    if car is None or car.is_demolished:
        return None
    back = last_back_car(frame, car.team)
    return back is not None and back.player_id == player_id


def _can_reach_shot(
    ctx: Context, car: PlayerFrame | None, ball: BallFrame, warning: float
) -> bool:
    """Check whether a car in goal could have got to the ball in time."""
    if car is None or ball.position.z >= GOAL_HEIGHT:
        return False
    in_goal = (
        ctx.depth(car.position.y) > GOAL_LINE_Y - IN_GOAL_DEPTH
        and abs(car.position.x) < GOAL_WIDTH + IN_GOAL_MARGIN
    )
    reach = min(SAVE_REACH + SAVE_TRAVEL * warning, SAVE_REACH_MAX)
    return in_goal and _flat_distance(car.position, ball.position) < reach


def _heading_into_goal(ctx: Context, ball: BallFrame) -> bool:
    """Project the ball to the goal line and check it lands between the posts."""
    speed = ctx.depth(ball.velocity.y)
    if speed < HEADING_MIN_SPEED:
        return False
    travel = (GOAL_LINE_Y - ctx.depth(ball.position.y)) / speed
    return abs(ball.position.x + ball.velocity.x * travel) < GOAL_WIDTH


def _touch_that_turned_it_in(ctx: Context, earliest: int, cross: int) -> Contact | None:
    """Find a defender's touch near the net that put a wide ball on target.

    Only touches after the last opponent touch count, because anything before
    that is not what sent the ball in. A touch far from the net doesn't count,
    because that ball can still be saved.
    """
    touches = [c for c in ctx.contacts if earliest <= c.index <= cross]
    for contact in reversed(touches):
        if contact.team != ctx.team:
            return None
        before = ctx.frames[contact.index - 1].ball
        after = ctx.frames[contact.index].ball
        if ctx.depth(after.position.y) < DANGER_DEPTH:
            continue
        if _heading_into_goal(ctx, after) and not _heading_into_goal(ctx, before):
            return contact
    return None


def _review_defender(
    ctx: Context, car_id: str, last_touch: int, cross: int
) -> DefenderRole:
    """Work out what one defender did about a goal."""
    first = ctx.index_at(ctx.times[cross] - GOAL_REVIEW_WINDOW_S)
    heights: list[float] = []
    jumped, late_jump = _jumps_before(ctx, car_id, first, cross)
    closest = after_shot = math.inf
    moment = shot_moment = cross
    for index in range(first, cross + 1):
        frame = ctx.frames[index]
        car = frame.get_player_by_id(car_id)
        if car is None or car.is_demolished:
            continue
        heights.append(car.position.z)
        gap = _distance(car.position, frame.ball.position)
        if gap < closest:
            closest, moment = gap, index
        if index >= last_touch and gap < after_shot:
            after_shot, shot_moment = gap, index
    if not heights:
        return DefenderRole("demolished", "was demolished", cross)

    if not ctx.reports_jumps:
        jumped = max(heights) - min(heights) > JUMP_RISE
    late_jump = late_jump and not jumped
    touched = any(
        c.player_id == car_id and first <= c.index <= cross for c in ctx.contacts
    )
    warning = ctx.times[cross] - ctx.times[last_touch]
    had_time = warning >= SAVE_REACTION_S
    crossing = ctx.frames[cross]
    at_line = crossing.get_player_by_id(car_id)

    velocity = ctx.frames[moment].ball.velocity
    speed = math.hypot(velocity.x, velocity.y, velocity.z)

    if touched:
        return DefenderRole("touched", "got a touch on it", moment)
    in_reach = _can_reach_shot(ctx, at_line, crossing.ball, warning)
    if in_reach and had_time and not jumped:
        late = "jumped too late" if late_jump else "never jumped"
        text = f"was in goal with time to react and {late}"
        return DefenderRole("no_save_attempt", text, moment, late_jump=late_jump)
    if closest >= MISS_RANGE:
        if (
            had_time
            and at_line is not None
            and ctx.depth(at_line.position.y) > GOAL_LINE_Y + BEHIND_LINE_MARGIN
        ):
            text = "was behind your goal line as it went in"
            gap = _flat_distance(at_line.position, crossing.ball.position)
            return DefenderRole("behind_line", text, last_touch, gap)
        text = (
            f"got no closer than {closest / 100:.0f} m to the ball "
            f"in the last {GOAL_REVIEW_WINDOW_S:.0f} s"
        )
        return DefenderRole("away", text, moment)
    if speed < SLOW_BALL_SPEED:
        text = "reached a slow ball and didn't clear it"
        return DefenderRole("missed_clear", text, moment, closest, speed)
    # A save is judged on the ball's path after the last touch, and the time to
    # react runs until the ball reached you, not the line. In goal the two
    # match. Out in front of the shooter the ball can be past you before you
    # could move.
    reaction = ctx.times[shot_moment] - ctx.times[last_touch]
    if after_shot >= MISS_RANGE or reaction < SAVE_REACTION_S:
        return DefenderRole("beaten", "was beaten by the shot", moment)
    velocity = ctx.frames[shot_moment].ball.velocity
    speed = math.hypot(velocity.x, velocity.y, velocity.z)
    if jumped:
        text = "jumped for it and missed"
    elif late_jump:
        text = "jumped too late"
    else:
        text = "couldn't reach it"
    return DefenderRole("missed_save", text, shot_moment, after_shot, speed)


def _review_goal(ctx: Context, goal: GoalEvent) -> tuple[GoalReview, Mistake | None]:
    goal_index = ctx.index_at(goal.t)
    # Stop at the kickoff: the ball sits in the net for a while after a goal.
    earliest = max(
        ctx.index_at(goal.t - GOAL_LOOKBACK_S),
        ctx.index_at(ctx.kickoff_start[goal_index]),
    )
    cross = next(
        (
            i
            for i in range(earliest, goal_index + 1)
            if ctx.depth(ctx.frames[i].ball.position.y) >= GOAL_LINE_Y
        ),
        goal_index,
    )
    shots = [
        c for c in ctx.contacts if c.team != ctx.team and earliest <= c.index <= cross
    ]
    shot = shots[-1].index if shots else earliest
    touches = [c.index for c in ctx.contacts if earliest <= c.index <= cross]
    last_touch = touches[-1] if touches else earliest
    turned = _touch_that_turned_it_in(ctx, earliest, cross)
    # Soft touches go unseen, so an old shot says nothing about who was back.
    decision = max(shot, ctx.index_at(ctx.times[cross] - GOAL_DECISION_S))
    decision_frame = ctx.frames[decision]
    ball_depth = ctx.depth(decision_frame.ball.position.y)
    cars = _cars_on_my_team(decision_frame, ctx.team)

    roles: dict[str, DefenderRole] = {}
    lines: list[str] = []
    for car in sorted(cars, key=lambda c: c.player_id != ctx.player_id):
        role = _review_defender(ctx, car.player_id, last_touch, cross)
        if turned is not None and turned.player_id == car.player_id:
            text = "turned the ball into your net"
            role = DefenderRole("own_touch_in", text, turned.index)
        roles[car.player_id] = role
        text = role.text
        if car.player_id == ctx.player_id and text.startswith("was "):
            text = "were " + text[len("was ") :]
        at_line = ctx.frames[cross].get_player_by_id(car.player_id) or car
        lines.append(
            f"{ctx.name(car.player_id)} {text} ({at_line.boost_amount:.0f} boost)"
        )

    last_back = last_back_car(decision_frame, ctx.team)
    my_role = roles.get(ctx.player_id)
    label = my_role.label if my_role is not None else None

    kind: str | None = None
    what = ""
    moment = decision
    if label == "own_touch_in":
        kind = "own_touch_in"
        what = "The ball wasn't heading for your goal until your touch turned it in."
    elif label == "no_save_attempt":
        kind = "no_save_attempt"
        late = "jumped too late" if my_role.late_jump else "never jumped"
        what = f"You were in goal with time to react, and you {late}."
    elif label == "missed_clear":
        kind = "missed_clear"
        what = (
            f"You got within {my_role.gap / 100:.1f} m of a slow ball "
            f"({my_role.ball_speed * UU_S_TO_KPH:.0f} km/h) by your net and "
            "didn't clear it."
        )
    elif label == "missed_save":
        kind = "missed_save"
        what = (
            "You had time to meet this shot, and it got past you "
            f"{my_role.gap / 100:.1f} m away."
        )
    elif label == "behind_line":
        kind = "behind_line"
        warning = ctx.times[cross] - ctx.times[last_touch]
        what = (
            f"You had {warning:.1f} s to react, but you were behind your goal line, "
            f"{my_role.gap / 100:.0f} m from the ball as it went in."
        )
    elif (
        last_back is not None
        and last_back.player_id == ctx.player_id
        and _past_kickoff(ctx, decision)
        # Chasing a late goal, the last player back should be up too
        and not _chasing_late(ctx, decision)
    ):
        my_depth = ctx.depth(last_back.position.y)
        ball_past_me = my_depth < ball_depth
        in_their_half = my_depth < -UPFIELD_DEPTH
        if ball_past_me or in_their_half:
            kind = "last_back_upfield"
            # Say which it was: most of these happen in your own half
            where = (
                f", {-my_depth / 100:.0f} m into their half," if in_their_half else ""
            )
            if ball_past_me:
                what = (
                    f"You were your team's last player back{where} and the ball "
                    "was already between you and your net when the shot came."
                )
            else:
                what = (
                    f"You were your team's last player back, {-my_depth / 100:.0f} m "
                    "into their half when the shot came."
                )
        elif (
            -ctx.depth(last_back.velocity.y) >= OVERCOMMIT_SPEED
            and _closing_speed(last_back, decision_frame.ball) >= OVERCOMMIT_SPEED
        ):
            kind = "last_back_overcommit"
            what = (
                "You were your team's last player back and went out at the ball, "
                "so nobody was left in goal when it got past you."
            )
    if my_role is not None and kind in GOAL_CHANCES:
        moment = my_role.index

    if kind in ("last_back_upfield", "last_back_overcommit"):
        summary = "You were the last one back."
    elif kind == "own_touch_in":
        summary = "Your touch turned it in."
    elif kind is not None:
        summary = "You had the chance to stop this."
    elif any(r.label in GOAL_CHANCES for r in roles.values()):
        summary = "A teammate had the chance to stop this."
    else:
        summary = "No mistake found."

    review = GoalReview(
        t=round(goal.t, 2),
        clock=_clock_at(ctx, goal_index),
        score=_score_at(ctx, goal.t),
        scorer=ctx.name(goal.scorer),
        on_you=kind is not None,
        summary=summary,
        lines=tuple(lines),
        seconds_left=round(_seconds_left_at(ctx, goal_index), 1),
    )
    flag = None
    if kind is not None:
        flag = _flag(ctx, kind, moment, 0.0, what, cost_goal=True)
    return review, flag


def review_conceded_goals(ctx: Context) -> tuple[list[GoalReview], list[Mistake]]:
    """Break down each goal against the reviewed player's team."""
    mine = team_name(ctx.team)
    reviews: list[GoalReview] = []
    flags: list[Mistake] = []
    for goal in ctx.goals:
        if goal.team == mine:
            continue
        review, flag = _review_goal(ctx, goal)
        reviews.append(review)
        if flag is not None:
            flags.append(flag)
    return reviews, flags


# How a goal review names the earlier moment that led to the goal
def _after_the_kickoff(kickoff: KickoffEvent, team: int) -> str:
    result = kickoff_result(kickoff, team)
    if result == "LOST":
        return " A second later the ball was coming back into your half."
    if result == "WON":
        return " The ball still went forward for you, but you can't count on that."
    return ""


def _kickoff_flags(
    ctx: Context, kickoff: KickoffEvent, me: KickoffPlayer
) -> list[Mistake]:
    """The kickoff habits a coach would correct, for one kickoff."""
    if kickoff.time_to_first_touch is None or not went_for_ball(me):
        return []
    index = ctx.index_at(kickoff.t_start + kickoff.time_to_first_touch)
    after = _after_the_kickoff(kickoff, ctx.team)
    spot = SPOT_NAMES.get(me.spot or "", "your spawn")
    flags = []
    timing = flip_timing(me)
    if me.role == "GO" and timing == "NONE":
        flags.append(
            _flag(
                ctx,
                "kickoff_no_flip",
                index,
                0.0,
                f"You went for the kickoff from {spot} and reached the ball "
                f"without flipping into it.{after}",
            )
        )
    elif me.role == "GO" and timing == "LATE":
        flags.append(
            _flag(
                ctx,
                "kickoff_late_flip",
                index,
                0.0,
                f"Your flip into the kickoff began {-me.flip_lead:.2f} s after the "
                f"ball was played, from {spot}.{after}",
            )
        )
    return flags


def review_kickoffs(
    ctx: Context, kickoffs: list[KickoffEvent]
) -> tuple[list[KickoffMoment], list[Mistake]]:
    """Place every kickoff on the clock, and flag your kickoff habits."""
    moments: list[KickoffMoment] = []
    flags: list[Mistake] = []
    for kickoff in kickoffs:
        index = ctx.index_at(kickoff.t_start)
        moments.append(
            KickoffMoment(
                t=round(kickoff.t_start, 2),
                clock=_clock_at(ctx, index),
                seconds_left=round(_seconds_left_at(ctx, index), 1),
                score=_score_at(ctx, kickoff.t_start),
                kickoff=kickoff,
            )
        )
        me = next((p for p in kickoff.players if p.player_id == ctx.player_id), None)
        if me is not None:
            flags.extend(_kickoff_flags(ctx, kickoff, me))
    return moments, flags


def _seconds_left(ctx: Context, index: int) -> float:
    return round(_seconds_left_at(ctx, index), 1)


def place_touches(ctx: Context, touches: Iterable[TouchEvent]) -> list[TouchMoment]:
    """Place every car's touches on the clock."""
    return [TouchMoment(_seconds_left(ctx, touch.frame), touch) for touch in touches]


def place_challenges(
    ctx: Context, challenges: Iterable[ChallengeEvent]
) -> list[ChallengeMoment]:
    """Place every 50/50 on the clock, with who was last back for each team."""
    moments = []
    for challenge in challenges:
        index = ctx.index_at(challenge.t)
        frame = ctx.frames[index]
        moments.append(
            ChallengeMoment(
                seconds_left=_seconds_left(ctx, index),
                challenge=challenge,
                first_last_back=is_last_back(frame, challenge.first_player),
                second_last_back=is_last_back(frame, challenge.second_player),
            )
        )
    return moments


def place_demos(ctx: Context, demos: Iterable[DemoEvent]) -> list[DemoMoment]:
    """Place every demo on the clock."""
    return [DemoMoment(_seconds_left(ctx, ctx.index_at(d.t)), d) for d in demos]


LEAD_IN = {
    "clear_given_back": "Your clear went straight back to them",
    "double_commit": "You double committed",
    "caught_upfield": "You were caught upfield",
    "last_back_challenge": "You lost a 50/50 as the last player back",
    "kickoff_no_flip": "You went for the kickoff without a flip",
    "kickoff_late_flip": "Your kickoff flip came late",
    "whiff": "You whiffed",
}


def link_goals_to_moments(
    ctx: Context, reviews: list[GoalReview], flags: list[Mistake]
) -> tuple[list[GoalReview], list[Mistake]]:
    """Blame a goal the review cleared you of on your moment that started it.

    The goal review only looks a few seconds back. If one of your flagged
    moments came earlier and the opponents kept the ball from then until it
    went in, that moment cost the goal. Each goal costs at most one moment, the
    latest, and a goal the review already put on you keeps its own verdict.
    """
    mine = team_name(ctx.team)
    against = [g for g in ctx.goals if g.team != mine]
    reviews = list(reviews)
    flags = list(flags)
    for position, (goal, review) in enumerate(zip(against, reviews, strict=True)):
        if review.on_you:
            continue
        leads = [
            i
            for i, flag in enumerate(flags)
            if flag.kind in LEAD_IN
            and not flag.cost_goal
            and flag.t <= goal.t <= flag.t + GOAL_CONSEQUENCE_S
            and _opponents_kept_it(ctx, flag.t, goal.t)
        ]
        if not leads:
            continue
        lead = max(leads, key=lambda i: flags[i].t)
        flag = flags[lead]
        delay = goal.t - flag.t
        when = "just before" if delay < 1.0 else f"{delay:.0f} s before"
        flags[lead] = replace(flag, cost_goal=True)
        reviews[position] = replace(
            review, on_you=True, summary=f"{LEAD_IN[flag.kind]} {when}."
        )
    return reviews, flags


def goal_timeline(ctx: Context) -> list[GoalMoment]:
    """Place every goal on the clock and mark the winner and equalizers."""
    mine = team_name(ctx.team)
    goals = sorted(ctx.goals, key=lambda g: g.t)
    final_ours = sum(1 for g in goals if g.team == mine)
    final_theirs = len(goals) - final_ours
    ours = theirs = 0
    moments: list[GoalMoment] = []
    for goal in goals:
        index = ctx.index_at(goal.t)
        is_ours = goal.team == mine
        before = f"{ours}-{theirs}"
        if is_ours:
            ours += 1
        else:
            theirs += 1
        moments.append(
            GoalMoment(
                t=round(goal.t, 2),
                clock=_clock_at(ctx, index),
                seconds_left=round(_seconds_left_at(ctx, index), 1),
                score=before,
                ours=is_ours,
                scorer=ctx.name(goal.scorer),
                by_you=goal.scorer == ctx.player_id,
                assist_by_you=goal.assist == ctx.player_id,
                winner=is_ours
                and final_ours > final_theirs
                and ours == final_theirs + 1,
                equalizer=is_ours and ours == theirs,
            )
        )
    return moments


def analyze_replay(
    path: Path, player: str | None = None, *, player_id: str | None = None
) -> MistakeReport:
    """Read a replay and review one player in it. See review_player."""
    return review_player(read_game(path), player, player_id=player_id)


def review_player(
    game: Game, player: str | None = None, *, player_id: str | None = None
) -> MistakeReport:
    """Review one player in a game, defaulting to whoever saved the replay.

    `player_id` picks the player by the id the database stores, which survives
    a name change. Otherwise `player` matches a display name.
    """
    from .situations import game_situations

    header, frames = game.header, game.frames
    check_supported_map(header.map_name)

    identities = build_player_identities(header.players)
    names = {i.canonical_id: i.display_name for i in identities}
    if player_id is not None:
        match = next((i for i in identities if i.canonical_id == player_id), None)
        wanted = player_id
    else:
        wanted = player or header.recorded_by
        match = next(
            (i for i in identities if wanted and i.display_name == wanted), None
        )
    if match is None:
        options = ", ".join(sorted(names.values()))
        raise ValueError(f"No player {wanted!r}. Players: {options}")

    ctx = build_context(
        frames,
        player_id=match.canonical_id,
        goals=game.goals,
        challenges=game.challenges,
        names=names,
        team_size=header.team_size,
        touches=game.touches,
    )

    reviews, goal_flags = review_conceded_goals(ctx)
    clear_flags, clears = detect_clears_given_back(ctx)
    kickoffs, kickoff_flags = review_kickoffs(ctx, game.kickoffs)
    reviews, earlier_flags = link_goals_to_moments(
        ctx,
        reviews,
        [
            *detect_double_commits(ctx),
            *detect_caught_upfield(ctx),
            *detect_last_back_challenges(ctx),
            *clear_flags,
            *detect_whiffs(ctx),
            *kickoff_flags,
        ],
    )
    mistakes = sorted([*goal_flags, *earlier_flags], key=lambda m: m.t)
    return MistakeReport(
        player=match.display_name,
        team=match.team,
        map_name=header.map_name,
        final_score=_score_at(ctx, math.inf),
        goals=reviews,
        mistakes=mistakes,
        clears=clears,
        player_id=match.canonical_id,
        goal_timeline=goal_timeline(ctx),
        kickoffs=kickoffs,
        touches=place_touches(ctx, game.touches),
        challenges=place_challenges(ctx, game.challenges),
        demos=place_demos(ctx, game.demos),
        situations=game_situations(game, names),
    )


def format_report(report: MistakeReport) -> str:
    """Render a review as plain text for the terminal."""
    lines = [
        f"Mistake review for {report.player} ({report.team}) on {report.map_name}",
        f"Final score, your team first: {report.final_score}",
        "Clock times are estimates, usually within a few seconds.",
        "",
    ]
    if report.goals:
        lines.append("Goals conceded")
        for goal in report.goals:
            lines.append(
                f"  ~{goal.clock} left ({goal.score}): {goal.scorer} scored. "
                f"{goal.summary}"
            )
            lines.extend(f"    - {line}" for line in goal.lines)
        lines.append("")

    lines.append(f"Your flagged moments: {len(report.mistakes)}")
    for number, mistake in enumerate(report.mistakes, start=1):
        title = mistake.kind.replace("_", " ")
        lines.append(f"  {number}. ~{mistake.clock} left ({mistake.score}): {title}")
        lines.append(f"     {mistake.what}")
        if mistake.outcome:
            lines.append(f"     {mistake.outcome}")
        lines.append(f"     Instead: {mistake.instead}")
    lines.append("")

    clears = report.clears
    if clears["clears"]:
        lines.append(
            f"Clears: {clears['given_back']} of {clears['clears']} from your half "
            "went to an opponent before leaving your third."
        )
    mine = [
        p
        for moment in report.kickoffs
        for p in moment.kickoff.players
        if p.player_id == report.player_id and p.role == "GO"
    ]
    if report.kickoffs:
        timings = [flip_timing(p) for p in mine]
        lines.append(
            f"Kickoffs: {len(report.kickoffs)}, {len(mine)} with you going. "
            f"Your flip into the ball: {timings.count('ON_TIME')} on time, "
            f"{timings.count('LATE')} late, {timings.count('NONE')} none."
        )
    return "\n".join(lines)
