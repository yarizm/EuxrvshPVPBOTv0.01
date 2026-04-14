from __future__ import annotations

from euxrvsh_core.domain.characters.output_king import build_output_king_role
from euxrvsh_core.domain.models import RoleDefinition


class CharacterRegistry:
    def __init__(self):
        output_king = build_output_king_role()
        self._by_key = {output_king.role_id: output_king}
        self._by_name = {output_king.name.lower(): output_king}

    def all(self) -> list[RoleDefinition]:
        return list(self._by_key.values())

    def get(self, role_key_or_name: str | None) -> RoleDefinition | None:
        if not role_key_or_name:
            return None
        normalized = str(role_key_or_name).strip().lower()
        return self._by_key.get(normalized) or self._by_name.get(normalized)
