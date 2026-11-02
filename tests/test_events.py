"""Tests for event detection and timeline aggregation."""

import math
from dataclasses import replace
from pathlib import Path

import pytest

from rlcoach.events import (
    GOAL_LINE_THRESHOLD,
    DemoEvent,
    GoalEvent,
    KickoffEvent,
    TouchEvent,
    build_timeline,
    detect_boost_pickups,
    detect_challenge_events,
    detect_demos,
    detect_goals,
    detect_kickoffs,
    detect_touches,
)
from rlcoach.field_constants import FIELD, Vec3
from rlcoach.normalize import build_timeline as build_normalized_frames
from rlcoach.parser import get_adapter
from rlcoach.parser.types import (
    BallFrame,
    Frame,
    Header,
    ParserComponentEvent,
    ParserDemoEvent,
    ParserKickoffMarker,
    ParserTouchEvent,
    PlayerFrame,
    Quaternion,
    Rotation,
)


def create_test_frame(
    timestamp: float, ball_pos: Vec3, ball_vel: Vec3, players: list[PlayerFrame]
) -> Frame:
    """Helper to create test frames."""
    return Frame(
        timestamp=timestamp,
        ball=BallFrame(
            position=ball_pos, velocity=ball_vel, angular_velocity=Vec3(0.0, 0.0, 0.0)
        ),
        players=players,
    )


def create_test_player(
    player_id: str,
    team: int,
    pos: Vec3,
    boost: int = 33,
    demolished: bool = False,
    on_ground: bool = True,
) -> PlayerFrame:
    """Helper to create test player frames."""
    return PlayerFrame(
        player_id=player_id,
        team=team,
        position=pos,
        velocity=Vec3(0.0, 0.0, 0.0),
        rotation=Vec3(0.0, 0.0, 0.0),
        boost_amount=boost,
        is_supersonic=False,
        is_on_ground=on_ground,
        is_demolished=demolished,
    )


FRAME_STEP = 1 / 30


def countdown_frames(
    reset: float,
    phase: str = "INITIAL",
    blue_drive: float = 920.0,
    orange_drive: float = 800.0,
    ball_exit: float = 1500.0,
) -> list[Frame]:
    """One kickoff as real replays record it, from ball reset to contact.

    The ball drops onto the spot, which fires a second parser marker once it stops,
    and the cars settle before the countdown holds them still. They are released 4s
    after the reset, and the ball is played 2.1s later, leaving along +y at
    ``ball_exit``. The drive speeds set how far each car is from it by then.
    """
    release = reset + 4.0
    contact = release + 2.1
    ball_drop = {0: (100.5, 0.0), 1: (98.8, -43.0), 2: (96.9, -65.0), 3: (94.3, -86.0)}

    frames = []
    for step in range(int((contact + 0.3 - reset) / FRAME_STEP)):
        t = reset + step * FRAME_STEP
        driving = max(0.0, t - release)
        held_speed = 120.0 if step <= 10 else 8.0
        blue_speed = blue_drive if driving else held_speed
        orange_speed = orange_drive if driving else held_speed
        players = [
            replace(
                create_test_player(
                    "blue",
                    0,
                    Vec3(0.0, -2048.0 + blue_drive * driving, 17.0),
                    boost=max(0, 33 - int(20.0 * driving)),
                ),
                velocity=Vec3(0.0, blue_speed, 0.0),
            ),
            replace(
                create_test_player(
                    "orange", 1, Vec3(0.0, 2048.0 - orange_drive * driving, 17.0)
                ),
                velocity=Vec3(0.0, -orange_speed, 0.0),
            ),
        ]

        if t >= contact:
            ball_pos = Vec3(0.0, ball_exit * (t - contact), 92.8)
            ball_vel = Vec3(0.0, ball_exit, 0.0)
        else:
            height, drop_speed = ball_drop.get(step, (92.8, 0.0))
            ball_pos = Vec3(0.0, 0.0, height)
            ball_vel = Vec3(0.0, 0.0, drop_speed)

        frame = create_test_frame(t, ball_pos, ball_vel, players)
        if step in (0, 4):
            marker = ParserKickoffMarker(timestamp=t, phase=phase)
            frame = replace(frame, parser_kickoff_markers=[marker])
        frames.append(frame)
    return frames


def with_flip(
    frames: list[Frame],
    player_id: str,
    at: float,
    torque: tuple[float, float],
    pitch_share: float = 1.0,
    rolls: bool = True,
) -> list[Frame]:
    """Give a car a dodge, then the spin real replays record after one.

    The car spins about ``torque`` at the flip rate. ``pitch_share`` is how much of
    the pitch survives, so a cancel is near 0. ``rolls=False`` is a dodge that lands
    before the car comes round, which keeps its roof up.
    """
    length = math.hypot(*torque)
    pitch_rate = pitch_share * 5.5 * torque[1] / length
    roll_rate = 5.5 * torque[0] / length if rolls else 0.0

    updated = []
    dodged = False
    for frame in frames:
        if frame.timestamp < at:
            updated.append(frame)
            continue
        angle = roll_rate * (frame.timestamp - at)
        spinning = replace(
            frame.get_player_by_id(player_id),
            rotation=Rotation(
                0.0,
                0.0,
                0.0,
                Quaternion(math.sin(angle / 2), 0.0, 0.0, math.cos(angle / 2)),
            ),
            angular_velocity=Vec3(
                roll_rate, pitch_rate * math.cos(angle), pitch_rate * math.sin(angle)
            ),
        )
        players = [
            spinning if car.player_id == player_id else car for car in frame.players
        ]
        events = frame.component_events
        if not dodged:
            dodged = True
            events = [
                ParserComponentEvent(
                    timestamp=frame.timestamp,
                    kind="dodge_torque",
                    component="dodge",
                    player_id=player_id,
                    vector=Vec3(torque[0], torque[1], 0.0),
                )
            ]
        updated.append(replace(frame, players=players, component_events=events))
    return updated


def with_teammate(
    frames: list[Frame],
    player_id: str,
    team: int,
    spawn: Vec3,
    drive: float = 0.0,
    release: float = 14.0,
) -> list[Frame]:
    """Add a car that holds its spawn for the countdown, then drives at the spot."""
    length = math.hypot(spawn.x, spawn.y)
    heading_x, heading_y = -spawn.x / length, -spawn.y / length

    updated = []
    for frame in frames:
        driving = max(0.0, frame.timestamp - release)
        speed = drive if driving else 0.0
        car = replace(
            create_test_player(
                player_id,
                team,
                Vec3(
                    spawn.x + heading_x * drive * driving,
                    spawn.y + heading_y * drive * driving,
                    spawn.z,
                ),
            ),
            velocity=Vec3(heading_x * speed, heading_y * speed, 0.0),
        )
        updated.append(replace(frame, players=[*frame.players, car]))
    return updated


def kickoff_row(kickoff: KickoffEvent, player_id: str) -> dict:
    """One car's row on a kickoff event."""
    return next(p for p in kickoff.players if p["player_id"] == player_id)


def open_play_frames(start: float, count: int = 30) -> list[Frame]:
    """Frames away from the spot with every car moving."""
    players = [
        replace(
            create_test_player(pid, team, Vec3(500.0, 1000.0, 17.0)),
            velocity=Vec3(1000.0, 0.0, 0.0),
        )
        for pid, team in (("blue", 0), ("orange", 1))
    ]
    return [
        create_test_frame(
            start + step * FRAME_STEP,
            Vec3(1500.0, 2500.0, 300.0),
            Vec3(800.0, 0.0, 0.0),
            players,
        )
        for step in range(count)
    ]


