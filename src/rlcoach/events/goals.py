"""Goals: when each was scored, by which team, and who scored and assisted.

The header lists every goal with its frame, its team and the scorer's name.
It names no assist, so the assist goes to the teammate who was last near the
ball within 6 s of the goal.
"""

from __future__ import annotations

from ..identity import build_player_identities, sanitize_display_name
from ..parser.types import Frame, GoalHeader, Header
from .types import GoalEvent, distance, team_name

NEAR_BALL_UU = 200.0  # A car this close to the ball counts as having touched it
ASSIST_WINDOW_S = 6.0


def detect_goals(frames: list[Frame], header: Header) -> list[GoalEvent]:
    """Each goal the header lists, timed by its frame.

    A goal the header gives no frame for can't be placed, so it's left out.
    """
    identities = build_player_identities(header.players)
    by_name = {
        identity.display_name.lower(): identity.canonical_id for identity in identities
    }

    def scorer_of(goal: GoalHeader, team: str) -> str | None:
        name = sanitize_display_name(goal.player_name).lower()
        if name in by_name:
            return by_name[name]
        # A player renamed mid-match goes by their team's first player
        return next((i.canonical_id for i in identities if i.team == team), None)

    pending = [goal for goal in header.goals if goal.frame is not None]
    # Each player's last time near the ball, and their team then. A dict keeps
    # the order players were first near it, which settles a tie for the assist.
    last_near: dict[str, tuple[float, int]] = {}
    goals: list[GoalEvent] = []

    def score(goal: GoalHeader, t: float, near: dict[str, tuple[float, int]]) -> None:
        team = team_name(goal.player_team)
        scorer = scorer_of(goal, team)
        assist, latest = None, None
        for player_id, (seen, player_team) in near.items():
            if player_id == scorer or team_name(player_team) != team:
                continue
            if t - seen <= ASSIST_WINDOW_S and (latest is None or seen > latest):
                assist, latest = player_id, seen
        goals.append(GoalEvent(t=t, team=team, scorer=scorer, assist=assist))

    next_goal = 0
    for index, frame in enumerate(frames):
        if next_goal == len(pending):
            break
        ball = frame.ball.position
        for car in frame.players:
            if distance(car.position, ball) < NEAR_BALL_UU:
                last_near[car.player_id] = (frame.timestamp, car.team)
        while next_goal < len(pending) and pending[next_goal].frame <= index:
            goal = pending[next_goal]
            score(goal, frames[max(goal.frame, 0)].timestamp, last_near)
            next_goal += 1
    # A goal past the last frame goes at the end, with no assist
    for goal in pending[next_goal:]:
        score(goal, frames[-1].timestamp, {})
    return goals
