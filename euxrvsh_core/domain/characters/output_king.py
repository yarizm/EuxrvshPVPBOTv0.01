from __future__ import annotations

import random
from typing import Protocol


class OutputKingContext(Protocol):
    def get_focus(self, player_id: int) -> int: ...

    def add_focus(self, player_id: int, count: int) -> str: ...

    def reset_focus(self, player_id: int) -> str: ...

    def heal_player(self, player_id: int, amount: int) -> None: ...

    def consume_buff(self, player_id: int, buff_name: str) -> int: ...

    def adjust_skill_cd(self, player_id: int, skill_idx: int, delta: int) -> int | None: ...

    def add_turn_defense(self, player_id: int, amount: int) -> int | None: ...

    def get_player_attack(self, player_id: int) -> int: ...

    def set_timer(self, player_id: int, timer_name: str, turns: int) -> None: ...


class OutputKingCharacter:
    def on_attack(
        self,
        context: OutputKingContext,
        attacker_id: int,
        target_id: int,
        damage_value: int,
    ) -> str:
        messages: list[str] = []
        messages.append(context.add_focus(attacker_id, 1))
        focus = context.get_focus(attacker_id)

        if focus < 3:
            bonus = 5 - focus
            messages.append(
                f"【输出大王】专注小于 3，触发范围压制效果。本次理论伤害额外 +{bonus}。"
            )

        if focus >= 3:
            heal_amount = int(damage_value * 0.5)
            if heal_amount > 0:
                context.heal_player(attacker_id, heal_amount)
                messages.append(f"【输出大王】触发 50% 吸血，恢复 {heal_amount} HP。")

        multiplier = context.consume_buff(attacker_id, "BUFF_NEXT_ATK_MULT")
        if multiplier:
            messages.append(
                f"【输出大王】触发伤害倍率 Buff：x{multiplier}，请按实际规则结算本次攻击。"
            )

        return "\n".join(msg for msg in messages if msg)

    def on_defend(
        self,
        context: OutputKingContext,
        target_id: int,
        attacker_id: int,
        damage_value: int,
    ) -> tuple[str, int]:
        messages: list[str] = []
        final_damage = damage_value
        focus = context.get_focus(target_id)

        if focus == 5:
            final_damage = max(0, final_damage - 2)
            messages.append("【输出大王】专注达到 5，减免 2 点伤害。")

        dodge_prob = min(25 * focus, 75)
        roll = random.randint(1, 100)
        if roll <= dodge_prob:
            messages.append(
                f"【输出大王】侧闪判定成功（概率 {dodge_prob}%，掷骰 {roll}），本次伤害为 0。"
            )
            return "\n".join(messages), 0

        messages.append(f"【输出大王】侧闪判定失败（概率 {dodge_prob}%，掷骰 {roll}）。")
        messages.append(context.add_focus(target_id, 1))
        context.adjust_skill_cd(target_id, 2, -3)
        messages.append("【输出大王】失败补偿：专注 +1，技能 2 CD -3。")
        return "\n".join(messages), final_damage

    def on_skill(self, context: OutputKingContext, player_id: int, skill_idx: int) -> str:
        player_id = int(player_id)
        skill_idx = int(skill_idx)
        messages: list[str] = []
        focus = context.get_focus(player_id)

        if skill_idx == 1:
            pending_state = context.consume_buff(player_id, "STACK_OUTPUT_KING_SKILL1_STATE")
            if pending_state > 0:
                if pending_state == 1:
                    base_atk = context.get_player_attack(player_id)
                    shield = max(0, base_atk - focus)
                    context.add_turn_defense(player_id, shield)
                    context.add_focus(player_id, 2)
                    messages.append(f"释放【集中】：获得 {shield} 点护盾，并获得 2 层专注。")
                elif pending_state == 2:
                    context.set_timer(player_id, "BUFF_NEXT_ATK_MULT", 2)
                    messages.append("释放【暴击】：下一次攻击造成 2 倍伤害。")
                elif pending_state == 3:
                    context.set_timer(player_id, "BUFF_NEXT_ATK_MULT", 4)
                    context.reset_focus(player_id)
                    context.adjust_skill_cd(player_id, 1, -100)
                    messages.append("释放【解脱】：下一次攻击造成 4 倍伤害，专注清零，技能 1 立即刷新。")
                return "\n".join(messages)

            new_state = 0
            skill_name = ""
            if focus < 3:
                new_state = 1
                skill_name = "集中"
            elif focus < 5:
                new_state = 2
                skill_name = "暴击"
            elif focus == 5:
                new_state = 3
                skill_name = "解脱"

            if new_state > 0:
                context.set_timer(player_id, "STACK_OUTPUT_KING_SKILL1_STATE", new_state)
                context.adjust_skill_cd(player_id, 1, -100)
                messages.append(f"技能 1 已切换为【{skill_name}】，请再次使用该技能触发效果。")

        elif skill_idx == 2:
            messages.append(
                "释放【侧闪·返还】：\n1 码内攻击，CD -1\n2 码内移动，CD -2\n未触发则 CD -3\n请根据实际距离手动结算。"
            )

        elif skill_idx == 3:
            messages.append(
                "释放【钩锁】：造成 ATK + 3 * 距离 的伤害，并手动附加【锁定】状态。"
            )

        return "\n".join(messages)
