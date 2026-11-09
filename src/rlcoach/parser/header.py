"""The replay's header, from its properties as the Rust parser hands them over.

A header property is a plain value, a dict for a struct, or a list of dicts for
an array such as `PlayerStats` (one entry per player who finished) and `Goals`.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

from .types import GoalHeader, Header, PlayerInfo

SCOREBOARD = ("Score", "Goals", "Assists", "Saves", "Shots")
# What each platform's accounts are filed under. "Dingo" is Xbox and "NNX" is
# Switch. Any other platform goes by its name, such as "ps5" for OnlinePlatform_PS5
PLATFORMS = {
    "OnlinePlatform_Steam": "steam",
    "OnlinePlatform_Epic": "epic",
    "OnlinePlatform_PS3": "psn",
    "OnlinePlatform_PS4": "psn",
    "OnlinePlatform_Dingo": "xbox",
    "OnlinePlatform_NNX": "switch",
}
_DATE_FORMATS = ("%Y-%m-%d %H-%M-%S", "%Y-%m-%d:%H-%M")


def header_from_properties(properties: dict[str, Any]) -> Header:
    # A row without a name isn't a player. The parser skips it too, so the rows
    # number the same players in the frames
    players = [
        _player(row)
        for row in properties.get("PlayerStats") or []
        if isinstance(row.get("Name"), str)
    ]
    return Header(
        match_type=properties.get("MatchType"),
        map_name=properties.get("MapName"),
        team_size=_team_size(properties, players),
        team0_score=_int(properties.get("Team0Score")),
        team1_score=_int(properties.get("Team1Score")),
        started_at_utc=parse_replay_date(properties.get("Date")),
        recorded_by=properties.get("PlayerName"),
        players=players,
        goals=[
            GoalHeader(
                frame=goal.get("frame"),
                player_name=goal.get("PlayerName"),
                player_team=goal.get("PlayerTeam"),
            )
            for goal in properties.get("Goals") or []
        ],
    )


def _team_size(properties: dict[str, Any], players: list[PlayerInfo]) -> int:
    """The match's team size. Leavers have no row, so the rows can come up short,
    and only a header without `TeamSize` counts them."""
    if size := _int(properties.get("TeamSize")):
        return size
    rows = [sum(1 for p in players if p.team == team) for team in (0, 1)]
    return max(rows)


def _int(value: Any) -> int:
    return value if isinstance(value, int) else 0


def _player(row: dict[str, Any]) -> PlayerInfo:
    return PlayerInfo(
        name=row["Name"],
        team=_int(row.get("Team")),
        platform_ids=accounts(row),
        stats={key: row[key] for key in SCOREBOARD if key in row},
    )


def accounts(row: dict[str, Any]) -> dict[str, str]:
    """A player's account, from their `PlayerStats` row: {platform: account}.

    An Epic account is `PlayerID.EpicAccountId`. Every other platform's is a
    number, `PlayerID.Uid`, which `OnlineID` repeats, so a row without `PlayerID`
    still has it. Bots and Epic rows without `PlayerID` have none.
    """
    unique = row.get("PlayerID") or {}
    name = str(unique.get("Platform") or row.get("Platform") or "")
    platform = PLATFORMS.get(name, name.removeprefix("OnlinePlatform_").lower())
    if platform == "epic":
        account = unique.get("EpicAccountId")
    else:
        account = unique.get("Uid") or row.get("OnlineID")
    if not (platform and account) or platform == "unknown":
        return {}
    return {platform: str(account)}


def parse_replay_date(raw: Any, tz: _dt.tzinfo | None = None) -> str | None:
    """A header `Date` as a UTC ISO timestamp, or None.

    The header has the recording machine's clock with no timezone. It's read in
    `tz`, or this machine's timezone by default, so it's only as right as that.
    """
    if not isinstance(raw, str):
        return None
    for fmt in _DATE_FORMATS:
        try:
            recorded = _dt.datetime.strptime(raw.strip(), fmt)
            if tz is not None:
                recorded = recorded.replace(tzinfo=tz)
            started = recorded.astimezone(_dt.UTC)
        except ValueError, OSError, OverflowError:
            continue
        return started.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return None
