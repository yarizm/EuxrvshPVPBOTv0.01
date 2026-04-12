# -*- coding: utf-8 -*-
from __future__ import annotations

import botpy
from botpy import logging
from botpy.message import Message

from euxrvsh_core.config import load_legacy_app_config
from euxrvsh_core.runtime import build_legacy_runtime

_log = logging.get_logger()
_legacy_config = load_legacy_app_config()
_runtime = build_legacy_runtime()


class MyClient(botpy.Client):
    async def on_ready(self):
        _log.info(f"robot {self.robot.name} on_ready!")

    async def on_group_at_message_create(self, message: Message):
        user_id = (
            getattr(message.author, "id", None)
            or getattr(message.author, "member_openid", None)
            or "unknown_user"
        )
        result = _runtime.dispatcher.dispatch(message.content, user_id=str(user_id))
        if result.matched:
            await message.reply(content=result.response)


if __name__ == "__main__":
    intents = botpy.Intents(public_messages=True)
    client = MyClient(intents=intents)
    client.run(appid=_legacy_config.appid, secret=_legacy_config.secret)
