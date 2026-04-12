from __future__ import annotations

import random

from euxrvsh_core.domain import CharacterRegistry
from euxrvsh_core.repositories import MySQLGameRepository


class GameService:
    def __init__(self, repository: MySQLGameRepository, characters: CharacterRegistry | None = None):
        self.repository = repository
        self.characters = characters or CharacterRegistry()

    def attack(self, attacker_id: int | str, target_id: int | str, damage_value: int | str) -> str:
        damage_value = int(damage_value)
        attacker_id = int(attacker_id)
        target_id = int(target_id)

        passive_msg_atk = self.trigger_passive_on_attack(attacker_id, target_id, damage_value)
        passive_msg_def, damage_modified = self.trigger_passive_on_defend(target_id, attacker_id, damage_value)
        damage_value = damage_modified if damage_modified is not None else damage_value
        if damage_value <= 0:
            return "\n".join(
                msg for msg in [passive_msg_atk, passive_msg_def, "攻击被完全规避。"] if msg
            )

        attack_result = self.repository.resolve_attack_damage(target_id, damage_value)
        if attack_result is None:
            return f"玩家 {target_id} 不存在。"
        _, actual_hp_damage, def_reduction = attack_result
        return "\n".join(
            msg
            for msg in [
                passive_msg_atk,
                passive_msg_def,
                (
                    f"玩家 {target_id} 受到来自玩家 {attacker_id} 的伤害：{damage_value} "
                    f"(实际扣除 HP: {actual_hp_damage}, 护甲减少: {def_reduction})"
                ),
            ]
            if msg
        )

    def start_game(self, play_num: int | str) -> int:
        return self.repository.initialize_game(int(play_num))

    def pick_role(self, role_id: int | str) -> str:
        try:
            current_player_id, role_name, turn_def_init, total_def_init = self.repository.pick_role_for_next_player(
                int(role_id)
            )
            return (
                f"玩家 {current_player_id} 已成功选择角色：{role_name} "
                f"(当前护甲: {turn_def_init}, 总护甲池: {total_def_init})"
            )
        except Exception as exc:
            return f"选角失败: {exc}"

    def end_game(self) -> bool:
        try:
            self.repository.end_game()
            return True
        except Exception:
            return False

    def skill_use(self, player_id: int | str, skill_idx: int | str) -> str:
        player_id = int(player_id)
        skill_idx = int(skill_idx)
        current_cd = self.repository.get_skill_cd(player_id, skill_idx)
        if current_cd > 0:
            return f"玩家 {player_id} 的技能 {skill_idx} 还在冷却中，剩余 {current_cd} 回合。"

        role_id = self.repository.get_player_role_id(player_id)
        if role_id is None:
            return "玩家尚未初始化。"

        max_cd = self.repository.get_role_skill_cd(role_id, skill_idx)
        self.repository.set_skill_cd(player_id, skill_idx, max_cd)
        result = self.execute_skill_effect(player_id, skill_idx)
        return f"玩家 {player_id} 使用了技能 {skill_idx}，CD 重置为 {max_cd}。\n{result}".strip()

    def turnend(self, sign: int) -> list[str]:
        results: list[str] = []
        try:
            if sign == 1:
                self.repository.decrement_all_skill_cds()

            play_num = self.repository.get_play_num()
            for player_id in range(1, play_num + 1):
                stats = self.repository.get_player_status(player_id)
                if not stats:
                    continue
                cd_rows = self.repository.list_active_skill_cds(player_id)
                cd_info = "".join(
                    f"玩家 {player_id} 的技能 {skill_idx} 当前 CD 为：{current_cd}\n"
                    for skill_idx, current_cd in cd_rows
                )
                base_info = (
                    f"玩家 {player_id} 最大 HP：{stats.max_hp}，当前 HP：{stats.now_hp}，"
                    f"当前护甲：{stats.turn_def}，总护甲池：{stats.total_def}，"
                    f"当前 ATK：{stats.atk}，当前攻击距离：{stats.distance}，"
                    f"当前行动值：{stats.now_ap}/{stats.max_ap}\n\n"
                )
                results.append(base_info + cd_info)
            return results
        except Exception as exc:
            return [f"结算出错: {exc}"]

    def reset_defense(self) -> bool:
        try:
            play_num = self.repository.get_play_num()
            for player_id in range(1, play_num + 1):
                row = self.repository.get_def_reset_context(player_id)
                if not row or row.current_def >= row.base_def:
                    continue
                diff = row.base_def - row.current_def
                if row.total_def >= diff:
                    new_current = row.base_def
                    new_total = row.total_def - diff
                else:
                    new_current = row.current_def + row.total_def
                    new_total = 0
                self.repository.set_player_defense(player_id, new_current, new_total)
            return True
        except Exception:
            return False

    def timerem(self, player_id: int | str, word: str, turns: int | str) -> str:
        try:
            turns = int(turns)
            self.repository.add_timer(int(player_id), word, turns)
            total_turn = self.repository.get_total_turn()
            return f"玩家 {player_id} 添加计时器 {word}，持续 {turns} 回合，将在第 {total_turn + turns} 回合结束。"
        except Exception as exc:
            return f"添加计时器失败: {exc}"

    def remsubauto(self) -> bool:
        try:
            self.repository.decrement_non_stack_timers()
            return True
        except Exception:
            return False

    def remsubhand(self, player_id: int | str, word: str, value: int | str) -> str:
        try:
            result = self.repository.increment_timer(int(player_id), word, int(value))
            if result is None:
                return "未找到指定计时器。"
            return f"计时器 {word} 已更新为 {result}。"
        except Exception as exc:
            return f"修改计时器失败: {exc}"

    def timeinfo(self) -> list[str]:
        try:
            results: list[str] = []
            play_num = self.repository.get_play_num()
            for player_id in range(1, play_num + 1):
                timers = self.repository.list_player_timers(player_id)
                info = f"玩家 {player_id} 的计时器信息：\n"
                info += "".join(f"计时器: {name}, 剩余: {turns} 回合\n" for name, turns in timers)
                results.append(info)
            return results
        except Exception as exc:
            return [f"查询计时器失败: {exc}"]

    def bleeding(self, player_id: int | str, turns: int | str) -> str:
        return self._apply_simple_effect(int(player_id), "流血", int(turns), "流血")

    def trigger_bleeding(self, player_id: int | str) -> str | None:
        return self._trigger_dot_effect(int(player_id), "流血", 1, "玩家 {player_id} 因流血损失 1 点 HP")

    def burning(self, player_id: int | str, turns: int | str) -> str:
        return self._apply_simple_effect(int(player_id), "灼烧", int(turns), "灼烧")

    def trigger_burning(self, player_id: int | str) -> str | None:
        return self._trigger_dot_effect(int(player_id), "灼烧", 1, "玩家 {player_id} 因灼烧损失 1 点 HP")

    def trigger_all_burning(self) -> list[str]:
        return self._trigger_all_players(self.trigger_burning)

    def recovery(self, player_id: int | str, heal_amount: int | str, turns: int | str) -> str:
        try:
            player_id = int(player_id)
            heal_amount = int(heal_amount)
            turns = int(turns)
            current_hp = self.repository.change_hp_with_cap(player_id, heal_amount)
            timer_name = f"恢复|{heal_amount}"
            existing = self.repository.get_timer_like(player_id, "恢复|%")
            if existing:
                self.repository.delete_timer_like(player_id, "恢复|%")
            self.repository.set_timer(player_id, timer_name, turns)
            hp_info = f"，当前 HP：{current_hp}" if current_hp is not None else ""
            return (
                f"玩家 {player_id} 获得恢复效果（等级 {heal_amount}），"
                f"立即恢复 {heal_amount} 点 HP{hp_info}，持续 {turns} 回合。"
            )
        except Exception as exc:
            return f"施加恢复失败: {exc}"

    def trigger_recovery(self, player_id: int | str) -> str | None:
        try:
            player_id = int(player_id)
            row = self.repository.get_timer_like(player_id, "恢复|%")
            if not row or row[1] <= 0:
                return None
            timer_name, remaining_turns = row
            heal_amount = int(timer_name.split("|")[1])
            self.repository.change_hp_with_cap(player_id, heal_amount)
            remaining = remaining_turns - 1
            if remaining <= 0:
                self.repository.delete_timer_like(player_id, "恢复|%")
                return f"玩家 {player_id} 恢复了 {heal_amount} 点 HP，恢复效果已结束。"
            self.repository.set_timer(player_id, timer_name, remaining)
            return f"玩家 {player_id} 恢复了 {heal_amount} 点 HP，剩余 {remaining} 回合。"
        except Exception as exc:
            return f"恢复触发失败: {exc}"

    def trigger_all_recovery(self) -> list[str]:
        return self._trigger_all_players(self.trigger_recovery)

    def event_occurs(self, probability: float) -> bool:
        return random.random() < probability

    def outprint_optimized(self) -> list[str]:
        results: list[str] = []
        try:
            play_num = self.repository.get_play_num()
            for player_id in range(1, play_num + 1):
                row = self.repository.get_player_ap_context(player_id)
                if not row:
                    continue
                ap_recover_min = row.ap_recover_min or 1
                ap_recover_max = row.ap_recover_max or 3
                max_ap = row.max_ap or 10
                now_ap = row.now_ap or 0
                recover_ap = random.randint(ap_recover_min, ap_recover_max)
                new_ap = min(now_ap + recover_ap, max_ap)
                self.repository.update_player_ap(player_id, new_ap)
                self.repository.increment_totalturn(player_id)
                results.append(
                    f"玩家 {player_id} 本回合恢复了 {recover_ap} 点行动值，当前行动值为 {new_ap} / {max_ap}"
                )
            return results
        except Exception as exc:
            return [f"AP 结算出错: {exc}"]

    def hp_change(self, player_id: int | str, value: int | str, change_type: int | str) -> str:
        player_id = int(player_id)
        result = self.repository.change_hp(player_id, int(value), max_mode=int(change_type) == 1)
        if result is None:
            return f"玩家 {player_id} 不存在。"
        label = "最大 HP" if int(change_type) == 1 else "当前 HP"
        return f"玩家 {player_id} 的{label}已变更为：{result}"

    def atk_change(self, player_id: int | str, value: int | str) -> str:
        return self._simple_stat_message(player_id, value, "atk", "攻击力(ATK)")

    def def_change(self, player_id: int | str, value: int | str) -> str:
        return self._simple_stat_message(player_id, value, "turn_def", "当前护甲")

    def distance_change(self, player_id: int | str, value: int | str) -> str:
        return self._simple_stat_message(player_id, value, "distance", "攻击距离")

    def cd_change(self, player_id: int | str, skill_idx: int | str, change_val: int | str) -> str:
        player_id = int(player_id)
        skill_idx = int(skill_idx)
        result = self.repository.adjust_skill_cd(player_id, skill_idx, int(change_val))
        if result is None:
            return f"玩家 {player_id} 的技能 {skill_idx} 当前不在冷却中。"
        return f"玩家 {player_id} 的技能 {skill_idx} CD 已变更为 {result}"

    def get_role_name(self, player_id: int | str) -> str | None:
        return self.repository.get_role_name(int(player_id))

    def consume_buff(self, player_id: int | str, buff_name: str) -> int:
        return self.repository.consume_buff(int(player_id), buff_name)

    def get_focus(self, player_id: int | str) -> int:
        return self.repository.get_timer(int(player_id), "STACK_专注") or 0

    def add_focus(self, player_id: int | str, count: int | str) -> str:
        player_id = int(player_id)
        current = self.get_focus(player_id)
        new_value = min(current + int(count), 5)
        self.repository.set_timer(player_id, "STACK_专注", new_value)
        return f"专注层数：{current} -> {new_value}"

    def reset_focus(self, player_id: int | str) -> str:
        self.repository.delete_timer(int(player_id), "STACK_专注")
        return "专注已重置为 0。"

    def heal_player(self, player_id: int | str, amount: int | str) -> None:
        self.repository.change_hp_with_cap(int(player_id), int(amount))

    def add_turn_defense(self, player_id: int | str, amount: int | str) -> int | None:
        return self.repository.simple_stat_change(int(player_id), int(amount), "turn_def")

    def set_timer(self, player_id: int | str, timer_name: str, turns: int | str) -> None:
        self.repository.set_timer(int(player_id), timer_name, int(turns))

    def get_player_attack(self, player_id: int | str) -> int:
        return self.repository.get_player_attack(int(player_id))

    def trigger_passive_on_attack(self, attacker_id: int, target_id: int, damage_value: int) -> str:
        role_name = self.get_role_name(attacker_id)
        character = self.characters.get(role_name)
        if not character:
            return ""
        return character.on_attack(self, attacker_id, target_id, damage_value)

    def trigger_passive_on_defend(self, target_id: int, attacker_id: int, damage_value: int) -> tuple[str, int]:
        role_name = self.get_role_name(target_id)
        character = self.characters.get(role_name)
        if not character:
            return "", damage_value
        return character.on_defend(self, target_id, attacker_id, damage_value)

    def execute_skill_effect(self, player_id: int, skill_idx: int) -> str:
        role_name = self.get_role_name(player_id)
        character = self.characters.get(role_name)
        if not character:
            return ""
        return character.on_skill(self, player_id, skill_idx)

    def _simple_stat_message(self, player_id: int | str, value: int | str, column_name: str, label: str) -> str:
        player_id = int(player_id)
        result = self.repository.simple_stat_change(player_id, int(value), column_name)
        if result is None:
            return f"玩家 {player_id} 不存在。"
        return f"玩家 {player_id} 的{label}已变更为：{result}"

    def _apply_simple_effect(self, player_id: int, effect_name: str, turns: int, label: str) -> str:
        try:
            existing = self.repository.get_timer(player_id, effect_name)
            if existing:
                new_turns = max(existing, turns)
                self.repository.set_timer(player_id, effect_name, new_turns)
                return f"玩家 {player_id} 的{label}效果已刷新，持续 {new_turns} 回合。"
            self.repository.set_timer(player_id, effect_name, turns)
            return f"玩家 {player_id} 被施加了{label}效果，持续 {turns} 回合。"
        except Exception as exc:
            return f"施加{label}失败: {exc}"

    def _trigger_dot_effect(self, player_id: int, effect_name: str, damage: int, template: str) -> str | None:
        try:
            remaining_turns = self.repository.get_timer(player_id, effect_name)
            if not remaining_turns or remaining_turns <= 0:
                return None
            self.repository.change_hp(player_id, -damage, max_mode=False)
            remaining = remaining_turns - 1
            if remaining <= 0:
                self.repository.delete_timer(player_id, effect_name)
                return template.format(player_id=player_id) + f"，{effect_name}效果已结束。"
            self.repository.set_timer(player_id, effect_name, remaining)
            return template.format(player_id=player_id) + f"，剩余 {remaining} 回合。"
        except Exception as exc:
            return f"{effect_name}触发失败: {exc}"

    def _trigger_all_players(self, fn) -> list[str]:
        results: list[str] = []
        try:
            play_num = self.repository.get_play_num()
            for player_id in range(1, play_num + 1):
                message = fn(player_id)
                if message:
                    results.append(message)
            return results
        except Exception as exc:
            return [f"批量触发效果失败: {exc}"]
