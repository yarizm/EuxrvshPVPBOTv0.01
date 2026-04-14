from __future__ import annotations


def __getattr__(name: str):
    raise RuntimeError(
        "旧版 `db.py` 兼容接口已废弃。当前插件已改为 SQLite 本地存储，不再暴露 MySQL 连接。"
    )
