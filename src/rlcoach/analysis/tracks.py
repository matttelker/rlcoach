"""Where each player is in a game's frames, and how long each frame lasts."""

from __future__ import annotations

from ..parser.types import Frame, PlayerFrame

# A player's frames, as (index into the game's frames, the car in that frame)
Track = list[tuple[int, PlayerFrame]]

# The recording pauses for each goal replay, so a longer gap between two frames
# is a replay and not play
PAUSE_GAP_S = 1.0


def player_tracks(frames: list[Frame]) -> dict[str, Track]:
    """Each player's frames, in order. A frame lists each player at most once."""
    tracks: dict[str, Track] = {}
    for index, frame in enumerate(frames):
        for car in frame.players:
            tracks.setdefault(car.player_id, []).append((index, car))
    return tracks
