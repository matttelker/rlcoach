"""Tests for reading when a replay was recorded."""

from datetime import timedelta, timezone

import pytest

from rlcoach.parser.rust_adapter import parse_replay_date
from rlcoach.parser.types import Header
from rlcoach.report import _utc_now_iso

EST = timezone(timedelta(hours=-5))


def test_converts_the_recorders_clock_to_utc():
    assert parse_replay_date("2026-10-31 23-56-53", EST) == "2026-11-01T04:56:53Z"


def test_reads_the_older_minute_precision_format():
    assert parse_replay_date("2016-08-19:12-04", EST) == "2016-08-19T17:04:00Z"


def test_ignores_surrounding_whitespace():
    assert parse_replay_date(" 2026-10-31 23-56-53\n", EST) == "2026-11-01T04:56:53Z"


@pytest.mark.parametrize("raw", [None, 20261031, "", "not a date", "2026-13-45 1-2-3"])
def test_unreadable_dates_return_none(raw):
    assert parse_replay_date(raw, EST) is None


def test_header_defaults_to_no_start_time():
    assert Header().started_at_utc is None


def test_utc_now_fallback_stays_a_valid_timestamp():
    assert _utc_now_iso().endswith("Z")
