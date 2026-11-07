"""Tests for version helpers."""

from rlcoach import version


def test_package_version_getter_returns_the_constant():
    assert version.get_package_version() == version.PACKAGE_VERSION
