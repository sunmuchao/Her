---
name: profile-status-auto-transition-plan-v2
description: 档案状态自动转换实施方案（简化版）：登录即活跃、匹配即已匹配、长期不登录标记不活跃、登录恢复、匹配不聊天恢复
metadata:
  type: project
---

# 档案状态自动转换实施方案（简化版）

## 核心思想

**一句话总结**：登录就是活跃，匹配成功就是已匹配，长期不登录标记不活跃，登录就恢复，匹配不聊天自动恢复。

---

## 状态定义（简化版）

### 只需要3个状态

| 状态 | 中文 | 含义 | 推荐行为 | 触发条件 |
|------|------|------|---------|---------|
| **active** | 活跃 | 用户登录，正在找对象 | ✅ 正常推荐 | 用户登录 |
| **matched** | 已匹配 | 用户匹配成功，正在聊天 | ❌ 暂停推荐 | 匹配成功 |
| **inactive** | 不活跃 | 用户长期不登录 | ❌ 暂停推荐 | 30天不登录 |

**删除的状态**：
- ❌ paused（暂停）- 不需要用户手动暂停，长期不登录自动标记
- ❌ archived（归档）- 不需要永久归档，登录就能恢复

---

## 状态转换流程图

```
┌─────────────────────────────────────────────────────────────┐
│                    状态转换完整流程                          │
└─────────────────────────────────────────────────────────────┘

用户注册
    ↓
初始状态：active
    ↓
用户登录 → 保持 active（如果 inactive 则恢复为 active）
    ↓
    ├─→ [匹配成功] → 自动改为 matched
    │        ↓
    │    专注于当前对象，不再推荐
    │        ↓
    │        ├─→ [正常聊天] → 保持 matched
    │        │
    │        └─→ [7天不聊天] → 自动恢复为 active
    │                ↓
    │            可以重新找对象
    │
    ├─→ [30天不登录] → 自动标记为 inactive
    │        ↓
    │    暂停推荐，标记为不活跃
    │        ↓
    │        ├─→ [用户登录] → 自动恢复为 active
    │        │        ↓
    │        │    重新开始推荐
    │        │
    │        └─→ [长期不登录] → 保持 inactive
    │
    └─→ [管理员封禁] → 特殊处理（删除档案或特殊标记）
```

---

## 状态转换规则矩阵

```
┌─────────────┬─────────────────────────────────────┬─────────────┐
│ 当前状态     │ 允许转换的目标状态                  │ 转换触发点  │
├─────────────┼─────────────────────────────────────┼─────────────┤
│ active      │ matched, inactive                   │ 匹配成功/不登录 │
│ matched     │ active, inactive                    │ 不聊天/不登录 │
│ inactive    │ active                              │ 用户登录    │
└─────────────┴─────────────────────────────────────┴─────────────┘

转换原因分类：
• match_success: 匹配成功（自动）
• match_inactive: 匹配后长期不聊天（自动）
• auto_inactive: 长期不登录标记不活跃（自动）
• user_login: 用户登录恢复（自动）
• admin_action: 管理员操作（封禁/删除）
```

---

## 具体实施方案

### 📌 实施点1：用户登录自动设置为活跃

**触发点**：用户登录成功

**触发时机**：
- 用户打开APP/网站
- 用户输入账号密码登录
- 用户使用第三方账号登录

**实现位置**：`profile_service/api.py` - 登录接口

**实现代码**：

```python
# 文件：profile_service/api.py

def on_user_login(
    *,
    user_id: int,
    source_dsn: str,
    source_table_name: str,
) -> dict[str, Any]:
    """用户登录时自动设置状态为活跃
    
    如果用户当前是 inactive，登录后自动恢复为 active
    """
    
    # 查询当前状态
    current_record = resolve_profile_record(
        self_id=user_id,
        records=[],
        source_dsn=source_dsn,
        source_table_name=source_table_name,
    )
    
    current_status = current_record.get("profile_status")
    
    # 如果是 inactive，登录后恢复为 active
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
        
        return {
            "status": "success",
            "message": "档案已恢复为活跃状态",
            "transition": transition_result,
        }
    
    # 如果已经是 active，更新登录时间
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
    }
```

**大白话解释**：
就像相亲群里，只要用户来了（登录），群主就把他的状态改成"正在找对象"。如果他之前被标记为"不活跃"，来了就自动恢复为"活跃"，不需要他做什么操作。

