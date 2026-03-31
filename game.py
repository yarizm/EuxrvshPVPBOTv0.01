import mysql.connector
from contextlib import contextmanager
import math
import random

# 1. 基础设施：配置与连接池
# ==========================================

from db import get_cursor, connection_pool
from game_utils import hp_change, atk_change, def_change, distance_change, cd_change, \
    get_role_name, consume_buff, simple_stat_change

# 导入角色逻辑
from character_logic import output_king

# ==========================================
# 2. 核心战斗数逻辑 (入口)
# ==========================================

def attack(attacker_id, target_id, damage_value):
    """
    攻击逻辑：优先扣除护甲，剩余扣除HP (事务保护)
    """
    damage_value = int(damage_value)
    attacker_id = int(attacker_id)
    target_id = int(target_id)
    
    try:
        # --- 触发被动（攻击前） ---
        # 1. 攻击者被动
        passive_msg_atk = trigger_passive_on_attack(attacker_id, target_id, damage_value)
        
        # 2. 防御者被动
        passive_msg_def, damage_modified = trigger_passive_on_defend(target_id, attacker_id, damage_value)
        
        if damage_modified is not None:
            damage_value = damage_modified
            # 如果伤害被完全规避
            if damage_value <= 0:
                return f"{passive_msg_atk}\n{passive_msg_def}\n攻击被完全规避！"

        with get_cursor(commit=True) as cursor:
            # 1. 锁定并读取当前护甲
            cursor.execute("SELECT turn_def FROM player_stats WHERE player_id = %s FOR UPDATE", (target_id,))
            row = cursor.fetchone()
            if not row:
                return f"玩家{target_id}不存在"

            current_def = row[0]

            # 2. 计算伤害分配
            if damage_value <= current_def:
                actual_hp_damage = 1  # 破防失败至少扣1血机制
                def_reduction = damage_value - 1
            else:
                actual_hp_damage = damage_value - current_def
                def_reduction = current_def  # 护甲全破

            # 3. 执行双字段更新
            sql_update = """
                         UPDATE player_stats
                         SET now_hp   = now_hp - %s,
                             turn_def = turn_def - %s
                         WHERE player_id = %s \
                         """
            cursor.execute(sql_update, (actual_hp_damage, def_reduction, target_id))

            base_msg = f"玩家{target_id}受到了来自玩家{attacker_id}的伤害：{damage_value} (实扣HP:{actual_hp_damage}, 扣防:{def_reduction})"
            return f"{passive_msg_atk}\n{passive_msg_def}\n{base_msg}".strip()
    except Exception as e:
        return f"攻击处理出错: {str(e)}"

# ==========================================
# 3. 游戏流程控制
# ==========================================

def startgame(play_num):
    try:
        with get_cursor(commit=True) as cursor:
            # 初始化全局计数
            cursor.execute("UPDATE playnum SET play_num = %s, nums = 1", (int(play_num),))

            # 清空动态表
            cursor.execute("TRUNCATE TABLE skill_cooldowns")
            cursor.execute("TRUNCATE TABLE timers")
            cursor.execute("DELETE FROM player_stats")  # 确保清空旧战绩

            # 重置玩家状态
            cursor.execute("UPDATE euxrate SET iswin=0, x_value=0, isgive=0, winrate=0.5")
            cursor.execute("UPDATE roles SET player_id = NULL")  # 释放所有角色

            return int(play_num)
    except Exception as e:
        return f"游戏启动失败: {str(e)}"

