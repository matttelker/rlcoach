"""Tests for reading and checking the config file."""

from __future__ import annotations

import tomllib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from rlcoach.config import (
    CONFIG_TEMPLATE,
    ConfigError,
    IdentityConfig,
    PathsConfig,
    PreferencesConfig,
    RLCoachConfig,
    compute_play_date,
    get_default_config_path,
    load_config,
)


def _write(tmp_path, text):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _config(**preferences):
    return RLCoachConfig(
        identity=IdentityConfig(platform_ids=["epic:abc"]),
        paths=PathsConfig(watch_folder=Path("w"), data_dir=Path("d")),
        preferences=PreferencesConfig(**preferences),
    )


def test_a_full_file_loads_every_setting(tmp_path):
    path = _write(
        tmp_path,
        """
[identity]
platform_ids = ["steam:123"]
display_names = ["Me"]
excluded_names = ["Smurf"]

[paths]
watch_folder = "C:/Demos"
data_dir = "~/rl-data"

[preferences]
primary_playlist = "STANDARD"
target_rank = "G3"
timezone = "Europe/London"

[teammates]
old_section = "ignored"
""",
    )
    config = load_config(path)
    assert config.identity == IdentityConfig(["steam:123"], ["Me"], ["Smurf"])
    assert config.paths.watch_folder == Path("C:/Demos")
    assert config.paths.data_dir == Path.home() / "rl-data"
    assert config.db_path == Path.home() / "rl-data" / "rlcoach.db"
    assert config.preferences == PreferencesConfig("STANDARD", "G3", "Europe/London")
    config.validate()


def test_missing_settings_take_their_defaults(tmp_path):
    config = load_config(_write(tmp_path, '[identity]\ndisplay_names = ["Me"]\n'))
    assert config.preferences == PreferencesConfig("DOUBLES", "P1", None)
    assert config.paths.data_dir == Path.home() / ".rlcoach" / "data"
    assert config.paths.watch_folder.name == "Demos"


def test_the_template_is_valid_toml_that_loads(tmp_path):
    tomllib.loads(CONFIG_TEMPLATE)
    config = load_config(_write(tmp_path, CONFIG_TEMPLATE))
    config.validate()
    assert config.identity.display_names == ["YourName"]


def test_a_missing_or_broken_file_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.toml")
    with pytest.raises(ConfigError, match="isn't valid TOML"):
        load_config(_write(tmp_path, "[identity\n"))


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (
            RLCoachConfig(
                IdentityConfig(),
                PathsConfig(Path("w"), Path("d")),
                PreferencesConfig(),
            ),
            "Say who you are",
        ),
        (
            RLCoachConfig(
                IdentityConfig(platform_ids=["origin:abc"]),
                PathsConfig(Path("w"), Path("d")),
                PreferencesConfig(),
            ),
            "isn't 'platform:id'",
        ),
        (_config(target_rank="Diamond"), "target_rank 'Diamond'"),
        (_config(target_rank="GC1"), "isn't one of G1, G2, .* C3, GC"),
        (_config(primary_playlist="HOOPS"), "primary_playlist 'HOOPS'"),
        (_config(timezone="Mars/Olympus"), "timezone 'Mars/Olympus'"),
        (
            RLCoachConfig(
                IdentityConfig(display_names=["Me "], excluded_names=["me"]),
                PathsConfig(Path("w"), Path("d")),
                PreferencesConfig(),
            ),
            "both a display_name and an excluded_name",
        ),
    ],
)
def test_validate_names_the_bad_setting(config, message):
    with pytest.raises(ConfigError, match=message):
        config.validate()


def test_the_play_date_is_the_day_in_your_timezone():
    late = datetime(2026, 3, 1, 3, 30, tzinfo=UTC)
    assert compute_play_date(late, "America/New_York") == date(2026, 2, 28)
    assert compute_play_date(late, "Europe/London") == date(2026, 3, 1)
    assert isinstance(compute_play_date(late, None), date)


def test_the_default_config_lives_in_your_home_folder():
    assert get_default_config_path() == Path.home() / ".rlcoach" / "config.toml"
