from __future__ import annotations

import random
from datetime import UTC, datetime

from euxrvsh_core.domain import (
    ActionResult,
    BattleLogEntry,
    BattlePlayerState,
    BattleState,
    CharacterRegistry,
    RoleDefinition,
    RoleSkillDefinition,
    SkillActionDefinition,
    SkillConditionDefinition,
)
from euxrvsh_core.repositories import GameRepository


class BattleService:
    def __init__(
        self,
        repository: GameRepository,
        characters: CharacterRegistry,
        rng: random.Random | None = None,
    ):
        self.repository = repository
        self.characters = characters
        self.rng = rng or random.Random()

    def create_battle(self, session_id: str, player_count: int | str) -> ActionResult:
        try:
            player_count = int(player_count)
        except (TypeError, ValueError):
            return ActionResult(ok=False, summary="玩家人数必须是数字。")

        if player_count < 2 or player_count > 4:
            return ActionResult(ok=False, summary="当前仅支持 2 到 4 人对局。")

        now = self._now()
        state = BattleState(
            session_id=session_id,
            status="draft",
            player_count=player_count,
            turn_index=1,
            round_index=1,
            players=[BattlePlayerState(player_slot=index) for index in range(1, player_count + 1)],
            logs=[
                BattleLogEntry(
                    turn_index=1,
                    actor_slot=None,
                    action_type="create_battle",
                    summary=f"创建了一场 {player_count} 人 PvP 对局。",
                    created_at=now,
                )
            ],
            created_at=now,
            updated_at=now,
        )
        self.repository.save_battle(state)
        return ActionResult(ok=True, summary=f"已创建 {player_count} 人对局。", battle_state=state)

    def join_or_bind_player(self, session_id: str, user_id: str) -> BattlePlayerState:
        state = self._require_battle(session_id)
        current = state.get_player_by_user(user_id)
        if current:
            return current
        for player in state.players:
            if not player.user_id:
                player.user_id = user_id
                self._save_state(state)
                return player
        raise ValueError("当前对局已满，无法加入。")

    def list_roles(self) -> list[RoleDefinition]:
        return self.characters.all()

    def pick_role(self, session_id: str, user_id: str, role_key: str) -> ActionResult:
        state = self._require_battle(session_id)
        if state.status == "finished":
            return ActionResult(ok=False, summary="当前对局已结束，请先重置后再选角。", battle_state=state)

        role = self.characters.get(role_key)
        if role is None:
            return ActionResult(ok=False, summary=f"未找到角色 `{role_key}`。", battle_state=state)

        self.join_or_bind_player(session_id, user_id)
        state = self._require_battle(session_id)
        player = state.get_player_by_user(user_id)
        if player is None:
            return ActionResult(ok=False, summary="绑定当前玩家失败。", battle_state=state)

        player.role_id = role.role_id
        player.role_name = role.name
        player.hp = role.base_hp
        player.max_hp = role.base_hp
        player.atk = role.base_atk
        player.defense = role.base_defense
        player.ap = role.max_ap
        player.max_ap = role.max_ap
        player.alive = True
        player.cooldowns = {}
        player.effects = []
        player.set_effect("focus", stacks=0, remaining_turns=-1)

        details = [f"你已绑定到 {player.player_slot} 号位，角色为 {role.name}。"]
        if self._all_players_ready(state):
            state.status = "active"
            state.turn_index = self._first_alive_slot(state)
            details.append(f"所有玩家已就绪。当前轮到 {state.turn_index} 号位行动。")
        else:
            ready_count = len([item for item in state.players if item.user_id and item.role_id])
            details.append(f"当前已有 {ready_count}/{state.player_count} 位玩家完成选角。")

        self._append_log(
            state,
            actor_slot=player.player_slot,
            action_type="pick_role",
            summary=f"{player.player_slot} 号位选择了 {role.name}。",
        )
        self._save_state(state)
        return ActionResult(ok=True, summary=details[0], details=details[1:], battle_state=state)

    def attack(self, session_id: str, user_id: str, target_slot: int | str) -> ActionResult:
        state, actor = self._require_actor_turn(session_id, user_id)
        target = self._require_target(state, actor, target_slot)
        if target is None:
            return ActionResult(ok=False, summary="目标不存在或无法攻击。", battle_state=state)
        if actor.ap < 1:
            return ActionResult(ok=False, summary="你的 AP 不足，无法进行普通攻击。", battle_state=state)

        actor.ap -= 1
        summary, details = self._resolve_attack(actor, target, base_damage=actor.atk, allow_multiplier=True)
        self._append_log(
            state,
            actor_slot=actor.player_slot,
            action_type="attack",
            summary=summary,
            detail={"target_slot": target.player_slot, "details": details},
        )
        self._finalize_state_after_action(state)
        self._save_state(state)
        return ActionResult(ok=True, summary=summary, details=details, battle_state=state)

    def use_skill(
        self,
        session_id: str,
        user_id: str,
        skill_key: str,
        target_slot: int | str | None = None,
    ) -> ActionResult:
        state, actor = self._require_actor_turn(session_id, user_id)
        role = self._require_role(actor)
        skill = next((item for item in role.skills if item.key == skill_key), None)
        if skill is None:
            return ActionResult(ok=False, summary=f"{role.name} 没有技能 `{skill_key}`。", battle_state=state)
        if skill.target_type == "enemy" and self._require_target(state, actor, target_slot) is None:
            return ActionResult(ok=False, summary=f"{skill.name} 需要一个有效的敌方目标。", battle_state=state)
        if actor.ap < skill.ap_cost:
            return ActionResult(ok=False, summary=f"你的 AP 不足，无法使用 {skill.name}。", battle_state=state)
        if actor.cooldowns.get(skill.key, 0) > 0:
            return ActionResult(
                ok=False,
                summary=f"{skill.name} 仍在冷却中，还需 {actor.cooldowns[skill.key]} 回合。",
                battle_state=state,
            )

        actor.ap -= skill.ap_cost
        actor.cooldowns[skill.key] = skill.cooldown
        summary, details = self._execute_skill(state, actor, skill, target_slot)
        self._append_log(
            state,
            actor_slot=actor.player_slot,
            action_type="skill",
            summary=summary,
            detail={"skill_key": skill.key, "details": details},
        )
        self._finalize_state_after_action(state)
        self._save_state(state)
        return ActionResult(ok=True, summary=summary, details=details, battle_state=state)

    def end_turn(self, session_id: str, user_id: str) -> ActionResult:
        state, actor = self._require_actor_turn(session_id, user_id)
        details = [f"{actor.player_slot} 号位结束了自己的回合。"]
        self._advance_turn(state, details)
        self._append_log(
            state,
            actor_slot=actor.player_slot,
            action_type="end_turn",
            summary=details[0],
            detail={"details": details[1:]},
        )
        self._finalize_state_after_action(state)
        self._save_state(state)
        return ActionResult(ok=True, summary=details[0], details=details[1:], battle_state=state)

    def get_battle_state(self, session_id: str, detail: str = "summary") -> ActionResult:
        state = self.repository.load_battle(session_id)
        if state is None:
            return ActionResult(ok=False, summary="当前会话还没有进行中的 PvP 对局。")
        return ActionResult(ok=True, summary=f"当前对局状态：{detail}", battle_state=state)

    def reset_battle(self, session_id: str, user_id: str, force: bool = False) -> ActionResult:
        del user_id
        state = self.repository.load_battle(session_id)
        if state is None:
            return ActionResult(ok=False, summary="当前没有可重置的对局。")
        if state.status in {"active", "finished"} and not force:
            return ActionResult(ok=False, summary="当前对局已开始，请确认后再强制重置。", battle_state=state)
        if not self.repository.delete_battle(session_id):
            return ActionResult(ok=False, summary="重置对局失败。")
        return ActionResult(ok=True, summary="当前会话的 PvP 对局已重置。")

    def _execute_skill(
        self,
        state: BattleState,
        actor: BattlePlayerState,
        skill: RoleSkillDefinition,
        target_slot: int | str | None,
    ) -> tuple[str, list[str]]:
        target = self._require_target(state, actor, target_slot) if skill.target_type == "enemy" else None
        details: list[str] = []
        for branch in skill.branches:
            if not self._condition_matches(actor, branch.when):
                continue
            for action in branch.actions:
                self._execute_skill_action(actor, skill, action, details, target)
            summary = f"{actor.player_slot} 号位释放了 {skill.name}。"
            if target is not None:
                summary = f"{summary} 目标为 {target.player_slot} 号位。"
            return summary, details
        return f"{actor.player_slot} 号位释放了 {skill.name}。", details

    def _condition_matches(self, actor: BattlePlayerState, condition: SkillConditionDefinition) -> bool:
        focus = self._get_focus(actor)
        if condition.kind == "always":
            return True
        if condition.kind == "focus_lt":
            return focus < int(condition.value or 0)
        if condition.kind == "focus_gte":
            return focus >= int(condition.value or 0)
        return False

    def _execute_skill_action(
        self,
        actor: BattlePlayerState,
        skill: RoleSkillDefinition,
        action: SkillActionDefinition,
        details: list[str],
        target: BattlePlayerState | None,
    ) -> None:
        params = action.params
        if action.kind == "set_focus":
            self._set_focus(actor, int(params.get("value", 0)))
            return
        if action.kind == "add_focus":
            self._set_focus(actor, self._get_focus(actor) + int(params.get("value", 0)))
            return
        if action.kind == "set_effect":
            actor.set_effect(
                str(params["effect_name"]),
                stacks=int(params.get("stacks", 0)),
                remaining_turns=int(params.get("remaining_turns", -1)),
                payload=dict(params.get("payload", {})),
            )
            return
        if action.kind == "clear_effect":
            actor.remove_effect(str(params["effect_name"]))
            return
        if action.kind == "append_detail":
            details.append(str(params.get("text", "")))
            return
        if action.kind == "attack":
            if target is None:
                raise ValueError(f"{skill.name} 需要一个有效目标。")
            summary, attack_details = self._resolve_attack(
                actor,
                target,
                base_damage=int(params.get("base_damage", actor.atk)),
                allow_multiplier=bool(params.get("allow_multiplier", True)),
                grant_focus=bool(params.get("grant_focus", True)),
            )
            details.append(summary)
            details.extend(attack_details)
            burn_config = params.get("apply_burn")
            if burn_config:
                stacks = int(burn_config.get("stacks", 1))
                remaining_turns = int(burn_config.get("remaining_turns", stacks))
                damage = int(burn_config.get("damage", 2))
                target.set_effect("burn", stacks=stacks, remaining_turns=remaining_turns, payload={"damage": damage})
                details.append(f"{target.player_slot} 号位进入灼烧状态，将在每轮开始时受到 {damage} 点伤害。")
            return
        raise ValueError(f"不支持的技能动作 `{action.kind}`。")

    def _require_battle(self, session_id: str) -> BattleState:
        state = self.repository.load_battle(session_id)
        if state is None:
            raise ValueError("当前会话还没有进行中的 PvP 对局。")
        return state

    def _require_actor_turn(self, session_id: str, user_id: str) -> tuple[BattleState, BattlePlayerState]:
        state = self._require_battle(session_id)
        if state.status != "active":
            raise ValueError("当前对局尚未进入行动阶段，请先完成开局和选角。")
        actor = state.get_player_by_user(user_id)
        if actor is None or not actor.role_id:
            raise ValueError("你还没有加入当前对局，或尚未完成选角。")
        if not actor.alive:
            raise ValueError("你已经被击倒，无法继续行动。")
        if actor.player_slot != state.turn_index:
            raise ValueError(f"当前轮到 {state.turn_index} 号位行动。")
        return state, actor

    def _require_role(self, player: BattlePlayerState) -> RoleDefinition:
        if not player.role_id:
            raise ValueError("当前玩家还没有角色。")
        role = self.characters.get(player.role_id)
        if role is None:
            raise ValueError(f"未找到角色定义 `{player.role_id}`。")
        return role

    def _require_target(
        self,
        state: BattleState,
        actor: BattlePlayerState,
        target_slot: int | str | None,
    ) -> BattlePlayerState | None:
        try:
            slot = int(target_slot)
        except (TypeError, ValueError):
            return None
        target = state.get_player_by_slot(slot)
        if target is None or not target.role_id or not target.alive:
            return None
        if target.player_slot == actor.player_slot:
            return None
        return target

    def _resolve_attack(
        self,
        actor: BattlePlayerState,
        target: BattlePlayerState,
        *,
        base_damage: int,
        allow_multiplier: bool,
        grant_focus: bool = True,
    ) -> tuple[str, list[str]]:
        details: list[str] = []
        damage = base_damage
        focus_after = self._get_focus(actor)

        if allow_multiplier:
            mult_effect = actor.get_effect("next_attack_mult")
            if mult_effect is not None:
                multiplier = max(1, int(mult_effect.payload.get("multiplier", 1)))
                damage *= multiplier
                actor.remove_effect("next_attack_mult")
                details.append(f"{actor.player_slot} 号位触发强化效果，本次伤害倍率为 x{multiplier}。")

        if grant_focus:
            focus_after = min(5, self._get_focus(actor) + 1)
            self._set_focus(actor, focus_after)
            if focus_after < 3:
                bonus = 5 - focus_after
                damage += bonus
                details.append(f"{actor.player_slot} 号位专注未满，获得 {bonus} 点额外伤害。")

        sidestep = target.get_effect("sidestep")
        if sidestep is not None:
            target.remove_effect("sidestep")
            self._set_focus(target, min(5, self._get_focus(target) + 1))
            details.append("闪避成功后，目标额外获得 1 层专注。")
            return f"{target.player_slot} 号位触发侧闪，完全闪避了这次攻击。", details

        target_focus = self._get_focus(target)
        if target_focus >= 5:
            damage = max(0, damage - 2)
            details.append(f"{target.player_slot} 号位专注已满，本次先减免 2 点伤害。")

        dodge_chance = min(target_focus * 15, 60)
        if dodge_chance > 0:
            roll = self.rng.randint(1, 100)
            if roll <= dodge_chance:
                details.append(f"闪避判定成功：掷骰 {roll} / 阈值 {dodge_chance}。")
                return f"{target.player_slot} 号位通过侧身闪避，规避了全部伤害。", details
            details.append(f"闪避判定失败：掷骰 {roll} / 阈值 {dodge_chance}。")

        fortify = target.get_effect("fortify")
        if fortify is not None and fortify.stacks > 0:
            absorbed = min(damage, fortify.stacks)
            damage -= absorbed
            target.remove_effect("fortify")
            details.append(f"{target.player_slot} 号位的护甲吸收了 {absorbed} 点伤害。")

        self._set_focus(target, min(5, self._get_focus(target) + 1))
        if target.cooldowns.get("sidestep", 0) > 0:
            target.cooldowns["sidestep"] = max(0, target.cooldowns["sidestep"] - 1)
            if target.cooldowns["sidestep"] == 0:
                target.cooldowns.pop("sidestep", None)
            details.append(f"{target.player_slot} 号位在受击后缩短了侧闪冷却。")

        actual_damage = max(1, damage - max(target.defense, 0)) if damage > 0 else 0
        target.hp = max(0, target.hp - actual_damage)
        target.alive = target.hp > 0

        if grant_focus and focus_after >= 3 and actual_damage > 0:
            heal_amount = max(1, actual_damage // 2)
            actor.hp = min(actor.max_hp, actor.hp + heal_amount)
            details.append(f"{actor.player_slot} 号位因高专注吸血，恢复了 {heal_amount} 点生命。")

        summary = (
            f"{actor.player_slot} 号位命中 {target.player_slot} 号位，造成 {actual_damage} 点伤害。"
            f" 目标剩余生命 {target.hp}/{target.max_hp}。"
        )
        if not target.alive:
            details.append(f"{target.player_slot} 号位已被击倒。")
        return summary, details

    def _advance_turn(self, state: BattleState, details: list[str]) -> None:
        alive_slots = [player.player_slot for player in state.players if player.alive]
        if len(alive_slots) <= 1:
            state.status = "finished"
            if alive_slots:
                details.append(f"对局已结束，{alive_slots[0]} 号位获胜。")
            return

        next_slots = [slot for slot in alive_slots if slot > state.turn_index]
        if next_slots:
            state.turn_index = next_slots[0]
            details.append(f"现在轮到 {state.turn_index} 号位行动。")
            return

        state.round_index += 1
        self._start_new_round(state, details)

    def _start_new_round(self, state: BattleState, details: list[str]) -> None:
        for player in state.players:
            if not player.role_id:
                continue
            if player.alive:
                player.ap = player.max_ap

            for skill_key, remaining in list(player.cooldowns.items()):
                if remaining <= 1:
                    player.cooldowns.pop(skill_key, None)
                else:
                    player.cooldowns[skill_key] = remaining - 1

            for effect in list(player.effects):
                if effect.effect_name == "focus":
                    continue
                if effect.effect_name == "burn" and player.alive:
                    damage = max(1, int(effect.payload.get("damage", 2)))
                    player.hp = max(0, player.hp - damage)
                    player.alive = player.hp > 0
                    details.append(
                        f"{player.player_slot} 号位因灼烧受到 {damage} 点伤害，剩余生命 {player.hp}/{player.max_hp}。"
                    )

                if effect.remaining_turns > 0:
                    effect.remaining_turns -= 1
                if effect.remaining_turns == 0:
                    player.remove_effect(effect.effect_name)

        alive_slots = [player.player_slot for player in state.players if player.alive]
        if len(alive_slots) <= 1:
            state.status = "finished"
            if alive_slots:
                details.append(f"对局已结束，{alive_slots[0]} 号位获胜。")
            return

        state.turn_index = alive_slots[0]
        details.append(f"进入第 {state.round_index} 轮，现在轮到 {state.turn_index} 号位行动。")

    def _finalize_state_after_action(self, state: BattleState) -> None:
        alive_slots = [player.player_slot for player in state.players if player.alive]
        if state.status == "active" and len(alive_slots) <= 1:
            state.status = "finished"
        if len(state.logs) > 50:
            state.logs = state.logs[-50:]

    def _save_state(self, state: BattleState) -> None:
        state.updated_at = self._now()
        self.repository.save_battle(state)

    def _append_log(
        self,
        state: BattleState,
        *,
        actor_slot: int | None,
        action_type: str,
        summary: str,
        detail: dict | None = None,
    ) -> None:
        state.logs.append(
            BattleLogEntry(
                turn_index=state.turn_index,
                actor_slot=actor_slot,
                action_type=action_type,
                summary=summary,
                detail_json=detail or {},
                created_at=self._now(),
            )
        )

    @staticmethod
    def _all_players_ready(state: BattleState) -> bool:
        return all(player.user_id and player.role_id for player in state.players)

    @staticmethod
    def _first_alive_slot(state: BattleState) -> int:
        for player in state.players:
            if player.alive:
                return player.player_slot
        return 1

    @staticmethod
    def _get_focus(player: BattlePlayerState) -> int:
        focus = player.get_effect("focus")
        return focus.stacks if focus else 0

    @staticmethod
    def _set_focus(player: BattlePlayerState, value: int) -> None:
        player.set_effect("focus", stacks=max(0, min(5, value)), remaining_turns=-1)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
