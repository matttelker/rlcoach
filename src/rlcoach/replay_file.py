"""Check that a file is a whole Rocket League replay, and name it by its hash.

A replay is two sections, the header and the body, and each starts with its
length and a checksum. The parser only checks those checksums when it fails,
so a file damaged in a way it can still read gets caught here.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from pathlib import Path

MIN_BYTES = 10_000
MAX_BYTES = 50_000_000
# Every replay's header names its class, such as TAGame.Replay_Soccar_TA
REPLAY_MARKER = b"TAGame.Replay_"
MARKER_SEARCH_BYTES = 2048

# Rocket League's checksum is CRC-32 over polynomial 0x04C11DB7, read most
# significant bit first, starting from 0x10340DFE and inverted at the end.
# zlib has the same polynomial read least significant bit first, so it gives
# the same checksum over mirrored bytes once its result is mirrored back.
CRC_START = 0x10340DFE
_MIRRORED_BYTES = bytes(int(f"{b:08b}"[::-1], 2) for b in range(256))


class ReplayFileError(ValueError):
    """The file is missing, an odd size, not a replay, or damaged."""


def _mirror32(value: int) -> int:
    return int(f"{value:032b}"[::-1], 2)


def replay_crc(data: bytes) -> int:
    """Rocket League's checksum of one section of a replay."""
    seed = _mirror32(CRC_START) ^ 0xFFFFFFFF
    return _mirror32(zlib.crc32(data.translate(_MIRRORED_BYTES), seed))


def file_hash(path: Path) -> str:
    """The file's SHA-256, which is also the replay's id in the database."""
    try:
        with path.open("rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()
    except FileNotFoundError:
        raise ReplayFileError(f"Replay file not found: {path}") from None
    except OSError as e:
        raise ReplayFileError(f"Couldn't read {path}: {e}") from e


def _section(data: bytes, start: int, name: str, path: Path) -> int:
    """Check one length-prefixed section and return where the next one starts."""
    if start + 8 > len(data):
        raise ReplayFileError(f"{path.name} ends before its {name}")
    length, expected = struct.unpack_from("<iI", data, start)
    end = start + 8 + length
    if length <= 0 or end > len(data):
        raise ReplayFileError(f"{path.name} is cut short in its {name}")
    if replay_crc(data[start + 8 : end]) != expected:
        raise ReplayFileError(f"{path.name} is damaged: its {name} checksum is wrong")
    return end


def check_replay_file(path: Path) -> None:
    """Raise ReplayFileError unless the file is a whole, undamaged replay."""
    try:
        size = path.stat().st_size
        if not path.is_file():
            raise ReplayFileError(f"{path} is not a file")
        if size < MIN_BYTES:
            raise ReplayFileError(f"{path.name} is too small to be a replay")
        if size > MAX_BYTES:
            raise ReplayFileError(f"{path.name} is too big to be a replay")
        data = path.read_bytes()
    except FileNotFoundError:
        raise ReplayFileError(f"Replay file not found: {path}") from None
    except OSError as e:
        raise ReplayFileError(f"Couldn't read {path}: {e}") from e

    if REPLAY_MARKER not in data[:MARKER_SEARCH_BYTES]:
        raise ReplayFileError(f"{path.name} is not a Rocket League replay")
    body = _section(data, 0, "header", path)
    _section(data, body, "body", path)
