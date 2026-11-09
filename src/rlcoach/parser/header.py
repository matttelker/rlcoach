"""The replay's header, from its properties as the Rust parser hands them over.

A header property is a plain value, a dict for a struct, or a list of dicts for
an array such as `PlayerStats` (one entry per player who finished) and `Goals`.
"""

from __future__ import annotations

import datetime as _dt
from collections import Counter
from typing import Any

from .types import GoalHeader, Header, PlayerInfo

SCOREBOARD = ("Score", "Goals", "Assists", "Saves", "Shots")
# The platforms an account is filed under by its own name. Other platforms, such
# as "OnlinePlatform_PS4", go by their whole name in lower case
PLATFORMS = {"OnlinePlatform_Steam": "steam", "OnlinePlatform_Epic": "epic"}
_DATE_FORMATS = ("%Y-%m-%d %H-%M-%S", "%Y-%m-%d:%H-%M")


def header_from_properties(properties: dict[str, Any]) -> Header:
    # A row without a name isn't a player. The parser skips it too, so the rows
    # number the same players in the frames
    players = [
        _player(row)
        for row in properties.get("PlayerStats") or []
        if isinstance(row.get("Name"), str)
    ]
    # The team size is the bigger team's row count. Leavers have no row
    by_team = Counter(player.team for player in players)
    team_size = max(by_team.values()) if by_team else _int(properties.get("TeamSize"))
    return Header(
        match_type=properties.get("MatchType"),
        map_name=properties.get("MapName"),
        team_size=team_size,
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
    """A player's accounts, from their `PlayerStats` row.

    `PlayerID.Uid` is the account number on Steam, PlayStation, Xbox and Switch
    alike, and has always been stored as "steam", so every such player's id is
    `steam:<uid>`. A row without `PlayerID` has only `OnlineID`, filed under its
    platform's name, such as "onlineplatform_ps4".
    """
    found: dict[str, str] = {}
    unique = row.get("PlayerID") or {}
    if unique.get("Uid"):
        found["steam"] = str(unique["Uid"])
    if unique.get("EpicAccountId"):
        found["epic"] = str(unique["EpicAccountId"])
    psn = ((unique.get("NpId") or {}).get("Handle") or {}).get("Data")
    if psn:
        found["psn"] = str(psn)
    platform = str(row.get("Platform") or "")
    platform = PLATFORMS.get(platform, platform.lower())
    if not found and row.get("OnlineID") and platform:
        found[platform] = str(row["OnlineID"])
    return found


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
