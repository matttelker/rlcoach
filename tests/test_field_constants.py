"""Tests for the field's size and boost pads."""

from __future__ import annotations

from rlcoach.field_constants import BOOST_PADS, Vec3


def test_soccar_has_six_big_pads_and_28_small_ones():
    assert [pad.pad_id for pad in BOOST_PADS] == list(range(34))
    big = [pad for pad in BOOST_PADS if pad.is_big]
    assert len(big) == 6 and all(pad.position.z == 73.0 for pad in big)
    small = [pad for pad in BOOST_PADS if not pad.is_big]
    assert all(pad.position.z == 70.0 for pad in small)
    # Each half has as many as the other
    assert sum(pad.position.y < 0 for pad in BOOST_PADS) == sum(
        pad.position.y > 0 for pad in BOOST_PADS
    )


def test_vectors_add_subtract_and_scale():
    a, b = Vec3(1.0, 2.0, 3.0), Vec3(0.5, -1.0, 2.0)
    assert a + b == Vec3(1.5, 1.0, 5.0)
    assert a - b == Vec3(0.5, 3.0, 1.0)
    assert a * 2.0 == Vec3(2.0, 4.0, 6.0)
