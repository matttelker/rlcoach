"""Tests for event detection and timeline aggregation."""

import math
from dataclasses import replace
from pathlib import Path

import pytest

from rlcoach.events import (
    KickoffEvent,
    detect_boost_pickups,
    detect_kickoffs,
)
from rlcoach.field_constants import FIELD, Vec3
from rlcoach.normalize import build_timeline as build_normalized_frames
from rlcoach.parser import RustAdapter
from rlcoach.parser.types import (
    BallFrame,
    BoostPadEventFrame,
    Frame,
    GoalHeader,
    Header,
    ParserComponentEvent,
    ParserKickoffMarker,
    ParserTouchEvent,
    PlayerFrame,
    Quaternion,
    Rotation,
)

REPLAY_DIR = Path(__file__).resolve().parents[1] / "Replay_files"


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


def create_test_match(
    kickoffs: list[float], goals: list[tuple[float, int]]
) -> tuple[list[Frame], Header]:
    """Helper to create frames and a header from kickoff and (time, team) goals."""
    player = create_test_player("p1", 0, Vec3(-200.0, -200.0, 17.0))
    ball_at_rest = (Vec3(0.0, 0.0, 93.15), Vec3(0.0, 0.0, 0.0))
    ball_in_play = (Vec3(200.0, 300.0, 150.0), Vec3(400.0, 600.0, 100.0))

    frames = []
    for t in kickoffs:
        frames.append(create_test_frame(t, *ball_at_rest, [player]))
        frames.append(create_test_frame(t + 1.0, *ball_in_play, [player]))
    for t, _ in goals:
        frames.append(create_test_frame(t, *ball_in_play, [player]))
    frames.sort(key=lambda frame: frame.timestamp)

    times = [frame.timestamp for frame in frames]
    header = Header(
        goals=[
            GoalHeader(frame=times.index(t), player_name="Player", player_team=team)
            for t, team in goals
        ]
    )
    return frames, header


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


def with_game_first_touch(
    frames: list[Frame], at: float, player_id: str, team: int
) -> list[Frame]:
    """Put a rise of the game's first-touch counter on the frame nearest ``at``."""
    nearest = min(range(len(frames)), key=lambda i: abs(frames[i].timestamp - at))
    event = ParserTouchEvent(timestamp=at, player_id=player_id, team=team)
    return [
        (
            replace(frame, parser_first_touch_events=[event])
            if index == nearest
            else frame
        )
        for index, frame in enumerate(frames)
    ]


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

    def test_overtime_kickoff_has_no_goal_since_the_last_kickoff(self):
        """The kickoff after regulation ends level is overtime."""
        frames, header = create_test_match(
            [0.0, 100.0, 210.0, 350.0], [(90.0, 0), (200.0, 1), (420.0, 0)]
        )

        kickoffs = detect_kickoffs(frames, header)

        assert [k.phase for k in kickoffs] == ["INITIAL", "INITIAL", "INITIAL", "OT"]

    def test_late_kickoff_after_a_goal_is_not_overtime(self):
        """Regression: replay time passes 300 s while the clock is still running."""
        frames, header = create_test_match(
            [0.0, 320.0, 345.0], [(315.0, 0), (340.0, 1)]
        )

        kickoffs = detect_kickoffs(frames, header)

        assert [k.phase for k in kickoffs] == ["INITIAL"] * 3

    def test_kickoff_without_a_goal_at_uneven_score_is_not_overtime(self):
        """Overtime only happens when regulation ends level."""
        frames, header = create_test_match([0.0, 100.0, 350.0], [(90.0, 0)])

        kickoffs = detect_kickoffs(frames, header)

        assert [k.phase for k in kickoffs] == ["INITIAL"] * 3

    def test_only_kickoff_is_not_overtime(self):
        """The opening kickoff has no kickoff before it to compare."""
        frames, header = create_test_match([350.0], [(400.0, 0)])

        kickoffs = detect_kickoffs(frames, header)

        assert [k.phase for k in kickoffs] == ["INITIAL"]

    def test_late_kickoffs_without_goal_data_are_not_overtime(self):
        """Nothing proves overtime, so replay time alone does not set it."""
        frames, _ = create_test_match([0.0, 350.0], [])

        kickoffs = detect_kickoffs(frames)

        assert [k.phase for k in kickoffs] == ["INITIAL"] * 2

    @pytest.mark.parametrize(
        ("replay", "overtime_kickoffs"),
        [
            ("0925.replay", []),
            ("4985385d-2a6a-4bea-a312-8e539c7fd098.replay", [350.2]),
            ("6804bd43-5415-49f4-b7d0-31b168c871ed.replay", []),
            ("70c0e78e-ea32-4722-a951-937baa40efc9.replay", []),
            ("77253f53-0654-4565-b18e-e77ddbb84282.replay", []),
            ("testing_replay.replay", [428.5]),
        ],
    )
    def test_overtime_kickoffs_match_the_game_clock(self, replay, overtime_kickoffs):
        """Expected values come from the game clock in each replay's network data."""
        path = REPLAY_DIR / replay
        if not path.exists():
            pytest.skip("replay fixture missing")
        pytest.importorskip("rlreplay_rust")
        adapter = RustAdapter()
        header = adapter.parse_header(path)
        frames = build_normalized_frames(header, adapter.parse_network(path).frames)

        kickoffs = detect_kickoffs(frames, header)

        assert [
            round(kickoff.t_start, 1) for kickoff in kickoffs if kickoff.phase == "OT"
        ] == overtime_kickoffs

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

        adapter = RustAdapter()
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


