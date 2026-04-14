from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StartupCheckResult:
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def run_startup_check(sqlite_path: str) -> StartupCheckResult:
    path = Path(sqlite_path).expanduser()
    errors: list[str] = []

    if path.exists() and path.is_dir():
        errors.append(f"SQLite 路径 `{path}` 指向的是目录，而不是数据库文件。")
        return StartupCheckResult(ok=False, errors=tuple(errors))

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        errors.append(f"无法创建 SQLite 数据目录 `{path.parent}`：{exc}")
        return StartupCheckResult(ok=False, errors=tuple(errors))

    try:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.close()
    except sqlite3.Error as exc:
        errors.append(f"无法初始化 SQLite 数据库 `{path}`：{exc}")
        return StartupCheckResult(ok=False, errors=tuple(errors))

    return StartupCheckResult(ok=True)
