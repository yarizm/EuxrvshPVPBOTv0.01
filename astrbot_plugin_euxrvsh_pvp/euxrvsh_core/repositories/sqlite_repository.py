from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from euxrvsh_core.domain.models import (
    BattleEffectState,
    BattleLogEntry,
    BattlePlayerState,
    BattleState,
    RoleDefinition,
    RoleSkillDefinition,
)
from euxrvsh_core.repositories.base import GameRepository


class SQLiteGameRepository(GameRepository):
    def __init__(self, sqlite_path: str):
        self.sqlite_path = Path(sqlite_path).expanduser().resolve()
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self, role_definitions: list[RoleDefinition]) -> None:
        with self.connection() as conn:
            self._create_schema(conn)
            self._upsert_roles(conn, role_definitions)

    def list_roles(self) -> list[RoleDefinition]:
        with self.connection() as conn:
            rows = conn.execute("SELECT * FROM role_definitions ORDER BY name ASC").fetchall()
        return [self._row_to_role(row) for row in rows]

    def get_role(self, role_id: str) -> RoleDefinition | None:
        with self.connection() as conn:
            row = conn.execute("SELECT * FROM role_definitions WHERE role_id = ?", (role_id,)).fetchone()
        return self._row_to_role(row) if row else None

    def load_battle(self, session_id: str) -> BattleState | None:
        with self.connection() as conn:
            battle_row = conn.execute("SELECT * FROM battles WHERE session_id = ?", (session_id,)).fetchone()
            if battle_row is None:
                return None

            player_rows = conn.execute(
                "SELECT * FROM battle_players WHERE session_id = ? ORDER BY player_slot ASC",
                (session_id,),
            ).fetchall()
            effect_rows = conn.execute(
                "SELECT * FROM battle_effects WHERE session_id = ? ORDER BY player_slot ASC, effect_name ASC",
                (session_id,),
            ).fetchall()
            cooldown_rows = conn.execute(
                "SELECT * FROM battle_cooldowns WHERE session_id = ? ORDER BY player_slot ASC, skill_key ASC",
                (session_id,),
            ).fetchall()
            log_rows = conn.execute(
                "SELECT * FROM battle_log WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()

        players_by_slot: dict[int, BattlePlayerState] = {}
        for row in player_rows:
            players_by_slot[int(row["player_slot"])] = BattlePlayerState(
                player_slot=int(row["player_slot"]),
                user_id=row["user_id"],
                role_id=row["role_id"],
                role_name=row["role_name"],
                hp=int(row["hp"]),
                max_hp=int(row["max_hp"]),
                atk=int(row["atk"]),
                defense=int(row["defense"]),
                ap=int(row["ap"]),
                max_ap=int(row["max_ap"]),
                alive=bool(row["alive"]),
                effects=[],
                cooldowns={},
            )

        for row in effect_rows:
            player = players_by_slot[int(row["player_slot"])]
            player.effects.append(
                BattleEffectState(
                    effect_name=str(row["effect_name"]),
                    stacks=int(row["stacks"]),
                    remaining_turns=int(row["remaining_turns"]),
                    payload=json.loads(row["payload_json"] or "{}"),
                )
            )

        for row in cooldown_rows:
            player = players_by_slot[int(row["player_slot"])]
            player.cooldowns[str(row["skill_key"])] = int(row["remaining_turns"])

        logs = [
            BattleLogEntry(
                turn_index=int(row["turn_index"]),
                actor_slot=int(row["actor_slot"]) if row["actor_slot"] is not None else None,
                action_type=str(row["action_type"]),
                summary=str(row["summary"]),
                detail_json=json.loads(row["detail_json"] or "{}"),
                created_at=str(row["created_at"]),
            )
            for row in log_rows
        ]

        return BattleState(
            session_id=str(battle_row["session_id"]),
            status=str(battle_row["status"]),
            player_count=int(battle_row["player_count"]),
            turn_index=int(battle_row["turn_index"]),
            round_index=int(battle_row["round_index"]),
            players=list(players_by_slot.values()),
            logs=logs,
            created_at=str(battle_row["created_at"]),
            updated_at=str(battle_row["updated_at"]),
        )

    def save_battle(self, battle_state: BattleState) -> None:
        now = self._now()
        if not battle_state.created_at:
            battle_state.created_at = now
        battle_state.updated_at = now

        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO battles (session_id, status, player_count, turn_index, round_index, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    status = excluded.status,
                    player_count = excluded.player_count,
                    turn_index = excluded.turn_index,
                    round_index = excluded.round_index,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at
                """,
                (
                    battle_state.session_id,
                    battle_state.status,
                    battle_state.player_count,
                    battle_state.turn_index,
                    battle_state.round_index,
                    battle_state.created_at,
                    battle_state.updated_at,
                ),
            )

            conn.execute("DELETE FROM battle_players WHERE session_id = ?", (battle_state.session_id,))
            conn.execute("DELETE FROM battle_effects WHERE session_id = ?", (battle_state.session_id,))
            conn.execute("DELETE FROM battle_cooldowns WHERE session_id = ?", (battle_state.session_id,))
            conn.execute("DELETE FROM battle_log WHERE session_id = ?", (battle_state.session_id,))

            for player in battle_state.players:
                conn.execute(
                    """
                    INSERT INTO battle_players (
                        session_id, player_slot, user_id, role_id, role_name, hp, max_hp, atk, defense, ap, max_ap, alive
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        battle_state.session_id,
                        player.player_slot,
                        player.user_id,
                        player.role_id,
                        player.role_name,
                        player.hp,
                        player.max_hp,
                        player.atk,
                        player.defense,
                        player.ap,
                        player.max_ap,
                        int(player.alive),
                    ),
                )
                for effect in player.effects:
                    conn.execute(
                        """
                        INSERT INTO battle_effects (
                            session_id, player_slot, effect_name, stacks, remaining_turns, payload_json
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            battle_state.session_id,
                            player.player_slot,
                            effect.effect_name,
                            effect.stacks,
                            effect.remaining_turns,
                            json.dumps(effect.payload, ensure_ascii=False),
                        ),
                    )
                for skill_key, remaining_turns in player.cooldowns.items():
                    conn.execute(
                        """
                        INSERT INTO battle_cooldowns (session_id, player_slot, skill_key, remaining_turns)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            battle_state.session_id,
                            player.player_slot,
                            skill_key,
                            remaining_turns,
                        ),
                    )

            for log in battle_state.logs:
                conn.execute(
                    """
                    INSERT INTO battle_log (session_id, turn_index, actor_slot, action_type, summary, detail_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        battle_state.session_id,
                        log.turn_index,
                        log.actor_slot,
                        log.action_type,
                        log.summary,
                        json.dumps(log.detail_json, ensure_ascii=False),
                        log.created_at or now,
                    ),
                )

    def delete_battle(self, session_id: str) -> bool:
        with self.connection() as conn:
            deleted = conn.execute("DELETE FROM battles WHERE session_id = ?", (session_id,)).rowcount
            conn.execute("DELETE FROM battle_players WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM battle_effects WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM battle_cooldowns WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM battle_log WHERE session_id = ?", (session_id,))
        return deleted > 0

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS battles (
                session_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                player_count INTEGER NOT NULL,
                turn_index INTEGER NOT NULL,
                round_index INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS battle_players (
                session_id TEXT NOT NULL,
                player_slot INTEGER NOT NULL,
                user_id TEXT,
                role_id TEXT,
                role_name TEXT,
                hp INTEGER NOT NULL,
                max_hp INTEGER NOT NULL,
                atk INTEGER NOT NULL,
                defense INTEGER NOT NULL,
                ap INTEGER NOT NULL,
                max_ap INTEGER NOT NULL,
                alive INTEGER NOT NULL,
                PRIMARY KEY (session_id, player_slot)
            );

            CREATE TABLE IF NOT EXISTS battle_effects (
                session_id TEXT NOT NULL,
                player_slot INTEGER NOT NULL,
                effect_name TEXT NOT NULL,
                stacks INTEGER NOT NULL,
                remaining_turns INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY (session_id, player_slot, effect_name)
            );

            CREATE TABLE IF NOT EXISTS battle_cooldowns (
                session_id TEXT NOT NULL,
                player_slot INTEGER NOT NULL,
                skill_key TEXT NOT NULL,
                remaining_turns INTEGER NOT NULL,
                PRIMARY KEY (session_id, player_slot, skill_key)
            );

            CREATE TABLE IF NOT EXISTS battle_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_index INTEGER NOT NULL,
                actor_slot INTEGER,
                action_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS role_definitions (
                role_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                summary TEXT NOT NULL,
                base_hp INTEGER NOT NULL,
                base_atk INTEGER NOT NULL,
                base_defense INTEGER NOT NULL,
                max_ap INTEGER NOT NULL,
                skills_json TEXT NOT NULL
            );
            """
        )

    def _upsert_roles(self, conn: sqlite3.Connection, role_definitions: list[RoleDefinition]) -> None:
        for role in role_definitions:
            conn.execute(
                """
                INSERT INTO role_definitions (
                    role_id, name, summary, base_hp, base_atk, base_defense, max_ap, skills_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(role_id) DO UPDATE SET
                    name = excluded.name,
                    summary = excluded.summary,
                    base_hp = excluded.base_hp,
                    base_atk = excluded.base_atk,
                    base_defense = excluded.base_defense,
                    max_ap = excluded.max_ap,
                    skills_json = excluded.skills_json
                """,
                (
                    role.role_id,
                    role.name,
                    role.summary,
                    role.base_hp,
                    role.base_atk,
                    role.base_defense,
                    role.max_ap,
                    json.dumps([skill.__dict__ for skill in role.skills], ensure_ascii=False),
                ),
            )

    def _row_to_role(self, row: sqlite3.Row) -> RoleDefinition:
        skills_raw = json.loads(row["skills_json"])
        skills = tuple(
            RoleSkillDefinition(
                key=str(skill["key"]),
                name=str(skill["name"]),
                description=str(skill["description"]),
                ap_cost=int(skill["ap_cost"]),
                cooldown=int(skill["cooldown"]),
                target_type=str(skill["target_type"]),
            )
            for skill in skills_raw
        )
        return RoleDefinition(
            role_id=str(row["role_id"]),
            name=str(row["name"]),
            summary=str(row["summary"]),
            base_hp=int(row["base_hp"]),
            base_atk=int(row["base_atk"]),
            base_defense=int(row["base_defense"]),
            max_ap=int(row["max_ap"]),
            skills=skills,
        )

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
