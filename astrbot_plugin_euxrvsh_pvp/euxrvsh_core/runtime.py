from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from euxrvsh_core.config import resolve_storage_root, runtime_config_from_mapping
from euxrvsh_core.domain import CharacterRegistry, RoleCatalogLoader
from euxrvsh_core.repositories import SQLiteGameRepository
from euxrvsh_core.services import BattleService
from euxrvsh_core.storage import StorageLayout, ensure_storage_layout


@dataclass
class EuxrvshRuntime:
    repository: SQLiteGameRepository
    battle_service: BattleService
    characters: CharacterRegistry
    storage_layout: StorageLayout
    role_warnings: tuple[str, ...]
    config: object


def build_runtime(
    config: Mapping[str, Any],
    *,
    default_storage_root: str,
) -> EuxrvshRuntime:
    storage_root, sqlite_path_compat_used = resolve_storage_root(config, default_storage_root=default_storage_root)
    storage_layout = ensure_storage_layout(storage_root)
    if sqlite_path_compat_used:
        storage_layout = StorageLayout(
            storage_root=storage_layout.storage_root,
            runtime_db_path=storage_layout.runtime_db_path,
            storage_json_path=storage_layout.storage_json_path,
            builtin_roles_dir=storage_layout.builtin_roles_dir,
            custom_roles_dir=storage_layout.custom_roles_dir,
            sqlite_path_compat_used=True,
        )

    runtime_config = runtime_config_from_mapping(
        config,
        storage_root=storage_layout.storage_root,
        runtime_db_path=storage_layout.runtime_db_path,
        storage_json_path=storage_layout.storage_json_path,
        builtin_roles_dir=storage_layout.builtin_roles_dir,
        custom_roles_dir=storage_layout.custom_roles_dir,
        sqlite_path_compat_used=storage_layout.sqlite_path_compat_used,
    )

    repository = SQLiteGameRepository(storage_layout.runtime_db_path)
    repository.initialize()
    catalog_loader = RoleCatalogLoader(storage_layout.builtin_roles_dir, storage_layout.custom_roles_dir)
    catalog = catalog_loader.load()
    characters = CharacterRegistry(catalog.role_files)
    battle_service = BattleService(repository, characters)
    return EuxrvshRuntime(
        repository=repository,
        battle_service=battle_service,
        characters=characters,
        storage_layout=storage_layout,
        role_warnings=catalog.warnings,
        config=runtime_config,
    )
