from __future__ import annotations

import os
import sys

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

PLUGIN_DIR = os.path.dirname(__file__)
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from euxrvsh_core.astrbot_memory import record_conversation_pair
from euxrvsh_core.config import runtime_config_from_mapping
from euxrvsh_core.runtime import build_runtime
from euxrvsh_core.startup_check import run_startup_check


@register(
    "astrbot_plugin_euxrvsh_pvp",
    "YARIZM",
    "Euxrvsh PvP 游戏插件",
    "1.0.0",
    "https://github.com/YARIZM/EuxrvshPVPBOT",
)
class EuxrvshAstrBotPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        self.runtime = None

        runtime_config = runtime_config_from_mapping(config)
        check_result = run_startup_check(runtime_config.database)

        logger.info("Euxrvsh PvP 插件启动自检开始。")
        logger.info(
            "Euxrvsh PvP 数据库配置：host=%s user=%s db=%s pool=%s size=%s",
            runtime_config.database.host,
            runtime_config.database.user,
            runtime_config.database.database,
            runtime_config.database.pool_name,
            runtime_config.database.pool_size,
        )

        for error in check_result.errors:
            logger.error("Euxrvsh PvP 自检失败：%s", error)
        for warning in check_result.warnings:
            logger.warning("Euxrvsh PvP 自检警告：%s", warning)

        if not check_result.ok:
            logger.error("Euxrvsh PvP 插件未就绪，已跳过运行时初始化。")
            return

        try:
            self.runtime = build_runtime(config)
        except Exception as exc:
            logger.exception("Euxrvsh PvP 运行时初始化失败：%s", exc)
            return

        logger.info("Euxrvsh PvP 插件启动自检通过，运行时已就绪。")

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        message = (event.message_str or "").strip()

        if self.runtime is None:
            if message.startswith("/"):
                yield event.plain_result("插件未就绪，请先检查 AstrBot 后台日志中的 Euxrvsh PvP 自检结果。")
                event.stop_event()
            return

        result = self.runtime.dispatcher.dispatch(message, user_id=self._get_user_id(event))
        if not result.matched:
            return

        try:
            recorded = await record_conversation_pair(
                conversation_manager=getattr(self.context, "conversation_manager", None),
                unified_msg_origin=str(getattr(event, "unified_msg_origin", "") or ""),
                user_text=message,
                assistant_text=result.response,
            )
            if recorded:
                logger.info("Euxrvsh PvP 已将游戏记录写入 AstrBot 对话历史。")
        except Exception as exc:
            logger.warning("Euxrvsh PvP 写入 AstrBot 对话历史失败：%s", exc)

        logger.info("Euxrvsh AstrBot command handled: %s", message)
        yield event.plain_result(result.response)
        event.stop_event()

    @staticmethod
    def _get_user_id(event: AstrMessageEvent) -> str:
        session_id = getattr(event, "unified_msg_origin", "")
        if session_id:
            return str(session_id)
        sender_id = getattr(event, "get_sender_id", None)
        if callable(sender_id):
            return str(sender_id())
        return "unknown_user"