class TestGoalDetection:
    """Test goal event detection."""

    def test_empty_frames_returns_empty(self):
        """Empty frame list returns no goals."""
        goals = detect_goals([])
        assert goals == []

    def test_blue_team_goal(self):
        """Blue team scoring in orange goal (positive Y)."""
        # Ball approaching orange goal
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 4100.0, 100.0),  # In the field of play
                Vec3(0.0, 500.0, 0.0),  # Moving toward goal
                [
                    create_test_player("player_1", 0, Vec3(0.0, 4020.0, 17.0))
                ],  # Blue player near ball
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 4350.0, 100.0),  # Ball crosses goal line
                Vec3(0.0, 500.0, 0.0),
                [create_test_player("player_1", 0, Vec3(0.0, 4250.0, 17.0))],
            ),
        ]

        goals = detect_goals(frames)
        assert len(goals) == 1

        goal = goals[0]
        assert goal.t == 1.1
        assert goal.scorer == "player_1"
        assert goal.team == "BLUE"
        assert goal.shot_speed_kph > 0

    def test_orange_team_goal(self):
        """Orange team scoring in blue goal (negative Y)."""
        frames = [
            create_test_frame(
                2.0,
                Vec3(0.0, -4100.0, 100.0),  # In the field of play
                Vec3(0.0, -500.0, 0.0),  # Moving toward goal
                [
                    create_test_player("player_2", 1, Vec3(0.0, -4020.0, 17.0))
                ],  # Orange player near ball
            ),
            create_test_frame(
                2.1,
                Vec3(0.0, -4350.0, 100.0),  # Ball crosses goal line
                Vec3(0.0, -500.0, 0.0),
                [create_test_player("player_2", 1, Vec3(0.0, -4250.0, 17.0))],
            ),
        ]

        goals = detect_goals(frames)
        assert len(goals) == 1

        goal = goals[0]
        assert goal.team == "ORANGE"
        assert goal.scorer == "player_2"

    def test_no_recent_touch_no_scorer(self):
        """Goal without recent player touch has no scorer."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 5200.0, 100.0),  # Ball already past goal line
                Vec3(0.0, 100.0, 0.0),
                [],  # No players near ball
            )
        ]

        goals = detect_goals(frames)
        assert len(goals) == 1
        assert goals[0].scorer is None

    def test_ball_not_crossing_goal_line(self):
        """Ball staying in field doesn't trigger goal."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 4000.0, 100.0),  # Ball in field
                Vec3(0.0, 100.0, 0.0),
                [create_test_player("player_1", 0, Vec3(0.0, 3800.0, 17.0))],
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 4200.0, 100.0),  # Still in field (below threshold)
                Vec3(0.0, 100.0, 0.0),
                [create_test_player("player_1", 0, Vec3(0.0, 4000.0, 17.0))],
            ),
        ]

        goals = detect_goals(frames)
        assert goals == []

    def test_goal_emitted_once_until_ball_clears(self):
        """Ball lingering inside goal volume does not create duplicate events."""
        frames = [
            create_test_frame(
                0.0,
                Vec3(0.0, GOAL_LINE_THRESHOLD - 50.0, 100.0),
                Vec3(0.0, 500.0, 0.0),
                [
                    create_test_player(
                        "player_1", 0, Vec3(0.0, GOAL_LINE_THRESHOLD - 120.0, 17.0)
                    )
                ],
            ),
            create_test_frame(
                0.1,
                Vec3(0.0, GOAL_LINE_THRESHOLD + 120.0, 100.0),
                Vec3(0.0, 450.0, 0.0),
                [
                    create_test_player(
                        "player_1", 0, Vec3(0.0, GOAL_LINE_THRESHOLD - 20.0, 17.0)
                    )
                ],
            ),
            create_test_frame(
                0.2,
                Vec3(0.0, GOAL_LINE_THRESHOLD + 260.0, 105.0),
                Vec3(0.0, 100.0, 0.0),
                [
                    create_test_player(
                        "player_1", 0, Vec3(0.0, GOAL_LINE_THRESHOLD - 20.0, 17.0)
                    )
                ],
            ),
        ]

        goals = detect_goals(frames)
        assert len(goals) == 1

    def test_goal_requires_exit_before_retrigger(self):
        """Ball must leave the goal volume before another goal is recorded."""
        frames = [
            create_test_frame(
                0.0,
                Vec3(0.0, GOAL_LINE_THRESHOLD - 80.0, 100.0),
                Vec3(0.0, 400.0, 0.0),
                [
                    create_test_player(
                        "player_1", 0, Vec3(0.0, GOAL_LINE_THRESHOLD - 200.0, 17.0)
                    )
                ],
            ),
            create_test_frame(
                0.1,
                Vec3(0.0, GOAL_LINE_THRESHOLD + 150.0, 100.0),
                Vec3(0.0, 450.0, 0.0),
                [
                    create_test_player(
                        "player_1", 0, Vec3(0.0, GOAL_LINE_THRESHOLD - 40.0, 17.0)
                    )
                ],
            ),
            create_test_frame(
                0.2,
                Vec3(0.0, GOAL_LINE_THRESHOLD + 220.0, 110.0),
                Vec3(0.0, 50.0, 0.0),
                [
                    create_test_player(
                        "player_1", 0, Vec3(0.0, GOAL_LINE_THRESHOLD - 40.0, 17.0)
                    )
                ],
            ),
            create_test_frame(
                0.5,
                Vec3(0.0, GOAL_LINE_THRESHOLD - 400.0, 100.0),
                Vec3(0.0, -200.0, 0.0),
                [
                    create_test_player(
                        "player_1", 0, Vec3(0.0, GOAL_LINE_THRESHOLD - 420.0, 17.0)
                    )
                ],
            ),
            create_test_frame(
                0.6,
                Vec3(0.0, GOAL_LINE_THRESHOLD + 180.0, 100.0),
                Vec3(0.0, 450.0, 0.0),
                [
                    create_test_player(
                        "player_1", 0, Vec3(0.0, GOAL_LINE_THRESHOLD - 50.0, 17.0)
                    )
                ],
            ),
        ]

        goals = detect_goals(frames)
        assert len(goals) == 2


