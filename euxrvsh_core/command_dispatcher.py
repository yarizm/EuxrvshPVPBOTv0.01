from __future__ import annotations

from dataclasses import dataclass

from euxrvsh_core.services import GameService


@dataclass(frozen=True)
class DispatchResult:
    matched: bool
    response: str = ""


class CommandDispatcher:
    def __init__(self, game_service: GameService):
        self.game_service = game_service

    def dispatch(self, raw_message: str, user_id: str = "unknown_user") -> DispatchResult:
        if not raw_message:
            return DispatchResult(matched=False)

        message = raw_message.strip()
        if not message:
            return DispatchResult(matched=False)

        parts = message.split(maxsplit=1)
        command_token = parts[0]
        params = parts[1] if len(parts) > 1 else ""
        normalized = command_token.lstrip("/").upper()
        if normalized == "寮€":
            normalized = "START"

        handler = getattr(self, f"_handle_{normalized}", None)
        if handler is None:
            return DispatchResult(matched=False)
        return DispatchResult(matched=True, response=handler(params, user_id))

    def _handle_START(self, params: str, user_id: str) -> str:
        if not params:
            return "请输入游戏人数，例如：/START 2"
        try:
            result = self.game_service.start_game(int(params))
        except Exception as exc:
            return f"启动失败：{exc}"

        return (
            f"启动成功，玩家人数设为 {result}。\n"
            "接下来请使用 /PICK [角色ID] 选择角色。\n"
            "当前为第 1 回合准备阶段。"
        )

    def _handle_PICK(self, params: str, user_id: str) -> str:
        if not params:
            return "请输入角色 ID，例如：/PICK 1"
        try:
            return self.game_service.pick_role(int(params.split()[0]))
        except Exception as exc:
            return f"选角出错：{exc}"

    def _handle_OUT(self, params: str, user_id: str) -> str:
        try:
            burn_report = self.game_service.trigger_all_burning()
            heal_report = self.game_service.trigger_all_recovery()
            self.game_service.reset_defense()
            self.game_service.remsubauto()
            prob_report = self.game_service.outprint_optimized()
            data_report = self.game_service.turnend(1)
        except Exception as exc:
            return f"结算报错：{exc}"

        burn_section = f"--- 灼烧伤害 ---\n{chr(10).join(burn_report)}\n\n" if burn_report else ""
        heal_section = f"--- 回复效果 ---\n{chr(10).join(heal_report)}\n\n" if heal_report else ""
        return (
            "【回合结算】\n"
            f"{burn_section}"
            f"{heal_section}"
            f"--- 行动值恢复 ---\n{chr(10).join(prob_report)}\n\n"
            f"--- 玩家状态 ---\n{chr(10).join(data_report)}\n\n"
            "请行动值足够的玩家继续输入指令。"
        )

    def _handle_END(self, params: str, user_id: str) -> str:
        if self.game_service.end_game():
            return "游戏已结束，数据已重置。"
        return "结束游戏失败，请检查日志。"

    def _handle_HPC(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 3:
            return "参数不足，格式：/HPC [ID] [数值] [类型0/1]"
        return self.game_service.hp_change(args[0], args[1], args[2])

    def _handle_ATTACK(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 3:
            return "参数不足，格式：/ATTACK [攻击者ID] [目标ID] [伤害]"
        bleed_msg = self.game_service.trigger_bleeding(args[0])
        result = self.game_service.attack(args[0], args[1], args[2])
        return f"{bleed_msg}\n{result}".strip() if bleed_msg else result

    def _handle_SKILL(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 2:
            return "参数不足，格式：/SKILL [玩家ID] [技能号]"
        bleed_msg = self.game_service.trigger_bleeding(args[0])
        result = self.game_service.skill_use(args[0], args[1])
        return f"{bleed_msg}\n{result}".strip() if bleed_msg else result

    def _handle_ATKC(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 2:
            return "参数不足，格式：/ATKC [ID] [数值]"
        return self.game_service.atk_change(args[0], args[1])

    def _handle_DEFC(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 2:
            return "参数不足，格式：/DEFC [ID] [数值]"
        return self.game_service.def_change(args[0], args[1])

    def _handle_DISC(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 2:
            return "参数不足，格式：/DISC [ID] [数值]"
        return self.game_service.distance_change(args[0], args[1])

    def _handle_CDC(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 3:
            return "参数不足，格式：/CDC [ID] [技能号] [数值]"
        return self.game_service.cd_change(args[0], args[1], args[2])

    def _handle_BLEED(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 2:
            return "参数不足，格式：/BLEED [玩家ID] [持续回合]"
        return self.game_service.bleeding(args[0], args[1])

    def _handle_BURN(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 2:
            return "参数不足，格式：/BURN [玩家ID] [持续回合]"
        return self.game_service.burning(args[0], args[1])

    def _handle_HEAL(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 3:
            return "参数不足，格式：/HEAL [玩家ID] [回复等级] [持续回合]"
        return self.game_service.recovery(args[0], args[1], args[2])

    def _handle_REMTIME(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 3:
            return "参数不足，格式：/REMTIME [玩家ID] [名称] [持续回合]"
        return self.game_service.timerem(args[0], args[1], args[2])

    def _handle_TIMEINFO(self, params: str, user_id: str) -> str:
        result = self.game_service.timeinfo()
        return "\n".join(result) if result else "当前没有计时器。"

    def _handle_TIMESET(self, params: str, user_id: str) -> str:
        args = params.split()
        if len(args) < 3:
            return "参数不足，格式：/TIMESET [玩家ID] [名称] [增减值]"
        return self.game_service.remsubhand(args[0], args[1], args[2])

    def _handle_ROLEDATA(self, params: str, user_id: str) -> str:
        result = self.game_service.turnend(0)
        return "当前数据：\n" + "\n\n".join(result)

    def _handle_RATE(self, params: str, user_id: str) -> str:
        try:
            result = self.game_service.event_occurs(float(params))
        except (TypeError, ValueError):
            return "参数不足，格式：/RATE [概率]"
        return "判定成功。" if result else "判定失败。"

    def _handle_HELP(self, params: str, user_id: str) -> str:
        return (
            "局内指令一览：\n\n"
            "/HPC [ID] [数值] [类型0/1]\n"
            "/ATKC [ID] [数值]\n"
            "/DEFC [ID] [数值]\n"
            "/DISC [ID] [数值]\n"
            "/CDC [ID] [技能号] [数值]\n"
            "/SKILL [ID] [技能号]\n"
            "/ATTACK [攻击者ID] [目标ID] [伤害]\n"
            "/BLEED [玩家ID] [持续回合]\n"
            "/BURN [玩家ID] [持续回合]\n"
            "/HEAL [玩家ID] [回复等级] [持续回合]\n"
            "/ROLEDATA\n"
            "/OUT\n"
            "/END\n"
            "/RATE [概率]"
        )