def pickrole(role_id):
    """
    玩家选角逻辑：绑定角色并初始化数值到 player_stats
    """
    try:
        with get_cursor(commit=True) as cursor:
            # 1. 确定当前轮到谁选 (锁行防止并发)
            cursor.execute("SELECT nums FROM playnum FOR UPDATE")
            row = cursor.fetchone()
            current_player_id = row[0]

            # 2. 检查角色占用情况
            cursor.execute("SELECT player_id, name FROM roles WHERE id = %s", (role_id,))
            role_row = cursor.fetchone()
            if not role_row: return "角色不存在"
            if role_row[0] is not None: return f"角色：{role_row[1]} 已被其他玩家使用！"

            # 3. 绑定角色
            cursor.execute("UPDATE roles SET player_id = %s WHERE id = %s", (current_player_id, role_id))

            # 4. 从 roleora 读取防御值
            cursor.execute("SELECT turndef, totaldef FROM roleora WHERE id = %s", (role_id,))
            def_row = cursor.fetchone()
            turn_def_init = def_row[0] if def_row and def_row[0] else 0
            total_def_init = def_row[1] if def_row and def_row[1] else 0

            # 5. 初始化属性 (从模板表 -> 状态表，防御从 roleora 读取)
            insert_sql = """
                         INSERT INTO player_stats (player_id, role_id, max_hp, now_hp, atk, distance, turn_def, total_def, now_ap, max_ap)
                         SELECT %s, 
                                id, 
                                base_max_hp, 
                                base_max_hp, 
                                base_atk, 
                                base_dist, 
                                %s, 
                                %s,
                                0,
                                max_ap
                         FROM role_templates 
                         WHERE id = %s
                         """
            cursor.execute(insert_sql, (current_player_id, turn_def_init, total_def_init, role_id))

            # 6. 轮次推进
            cursor.execute("UPDATE playnum SET nums = nums + 1")

            return f"玩家{current_player_id}, 您已成功选择角色：{role_row[1]} (护甲:{turn_def_init}, 总护甲:{total_def_init})"
    except Exception as e:
        return f"选角失败: {str(e)}"

def endgame():
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE euxrate SET winrate=0.5, isdiff=0, iswin=NULL, x_value=0, isgive=0, totalturn=0, giveturn=0")
            cursor.execute("UPDATE roles SET player_id = NULL")
            cursor.execute("DELETE FROM player_stats")
            cursor.execute("DELETE FROM skill_cooldowns")
            cursor.execute("DELETE FROM timers")
            return True
    except Exception as e:
        print(f"重置失败: {e}")
        return False

# ==========================================
# 4. 技能与状态管理
# ==========================================

def skill_use(player_id, skill_idx):
    skill_idx = int(skill_idx)
    try:
        with get_cursor(commit=True) as cursor:
            # 1. CD检查
            cursor.execute("SELECT current_cd FROM skill_cooldowns WHERE player_id=%s AND skill_index=%s",
                           (player_id, skill_idx))
            row = cursor.fetchone()
            if row and row[0] > 0:
                return f"玩家{player_id}的技能{skill_idx}还在CD中，剩余{row[0]}回合"

            # 2. 读取配置CD (需关联 player_stats 找到 role_id, 再查 roleora)
            cursor.execute("SELECT role_id FROM player_stats WHERE player_id = %s", (player_id,))
            stats_row = cursor.fetchone()
            if not stats_row: return "玩家未初始化"
            role_id = stats_row[0]

            # 动态列查询 artX (兼容旧表结构)
            cursor.execute(f"SELECT art{skill_idx} FROM roleora WHERE id = %s", (role_id,))
            cd_row = cursor.fetchone()
            max_cd = cd_row[0] if cd_row else 0

            # 3. 写入CD
            sql = """
                  INSERT INTO skill_cooldowns (player_id, skill_index, current_cd)
                  VALUES (%s, %s, %s) ON DUPLICATE KEY \
                  UPDATE current_cd = %s \
                  """
            cursor.execute(sql, (player_id, skill_idx, max_cd, max_cd))

            return f"玩家{player_id}技能{skill_idx}已使用，CD重置为{max_cd}\n" + execute_skill_effect(player_id, skill_idx)
    except Exception as e:
        return f"技能使用失败: {str(e)}"


# ==========================================
# 5. 回合结算与辅助功能
# ==========================================

