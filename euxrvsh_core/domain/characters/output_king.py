from __future__ import annotations

from euxrvsh_core.domain.models import RoleDefinition, RoleSkillDefinition


def build_output_king_role() -> RoleDefinition:
    return RoleDefinition(
        role_id="output_king",
        name="输出大王",
        summary="以专注叠层、闪避反打和强化普攻为核心的近战斗士。",
        base_hp=24,
        base_atk=6,
        base_defense=2,
        max_ap=2,
        skills=(
            RoleSkillDefinition(
                key="focus_shift",
                name="聚势",
                description="低专注时获得护甲与专注，高专注时强化下一次普攻。",
                ap_cost=1,
                cooldown=2,
                target_type="self",
            ),
            RoleSkillDefinition(
                key="sidestep",
                name="侧闪",
                description="进入侧闪状态，下一次受到攻击时闪避并积累专注。",
                ap_cost=1,
                cooldown=3,
                target_type="self",
            ),
            RoleSkillDefinition(
                key="chain_burst",
                name="链爆",
                description="对单体目标造成重击，并附加灼烧。",
                ap_cost=2,
                cooldown=4,
                target_type="enemy",
            ),
        ),
    )
