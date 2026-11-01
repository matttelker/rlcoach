from pathlib import Path

import pytest


def _has_rust_core():
    try:
        import rlreplay_rust  # type: ignore

        return bool(getattr(rlreplay_rust, "RUST_CORE", False))
    except Exception:
        return False


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
def test_rust_pad_registry_event_completeness():
    from rlcoach.parser import get_adapter

    adapter = get_adapter("rust")
    frames = adapter.parse_network(Path("testing_replay.replay"))

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
    assert len(collected_events) == 569

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
    from rlcoach.field_constants import FIELD
    from rlcoach.parser import get_adapter

    adapter = get_adapter("rust")
    frames = adapter.parse_network(Path("testing_replay.replay"))
    collected = [
        event
        for frame in frames.frames
        for event in frame.get("boost_pad_events", [])
        if event["status"] == "COLLECTED"
    ]

    assert {event["pad_id"] for event in collected} == set(range(34))
    assert sum(event["is_big"] for event in collected) > 50

    # A re-sent state would read as a second pickup inside the respawn window.
    last_collect: dict[int, float] = {}
    for event in collected:
        pad = FIELD.BOOST_PADS[event["pad_id"]]
        assert event["is_big"] == pad.is_big
        previous = last_collect.get(pad.pad_id)
        if previous is not None:
            respawn = 10.0 if pad.is_big else 4.0
            gap = event["timestamp"] - previous
            assert gap >= respawn - 0.15, f"pad {pad.pad_id} collected {gap:.2f}s apart"
        last_collect[pad.pad_id] = event["timestamp"]


@pytest.mark.skipif(not _has_rust_core(), reason="Rust core not available")
def test_location_component_events_do_not_break_pad_registry():
    from rlcoach.parser import get_adapter

    adapter = get_adapter("rust")
    frames = adapter.parse_network(Path("testing_replay.replay"))

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
