"""Tests for following each player through a game's frames."""

from __future__ import annotations

from rlcoach.analysis.tracks import player_tracks
from tests.fixtures.builders import create_test_frame, create_test_player


def test_each_player_keeps_the_index_of_every_frame_they_are_in():
    me, them = create_test_player("me", 0), create_test_player("them", 1)
    frames = [
        create_test_frame(0.0, [me, them]),
        create_test_frame(0.1, [them]),  # I'm respawning
        create_test_frame(0.2, [me, them]),
    ]
    tracks = player_tracks(frames)
    assert [index for index, _ in tracks["me"]] == [0, 2]
    assert [index for index, _ in tracks["them"]] == [0, 1, 2]
    assert tracks["me"][1][1] is me


def test_no_frames_no_tracks():
    assert player_tracks([]) == {}
