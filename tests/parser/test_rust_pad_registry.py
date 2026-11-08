"""The Rust parser's boost pad events on a real replay."""

import pytest

from tests.fixtures import real_replays


def _has_rust_core():
    try:
        import rlreplay_rust  # type: ignore

        return bool(getattr(rlreplay_rust, "RUST_CORE", False))
    except Exception:
        return False


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
def test_rust_pad_registry_event_completeness():
    from rlcoach.parser import RustAdapter

    adapter = RustAdapter()
    frames = adapter.parse_network(real_replays.replay(real_replays.REGULATION))

    pad_events = []
    for frame in frames.frames:
        pad_events.extend(frame.get("boost_pad_events", []))

    assert pad_events, "expected boost pad events from Rust adapter"

    required_keys = {
        "pad_id",
        "is_big",
        "object_name",
        "timestamp",
        "status",
        "position",
    }
    for event in pad_events:
        missing = required_keys - event.keys()
        assert not missing, f"event missing keys {missing}: {event}"
        assert isinstance(event["pad_id"], int)
        assert isinstance(event["is_big"], bool)
        assert isinstance(event["timestamp"], float)
        assert event["status"] in {"COLLECTED", "RESPAWNED"}
        position = event["position"]
        for axis in ("x", "y", "z"):
            assert axis in position, f"missing {axis} in position payload"

    collected_events = [event for event in pad_events if event["status"] == "COLLECTED"]
    assert collected_events, "expected collected pad events"
    # Pin catches Location-arm dispatch regressions that drop pickup routing.
    assert len(collected_events) == 285

    for event in collected_events:
        assert "actor_id" in event, f"missing actor_id on collected event: {event}"
        if "instigator_actor_id" in event:
            assert isinstance(event["instigator_actor_id"], int)

    resolved_player = [event for event in collected_events if "player_id" in event]
    coverage = len(resolved_player) / len(collected_events)
    assert coverage >= 0.9, f"player_id resolution below threshold: {coverage:.2%}"


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
def test_rust_pad_registry_survives_checkpoints():
    """Pad actors re-spawn about every 10s and re-send their last state."""
    from rlcoach.field_constants import BOOST_PADS
    from rlcoach.parser import RustAdapter

    adapter = RustAdapter()
    frames = adapter.parse_network(real_replays.replay(real_replays.REGULATION))
    pad_events = [
        event for frame in frames.frames for event in frame.get("boost_pad_events", [])
    ]

    assert {event["pad_id"] for event in pad_events} == set(range(34))
    assert sum(event["is_big"] for event in pad_events) > 50

    # Statuses need not alternate: a car on a pad as it respawns collects with no
    # RESPAWNED between. A re-sent state is the one repeat that cannot be real.
    last_state: dict[int, int] = {}
    for event in pad_events:
        pad_id = event["pad_id"]
        assert event["is_big"] == BOOST_PADS[pad_id].is_big
        assert last_state.get(pad_id) != event["raw_state"], f"pad {pad_id} re-sent"
        last_state[pad_id] = event["raw_state"]


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
def test_location_component_events_do_not_break_pad_registry():
    from rlcoach.parser import RustAdapter

    adapter = RustAdapter()
    frames = adapter.parse_network(real_replays.replay(real_replays.REGULATION))

    pad_events = []
    component_events = []
    for frame in frames.frames:
        pad_events.extend(frame.get("boost_pad_events", []))
        component_events.extend(frame.get("component_events", []))

    assert pad_events, "Location-arm changes must preserve pad registry events"
    assert any(
        event.get("kind") in {"dodge_torque", "double_jump_impulse"}
        for event in component_events
    ), "fixture should exercise Location-arm component vector extraction"