class TestKickoffGameFirstTouch:
    """The game's first-touch counter outranks the estimate from frames.

    ``countdown_frames(10.0)`` plays the ball at 16.1 with blue closest, so the
    frames alone credit blue.
    """

    @staticmethod
    def kickoff_with_counter(at: float, player_id: str, team: int, **drives):
        frames = countdown_frames(10.0, **drives) + open_play_frames(16.4, count=90)
        return detect_kickoffs(with_game_first_touch(frames, at, player_id, team))[0]

    def test_counter_names_the_first_touch(self):
        kickoff = self.kickoff_with_counter(16.8, "orange", 1)

        assert kickoff.first_touch_player == "orange"
        assert kickoff.outcome == "FIRST_POSSESSION_ORANGE"

    def test_counter_keeps_the_estimate_when_they_agree(self):
        kickoff = self.kickoff_with_counter(16.8, "blue", 0)

        assert kickoff.first_touch_player == "blue"
        assert kickoff.outcome == "FIRST_POSSESSION_BLUE"

    def test_contact_time_stays_with_the_frames(self):
        estimated = detect_kickoffs(countdown_frames(10.0))[0]

        kickoff = self.kickoff_with_counter(16.8, "orange", 1)

        assert kickoff.time_to_first_touch == estimated.time_to_first_touch
        assert kickoff.t_start == estimated.t_start

    @pytest.mark.parametrize("lag", [0.0, 1.02])
    def test_counter_counts_across_its_replication_lag(self, lag):
        """It arrives 0-1.02s after contact on real replays, once the window closed."""
        kickoff = self.kickoff_with_counter(16.1 + lag, "orange", 1)

        assert kickoff.first_touch_player == "orange"

    def test_counter_can_arrive_just_before_the_contact_frame(self):
        """Contact reads up to a frame late, and a rise can replicate at once."""
        kickoff = self.kickoff_with_counter(16.05, "orange", 1)

        assert kickoff.first_touch_player == "orange"

    @pytest.mark.parametrize("at", [13.9, 17.8])
    def test_counter_outside_the_kickoff_is_ignored(self, at):
        """A rise before the release or long after contact is some other moment."""
        kickoff = self.kickoff_with_counter(at, "orange", 1)

        assert kickoff.first_touch_player == "blue"
        assert kickoff.outcome == "FIRST_POSSESSION_BLUE"

    def test_counter_for_a_player_not_in_the_kickoff_keeps_the_estimate(self):
        kickoff = self.kickoff_with_counter(16.8, "left_the_match", 1)

        assert kickoff.first_touch_player == "blue"

    def test_each_kickoff_takes_its_own_counter(self):
        first = countdown_frames(0.0) + open_play_frames(6.4)
        second = countdown_frames(30.0) + open_play_frames(36.4)
        frames = with_game_first_touch(first, 6.8, "orange", 1)
        frames += with_game_first_touch(second, 36.8, "blue", 0)

        kickoffs = detect_kickoffs(frames)

        assert [kickoff.first_touch_player for kickoff in kickoffs] == [
            "orange",
            "blue",
        ]

    def test_credited_car_out_of_reach_is_not_a_fake(self):
        """Stale positions can read the real toucher beyond the reach limit."""
        kickoff = self.kickoff_with_counter(16.8, "orange", 1, orange_drive=500.0)

        orange = next(p for p in kickoff.players if p["player_id"] == "orange")
        assert kickoff.first_touch_player == "orange"
        assert orange["time_to_first_touch"] == kickoff.time_to_first_touch
        assert not orange["approach_type"].startswith("FAKE")

    def test_counter_without_a_contact_frame_has_no_time(self):
        """A ball hit straight up shows no sideways speed, but the counter rises."""
        frames = countdown_frames(
            10.0, blue_drive=300.0, orange_drive=300.0, ball_exit=0.0
        )

        kickoff = detect_kickoffs(with_game_first_touch(frames, 16.3, "orange", 1))[0]

        assert kickoff.first_touch_player == "orange"
        assert kickoff.outcome == "FIRST_POSSESSION_ORANGE"
        assert kickoff.time_to_first_touch is None

    def test_frames_with_no_countdown_use_the_counter_too(self):
        """A recording that starts mid-reset never shows a hold to release from."""
        frames = [
            create_test_frame(
                1.0 + step * FRAME_STEP,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("blue", 0, Vec3(0.0, -150.0, 17.0)),
                    create_test_player("orange", 1, Vec3(0.0, 2048.0, 17.0)),
                ],
            )
            for step in range(10)
        ] + open_play_frames(1.4)

        kickoff = detect_kickoffs(with_game_first_touch(frames, 1.8, "orange", 1))[0]

        assert kickoff.first_touch_player == "orange"


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

        adapter = RustAdapter()
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
                    create_test_player("p1", 0, Vec3(-3072.0, -4096.0, 17.0), boost=20)
                ],  # Corner boost
            ),
            create_test_frame(
                1.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player("p1", 0, Vec3(-3072.0, -4096.0, 17.0), boost=100)
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
                        "blue_p", 0, Vec3(3072.0, 4096.0, 17.0), boost=10
                    )
                ],  # Blue in orange corner
            ),
            create_test_frame(
                3.1,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [
                    create_test_player(
                        "blue_p", 0, Vec3(3072.0, 4096.0, 17.0), boost=100
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


class TestBoostPadEventPickups:
    """Pickups taken straight from parser pad events."""

    @staticmethod
    def _frame(timestamp, boost, events):
        frame = create_test_frame(
            timestamp,
            Vec3(0.0, 0.0, 93.15),
            Vec3(0.0, 0.0, 0.0),
            [create_test_player("p1", 0, Vec3(0.0, -4000.0, 17.0), boost=boost)],
        )
        return replace(frame, boost_pad_events=events)

    @staticmethod
    def _collected(pad_id, timestamp, player_id):
        return BoostPadEventFrame(
            pad_id=pad_id,
            status="COLLECTED",
            is_big=FIELD.BOOST_PADS[pad_id].is_big,
            player_id=player_id,
            player_team=0 if player_id else None,
            timestamp=timestamp,
        )

    def test_unattributed_event_is_skipped_without_losing_the_rest(self):
        """One car with no player binding must not discard every pad event."""
        frames = [
            self._frame(1.0, 0, []),
            self._frame(1.1, 12, [self._collected(6, 1.1, "p1")]),
            self._frame(2.1, 12, [self._collected(9, 2.1, None)]),
            self._frame(3.1, 24, [self._collected(11, 3.1, "p1")]),
        ]

        pickups = detect_boost_pickups(frames)

        assert [pickup.pad_id for pickup in pickups] == [6, 11]
        assert all(pickup.player_id == "p1" for pickup in pickups)

    def test_side_big_pad_is_not_stolen(self):
        """The (+-3584, 0) big pads sit on the halfway line, not in a half."""
        pad = FIELD.BOOST_PADS[5]
        assert (pad.position.x, pad.position.y) == (3584.0, 0.0)
        frames = [
            self._frame(1.0, 0, []),
            self._frame(1.1, 100, [self._collected(5, 1.1, "p1")]),
        ]

        pickups = detect_boost_pickups(frames)

        assert len(pickups) == 1
        assert pickups[0].pad_type == "BIG"
        assert pickups[0].stolen is False


class TestParserAuthorityPreference:
    """Parser-auth event streams should win over heuristic fallbacks."""

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


class TestBoostPadEventCoverage:
    """Pad events only replace boost-delta detection when they are complete."""

    @staticmethod
    def _collected(player_id: str) -> BoostPadEventFrame:
        return BoostPadEventFrame(
            pad_id=0, status="COLLECTED", is_big=True, player_id=player_id
        )

    def _three_pickup_frames(self, pad_event_times: set[float]) -> list[Frame]:
        corner = Vec3(-3584.0, -4096.0, 17.0)
        boost_by_time = [
            (1.0, 20),
            (1.1, 100),
            (12.0, 20),
            (12.1, 100),
            (23.0, 20),
            (23.1, 100),
        ]
        frames = []
        for timestamp, boost in boost_by_time:
            frame = create_test_frame(
                timestamp,
                Vec3(0.0, 0.0, 93.15),
                Vec3(0.0, 0.0, 0.0),
                [create_test_player("p1", 0, corner, boost=boost)],
            )
            if timestamp in pad_event_times:
                frame = replace(frame, boost_pad_events=[self._collected("p1")])
            frames.append(frame)
        return frames

    def test_sparse_pad_events_do_not_hide_boost_gains(self):
        """One decoded pad event must not erase the other two pickups."""
        assert len(detect_boost_pickups(self._three_pickup_frames({1.1}))) == 3

    def test_pad_events_are_used_when_they_cover_most_pickups(self):
        """Pad events stay preferred once they explain most boost gains."""
        pickups = detect_boost_pickups(self._three_pickup_frames({1.1, 12.1}))

        assert [round(pickup.t, 1) for pickup in pickups] == [1.1, 12.1]
