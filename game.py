import mysql.connector
from contextlib import contextmanager
import random
import math

# ==========================================
# 1. 基础设施：配置与连接池
# ==========================================

db_config = {
    "host": "localhost",
    "user": "root",
    "password": "yarizm75",
    "database": "euxrvsh",
    "pool_name": "game_pool",
    "pool_size": 5
}

# 初始化连接池
try:
    connection_pool = mysql.connector.pooling.MySQLConnectionPool(**db_config)
except Exception as e:
    print(f"数据库连接池初始化失败: {e}")
    exit(1)


@contextmanager
def get_cursor(commit=False):
    """
    上下文管理器：自动获取连接、创建游标、提交事务/回滚、关闭连接
    """
    conn = None
    cursor = None
    try:
        conn = connection_pool.get_connection()
        cursor = conn.cursor(dictionary=False)
        yield cursor
        if commit:
            conn.commit()
    except mysql.connector.Error as err:
        if conn:
            conn.rollback()
        print(f"Database Error: {err}")
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        print(f"System Error: {e}")
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# ==========================================
# 2. 核心战斗数值管理
# ==========================================

def hp_change(player_id, value, change_type):
    """
    修改HP (原子操作)
    change_type: 0=当前HP, 1=最大HP
    """
    field = "now_hp" if int(change_type) == 0 else "max_hp"

    # 原子更新 SQL
    update_sql = f"UPDATE player_stats SET {field} = {field} + %s WHERE player_id = %s"
    select_sql = f"SELECT {field} FROM player_stats WHERE player_id = %s"

    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute(update_sql, (int(value), player_id))

            # 立即查回最新值
            cursor.execute(select_sql, (player_id,))
            result = cursor.fetchone()

            if result:
                label = "当前HP" if int(change_type) == 0 else "最大HP"
                return f"玩家{player_id}的{label}已变更为：{result[0]}"
            else:
                return f"玩家{player_id}不存在"
    except Exception as e:
        return f"HP变更失败: {str(e)}"


def attack(player_id, damage_value):
    """
    攻击逻辑：优先扣除护甲，剩余扣除HP (事务保护)
    """
    damage_value = int(damage_value)
    try:
        with get_cursor(commit=True) as cursor:
            # 1. 锁定并读取当前护甲
            cursor.execute("SELECT turn_def FROM player_stats WHERE player_id = %s FOR UPDATE", (player_id,))
            row = cursor.fetchone()
            if not row:
                return f"玩家{player_id}不存在"

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
            cursor.execute(sql_update, (actual_hp_damage, def_reduction, player_id))

            return f"玩家{player_id}受到了伤害：{damage_value} (实扣HP:{actual_hp_damage}, 扣防:{def_reduction})"
    except Exception as e:
        return f"攻击处理出错: {str(e)}"


def simple_stat_change(player_id, value, column_name, label_cn):
    """通用属性变更 (ATK, 距离等)"""
    try:
        with get_cursor(commit=True) as cursor:
            sql = f"UPDATE player_stats SET {column_name} = {column_name} + %s WHERE player_id = %s"
            cursor.execute(sql, (int(value), player_id))

            cursor.execute(f"SELECT {column_name} FROM player_stats WHERE player_id = %s", (player_id,))
            row = cursor.fetchone()
            return f"玩家{player_id}的{label_cn}已变更为：{row[0]}" if row else "玩家不存在"
    except Exception as e:
        return f"{label_cn}变更失败: {str(e)}"


def atk_change(player_id, value):
    return simple_stat_change(player_id, value, "atk", "攻击力(ATK)")


def distance_change(player_id, value):
    return simple_stat_change(player_id, value, "distance", "攻击距离")


def def_change(player_id, value):
    return simple_stat_change(player_id, value, "turn_def", "当前护甲")


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

            # 4. 初始化属性 (从模板表 -> 状态表)
            # 注意：这里直接初始化 total_def 和 turn_def 为 0
            insert_sql = """
                         INSERT INTO player_stats (player_id, role_id, max_hp, now_hp, atk, distance, turn_def, \
                                                   total_def)
                         SELECT %s, \
                                id, \
                                base_max_hp, \
                                base_max_hp, \
                                base_atk, \
                                base_dist, \
                                0, \
                                0
                         FROM role_templates \
                         WHERE id = %s \
                         """
            cursor.execute(insert_sql, (current_player_id, role_id))

            # 5. 轮次推进
            cursor.execute("UPDATE playnum SET nums = nums + 1")

            return f"玩家{current_player_id}, 您已成功选择角色：{role_row[1]}"
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

            return f"玩家{player_id}技能{skill_idx}已使用，CD重置为{max_cd}"
    except Exception as e:
        return f"技能使用失败: {str(e)}"


