"""档案状态转换服务（简化版）

统一管理 profile_status 的状态转换逻辑：
- 状态转换规则验证
- 数据库更新
- 审计日志记录
- 状态转换通知

核心思想：登录即活跃、匹配即已匹配、长期不登录标记不活跃、登录恢复、匹配不聊天恢复
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from profile_service import apply_profile_updates
from profile_status_audit_log import ProfileStatusAuditLog


# 允许的状态转换规则（简化版，只有3个状态）
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "active": {"matched", "inactive"},
    "matched": {"active", "inactive"},
    "inactive": {"active"},
}


def transition_profile_status(
    *,
    profile_id: int,
    from_status: str,
    to_status: str,
    reason: str,
    details: dict[str, Any],
    source_dsn: str,
    source_table_name: str,
    actor_type: str = "system",
    actor_id: int | None = None,
) -> dict[str, Any]:
    """执行档案状态转换

    Args:
        profile_id: 档案ID
        from_status: 当前状态
        to_status: 目标状态
        reason: 转换原因（match_success/match_inactive/auto_inactive/user_login/admin_action）
        details: 转换详情
        source_dsn: 数据源
        source_table_name: 档案表名
        actor_type: 操作者类型（system/user/admin）
        actor_id: 操作者ID

    Returns:
        转换结果

    Raises:
        ValueError: 状态转换规则不允许

    Example:
        >>> transition_profile_status(
        ...     profile_id=123,
        ...     from_status="active",
        ...     to_status="matched",
        ...     reason="match_success",
        ...     details={"matched_with": 456},
        ...     source_dsn="mysql://...",
        ...     source_table_name="profiles",
        ... )
    """

    # 1. 验证转换规则
    if to_status not in ALLOWED_TRANSITIONS.get(from_status, set()):
        raise ValueError(
            f"不允许从 {from_status} 转换到 {to_status}。"
            f"允许的目标状态：{ALLOWED_TRANSITIONS.get(from_status, set())}"
        )

    # 2. 更新数据库
    update_result = apply_profile_updates(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        profile_id=profile_id,
        updates={
            "profile_status": to_status,
            "updated_at": datetime.now(),
        },
    )

    # 3. 记录审计日志
    ProfileStatusAuditLog.log_transition(
        profile_id=profile_id,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        details=details,
        actor_type=actor_type,
        actor_id=actor_id,
        source_dsn=source_dsn,
    )

    # 4. 发送通知（可选）
    _send_transition_notification(
        profile_id=profile_id,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        details=details,
    )

    return {
        "status": "success",
        "profile_id": profile_id,
        "from_status": from_status,
        "to_status": to_status,
        "reason": reason,
        "occurred_at": datetime.now().isoformat(),
        "update_result": update_result,
    }


def _send_transition_notification(
    profile_id: int,
    from_status: str,
    to_status: str,
    reason: str,
    details: dict[str, Any],
) -> None:
    """发送状态转换通知

    目前只记录日志，后续可以接入通知服务
    """

    # 匹配成功通知
    if reason == "match_success":
        matched_with = details.get("matched_with")
        # TODO: 接入通知服务
        print(f"[通知] 用户 {profile_id} 与用户 {matched_with} 匹配成功")

    # 匹配不活跃恢复通知
    if reason == "match_inactive":
        previous_match = details.get("previous_match")
        # TODO: 接入通知服务
        print(f"[通知] 用户 {profile_id} 与用户 {previous_match} 匹配关系已结束，档案恢复为活跃")

    # 用户登录恢复通知
    if reason == "user_login":
        # TODO: 接入通知服务
        print(f"[通知] 用户 {profile_id} 登录，档案恢复为活跃")


def get_status_transition_rules() -> dict[str, set[str]]:
    """获取状态转换规则

    Returns:
        状态转换规则字典

    Example:
        >>> rules = get_status_transition_rules()
        >>> print(rules)
        {'active': {'matched', 'inactive'}, 'matched': {'active', 'inactive'}, 'inactive': {'active'}}
    """
    return ALLOWED_TRANSITIONS.copy()


def validate_transition(from_status: str, to_status: str) -> bool:
    """验证状态转换是否允许

    Args:
        from_status: 当前状态
        to_status: 目标状态

    Returns:
        是否允许转换

    Example:
        >>> validate_transition("active", "matched")
        True
        >>> validate_transition("inactive", "matched")
        False
    """
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


def get_allowed_transitions_for_status(status: str) -> set[str]:
    """获取某个状态允许转换的目标状态

    Args:
        status: 当前状态

    Returns:
        允许转换的目标状态集合

    Example:
        >>> get_allowed_transitions_for_status("active")
        {'matched', 'inactive'}
        >>> get_allowed_transitions_for_status("inactive")
        {'active'}
    """
    return ALLOWED_TRANSITIONS.get(status, set())


__all__ = [
    "transition_profile_status",
    "get_status_transition_rules",
    "validate_transition",
    "get_allowed_transitions_for_status",
    "ALLOWED_TRANSITIONS",
]