def turnend(sign):
    res = []
    try:
        with get_cursor(commit=True) as cursor:
            # 1. 批量减少CD
            if sign == 1:
                cursor.execute("UPDATE skill_cooldowns SET current_cd = current_cd - 1 WHERE current_cd > 0")

            # 2. 生成战报
            cursor.execute("SELECT play_num FROM playnum")
            play_num_row = cursor.fetchone()
            if not play_num_row: return []
            play_num = play_num_row[0]

            for i in range(play_num):
                pid = i + 1
                # 查属性
                cursor.execute(
                    "SELECT max_hp, now_hp, turn_def, total_def, atk, distance, now_ap, max_ap FROM player_stats WHERE player_id = %s",
                    (pid,))
                stats = cursor.fetchone()
                if not stats: continue

                # 查CD
                cursor.execute(
                    "SELECT skill_index, current_cd FROM skill_cooldowns WHERE player_id = %s AND current_cd > 0",
                    (pid,))
                cd_rows = cursor.fetchall()
                cd_info = "".join([f"玩家{pid}的技能{s}当前的cd为：{c} \n" for s, c in cd_rows])

                base_info = (f"玩家{pid}最大hp为：{stats[0]}，当前hp为：{stats[1]}，"
                             f"当前护甲为：{stats[2]}，总护甲为：{stats[3]}，"
                             f"当前ATK为：{stats[4]}，当前攻击距离为：{stats[5]}，"
                             f"当前行动值：{stats[6]}/{stats[7]}。 \n\n")
                res.append(base_info + cd_info)
        return res
    except Exception as e:
        return [f"结算出错: {str(e)}"]


def resetdef():
    """
    【重要修复】护甲重置逻辑
    修正点：不再查询 'role' 表，改为查询 'player_stats' 并关联 'roleora'
    """
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("SELECT play_num FROM playnum")
            play_num_row = cursor.fetchone()
            if not play_num_row: return False
            play_num = play_num_row[0]

            for i in range(play_num):
                pid = i + 1
                # 关联 player_stats 和 roleora (通过 role_id)
                query = """
                        SELECT ps.player_id, ps.turn_def, ps.total_def, ro.turndef as base_def
                        FROM player_stats ps
                                 JOIN roleora ro ON ps.role_id = ro.id
                        WHERE ps.player_id = %s \
                        """
                cursor.execute(query, (pid,))
                row = cursor.fetchone()

                # 使用字典索引需要 row 是字典，这里改为使用索引
                if not row: continue
                # row: (player_id, turn_def, total_def, base_def)
                curr_def, total_pool, base_def = row[1], row[2], row[3]

                if curr_def < base_def:
                    diff = base_def - curr_def
                    if total_pool >= diff:
                        new_curr = base_def
                        new_total = total_pool - diff
                    else:
                        new_curr = curr_def + total_pool
                        new_total = 0

                    update_sql = "UPDATE player_stats SET turn_def = %s, total_def = %s WHERE player_id = %s"
                    cursor.execute(update_sql, (new_curr, new_total, pid))
            return True
    except Exception as e:
        print(f"护甲重置错误: {e}")
        return False


# 计时器相关函数
def timerem(player_id, word, turns):
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("INSERT INTO timers (player_id, timer_name, remaining_turns) VALUES (%s, %s, %s)",
                           (player_id, word, int(turns)))

            cursor.execute("SELECT totalturn FROM euxrate WHERE id=1")
            row = cursor.fetchone()
            total_turn = row[0] if row else 0
            return f"玩家{player_id}添加计时：{word}，持续{turns}回合，将在第{total_turn + int(turns)}回合结束"
    except Exception as e:
        return f"计时失败: {e}"


def remsubauto():
    try:
        with get_cursor(commit=True) as cursor:
            # 只减少非 STACK_ 开头的计时器
            cursor.execute("UPDATE timers SET remaining_turns = remaining_turns - 1 WHERE remaining_turns > 0 AND timer_name NOT LIKE 'STACK_%'")
            # 只清理非 STACK_ 开头的过期计时器
            cursor.execute("DELETE FROM timers WHERE remaining_turns <= 0 AND timer_name NOT LIKE 'STACK_%'")
            return True
    except Exception as e:
        print(f"计时更新失败: {e}")
        return False