---

### 📌 实施点2：匹配成功自动改为已匹配

**触发点**：双向匹配检测成功

**触发时机**：
- 用户A和用户B都互相接受
- 系统检测到双向匹配
- 创建匹配关系

**实现位置**：`match_domain/ledger.py` - 匹配关系建立

**实现代码**：

```python
# 文件：match_domain/ledger.py

def on_match_success_transition(
    *,
    owner_id: int,
    target_id: int,
    source_dsn: str,
    source_table_name: str,
) -> dict[str, Any]:
    """匹配成功后自动更新双方档案状态为 matched
    
    双方都改为 matched，系统不再推荐新人
    """
    
    from profile_status_service import transition_profile_status
    
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
    }


# 在匹配关系建立时调用
def apply_ledger_event(event: MatchEvent) -> None:
    """应用事件到状态"""
    
    if event.event_type == "relation_state_revision":
        payload = event.payload
        
        if payload.get("status") == RelationStatus.MATCHED.value:
            # 双向匹配成功！
            on_match_success_transition(
                owner_id=int(event.aggregate_id.split(":")[1]),
                target_id=int(payload.get("target_id")),
                source_dsn=payload.get("source_dsn"),
                source_table_name=payload.get("source_table_name"),
            )
```

**大白话解释**：
就像相亲群里，小明和小红都同意了，群主自动把两个人的状态改成"已经有对象了"，系统就不会再给他们推新人，也不会把他们的资料推给别人。

---

### 📌 实施点3：长期不登录自动标记为不活跃

**触发点**：定时任务（每天凌晨执行）

**触发时机**：
- 每天凌晨2点自动检查
- 检查所有用户最近登录时间
- 30天不登录的用户标记为 inactive

**实现位置**：新增脚本 `scripts/auto_mark_inactive_profiles.py`

**实现代码**：

```python
# 文件：scripts/auto_mark_inactive_profiles.py

import argparse
import json
from datetime import datetime, timedelta
from profile_service import list_profiles
from profile_status_service import transition_profile_status

def auto_mark_inactive_profiles(
    *,
    source_dsn: str,
    source_table_name: str,
    days_threshold: int = 30,
    batch_size: int = 100,
) -> dict[str, Any]:
    """自动标记长期不登录的用户为不活跃
    
    Args:
        days_threshold: 不登录天数阈值（默认30天）
        batch_size: 每批处理数量
    
    Returns:
        处理结果统计
    """
    
    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    
    # 查询长期不登录的用户（状态为 active 或 matched）
    profiles = list_profiles(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        criteria={
            "profile_statuses": ["active", "matched"],
            "last_active_before": cutoff_date,
        },
    )
    
    marked_count = 0
    active_count = 0
    matched_count = 0
    errors = []
    
    # 分批处理
    for i in range(0, len(profiles), batch_size):
        batch = profiles[i:i + batch_size]
        
        for profile in batch:
            try:
                current_status = profile.get("profile_status")
                
                transition_profile_status(
                    profile_id=profile["id"],
                    from_status=current_status,
                    to_status="inactive",
                    reason="auto_inactive",
                    details={
                        "last_active_at": profile.get("last_active_at"),
                        "inactive_days": days_threshold,
                    },
                    source_dsn=source_dsn,
                    source_table_name=source_table_name,
                    actor_type="system",
                )
                
                marked_count += 1
                
                if current_status == "active":
                    active_count += 1
                elif current_status == "matched":
                    matched_count += 1
                    
            except Exception as e:
                errors.append({
                    "profile_id": profile["id"],
                    "error": str(e),
                })
    
    return {
        "status": "completed",
        "marked_count": marked_count,
        "active_to_inactive": active_count,
        "matched_to_inactive": matched_count,
        "total_profiles": len(profiles),
        "errors": errors,
        "cutoff_date": cutoff_date.isoformat(),
        "days_threshold": days_threshold,
    }


def main():
    parser = argparse.ArgumentParser(description="自动标记长期不登录用户为不活跃")
    parser.add_argument("--source", required=True, help="数据源")
    parser.add_argument("--table", default="profiles", help="档案表名")
    parser.add_argument("--days", type=int, default=30, help="不登录天数阈值")
    parser.add_argument("--batch-size", type=int, default=100, help="批处理大小")
    
    args = parser.parse_args()
    
    result = auto_mark_inactive_profiles(
        source_dsn=args.source,
        source_table_name=args.table,
        days_threshold=args.days,
        batch_size=args.batch_size,
    )
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 发送通知（可选）
    if result["marked_count"] > 0:
        send_admin_notification(
            title="自动标记不活跃用户完成",
            message=f"本次标记了 {result['marked_count']} 个用户为不活跃状态",
            details=result,
        )


if __name__ == "__main__":
    main()
```

