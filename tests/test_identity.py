"""Tests for player ids from replay headers, and for picking you out."""

from __future__ import annotations

from rlcoach.config import IdentityConfig
from rlcoach.identity import (
    Me,
    build_alias_lookup,
    build_player_identities,
    sanitize_display_name,
    slugify_display_name,
)
from rlcoach.parser.types import PlayerInfo


def test_names_are_tidied():
    assert sanitize_display_name("  Jo \t  Smith\n") == "Jo Smith"
    assert sanitize_display_name("Ｆｕｌｌ") == "Full"  # NFKC folds wide letters
    assert sanitize_display_name(None) == "Unknown"
    assert sanitize_display_name("   ") == "Unknown"


def test_slugs_are_ascii_words_joined_by_hyphens():
    assert slugify_display_name("Skillz. †") == "skillz"
    assert slugify_display_name("Zoë  the_Great!") == "zoe-the-great"
    assert slugify_display_name("†††") == "player"


def test_an_account_names_the_player():
    [player] = build_player_identities(
        [PlayerInfo(name="night.", team=0, platform_ids={"steam": "76"})]
    )
    assert player.canonical_id == "steam:76"
    assert player.display_name == "night."
    assert player.team == "BLUE"
    assert player.platform_ids == {"steam": "76"}


def test_steam_comes_before_epic_and_odd_platforms_come_last():
    both = PlayerInfo(name="a", platform_ids={"epic": "e1", "steam": "s1"})
    odd = PlayerInfo(name="b", platform_ids={"wegame": "w1", "tencent": "t1"})
    ids = [p.canonical_id for p in build_player_identities([both, odd])]
    assert ids == ["steam:s1", "tencent:t1"]


def test_platform_names_are_lower_case_and_empty_accounts_dont_count():
    [player] = build_player_identities(
        [PlayerInfo(name="x", platform_ids={"Epic": " abc ", "steam": ""})]
    )
    assert player.canonical_id == "epic:abc"
    assert player.platform_ids == {"epic": "abc"}


def test_players_without_accounts_get_a_slug_id_and_repeats_get_a_number():
    players = [PlayerInfo(name="Rex", team=1), PlayerInfo(name="Rex", team=0)]
    first, second = build_player_identities(players)
    assert (first.canonical_id, first.team) == ("slug:rex", "ORANGE")
    assert (second.canonical_id, second.header_index) == ("slug:rex-2", 1)


def test_an_unknown_team_counts_as_blue():
    [player] = build_player_identities([PlayerInfo(name="x", team=None)])
    assert player.team == "BLUE"


def test_aliases_cover_every_name_the_frames_may_use():
    [player] = build_player_identities(
        [PlayerInfo(name="Jo", platform_ids={"steam": "9"})]
    )
    assert set(player.aliases) == {
        "steam:9",
        "9",
        "jo",
        "slug:jo",
        "player_0",
    }
    assert build_alias_lookup([player])["player_0"] == "steam:9"


def test_a_shared_alias_belongs_to_the_first_player():
    players = build_player_identities([PlayerInfo(name="Jo"), PlayerInfo(name="Jo")])
    assert build_alias_lookup(players)["jo"] == "slug:jo"


def _me(**config) -> Me:
    return Me(IdentityConfig(**config))


def test_you_are_found_by_account_before_name():
    players = build_player_identities(
        [
            PlayerInfo(name="midnightmelker", platform_ids={"steam": "1"}),
            PlayerInfo(name="Someone", platform_ids={"epic": "me"}),
        ]
    )
    me = _me(platform_ids=["epic:me"], display_names=["midnightmelker"])
    assert me.find(players).display_name == "Someone"


def test_names_match_without_case_or_spaces():
    players = build_player_identities([PlayerInfo(name="MidnightMelker")])
    assert _me(display_names=[" midnightmelker "]).find(players) is not None
    assert _me(display_names=["other"]).find(players) is None


def test_is_me_and_excluded_accounts():
    me = _me(platform_ids=["epic:me"], display_names=["Me"], excluded_names=["Kid"])
    assert me.is_me("epic:me", "anything")
    assert me.is_me("steam:1", "ME")
    assert not me.is_me("steam:1", "Other")
    assert me.is_excluded(" kid ")
    assert not me.is_excluded("Me")
