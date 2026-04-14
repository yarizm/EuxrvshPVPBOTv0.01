from __future__ import annotations


def __getattr__(name: str):
    raise RuntimeError(
        "旧版 `game_utils.py` 兼容接口已废弃。请改用 AstrBot 插件工具或新的 BattleService。"
    )