**定时任务配置**：

```bash
# crontab -e

# 每天凌晨2点：标记30天不登录的用户为 inactive
0 2 * * * cd /path/to/Her && python scripts/auto_mark_inactive_profiles.py --source mysql://user:pass@host/db --days 30 >> logs/inactive_profiles.log 2>&1
```

**大白话解释**：
就像相亲群管理员，每天晚上检查一下，谁超过30天没来群里了，就把他标记为"不活跃"。这样群里推荐的都是真正想找对象的人，不会推荐给那些不来的人。但是这个标记不是永久开除，只要用户一来（登录），自动就恢复为"活跃"了。

---

### 📌 实施点4：匹配后长期不聊天自动恢复

**触发点**：定时任务（每天凌晨执行）

**触发时机**：
- 每天凌晨3点自动检查
- 检查所有 matched 状态的用户
- 查询与匹配对象的聊天记录
- 7天不聊天的用户恢复为 active

**实现位置**：新增脚本 `scripts/auto_resume_inactive_matches.py`

**实现代码**：

```python
# 文件：scripts/auto_resume_inactive_matches.py

import argparse
import json
from datetime import datetime, timedelta
from profile_service import list_profiles, resolve_profile_record
from profile_status_service import transition_profile_status
from chat_service import get_last_chat_time  # 假设的聊天服务

def auto_resume_inactive_matches(
    *,
    source_dsn: str,
    source_table_name: str,
    chat_dsn: str,
    days_threshold: int = 7,
    batch_size: int = 50,
) -> dict[str, Any]:
    """自动恢复匹配后长期不聊天的用户为活跃状态
    
    Args:
        days_threshold: 不聊天天数阈值（默认7天）
        batch_size: 每批处理数量
    
    Returns:
        处理结果统计
    """
    
    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    
    # 查询 matched 状态的用户
    matched_profiles = list_profiles(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        criteria={"profile_statuses": ["matched"]},
    )
    
    resumed_count = 0
    pairs_resumed = []
    errors = []
    
    # 分批处理
    for i in range(0, len(matched_profiles), batch_size):
        batch = matched_profiles[i:i + batch_size]
        
        for profile in batch:
            try:
                # 获取匹配对象ID（从匹配详情中获取）
                match_details = profile.get("match_details") or {}
                matched_with_id = match_details.get("matched_with")
                
                if not matched_with_id:
                    continue
                
                # 查询双方最后聊天时间
                last_chat_time = get_last_chat_time(
                    user_a_id=profile["id"],
                    user_b_id=matched_with_id,
                    chat_dsn=chat_dsn,
                )
                
                # 如果超过7天没聊天，双方都恢复为 active
                if last_chat_time and last_chat_time < cutoff_date:
                    
                    # 查询匹配对象的状态
                    matched_with_record = resolve_profile_record(
                        self_id=matched_with_id,
                        records=[],
                        source_dsn=source_dsn,
                        source_table_name=source_table_name,
                    )
                    
                    # 双方都恢复为 active（如果还是 matched）
                    if matched_with_record.get("profile_status") == "matched":
                        # 用户A恢复
                        transition_profile_status(
                            profile_id=profile["id"],
                            from_status="matched",
                            to_status="active",
                            reason="match_inactive",
                            details={
                                "previous_match": matched_with_id,
                                "last_chat_time": last_chat_time.isoformat(),
                                "inactive_days": days_threshold,
                            },
                            source_dsn=source_dsn,
                            source_table_name=source_table_name,
                            actor_type="system",
                        )
                        
                        # 用户B恢复
                        transition_profile_status(
                            profile_id=matched_with_id,
                            from_status="matched",
                            to_status="active",
                            reason="match_inactive",
                            details={
                                "previous_match": profile["id"],
                                "last_chat_time": last_chat_time.isoformat(),
                                "inactive_days": days_threshold,
                            },
                            source_dsn=source_dsn,
                            source_table_name=source_table_name,
                            actor_type="system",
                        )
                        
                        resumed_count += 2
                        pairs_resumed.append({
                            "user_a": profile["id"],
                            "user_b": matched_with_id,
                            "last_chat": last_chat_time.isoformat(),
                        })
                        
            except Exception as e:
                errors.append({
                    "profile_id": profile["id"],
                    "error": str(e),
                })
    
    return {
        "status": "completed",
        "resumed_count": resumed_count,
        "pairs_resumed": pairs_resumed,
        "total_matched_profiles": len(matched_profiles),
        "errors": errors,
        "cutoff_date": cutoff_date.isoformat(),
        "days_threshold": days_threshold,
    }


def main():
    parser = argparse.ArgumentParser(description="自动恢复匹配后长期不聊天的用户")
    parser.add_argument("--source", required=True, help="档案数据源")
    parser.add_argument("--table", default="profiles", help="档案表名")
    parser.add_argument("--chat-source", required=True, help="聊天数据源")
    parser.add_argument("--days", type=int, default=7, help="不聊天天数阈值")
    parser.add_argument("--batch-size", type=int, default=50, help="批处理大小")
    
    args = parser.parse_args()
    
    result = auto_resume_inactive_matches(
        source_dsn=args.source,
        source_table_name=args.table,
        chat_dsn=args.chat_source,
        days_threshold=args.days,
        batch_size=args.batch_size,
    )
    
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    # 发送通知（可选）
    if result["resumed_count"] > 0:
        send_admin_notification(
            title="匹配不活跃自动恢复完成",
            message=f"本次恢复了 {result['resumed_count']} 个用户为活跃状态",
            details=result,
        )


if __name__ == "__main__":
    main()
```

