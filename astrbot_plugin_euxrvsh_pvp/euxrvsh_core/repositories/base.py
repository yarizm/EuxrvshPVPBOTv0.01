from __future__ import annotations

from abc import ABC, abstractmethod

from euxrvsh_core.domain.models import BattleState


class GameRepository(ABC):
    @abstractmethod
    def initialize(self) -> None: ...

    @abstractmethod
    def load_battle(self, session_id: str) -> BattleState | None: ...

    @abstractmethod
    def save_battle(self, battle_state: BattleState) -> None: ...

    @abstractmethod
    def delete_battle(self, session_id: str) -> bool: ...
