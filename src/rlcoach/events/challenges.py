"""Challenges: 50/50s, found as touches by opponents one straight after the other."""

from __future__ import annotations

from ..parser.types import Frame
from .types import ChallengeEvent, TouchEvent, distance, team_name

WINDOW_S = 1.2  # The second touch comes this soon after the first
FARTHEST_UU = 1000.0  # The two cars were this close together, at most
NEAREST_UU = 200.0  # And at least this far apart, or it's one car's touch
SLOWEST_KPH = 15.0  # One of the touches moved the ball at least this fast
RETOUCH_S = 0.25  # A third touch this soon after makes it nobody's


def detect_challenges(
    frames: list[Frame], touches: list[TouchEvent]
) -> list[ChallengeEvent]:
    """Pair up opposing touches into 50/50s. Each touch is in one at most."""
    teams: dict[str, int] = {}
    for frame in frames:
        for car in frame.players:
            teams.setdefault(car.player_id, car.team)

    ordered = sorted(touches, key=lambda touch: (touch.t, touch.player_id))
    challenges: list[ChallengeEvent] = []
    i = 0
    while i < len(ordered) - 1:
        first, second = ordered[i], ordered[i + 1]
        first_team, second_team = teams.get(first.player_id), teams.get(
            second.player_id
        )
        gap = distance(first.location, second.location)
        if (
            first_team is None
            or second_team is None
            or first_team == second_team
            or not 0 <= second.t - first.t <= WINDOW_S
            or not NEAREST_UU <= gap <= FARTHEST_UU
            or max(first.ball_speed_kph, second.ball_speed_kph) < SLOWEST_KPH
        ):
            i += 1
            continue
        winner: str | None = team_name(second_team)
        step = 2
        if i + 2 < len(ordered):
            third = ordered[i + 2]
            if (
                third.player_id in teams
                and third.t - second.t <= RETOUCH_S
                and distance(second.location, third.location) <= FARTHEST_UU
            ):
                winner, step = None, 3
        challenges.append(
            ChallengeEvent(
                t=(first.t + second.t) / 2.0,
                first_player=first.player_id,
                second_player=second.player_id,
                winner_team=winner,
            )
        )
        i += step
    return challenges
