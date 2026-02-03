# -*- coding: utf-8 -*-
import os
import botpy
import dashscope  # 引入阿里云SDK
from botpy import logging, BotAPI
from botpy.ext.cog_yaml import read
from botpy.ext.command_util import Commands
from botpy.message import Message

# 导入游戏逻辑和插件
import game as newgame
from plugins import chat_api

# 1. 读取配置文件
config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
test_config = read(config_path)

# 2. 【关键安全配置】初始化阿里云 SDK
# 从配置文件中获取 Key，如果不存在则报错提示
if "dashscope_api_key" in test_config:
    dashscope.api_key = test_config["dashscope_api_key"]
else:
    print("警告：config.yaml 中未找到 dashscope_api_key，AI 功能将无法使用！")

_log = logging.get_logger()


# =======================================================
# 游戏流程指令
# =======================================================

@Commands("/START", "开")
async def start(api: BotAPI, message: Message, params=None):
    _log.info(f"Start params: {params}")
    if not params:
        await message.reply(content="请输入游戏人数！例如：/START 2")
        return True

    try:
        play_num = int(params)
        result = newgame.startgame(play_num)
        nowturn = 1
        await message.reply(content=f"启动！设定玩家数为 {result}。\n"
                                    f"接下来请输入 /PICK [角色id] 来选择角色。\n"
                                    f"当前是第 {nowturn} 回合准备阶段。")
    except Exception as e:
        await message.reply(content=f"启动失败：{str(e)}")
    return True


@Commands("/PICK", "/pick")
async def pick(api: BotAPI, message: Message, params=None):
    if not params: return True
    args = params.split()
    try:
        role_id = int(args[0])
        result = newgame.pickrole(role_id)
        await message.reply(content=f"{result}")
    except Exception as e:
        await message.reply(content=f"选角出错: {e}")
    return True


@Commands("/OUT", "/out")
async def out(api: BotAPI, message: Message, params=None):
    try:
        newgame.resetdef()
        newgame.remsubauto()
        data_report = newgame.turnend(1)
        prob_report = newgame.outprint_optimized()

        data_str = '\n\n'.join(str(e) for e in data_report)
        prob_str = '\n\n'.join(str(e) for e in prob_report)

        await message.reply(content=f"【回合结算】\n\n"
                                    f"--- 行动权判定 ---\n{prob_str}\n\n"
                                    f"--- 玩家状态 ---\n{data_str}\n\n"
                                    f"请获得行动权的玩家输入指令行动。\n"
                                    f"放弃回合请输 /LGIVEUP [玩家id]")
    except Exception as e:
        _log.error(e)
        await message.reply(content=f"结算报错: {e}")
    return True


@Commands("/END", "/end")
async def end(api: BotAPI, message: Message, params=None):
    try:
        if newgame.endgame():
            await message.reply(content="游戏已结束，数据已重置。")
        else:
            await message.reply(content="结束游戏失败，请查看日志。")
    except Exception as e:
        await message.reply(content=f"Error: {e}")
    return True


# =======================================================
# AI 问答指令
# =======================================================

@Commands("/AI", "/ai")
async def ai(api: BotAPI, message: Message, params=None):
    # 1. 处理输入文本
    msg = params.strip() if params else ""

    if not msg:
        await message.reply(content="请在指令后面输入你想问的内容哦，例如：/ai 介绍一下慕亚斯")
        return True

    # 2. 【修复点】兼容获取用户 ID (群聊用 member_openid, 频道用 id)
    user_id = getattr(message.author, "id", None) or getattr(message.author, "member_openid", None)

    # 如果还是获取不到，做一个兜底（比如用 unknown）
    if not user_id:
        user_id = "unknown_user"

    try:
        # 3. 调用 API
        result = chat_api.chat_answer(user_id=str(user_id), text=msg)
        await message.reply(content=f"{result}")
    except Exception as e:
        _log.error(f"AI Reply Error: {e}")
        await message.reply(content="AI 接口出现异常，请检查后台日志。")

    return True


# =======================================================
# 玩家战斗与属性指令
# =======================================================

@Commands("/HPC", "/hpc")
async def hpc(api: BotAPI, message: Message, params=None):
    if not params: return
    args = params.split()
    try:
        # 兼容性检查：确保传了3个参数
        if len(args) < 3:
            await message.reply(content="参数不足，格式：/HPC [ID] [数值] [类型]")
            return True
        res = newgame.hp_change(args[0], args[1], args[2])
        await message.reply(content=f"{res}")
    except Exception as e:
        await message.reply(content=f"Error: {e}")
    return True


@Commands("/ATTACK", "/attack")
async def attack(api: BotAPI, message: Message, params=None):
    if not params: return
    args = params.split()
    try:
        if len(args) < 2:
            await message.reply(content="参数不足，格式：/ATTACK [目标ID] [伤害]")
            return True
        res = newgame.attack(args[0], args[1])
        await message.reply(content=f"{res}")
    except Exception as e:
        await message.reply(content=f"攻击出错: {e}")
    return True