class TestDemoDetection:
    """Test demolition event detection."""

    def test_empty_frames_returns_empty(self):
        """Empty frame list returns no demos."""
        demos = detect_demos([])
        assert demos == []

    def test_player_gets_demolished(self):
        """Player state transition from alive to demolished."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "victim", 0, Vec3(1000.0, 0.0, 17.0), demolished=False
                    ),
                    create_test_player(
                        "attacker", 1, Vec3(1100.0, 0.0, 17.0), demolished=False
                    ),
                ],
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "victim", 0, Vec3(1000.0, 0.0, 17.0), demolished=True
                    ),
                    create_test_player(
                        "attacker", 1, Vec3(1050.0, 0.0, 17.0), demolished=False
                    ),
                ],
            ),
        ]

        demos = detect_demos(frames)
        assert len(demos) == 1

        demo = demos[0]
        assert demo.t == 1.1
        assert demo.victim == "victim"
        assert demo.attacker == "attacker"
        assert demo.team_victim == "BLUE"
        assert demo.team_attacker == "ORANGE"

    def test_no_demo_transition_no_event(self):
        """No state change means no demo event."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "player_1", 0, Vec3(1000.0, 0.0, 17.0), demolished=False
                    )
                ],
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "player_1", 0, Vec3(1100.0, 0.0, 17.0), demolished=False
                    )
                ],
            ),
        ]

        demos = detect_demos(frames)
        assert demos == []

    def test_demo_without_nearby_attacker(self):
        """Demo event with no clear attacker nearby."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "victim", 0, Vec3(1000.0, 0.0, 17.0), demolished=False
                    ),
                    create_test_player(
                        "far_player", 1, Vec3(3000.0, 0.0, 17.0), demolished=False
                    ),  # Too far
                ],
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "victim", 0, Vec3(1000.0, 0.0, 17.0), demolished=True
                    ),
                    create_test_player(
                        "far_player", 1, Vec3(3000.0, 0.0, 17.0), demolished=False
                    ),
                ],
            ),
        ]

        demos = detect_demos(frames)
        assert len(demos) == 1
        assert demos[0].attacker is None

    def test_parser_demo_events_dedupe_respawn_echoes(self):
        """Parser demo variants for the same victim/location count once."""
        victim_position = Vec3(1000.0, 500.0, 17.0)
        frames = []
        for timestamp in (10.0, 11.7):
            frame = create_test_frame(
                timestamp,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("victim", 0, victim_position, demolished=True),
                    create_test_player("attacker", 1, Vec3(1050.0, 500.0, 17.0)),
                ],
            )
            frame.parser_demo_events.append(
                ParserDemoEvent(
                    timestamp=timestamp,
                    victim_id="victim",
                    attacker_id="attacker",
                    victim_team=0,
                    attacker_team=1,
                    frame_index=int(timestamp * 30),
                )
            )
            frames.append(frame)

        demos = detect_demos(frames)

        assert len(demos) == 1
        assert demos[0].t == 10.0
        assert demos[0].victim == "victim"
        assert demos[0].attacker == "attacker"


class TestKickoffDetection:
    """Test kickoff event detection."""

    def test_empty_frames_returns_empty(self):
        """Empty frame list returns no kickoffs."""
        kickoffs = detect_kickoffs([])
        assert kickoffs == []

    def test_initial_kickoff_detected(self):
        """Ball at center triggers kickoff detection."""
        frames = [
            create_test_frame(
                0.0,
                Vec3(0.0, 0.0, 93.15),  # Ball at center
                Vec3(0.0, 0.0, 0.0),  # Stationary
                [
                    create_test_player(
                        "p1", 0, Vec3(-500.0, -1000.0, 17.0)
                    ),  # Blue side
                    create_test_player(
                        "p2", 1, Vec3(500.0, 1000.0, 17.0)
                    ),  # Orange side
                ],
            ),
            create_test_frame(
                0.5,
                Vec3(0.0, 0.0, 93.15),  # Still at center
                Vec3(0.0, 0.0, 0.0),  # Still stationary
                [
                    create_test_player("p1", 0, Vec3(-200.0, -800.0, 17.0)),
                    create_test_player("p2", 1, Vec3(200.0, 800.0, 17.0)),
                ],
            ),
            create_test_frame(
                1.0,
                Vec3(100.0, 200.0, 100.0),  # Ball moves away
                Vec3(200.0, 400.0, 50.0),  # Ball has velocity
                [
                    create_test_player("p1", 0, Vec3(50.0, -50.0, 17.0)),
                    create_test_player("p2", 1, Vec3(150.0, 150.0, 17.0)),
                ],
            ),
        ]

        kickoffs = detect_kickoffs(frames)
        assert len(kickoffs) == 1

        kickoff = kickoffs[0]
        assert kickoff.phase == "INITIAL"
        assert kickoff.t_start == 0.0
        assert len(kickoff.players) == 2

    def test_overtime_kickoff(self):
        """Late-game kickoff detected as overtime."""
        frames = [
            create_test_frame(
                350.0,  # Late in match
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(-200.0, -200.0, 17.0))],
            ),
            create_test_frame(
                351.0,
                Vec3(200.0, 300.0, 150.0),  # Ball moves
                Vec3(400.0, 600.0, 100.0),
                [create_test_player("p1", 0, Vec3(100.0, 100.0, 17.0))],
            ),
        ]

        kickoffs = detect_kickoffs(frames)
        assert len(kickoffs) == 1
        assert kickoffs[0].phase == "OT"

    def test_ball_not_at_center_no_kickoff(self):
        """Ball away from center doesn't trigger kickoff."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(1000.0, 2000.0, 100.0),  # Ball away from center
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(500.0, 1000.0, 17.0))],
            )
        ]

        kickoffs = detect_kickoffs(frames)
        assert kickoffs == []


class TestKickoffCountdown:
    """Kickoffs on frames shaped like real replays, with a countdown."""

    def test_one_event_per_kickoff(self):
        """Two markers, a settling ball and a countdown are still one kickoff."""
        kickoffs = detect_kickoffs(countdown_frames(10.0))

        assert len(kickoffs) == 1
        kickoff = kickoffs[0]
        assert kickoff.source == "parser"
        assert kickoff.t_start == pytest.approx(14.0, abs=2 * FRAME_STEP)
        assert kickoff.outcome == "FIRST_POSSESSION_BLUE"
        assert kickoff.first_touch_player == "blue"

    def test_one_event_without_parser_markers(self):
        """Gameplay state alone doesn't split a kickoff either."""
        frames = [
            replace(frame, parser_kickoff_markers=[])
            for frame in countdown_frames(10.0)
        ]

        kickoffs = detect_kickoffs(frames)

        assert len(kickoffs) == 1
        assert kickoffs[0].source == "inferred"

    def test_times_count_from_release(self):
        """The approach is timed from the release, not the ball reset."""
        kickoff = detect_kickoffs(countdown_frames(10.0))[0]

        assert kickoff.time_to_first_touch == pytest.approx(2.05, abs=0.1)
        blue = next(p for p in kickoff.players if p["player_id"] == "blue")
        assert blue["boost_used"] == 33
        assert blue["time_to_first_touch"] == pytest.approx(2.05, abs=0.1)

    def test_opening_kickoff_reaches_first_touch(self):
        """The contact 6s into a replay falls inside the kickoff window."""
        kickoffs = detect_kickoffs(countdown_frames(0.0))

        assert len(kickoffs) == 1
        assert kickoffs[0].first_touch_player == "blue"

    def test_each_kickoff_counts_once(self):
        frames = countdown_frames(0.0) + open_play_frames(7.0) + countdown_frames(30.0)

        kickoffs = detect_kickoffs(frames)

        assert [round(kickoff.t_start) for kickoff in kickoffs] == [4, 34]
        assert all(kickoff.first_touch_player == "blue" for kickoff in kickoffs)

    def test_placeholder_frame_is_not_a_kickoff(self):
        """With no ball, the parser reports a default ball on an empty frame."""
        marker = ParserKickoffMarker(timestamp=8.0, phase="INITIAL")
        placeholder = replace(
            create_test_frame(8.0, Vec3(0.0, 0.0, 93.15), Vec3(0.0, 0.0, 0.0), []),
            parser_kickoff_markers=[marker],
        )
        frames = (
            countdown_frames(0.0)
            + open_play_frames(7.0, count=15)
            + [placeholder]
            + open_play_frames(8.1)
        )

        kickoffs = detect_kickoffs(frames)

        assert len(kickoffs) == 1
        assert kickoffs[0].t_start == pytest.approx(4.0, abs=2 * FRAME_STEP)

    def test_twitch_during_countdown_keeps_the_release(self):
        """One car jostling mid-countdown doesn't release the others."""

        def twitch(frame: Frame) -> Frame:
            if not 13.4 <= frame.timestamp <= 13.9:
                return frame
            jostled = replace(frame.players[0], velocity=Vec3(0.0, 97.0, 0.0))
            return replace(frame, players=[jostled, frame.players[1]])

        frames = [twitch(frame) for frame in countdown_frames(10.0)]

        kickoffs = detect_kickoffs(frames)

        assert len(kickoffs) == 1
        assert kickoffs[0].t_start == pytest.approx(14.0, abs=2 * FRAME_STEP)

    def test_contact_is_found_with_the_car_still_out_of_touch_range(self):
        """Positions refresh every few frames, so a car often reads 230uu out."""
        kickoff = detect_kickoffs(countdown_frames(10.0, blue_drive=872.0))[0]

        assert kickoff.first_touch_player == "blue"
        assert kickoff.outcome == "FIRST_POSSESSION_BLUE"
        assert kickoff.time_to_first_touch == pytest.approx(2.1, abs=2 * FRAME_STEP)

    def test_ball_direction_decides_a_fifty_fifty(self):
        """Both cars are level, and the ball leaves away from the one that won it."""
        level = {"blue_drive": 900.0, "orange_drive": 900.0}

        to_orange_side = countdown_frames(10.0, ball_exit=1500.0, **level)
        to_blue_side = countdown_frames(10.0, ball_exit=-1500.0, **level)

        assert detect_kickoffs(to_orange_side)[0].first_touch_player == "blue"
        assert detect_kickoffs(to_blue_side)[0].first_touch_player == "orange"

    def test_challenger_in_reach_is_not_a_fake(self):
        """Losing the ball by a car length still counts as contesting it."""
        frames = countdown_frames(10.0, orange_drive=830.0)

        kickoff = detect_kickoffs(frames)[0]

        orange = next(p for p in kickoff.players if p["player_id"] == "orange")
        assert kickoff.first_touch_player == "blue"
        assert orange["time_to_first_touch"] == pytest.approx(2.1, abs=2 * FRAME_STEP)
        assert not orange["approach_type"].startswith("FAKE")

    def test_car_out_of_reach_is_not_contesting(self):
        kickoff = detect_kickoffs(countdown_frames(10.0, orange_drive=500.0))[0]

        orange = next(p for p in kickoff.players if p["player_id"] == "orange")
        assert orange["time_to_first_touch"] is None

    def test_hoops_launch_is_not_a_touch(self):
        """Hoops throws the ball straight up at the release, with no car near it."""
        frames = []
        for frame in countdown_frames(10.0):
            if 14.2 <= frame.timestamp < 16.1:
                launched = replace(
                    frame.ball,
                    position=Vec3(0.0, 0.0, 300.0),
                    velocity=Vec3(0.0, 0.0, 900.0),
                )
                frame = replace(frame, ball=launched)
            frames.append(frame)

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff.first_touch_player == "blue"
        assert kickoff.time_to_first_touch == pytest.approx(2.1, abs=2 * FRAME_STEP)

    def test_kickoff_nobody_plays_stays_neutral(self):
        """The cars stop short, so the ball never moves before the replay ends."""
        frames = countdown_frames(
            10.0, blue_drive=300.0, orange_drive=300.0, ball_exit=0.0
        )

        kickoffs = detect_kickoffs(frames)

        assert len(kickoffs) == 1
        assert kickoffs[0].t_start == pytest.approx(14.0, abs=2 * FRAME_STEP)
        assert kickoffs[0].outcome == "NEUTRAL"
        assert kickoffs[0].first_touch_player is None

    def test_parser_phase_applies_to_the_kickoff(self):
        kickoffs = detect_kickoffs(countdown_frames(310.0, phase="OT"))

        assert len(kickoffs) == 1
        assert kickoffs[0].phase == "OT"
        assert kickoffs[0].t_start == pytest.approx(314.0, abs=2 * FRAME_STEP)

    def test_real_replay_has_one_kickoff_per_countdown(self):
        """Expected times are the stream's own countdown reaching zero."""
        rlreplay_rust = pytest.importorskip("rlreplay_rust")
        if not getattr(rlreplay_rust, "RUST_CORE", False):
            pytest.skip("Rust core not available")
        replay = Path("Replay_files/testing_replay.replay")
        if not replay.exists():
            pytest.skip("testing_replay.replay not found")

        adapter = get_adapter("rust")
        header = adapter.parse_header(replay)
        network = adapter.parse_network(replay)
        frames = build_normalized_frames(header, network.frames)

        kickoffs = detect_kickoffs(frames, header)

        released = [4.02, 28.97, 53.28, 82.44, 110.79, 250.21, 289.87, 341.90]
        released += [398.72, 428.54]
        assert [kickoff.t_start for kickoff in kickoffs] == pytest.approx(
            released, abs=0.1
        )
        # The stream's bBallHasBeenHit, measured from each release.
        played = [2.17, 1.9, 1.9, 1.93, 2.17, 2.2, 1.94, 1.91, 1.91, 2.21]
        assert [kickoff.time_to_first_touch for kickoff in kickoffs] == pytest.approx(
            played, abs=0.15
        )