**定时任务配置**：

```bash
# crontab -e

# 每天凌晨3点：检查匹配双方7天不聊天的恢复为 active
0 3 * * * cd /path/to/Her && python scripts/auto_resume_inactive_matches.py --source mysql://... --chat-source mysql://... --days 7 >> logs/resume_matches.log 2>&1
```

**大白话解释**：
就像相亲群里，小明和小红匹配成功了，但是如果两个人7天都不说话，说明没缘分、没兴趣。群主自动把两个人改回"正在找对象"状态，让他们可以重新找其他人。这样用户不会被一个不说话的匹配"卡住"，找不到新对象。

---

## 核心服务：状态转换统一入口

### 状态转换服务

**文件**：`profile_status_service.py`

**核心代码**：

```python
# 文件：profile_status_service.py

"""档案状态转换服务（简化版）

统一管理 profile_status 的状态转换逻辑：
- 状态转换规则验证
- 数据库更新
- 审计日志记录
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from profile_service import apply_profile_updates
from profile_status_audit_log import ProfileStatusAuditLog


# 允许的状态转换规则（简化版）
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
        reason: 转换原因
        details: 转换详情
        source_dsn: 数据源
        source_table_name: 档案表名
        actor_type: 操作者类型（system/user/admin）
        actor_id: 操作者ID
    
    Returns:
        转换结果
    
    Raises:
        ValueError: 状态转换规则不允许
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
    }


def _send_transition_notification(
    profile_id: int,
    from_status: str,
    to_status: str,
    reason: str,
    details: dict[str, Any],
) -> None:
    """发送状态转换通知"""
    
    # 匹配成功通知
    if reason == "match_success":
        matched_with = details.get("matched_with")
        send_notification(
            user_id=profile_id,
            title="匹配成功！",
            message=f"您与用户 {matched_with} 匹配成功，档案状态已更新为已匹配",
        )
    
    # 匹配不活跃恢复通知
    if reason == "match_inactive":
        send_notification(
            user_id=profile_id,
            title="匹配关系已结束",
            message="您与匹配对象长期未聊天，档案已恢复为活跃状态，可以重新寻找对象",
        )


def get_status_transition_rules() -> dict[str, set[str]]:
    """获取状态转换规则"""
    return ALLOWED_TRANSITIONS.copy()


def validate_transition(from_status: str, to_status: str) -> bool:
    """验证状态转换是否允许"""
    return to_status in ALLOWED_TRANSITIONS.get(from_status, set())


__all__ = [
    "transition_profile_status",
    "get_status_transition_rules",
    "validate_transition",
]
```

