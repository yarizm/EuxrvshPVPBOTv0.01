from __future__ import annotations

from typing import Any, Callable


def _default_segment_builder(user_text: str, assistant_text: str) -> tuple[Any, Any]:
    from astrbot.core.agent.message import AssistantMessageSegment, TextPart, UserMessageSegment

    user_message = UserMessageSegment(content=[TextPart(text=user_text)])
    assistant_message = AssistantMessageSegment(content=[TextPart(text=assistant_text)])
    return user_message, assistant_message


async def record_conversation_pair(
    conversation_manager: Any,
    unified_msg_origin: str,
    user_text: str,
    assistant_text: str,
    *,
    segment_builder: Callable[[str, str], tuple[Any, Any]] | None = None,
) -> bool:
    if conversation_manager is None:
        return False
    if not str(unified_msg_origin).strip():
        return False
    if not str(user_text).strip():
        return False
    if not str(assistant_text).strip():
        return False

    builder = segment_builder or _default_segment_builder
    curr_cid = await conversation_manager.get_curr_conversation_id(unified_msg_origin)
    if not curr_cid:
        curr_cid = await conversation_manager.new_conversation(unified_msg_origin)

    user_message, assistant_message = builder(user_text, assistant_text)
    await conversation_manager.add_message_pair(
        cid=curr_cid,
        user_message=user_message,
        assistant_message=assistant_message,
    )
    return True
