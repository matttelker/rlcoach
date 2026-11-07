"""Tests for finding boost pad pickups."""

from dataclasses import replace

from rlcoach.events import detect_boost_pickups
from rlcoach.field_constants import FIELD, Vec3
from rlcoach.parser.types import (
    BallFrame,
    BoostPadEventFrame,
    Frame,
    PlayerFrame,
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