---

### 审计日志服务

**文件**：`profile_status_audit_log.py`

**核心代码**：

```python
# 文件：profile_status_audit_log.py

"""档案状态转换审计日志"""

import json
from datetime import datetime
from typing import Any
from profile_service import _connect_profile_db, release_profile_connection


class ProfileStatusAuditLog:
    """档案状态转换审计日志"""
    
    @staticmethod
    def log_transition(
        *,
        profile_id: int,
        from_status: str,
        to_status: str,
        reason: str,
        details: dict[str, Any],
        actor_type: str = "system",
        actor_id: int | None = None,
        source_dsn: str,
    ) -> None:
        """记录状态转换日志"""
        
        conn = _connect_profile_db(source_dsn, use_pool=False, timeout=5.0)
        
        try:
            sql = """
                INSERT INTO profile_status_audit 
                (profile_id, from_status, to_status, reason, details, actor_type, actor_id, occurred_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            conn.execute(
                sql,
                (
                    profile_id,
                    from_status,
                    to_status,
                    reason,
                    json.dumps(details, ensure_ascii=False),
                    actor_type,
                    actor_id,
                    datetime.now(),
                ),
            )
            conn.commit()
        finally:
            release_profile_connection(source_dsn, conn)


__all__ = ["ProfileStatusAuditLog"]
```

---

## 数据库表设计

### profile_status_audit 表（审计日志）

```sql
-- 文件：outer_system_mysql_schema.py

CREATE TABLE profile_status_audit (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    profile_id BIGINT NOT NULL COMMENT '档案ID',
    from_status VARCHAR(20) NOT NULL COMMENT '原状态',
    to_status VARCHAR(20) NOT NULL COMMENT '新状态',
    reason VARCHAR(50) NOT NULL COMMENT '转换原因',
    details JSON COMMENT '转换详情',
    actor_type VARCHAR(20) COMMENT '操作者类型（system/user/admin）',
    actor_id BIGINT COMMENT '操作者ID',
    occurred_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '转换时间',
    
    INDEX idx_profile_id_time (profile_id, occurred_at),
    INDEX idx_reason_time (reason, occurred_at),
    INDEX idx_from_to (from_status, to_status),
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='档案状态转换审计日志';
```

---

## 实施计划

### 第1周：核心服务

**任务**：
1. 创建 `profile_status_service.py`（状态转换服务）
2. 创建 `profile_status_audit_log.py`（审计日志）
3. 创建数据库表 `profile_status_audit`
4. 修改状态映射（删除 paused 和 archived，添加 inactive）
5. 编写单元测试

**验收标准**：
- 状态转换逻辑正确
- 审计日志正确记录
- 单元测试覆盖率 > 80%

---

### 第2周：自动转换逻辑

**任务**：
1. 实现登录自动恢复逻辑（修改 `profile_service/api.py`）
2. 实现匹配成功自动更新逻辑（修改 `match_domain/ledger.py`）
3. 实现长期不登录标记脚本（新增 `scripts/auto_mark_inactive_profiles.py`）
4. 实现匹配不聊天恢复脚本（新增 `scripts/auto_resume_inactive_matches.py`）
5. 配置定时任务

**验收标准**：
- 用户登录自动恢复为 active
- 匹配成功自动改为 matched
- 30天不登录自动标记为 inactive
- 7天不聊天自动恢复为 active

---

### 第3周：前端显示

**任务**：
1. 修改前端状态显示（active=活跃、matched=已匹配、inactive=不活跃）
2. 添加状态转换提示文案
3. 编写API文档

**验收标准**：
- 前端正确显示中文状态
- 用户能看到状态变化提示

---

### 第4周：测试与发布

**任务**：
1. 编写集成测试
2. 编写端到端测试
3. 灰度发布方案
4. 监控指标设计

**验收标准**：
- 所有测试通过
- 灰度发布方案完整
- 监控指标可追踪

---

## 监控指标

### 业务指标

```
• active_users_count: 当前活跃用户数
• matched_users_count: 当前已匹配用户数
• inactive_users_count: 当前不活跃用户数

• status_transition_count_{from_to}: 各转换路径的数量
• user_login_resume_count: 用户登录恢复次数
• match_success_count: 匹配成功次数
• auto_inactive_count: 自动标记不活跃次数
• match_inactive_resume_count: 匹配不活跃恢复次数
```

