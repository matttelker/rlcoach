"""Tests for checking replay files and naming them by hash."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest

from rlcoach.replay_file import (
    CRC_START,
    ReplayFileError,
    check_replay_file,
    file_hash,
    replay_crc,
)

REPLAY = Path("Replay_files/6804bd43-5415-49f4-b7d0-31b168c871ed.replay")


def _crc_bit_by_bit(data: bytes) -> int:
    """The checksum as Rocket League defines it, one bit at a time."""
    crc = CRC_START
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) if crc & 0x80000000 else crc << 1
            crc &= 0xFFFFFFFF
    return crc ^ 0xFFFFFFFF


def _replay_like(header: bytes, body: bytes, *, header_crc: int | None = None) -> bytes:
    """A file laid out like a replay: two sections, each length then checksum."""
    crc = replay_crc(header) if header_crc is None else header_crc
    return (
        struct.pack("<iI", len(header), crc)
        + header
        + struct.pack("<iI", len(body), replay_crc(body))
        + body
    )


@pytest.mark.parametrize(
    "data", [b"", b"a", b"TAGame.Replay_Soccar_TA", bytes(range(256)) * 3]
)
def test_the_fast_checksum_matches_the_definition(data):
    assert replay_crc(data) == _crc_bit_by_bit(data)


def test_a_real_replay_passes(tmp_path):
    check_replay_file(REPLAY)


def test_a_real_replays_stored_checksums_match_the_definition():
    data = REPLAY.read_bytes()
    length, stored = struct.unpack_from("<iI", data, 0)
    header = data[8 : 8 + length]
    assert replay_crc(header) == _crc_bit_by_bit(header) == stored


def test_one_changed_byte_is_caught(tmp_path):
    data = bytearray(REPLAY.read_bytes())
    data[len(data) // 2] ^= 0x01
    damaged = tmp_path / "damaged.replay"
    damaged.write_bytes(bytes(data))
    with pytest.raises(ReplayFileError, match="body checksum"):
        check_replay_file(damaged)


def test_a_wrong_header_checksum_is_caught(tmp_path):
    header = b"TAGame.Replay_Soccar_TA" + bytes(10_000)
    path = tmp_path / "bad.replay"
    path.write_bytes(_replay_like(header, b"body", header_crc=12345))
    with pytest.raises(ReplayFileError, match="header checksum"):
        check_replay_file(path)


def test_a_cut_short_file_is_caught(tmp_path):
    path = tmp_path / "short.replay"
    path.write_bytes(REPLAY.read_bytes()[:20_000])
    with pytest.raises(ReplayFileError, match="cut short"):
        check_replay_file(path)


def test_a_file_that_isnt_a_replay_is_caught(tmp_path):
    path = tmp_path / "notes.replay"
    path.write_bytes(b"hello " * 5_000)
    with pytest.raises(ReplayFileError, match="not a Rocket League replay"):
        check_replay_file(path)


def test_tiny_and_missing_files_are_caught(tmp_path):
    tiny = tmp_path / "tiny.replay"
    tiny.write_bytes(b"TAGame.Replay_")
    with pytest.raises(ReplayFileError, match="too small"):
        check_replay_file(tiny)
    with pytest.raises(ReplayFileError, match="not found"):
        check_replay_file(tmp_path / "gone.replay")


def test_the_hash_is_the_files_sha256(tmp_path):
    path = tmp_path / "x.replay"
    path.write_bytes(b"some bytes")
    assert file_hash(path) == hashlib.sha256(b"some bytes").hexdigest()
    with pytest.raises(ReplayFileError, match="not found"):
        file_hash(tmp_path / "gone.replay")
