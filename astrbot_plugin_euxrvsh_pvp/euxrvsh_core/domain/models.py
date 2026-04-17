from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SkillConditionDefinition:
    kind: str
    value: int | None = None


@dataclass(frozen=True)
class SkillActionDefinition:
    kind: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SkillBranchDefinition:
    when: SkillConditionDefinition
    actions: tuple[SkillActionDefinition, ...]


@dataclass(frozen=True)
class RoleSkillDefinition:
    key: str
    name: str
    description: str
    ap_cost: int
    cooldown: int
    target_type: str
    branches: tuple[SkillBranchDefinition, ...] = ()


@dataclass(frozen=True)
class RoleStatsDefinition:
    hp: int
    atk: int
    defense: int
    max_ap: int


@dataclass(frozen=True)
class RoleDefinition:
    role_id: str
    name: str
    summary: str
    stats: RoleStatsDefinition
    skills: tuple[RoleSkillDefinition, ...]
    source_kind: str = "builtin"
    source_path: str = ""

    @property
    def base_hp(self) -> int:
        return self.stats.hp

    @property
    def base_atk(self) -> int:
        return self.stats.atk

    @property
    def base_defense(self) -> int:
        return self.stats.defense

    @property
    def max_ap(self) -> int:
        return self.stats.max_ap


@dataclass(frozen=True)
class RoleFileDefinition:
    role: RoleDefinition
    source_kind: str
    source_path: str


@dataclass
class BattleEffectState:
    effect_name: str
    stacks: int = 0
    remaining_turns: int = -1
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class BattlePlayerState:
    player_slot: int
    user_id: str | None = None
    role_id: str | None = None
    role_name: str | None = None
    hp: int = 0
    max_hp: int = 0
    atk: int = 0
    defense: int = 0
    ap: int = 0
    max_ap: int = 0
    alive: bool = False
    effects: list[BattleEffectState] = field(default_factory=list)
    cooldowns: dict[str, int] = field(default_factory=dict)

    def get_effect(self, effect_name: str) -> BattleEffectState | None:
        return next((effect for effect in self.effects if effect.effect_name == effect_name), None)

    def set_effect(
        self,
        effect_name: str,
        *,
        stacks: int = 0,
        remaining_turns: int = -1,
        payload: dict[str, Any] | None = None,
    ) -> BattleEffectState:
        current = self.get_effect(effect_name)
        if current is None:
            current = BattleEffectState(effect_name=effect_name)
            self.effects.append(current)
        current.stacks = stacks
        current.remaining_turns = remaining_turns
        current.payload = dict(payload or {})
        return current

    def remove_effect(self, effect_name: str) -> None:
        self.effects = [effect for effect in self.effects if effect.effect_name != effect_name]


@dataclass
class BattleLogEntry:
    turn_index: int
    actor_slot: int | None
    action_type: str
    summary: str
    detail_json: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class BattleState:
    session_id: str
    status: str
    player_count: int
    turn_index: int
    round_index: int
    players: list[BattlePlayerState]
    logs: list[BattleLogEntry] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def get_player_by_slot(self, player_slot: int) -> BattlePlayerState | None:
        return next((player for player in self.players if player.player_slot == player_slot), None)

    def get_player_by_user(self, user_id: str) -> BattlePlayerState | None:
        return next((player for player in self.players if player.user_id == user_id), None)

    def alive_players(self) -> list[BattlePlayerState]:
        return [player for player in self.players if player.alive]


@dataclass
class ActionResult:
    ok: bool
    summary: str
    details: list[str] = field(default_factory=list)
    battle_state: BattleState | None = None