def remsubhand(player_id, word, value):
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE timers SET remaining_turns = remaining_turns + %s WHERE player_id = %s AND timer_name = %s",
                (int(value), player_id, word))
            if cursor.rowcount > 0:
                cursor.execute("SELECT remaining_turns FROM timers WHERE player_id=%s AND timer_name=%s",
                               (player_id, word))
                return f"计时器 {word} 更新为 {cursor.fetchone()[0]}"
            return "未找到指定计时器"
    except Exception as e:
        return f"修改失败: {e}"


def timeinfo():
    res = []
    try:
        with get_cursor() as cursor:
            cursor.execute("SELECT play_num FROM playnum")
            play_num = cursor.fetchone()[0]
            for i in range(play_num):
                pid = i + 1
                cursor.execute("SELECT timer_name, remaining_turns FROM timers WHERE player_id = %s", (pid,))
                info = f"玩家{pid}的计时一览: \n" + "".join(
                    [f"计时: {n}, 剩余: {t}回合! \n" for n, t in cursor.fetchall()])
                res.append(info)
        return res
    except Exception as e:
        return [f"查询失败: {e}"]


# ==========================================
# 流血效果系统
# ==========================================

def bleeding(player_id, turns):
    """
    对指定玩家施加流血效果
    参数:
        player_id: 目标玩家ID
        turns: 持续回合数
    效果: 每次消耗行动力进行动作时，损失1点HP
    """
    try:
        with get_cursor(commit=True) as cursor:
            # 检查是否已有流血效果
            cursor.execute(
                "SELECT remaining_turns FROM timers WHERE player_id = %s AND timer_name = '流血'",
                (player_id,)
            )
            existing = cursor.fetchone()

            if existing:
                # 叠加/刷新流血效果（取较大值）
                new_turns = max(existing[0], int(turns))
                cursor.execute(
                    "UPDATE timers SET remaining_turns = %s WHERE player_id = %s AND timer_name = '流血'",
                    (new_turns, player_id)
                )
                return f"玩家{player_id}的流血效果已刷新，持续{new_turns}回合"
            else:
                # 新增流血效果
                cursor.execute(
                    "INSERT INTO timers (player_id, timer_name, remaining_turns) VALUES (%s, '流血', %s)",
                    (player_id, int(turns))
                )
                return f"玩家{player_id}被施加了流血效果，持续{turns}回合"
    except Exception as e:
        return f"施加流血效果失败: {e}"


def trigger_bleeding(player_id):
    """
    触发流血伤害（在玩家消耗行动力进行动作时调用）
    如果玩家有流血效果，则扣除1点HP并减少1回合持续时间
    返回: 伤害信息或None（如果没有流血效果）
    """
    try:
        with get_cursor(commit=True) as cursor:
            # 检查是否有流血效果
            cursor.execute(
                "SELECT remaining_turns FROM timers WHERE player_id = %s AND timer_name = '流血'",
                (player_id,)
            )
            row = cursor.fetchone()

            if not row or row[0] <= 0:
                return None  # 没有流血效果

            # 扣除1点HP
            cursor.execute(
                "UPDATE player_stats SET now_hp = now_hp - 1 WHERE player_id = %s",
                (player_id,)
            )

            # 减少流血持续回合
            remaining = row[0] - 1
            if remaining <= 0:
                cursor.execute(
                    "DELETE FROM timers WHERE player_id = %s AND timer_name = '流血'",
                    (player_id,)
                )
                return f"玩家{player_id}因流血损失1点HP，流血效果已结束"
            else:
                cursor.execute(
                    "UPDATE timers SET remaining_turns = %s WHERE player_id = %s AND timer_name = '流血'",
                    (remaining, player_id)
                )
                return f"玩家{player_id}因流血损失1点HP，剩余{remaining}回合"
    except Exception as e:
        return f"流血触发失败: {e}"


