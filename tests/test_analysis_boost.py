"""Tests for boost analysis."""

from unittest.mock import Mock

from rlcoach.analysis.boost import analyze_boost
from rlcoach.events import BoostPickupEvent
from rlcoach.field_constants import Vec3
from rlcoach.parser.types import BallFrame, Frame, PlayerFrame


def create_test_frame(timestamp: float, players: list[PlayerFrame]) -> Frame:
    """Helper to create test frames."""
    return Frame(
        timestamp=timestamp,
        ball=BallFrame(
            position=Vec3(0.0, 0.0, 93.15),
            velocity=Vec3(0.0, 0.0, 0.0),
            angular_velocity=Vec3(0.0, 0.0, 0.0),
        ),
        players=players,
    )


def create_test_player(
    player_id: str,
    team: int,
    boost: int = 33,
    velocity: Vec3 = None,
    position: Vec3 = None,
) -> PlayerFrame:
    """Helper to create test player frames."""
    if velocity is None:
        velocity = Vec3(0.0, 0.0, 0.0)
    if position is None:
        position = Vec3(0.0, 0.0, 17.0)

    return PlayerFrame(
        player_id=player_id,
        team=team,
        position=position,
        velocity=velocity,
        rotation=Vec3(0.0, 0.0, 0.0),
        boost_amount=boost,
        is_supersonic=(
            velocity is not None
            and (velocity.x**2 + velocity.y**2 + velocity.z**2) > (2300**2)
        ),
        is_on_ground=True,
        is_demolished=False,
    )


