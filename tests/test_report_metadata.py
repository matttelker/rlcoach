"""Unit tests for report metadata helpers."""

from rlcoach import report
from rlcoach.events import KickoffEvent, TimelineEvent
from rlcoach.parser.types import Header


class TestNormalizePlaylistId:
    def test_known_playlist_normalizes_without_warning(self):
        value, warnings = report._normalize_playlist_id("standard")
        assert value == "STANDARD"
        assert warnings == []

    def test_unknown_playlist_falls_back_to_unknown_with_warning(self):
        value, warnings = report._normalize_playlist_id("ranked_hoops")
        assert value == "UNKNOWN"
        assert warnings and "ranked_hoops" in warnings[0]


class TestApplyMapPlaylist:
    def test_extra_mode_arenas_leave_core_playlists(self):
        assert report._apply_map_playlist("DOUBLES", "HoopsStadium_P") == "EXTRA_MODE"
        assert report._apply_map_playlist("STANDARD", "ShatterShot_P") == "EXTRA_MODE"

    def test_core_arena_keeps_playlist(self):
        assert report._apply_map_playlist("DOUBLES", "Stadium_P") == "DOUBLES"

    def test_private_match_on_extra_mode_arena_stays_private(self):
        assert report._apply_map_playlist("PRIVATE", "HoopsStadium_P") == "PRIVATE"

    def test_missing_map_keeps_playlist(self):
        assert report._apply_map_playlist("STANDARD", None) == "STANDARD"


def _kickoff(phase: str) -> KickoffEvent:
    return KickoffEvent(phase=phase, t_start=0.0, players=[])


class TestWentToOvertime:
    def test_overtime_kickoff_means_overtime_without_a_header_flag(self):
        kickoffs = [_kickoff("INITIAL"), _kickoff("OT")]
        assert report._went_to_overtime(Header(overtime=None), kickoffs) is True

    def test_regulation_kickoffs_only_mean_no_overtime(self):
        kickoffs = [_kickoff("INITIAL"), _kickoff("INITIAL")]
        assert report._went_to_overtime(Header(overtime=None), kickoffs) is False

    def test_header_flag_counts_without_kickoffs(self):
        assert report._went_to_overtime(Header(overtime=True), []) is True

    def test_no_header_and_no_kickoffs_mean_no_overtime(self):
        assert report._went_to_overtime(None, []) is False


class TestTimelineEventToDict:
    def test_optional_fields_with_none_are_omitted(self):
        ev = TimelineEvent(t=1.0, type="KICKOFF")
        entry = report._timeline_event_to_dict(ev)
        assert entry == {"t": 1.0, "type": "KICKOFF"}
