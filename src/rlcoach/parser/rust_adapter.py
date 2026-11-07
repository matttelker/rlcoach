"""Read replays with the Rust parser, rlreplay_rust (boxcars through pyo3).

It's the only parser. Without it nothing can be read, so a missing build
raises rather than falling back to the header alone.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import replace
from pathlib import Path
from typing import Any

from .errors import HeaderParseError
from .types import (
    GoalHeader,
    Header,
    Highlight,
    NetworkDiagnostics,
    NetworkFrames,
    PlayerInfo,
)

try:
    import rlreplay_rust as _rust
except ImportError:  # pragma: no cover - only before the parser is built
    _rust = None  # type: ignore

MISSING_PARSER = "the Rust parser rlreplay_rust isn't installed; see AGENTS.md"

_REPLAY_DATE_FORMATS = ("%Y-%m-%d %H-%M-%S", "%Y-%m-%d:%H-%M")


def parse_replay_date(raw: Any, tz: _dt.tzinfo | None = None) -> str | None:
    """Convert a replay header Date to a UTC ISO timestamp.

    The header stores the recording machine's clock with no timezone. It is
    read in ``tz``, or this machine's timezone by default, so the result is
    only as accurate as that assumption.
    """
    if not isinstance(raw, str):
        return None
    for fmt in _REPLAY_DATE_FORMATS:
        try:
            recorded = _dt.datetime.strptime(raw.strip(), fmt)
            if tz is not None:
                recorded = recorded.replace(tzinfo=tz)
            started = recorded.astimezone(_dt.UTC)
        except ValueError, OSError, OverflowError:
            continue
        return started.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return None


def _read_started_at_utc(path: Path) -> str | None:
    """Read when a replay was recorded, or None if the header lacks it."""
    try:
        return parse_replay_date(_rust.header_property(str(path), "Date"))
    except Exception:
        return None


class RustAdapter:
    """Header and frames from the Rust parser, as the Python types."""

    def _header_from_rust_dict(self, d: dict[str, Any]) -> Header:
        # Convert rust dict to Header dataclass
        players: list[PlayerInfo] = []
        for raw_player in d.get("players", []) or []:
            name = raw_player.get("name", "Unknown")
            team = raw_player.get("team")
            stats = raw_player.get("stats") or {}

            platform_id, platform_ids = self._extract_platform_ids(stats)
            camera_settings = self._extract_camera_settings(stats)
            loadout = self._extract_loadout(stats)
            score = (
                stats.get("Score")
                if isinstance(stats.get("Score"), (int, float))
                else 0
            )

            normalized_stats: dict[str, Any] = {}
            if isinstance(stats, dict):
                for key, value in stats.items():
                    if isinstance(value, dict) and "value" in value:
                        normalized_stats[key] = value.get("value")
                    else:
                        normalized_stats[key] = value

            players.append(
                PlayerInfo(
                    name=name,
                    team=team,
                    platform_id=platform_id,
                    score=int(score or 0),
                    platform_ids=platform_ids,
                    camera_settings=camera_settings,
                    loadout=loadout,
                    stats=normalized_stats,
                )
            )
        goals = []
        for g in d.get("goals", []) or []:
            goals.append(
                GoalHeader(
                    frame=int(g.get("frame")) if g.get("frame") is not None else None,
                    player_name=g.get("player_name"),
                    player_team=(
                        int(g.get("player_team"))
                        if g.get("player_team") is not None
                        else None
                    ),
                )
            )
        highlights = []
        for h in d.get("highlights", []) or []:
            highlights.append(
                Highlight(
                    frame=int(h.get("frame")) if h.get("frame") is not None else None,
                    ball_name=h.get("ball_name"),
                    car_name=h.get("car_name"),
                )
            )
        # Use warnings as provided by Rust core; avoid adding any *_stub markers
        warnings = list(d.get("quality_warnings", []))
        mutators = d.get("mutators", {})
        if not isinstance(mutators, dict):
            mutators = {}
        return Header(
            playlist_id=d.get("playlist_id"),
            map_name=d.get("map_name"),
            team_size=int(d.get("team_size", 0) or 0),
            team0_score=int(d.get("team0_score", 0) or 0),
            team1_score=int(d.get("team1_score", 0) or 0),
            match_length=float(d.get("match_length", 0.0) or 0.0),
            engine_build=d.get("engine_build"),
            match_guid=d.get("match_guid"),
            started_at_utc=d.get("started_at_utc"),
            declared_record_fps=(
                float(d["declared_record_fps"])
                if d.get("declared_record_fps") is not None
                else None
            ),
            overtime=d.get("overtime"),
            mutators=mutators,
            players=players,
            goals=goals,
            highlights=highlights,
            quality_warnings=warnings,
        )

    @staticmethod
    def _extract_platform_ids(
        stats: dict[str, Any],
    ) -> tuple[str | None, dict[str, str]]:
        platform_map = {
            "OnlinePlatform_Steam": "steam",
            "OnlinePlatform_Epic": "epic",
            "OnlinePlatform_Psn": "psn",
            "OnlinePlatform_Xbox": "xbox",
            "OnlinePlatform_Switch": "switch",
            "OnlinePlatform_WeGame": "wegame",
        }

        platform_ids: dict[str, str] = {}
        primary_platform_id: str | None = None

        # Extract platform type from Platform struct
        platform_struct = stats.get("Platform")
        primary_platform_key = None
        if isinstance(platform_struct, dict):
            raw_value = platform_struct.get("value") or platform_struct.get("Platform")
            if isinstance(raw_value, str):
                primary_platform_key = platform_map.get(raw_value, raw_value.lower())

        # Try PlayerID struct first (newer format), then UniqueId (boxcars format)
        player_id_struct = stats.get("PlayerID") or stats.get("UniqueId")
        if isinstance(player_id_struct, dict):
            # Steam UID - only use if non-zero (0 means missing/placeholder)
            uid = player_id_struct.get("Uid")
            if uid is not None and int(uid) != 0:
                platform_ids.setdefault("steam", str(uid))
                if primary_platform_key == "steam":
                    primary_platform_id = str(uid)

            # Epic Account ID
            epic_id = player_id_struct.get("EpicAccountId")
            if epic_id:
                platform_ids["epic"] = str(epic_id)
                if primary_platform_key == "epic":
                    primary_platform_id = str(epic_id)

            # PSN ID (nested structure)
            npid = player_id_struct.get("NpId")
            if isinstance(npid, dict):
                handle = npid.get("Handle")
                if isinstance(handle, dict):
                    data = handle.get("Data")
                    if data:
                        platform_ids["psn"] = str(data)
                        if primary_platform_key == "psn":
                            primary_platform_id = str(data)

            # Remote ID (another format used by boxcars)
            remote_id = player_id_struct.get("Remote")
            if isinstance(remote_id, dict):
                for rid_key, rid_val in remote_id.items():
                    if isinstance(rid_val, dict):
                        # Handle nested Remote structs like Steam(123456)
                        for _inner_k, inner_v in rid_val.items():
                            if inner_v and str(inner_v) != "0":
                                platform = rid_key.lower()
                                platform_ids.setdefault(platform, str(inner_v))
                                if primary_platform_id is None:
                                    primary_platform_id = str(inner_v)
                                    primary_platform_key = platform
                    elif rid_val and str(rid_val) != "0":
                        platform = rid_key.lower()
                        platform_ids.setdefault(platform, str(rid_val))
                        if primary_platform_id is None:
                            primary_platform_id = str(rid_val)
                            primary_platform_key = platform

        # Fallback: OnlineID (older replays)
        online_id = stats.get("OnlineID")
        if (
            primary_platform_id is None
            and online_id is not None
            and str(online_id) != "0"
        ):
            primary_platform_id = str(online_id)
            if primary_platform_key and primary_platform_key not in platform_ids:
                platform_ids[primary_platform_key] = primary_platform_id

        return primary_platform_id, platform_ids

    @staticmethod
    def _extract_camera_settings(stats: dict[str, Any]) -> dict[str, float] | None:
        camera_struct = stats.get("CameraSettings")
        if not isinstance(camera_struct, dict):
            return None

        result: dict[str, float] = {}
        for key, value in camera_struct.items():
            if key.startswith("_"):
                continue
            if isinstance(value, (int, float)):
                normalized_key = (
                    key.replace("Camera", "").replace("Settings", "").strip("_")
                )
                normalized_key = normalized_key or key
                result[normalized_key.lower()] = float(value)
        return result or None

    @staticmethod
    def _extract_loadout(stats: dict[str, Any]) -> dict[str, Any]:
        for key in ("Loadout", "PlayerLoadout", "LoadoutPaint", "LoadoutPaints"):
            loadout_struct = stats.get(key)
            if isinstance(loadout_struct, dict):
                loadout = {}
                for lk, lv in loadout_struct.items():
                    if lk.startswith("_"):
                        continue
                    loadout[lk.lower()] = lv
                if loadout:
                    return loadout
        return {}

    def parse_header(self, path: Path) -> Header:
        if _rust is None:
            raise HeaderParseError(str(path), MISSING_PARSER)
        try:
            d = _rust.parse_header(str(path))  # returns dict-like
            if not isinstance(d, dict):  # defensive check
                raise HeaderParseError(str(path), "Rust core returned non-dict header")
            d["started_at_utc"] = _read_started_at_utc(path)
            return self._header_from_rust_dict(d)
        except Exception as e:  # normalize to HeaderParseError
            raise HeaderParseError(str(path), f"Rust adapter failed: {e}") from e

    def parse_network(self, path: Path) -> NetworkFrames:
        if _rust is None:
            raise RuntimeError(MISSING_PARSER)
        parsed, frames = self._parse_boxcars_network(path)
        self._dedupe_frame_players(frames)
        diagnostics = self._build_diagnostics(parsed.get("diagnostics"), ["boxcars"])
        if diagnostics.frames_emitted is None:
            diagnostics = replace(diagnostics, frames_emitted=len(frames))
        network = self._build_network_frames(
            frames, self._normalize_player_metadata(parsed.get("player_metadata"))
        )
        object.__setattr__(network, "diagnostics", diagnostics)
        return network

    @staticmethod
    def _coerce_frames(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [frame for frame in payload if isinstance(frame, dict)]
        try:
            frames = list(payload)
        except Exception:
            return []
        return [frame for frame in frames if isinstance(frame, dict)]

    def _parse_boxcars_network(
        self, path: Path
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        try:
            if hasattr(_rust, "parse_network_with_diagnostics"):
                parsed = _rust.parse_network_with_diagnostics(str(path))
                if not isinstance(parsed, dict):
                    parsed = {
                        "frames": [],
                        "diagnostics": {
                            "status": "degraded",
                            "error_code": "boxcars_network_error",
                            "error_detail": "Rust parser returned non-dict payload",
                            "frames_emitted": 0,
                        },
                    }
            else:
                frames_payload = _rust.iter_frames(str(path))
                parsed = {
                    "frames": frames_payload,
                    "diagnostics": {
                        "status": "ok",
                        "error_code": None,
                        "error_detail": None,
                    },
                }
        except Exception as exc:
            parsed = {
                "frames": [],
                "diagnostics": {
                    "status": "degraded",
                    "error_code": "boxcars_network_error",
                    "error_detail": str(exc),
                    "frames_emitted": 0,
                },
            }

        frames = self._coerce_frames(parsed.get("frames"))
        return parsed, frames

    @staticmethod
    def _build_diagnostics(
        raw_diagnostics: Any, attempted_backends: list[str]
    ) -> NetworkDiagnostics:
        if not isinstance(raw_diagnostics, dict):
            raw_diagnostics = {}

        status = raw_diagnostics.get("status")
        if not isinstance(status, str):
            status = "degraded"

        error_code = raw_diagnostics.get("error_code")
        if error_code is not None and not isinstance(error_code, str):
            error_code = str(error_code)

        error_detail = raw_diagnostics.get("error_detail")
        if error_detail is not None and not isinstance(error_detail, str):
            error_detail = str(error_detail)

        frames_emitted = raw_diagnostics.get("frames_emitted")
        if isinstance(frames_emitted, bool):
            frames_emitted = int(frames_emitted)
        elif not isinstance(frames_emitted, int):
            frames_emitted = None

        attempted = list(attempted_backends)
        if isinstance(raw_diagnostics.get("attempted_backends"), list):
            for backend in raw_diagnostics["attempted_backends"]:
                if isinstance(backend, str):
                    candidate = backend.strip().lower()
                    if candidate and candidate not in attempted:
                        attempted.append(candidate)

        return NetworkDiagnostics(
            status=status,
            error_code=error_code,
            error_detail=error_detail,
            frames_emitted=frames_emitted,
            attempted_backends=attempted,
        )

    @staticmethod
    def _dedupe_frame_players(frames: list[dict[str, Any]]) -> None:
        # Deduplicate per-frame player entries keyed by player_id to guard
        # against duplicate car component actors leaking through the bridge.
        for frame in frames:
            players = frame.get("players")
            if not isinstance(players, list):
                continue

            unique_by_key: dict[str, Any] = {}
            order: list[str] = []
            anonymous_index = 0
            for player in players:
                key: str
                if isinstance(player, dict) and isinstance(
                    player.get("player_id"), str
                ):
                    key = player["player_id"]  # keep stable key per player id
                else:
                    key = f"__anon_{anonymous_index}"
                    anonymous_index += 1
                if key not in unique_by_key:
                    order.append(key)
                unique_by_key[key] = player
            frame["players"] = [unique_by_key[k] for k in order]

    @staticmethod
    def _normalize_player_metadata(raw: Any) -> dict[int, dict[str, Any]]:
        # Rust emits player_metadata keyed by header player index. Coerce keys
        # to int (pyo3 dict keys survive as int, but stay defensive) and drop
        # any malformed entries.
        if not isinstance(raw, dict):
            return {}
        out: dict[int, dict[str, Any]] = {}
        for key, value in raw.items():
            try:
                idx = int(key)
            except TypeError, ValueError:
                continue
            if isinstance(value, dict):
                out[idx] = value
        return out

    @staticmethod
    def _build_network_frames(
        frames: list[dict[str, Any]],
        player_metadata: dict[int, dict[str, Any]] | None = None,
    ) -> NetworkFrames:
        # Measure sample rate from timestamps if available.
        try:
            from ..normalize import measure_frame_rate

            hz = float(measure_frame_rate(frames))
        except Exception:
            hz = 30.0
        return NetworkFrames(
            frame_count=len(frames),
            sample_rate=hz,
            frames=frames,
            player_metadata=player_metadata or {},
        )
