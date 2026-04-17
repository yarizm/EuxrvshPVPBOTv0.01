from __future__ import annotations

from euxrvsh_core.domain import ActionResult, BattlePlayerState, BattleState
from euxrvsh_core.services import BattleService

PVP_TOOL_NAMES = (
    "pvp_create_battle",
    "pvp_list_roles",
    "pvp_pick_role",
    "pvp_attack",
    "pvp_use_skill",
    "pvp_end_turn",
    "pvp_view_state",
    "pvp_reset_battle",
)


class PvpApplication:
    def __init__(self, battle_service: BattleService):
        self.battle_service = battle_service

    def create_battle(self, session_id: str, user_id: str, player_count: int | str) -> str:
        del user_id
        return self._render_result(self.battle_service.create_battle(session_id, player_count))

    def list_roles(self) -> str:
        roles = self.battle_service.list_roles()
        if not roles:
            return "当前没有可选角色。"

        lines = ["可选角色："]
        for role in roles:
            source = f"{role.source_kind}:{role.source_path}" if role.source_path else role.source_kind
            lines.append(f"- {role.name} ({role.role_id})：{role.summary}")
            lines.append(f"  来源：{source}")
            for skill in role.skills:
                lines.append(
                    f"  技能 {skill.name} / {skill.key}：AP {skill.ap_cost}，CD {skill.cooldown}，{skill.description}"
                )
        return "\n".join(lines)

    def pick_role(self, session_id: str, user_id: str, role_key: str) -> str:
        return self._safe_render(lambda: self.battle_service.pick_role(session_id, user_id, role_key))

    def attack(self, session_id: str, user_id: str, target_slot: int | str) -> str:
        return self._safe_render(lambda: self.battle_service.attack(session_id, user_id, target_slot))

    def use_skill(
        self,
        session_id: str,
        user_id: str,
        skill_key: str,
        target_slot: int | str | None = None,
    ) -> str:
        return self._safe_render(lambda: self.battle_service.use_skill(session_id, user_id, skill_key, target_slot))

    def end_turn(self, session_id: str, user_id: str) -> str:
        return self._safe_render(lambda: self.battle_service.end_turn(session_id, user_id))

    def view_state(self, session_id: str, detail: str = "summary") -> str:
        result = self.battle_service.get_battle_state(session_id, detail=detail)
        if not result.ok or result.battle_state is None:
            return result.summary
        return self._render_state(result.battle_state, detail=detail)

    def reset_battle(self, session_id: str, user_id: str, force: bool = False) -> str:
        return self._safe_render(lambda: self.battle_service.reset_battle(session_id, user_id, force=force))

    def _safe_render(self, call) -> str:
        try:
            return self._render_result(call())
        except ValueError as exc:
            return str(exc)

    def _render_result(self, result: ActionResult) -> str:
        lines = [result.summary]
        lines.extend(result.details)
        if result.battle_state is not None and result.ok:
            lines.append("")
            lines.append(self._render_state(result.battle_state, detail="summary"))
        return "\n".join(line for line in lines if line is not None).strip()

    def _render_state(self, state: BattleState, detail: str = "summary") -> str:
        lines = [
            f"对局状态：{state.status}",
            f"回合：第 {state.round_index} 轮",
            f"当前行动位：{state.turn_index} 号",
            "玩家状态：",
        ]
        for player in state.players:
            lines.extend(self._render_player(player, detail=detail))

        if state.logs:
            lines.append("最近记录：")
            logs = state.logs if detail == "full" else state.logs[-3:]
            for log in logs:
                actor = f"{log.actor_slot}号" if log.actor_slot is not None else "系统"
                lines.append(f"- [{log.action_type}] {actor}：{log.summary}")
        return "\n".join(lines)

    def _render_player(self, player: BattlePlayerState, detail: str = "summary") -> list[str]:
        role = player.role_name or "未选角"
        owner = player.user_id or "未绑定"
        status = "存活" if player.alive else "待命/已倒下"
        lines = [
            f"- {player.player_slot}号位 [{owner}] {role} | HP {player.hp}/{player.max_hp} | AP {player.ap}/{player.max_ap} | DEF {player.defense} | {status}"
        ]
        if detail == "full":
            effects = ", ".join(
                f"{effect.effect_name}(层数={effect.stacks}, 剩余={effect.remaining_turns})" for effect in player.effects
            )
            cooldowns = ", ".join(f"{key}:{value}" for key, value in sorted(player.cooldowns.items()))
            if effects:
                lines.append(f"  效果：{effects}")
            if cooldowns:
                lines.append(f"  冷却：{cooldowns}")
        return lines
