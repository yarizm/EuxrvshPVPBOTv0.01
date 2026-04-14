from __future__ import annotations

from abc import ABC, abstractmethod

from euxrvsh_core.domain.models import BattleState, RoleDefinition


class GameRepository(ABC):
    @abstractmethod
    def initialize(self, role_definitions: list[RoleDefinition]) -> None: ...

    @abstractmethod
    def list_roles(self) -> list[RoleDefinition]: ...

    @abstractmethod
    def get_role(self, role_id: str) -> RoleDefinition | None: ...

    @abstractmethod
    def load_battle(self, session_id: str) -> BattleState | None: ...

    @abstractmethod
    def save_battle(self, battle_state: BattleState) -> None: ...

    @abstractmethod
    def delete_battle(self, session_id: str) -> bool: ...