def check_bleeding(player_id):
    """
    检查玩家是否有流血效果
    返回: 剩余回合数，如果没有则返回0
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT remaining_turns FROM timers WHERE player_id = %s AND timer_name = '流血'",
                (player_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        print(f"检查流血状态失败: {e}")
        return 0


# ==========================================
# 灼烧效果系统
# ==========================================

def burning(player_id, turns):
    """
    对指定玩家施加灼烧效果
    参数:
        player_id: 目标玩家ID
        turns: 持续回合数
    效果: 每回合开始时（执行/out指令时），损失1点HP
    """
    try:
        with get_cursor(commit=True) as cursor:
            # 检查是否已有灼烧效果
            cursor.execute(
                "SELECT remaining_turns FROM timers WHERE player_id = %s AND timer_name = '灼烧'",
                (player_id,)
            )
            existing = cursor.fetchone()

            if existing:
                # 叠加/刷新灼烧效果（取较大值）
                new_turns = max(existing[0], int(turns))
                cursor.execute(
                    "UPDATE timers SET remaining_turns = %s WHERE player_id = %s AND timer_name = '灼烧'",
                    (new_turns, player_id)
                )
                return f"玩家{player_id}的灼烧效果已刷新，持续{new_turns}回合"
            else:
                # 新增灼烧效果
                cursor.execute(
                    "INSERT INTO timers (player_id, timer_name, remaining_turns) VALUES (%s, '灼烧', %s)",
                    (player_id, int(turns))
                )
                return f"玩家{player_id}被施加了灼烧效果，持续{turns}回合"
    except Exception as e:
        return f"施加灼烧效果失败: {e}"


def trigger_burning(player_id):
    """
    触发灼烧伤害（在回合开始时调用）
    如果玩家有灼烧效果，则扣除1点HP并减少1回合持续时间
    返回: 伤害信息或None（如果没有灼烧效果）
    """
    try:
        with get_cursor(commit=True) as cursor:
            # 检查是否有灼烧效果
            cursor.execute(
                "SELECT remaining_turns FROM timers WHERE player_id = %s AND timer_name = '灼烧'",
                (player_id,)
            )
            row = cursor.fetchone()

            if not row or row[0] <= 0:
                return None  # 没有灼烧效果

            # 扣除1点HP
            cursor.execute(
                "UPDATE player_stats SET now_hp = now_hp - 1 WHERE player_id = %s",
                (player_id,)
            )

            # 减少灼烧持续回合
            remaining = row[0] - 1
            if remaining <= 0:
                cursor.execute(
                    "DELETE FROM timers WHERE player_id = %s AND timer_name = '灼烧'",
                    (player_id,)
                )
                return f"玩家{player_id}因灼烧损失1点HP，灼烧效果已结束"
            else:
                cursor.execute(
                    "UPDATE timers SET remaining_turns = %s WHERE player_id = %s AND timer_name = '灼烧'",
                    (remaining, player_id)
                )
                return f"玩家{player_id}因灼烧损失1点HP，剩余{remaining}回合"
    except Exception as e:
        return f"灼烧触发失败: {e}"


def trigger_all_burning():
    """
    触发所有玩家的灼烧效果（在回合开始时调用）
    返回: 所有灼烧伤害信息的列表
    """
    results = []
    try:
        with get_cursor() as cursor:
            cursor.execute("SELECT play_num FROM playnum")
            play_num_row = cursor.fetchone()
            if not play_num_row:
                return results
            play_num = play_num_row[0]

        for i in range(play_num):
            pid = i + 1
            msg = trigger_burning(pid)
            if msg:
                results.append(msg)
        return results
    except Exception as e:
        return [f"灼烧触发出错: {e}"]


def check_burning(player_id):
    """
    检查玩家是否有灼烧效果
    返回: 剩余回合数，如果没有则返回0
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT remaining_turns FROM timers WHERE player_id = %s AND timer_name = '灼烧'",
                (player_id,)
            )
            row = cursor.fetchone()
            return row[0] if row else 0
    except Exception as e:
        print(f"检查灼烧状态失败: {e}")
        return 0


