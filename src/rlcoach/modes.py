"""Which playlist a game was in, and whether the coaching fits its arena.

The game sends its own number for the playlist once the match starts, which
tells a ranked game from a casual one. Replay headers carry no playlist id any
more: they give the match type (online, tournament, private) and the team
size, which pick the playlist for a replay without the number, and the arena.
Modes such as Hoops have arenas of their own, so the arena's name
tells them apart. Each mode is one row of MODES: to coach Hoops, give its row
a playlist of its own, a field the mistake rules can use and its boost pads.
"""

from __future__ import annotations

from dataclasses import dataclass

from .parser.types import Header

EXTRA_MODE = "EXTRA_MODE"
PRIVATE = "PRIVATE"
UNKNOWN = "UNKNOWN"
# Casual games, of any team size. They aren't matched by rank, so they stay
# out of the coached playlists and the rank comparisons
CASUAL = "CASUAL"

# The game's playlist numbers for ranked Soccar, and for casual
RANKED_PLAYLISTS = {10: "DUEL", 11: "DOUBLES", 13: "STANDARD"}
CASUAL_PLAYLISTS = frozenset({1, 2, 3, 4})

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


def playlist_of(header: Header, playlist_id: int | None = None) -> str:
    """The playlist a replay's game was played in.

    `playlist_id` is the game's own number, where the replay has it. Any other
    number, such as a tournament's or an extra mode's, goes by the header.
    """
    if playlist_id in RANKED_PLAYLISTS:
        return RANKED_PLAYLISTS[playlist_id]
    if playlist_id in CASUAL_PLAYLISTS:
        return CASUAL
    match_type = str(header.match_type or "").lower()
    if match_type in ("private", "offline"):
        return PRIVATE
    if match_type not in ("online", "tournament"):
        return UNKNOWN
    playlist = TEAM_SIZE_PLAYLISTS.get(header.team_size)
    if playlist is None:
        return UNKNOWN
    return mode_of(header.map_name).playlist or playlist
