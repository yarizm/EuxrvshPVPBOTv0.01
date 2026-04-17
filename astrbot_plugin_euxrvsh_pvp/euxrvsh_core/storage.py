from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


STORAGE_VERSION = 1

BUILTIN_OUTPUT_KING = {
    "role_id": "output_king",
    "name": "输出大王",
    "summary": "以专注叠层、侧闪反打和强化普攻为核心的近战斗士。",
    "stats": {
        "hp": 24,
        "atk": 6,
        "defense": 2,
        "max_ap": 2,
    },
    "skills": [
        {
            "key": "focus_shift",
            "name": "聚势",
            "description": "低专注时获得护甲与专注，高专注时强化下一次普攻。",
            "ap_cost": 1,
            "cooldown": 2,
            "target_type": "self",
            "branches": [
                {
                    "when": {"type": "focus_lt", "value": 3},
                    "actions": [
                        {"type": "set_effect", "effect_name": "fortify", "stacks": 3, "remaining_turns": 1},
                        {"type": "add_focus", "value": 2},
                        {"type": "append_detail", "text": "获得 3 点护甲，并叠加 2 层专注。"},
                    ],
                },
                {
                    "when": {"type": "focus_lt", "value": 5},
                    "actions": [
                        {
                            "type": "set_effect",
                            "effect_name": "next_attack_mult",
                            "stacks": 1,
                            "remaining_turns": 2,
                            "payload": {"multiplier": 2},
                        },
                        {"type": "append_detail", "text": "下一次普攻将造成 2 倍伤害。"},
                    ],
                },
                {
                    "when": "always",
                    "actions": [
                        {
                            "type": "set_effect",
                            "effect_name": "next_attack_mult",
                            "stacks": 1,
                            "remaining_turns": 2,
                            "payload": {"multiplier": 3},
                        },
                        {"type": "set_focus", "value": 0},
                        {"type": "append_detail", "text": "下一次普攻将造成 3 倍伤害，并清空专注。"},
                    ],
                },
            ],
        },
        {
            "key": "sidestep",
            "name": "侧闪",
            "description": "进入侧闪状态，下一次受到攻击时闪避。",
            "ap_cost": 1,
            "cooldown": 3,
            "target_type": "self",
            "branches": [
                {
                    "when": "always",
                    "actions": [
                        {"type": "set_effect", "effect_name": "sidestep", "stacks": 1, "remaining_turns": 1},
                        {"type": "append_detail", "text": "进入侧闪状态，下一次受到攻击时将完全闪避。"},
                    ],
                }
            ],
        },
        {
            "key": "chain_burst",
            "name": "链爆",
            "description": "对单体目标造成重击，并附加灼烧。",
            "ap_cost": 2,
            "cooldown": 4,
            "target_type": "enemy",
            "branches": [
                {
                    "when": "always",
                    "actions": [
                        {
                            "type": "attack",
                            "base_damage": 12,
                            "allow_multiplier": False,
                            "grant_focus": False,
                            "apply_burn": {"stacks": 2, "remaining_turns": 2, "damage": 2},
                        }
                    ],
                }
            ],
        },
    ],
}


@dataclass(frozen=True)
class StorageLayout:
    storage_root: Path
    runtime_db_path: Path
    storage_json_path: Path
    builtin_roles_dir: Path
    custom_roles_dir: Path
    sqlite_path_compat_used: bool = False


def ensure_storage_layout(storage_root: Path | str) -> StorageLayout:
    root = Path(storage_root).expanduser().resolve()
    runtime_db_path = root / "runtime.db"
    storage_json_path = root / "storage.json"
    builtin_roles_dir = root / "roles" / "builtin"
    custom_roles_dir = root / "roles" / "custom"

    root.mkdir(parents=True, exist_ok=True)
    builtin_roles_dir.mkdir(parents=True, exist_ok=True)
    custom_roles_dir.mkdir(parents=True, exist_ok=True)

    _write_storage_json(storage_json_path, runtime_db_path, builtin_roles_dir, custom_roles_dir)
    _ensure_builtin_role_files(builtin_roles_dir)

    return StorageLayout(
        storage_root=root,
        runtime_db_path=runtime_db_path,
        storage_json_path=storage_json_path,
        builtin_roles_dir=builtin_roles_dir,
        custom_roles_dir=custom_roles_dir,
    )


def _write_storage_json(
    storage_json_path: Path,
    runtime_db_path: Path,
    builtin_roles_dir: Path,
    custom_roles_dir: Path,
) -> None:
    content = {
        "storage_version": STORAGE_VERSION,
        "runtime_db": str(runtime_db_path),
        "roles_builtin_dir": str(builtin_roles_dir),
        "roles_custom_dir": str(custom_roles_dir),
    }
    storage_json_path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _ensure_builtin_role_files(builtin_roles_dir: Path) -> None:
    if any(builtin_roles_dir.glob("*.json")):
        return
    output_path = builtin_roles_dir / "output_king.json"
    output_path.write_text(json.dumps(BUILTIN_OUTPUT_KING, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
