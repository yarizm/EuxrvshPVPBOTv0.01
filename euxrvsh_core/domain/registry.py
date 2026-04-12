from __future__ import annotations

from euxrvsh_core.domain.characters.output_king import OutputKingCharacter


class CharacterRegistry:
    def __init__(self) -> None:
        self._by_name = {
            "输出大王": OutputKingCharacter(),
        }

    def get(self, role_name: str | None):
        if not role_name:
            return None
        return self._by_name.get(role_name)
