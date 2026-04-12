from __future__ import annotations

from euxrvsh_core.domain.characters.output_king import OutputKingCharacter
from euxrvsh_core.runtime import build_legacy_runtime

_service = build_legacy_runtime().game_service
_character = OutputKingCharacter()


def get_focus(player_id):
    return _service.get_focus(player_id)


def add_focus(player_id, count):
    return _service.add_focus(player_id, count)


def reset_focus(player_id):
    return _service.reset_focus(player_id)


def on_attack(attacker_id, target_id, damage_value):
    return _character.on_attack(_service, attacker_id, target_id, damage_value)


def on_defend(target_id, attacker_id, damage_value):
    return _character.on_defend(_service, target_id, attacker_id, damage_value)


def on_skill(player_id, skill_idx):
    return _character.on_skill(_service, player_id, skill_idx)
