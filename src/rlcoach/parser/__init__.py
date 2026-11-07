"""Read replays with the Rust parser, the only one rlcoach has."""

from __future__ import annotations

from pathlib import Path

from .rust_adapter import RustAdapter
from .types import Header, NetworkFrames

_parser = RustAdapter()


def read_header(path: Path) -> Header:
    """The replay's header: arena, teams, players, scores and match type."""
    return _parser.parse_header(path)


def read_network(path: Path) -> NetworkFrames:
    """Every recorded frame, with the parser's own events on each."""
    return _parser.parse_network(path)
