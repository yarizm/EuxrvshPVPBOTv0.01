from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StartupCheckResult:
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def run_startup_check(storage_root: str, *, sqlite_path_compat_used: bool = False) -> StartupCheckResult:
    root = Path(storage_root).expanduser()
    errors: list[str] = []
    warnings: list[str] = []

    if root.exists() and root.is_file():
        errors.append(f"storage_root `{root}` 指向的是文件，而不是目录。")
        return StartupCheckResult(ok=False, errors=tuple(errors))

    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        errors.append(f"无法创建插件存储目录 `{root}`：{exc}")
        return StartupCheckResult(ok=False, errors=tuple(errors))

    if sqlite_path_compat_used:
        warnings.append("检测到仍在使用兼容字段 `sqlite_path`，当前已将其父目录视为 storage_root。")

    return StartupCheckResult(ok=True, warnings=tuple(warnings))
