from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

PLUGIN_DIR = os.path.dirname(__file__)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

try:
    from plugin import PVP_TOOL_NAMES, PvpApplication
except ImportError:
    from astrbot_plugin_euxrvsh_pvp.plugin import PVP_TOOL_NAMES, PvpApplication
from euxrvsh_core.astrbot_memory import record_conversation_pair
from euxrvsh_core.runtime import build_runtime
from euxrvsh_core.startup_check import run_startup_check

GROUP_REPLY_COOLDOWN_SECONDS = 5.0

PVP_AGENT_GUIDE = "\n".join(
    [
        "当用户在聊天里表达 PvP 对战意图时，优先使用 PvP 工具，而不是纯文字猜测结果。",
        "常见触发话术包括：开一把 2 人局、来一局对战、我选输出大王、我打 2 号、我用链爆打 2 号、看看战况、结束回合、重开这局。",
        "如果当前还没有对局，优先创建对局或先列出角色。",
        "非游戏闲聊不要调用 PvP 工具。",
        "群聊中尽量减少额外说明和追问，能直接执行时就直接执行。",
    ]
)


@register(
    "astrbot_plugin_euxrvsh_pvp",
    "YARIZM",
    "Euxrvsh PvP 游戏插件",
    "2.1.0",
    "https://github.com/yarizm/EuxrvshPVPBOTv0.01",
)
class EuxrvshAstrBotPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.runtime = None
        self.app = None
        self._group_reply_cooldowns: dict[str, float] = {}

        default_sqlite_path = self._default_sqlite_path()
        configured_sqlite_path = str(self.config.get("sqlite_path", "")).strip()
        sqlite_path = str(Path(configured_sqlite_path).expanduser()) if configured_sqlite_path else str(default_sqlite_path)

        check_result = run_startup_check(sqlite_path)
        for error in check_result.errors:
            logger.error("Euxrvsh PvP 启动检查失败：%s", error)
        for warning in check_result.warnings:
            logger.warning("Euxrvsh PvP 启动检查警告：%s", warning)
        if not check_result.ok:
            return

        self.runtime = build_runtime(self.config, default_sqlite_path=str(default_sqlite_path))
        self.app = PvpApplication(self.runtime.battle_service)
        logger.info("Euxrvsh PvP 初始化完成，SQLite 路径：%s", self.runtime.config.sqlite_path)
        logger.info("Euxrvsh PvP 已注册工具：%s", ", ".join(PVP_TOOL_NAMES))
        logger.info("Euxrvsh PvP Agent 提示：%s", PVP_AGENT_GUIDE)

    @filter.command_group("pvp")
    def pvp(self):
        """PvP 兜底命令组。"""

    @pvp.command("help")
    async def pvp_help(self, event: AstrMessageEvent):
        yield event.plain_result(self._help_text())
        event.stop_event()

    @pvp.command("start")
    async def pvp_start(self, event: AstrMessageEvent, player_count: int):
        response = self._run_fallback_command(event, self.app.create_battle, player_count)
        yield event.plain_result(response)
        event.stop_event()

    @pvp.command("roles")
    async def pvp_roles(self, event: AstrMessageEvent):
        response = self._run_fallback_command(event, self.app.list_roles)
        yield event.plain_result(response)
        event.stop_event()

    @pvp.command("pick")
    async def pvp_pick(self, event: AstrMessageEvent, role_key: str):
        response = self._run_fallback_command(event, self.app.pick_role, role_key)
        yield event.plain_result(response)
        event.stop_event()

    @pvp.command("state")
    async def pvp_state(self, event: AstrMessageEvent, detail: str = "summary"):
        response = self._run_fallback_command(event, self.app.view_state, detail)
        yield event.plain_result(response)
        event.stop_event()

    @pvp.command("endturn")
    async def pvp_endturn(self, event: AstrMessageEvent):
        response = self._run_fallback_command(event, self.app.end_turn)
        yield event.plain_result(response)
        event.stop_event()

    @pvp.command("reset")
    async def pvp_reset(self, event: AstrMessageEvent, force: bool = True):
        response = self._run_fallback_command(event, self.app.reset_battle, force)
        yield event.plain_result(response)
        event.stop_event()

    @filter.llm_tool(name="pvp_create_battle")
    async def llm_create_battle(self, event: AstrMessageEvent, player_count: int):
        """创建一场 PvP 对局。

        适用意图：用户想开局、来一局、创建 2 到 4 人对战。
        常见说法：开一把 2 人局、来一局对战、创建三人 PvP。

        Args:
            player_count(number): 对局人数，推荐 2 到 4。
        """
        return self._run_tool(event, self.app.create_battle, player_count)

    @filter.llm_tool(name="pvp_list_roles")
    async def llm_list_roles(self, event: AstrMessageEvent):
        """查看当前可选角色列表。

        适用意图：用户想知道能玩什么角色、角色技能是什么、先看职业介绍。
        常见说法：有哪些角色、给我看看技能、我能选什么。
        当用户还没决定选谁时，优先调用这个工具。
        如果用户只是在闲聊“你喜欢什么角色”，不要调用。
        """
        return self._run_tool(event, self.app.list_roles)

    @filter.llm_tool(name="pvp_pick_role")
    async def llm_pick_role(self, event: AstrMessageEvent, role_key: str):
        """选择当前对局中的角色。

        适用意图：用户明确要选角、换角色、确认自己的角色。
        常见说法：我选输出大王、帮我选 output_king、我要这个角色。

        Args:
            role_key(string): 角色 ID 或角色名称，例如 output_king 或 输出大王。
        """
        return self._run_tool(event, self.app.pick_role, role_key)

    @filter.llm_tool(name="pvp_attack")
    async def llm_attack(self, event: AstrMessageEvent, target_slot: int):
        """对指定目标执行普通攻击。

        适用意图：用户明确表示要平 A、普攻、打某个号位。
        常见说法：我打 2 号、普攻二号位、A 2。
        非 PvP 闲聊不要调用。

        Args:
            target_slot(number): 目标号位，例如 2 表示攻击 2 号位。
        """
        return self._run_tool(event, self.app.attack, target_slot)

    @filter.llm_tool(name="pvp_use_skill")
    async def llm_use_skill(self, event: AstrMessageEvent, skill_key: str, target_slot: int = 0):
        """使用技能。

        适用意图：用户明确要放技能、点名某个技能、技能命中某个目标。
        常见说法：我用聚势、我开侧闪、我用链爆打 2 号。
        无目标技能可把 target_slot 留为 0；有目标技能则传入对应号位。

        Args:
            skill_key(string): 技能 ID，例如 focus_shift、sidestep、chain_burst。
            target_slot(number): 目标号位；无目标技能可填 0。
        """
        target = None if int(target_slot) == 0 else target_slot
        return self._run_tool(event, self.app.use_skill, skill_key, target)

    @filter.llm_tool(name="pvp_end_turn")
    async def llm_end_turn(self, event: AstrMessageEvent):
        """结束当前玩家回合。

        适用意图：用户想结束自己这回合、跳过操作、让下一个人行动。
        常见说法：结束回合、过、下一个、我不动了。
        """
        return self._run_tool(event, self.app.end_turn)

    @filter.llm_tool(name="pvp_view_state")
    async def llm_view_state(self, event: AstrMessageEvent, detail: str = "summary"):
        """查看当前对局状态。

        适用意图：用户想看战况、轮到谁、血量、AP、冷却、最近发生了什么。
        常见说法：看看战况、现在谁的回合、我还有多少血、详细状态。
        如果用户问的是普通闲聊上下文，不要误判成 PvP 状态查询。

        Args:
            detail(string): summary 或 full。
        """
        return self._run_tool(event, self.app.view_state, detail)

    @filter.llm_tool(name="pvp_reset_battle")
    async def llm_reset_battle(self, event: AstrMessageEvent, force: bool = False):
        """重置当前会话中的 PvP 对局。

        适用意图：用户想重开、清空这局、结束当前对战重新来。
        常见说法：重开这局、重置对战、清空当前 PvP。

        Args:
            force(boolean): 是否强制重置已开始的对局。
        """
        return self._run_tool(event, self.app.reset_battle, force)

    def _run_tool(self, event: AstrMessageEvent, fn, *args, apply_cooldown: bool = True):
        if self.app is None:
            return "插件尚未初始化完成，请稍后再试。"
        if apply_cooldown:
            cooldown_message = self._check_group_cooldown(event)
            if cooldown_message is not None:
                return cooldown_message

        session_id = self._get_session_id(event)
        user_id = self._get_user_id(event)
        name = getattr(fn, "__name__", "")

        if name == "list_roles":
            return fn()
        if name == "view_state":
            return fn(session_id, *args)
        if name in {"create_battle", "pick_role", "attack", "use_skill", "end_turn", "reset_battle"}:
            return fn(session_id, user_id, *args)
        return "未识别的工具调用。"

    def _run_fallback_command(self, event: AstrMessageEvent, fn, *args):
        if self.app is None or self.runtime is None:
            return "插件尚未初始化完成，请先检查后台日志。"
        if not self.runtime.config.enable_fallback_commands:
            return "当前插件已关闭 `/pvp` 兜底命令，请直接用自然语言让 AI 调用工具。"
        cooldown_message = self._check_group_cooldown(event)
        if cooldown_message is not None:
            return cooldown_message

        response = self._run_tool(event, fn, *args, apply_cooldown=False)
        self._remember_fallback_command(event, response)
        return response

    def _remember_fallback_command(self, event: AstrMessageEvent, response: str) -> None:
        try:
            asyncio.create_task(
                record_conversation_pair(
                    conversation_manager=getattr(self.context, "conversation_manager", None),
                    unified_msg_origin=self._get_session_id(event),
                    user_text=(event.message_str or "").strip(),
                    assistant_text=response,
                )
            )
        except Exception as exc:
            logger.warning("Euxrvsh PvP 写入对话历史失败：%s", exc)

    def _default_sqlite_path(self) -> Path:
        plugin_name = getattr(self, "name", "astrbot_plugin_euxrvsh_pvp")
        base_path = Path(str(get_astrbot_data_path()))
        return base_path / "plugin_data" / plugin_name / "battle.sqlite"

    def _check_group_cooldown(self, event: AstrMessageEvent) -> str | None:
        if not self._is_group_event(event):
            return None

        session_id = self._get_session_id(event)
        now = time.monotonic()
        last_reply_at = self._group_reply_cooldowns.get(session_id, 0.0)
        remaining = GROUP_REPLY_COOLDOWN_SECONDS - (now - last_reply_at)
        if remaining > 0:
            return f"群聊冷却中，请 {remaining:.1f} 秒后再试。"

        self._group_reply_cooldowns[session_id] = now
        return None

    @staticmethod
    def _get_session_id(event: AstrMessageEvent) -> str:
        session_id = getattr(event, "unified_msg_origin", "")
        if session_id:
            return str(session_id)
        sender_id = getattr(event, "get_sender_id", None)
        if callable(sender_id):
            return str(sender_id())
        return "unknown_session"

    @staticmethod
    def _get_user_id(event: AstrMessageEvent) -> str:
        sender_id = getattr(event, "get_sender_id", None)
        if callable(sender_id):
            return str(sender_id())
        return str(getattr(event, "unified_msg_origin", "") or "unknown_user")

    @classmethod
    def _is_group_event(cls, event: AstrMessageEvent) -> bool:
        for attr_name in ("is_group", "is_group_message"):
            attr = getattr(event, attr_name, None)
            if isinstance(attr, bool):
                return attr
            if callable(attr):
                try:
                    return bool(attr())
                except Exception:
                    pass

        for attr_name in ("group_id", "group_openid", "guild_id", "channel_id"):
            if getattr(event, attr_name, None):
                return True

        session_id = cls._get_session_id(event).lower()
        return any(token in session_id for token in ("group", "guild", "channel"))

    @staticmethod
    def _help_text() -> str:
        return "\n".join(
            [
                "PvP 兜底命令：",
                "/pvp start <人数>",
                "/pvp roles",
                "/pvp pick <角色名或ID>",
                "/pvp state [summary|full]",
                "/pvp endturn",
                "/pvp reset",
                "",
                "自然语言示例：",
                "开一把 2 人局",
                "我选输出大王",
                "我打 2 号",
                "我用链爆打 2 号",
                "看看战况",
                "结束回合",
            ]
        )
