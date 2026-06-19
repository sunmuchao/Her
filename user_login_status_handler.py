"""用户登录状态恢复逻辑

当用户登录时：
1. 如果用户当前状态是 inactive，自动恢复为 active
2. 更新 last_active_at 时间
3. 记录状态转换审计日志
"""

from datetime import datetime
from typing import Any
from profile_service import apply_profile_updates, resolve_profile_record
from profile_status_service import transition_profile_status


def on_user_login(
    *,
    user_id: int,
    source_dsn: str,
    source_table_name: str,
) -> dict[str, Any]:
    """用户登录时自动设置状态为活跃

    核心思想：登录即活跃

    Args:
        user_id: 用户ID
        source_dsn: 数据源
        source_table_name: 档案表名

    Returns:
        登录状态处理结果

    Example:
        >>> result = on_user_login(
        ...     user_id=123,
        ...     source_dsn="mysql://...",
        ...     source_table_name="profiles",
        ... )
        >>> print(result["message"])
        "档案已恢复为活跃状态"
    """

    # 查询当前状态
    current_record = resolve_profile_record(
        self_id=user_id,
        records=[],
        source_dsn=source_dsn,
        source_table_name=source_table_name,
    )

    current_status = current_record.get("profile_status")

    # 如果是 inactive，登录后自动恢复为 active
    if current_status == "inactive":
        transition_result = transition_profile_status(
            profile_id=user_id,
            from_status="inactive",
            to_status="active",
            reason="user_login",
            details={
                "previous_status": current_status,
                "login_time": datetime.now().isoformat(),
            },
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            actor_type="user",
            actor_id=user_id,
        )

        # 同时更新 last_active_at
        apply_profile_updates(
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            profile_id=user_id,
            updates={"last_active_at": datetime.now()},
        )

        return {
            "status": "success",
            "message": "档案已恢复为活跃状态",
            "transition": transition_result,
            "previous_status": current_status,
            "current_status": "active",
        }

    # 如果已经是 active 或 matched，只更新登录时间
    apply_profile_updates(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_id=user_id,
        updates={"last_active_at": datetime.now()},
    )

    return {
        "status": "success",
        "message": "登录成功",
        "current_status": current_status,
        "action": "update_last_active_at",
    }


__all__ = ["on_user_login"]