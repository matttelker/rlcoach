"""Detection thresholds and constants for event detection.

All numeric constants used by event detectors are centralized here
for easy tuning and documentation.
"""

from __future__ import annotations

from ..field_constants import FIELD
from .types import PadEnvelope

BOOST_PICKUP_MIN_GAIN = 1.0  # Minimum net gain to record a pickup event
BOOST_HISTORY_WINDOW_S = 0.45
BOOST_HISTORY_MAX_SAMPLES = 18
BIG_PAD_EXTRA_RADIUS = 220.0
SMALL_PAD_EXTRA_RADIUS = 140.0
BIG_PAD_RESPAWN_S = 10.0
SMALL_PAD_RESPAWN_S = 4.0
PAD_RESPAWN_TOLERANCE = 0.15
BOOST_PICKUP_MERGE_WINDOW = 0.6
DEBUG_BOOST_ENV = "RLCOACH_DEBUG_BOOST_EVENTS"
BIG_PAD_MIN_GAIN = 70.0
RESPAWN_BOOST_AMOUNT = 33.0
RESPAWN_DISTANCE_THRESHOLD = 800.0
CHAIN_PAD_RADIUS = 1500.0
MIN_PAD_EVENT_COVERAGE = 0.5  # Share of boost-delta pickups pad events must match

PAD_NEUTRAL_TOLERANCE = 100.0  # Only halfway-line pads; the next row is 1000uu out

MIN_ORIENTATION_SAMPLES = 5

PAD_ENVELOPES: dict[int, PadEnvelope] = {}
for _pad in FIELD.BOOST_PADS:
    _base_radius = _pad.radius + (
        BIG_PAD_EXTRA_RADIUS if _pad.is_big else SMALL_PAD_EXTRA_RADIUS
    )
    _height_tol = 220.0 if _pad.is_big else 150.0
    _max_distance = _base_radius + (650.0 if _pad.is_big else 420.0)
    PAD_ENVELOPES[_pad.pad_id] = PadEnvelope(
        radius=_base_radius, max_distance=_max_distance, height_tolerance=_height_tol
    )