@Commands("/SKILL", "/skill")
async def skill(api: BotAPI, message: Message, params=None):
    if not params: return
    args = params.split()
    try:
        res = newgame.skill_use(args[0], args[1])
        await message.reply(content=f"{res}")
    except Exception as e:
        await message.reply(content=f"技能出错: {e}")
    return True


@Commands("/LGIVEUP", "/lgiveup")
async def lgiveup(api: BotAPI, message: Message, params=None):
    if not params: return
    try:
        pid = params.split()[0]
        res = newgame.latergiveup(pid)
        # latergiveup 返回的是 list，取第一个元素
        await message.reply(content=f"{res[0]}")
    except Exception as e:
        await message.reply(content=f"操作出错: {e}")
    return True


# ... 其他属性指令 (ATKC, DEFC, CDC, DISC) 保持原逻辑即可，注意 split() ...

@Commands("/ATKC", "/atkc")
async def atkc(api: BotAPI, message: Message, params=None):
    args = params.split()
    res = newgame.atk_change(args[0], args[1])
    await message.reply(content=f"{res}")
    return True


@Commands("/DEFC", "/defc")
async def defc(api: BotAPI, message: Message, params=None):
    args = params.split()
    res = newgame.def_change(args[0], args[1])
    await message.reply(content=f"{res}")
    return True


@Commands("/DISC", "/disc")
async def disc(api: BotAPI, message: Message, params=None):
    args = params.split()
    res = newgame.distance_change(args[0], args[1])
    await message.reply(content=f"{res}")
    return True


@Commands("/CDC", "/cdc")
async def cdc(api: BotAPI, message: Message, params=None):
    args = params.split()
    res = newgame.cd_change(args[0], args[1], args[2])
    await message.reply(content=f"{res}")
    return True


# =======================================================
# 计时器与辅助
# =======================================================

@Commands("/REMTIME", "/remtime")
async def remtime(api: BotAPI, message: Message, params=None):
    args = params.split()
    res = newgame.timerem(args[0], args[1], args[2])
    await message.reply(content=f"{res}")
    return True


@Commands("/TIMEINFO", "/timeinfo")
async def timeinfo(api: BotAPI, message: Message, params=None):
    res = newgame.timeinfo()
    txt = '\n'.join(str(e) for e in res) if res else "当前无计时器"
    await message.reply(content=f"\n{txt}")
    return True


@Commands("/TIMESET", "/timeset")
async def timeset(api: BotAPI, message: Message, params=None):
    args = params.split()
    res = newgame.remsubhand(args[0], args[1], args[2])
    await message.reply(content=f"{res}")
    return True


@Commands("/ROLEDATA", "/roledata")
async def roledata(api: BotAPI, message: Message, params=None):
    res = newgame.turnend(0)
    txt = '\n\n'.join(str(e) for e in res)
    await message.reply(content=f"当前数据:\n{txt}")
    return True

@Commands("/RATE", "/rate")
async def rate(api: BotAPI, message: Message, params=None):
    res = newgame.event_occurs(float(params))
    if res:
        res = "判定成功!"
    else:
        res = "判定失败!"
    await message.reply(content=f"{res}")
    return True


@Commands("/HELP", "/help")
async def help(api: BotAPI, message: Message, params=None):
    msg = ("局内指令格式一览：\n\n"
           "AI问答：/AI [问题] \n"
           "改变血量：/HPC [ID] [数值] [类型0/1] \n"
           "改变ATK：/ATKC [ID] [数值] \n"
           "改变DEF：/DEFC [ID] [数值] \n"
           "改变CD：/CDC [ID] [技能号] [数值] \n"
           "使用技能：/SKILL [ID] [技能号] \n"
           "攻击：/ATTACK [目标ID] [伤害] \n"
           "查看状态：/ROLEDATA \n"
           "回合结算：/OUT \n"
           "结束游戏：/END\n"
           "概率判定：/RATE [概率]")
    await message.reply(content=msg)
    return True


# =======================================================
# 机器人主类
# =======================================================

class MyClient(botpy.Client):
    async def on_ready(self):
        _log.info(f"robot 「{self.robot.name}」 on_ready!")

    async def on_group_at_message_create(self, message: Message):
        handlers = [
            start, pick, out, end, ai,
            hpc, atkc, defc, cdc, skill, attack, disc,
            remtime, timeset, timeinfo,
            roledata, lgiveup, help,rate
        ]
        for handler in handlers:
            if await handler(api=self.api, message=message):
                return


if __name__ == "__main__":
    # 使用 config.yaml 中的配置启动
    intents = botpy.Intents(public_messages=True)
    client = MyClient(intents=intents)
    client.run(appid=test_config["appid"], secret=test_config["secret"])