from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from euxrvsh_core.domain.models import (
    RoleDefinition,
    RoleFileDefinition,
    RoleSkillDefinition,
    RoleStatsDefinition,
    SkillActionDefinition,
    SkillBranchDefinition,
    SkillConditionDefinition,
)

SUPPORTED_WHEN_TYPES = {"always", "focus_lt", "focus_gte"}
SUPPORTED_ACTION_TYPES = {
    "set_focus",
    "add_focus",
    "set_effect",
    "clear_effect",
    "attack",
    "append_detail",
}


@dataclass(frozen=True)
class RoleCatalogLoadResult:
    role_files: tuple[RoleFileDefinition, ...]
    warnings: tuple[str, ...] = ()


class RoleCatalogLoader:
    def __init__(self, builtin_dir: Path | str, custom_dir: Path | str):
        self.builtin_dir = Path(builtin_dir)
        self.custom_dir = Path(custom_dir)

    def load(self) -> RoleCatalogLoadResult:
        role_files: list[RoleFileDefinition] = []
        warnings: list[str] = []
        builtin_ids: set[str] = set()

        for path in sorted(self.builtin_dir.glob("*.json")):
            loaded, warning = self._load_one(path, source_kind="builtin")
            if warning:
                warnings.append(warning)
            if loaded is None:
                continue
            role_files.append(loaded)
            builtin_ids.add(loaded.role.role_id)

        for path in sorted(self.custom_dir.glob("*.json")):
            loaded, warning = self._load_one(path, source_kind="custom")
            if warning:
                warnings.append(warning)
            if loaded is None:
                continue
            if loaded.role.role_id in builtin_ids:
                warnings.append(
                    f"自定义角色 `{loaded.role.role_id}` 与内置角色重复，已跳过文件 `{path.name}`。"
                )
                continue
            role_files.append(loaded)

        return RoleCatalogLoadResult(role_files=tuple(role_files), warnings=tuple(warnings))

    def _load_one(self, path: Path, *, source_kind: str) -> tuple[RoleFileDefinition | None, str | None]:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return None, f"无法加载角色文件 `{path}`：{exc}"

        try:
            role = self._parse_role(raw, source_kind=source_kind, source_path=str(path))
        except (KeyError, TypeError, ValueError) as exc:
            return None, f"角色文件 `{path}` 格式不合法：{exc}"

        return RoleFileDefinition(role=role, source_kind=source_kind, source_path=str(path)), None

    def _parse_role(self, raw: dict, *, source_kind: str, source_path: str) -> RoleDefinition:
        stats_raw = raw["stats"]
        skills = tuple(self._parse_skill(skill) for skill in raw.get("skills", []))
        return RoleDefinition(
            role_id=str(raw["role_id"]).strip(),
            name=str(raw["name"]).strip(),
            summary=str(raw["summary"]).strip(),
            stats=RoleStatsDefinition(
                hp=int(stats_raw["hp"]),
                atk=int(stats_raw["atk"]),
                defense=int(stats_raw["defense"]),
                max_ap=int(stats_raw["max_ap"]),
            ),
            skills=skills,
            source_kind=source_kind,
            source_path=source_path,
        )

    def _parse_skill(self, raw: dict) -> RoleSkillDefinition:
        branches = tuple(self._parse_branch(branch) for branch in raw.get("branches", []))
        return RoleSkillDefinition(
            key=str(raw["key"]).strip(),
            name=str(raw["name"]).strip(),
            description=str(raw["description"]).strip(),
            ap_cost=int(raw["ap_cost"]),
            cooldown=int(raw["cooldown"]),
            target_type=str(raw["target_type"]).strip(),
            branches=branches,
        )

    def _parse_branch(self, raw: dict) -> SkillBranchDefinition:
        when_raw = raw["when"]
        if isinstance(when_raw, str):
            when = SkillConditionDefinition(kind=when_raw)
        else:
            when = SkillConditionDefinition(kind=str(when_raw["type"]), value=self._maybe_int(when_raw.get("value")))
        if when.kind not in SUPPORTED_WHEN_TYPES:
            raise ValueError(f"不支持的分支条件类型 `{when.kind}`")

        actions: list[SkillActionDefinition] = []
        for action_raw in raw.get("actions", []):
            kind = str(action_raw["type"])
            if kind not in SUPPORTED_ACTION_TYPES:
                raise ValueError(f"不支持的动作类型 `{kind}`")
            params = {key: value for key, value in action_raw.items() if key != "type"}
            actions.append(SkillActionDefinition(kind=kind, params=params))
        return SkillBranchDefinition(when=when, actions=tuple(actions))

    @staticmethod
    def _maybe_int(value: object) -> int | None:
        if value is None:
            return None
        return int(value)


class CharacterRegistry:
    def __init__(self, role_files: list[RoleFileDefinition] | tuple[RoleFileDefinition, ...]):
        self._role_files = list(role_files)
        self._by_key = {role_file.role.role_id.lower(): role_file.role for role_file in self._role_files}
        self._by_name = {role_file.role.name.lower(): role_file.role for role_file in self._role_files}

    def all(self) -> list[RoleDefinition]:
        return [role_file.role for role_file in self._role_files]

    def role_files(self) -> list[RoleFileDefinition]:
        return list(self._role_files)

    def get(self, role_key_or_name: str | None) -> RoleDefinition | None:
        if not role_key_or_name:
            return None
        normalized = str(role_key_or_name).strip().lower()
        return self._by_key.get(normalized) or self._by_name.get(normalized)
