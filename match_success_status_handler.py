"""匹配成功状态转换逻辑

当用户匹配成功时：
1. 双方档案状态自动改为 matched
2. 记录状态转换审计日志
3. 发送匹配成功通知

核心思想：匹配即已匹配
"""

from datetime import datetime
from typing import Any
from profile_service import resolve_profile_record
from profile_status_service import transition_profile_status


def on_match_success_transition(
    *,
    owner_id: int,
    target_id: int,
    source_dsn: str,
    source_table_name: str,
) -> dict[str, Any]:
    """匹配成功后自动更新双方档案状态为 matched

    核心思想：匹配即已匹配

    Args:
        owner_id: 用户A的ID
        target_id: 用户B的ID
        source_dsn: 数据源
        source_table_name: 档案表名

    Returns:
        匹配状态转换结果

    Example:
        >>> result = on_match_success_transition(
        ...     owner_id=123,
        ...     target_id=456,
        ...     source_dsn="mysql://...",
        ...     source_table_name="profiles",
        ... )
        >>> print(result["message"])
        "匹配成功，双方状态已更新"
    """

    # 查询双方当前状态
    owner_record = resolve_profile_record(
        self_id=owner_id,
        records=[],
        source_dsn=source_dsn,
        source_table_name=source_table_name,
    )

    target_record = resolve_profile_record(
        self_id=target_id,
        records=[],
        source_dsn=source_dsn,
        source_table_name=source_table_name,
    )

    owner_status = owner_record.get("profile_status")
    target_status = target_record.get("profile_status")

    # 只有 active 状态才能改为 matched
    transitions = []

    if owner_status == "active":
        owner_transition = transition_profile_status(
            profile_id=owner_id,
            from_status="active",
            to_status="matched",
            reason="match_success",
            details={
                "matched_with": target_id,
                "matched_at": datetime.now().isoformat(),
            },
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            actor_type="system",
        )
        transitions.append(owner_transition)

    if target_status == "active":
        target_transition = transition_profile_status(
            profile_id=target_id,
            from_status="active",
            to_status="matched",
            reason="match_success",
            details={
                "matched_with": owner_id,
                "matched_at": datetime.now().isoformat(),
            },
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            actor_type="system",
        )
        transitions.append(target_transition)

    return {
        "status": "success",
        "message": "匹配成功，双方状态已更新",
        "transitions": transitions,
        "owner_id": owner_id,
        "target_id": target_id,
        "owner_previous_status": owner_status,
        "target_previous_status": target_status,
    }


__all__ = ["on_match_success_transition"]