# ==========================================
# 恢复效果系统
# ==========================================

def recovery(player_id, heal_amount, turns):
    """
    对指定玩家施加恢复效果
    参数:
        player_id: 目标玩家ID
        heal_amount: 每次恢复的HP数量（恢复等级）
        turns: 持续回合数
    效果: 立即恢复HP，之后每回合开始时恢复等同于恢复等级的HP
    """
    try:
        with get_cursor(commit=True) as cursor:
            heal_amount = int(heal_amount)
            turns = int(turns)
            
            # 立即恢复HP
            cursor.execute(
                "UPDATE player_stats SET now_hp = LEAST(now_hp + %s, max_hp) WHERE player_id = %s",
                (heal_amount, player_id)
            )
            
            # 检查是否已有恢复效果
            cursor.execute(
                "SELECT remaining_turns FROM timers WHERE player_id = %s AND timer_name LIKE '恢复|%'",
                (player_id,)
            )
            existing = cursor.fetchone()

            # 使用 timer_name 格式: "恢复|恢复等级" 来存储恢复等级
            timer_name = f"恢复|{heal_amount}"
            
            if existing:
                # 刷新恢复效果
                cursor.execute(
                    "DELETE FROM timers WHERE player_id = %s AND timer_name LIKE '恢复|%'",
                    (player_id,)
                )
            
            # 新增恢复效果
            cursor.execute(
                "INSERT INTO timers (player_id, timer_name, remaining_turns) VALUES (%s, %s, %s)",
                (player_id, timer_name, turns)
            )
            
            # 查询当前HP
            cursor.execute("SELECT now_hp FROM player_stats WHERE player_id = %s", (player_id,))
            current_hp = cursor.fetchone()
            hp_info = f"，当前HP：{current_hp[0]}" if current_hp else ""
            
            return f"玩家{player_id}被施加了恢复效果（等级{heal_amount}），立即恢复{heal_amount}点HP{hp_info}，持续{turns}回合"
    except Exception as e:
        return f"施加恢复效果失败: {e}"


def trigger_recovery(player_id):
    """
    触发恢复效果（在回合开始时调用）
    如果玩家有恢复效果，则恢复HP并减少1回合持续时间
    返回: 恢复信息或None（如果没有恢复效果）
    """
    try:
        with get_cursor(commit=True) as cursor:
            # 检查是否有恢复效果
            cursor.execute(
                "SELECT timer_name, remaining_turns FROM timers WHERE player_id = %s AND timer_name LIKE '恢复|%'",
                (player_id,)
            )
            row = cursor.fetchone()

            if not row or row[1] <= 0:
                return None  # 没有恢复效果

            # 解析恢复等级
            timer_name = row[0]
            heal_amount = int(timer_name.split('|')[1])
            
            # 恢复HP（不超过最大HP）
            cursor.execute(
                "UPDATE player_stats SET now_hp = LEAST(now_hp + %s, max_hp) WHERE player_id = %s",
                (heal_amount, player_id)
            )

            # 减少恢复持续回合
            remaining = row[1] - 1
            if remaining <= 0:
                cursor.execute(
                    "DELETE FROM timers WHERE player_id = %s AND timer_name LIKE '恢复|%'",
                    (player_id,)
                )
                return f"玩家{player_id}恢复了{heal_amount}点HP，恢复效果已结束"
            else:
                cursor.execute(
                    "UPDATE timers SET remaining_turns = %s WHERE player_id = %s AND timer_name = %s",
                    (remaining, player_id, timer_name)
                )
                return f"玩家{player_id}恢复了{heal_amount}点HP，剩余{remaining}回合"
    except Exception as e:
        return f"恢复触发失败: {e}"


def trigger_all_recovery():
    """
    触发所有玩家的恢复效果（在回合开始时调用）
    返回: 所有恢复信息的列表
    """
    results = []
    try:
        with get_cursor() as cursor:
            cursor.execute("SELECT play_num FROM playnum")
            play_num_row = cursor.fetchone()
            if not play_num_row:
                return results
            play_num = play_num_row[0]

        for i in range(play_num):
            pid = i + 1
            msg = trigger_recovery(pid)
            if msg:
                results.append(msg)
        return results
    except Exception as e:
        return [f"恢复触发出错: {e}"]


