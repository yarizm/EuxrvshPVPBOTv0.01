from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

import mysql.connector
import mysql.connector.pooling

from euxrvsh_core.config import DatabaseConfig


@dataclass(frozen=True)
class PlayerStatus:
    max_hp: int
    now_hp: int
    turn_def: int
    total_def: int
    atk: int
    distance: int
    now_ap: int
    max_ap: int


@dataclass(frozen=True)
class PlayerApContext:
    now_ap: int
    max_ap: int
    ap_recover_min: int
    ap_recover_max: int


@dataclass(frozen=True)
class DefResetContext:
    current_def: int
    total_def: int
    base_def: int


class MySQLGameRepository:
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.connection_pool = self._create_pool()

    def _create_pool(self) -> mysql.connector.pooling.MySQLConnectionPool:
        try:
            return mysql.connector.pooling.MySQLConnectionPool(
                host=self.config.host,
                user=self.config.user,
                password=self.config.password,
                database=self.config.database,
                pool_name=self.config.pool_name,
                pool_size=self.config.pool_size,
            )
        except mysql.connector.pooling.PoolError:
            return mysql.connector.pooling.MySQLConnectionPool(pool_name=self.config.pool_name)

    @contextmanager
    def cursor(self, commit: bool = False):
        conn = None
        cursor = None
        try:
            conn = self.connection_pool.get_connection()
            cursor = conn.cursor(dictionary=False, buffered=True)
            yield cursor
            conn.commit()
        except mysql.connector.Error:
            if conn:
                conn.rollback()
            raise
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if cursor:
                cursor.close()
            if conn:
                conn.close()

    def initialize_game(self, play_num: int) -> int:
        with self.cursor(commit=True) as cursor:
            cursor.execute("UPDATE playnum SET play_num = %s, nums = 1", (play_num,))
            cursor.execute("TRUNCATE TABLE skill_cooldowns")
            cursor.execute("TRUNCATE TABLE timers")
            cursor.execute("DELETE FROM player_stats")
            cursor.execute("UPDATE euxrate SET iswin=0, x_value=0, isgive=0, winrate=0.5")
            cursor.execute("UPDATE roles SET player_id = NULL")
        return play_num

    def end_game(self) -> None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE euxrate SET winrate=0.5, isdiff=0, iswin=NULL, x_value=0, isgive=0, totalturn=0, giveturn=0"
            )
            cursor.execute("UPDATE roles SET player_id = NULL")
            cursor.execute("DELETE FROM player_stats")
            cursor.execute("DELETE FROM skill_cooldowns")
            cursor.execute("DELETE FROM timers")

    def pick_role_for_next_player(self, role_id: int) -> tuple[int, str, int, int]:
        with self.cursor(commit=True) as cursor:
            cursor.execute("SELECT nums FROM playnum FOR UPDATE")
            row = cursor.fetchone()
            current_player_id = int(row[0]) if row else 1

            cursor.execute("SELECT player_id, name FROM roles WHERE id = %s", (role_id,))
            role_row = cursor.fetchone()
            if not role_row:
                raise ValueError("角色不存在")
            if role_row[0] is not None:
                raise ValueError(f"角色 {role_row[1]} 已被其他玩家使用")

            cursor.execute("UPDATE roles SET player_id = %s WHERE id = %s", (current_player_id, role_id))

            cursor.execute("SELECT turndef, totaldef FROM roleora WHERE id = %s", (role_id,))
            def_row = cursor.fetchone()
            turn_def_init = int(def_row[0]) if def_row and def_row[0] is not None else 0
            total_def_init = int(def_row[1]) if def_row and def_row[1] is not None else 0

            cursor.execute(
                """
                INSERT INTO player_stats (
                    player_id, role_id, max_hp, now_hp, atk, distance, turn_def, total_def, now_ap, max_ap
                )
                SELECT %s, id, base_max_hp, base_max_hp, base_atk, base_dist, %s, %s, 0, max_ap
                FROM role_templates
                WHERE id = %s
                """,
                (current_player_id, turn_def_init, total_def_init, role_id),
            )

            cursor.execute("UPDATE playnum SET nums = nums + 1")
            return current_player_id, str(role_row[1]), turn_def_init, total_def_init

    def get_player_role_id(self, player_id: int) -> int | None:
        with self.cursor() as cursor:
            cursor.execute("SELECT role_id FROM player_stats WHERE player_id = %s", (player_id,))
            row = cursor.fetchone()
            return int(row[0]) if row else None

    def get_role_skill_cd(self, role_id: int, skill_idx: int) -> int:
        with self.cursor() as cursor:
            cursor.execute(f"SELECT art{skill_idx} FROM roleora WHERE id = %s", (role_id,))
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

    def get_skill_cd(self, player_id: int, skill_idx: int) -> int:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT current_cd FROM skill_cooldowns WHERE player_id=%s AND skill_index=%s",
                (player_id, skill_idx),
            )
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0

    def set_skill_cd(self, player_id: int, skill_idx: int, current_cd: int) -> None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO skill_cooldowns (player_id, skill_index, current_cd)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE current_cd = %s
                """,
                (player_id, skill_idx, current_cd, current_cd),
            )

    def adjust_skill_cd(self, player_id: int, skill_idx: int, delta: int) -> int | None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE skill_cooldowns
                SET current_cd = GREATEST(0, current_cd + %s)
                WHERE player_id = %s AND skill_index = %s
                """,
                (delta, player_id, skill_idx),
            )
            if cursor.rowcount == 0:
                return None
            cursor.execute(
                "SELECT current_cd FROM skill_cooldowns WHERE player_id=%s AND skill_index=%s",
                (player_id, skill_idx),
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def decrement_all_skill_cds(self) -> None:
        with self.cursor(commit=True) as cursor:
            cursor.execute("UPDATE skill_cooldowns SET current_cd = current_cd - 1 WHERE current_cd > 0")

    def get_play_num(self) -> int:
        with self.cursor() as cursor:
            cursor.execute("SELECT play_num FROM playnum")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def get_player_status(self, player_id: int) -> PlayerStatus | None:
        with self.cursor() as cursor:
            cursor.execute(
                """
                SELECT max_hp, now_hp, turn_def, total_def, atk, distance, now_ap, max_ap
                FROM player_stats
                WHERE player_id = %s
                """,
                (player_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return PlayerStatus(*[int(value or 0) for value in row])

    def list_active_skill_cds(self, player_id: int) -> list[tuple[int, int]]:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT skill_index, current_cd FROM skill_cooldowns WHERE player_id = %s AND current_cd > 0",
                (player_id,),
            )
            return [(int(skill_idx), int(current_cd)) for skill_idx, current_cd in cursor.fetchall()]

    def resolve_attack_damage(self, player_id: int, damage_value: int) -> tuple[int, int, int] | None:
        with self.cursor(commit=True) as cursor:
            cursor.execute("SELECT turn_def FROM player_stats WHERE player_id = %s FOR UPDATE", (player_id,))
            row = cursor.fetchone()
            if not row:
                return None
            current_def = int(row[0])
            if damage_value <= current_def:
                actual_hp_damage = 1
                def_reduction = damage_value - 1
            else:
                actual_hp_damage = damage_value - current_def
                def_reduction = current_def
            cursor.execute(
                """
                UPDATE player_stats
                SET now_hp = now_hp - %s, turn_def = turn_def - %s
                WHERE player_id = %s
                """,
                (actual_hp_damage, def_reduction, player_id),
            )
            return current_def, actual_hp_damage, def_reduction

    def get_def_reset_context(self, player_id: int) -> DefResetContext | None:
        with self.cursor() as cursor:
            cursor.execute(
                """
                SELECT ps.turn_def, ps.total_def, ro.turndef
                FROM player_stats ps
                JOIN roleora ro ON ps.role_id = ro.id
                WHERE ps.player_id = %s
                """,
                (player_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return DefResetContext(*[int(value or 0) for value in row])

    def set_player_defense(self, player_id: int, turn_def: int, total_def: int) -> None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE player_stats SET turn_def = %s, total_def = %s WHERE player_id = %s",
                (turn_def, total_def, player_id),
            )

    def add_timer(self, player_id: int, timer_name: str, remaining_turns: int) -> None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                "INSERT INTO timers (player_id, timer_name, remaining_turns) VALUES (%s, %s, %s)",
                (player_id, timer_name, remaining_turns),
            )

    def get_timer(self, player_id: int, timer_name: str) -> int | None:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT remaining_turns FROM timers WHERE player_id = %s AND timer_name = %s",
                (player_id, timer_name),
            )
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else None

    def get_timer_like(self, player_id: int, timer_name_pattern: str) -> tuple[str, int] | None:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT timer_name, remaining_turns FROM timers WHERE player_id = %s AND timer_name LIKE %s",
                (player_id, timer_name_pattern),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return str(row[0]), int(row[1])

    def set_timer(self, player_id: int, timer_name: str, remaining_turns: int) -> None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO timers (player_id, timer_name, remaining_turns)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE remaining_turns = %s
                """,
                (player_id, timer_name, remaining_turns, remaining_turns),
            )

    def delete_timer(self, player_id: int, timer_name: str) -> None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                "DELETE FROM timers WHERE player_id = %s AND timer_name = %s",
                (player_id, timer_name),
            )

    def delete_timer_like(self, player_id: int, timer_name_pattern: str) -> None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                "DELETE FROM timers WHERE player_id = %s AND timer_name LIKE %s",
                (player_id, timer_name_pattern),
            )

    def decrement_non_stack_timers(self) -> None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE timers SET remaining_turns = remaining_turns - 1 WHERE remaining_turns > 0 AND timer_name NOT LIKE 'STACK_%%'"
            )
            cursor.execute(
                "DELETE FROM timers WHERE remaining_turns <= 0 AND timer_name NOT LIKE 'STACK_%%'"
            )

    def increment_timer(self, player_id: int, timer_name: str, delta: int) -> int | None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE timers
                SET remaining_turns = remaining_turns + %s
                WHERE player_id = %s AND timer_name = %s
                """,
                (delta, player_id, timer_name),
            )
            if cursor.rowcount == 0:
                return None
            cursor.execute(
                "SELECT remaining_turns FROM timers WHERE player_id = %s AND timer_name = %s",
                (player_id, timer_name),
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def list_player_timers(self, player_id: int) -> list[tuple[str, int]]:
        with self.cursor() as cursor:
            cursor.execute(
                "SELECT timer_name, remaining_turns FROM timers WHERE player_id = %s",
                (player_id,),
            )
            return [(str(name), int(turns)) for name, turns in cursor.fetchall()]

    def get_total_turn(self) -> int:
        with self.cursor() as cursor:
            cursor.execute("SELECT totalturn FROM euxrate WHERE id=1")
            row = cursor.fetchone()
            return int(row[0]) if row else 0

    def change_hp(self, player_id: int, delta: int, *, max_mode: bool = False) -> int | None:
        field = "max_hp" if max_mode else "now_hp"
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                f"UPDATE player_stats SET {field} = {field} + %s WHERE player_id = %s",
                (delta, player_id),
            )
            cursor.execute(f"SELECT {field} FROM player_stats WHERE player_id = %s", (player_id,))
            row = cursor.fetchone()
            return int(row[0]) if row else None

    def change_hp_with_cap(self, player_id: int, delta: int) -> int | None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE player_stats SET now_hp = LEAST(now_hp + %s, max_hp) WHERE player_id = %s",
                (delta, player_id),
            )
            cursor.execute("SELECT now_hp FROM player_stats WHERE player_id = %s", (player_id,))
            row = cursor.fetchone()
            return int(row[0]) if row else None

    def simple_stat_change(self, player_id: int, delta: int, column_name: str) -> int | None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                f"UPDATE player_stats SET {column_name} = {column_name} + %s WHERE player_id = %s",
                (delta, player_id),
            )
            cursor.execute(f"SELECT {column_name} FROM player_stats WHERE player_id = %s", (player_id,))
            row = cursor.fetchone()
            return int(row[0]) if row else None

    def get_role_name(self, player_id: int) -> str | None:
        with self.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.name
                FROM player_stats ps
                JOIN roles r ON ps.role_id = r.id
                WHERE ps.player_id = %s
                """,
                (player_id,),
            )
            row = cursor.fetchone()
            return str(row[0]) if row else None

    def consume_buff(self, player_id: int, buff_name: str) -> int:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                "SELECT remaining_turns FROM timers WHERE player_id = %s AND timer_name = %s",
                (player_id, buff_name),
            )
            row = cursor.fetchone()
            if not row or row[0] is None:
                return 0
            value = int(row[0])
            cursor.execute(
                "DELETE FROM timers WHERE player_id = %s AND timer_name = %s",
                (player_id, buff_name),
            )
            return value

    def get_player_ap_context(self, player_id: int) -> PlayerApContext | None:
        with self.cursor() as cursor:
            cursor.execute(
                """
                SELECT ps.now_ap, ps.max_ap, rt.ap_recover_min, rt.ap_recover_max
                FROM player_stats ps
                JOIN role_templates rt ON ps.role_id = rt.id
                WHERE ps.player_id = %s
                """,
                (player_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            values = [int(value) if value is not None else 0 for value in row]
            return PlayerApContext(*values)

    def update_player_ap(self, player_id: int, now_ap: int) -> None:
        with self.cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE player_stats SET now_ap = %s WHERE player_id = %s",
                (now_ap, player_id),
            )

    def increment_totalturn(self, player_id: int) -> None:
        with self.cursor(commit=True) as cursor:
            cursor.execute("UPDATE euxrate SET totalturn = totalturn + 1 WHERE id = %s", (player_id,))

    def get_player_attack(self, player_id: int) -> int:
        with self.cursor() as cursor:
            cursor.execute("SELECT atk FROM player_stats WHERE player_id = %s", (player_id,))
            row = cursor.fetchone()
            return int(row[0]) if row else 0
