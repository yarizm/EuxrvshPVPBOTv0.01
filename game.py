from __future__ import annotations

from euxrvsh_core.runtime import build_legacy_runtime

_service = build_legacy_runtime().game_service


def attack(attacker_id, target_id, damage_value):
    return _service.attack(attacker_id, target_id, damage_value)


def startgame(play_num):
    return _service.start_game(play_num)


def pickrole(role_id):
    return _service.pick_role(role_id)


def endgame():
    return _service.end_game()


def skill_use(player_id, skill_idx):
    return _service.skill_use(player_id, skill_idx)


def turnend(sign):
    return _service.turnend(sign)


def resetdef():
    return _service.reset_defense()


def timerem(player_id, word, turns):
    return _service.timerem(player_id, word, turns)


def remsubauto():
    return _service.remsubauto()


def remsubhand(player_id, word, value):
    return _service.remsubhand(player_id, word, value)


def timeinfo():
    return _service.timeinfo()


def bleeding(player_id, turns):
    return _service.bleeding(player_id, turns)


def trigger_bleeding(player_id):
    return _service.trigger_bleeding(player_id)


def burning(player_id, turns):
    return _service.burning(player_id, turns)


def trigger_burning(player_id):
    return _service.trigger_burning(player_id)


def trigger_all_burning():
    return _service.trigger_all_burning()


def recovery(player_id, heal_amount, turns):
    return _service.recovery(player_id, heal_amount, turns)


def trigger_recovery(player_id):
    return _service.trigger_recovery(player_id)


def trigger_all_recovery():
    return _service.trigger_all_recovery()


def event_occurs(prob):
    return _service.event_occurs(prob)


def outprint_optimized():
    return _service.outprint_optimized()


def trigger_passive_on_attack(attacker_id, target_id, damage_value):
    return _service.trigger_passive_on_attack(attacker_id, target_id, damage_value)


def trigger_passive_on_defend(target_id, attacker_id, damage_value):
    return _service.trigger_passive_on_defend(target_id, attacker_id, damage_value)


def execute_skill_effect(player_id, skill_idx):
    return _service.execute_skill_effect(player_id, skill_idx)