def check_recovery(player_id):
    """
    检查玩家是否有恢复效果
    返回: (恢复等级, 剩余回合数) 元组，如果没有则返回 (0, 0)
    """
    try:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT timer_name, remaining_turns FROM timers WHERE player_id = %s AND timer_name LIKE '恢复|%'",
                (player_id,)
            )
            row = cursor.fetchone()
            if row:
                heal_amount = int(row[0].split('|')[1])
                return (heal_amount, row[1])
            return (0, 0)
    except Exception as e:
        print(f"检查恢复状态失败: {e}")
        return (0, 0)


# 概率系统 (euxrate)


def event_occurs(prob):
    return random.random() < prob


def outprint_optimized():
    res = []
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("SELECT play_num FROM playnum")
            play_num = cursor.fetchone()[0]

            for i in range(play_num):
                pid = i + 1
                # 获取该玩家的 now_ap, max_ap 以及角色的 ap_recover_min, ap_recover_max
                cursor.execute(
                    "SELECT ps.now_ap, ps.max_ap, rt.ap_recover_min, rt.ap_recover_max "
                    "FROM player_stats ps "
                    "JOIN role_templates rt ON ps.role_id = rt.id "
                    "WHERE ps.player_id = %s", (pid,)
                )
                row = cursor.fetchone()
                if not row: continue
                now_ap, max_ap, ap_recover_min, ap_recover_max = row
                
                # 如果没有设定配置，给个保守的默认值
                if ap_recover_min is None: ap_recover_min = 1
                if ap_recover_max is None: ap_recover_max = 3
                if max_ap is None: max_ap = 10
                if now_ap is None: now_ap = 0
                
                # 计算随机增加的 AP
                recover_ap = random.randint(ap_recover_min, ap_recover_max)
                new_ap = min(now_ap + recover_ap, max_ap)
                
                # 更新数据库
                cursor.execute(
                    "UPDATE player_stats SET now_ap = %s WHERE player_id = %s",
                    (new_ap, pid)
                )
                
                msg = f"玩家{pid} 本回合回复了 {recover_ap} 点行动值，当前行动值为 {new_ap} / {max_ap}"
                res.append(msg)
                
                # 同步更新原有的 euxrate，防止其他地方获取 totalturn 失效
                cursor.execute(
                    "UPDATE euxrate SET totalturn = totalturn + 1 WHERE id = %s", (pid,)
                )
        return res
    except Exception as e:
        return [f"AP结算出错: {str(e)}"]


# ==========================================
# 6. 角色特性与被动系统
# ==========================================

def trigger_passive_on_attack(attacker_id, target_id, damage_value):
    """
    攻击前触发 (攻击者视角)
    返回: 描述文本
    """
    role_name = get_role_name(attacker_id)
    msg = []
    
    if role_name == "输出大王":
        res = output_king.on_attack(attacker_id, target_id, damage_value)
        if res: msg.append(res)
    
    return "\n".join(msg)

def trigger_passive_on_defend(target_id, attacker_id, damage_value):
    """
    受击前触发 (防御者视角)
    返回: (描述文本, 修改后的伤害值 or None)
    """
    role_name = get_role_name(target_id)
    msg = []
    final_damage = damage_value
    
    if role_name == "输出大王":
        txt, dmg = output_king.on_defend(target_id, attacker_id, final_damage)
        if txt: msg.append(txt)
        if dmg is not None: final_damage = dmg

    return "\n".join(msg), final_damage

def execute_skill_effect(player_id, skill_idx):
    """
    执行技能效果 (在 skill_use CD 扣除后调用)
    """
    role_name = get_role_name(player_id)
    msg = []
    
    if role_name == "输出大王":
        res = output_king.on_skill(player_id, skill_idx)
        if res: msg.append(res)

    return "\n".join(msg)