class TestKickoffApproach:
    """How each car played the kickoff, on frames shaped like real replays."""

    def test_cancelled_forward_dodge_is_a_speedflip(self):
        frames = with_flip(
            countdown_frames(10.0),
            "blue",
            at=14.5,
            torque=(1.84, 1.58),
            pitch_share=0.1,
        )

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "blue")["approach_type"] == "SPEEDFLIP"

    def test_completed_flip_is_not_a_speedflip(self):
        """The same dodge with its pitch left in is an ordinary diagonal flip."""
        frames = with_flip(countdown_frames(10.0), "blue", at=14.5, torque=(1.84, 1.58))

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "blue")["approach_type"] == "STANDARD_DIAGONAL"

    def test_dodge_that_lands_is_not_a_speedflip(self):
        """A wavedash shows no pitch either, but its roof never comes round."""
        frames = with_flip(
            countdown_frames(10.0),
            "blue",
            at=14.5,
            torque=(0.54, 2.19),
            pitch_share=0.1,
            rolls=False,
        )

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "blue")["approach_type"] == "STANDARD_FRONTFLIP"

    def test_side_dodge_has_no_pitch_to_cancel(self):
        frames = with_flip(countdown_frames(10.0), "blue", at=14.5, torque=(2.6, 0.0))

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "blue")["approach_type"] == "STANDARD_DIAGONAL"

    def test_flip_into_the_ball_is_not_a_speedflip(self):
        """Contact ends the spin too soon after the dodge to judge a cancel."""
        frames = with_flip(
            countdown_frames(10.0),
            "blue",
            at=15.9,
            torque=(1.84, 1.58),
            pitch_share=0.1,
        )

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "blue")["approach_type"] == "STANDARD_DIAGONAL"

    def test_fast_car_that_only_jumped_is_not_a_speedflip(self):
        """Every car meets the ball at about 2.1s, so speed and timing prove nothing."""
        frames = []
        for frame in countdown_frames(10.0):
            if frame.timestamp > 15.0:
                blue = replace(
                    frame.get_player_by_id("blue"),
                    velocity=Vec3(0.0, 2200.0, 0.0),
                    is_on_ground=False,
                )
                position = blue.position
                blue = replace(blue, position=Vec3(position.x, position.y, 60.0))
                frame = replace(frame, players=[blue, frame.players[1]])
            frames.append(frame)

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "blue")["approach_type"] == "STANDARD_BOOST"

    @pytest.mark.parametrize(
        ("torque", "expected"),
        [
            ((0.0, 2.24), "STANDARD_FRONTFLIP"),
            ((0.4, 2.2), "STANDARD_FRONTFLIP"),
            ((1.84, 1.58), "STANDARD_DIAGONAL"),
            ((2.6, 0.0), "STANDARD_DIAGONAL"),
        ],
    )
    def test_flip_type_comes_from_the_dodge_direction(self, torque, expected):
        frames = with_flip(countdown_frames(10.0), "blue", at=15.9, torque=torque)

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "blue")["approach_type"] == expected

    def test_first_dodge_names_the_flip(self):
        """A car that flipped early and again into the ball flipped diagonally."""
        frames = with_flip(countdown_frames(10.0), "blue", at=14.5, torque=(1.84, 1.58))
        frames = with_flip(frames, "blue", at=15.9, torque=(0.0, 2.24))

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "blue")["approach_type"] == "STANDARD_DIAGONAL"

    def test_flip_after_contact_is_ignored(self):
        frames = with_flip(countdown_frames(10.0), "blue", at=16.2, torque=(0.0, 2.24))

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "blue")["approach_type"] == "STANDARD_BOOST"

    def test_back_car_that_stays_is_holding_not_faking(self):
        frames = with_teammate(countdown_frames(10.0), "back", 0, Vec3(0, -4608, 17))

        row = kickoff_row(detect_kickoffs(frames)[0], "back")

        assert row["role"] == "BACK"
        assert row["approach_type"] == "SUPPORT_HOLD"

    def test_back_car_moving_up_is_cheating(self):
        frames = with_teammate(
            countdown_frames(10.0), "back", 0, Vec3(256, -3840, 17), drive=1000.0
        )

        row = kickoff_row(detect_kickoffs(frames)[0], "back")

        assert row["role"] == "BACK"
        assert row["approach_type"] == "SUPPORT_CHEAT"

    def test_small_move_is_still_holding(self):
        frames = with_teammate(
            countdown_frames(10.0), "back", 0, Vec3(256, -3840, 17), drive=300.0
        )

        row = kickoff_row(detect_kickoffs(frames)[0], "back")

        assert row["approach_type"] == "SUPPORT_HOLD"

    def test_wing_leaving_the_ball_is_support(self):
        frames = with_teammate(countdown_frames(10.0), "wing", 0, Vec3(2048, -2560, 17))

        row = kickoff_row(detect_kickoffs(frames)[0], "wing")

        assert row["role"] == "WING"
        assert row["approach_type"] == "SUPPORT_HOLD"

    def test_support_car_in_reach_reports_how_it_got_there(self):
        frames = with_teammate(
            countdown_frames(10.0), "back", 0, Vec3(256, -3840, 17), drive=1700.0
        )
        frames = with_flip(frames, "back", at=14.5, torque=(1.84, 1.58))

        row = kickoff_row(detect_kickoffs(frames)[0], "back")

        assert row["role"] == "BACK"
        assert row["approach_type"] == "STANDARD_DIAGONAL"

    def test_support_car_closing_on_the_ball_is_not_contesting_it(self):
        """Cars cheating up pass through this range all the time."""
        frames = with_teammate(
            countdown_frames(10.0), "back", 0, Vec3(256, -3840, 17), drive=1500.0
        )

        row = kickoff_row(detect_kickoffs(frames)[0], "back")

        assert row["approach_type"] == "SUPPORT_CHEAT"

    def test_go_car_beaten_to_the_ball_is_not_a_fake(self):
        """Still 600uu out and closing, it lost the race instead of declining it."""
        kickoff = detect_kickoffs(countdown_frames(10.0, orange_drive=700.0))[0]

        orange = kickoff_row(kickoff, "orange")
        assert orange["time_to_first_touch"] is None
        assert not orange["approach_type"].startswith("FAKE")

    def test_go_car_that_never_goes_is_a_stationary_fake(self):
        kickoff = detect_kickoffs(countdown_frames(10.0, orange_drive=0.0))[0]

        assert kickoff_row(kickoff, "orange")["approach_type"] == "FAKE_STATIONARY"

    def test_go_car_too_far_out_is_a_fake(self):
        kickoff = detect_kickoffs(countdown_frames(10.0, orange_drive=500.0))[0]

        assert kickoff_row(kickoff, "orange")["approach_type"] == "FAKE_AGGRESSIVE"

    def test_go_car_driving_away_is_a_fake(self):
        kickoff = detect_kickoffs(countdown_frames(10.0, orange_drive=-500.0))[0]

        assert kickoff_row(kickoff, "orange")["approach_type"] == "FAKE_AGGRESSIVE"

    def test_go_car_flipping_backward_is_a_halfflip_fake(self):
        frames = with_flip(
            countdown_frames(10.0, orange_drive=-500.0),
            "orange",
            at=14.5,
            torque=(0.16, -2.24),
        )

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "orange")["approach_type"] == "FAKE_HALFFLIP"

    def test_level_spawns_give_go_to_the_car_that_went(self):
        """Spawn order can't say who goes when a team's cars start level."""
        frames = with_teammate(
            countdown_frames(10.0, blue_drive=0.0),
            "mate",
            0,
            Vec3(-2048, 0, 17),
            drive=900.0,
        )

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "mate")["role"] == "GO"
        blue = kickoff_row(kickoff, "blue")
        assert blue["role"] == "WING"
        assert blue["approach_type"] == "SUPPORT_HOLD"

    def test_level_spawns_keep_go_when_it_went(self):
        frames = with_teammate(countdown_frames(10.0), "mate", 0, Vec3(-2048, 0, 17))

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "blue")["role"] == "GO"
        assert kickoff_row(kickoff, "mate")["role"] == "WING"

    def test_spawn_further_back_never_takes_go(self):
        """Only level spawns are the team's choice; the nearer car is still GO."""
        frames = with_teammate(
            countdown_frames(10.0, blue_drive=0.0),
            "back",
            0,
            Vec3(256, -3840, 17),
            drive=1800.0,
        )

        kickoff = detect_kickoffs(frames)[0]

        assert kickoff_row(kickoff, "blue")["role"] == "GO"
        assert kickoff_row(kickoff, "back")["role"] == "BACK"

    def test_frames_without_rotation_data_never_read_as_speedflip(self):
        """A dodge alone isn't a speedflip; the spin after it has to show the cancel."""
        frames = with_flip(countdown_frames(10.0), "blue", at=14.5, torque=(1.84, 1.58))
        stripped = []
        for frame in frames:
            players = [
                replace(car, rotation=Vec3(0.0, 0.0, 0.0), angular_velocity=None)
                for car in frame.players
            ]
            stripped.append(replace(frame, players=players))

        kickoff = detect_kickoffs(stripped)[0]

        assert kickoff_row(kickoff, "blue")["approach_type"] == "STANDARD_DIAGONAL"

    def test_real_replay_approaches(self):
        """Every GO car in this game speedflips, and every other car cheats up."""
        rlreplay_rust = pytest.importorskip("rlreplay_rust")
        if not getattr(rlreplay_rust, "RUST_CORE", False):
            pytest.skip("Rust core not available")
        replay = Path("Replay_files/testing_replay.replay")
        if not replay.exists():
            pytest.skip("testing_replay.replay not found")

        adapter = get_adapter("rust")
        header = adapter.parse_header(replay)
        network = adapter.parse_network(replay)
        frames = build_normalized_frames(header, network.frames)

        kickoffs = detect_kickoffs(frames, header)

        rows = [row for kickoff in kickoffs for row in kickoff.players]
        goers = [row for row in rows if row["role"] == "GO"]
        others = [row for row in rows if row["role"] != "GO"]
        assert len(goers) == 20
        assert {row["approach_type"] for row in goers} == {"SPEEDFLIP"}
        assert {row["approach_type"] for row in others} == {"SUPPORT_CHEAT"}