### 系统指标

```
• status_transition_latency: 状态转换耗时
• audit_log_write_latency: 审计日志写入耗时
• auto_mark_script_duration: 自动标记脚本执行时长
• auto_resume_script_duration: 自动恢复脚本执行时长
```

---

## 预期收益

### ✅ 用户体验提升

- **登录就是活跃**：用户不需要手动操作，登录就自动活跃
- **匹配自动更新**：匹配成功自动改为已匹配，不需要用户改
- **不活跃只是标记**：30天不来只是标记，一登录就恢复，不会被"开除"
- **匹配不聊天自动恢复**：7天不聊天就自动恢复，不会被"卡住"

---

### ✅ 系统质量提升

- **推荐池干净**：只有活跃用户，不推荐给不来的人
- **自动管理**：系统自动管理状态，减少人工干预
- **有日志追踪**：每次状态变化都有记录，便于统计和排查

---

### ✅ 业务数据提升

- **减少用户流失**：不活跃用户登录就能恢复，不会永久流失
- **提高匹配成功率**：推荐的都是真正想找对象的人
- **提高用户满意度**：系统自动管理，不打扰用户

---

## 大白话总结

### 状态转换逻辑（一句话版）

**登录就是活跃，匹配成功就是已匹配，长期不登录标记不活跃，登录就恢复，匹配不聊天自动恢复**

---

### 为什么这个方案更好

#### ✅ 简单

只需要3个状态：active、matched、inactive

不需要 paused（手动暂停）、archived（永久归档）

---

#### ✅ 人性化

- **不活跃只是标记**：用户一登录就恢复，不会被"开除"
- **匹配不聊天自动恢复**：不会被一个不说话的匹配"卡住"
- **自动管理**：用户不需要手动操作，系统自动搞定

---

#### ✅ 符合业务

- **登录就是活跃**：真正想找对象的人才会登录
- **30天不登录标记**：30天足够判断用户是否还在用
- **7天不聊天恢复**：7天不聊天说明没缘分，可以重新找

---

### 实际效果对比

**场景1：小明工作忙**

我的复杂方案：
- 工作忙 → 需要点击"暂停"按钮 → 手动恢复 → 累

你的简单方案：
- 工作忙 → 不登录 → 30天后自动标记不活跃 → 一登录就恢复 → 简单

---

**场景2：小明匹配成功但不聊天**

我的复杂方案：
- 匹配成功 → matched → 需要分手操作 → 不知道怎么分手 → 卡住

你的简单方案：
- 匹配成功 → matched → 7天不聊天 → 自动恢复为活跃 → 可以重新找 → 不卡

---

**场景3：小刚半年不来**

我的复杂方案：
- 半年不来 → 归档 → 需要联系客服恢复 → 永久离开

你的简单方案：
- 半年不来 → 不活跃 → 一登录就恢复 → 可能回来 → 不流失

---

## 核心思想

**让系统自动管理状态，减少用户手动操作，更智能更人性化！**

用户只需要做两件事：
1. **登录**（状态自动活跃）
2. **聊天**（保持匹配状态）

其他都由系统自动管理！

---

## 代码位置规划

```
新增文件：
├─ profile_status_service.py （核心服务）
├─ profile_status_audit_log.py （审计日志）
├─ scripts/auto_mark_inactive_profiles.py （自动标记脚本）
└─ scripts/auto_resume_inactive_matches.py （自动恢复脚本）

修改文件：
├─ match_domain/ledger.py （添加匹配成功状态转换）
├─ profile_service/api.py （添加登录状态转换）
├─ outer_system_mysql_schema.py （添加审计表）
└─ partner_search/search_matching.py （已修改：状态显示中文）

数据库：
├─ profiles 表：profile_status 字段（已有，修改状态值）
└─ profile_status_audit 表：状态转换日志（新增）
```

---

## 总结

这个方案基于你的想法，核心是：

**登录即活跃、匹配即已匹配、长期不登录标记不活跃、登录恢复、匹配不聊天恢复**

实施后：
- ✅ 系统自动管理状态
- ✅ 用户不需要手动操作
- ✅ 推荐池干净（只有活跃用户）
- ✅ 不活跃用户登录就能恢复（减少流失）
- ✅ 匹配不聊天自动恢复（不被"卡住"）

**核心思想：简单、智能、人性化！**