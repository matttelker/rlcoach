"""What the parser raises when it can't read a replay."""

from __future__ import annotations


class HeaderParseError(ValueError):
    """The parser couldn't read a replay's header."""

    def __init__(self, path: str, reason: str | None = None):
        message = f"Failed to parse header from replay: {path}"
        super().__init__(f"{message} ({reason})" if reason else message)
