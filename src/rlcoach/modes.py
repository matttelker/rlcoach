"""Which playlist a game was in, and whether the coaching fits its arena.

Replay headers carry no playlist id any more. They give the match type
(online, tournament, private) and the team size, which pick the playlist, and
the arena. Modes such as Hoops have arenas of their own, so the arena's name
tells them apart. Each mode is one row of MODES: to coach Hoops, give its row
a playlist of its own, a field the mistake rules can use and its boost pads.
"""

from __future__ import annotations

from dataclasses import dataclass

from .parser.types import Header

EXTRA_MODE = "EXTRA_MODE"
PRIVATE = "PRIVATE"
UNKNOWN = "UNKNOWN"

# Online and tournament games, by players per team
TEAM_SIZE_PLAYLISTS = {1: "DUEL", 2: "DOUBLES", 3: "STANDARD", 4: "CHAOS"}

# The playlists with benchmarks and the dashboard's picks, in its order
COACHED_PLAYLISTS = ("STANDARD", "DOUBLES", "DUEL")


@dataclass(frozen=True)
class Mode:
    """A game mode, known by its arenas."""

    name: str
    arena_marker: str  # Text in the lowercased arena name, such as "hoops"
    # Where its online games are filed, or None to file them by team size
    playlist: str | None = None
    reviewed: bool = False  # The mistake rules fit its field
    # Its boost pads are Soccar's, so the parser can name the pad of each pickup
    soccar_pads: bool = True


SOCCAR = Mode("soccar", "", reviewed=True)
MODES = (
    Mode("hoops", "hoops", EXTRA_MODE, soccar_pads=False),
    Mode("dropshot", "shattershot", EXTRA_MODE, soccar_pads=False),
    Mode("knockout", "knockout", EXTRA_MODE),
    # Soccar on Rocket Labs' odd-shaped fields
    Mode("rocket labs", "labs_"),
)


def mode_of(map_name: str | None) -> Mode:
    """The mode an arena belongs to."""
    lowered = (map_name or "").lower()
    return next((m for m in MODES if m.arena_marker in lowered), SOCCAR)


def playlist_of(header: Header) -> str:
    """The playlist a replay's game was played in."""
    match_type = str(header.match_type or "").lower()
    if match_type in ("private", "offline"):
        return PRIVATE
    if match_type not in ("online", "tournament"):
        return UNKNOWN
    playlist = TEAM_SIZE_PLAYLISTS.get(header.team_size)
    if playlist is None:
        return UNKNOWN
    return mode_of(header.map_name).playlist or playlist
