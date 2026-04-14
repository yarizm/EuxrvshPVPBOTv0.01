from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class RuntimeConfig:
    sqlite_path: str
    enable_fallback_commands: bool = True
    enable_debug_tools: bool = False


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _get_str(source: Mapping[str, Any], key: str, default: str = "") -> str:
    value = source.get(key, default)
    if value is None:
        return default
    return str(value)


def runtime_config_from_mapping(
    raw_config: Mapping[str, Any],
    *,
    default_sqlite_path: str,
) -> RuntimeConfig:
    sqlite_path = _get_str(raw_config, "sqlite_path", "").strip() or default_sqlite_path
    return RuntimeConfig(
        sqlite_path=sqlite_path,
        enable_fallback_commands=_coerce_bool(raw_config.get("enable_fallback_commands"), True),
        enable_debug_tools=_coerce_bool(raw_config.get("enable_debug_tools"), False),
    )
