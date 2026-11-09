"""Read replays with rlreplay_rust, the Rust parser (boxcars underneath).

`read_header` gives what the replay says about its match. `read_frames` gives every
network frame as the parser hands it over, which normalize turns into Frames.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .header import header_from_properties
from .types import Header

try:
    import rlreplay_rust as _rust
except ImportError:  # pragma: no cover - only before the parser is built
    _rust = None

MISSING_PARSER = "the Rust parser rlreplay_rust isn't installed; see AGENTS.md"


def _parser():
    if _rust is None:
        raise RuntimeError(MISSING_PARSER)
    return _rust


def read_header(path: Path) -> Header:
    """The replay's arena, match type, teams, players, scores and goals."""
    return header_from_properties(_parser().header(str(path)))


def read_frames(
    path: Path, pad_spots: list[tuple[float, float, float]]
) -> list[dict[str, Any]]:
    """Every network frame, in the order recorded.

    `pad_spots` are the arena's boost pads, which number the pickups. With none,
    the frames have no pickups. A frame is a dict:

    - "time": seconds into the recording
    - "ball": its position and velocity, each (x, y, z)
    - "cars": (row, team, position, velocity, angular velocity, rotation, boost,
      demolished) for each player's car. The row is the player's in the header,
      or a number past them for someone who left. The rotation is a quaternion
      (x, y, z, w), or None before the car sends one
    - "pickups": (pad, row, team, time) for each pad taken. The team can be None
    - "dodges": (row, torque) for each flip
    - "touches": the rows of the cars that touched the ball
    - "first_touches": the rows whose first-touch counter rose
    - "demos": (victim row, attacker row or None)
    """
    return _parser().frames(str(path), [tuple(spot) for spot in pad_spots])
