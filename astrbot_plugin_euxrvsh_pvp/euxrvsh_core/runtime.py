from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from euxrvsh_core.command_dispatcher import CommandDispatcher
from euxrvsh_core.config import load_legacy_app_config, runtime_config_from_mapping
from euxrvsh_core.domain import CharacterRegistry
from euxrvsh_core.repositories import MySQLGameRepository
from euxrvsh_core.services import GameService


@dataclass
class EuxrvshRuntime:
    repository: MySQLGameRepository
    game_service: GameService
    dispatcher: CommandDispatcher


def build_runtime(config: Mapping[str, Any]) -> EuxrvshRuntime:
    runtime_config = runtime_config_from_mapping(config)
    repository = MySQLGameRepository(runtime_config.database)
    game_service = GameService(repository, CharacterRegistry())
    dispatcher = CommandDispatcher(game_service)
    return EuxrvshRuntime(repository, game_service, dispatcher)


_LEGACY_RUNTIME: EuxrvshRuntime | None = None


def build_legacy_runtime() -> EuxrvshRuntime:
    global _LEGACY_RUNTIME
    if _LEGACY_RUNTIME is None:
        legacy_config = load_legacy_app_config()
        repository = MySQLGameRepository(legacy_config.runtime.database)
        game_service = GameService(repository, CharacterRegistry())
        dispatcher = CommandDispatcher(game_service)
        _LEGACY_RUNTIME = EuxrvshRuntime(repository, game_service, dispatcher)
    return _LEGACY_RUNTIME
