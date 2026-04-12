from __future__ import annotations

from euxrvsh_core.runtime import build_legacy_runtime

_service = build_legacy_runtime().game_service


def hp_change(player_id, value, change_type):
    return _service.hp_change(player_id, value, change_type)


def atk_change(player_id, value):
    return _service.atk_change(player_id, value)


def distance_change(player_id, value):
    return _service.distance_change(player_id, value)


def def_change(player_id, value):
    return _service.def_change(player_id, value)


def cd_change(player_id, skill_idx, change_val):
    return _service.cd_change(player_id, skill_idx, change_val)


def get_role_name(player_id):
    return _service.get_role_name(player_id)


def consume_buff(player_id, buff_name):
    return _service.consume_buff(player_id, buff_name)


def simple_stat_change(player_id, value, column_name, label_cn):
    if column_name == "atk":
        return atk_change(player_id, value)
    if column_name == "turn_def":
        return def_change(player_id, value)
    if column_name == "distance":
        return distance_change(player_id, value)
    return f"暂不支持的属性变更：{label_cn}"
