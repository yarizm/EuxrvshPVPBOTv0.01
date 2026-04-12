from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

ROOT_DIR = Path(__file__).resolve().parent.parent
LEGACY_CONFIG_PATH = ROOT_DIR / "config.yaml"


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = "localhost"
    user: str = "root"
    password: str = "yarizm75"
    database: str = "euxrvsh"
    pool_name: str = "game_pool"
    pool_size: int = 20


@dataclass(frozen=True)
class RuntimeConfig:
    database: DatabaseConfig


@dataclass(frozen=True)
class LegacyAppConfig:
    appid: str = ""
    secret: str = ""
    runtime: RuntimeConfig = RuntimeConfig(database=DatabaseConfig())


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _get_str(source: Mapping[str, Any], key: str, default: str = "") -> str:
    value = source.get(key, default)
    if value is None:
        return default
    return str(value)


def load_simple_yaml(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip("\"'")
    return data


def runtime_config_from_mapping(
    raw_config: Mapping[str, Any],
    *,
    default_db: DatabaseConfig | None = None,
) -> RuntimeConfig:
    default_db = default_db or DatabaseConfig()
    database = DatabaseConfig(
        host=_get_str(raw_config, "db_host", default_db.host),
        user=_get_str(raw_config, "db_user", default_db.user),
        password=_get_str(raw_config, "db_password", default_db.password),
        database=_get_str(raw_config, "db_name", default_db.database),
        pool_name=_get_str(raw_config, "db_pool_name", default_db.pool_name),
        pool_size=_coerce_int(raw_config.get("db_pool_size"), default_db.pool_size),
    )
    return RuntimeConfig(database=database)


def load_legacy_app_config(path: Path = LEGACY_CONFIG_PATH) -> LegacyAppConfig:
    raw = load_simple_yaml(path)
    runtime = runtime_config_from_mapping({}, default_db=DatabaseConfig())
    return LegacyAppConfig(
        appid=raw.get("appid", ""),
        secret=raw.get("secret", ""),
        runtime=runtime,
    )
