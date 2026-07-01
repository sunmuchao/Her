"""SSE推送工具函数

封装调用SSE Server的推送接口，用于各种事件触发点调用。

使用场景：
- 匹配成功时推送new_match事件
- 匹配状态变化时推送match_status_change事件
- 验证完成时推送verification_passed/failed事件
- 档案更新时推送profile_update事件
"""

import httpx
from datetime import datetime
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

# SSE Server推送接口地址
SSE_SERVER_URL = "http://localhost:8000"  # 根据实际部署环境调整


async def push_sse_event(
    profile_id: str,
    event_type: str,
    data: Optional[Dict[str, Any]] = None
) -> bool:
    """
    推送SSE事件到全局Profile连接

    Args:
        profile_id: 用户档案ID
        event_type: 事件类型（如new_match、match_status_change等）
        data: 事件额外数据

    Returns:
        True if推送成功, False otherwise
    """
    try:
        payload = {
            "profile_id": profile_id,
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # 添加事件特定数据
        if data:
            payload.update(data)

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{SSE_SERVER_URL}/internal/push/profile",
                json=payload
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"[SSE Push] 推送成功: profile={profile_id}, event={event_type}, pushed={result.get('pushed')}"
                )
                return True
            else:
                logger.error(
                    f"[SSE Push] 推送失败: profile={profile_id}, event={event_type}, status={response.status_code}"
                )
                return False

    except Exception as e:
        logger.error(
            f"[SSE Push] 推送异常: profile={profile_id}, event={event_type}, error={str(e)}"
        )
        return False


# ===== 具体事件推送函数 =====

async def push_new_match(
    profile_id: str,
    match_id: str,
    target_profile_id: str,
    status: str = "waiting_response"
) -> bool:
    """
    推送新匹配到达事件

    Args:
        profile_id: 接收推送的用户档案ID
        match_id: 匹配ID
        target_profile_id: 匹配对象档案ID
        status: 匹配状态

    Returns:
        True if推送成功
    """
    return await push_sse_event(
        profile_id,
        "new_match",
        {
            "match_id": match_id,
            "target_profile_id": target_profile_id,
            "status": status,
        }
    )


async def push_match_status_change(
    profile_id: str,
    match_id: str,
    old_status: str,
    new_status: str
) -> bool:
    """
    推送匹配状态变化事件

    Args:
        profile_id: 接收推送的用户档案ID
        match_id: 匹配ID
        old_status: 旧状态
        new_status: 新状态

    Returns:
        True if推送成功
    """
    return await push_sse_event(
        profile_id,
        "match_status_change",
        {
            "match_id": match_id,
            "old_status": old_status,
            "new_status": new_status,
        }
    )


async def push_verification_passed(
    profile_id: str,
    message: str = "恭喜！您的身份验证已通过"
) -> bool:
    """
    推送验证通过事件

    Args:
        profile_id: 用户档案ID
        message: 提示消息

    Returns:
        True if推送成功
    """
    return await push_sse_event(
        profile_id,
        "verification_passed",
        {
            "message": message,
        }
    )


async def push_verification_failed(
    profile_id: str,
    message: str = "验证未通过，请重新提交材料"
) -> bool:
    """
    推送验证失败事件

    Args:
        profile_id: 用户档案ID
        message: 提示消息

    Returns:
        True if推送成功
    """
    return await push_sse_event(
        profile_id,
        "verification_failed",
        {
            "message": message,
        }
    )


async def push_profile_update(
    profile_id: str,
    updated_profile_id: str,
    updated_fields: list[str]
) -> bool:
    """
    推送用户档案更新事件（通知对方）

    Args:
        profile_id: 接收推送的用户档案ID（匹配对象）
        updated_profile_id: 更新的档案ID（被查看的人）
        updated_fields: 更新的字段列表

    Returns:
        True if推送成功
    """
    return await push_sse_event(
        profile_id,
        "profile_update",
        {
            "updated_profile_id": updated_profile_id,
            "updated_fields": updated_fields,
        }
    )


async def push_badge_update(
    profile_id: str,
    badge_type: str,
    count: int
) -> bool:
    """
    推送徽章数量更新事件

    Args:
        profile_id: 用户档案ID
        badge_type: 徽章类型
        count: 徽章数量

    Returns:
        True if推送成功
    """
    return await push_sse_event(
        profile_id,
        "badge_update",
        {
            "badge_type": badge_type,
            "count": count,
        }
    )


async def push_typing_start(
    profile_id: str,
    case_id: str,
    typing_user_id: str
) -> bool:
    """
    推送正在输入事件

    Args:
        profile_id: 接收推送的用户档案ID
        case_id: 聊天case ID
        typing_user_id: 正在输入的用户ID

    Returns:
        True if推送成功
    """
    return await push_sse_event(
        profile_id,
        "typing_start",
        {
            "case_id": case_id,
            "typing_user_id": typing_user_id,
        }
    )


async def push_typing_end(
    profile_id: str,
    case_id: str,
    typing_user_id: str
) -> bool:
    """
    推送停止输入事件

    Args:
        profile_id: 接收推送的用户档案ID
        case_id: 聊天case ID
        typing_user_id: 停止输入的用户ID

    Returns:
        True if推送成功
    """
    return await push_sse_event(
        profile_id,
        "typing_end",
        {
            "case_id": case_id,
            "typing_user_id": typing_user_id,
        }
    )