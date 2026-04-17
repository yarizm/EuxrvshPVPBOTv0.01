from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeConfig:
    storage_root: str
    runtime_db_path: str
    storage_json_path: str
    builtin_roles_dir: str
    custom_roles_dir: str
    sqlite_path: str
    sqlite_path_compat_used: bool = False
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


def resolve_storage_root(raw_config: Mapping[str, Any], *, default_storage_root: str) -> tuple[Path, bool]:
    configured_root = _get_str(raw_config, "storage_root", "").strip()
    if configured_root:
        return Path(configured_root).expanduser(), False

    sqlite_path = _get_str(raw_config, "sqlite_path", "").strip()
    if sqlite_path:
        sqlite_path_obj = Path(sqlite_path).expanduser()
        return sqlite_path_obj.parent, True

    return Path(default_storage_root).expanduser(), False


def runtime_config_from_mapping(
    raw_config: Mapping[str, Any],
    *,
    storage_root: Path,
    runtime_db_path: Path,
    storage_json_path: Path,
    builtin_roles_dir: Path,
    custom_roles_dir: Path,
    sqlite_path_compat_used: bool,
) -> RuntimeConfig:
    return RuntimeConfig(
        storage_root=str(storage_root),
        runtime_db_path=str(runtime_db_path),
        storage_json_path=str(storage_json_path),
        builtin_roles_dir=str(builtin_roles_dir),
        custom_roles_dir=str(custom_roles_dir),
        sqlite_path=str(runtime_db_path),
        sqlite_path_compat_used=sqlite_path_compat_used,
        enable_fallback_commands=_coerce_bool(raw_config.get("enable_fallback_commands"), True),
        enable_debug_tools=_coerce_bool(raw_config.get("enable_debug_tools"), False),
    )
