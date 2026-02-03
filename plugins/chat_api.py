# -*- coding: utf-8 -*-
import os
import dashscope
from dashscope import Generation
import logging

_log = logging.getLogger(__name__)

# =================配置区域=================
DEFAULT_MODEL = Generation.Models.qwen_turbo
MAX_HISTORY_LENGTH = 20

# 定义提示词文件的绝对路径
# 假设文件放在 plugins 文件夹下，与当前脚本同级
PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), "system_prompt.txt")

# 默认人设 (当文件读取失败时的兜底)
DEFAULT_SYSTEM_PROMPT = "你是一个游戏助手。"

# 全局内存字典
history_buffer = {}


def load_system_prompt():
    """
    从文本文件中读取系统提示词
    """
    try:
        if os.path.exists(PROMPT_FILE_PATH):
            with open(PROMPT_FILE_PATH, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return {'role': 'system', 'content': content}
    except Exception as e:
        _log.error(f"读取提示词文件失败: {e}")

    # 如果文件不存在或读取出错，返回默认值
    return {'role': 'system', 'content': DEFAULT_SYSTEM_PROMPT}


def reset_memory(user_id: str):
    """清空指定用户的记忆"""
    if user_id in history_buffer:
        del history_buffer[user_id]
        return True
    return False


def chat_answer(user_id: str, text: str, model_name=DEFAULT_MODEL) -> str:
    if not text:
        return "请在这条指令后面加上你想问的问题哦~"

    if not dashscope.api_key:
        _log.error("DashScope API Key is missing!")
        return "系统配置错误：未设置 API Key。"

    # 1. 获取当前最新的系统提示词 (实现热更新)
    current_system_prompt = load_system_prompt()

    # 2. 初始化或更新记忆
    if user_id not in history_buffer:
        history_buffer[user_id] = [current_system_prompt]
    else:
        # 【关键优化】
        # 每次对话前，强制检查并更新记忆中的第一条 System Prompt
        # 这样你在运行期间修改 txt 文件，下一轮对话 AI 就会立即应用新人设
        if history_buffer[user_id] and history_buffer[user_id][0]['role'] == 'system':
            history_buffer[user_id][0] = current_system_prompt
        else:
            # 如果记忆错乱（第一条不是system），则强行插入
            history_buffer[user_id].insert(0, current_system_prompt)

    # 3. 追加用户问题
    history_buffer[user_id].append({'role': 'user', 'content': text})

    # 4. 滑动窗口修剪 (保留最新的N条，但永远保留第一条System Prompt)
    if len(history_buffer[user_id]) > MAX_HISTORY_LENGTH + 1:
        history_buffer[user_id] = [history_buffer[user_id][0]] + history_buffer[user_id][-MAX_HISTORY_LENGTH:]

    try:
        response = Generation.call(
            model=model_name,
            messages=history_buffer[user_id],
            result_format='message',
            enable_search=False
        )

        # if response.status_code == HTTPStatus.OK:
        reply_content = response.output.choices[0].message.content
        history_buffer[user_id].append({'role': 'assistant', 'content': reply_content})
        return reply_content
        # else:
        #     history_buffer[user_id].pop()
        #     _log.error(f"AI Call Error: {response.code} - {response.message}")
        #     return f"响应失败 (错误码: {response.code})"

    except Exception as e:
        if user_id in history_buffer and history_buffer[user_id][-1]['role'] == 'user':
            history_buffer[user_id].pop()
        _log.error(f"System Error in chat_api: {e}")
        return "网络连接失败，请稍后再试~"