class TestBoostPickupDetection:
    """Test boost pickup event detection."""

    def test_empty_frames_returns_empty(self):
        """Empty frame list returns no pickups."""
        pickups = detect_boost_pickups([])
        assert pickups == []

    def test_big_boost_pickup(self):
        """Large boost increase detected as big pad pickup."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("p1", 0, Vec3(-3584.0, -4096.0, 17.0), boost=20)
                ],  # Corner boost
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("p1", 0, Vec3(-3584.0, -4096.0, 17.0), boost=100)
                ],  # Got 100 boost
            ),
        ]

        pickups = detect_boost_pickups(frames)
        assert len(pickups) == 1

        pickup = pickups[0]
        assert pickup.t == 1.1
        assert pickup.player_id == "p1"
        assert pickup.pad_type == "BIG"
        assert pickup.stolen is False  # Blue player in blue corner
        assert pickup.pad_id == 0

    def test_small_boost_pickup(self):
        """Small boost increase detected as small pad pickup."""
        frames = [
            create_test_frame(
                2.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("p1", 0, Vec3(0.0, -2816.0, 17.0), boost=50)
                ],  # Centre small pad
            ),
            create_test_frame(
                2.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("p1", 0, Vec3(0.0, -2816.0, 17.0), boost=62)
                ],  # Got 12 boost
            ),
        ]

        pickups = detect_boost_pickups(frames)
        assert len(pickups) == 1

        pickup = pickups[0]
        assert pickup.pad_type == "SMALL"
        assert pickup.pad_id == 11

    def test_small_pad_preferred_over_big_for_small_gain(self):
        """Ensure nearby small pad is chosen over distant big pad for small gains."""
        pad_small = FIELD.BOOST_PADS[27]  # (3584, 2484)
        pos = Vec3(
            pad_small.position.x, pad_small.position.y - 134.0, 17.0
        )  # Within radius
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, pos, boost=60)],
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, pos, boost=66)],
            ),
        ]

        pickups = detect_boost_pickups(frames)
        assert len(pickups) == 1
        pickup = pickups[0]
        assert pickup.pad_type == "SMALL"
        assert pickup.pad_id == pad_small.pad_id

    def test_stolen_boost_detection(self):
        """Boost pickup on opponent half detected as stolen."""
        frames = [
            create_test_frame(
                3.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "blue_p", 0, Vec3(3584.0, 4096.0, 17.0), boost=10
                    )
                ],  # Blue in orange corner
            ),
            create_test_frame(
                3.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "blue_p", 0, Vec3(3584.0, 4096.0, 17.0), boost=100
                    )
                ],  # Boost stolen
            ),
        ]

        pickups = detect_boost_pickups(frames)
        assert len(pickups) == 1
        assert pickups[0].stolen is True
        assert pickups[0].pad_id == 3

    def test_far_legacy_pad_match_does_not_count_as_stolen(self):
        """Low-confidence boost jumps should not inflate stolen boost."""
        frames = [
            create_test_frame(
                3.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("blue_p", 0, Vec3(-3350.0, 50.0, 17.0), boost=7)],
            ),
            create_test_frame(
                3.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("blue_p", 0, Vec3(-3350.0, 50.0, 17.0), boost=100)],
            ),
        ]

        pickups = detect_boost_pickups(frames)
        assert len(pickups) == 1
        assert pickups[0].pad_type == "BIG"
        assert pickups[0].stolen is False

    def test_center_pad_not_stolen(self):
        """Pads on the midfield line should not be marked stolen."""
        pad_center = FIELD.BOOST_PADS[19]  # Midfield small pad
        frames = [
            create_test_frame(
                5.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "blue_mid",
                        0,
                        Vec3(pad_center.position.x, pad_center.position.y, 17.0),
                        boost=20,
                    )
                ],
            ),
            create_test_frame(
                5.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "blue_mid",
                        0,
                        Vec3(pad_center.position.x, pad_center.position.y, 17.0),
                        boost=32,
                    )
                ],
            ),
        ]

        pickups = detect_boost_pickups(frames)
        assert len(pickups) == 1
        assert pickups[0].stolen is False
        assert pickups[0].pad_id == pad_center.pad_id

    def test_no_boost_increase_no_pickup(self):
        """No boost change means no pickup event."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(1000.0, 0.0, 17.0), boost=50)],
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("p1", 0, Vec3(1100.0, 0.0, 17.0), boost=50)
                ],  # Same boost
            ),
        ]

        pickups = detect_boost_pickups(frames)
        assert pickups == []

    def test_all_boost_pads_match(self):
        """Every canonical boost pad resolves to a concrete pad id."""
        for pad in FIELD.BOOST_PADS:
            base_boost = 0 if pad.is_big else 20
            delta = 100 if pad.is_big else 12
            frames = [
                create_test_frame(
                    pad.pad_id,
                    Vec3(0.0, 0.0, 93.15),
                    Vec3(0.0, 0.0, 0.0),
                    [
                        create_test_player(
                            f"player_{pad.pad_id}",
                            0,
                            Vec3(pad.position.x, pad.position.y, 17.0),
                            boost=base_boost,
                        )
                    ],
                ),
                create_test_frame(
                    pad.pad_id + 0.1,
                    Vec3(0.0, 0.0, 93.15),
                    Vec3(0.0, 0.0, 0.0),
                    [
                        create_test_player(
                            f"player_{pad.pad_id}",
                            0,
                            Vec3(pad.position.x, pad.position.y, 17.0),
                            boost=base_boost + delta,
                        )
                    ],
                ),
            ]

            pickups = detect_boost_pickups(frames)
            assert len(pickups) == 1
            event = pickups[0]
            assert event.pad_id == pad.pad_id
            assert event.location == pad.position

    def test_small_pad_respawn_allows_recollection(self):
        """Small pads should allow recollection once respawn timer elapses."""
        pad = FIELD.BOOST_PADS[27]
        frames = [
            create_test_frame(
                0.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "player",
                        0,
                        Vec3(pad.position.x, pad.position.y, 17.0),
                        boost=20,
                    )
                ],
            ),
            create_test_frame(
                0.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "player",
                        0,
                        Vec3(pad.position.x, pad.position.y, 17.0),
                        boost=32,
                    )
                ],
            ),
            create_test_frame(
                4.2,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "player",
                        0,
                        Vec3(pad.position.x, pad.position.y, 17.0),
                        boost=32,
                    )
                ],
            ),
            create_test_frame(
                4.3,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "player",
                        0,
                        Vec3(pad.position.x, pad.position.y, 17.0),
                        boost=44,
                    )
                ],
            ),
        ]

        pickups = detect_boost_pickups(frames)
        assert len(pickups) == 2
        assert all(event.pad_id == pad.pad_id for event in pickups)

    def test_big_pad_requires_full_respawn(self):
        """Big pads should not be reassigned before their respawn window."""
        pad = FIELD.BOOST_PADS[0]
        frames = [
            create_test_frame(
                0.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "player", 0, Vec3(pad.position.x, pad.position.y, 17.0), boost=0
                    )
                ],
            ),
            create_test_frame(
                0.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "player",
                        0,
                        Vec3(pad.position.x, pad.position.y, 17.0),
                        boost=100,
                    )
                ],
            ),
            create_test_frame(
                5.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "player",
                        0,
                        Vec3(pad.position.x, pad.position.y, 17.0),
                        boost=100,
                    )
                ],
            ),
            create_test_frame(
                5.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "player",
                        0,
                        Vec3(pad.position.x, pad.position.y, 17.0),
                        boost=100,
                    )
                ],
            ),
        ]

        pickups = detect_boost_pickups(frames)
        assert len(pickups) == 1