class TestBoostAnalysis:
    """Test boost analysis functions."""

    def test_empty_frames_returns_zeros(self):
        """Empty frames should return all zero metrics."""
        frames = []
        events = {}

        result = analyze_boost(frames, events, player_id="player1")

        assert result["bpm"] == 0.0
        assert result["bcpm"] == 0.0
        assert result["avg_boost"] == 0.0
        assert result["time_zero_boost_s"] == 0.0
        assert result["time_full_boost_s"] == 0.0
        assert result["boost_collected"] == 0.0
        assert result["boost_stolen"] == 0.0
        assert result["big_pads"] == 0
        assert result["small_pads"] == 0
        assert result["stolen_big_pads"] == 0
        assert result["stolen_small_pads"] == 0
        assert result["overfill"] == 0.0
        assert result["waste"] == 0.0

    def test_basic_boost_collection_tracking(self):
        """Test basic boost collection from pickup events."""
        player1 = create_test_player("player1", 0, boost=50)
        frames = [
            create_test_frame(0.0, [player1]),
            create_test_frame(60.0, [player1]),  # 60 second match
        ]

        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    frame=1,
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
                BoostPickupEvent(
                    t=20.0,
                    player_id="player1",
                    pad_type="SMALL",
                    stolen=False,
                    pad_id=5,
                    location=Vec3(0, 2048, 73),
                    frame=2,
                    boost_before=50.0,
                    boost_after=62.0,
                    boost_gain=12.0,
                ),
                BoostPickupEvent(
                    t=30.0,
                    player_id="player2",
                    pad_type="BIG",
                    stolen=True,
                    pad_id=1,
                    location=Vec3(-3584, 0, 73),
                    frame=3,
                    boost_before=10.0,
                    boost_after=100.0,
                    boost_gain=90.0,
                ),
            ]
        }

        result = analyze_boost(frames, events, player_id="player1")

        assert result["boost_collected"] == 112.0  # 100 (big) + 12 (small)
        assert result["boost_stolen"] == 0.0  # Neither pickup was stolen
        assert result["big_pads"] == 1
        assert result["small_pads"] == 1
        assert result["stolen_big_pads"] == 0
        assert result["stolen_small_pads"] == 0
        assert result["bpm"] == 112.0  # 112 boost in 1 minute
        assert result["bcpm"] == 2.0  # 2 pickups in 1 minute

    def test_stolen_boost_tracking(self):
        """Test tracking stolen boost pickups."""
        player1 = create_test_player("player1", 0)  # Blue team
        frames = [
            create_test_frame(0.0, [player1]),
            create_test_frame(60.0, [player1]),
        ]

        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=True,
                    pad_id=0,
                    location=Vec3(3584, 2500, 73),
                    frame=1,
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),  # Orange side
                BoostPickupEvent(
                    t=20.0,
                    player_id="player1",
                    pad_type="SMALL",
                    stolen=True,
                    pad_id=5,
                    location=Vec3(0, 3000, 73),
                    frame=2,
                    boost_before=10.0,
                    boost_after=22.0,
                    boost_gain=12.0,
                ),  # Orange side
                BoostPickupEvent(
                    t=30.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=1,
                    location=Vec3(-3584, -2500, 73),
                    frame=3,
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),  # Blue side
            ]
        }

        result = analyze_boost(frames, events, player_id="player1")

        assert result["boost_collected"] == 212.0  # 200 (2 big) + 12 (1 small)
        assert result["boost_stolen"] == 112.0  # 100 (1 big) + 12 (1 small)
        assert result["big_pads"] == 2
        assert result["small_pads"] == 1
        assert result["stolen_big_pads"] == 1
        assert result["stolen_small_pads"] == 1

    def test_time_at_zero_and_full_boost(self):
        """Test tracking time spent at 0 and 100 boost."""
        boosts = [0, 0, 50, 100, 100, 100, 30]
        frames = [
            create_test_frame(
                float(second), [create_test_player("player1", 0, boost=b)]
            )
            for second, b in enumerate(boosts)
        ]

        events = {}

        result = analyze_boost(frames, events, player_id="player1")

        assert result["time_zero_boost_s"] == 2.0  # 0-2s at zero boost
        assert result["time_full_boost_s"] == 3.0  # 3-6s at full boost
        assert (
            abs(result["avg_boost"] - 54.29) < 0.1
        )  # Average of all boost amounts (allow small rounding)

    def test_almost_empty_or_full_does_not_count(self):
        """Zero and full mean exactly that, as Ballchasing counts them."""
        boosts = [1, 2, 3, 99, 98, 50]
        frames = [
            create_test_frame(
                float(second), [create_test_player("player1", 0, boost=b)]
            )
            for second, b in enumerate(boosts)
        ]

        result = analyze_boost(frames, {}, player_id="player1")

        assert result["time_zero_boost_s"] == 0.0
        assert result["time_full_boost_s"] == 0.0

    def test_goal_replay_pause_is_not_time_at_zero_or_full(self):
        empty = [create_test_player("player1", 0, boost=0)]
        full = [create_test_player("player1", 0, boost=100)]
        frames = [
            create_test_frame(0.0, empty),
            create_test_frame(1.0, empty),
            create_test_frame(11.0, full),
            create_test_frame(12.0, full),
            create_test_frame(22.0, full),
        ]

        result = analyze_boost(frames, {}, player_id="player1")

        assert result["time_zero_boost_s"] == 1.0
        assert result["time_full_boost_s"] == 1.0

    def test_overfill_detection(self):
        """Test overfill calculation when collecting boost above threshold."""
        frames = [
            create_test_frame(
                0.0, [create_test_player("player1", 0, boost=85)]
            ),  # High boost
            create_test_frame(
                10.0, [create_test_player("player1", 0, boost=95)]
            ),  # Very high
            create_test_frame(20.0, [create_test_player("player1", 0, boost=50)]),
            create_test_frame(30.0, [create_test_player("player1", 0, boost=50)]),
        ]

        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    frame=1,
                    boost_before=85.0,
                    boost_after=100.0,
                    boost_gain=15.0,
                ),
                BoostPickupEvent(
                    t=20.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=1,
                    location=Vec3(-3584, 0, 73),
                    frame=2,
                    boost_before=95.0,
                    boost_after=100.0,
                    boost_gain=5.0,
                ),
                BoostPickupEvent(
                    t=30.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=2,
                    location=Vec3(0, 5120, 73),
                    frame=3,
                    boost_before=20.0,
                    boost_after=100.0,
                    boost_gain=80.0,
                ),
            ]
        }

        result = analyze_boost(frames, events, player_id="player1")

        assert (
            result["overfill"] == 180.0
        )  # 85 wasted + 95 wasted on two big-pad pickups

    def test_boost_waste_detection(self):
        """Test boost waste detection during supersonic speeds."""
        frames = [
            # Player using boost while supersonic (wasteful)
            create_test_frame(
                0.0,
                [
                    create_test_player(
                        "player1", 0, boost=100, velocity=Vec3(2400, 0, 0)
                    )
                ],
            ),  # Supersonic
            create_test_frame(
                5.0,
                [create_test_player("player1", 0, boost=80, velocity=Vec3(2400, 0, 0))],
            ),  # Still supersonic, used 20 boost
            # Player using boost effectively
            create_test_frame(
                10.0,
                [create_test_player("player1", 0, boost=70, velocity=Vec3(1500, 0, 0))],
            ),  # Not supersonic
            create_test_frame(
                15.0,
                [create_test_player("player1", 0, boost=60, velocity=Vec3(1800, 0, 0))],
            ),  # Accelerating
        ]

        events = {}

        result = analyze_boost(frames, events, player_id="player1")

        assert (
            result["waste"] > 0.0
        )  # Should detect some waste from supersonic boosting

    def test_bpm_and_bcpm_calculation(self):
        """Test BPM and BCPM rate calculations."""
        player1 = create_test_player("player1", 0)
        frames = [
            create_test_frame(0.0, [player1]),
            create_test_frame(120.0, [player1]),  # 2 minute match
        ]

        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=30.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    frame=1,
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
                BoostPickupEvent(
                    t=60.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=1,
                    location=Vec3(-3584, 0, 73),
                    frame=2,
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
                BoostPickupEvent(
                    t=90.0,
                    player_id="player1",
                    pad_type="SMALL",
                    stolen=False,
                    pad_id=5,
                    location=Vec3(0, 2048, 73),
                    frame=3,
                    boost_before=40.0,
                    boost_after=52.0,
                    boost_gain=12.0,
                ),
            ]
        }

        result = analyze_boost(frames, events, player_id="player1")

        # 212 boost collected in 2 minutes = 106 BPM
        assert result["bpm"] == 106.0
        # 3 pickups in 2 minutes = 1.5 BCPM
        assert result["bcpm"] == 1.5
        assert result["boost_collected"] == 212.0

    def test_rates_use_active_play_time(self):
        """Goal replays and kickoff countdowns should not dilute rates."""
        held = create_test_player("player1", 0)
        moving = create_test_player("player1", 0, velocity=Vec3(1000.0, 0.0, 0.0))

        # Two kickoff holds around a 20s goal replay
        frames = []
        for start, end in ((0.0, 130.0), (150.0, 206.0)):
            for step in range(int((end - start) * 2) + 1):
                t = start + step * 0.5
                player = held if t - start < 3.5 else moving
                frames.append(create_test_frame(t, [player]))

        pickups = [
            BoostPickupEvent(
                t=t,
                player_id="player1",
                pad_type="BIG",
                stolen=False,
                pad_id=0,
                location=Vec3(3584, 0, 73),
                frame=1,
                boost_before=0.0,
                boost_after=100.0,
                boost_gain=100.0,
            )
            for t in (30.0, 60.0, 90.0)
        ]
        events = {"boost_pickups": pickups}

        player = analyze_boost(frames, events, player_id="player1")
        team = analyze_boost(frames, events, team="BLUE")

        # 206s recorded - 20s replay - 6s for two kickoffs = 3 minutes of play
        assert player["bpm"] == 100.0
        assert player["bcpm"] == 1.0
        assert team["bpm"] == 100.0

    def test_short_still_moment_is_not_a_kickoff(self):
        """A car and ball briefly at rest should not count as a countdown."""
        held = create_test_player("player1", 0)
        moving = create_test_player("player1", 0, velocity=Vec3(1000.0, 0.0, 0.0))

        frames = [
            create_test_frame(step * 0.5, [held if 100 <= step < 102 else moving])
            for step in range(361)
        ]
        pickup = BoostPickupEvent(
            t=30.0,
            player_id="player1",
            pad_type="BIG",
            stolen=False,
            pad_id=0,
            location=Vec3(3584, 0, 73),
            frame=1,
            boost_before=0.0,
            boost_after=100.0,
            boost_gain=100.0,
        )

        result = analyze_boost(frames, {"boost_pickups": [pickup]}, player_id="player1")

        # 180s of play with nothing removed = 3 minutes
        assert result["bpm"] == 33.33

    def test_team_analysis_aggregation(self):
        """Test team-level boost analysis aggregation."""
        player1 = create_test_player("player1", 0, boost=50)  # Blue team
        player2 = create_test_player("player2", 0, boost=30)  # Blue team
        player3 = create_test_player("player3", 1, boost=80)  # Orange team

        frames = [
            create_test_frame(0.0, [player1, player2, player3]),
            create_test_frame(60.0, [player1, player2, player3]),
        ]

        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    frame=1,
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
                BoostPickupEvent(
                    t=20.0,
                    player_id="player2",
                    pad_type="SMALL",
                    stolen=False,
                    pad_id=5,
                    location=Vec3(0, 2048, 73),
                    frame=2,
                    boost_before=30.0,
                    boost_after=42.0,
                    boost_gain=12.0,
                ),
                BoostPickupEvent(
                    t=30.0,
                    player_id="player3",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=1,
                    location=Vec3(-3584, 0, 73),
                    frame=3,
                    boost_before=20.0,
                    boost_after=100.0,
                    boost_gain=80.0,
                ),
            ]
        }

        result = analyze_boost(frames, events, team="BLUE")

        # Blue team collected: 100 (player1) + 12 (player2) = 112
        assert result["boost_collected"] == 112.0
        assert result["big_pads"] == 1  # player1's big pad
        assert result["small_pads"] == 1  # player2's small pad
        assert result["bpm"] == 112.0  # 112 in 1 minute
        assert result["bcpm"] == 2.0  # 2 pickups in 1 minute
        # Note: Team avg_boost sums individual player avg_boosts (internal convention)
        # player1 avg=50, player2 avg=30, team sum=80
        assert result["avg_boost"] == 80.0

    def test_no_pickup_events(self):
        """Test handling when no boost pickup events are available."""
        player1 = create_test_player("player1", 0, boost=50)
        frames = [
            create_test_frame(0.0, [player1]),
            create_test_frame(60.0, [player1]),
        ]

        events = {}  # No boost_pickups key

        result = analyze_boost(frames, events, player_id="player1")

        assert result["boost_collected"] == 0.0
        assert result["big_pads"] == 0
        assert result["small_pads"] == 0
        assert result["bpm"] == 0.0
        assert result["bcpm"] == 0.0
        assert result["avg_boost"] == 50.0  # Still calculated from frames

    def test_player_not_in_frames(self):
        """Test handling when requested player is not found in frames."""
        player2 = create_test_player("player2", 0)
        frames = [
            create_test_frame(0.0, [player2]),  # Only player2, not player1
            create_test_frame(60.0, [player2]),
        ]

        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    frame=1,
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
            ]
        }

        result = analyze_boost(frames, events, player_id="player1")

        # Player1 not in frames, so frame-based metrics should be zero
        assert result["avg_boost"] == 0.0
        assert result["time_zero_boost_s"] == 0.0
        assert result["time_full_boost_s"] == 0.0
        # But pickup-based metrics should still work
        assert result["boost_collected"] == 100.0
        assert result["big_pads"] == 1

    def test_header_only_mode(self):
        """Test graceful degradation with no frame data."""
        frames = []
        events = {
            "boost_pickups": [
                BoostPickupEvent(
                    t=10.0,
                    player_id="player1",
                    pad_type="BIG",
                    stolen=False,
                    pad_id=0,
                    location=Vec3(3584, 0, 73),
                    frame=1,
                    boost_before=0.0,
                    boost_after=100.0,
                    boost_gain=100.0,
                ),
            ]
        }
        header = Mock()

        result = analyze_boost(frames, events, player_id="player1", header=header)

        # Should handle empty frames gracefully
        assert result["avg_boost"] == 0.0
        assert result["time_zero_boost_s"] == 0.0
        assert result["time_full_boost_s"] == 0.0
        # Pickup data should still be processed
        assert result["boost_collected"] == 100.0
        assert (
            result["bpm"] == 100.0
        )  # 100 boost collected in default 1 minute duration