def cd_change(player_id, skill_idx, change_val):
    try:
        with get_cursor(commit=True) as cursor:
            sql = """
                  UPDATE skill_cooldowns
                  SET current_cd = GREATEST(0, current_cd + %s)
                  WHERE player_id = %s \
                    AND skill_index = %s \
                  """
            cursor.execute(sql, (int(change_val), player_id, int(skill_idx)))

            if cursor.rowcount == 0: return f"技能{skill_idx}不在冷却中"

            cursor.execute("SELECT current_cd FROM skill_cooldowns WHERE player_id=%s AND skill_index=%s",
                           (player_id, int(skill_idx)))
            return f"玩家{player_id}技能{skill_idx} CD变更为 {cursor.fetchone()[0]}"
    except Exception as e:
        return f"CD变更失败: {str(e)}"


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
                    "SELECT max_hp, now_hp, turn_def, total_def, atk, distance FROM player_stats WHERE player_id = %s",
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
                             f"当前ATK为：{stats[4]}，当前攻击距离为：{stats[5]}。 \n\n")
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
            cursor.execute("UPDATE timers SET remaining_turns = remaining_turns - 1 WHERE remaining_turns > 0")
            cursor.execute("DELETE FROM timers WHERE remaining_turns <= 0")
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


# 概率系统 (euxrate)
def latergiveup(player_id):
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("SELECT name, is_win FROM players WHERE id = %s", (player_id,))
            row = cursor.fetchone()
            if not row: return ["玩家不存在"]
            name, is_win = row

            if is_win:
                cursor.execute("UPDATE players SET is_win = 0, win_rate = 0.75 WHERE id = %s", (player_id,))
                msg = f"{name}已经在判定结束后放弃,该名玩家下次获得行动机会的概率为0.75"
                print(msg)
                return [msg]
            else:
                msg = f"{name}没有行动机会，不能放弃回合！"
                print(msg)
                return [msg]
    except Exception as e:
        return [f"操作失败: {e}"]


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
                cursor.execute(
                    "SELECT winrate, isdiff, iswin, x_value, isgive, totalturn, giveturn FROM euxrate WHERE id = %s",
                    (pid,))
                row = cursor.fetchone()
                if not row: continue
                winrate, isdiff, iswin, x_val, isgive, totalturn, giveturn = row

                msg = ""
                if isgive == 0:
                    have_turn = event_occurs(winrate)
                    new_isdiff = 1 if (iswin is not None and iswin != have_turn) else 0
                    new_iswin = 1 if have_turn else 0

                    if new_iswin:
                        new_x = x_val + 1 if new_isdiff == 0 else 0
                        new_winrate = 0.5
                    else:
                        new_x = x_val + 1 if new_isdiff == 0 else 0
                        new_winrate = winrate + 0.5 * (1 - math.exp(-0.1 * abs(new_x)))

                    new_totalturn = totalturn + 1
                    new_giveturn = 0
                    status = "有" if have_turn else "没有"
                    msg = f"玩家{pid} {status}行动机会, 下次概率 {new_winrate:.2f}"
                else:
                    new_isdiff, new_iswin, new_x = 0, 0, 0
                    new_totalturn = totalturn + 1
                    new_giveturn = giveturn + 1
                    new_winrate = 0.5 + 0.2 * new_giveturn
                    new_isgive = 0
                    msg = f"玩家{pid}已放弃回合, 下次概率 {new_winrate:.2f}"

                res.append(msg)
                update_sql = """
                             UPDATE euxrate \
                             SET winrate=%s, \
                                 isdiff=%s, \
                                 iswin=%s, \
                                 x_value=%s, \
                                 isgive=%s, \
                                 totalturn=%s, \
                                 giveturn=%s \
                             WHERE id = %s \
                             """
                cursor.execute(update_sql,
                               (new_winrate, new_isdiff, new_iswin, new_x, isgive if isgive == 0 else 0, new_totalturn,
                                new_giveturn, pid))
        return res
    except Exception as e:
        return [f"概率判定出错: {str(e)}"]