class TestTouchDetection:
    """Test player-ball touch detection."""

    def test_empty_frames_returns_empty(self):
        """Empty frame list returns no touches."""
        touches = detect_touches([])
        assert touches == []

    def test_player_near_ball_creates_touch(self):
        """Player within proximity threshold creates touch event."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(1000.0, 2000.0, 100.0),  # Ball position
                Vec3(500.0, 0.0, 0.0),  # Ball moving
                [
                    create_test_player("p1", 0, Vec3(1100.0, 2000.0, 17.0))
                ],  # Player near ball
            )
        ]

        touches = detect_touches(frames)
        assert len(touches) == 1

        touch = touches[0]
        assert touch.t == 1.0
        assert touch.player_id == "p1"
        assert touch.ball_speed_kph > 0

    def test_high_speed_classified_as_shot(self):
        """High ball speed classified as shot."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(1000.0, 2000.0, 100.0),
                Vec3(2000.0, 0.0, 0.0),  # High speed
                [create_test_player("p1", 0, Vec3(1100.0, 2000.0, 17.0))],
            )
        ]

        touches = detect_touches(frames)
        assert len(touches) == 1
        assert touches[0].outcome == "SHOT"

    def test_low_speed_classified_as_dribble(self):
        """Low ball speed classified as dribble."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(1000.0, 2000.0, 100.0),
                Vec3(100.0, 0.0, 0.0),  # Low speed
                [create_test_player("p1", 0, Vec3(1100.0, 2000.0, 17.0))],
            )
        ]

        touches = detect_touches(frames)
        assert len(touches) == 1
        assert touches[0].outcome == "DRIBBLE"

    def test_save_flagged_with_clear_outcome(self):
        """Touch that stops shot toward own net is flagged as save."""
        frames = [
            create_test_frame(
                0.0, Vec3(0.0, -3000.0, 100.0), Vec3(0.0, -1200.0, 0.0), []
            ),
            create_test_frame(
                0.2,
                Vec3(0.0, -2500.0, 100.0),
                Vec3(0.0, 800.0, 0.0),
                [create_test_player("p_blue", 0, Vec3(50.0, -2500.0, 17.0))],
            ),
        ]

        touches = detect_touches(frames)
        assert len(touches) == 1
        assert touches[0].outcome == "CLEAR"
        assert touches[0].is_save is True

    def test_player_far_from_ball_no_touch(self):
        """Player far from ball doesn't create touch event."""
        frames = [
            create_test_frame(
                1.0,
                Vec3(1000.0, 2000.0, 100.0),  # Ball position
                Vec3(500.0, 0.0, 0.0),
                [
                    create_test_player("p1", 0, Vec3(2000.0, 3000.0, 17.0))
                ],  # Player far away
            )
        ]

        touches = detect_touches(frames)
        assert touches == []

    def test_touch_debounced_for_repeated_contacts(self):
        """Repeated frames at the same spot with low speed collapse to one touch."""
        frames = [
            create_test_frame(
                0.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(50.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(10.0, 0.0, 17.0))],
            ),
            create_test_frame(
                0.05,
                Vec3(0.0, 0.0, 93.15),
                Vec3(40.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(10.0, 0.0, 17.0))],
            ),
            create_test_frame(
                0.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(30.0, 0.0, 0.0),
                [create_test_player("p1", 0, Vec3(10.0, 0.0, 17.0))],
            ),
        ]

        touches = detect_touches(frames)
        assert len(touches) == 1


