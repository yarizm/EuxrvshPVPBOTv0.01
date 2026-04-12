from __future__ import annotations

from dataclasses import dataclass

import mysql.connector

from euxrvsh_core.config import DatabaseConfig

REQUIRED_TABLES = (
    "player_stats",
    "timers",
    "skill_cooldowns",
    "roles",
    "roleora",
    "role_templates",
    "playnum",
    "euxrate",
)


@dataclass(frozen=True)
class StartupCheckResult:
    ok: bool
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def validate_database_config(config: DatabaseConfig) -> list[str]:
    issues: list[str] = []
    if not str(config.host).strip():
        issues.append("缺少数据库配置项 `db_host`。")
    if not str(config.user).strip():
        issues.append("缺少数据库配置项 `db_user`。")
    if not str(config.password).strip():
        issues.append("缺少数据库配置项 `db_password`。")
    if not str(config.database).strip():
        issues.append("缺少数据库配置项 `db_name`。")
    if not str(config.pool_name).strip():
        issues.append("缺少数据库配置项 `db_pool_name`。")
    if int(config.pool_size) <= 0:
        issues.append("数据库配置项 `db_pool_size` 必须大于 0。")
    return issues


def format_mysql_error(exc: mysql.connector.Error, config: DatabaseConfig) -> str:
    errno = getattr(exc, "errno", None)
    if errno == 1045:
        return (
            f"MySQL 认证失败：无法使用用户 `{config.user}` 连接 `{config.host}`。"
            " 请检查 `db_user` 和 `db_password`。"
        )
    if errno == 1049:
        return f"MySQL 数据库 `{config.database}` 不存在，请检查 `db_name`。"
    if errno == 2003:
        return f"MySQL 连接失败：无法连接到 `{config.host}`，请检查 `db_host` 和数据库服务状态。"
    if errno == 2005:
        return f"MySQL 主机名 `{config.host}` 无法解析，请检查 `db_host`。"
    return f"MySQL 自检失败：{exc}"


def run_startup_check(config: DatabaseConfig) -> StartupCheckResult:
    config_issues = validate_database_config(config)
    if config_issues:
        return StartupCheckResult(ok=False, errors=tuple(config_issues))

    conn = None
    cursor = None
    try:
        conn = mysql.connector.connect(
            host=config.host,
            user=config.user,
            password=config.password,
            database=config.database,
        )
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        existing_tables = {str(row[0]) for row in cursor.fetchall()}
        missing_tables = [table for table in REQUIRED_TABLES if table not in existing_tables]

        warnings: list[str] = []
        if missing_tables:
            warnings.append(
                "数据库已连接，但缺少核心表："
                + ", ".join(missing_tables)
                + "。请先初始化 schema。"
            )
        return StartupCheckResult(ok=not missing_tables, warnings=tuple(warnings))
    except mysql.connector.Error as exc:
        return StartupCheckResult(ok=False, errors=(format_mysql_error(exc, config),))
    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()
