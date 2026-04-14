from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from euxrvsh_core.config import RuntimeConfig, runtime_config_from_mapping
from euxrvsh_core.domain import CharacterRegistry
from euxrvsh_core.repositories import SQLiteGameRepository
from euxrvsh_core.services import BattleService


@dataclass
class EuxrvshRuntime:
    repository: SQLiteGameRepository
    battle_service: BattleService
    config: RuntimeConfig


def build_runtime(
    config: Mapping[str, Any],
    *,
    default_sqlite_path: str,
) -> EuxrvshRuntime:
    runtime_config = runtime_config_from_mapping(config, default_sqlite_path=default_sqlite_path)
    repository = SQLiteGameRepository(runtime_config.sqlite_path)
    battle_service = BattleService(repository, CharacterRegistry())
    return EuxrvshRuntime(repository=repository, battle_service=battle_service, config=runtime_config)