class TestChallengeDetection:
    """Test detection of 50/50 challenge events."""

    def test_basic_challenge_detection(self):
        """Opposing sequential touches produce a challenge event."""
        frames = [
            create_test_frame(
                0.0,
                Vec3(0.0, -200.0, 93.15),
                Vec3(0.0, 900.0, 0.0),
                [
                    create_test_player("blue", 0, Vec3(0.0, -210.0, 17.0)),
                    create_test_player("orange", 1, Vec3(300.0, 200.0, 17.0)),
                ],
            ),
            create_test_frame(
                0.25,
                Vec3(0.0, 60.0, 93.15),
                Vec3(0.0, 960.0, 0.0),
                [
                    create_test_player("blue", 0, Vec3(0.0, 50.0, 17.0)),
                    create_test_player("orange", 1, Vec3(10.0, 80.0, 17.0)),
                ],
            ),
            create_test_frame(
                0.6,
                Vec3(0.0, 320.0, 93.15),
                Vec3(0.0, 1000.0, 0.0),
                [
                    create_test_player("blue", 0, Vec3(-200.0, 100.0, 17.0)),
                    create_test_player("orange", 1, Vec3(0.0, 330.0, 17.0)),
                ],
            ),
        ]

        touches = [
            TouchEvent(
                t=0.0,
                player_id="blue",
                location=Vec3(0.0, -200.0, 17.0),
                ball_speed_kph=80.0,
            ),
            TouchEvent(
                t=0.4,
                player_id="orange",
                location=Vec3(0.0, 40.0, 17.0),
                ball_speed_kph=85.0,
            ),
        ]
        challenges = detect_challenge_events(frames, touches)
        assert len(challenges) == 1

        challenge = challenges[0]
        assert challenge.first_player == "blue"
        assert challenge.second_player == "orange"
        assert challenge.first_team == "BLUE"
        assert challenge.second_team == "ORANGE"
        assert 0.0 <= challenge.risk_first <= 1.0
        assert 0.0 <= challenge.risk_second <= 1.0

    def test_neutral_challenge_with_immediate_retouch(self):
        """Third touch quickly after contest marks the challenge neutral."""
        frames = [
            create_test_frame(
                0.0,
                Vec3(0.0, -120.0, 93.15),
                Vec3(0.0, 900.0, 0.0),
                [
                    create_test_player("blue", 0, Vec3(0.0, -130.0, 17.0)),
                    create_test_player("orange", 1, Vec3(0.0, 110.0, 17.0)),
                ],
            ),
            create_test_frame(
                0.2,
                Vec3(0.0, 80.0, 93.15),
                Vec3(0.0, 960.0, 0.0),
                [
                    create_test_player("blue", 0, Vec3(0.0, 70.0, 17.0)),
                    create_test_player("orange", 1, Vec3(0.0, 90.0, 17.0)),
                ],
            ),
            create_test_frame(
                0.35,
                Vec3(0.0, 60.0, 93.15),
                Vec3(0.0, -300.0, 0.0),
                [
                    create_test_player("blue", 0, Vec3(0.0, 55.0, 17.0)),
                    create_test_player("orange", 1, Vec3(0.0, 65.0, 17.0)),
                ],
            ),
        ]

        touches = [
            TouchEvent(
                t=0.0,
                player_id="blue",
                location=Vec3(0.0, -280.0, 17.0),
                ball_speed_kph=82.0,
            ),
            TouchEvent(
                t=0.2,
                player_id="orange",
                location=Vec3(0.0, 40.0, 17.0),
                ball_speed_kph=95.0,
            ),
            TouchEvent(
                t=0.3,
                player_id="blue",
                location=Vec3(0.0, 35.0, 17.0),
                ball_speed_kph=90.0,
            ),
        ]
        challenges = detect_challenge_events(frames, touches)
        assert len(challenges) >= 1
        assert any(ch.outcome == "NEUTRAL" for ch in challenges)


class TestTimelineAggregation:
    """Test timeline building from events."""

    def test_empty_events_returns_empty_timeline(self):
        """Empty events dict returns empty timeline."""
        timeline = build_timeline({})
        assert timeline == []

    def test_mixed_events_sorted_chronologically(self):
        """Mixed event types sorted by timestamp."""
        goal = GoalEvent(t=2.0, scorer="p1", team="BLUE")
        demo = DemoEvent(t=1.0, victim="p2", attacker="p1")
        touch = TouchEvent(t=3.0, player_id="p1", location=Vec3(0.0, 0.0, 0.0))

        events = {"goals": [goal], "demos": [demo], "touches": [touch]}

        timeline = build_timeline(events)
        assert len(timeline) == 3

        assert timeline[0].t == 1.0
        assert timeline[0].type == "DEMO"
        assert timeline[1].t == 2.0
        assert timeline[1].type == "GOAL"
        assert timeline[2].t == 3.0
        assert timeline[2].type == "TOUCH"

    def test_timeline_event_data_preserved(self):
        """Timeline events preserve original event data."""
        goal = GoalEvent(t=1.0, scorer="p1", team="BLUE", shot_speed_kph=120.0)
        events = {"goals": [goal]}

        timeline = build_timeline(events)
        assert len(timeline) == 1

        event = timeline[0]
        assert event.type == "GOAL"
        assert event.player_id == "p1"
        assert event.team == "BLUE"
        assert event.data["shot_speed_kph"] == 120.0

    def test_shot_and_save_timeline_entries(self):
        """Touches tagged as shot/save emit additional timeline markers."""
        touch_shot = TouchEvent(
            t=2.0,
            frame=20,
            player_id="shooter",
            location=Vec3(0.0, 2000.0, 100.0),
            ball_speed_kph=150.0,
            outcome="SHOT",
        )
        touch_save = TouchEvent(
            t=3.0,
            frame=30,
            player_id="saver",
            location=Vec3(0.0, -3000.0, 100.0),
            ball_speed_kph=80.0,
            outcome="CLEAR",
            is_save=True,
        )

        events = {
            "goals": [],
            "demos": [],
            "kickoffs": [],
            "boost_pickups": [],
            "touches": [touch_shot, touch_save],
            "challenges": [],
        }

        timeline = build_timeline(events)
        event_types = [ev.type for ev in timeline]
        assert "SHOT" in event_types
        assert "SAVE" in event_types

    def test_same_timestamp_stable_sort(self):
        """Events with same timestamp sorted by type for stability."""
        events = {
            "touches": [
                TouchEvent(t=1.0, player_id="p1", location=Vec3(0.0, 0.0, 0.0))
            ],
            "demos": [DemoEvent(t=1.0, victim="p2", attacker="p1")],
            "goals": [GoalEvent(t=1.0, scorer="p1", team="BLUE")],
        }

        timeline = build_timeline(events)
        assert len(timeline) == 3

        # Should be sorted alphabetically by type: DEMO, GOAL, TOUCH
        assert timeline[0].type == "DEMO"
        assert timeline[1].type == "GOAL"
        assert timeline[2].type == "TOUCH"

    def test_timeline_preserves_parser_event_sources(self):
        """Timeline entries keep parser provenance visible."""
        events = {
            "touches": [
                TouchEvent(
                    t=1.0,
                    player_id="p1",
                    location=Vec3(0.0, 0.0, 93.15),
                    source="parser",
                )
            ],
            "demos": [DemoEvent(t=2.0, victim="p2", attacker="p1", source="parser")],
            "kickoffs": [
                KickoffEvent(t_start=0.0, phase="INITIAL", players=[], source="parser")
            ],
        }

        timeline = build_timeline(events)
        source_by_type = {event.type: event.data["source"] for event in timeline}

        assert source_by_type["KICKOFF"] == "parser"
        assert source_by_type["TOUCH"] == "parser"
        assert source_by_type["DEMO"] == "parser"


