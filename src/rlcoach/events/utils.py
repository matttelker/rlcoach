"""Distance and speed for the kickoff and boost detectors."""

from __future__ import annotations

import math

from ..field_constants import Vec3


def distance_3d(pos1: Vec3, pos2: Vec3) -> float:
    """Calculate 3D Euclidean distance between two positions."""
    dx = pos1.x - pos2.x
    dy = pos1.y - pos2.y
    dz = pos1.z - pos2.z
    return math.sqrt(dx * dx + dy * dy + dz * dz)


def vector_magnitude(vec: Vec3) -> float:
    """Calculate magnitude of a 3D vector."""
    return math.sqrt(vec.x * vec.x + vec.y * vec.y + vec.z * vec.z)
