"""Who is who in a replay, and which of them is you.

The header lists the players. Each gets an id that stays the same from game to
game: their platform account where the header gives one, otherwise a slug of
their name. Your config names your accounts and names, which picks you out.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import IdentityConfig
    from .parser.types import PlayerInfo

# When a player has several accounts, the first of these names them
PLATFORM_ORDER = (
    "steam",
    "epic",
    "psn",
    "ps4",
    "ps5",
    "xbox",
    "xboxone",
    "xboxseries",
    "switch",
    "nintendo",
)
TEAMS = {0: "BLUE", 1: "ORANGE"}


@dataclass(frozen=True)
class PlayerIdentity:
    """One player in one replay's header."""

    canonical_id: str  # The id the database stores, such as "epic:abc123"
    display_name: str
    team: str  # "BLUE" or "ORANGE"
    platform_ids: dict[str, str]  # {"epic": "abc123"}
    slug: str
    header_index: int  # Position in the header's player list
    aliases: tuple[str, ...]  # Every other id the frames may use for them


def sanitize_display_name(name: str | None) -> str:
    """A name with its whitespace tidied, or "Unknown" if there's nothing left."""
    text = " ".join(unicodedata.normalize("NFKC", str(name or "")).split())
    return text or "Unknown"


def slugify_display_name(name: str | None) -> str:
    """Lowercase ASCII letters and digits joined by hyphens, such as "jo-n-1"."""
    folded = unicodedata.normalize("NFKD", sanitize_display_name(name).lower())
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", ascii_only).strip("-") or "player"


def _split_account(account: str | None) -> tuple[str, str] | None:
    """Read "epic:abc" or "epic|abc" as ("epic", "abc")."""
    text = str(account or "").strip()
    delimiter = ":" if ":" in text else "|" if "|" in text else None
    if delimiter is None:
        return None
    platform, _, value = text.partition(delimiter)
    platform, value = platform.strip().lower(), value.strip()
    return (platform, value) if platform and value else None


def _accounts(player: PlayerInfo) -> dict[str, str]:
    accounts = {
        str(platform).lower(): str(value).strip()
        for platform, value in (player.platform_ids or {}).items()
        if value and str(value).strip()
    }
    split = _split_account(player.platform_id)
    if split is not None:
        accounts.setdefault(*split)
    return accounts


def _preferred_id(accounts: dict[str, str], slug: str) -> str:
    for platform in PLATFORM_ORDER:
        if accounts.get(platform):
            return f"{platform}:{accounts[platform]}"
    if accounts:
        platform = min(accounts)
        return f"{platform}:{accounts[platform]}"
    return f"slug:{slug}"


def build_player_identities(players: Iterable[PlayerInfo]) -> list[PlayerIdentity]:
    """Give each header player an id, keeping ids unique within the replay."""
    identities: list[PlayerIdentity] = []
    taken: set[str] = set()
    for index, player in enumerate(players):
        accounts = _accounts(player)
        slug = slugify_display_name(player.name)
        wanted = _preferred_id(accounts, slug)
        player_id, suffix = wanted, 2
        while player_id in taken:
            player_id, suffix = f"{wanted}-{suffix}", suffix + 1
        taken.add(player_id)

        aliases = {player_id, slug, f"slug:{slug}", f"player_{index}"}
        if player.platform_id:
            aliases.add(str(player.platform_id).strip())
        for platform, value in accounts.items():
            aliases.update((value, f"{platform}:{value}"))
        team = player.team if isinstance(player.team, int) else 0
        identities.append(
            PlayerIdentity(
                canonical_id=player_id,
                display_name=sanitize_display_name(player.name),
                team=TEAMS.get(team, "BLUE"),
                platform_ids=accounts,
                slug=slug,
                header_index=index,
                aliases=tuple(sorted(alias for alias in aliases if alias)),
            )
        )
    return identities


def build_alias_lookup(identities: Iterable[PlayerIdentity]) -> dict[str, str]:
    """Map every alias to its player's id. The first player keeps a shared alias."""
    lookup: dict[str, str] = {}
    for identity in identities:
        for alias in identity.aliases:
            lookup.setdefault(alias, identity.canonical_id)
    return lookup


def _folded(name: str) -> str:
    return name.casefold().strip()


class Me:
    """Picks you out of a replay from your config's accounts and names.

    Accounts win over names, so a stranger who shares your name never counts
    as you when your account is in the game.
    """

    def __init__(self, config: IdentityConfig):
        self._accounts = set(config.platform_ids)
        self._names = {_folded(name) for name in config.display_names}
        self._excluded = {_folded(name) for name in config.excluded_names}

    def is_me(self, player_id: str, display_name: str) -> bool:
        return player_id in self._accounts or _folded(display_name) in self._names

    def find(self, players: Iterable[PlayerIdentity]) -> PlayerIdentity | None:
        """You in this replay, or None."""
        players = list(players)
        by_account = (p for p in players if p.canonical_id in self._accounts)
        by_name = (p for p in players if _folded(p.display_name) in self._names)
        return next(by_account, None) or next(by_name, None)

    def is_excluded(self, display_name: str) -> bool:
        """One of the accounts whose games you don't want loaded."""
        return _folded(display_name) in self._excluded