class TestParserAuthorityPreference:
    """Parser-auth event streams should win over heuristic fallbacks."""

    def test_touches_prefer_parser_events_when_present(self):
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 1000.0, 0.0),
                [create_test_player("heuristic_player", 0, Vec3(0.0, 0.0, 17.0))],
            )
        ]
        frames[0] = Frame(
            timestamp=frames[0].timestamp,
            ball=frames[0].ball,
            players=frames[0].players,
            parser_touch_events=[
                ParserTouchEvent(timestamp=1.0, player_id="parser_player", team=0)
            ],
        )

        touches = detect_touches(frames)
        assert len(touches) == 1
        assert touches[0].player_id == "parser_player"

    def test_touches_fall_back_to_inference_without_parser_events(self):
        frames = [
            create_test_frame(
                1.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 1000.0, 0.0),
                [create_test_player("heuristic_player", 0, Vec3(0.0, 0.0, 17.0))],
            )
        ]

        touches = detect_touches(frames)
        assert touches

    def test_demos_prefer_parser_events_when_present(self):
        frames = [
            create_test_frame(
                2.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("victim", 0, Vec3(500.0, 0.0, 17.0))],
            )
        ]
        frames[0] = Frame(
            timestamp=frames[0].timestamp,
            ball=frames[0].ball,
            players=frames[0].players,
            parser_demo_events=[
                ParserDemoEvent(
                    timestamp=2.0,
                    victim_id="victim",
                    attacker_id="attacker",
                    victim_team=0,
                    attacker_team=1,
                )
            ],
        )

        demos = detect_demos(frames)
        assert len(demos) == 1
        assert demos[0].victim == "victim"
        assert demos[0].attacker == "attacker"

    def test_demos_keep_parser_authority_without_attacker_attribution(self):
        frames = [
            create_test_frame(
                2.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("victim", 0, Vec3(500.0, 0.0, 17.0)),
                    create_test_player("attacker", 1, Vec3(560.0, 0.0, 17.0)),
                ],
            ),
            create_test_frame(
                2.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "victim",
                        0,
                        Vec3(500.0, 0.0, 17.0),
                        demolished=True,
                    ),
                    create_test_player("attacker", 1, Vec3(540.0, 0.0, 17.0)),
                ],
            ),
        ]
        frames[1] = Frame(
            timestamp=frames[1].timestamp,
            ball=frames[1].ball,
            players=frames[1].players,
            parser_demo_events=[
                ParserDemoEvent(
                    timestamp=2.1,
                    victim_id="victim",
                    attacker_id=None,
                    victim_team=0,
                    attacker_team=None,
                )
            ],
        )

        demos = detect_demos(frames)
        assert len(demos) == 1
        assert demos[0].victim == "victim"
        assert demos[0].attacker is None
        assert demos[0].source == "parser"

    def test_parser_demos_drop_same_victim_location_echoes(self):
        frames = [
            create_test_frame(
                41.8,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("victim", 0, Vec3(500.0, 0.0, 17.0)),
                    create_test_player("attacker", 1, Vec3(540.0, 0.0, 17.0)),
                ],
            ),
            create_test_frame(
                43.4,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("victim", 0, Vec3(500.0, 0.0, 17.0)),
                    create_test_player("attacker", 1, Vec3(540.0, 0.0, 17.0)),
                ],
            ),
        ]
        frames[0] = Frame(
            timestamp=frames[0].timestamp,
            ball=frames[0].ball,
            players=frames[0].players,
            parser_demo_events=[
                ParserDemoEvent(
                    timestamp=41.8,
                    victim_id="victim",
                    attacker_id="attacker",
                    victim_team=0,
                    attacker_team=1,
                )
            ],
        )
        frames[1] = Frame(
            timestamp=frames[1].timestamp,
            ball=frames[1].ball,
            players=frames[1].players,
            parser_demo_events=[
                ParserDemoEvent(
                    timestamp=43.4,
                    victim_id="victim",
                    attacker_id=None,
                    victim_team=0,
                    attacker_team=None,
                )
            ],
        )

        demos = detect_demos(frames)
        assert len(demos) == 1
        assert demos[0].t == 41.8
        assert demos[0].attacker == "attacker"

    def test_kickoffs_merge_parser_markers_with_heuristic_enrichment(self):
        frames = [
            create_test_frame(
                0.0,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("blue_go", 0, Vec3(-500.0, -1000.0, 17.0)),
                    create_test_player("orange_go", 1, Vec3(500.0, 1000.0, 17.0)),
                ],
            ),
            create_test_frame(
                0.25,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("blue_go", 0, Vec3(0.0, -130.0, 17.0)),
                    create_test_player("orange_go", 1, Vec3(0.0, 110.0, 17.0)),
                ],
            ),
            create_test_frame(
                0.35,
                Vec3(0.0, 60.0, 93.15),
                Vec3(0.0, 960.0, 0.0),
                [
                    create_test_player("blue_go", 0, Vec3(0.0, 55.0, 17.0)),
                    create_test_player("orange_go", 1, Vec3(0.0, 65.0, 17.0)),
                ],
            ),
        ]
        frames[0] = Frame(
            timestamp=frames[0].timestamp,
            ball=frames[0].ball,
            players=frames[0].players,
            parser_kickoff_markers=[
                ParserKickoffMarker(timestamp=0.0, phase="INITIAL")
            ],
        )

        kickoffs = detect_kickoffs(frames)

        assert len(kickoffs) == 1
        kickoff = kickoffs[0]
        assert kickoff.phase == "INITIAL"
        assert kickoff.source == "parser"
        assert kickoff.first_touch_player == "blue_go"
        assert kickoff.time_to_first_touch == 0.25
        assert {player["role"] for player in kickoff.players} == {"GO"}
        assert all(player["approach_type"] != "UNKNOWN" for player in kickoff.players)

    def test_parser_kickoff_markers_preserve_ot_phase(self):
        frames = [
            create_test_frame(
                301.0,
                Vec3(1000.0, 1000.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [],
            )
        ]
        frames[0] = Frame(
            timestamp=frames[0].timestamp,
            ball=frames[0].ball,
            players=frames[0].players,
            parser_kickoff_markers=[ParserKickoffMarker(timestamp=301.0, phase="OT")],
        )

        kickoffs = detect_kickoffs(
            frames,
            Header(match_length=300.0, overtime=True),
        )

        assert len(kickoffs) == 1
        assert kickoffs[0].phase == "OT"

    def test_parser_kickoff_markers_infer_roles_from_positions(self):
        """Parser-only markers infer roles from positions, not hardcode BACK.

        Regression: when parser markers exist without a heuristic match,
        roles must be inferred (GO/CHEAT/WING/BACK) from spawn positions,
        not assigned BACK for everyone.
        """
        # Ball away from center so no heuristic kickoff is detected,
        # but parser still emits markers that need proper role inference.
        frames = [
            create_test_frame(
                0.0,
                Vec3(500.0, 1000.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    # Blue team (team 0) - 3 players at different depths
                    create_test_player("blue_go", 0, Vec3(0.0, -200.0, 17.0)),
                    create_test_player("blue_wing", 0, Vec3(-1800.0, -3000.0, 17.0)),
                    create_test_player("blue_back", 0, Vec3(0.0, -4000.0, 17.0)),
                    # Orange team (team 1) - 3 players
                    create_test_player("orange_go", 1, Vec3(0.0, 200.0, 17.0)),
                    create_test_player("orange_wing", 1, Vec3(1800.0, 3000.0, 17.0)),
                    create_test_player("orange_back", 1, Vec3(0.0, 4000.0, 17.0)),
                ],
            ),
        ]
        frames[0] = Frame(
            timestamp=frames[0].timestamp,
            ball=frames[0].ball,
            players=frames[0].players,
            parser_kickoff_markers=[
                ParserKickoffMarker(timestamp=0.0, phase="INITIAL")
            ],
        )

        kickoffs = detect_kickoffs(frames)

        assert len(kickoffs) == 1
        kickoff = kickoffs[0]
        assert kickoff.source == "parser"

        player_roles = {p["player_id"]: p["role"] for p in kickoff.players}

        # Verify roles are inferred, NOT all BACK
        assert player_roles["blue_go"] == "GO"
        assert player_roles["orange_go"] == "GO"
        assert player_roles["blue_wing"] == "WING"
        assert player_roles["orange_wing"] == "WING"
        assert player_roles["blue_back"] == "BACK"
        assert player_roles["orange_back"] == "BACK"

        # Ensure roles vary (the original bug was all BACK)
        assert len(set(player_roles.values())) > 1
