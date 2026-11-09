"""Your settings, read from ~/.rlcoach/config.toml.

The file says who you are in replays, where Rocket League saves them, and how
the dashboard opens. Keys it doesn't know are ignored, so an old file still
loads.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .metrics import RANKS
from .modes import COACHED_PLAYLISTS

ACCOUNT_PATTERN = re.compile(r"^(steam|epic|psn|xbox|switch):[a-zA-Z0-9_-]+$")
DEFAULT_WATCH_FOLDER = "~/Documents/My Games/Rocket League/TAGame/Demos"
DEFAULT_DATA_DIR = "~/.rlcoach/data"
DEFAULT_RANK = "P1"

CONFIG_TEMPLATE = """\
# rlcoach settings

[identity]
# Your accounts as "platform:id", with platform one of steam, epic, psn, xbox
# or switch. Accounts are checked first, then names, which ignore case.
platform_ids = []
display_names = ["YourName"]
# Accounts whose replays you don't want loaded at all
excluded_names = []

[paths]
# Rocket League saves your replays here
watch_folder = "~/Documents/My Games/Rocket League/TAGame/Demos"
data_dir = "~/.rlcoach/data"

[preferences]
# Playlist the stats pages open on: STANDARD, DOUBLES or DUEL
primary_playlist = "STANDARD"
# Rank the benchmarks compare you with: G1 to G3 for Gold, then P1 to P3,
# D1 to D3, C1 to C3, or GC for every Grand Champion tier
target_rank = "P1"
# Decides which day a game belongs to, such as "America/New_York".
# Leave it out to use this computer's timezone.
# timezone = "America/New_York"
"""


class ConfigError(Exception):
    """The config file is missing or says something that can't be used."""


@dataclass
class IdentityConfig:
    platform_ids: list[str] = field(default_factory=list)
    display_names: list[str] = field(default_factory=list)
    excluded_names: list[str] = field(default_factory=list)


@dataclass
class PathsConfig:
    watch_folder: Path
    data_dir: Path


@dataclass
class PreferencesConfig:
    primary_playlist: str = "DOUBLES"
    target_rank: str = DEFAULT_RANK
    timezone: str | None = None


@dataclass
class RLCoachConfig:
    identity: IdentityConfig
    paths: PathsConfig
    preferences: PreferencesConfig

    @property
    def db_path(self) -> Path:
        return self.paths.data_dir / "rlcoach.db"

    def validate(self) -> None:
        """Raise ConfigError for the first setting that can't be used."""
        identity, prefs = self.identity, self.preferences
        if not identity.platform_ids and not identity.display_names:
            raise ConfigError(
                "Say who you are: [identity] needs a platform_id or a display_name"
            )
        for account in identity.platform_ids:
            if not ACCOUNT_PATTERN.match(account):
                raise ConfigError(
                    f"platform_id {account!r} isn't 'platform:id' with platform "
                    "one of steam, epic, psn, xbox or switch"
                )
        if prefs.target_rank not in RANKS:
            raise ConfigError(
                f"target_rank {prefs.target_rank!r} isn't one of {', '.join(RANKS)}"
            )
        if prefs.primary_playlist not in COACHED_PLAYLISTS:
            raise ConfigError(
                f"primary_playlist {prefs.primary_playlist!r} isn't one of "
                f"{', '.join(COACHED_PLAYLISTS)}"
            )
        if prefs.timezone is not None:
            try:
                ZoneInfo(prefs.timezone)
            except (ZoneInfoNotFoundError, ValueError) as e:
                raise ConfigError(
                    f"timezone {prefs.timezone!r} isn't an IANA name like "
                    "'America/New_York'"
                ) from e
        both = {n.casefold().strip() for n in identity.display_names} & {
            n.casefold().strip() for n in identity.excluded_names
        }
        if both:
            raise ConfigError(
                f"{', '.join(sorted(both))} can't be both a display_name and an "
                "excluded_name"
            )


def compute_play_date(played_at_utc: datetime, timezone: str | None) -> date:
    """The day a game was played on in your timezone, or this computer's."""
    zone = ZoneInfo(timezone) if timezone else datetime.now().astimezone().tzinfo
    return played_at_utc.astimezone(zone).date()


def load_config(path: Path) -> RLCoachConfig:
    """Read the config file. Raises ConfigError if there isn't one."""
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} isn't valid TOML: {e}") from e
    identity = data.get("identity", {})
    paths = data.get("paths", {})
    prefs = data.get("preferences", {})
    return RLCoachConfig(
        identity=IdentityConfig(
            platform_ids=list(identity.get("platform_ids", [])),
            display_names=list(identity.get("display_names", [])),
            excluded_names=list(identity.get("excluded_names", [])),
        ),
        paths=PathsConfig(
            watch_folder=Path(
                paths.get("watch_folder", DEFAULT_WATCH_FOLDER)
            ).expanduser(),
            data_dir=Path(paths.get("data_dir", DEFAULT_DATA_DIR)).expanduser(),
        ),
        preferences=PreferencesConfig(
            primary_playlist=prefs.get("primary_playlist", "DOUBLES"),
            target_rank=prefs.get("target_rank", DEFAULT_RANK),
            timezone=prefs.get("timezone"),
        ),
    )


def get_default_config_path() -> Path:
    return Path.home() / ".rlcoach" / "config.toml"
