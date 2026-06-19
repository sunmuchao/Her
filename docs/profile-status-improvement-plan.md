---
name: profile-status-improvement-plan
description: 档案状态自动转换改进方案：解决当前缺少的状态转换逻辑，包括匹配成功自动更新、长期不活跃归档、用户手动操作等
metadata:
  type: project
---

# 档案状态自动转换改进方案

## 问题分析

### 当前存在的问题

#### ❌ 问题1：缺少匹配成功自动更新逻辑

**现象**：用户匹配成功后，profile_status 没有自动改为 matched

**影响**：
- matched 用户仍在搜索池中，干扰其他用户
- 系统继续推荐给已匹配用户，打扰他们
- 用户体验差：明明已经找到对象，系统还在推新人

**根因**：缺少双向匹配成功后的状态转换触发点

---

#### ❌ 问题2：缺少长期不活跃自动归档逻辑

**现象**：长期不登录的用户档案仍然在系统中，占用资源

**影响**：
- 推荐池混入大量不活跃用户
- 搜索结果包含半年不来的人，降低推荐质量
- 数据库资源浪费

**根因**：缺少定时任务检测和自动归档逻辑

---

#### ❌ 问题3：缺少匹配关系结束恢复逻辑

**现象**：用户分手后，profile_status 仍为 matched，无法继续找对象

**影响**：
- 用户分手后系统不再推荐，用户找不到新对象
- 用户可能不知道需要手动改状态
- 用户流失：分手后找不到新人就离开了

**根因**：缺少匹配关系结束后的状态恢复触发点

---

#### ❌ 问题4：缺少用户手动操作接口

**现象**：用户无法方便地暂停/恢复档案

**影响**：
- 用户工作忙时无法暂停档案，只能注销
- 用户想恢复时找不到入口
- 用户流失：工作忙就永久离开平台

**根因**：缺少前端接口和后端服务

---

## 改进方案

### 方案总览

```
┌─────────────────────────────────────────────────────────────┐
│                    状态转换触发点                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【自动触发】                                                │
│  • 匹配成功 → 自动改为 matched                              │
│  • 匹配结束 → 自动恢复为 active                             │
│  • 长期不活跃 → 自动归档为 archived                         │
│                                                             │
│  【手动触发】                                                │
│  • 用户点击暂停 → 改为 paused                               │
│  • 用户点击恢复 → 改为 active                               │
│  • 用户注销 → 改为 archived                                 │
│  • 管理员封禁 → 改为 archived                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│               ProfileStatusService（新增）                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  功能：                                                     │
│  • 状态转换逻辑（验证规则）                                  │
│  • 状态转换审计日志                                          │
│  • 状态转换通知                                              │
│  • 状态转换统计                                              │
│                                                             │
│  核心方法：                                                 │
│  • transition_status(profile_id, from_status, to_status)   │
│  • auto_match_success(profile_id)                          │
│  • auto_match_end(profile_id)                              │
│  • auto_archive_inactive(days_threshold=90)                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│                  数据库更新                                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  • profiles 表：profile_status 字段更新                     │
│  • profile_status_audit 表：状态转换日志（新增）            │
│  • profile_status_stats 表：状态统计（新增）                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 具体改进点

#### ✅ 改进1：匹配成功自动更新为 matched

**触发点**：match_domain 双向匹配检测逻辑

**实现位置**：
- match_domain/ledger.py - 添加状态转换调用
- match_domain/model.py - RelationStatus.MATCHED 触发 profile_status 更新

**代码实现**：

```python
# 文件：match_domain/ledger.py

def apply_match_success_status_transition(
    *,
    owner_id: int,
    target_id: int,
    source_dsn: str,
    source_table_name: str,
) -> None:
    """匹配成功后自动更新双方档案状态为 matched"""
    
    # 导入 profile_status_service（新增服务）
    from profile_status_service import transition_profile_status
    
    # 双方都改为 matched
    transition_profile_status(
        profile_id=owner_id,
        from_status="active",
        to_status="matched",
        reason="match_success",
        details={"matched_with": target_id},
        source_dsn=source_dsn,
        source_table_name=source_table_name,
    )
    
    transition_profile_status(
        profile_id=target_id,
        from_status="active",
        to_status="matched",
        reason="match_success",
        details={"matched_with": owner_id},
        source_dsn=source_dsn,
        source_table_name=source_table_name,
    )


# 在 relation_status_from_row_snapshot 函数中调用
def relation_status_from_row_snapshot(...) -> tuple[RelationStatus, str | None]:
    ...
    if ds == "escalated_to_case":
        if reason == "proxy_intro_handoff_completed":
            # 匹配成功！自动更新档案状态
            apply_match_success_status_transition(...)
            return RelationStatus.CLOSED, None
        return RelationStatus.PROXY_INTRO_ACTIVE, None
    ...
```

**大白话解释**：
就像相亲群里，小明和小红两个人都同意了，群主自动把两个人的状态改成"已经有对象了"，不需要他们自己改。这样系统就不会再给他们推新人，也不会把他们的资料推给别人。

---

#### ✅ 改进2：长期不活跃自动归档

**触发点**：定时任务（每天凌晨执行）

**实现位置**：新增 scripts/auto_archive_inactive_profiles.py

**代码实现**：

```python
# 文件：scripts/auto_archive_inactive_profiles.py

import argparse
from datetime import datetime, timedelta
from profile_service import list_profiles
from profile_status_service import transition_profile_status

def auto_archive_inactive_profiles(
    *,
    source_dsn: str,
    source_table_name: str,
    days_threshold: int = 90,
    batch_size: int = 100,
) -> dict[str, Any]:
    """自动归档长期不活跃的用户档案
    
    Args:
        days_threshold: 不活跃天数阈值（默认90天）
        batch_size: 每批处理数量（避免一次性更新太多）
    
    Returns:
        处理结果统计
    """
    
    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    
    # 查询长期不活跃的用户（状态为 active 或 paused）
    profiles = list_profiles(
        source_dsn=source_dsn,
        source_table_name=source_table_name,
        criteria={
            "profile_statuses": ["active", "paused"],
            "last_active_before": cutoff_date,
        },
    )
    
    archived_count = 0
    errors = []
    
    # 分批处理
    for i in range(0, len(profiles), batch_size):
        batch = profiles[i:i + batch_size]
        for profile in batch:
            try:
                transition_profile_status(
                    profile_id=profile["id"],
                    from_status=profile["profile_status"],
                    to_status="archived",
                    reason="auto_archive_inactive",
                    details={
                        "last_active_at": profile.get("last_active_at"),
                        "inactive_days": days_threshold,
                    },
                    source_dsn=source_dsn,
                    source_table_name=source_table_name,
                )
                archived_count += 1
            except Exception as e:
                errors.append({"profile_id": profile["id"], "error": str(e)})
    
    return {
        "status": "completed",
        "archived_count": archived_count,
        "total_profiles": len(profiles),
        "errors": errors,
        "cutoff_date": cutoff_date.isoformat(),
    }


def main():
    parser = argparse.ArgumentParser(description="自动归档长期不活跃档案")
    parser.add_argument("--source", required=True, help="数据源")
    parser.add_argument("--table", default="profiles", help="档案表名")
    parser.add_argument("--days", type=int, default=90, help="不活跃天数阈值")
    parser.add_argument("--batch-size", type=int, default=100, help="批处理大小")
    
    args = parser.parse_args()
    
    result = auto_archive_inactive_profiles(
        source_dsn=args.source,
        source_table_name=args.table,
        days_threshold=args.days,
        batch_size=args.batch_size,
    )
    
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

**定时任务配置**：

```bash
# crontab -e
# 每天凌晨2点执行
0 2 * * * cd /path/to/Her && python scripts/auto_archive_inactive_profiles.py --source mysql://... --days 90
```

**大白话解释**：
就像相亲群管理员，每天晚上检查一下，谁超过3个月没来了，就把他们的资料收起来（归档）。这样群里推荐的都是真正想找对象的人，不会推荐给那些已经不来的人。

---

#### ✅ 改进3：匹配关系结束自动恢复为 active

**触发点**：match_domain 关系结束逻辑

**实现位置**：
- match_domain/ledger.py - RelationStatus.CLOSED 触发状态恢复
- match_domain/model.py - 添加关系结束检测

**代码实现**：

```python
# 文件：match_domain/ledger.py

def apply_match_end_status_transition(
    *,
    owner_id: int,
    target_id: int,
    source_dsn: str,
    source_table_name: str,
) -> None:
    """匹配关系结束后自动恢复双方档案状态为 active"""
    
    from profile_status_service import transition_profile_status
    
    # 查询当前状态（只有 matched 才能恢复）
    from profile_service import resolve_profile_record
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
    
    # 只有 matched 状态才恢复为 active
    if owner_record.get("profile_status") == "matched":
        transition_profile_status(
            profile_id=owner_id,
            from_status="matched",
            to_status="active",
            reason="match_end",
            details={"previous_match": target_id},
            source_dsn=source_dsn,
            source_table_name=source_table_name,
        )
    
    if target_record.get("profile_status") == "matched":
        transition_profile_status(
            profile_id=target_id,
            from_status="matched",
            to_status="active",
            reason="match_end",
            details={"previous_match": owner_id},
            source_dsn=source_dsn,
            source_table_name=source_table_name,
        )


# 在关系结束事件中调用
def replay_ledger_events(events: list[MatchEvent]) -> dict[str, Any]:
    """重放事件日志，处理状态转换"""
    
    for event in sort_ledger_events(events):
        if event.event_type == "relation_state_revision":
            payload = event.payload
            if payload.get("status") == RelationStatus.CLOSED.value:
                # 关系结束，自动恢复档案状态
                apply_match_end_status_transition(
                    owner_id=int(event.aggregate_id.split(":")[1]),
                    target_id=int(payload.get("target_id")),
                    source_dsn=payload.get("source_dsn"),
                    source_table_name=payload.get("source_table_name"),
                )
```

**大白话解释**：
就像相亲群里，小明和小红分手了，群主自动把两个人的状态改回"正在找对象"，这样他们可以重新找人，系统会重新给他们推荐新人。

---

#### ✅ 改进4：用户手动暂停/恢复接口

**触发点**：前端用户操作

**实现位置**：
- 前端：新增暂停/恢复按钮
- 后端：新增 HTTP API 接口
- 数据库：使用现有 apply_profile_updates 函数

**前端实现**：

```tsx
// 文件：frontend/her-app/components/profile/profile-status-control.tsx

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'

interface ProfileStatusControlProps {
  profileId: number
  currentStatus: 'active' | 'matched' | 'paused' | 'archived'
  onStatusChange?: (newStatus: string) => void
}

export function ProfileStatusControl({
  profileId,
  currentStatus,
  onStatusChange,
}: ProfileStatusControlProps) {
  const { toast } = useToast()
  const [loading, setLoading] = useState(false)

  const handlePause = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/profile/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_id: profileId,
          status: 'paused',
        }),
      })

      const data = await response.json()

      if (data.status === 'success') {
        toast({
          title: '档案已暂停',
          description: '您的档案已暂停展示，需要恢复时请点击"恢复档案"按钮',
        })
        onStatusChange?.('paused')
      } else {
        toast({
          title: '操作失败',
          description: data.message || '暂停档案失败，请稍后重试',
          variant: 'destructive',
        })
      }
    } catch (error) {
      toast({
        title: '网络错误',
        description: '请检查网络连接后重试',
        variant: 'destructive',
      })
    } finally {
      setLoading(false)
    }
  }

  const handleResume = async () => {
    setLoading(true)
    try {
      const response = await fetch('/api/profile/status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          profile_id: profileId,
          status: 'active',
        }),
      })

      const data = await response.json()

      if (data.status === 'success') {
        toast({
          title: '档案已恢复',
          description: '您的档案已恢复展示，系统将开始为您推荐候选人',
        })
        onStatusChange?.('active')
      } else {
        toast({
          title: '操作失败',
          description: data.message || '恢复档案失败，请稍后重试',
          variant: 'destructive',
        })
      }
    } catch (error) {
      toast({
        title: '网络错误',
        description: '请检查网络连接后重试',
        variant: 'destructive',
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex gap-2">
      {currentStatus === 'active' && (
        <Button
          onClick={handlePause}
          disabled={loading}
          variant="outline"
          className="text-yellow-600 border-yellow-600 hover:bg-yellow-50"
        >
          {loading ? '处理中...' : '暂停档案'}
        </Button>
      )}

      {currentStatus === 'paused' && (
        <Button
          onClick={handleResume}
          disabled={loading}
          variant="outline"
          className="text-green-600 border-green-600 hover:bg-green-50"
        >
          {loading ? '处理中...' : '恢复档案'}
        </Button>
      )}

      {currentStatus === 'matched' && (
        <div className="text-sm text-muted-foreground">
          您已匹配成功，档案已暂停展示。如需恢复寻找，请联系客服或等待关系结束后自动恢复。
        </div>
      )}

      {currentStatus === 'archived' && (
        <div className="text-sm text-muted-foreground">
          您的档案已归档，如需恢复请联系客服。
        </div>
      )}
    </div>
  )
}
```

**后端API实现**：

```python
# 文件：external-systems/partner-http-gateway/profile_status_service.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal
from profile_service import apply_profile_updates
from profile_status_service import transition_profile_status

router = APIRouter(prefix="/api/profile", tags=["profile-status"])


class UpdateStatusRequest(BaseModel):
    profile_id: int
    status: Literal["active", "paused"]
    reason: str | None = None


class UpdateStatusResponse(BaseModel):
    status: str
    message: str
    profile_id: int
    new_status: str
    previous_status: str


@router.post("/status", response_model=UpdateStatusResponse)
async def update_profile_status(request: UpdateStatusRequest):
    """用户手动更新档案状态
    
    允许的转换：
    - active → paused（用户主动暂停）
    - paused → active（用户恢复档案）
    """
    
    # 获取当前状态
    from profile_service import resolve_profile_record
    
    source_dsn = "mysql://..."  # 从配置读取
    source_table_name = "profiles"
    
    current_record = resolve_profile_record(
        self_id=request.profile_id,
        records=[],
        source_dsn=source_dsn,
        source_table_name=source_table_name,
    )
    
    current_status = current_record.get("profile_status")
    
    # 验证转换规则
    if current_status == request.status:
        raise HTTPException(
            status_code=400,
            detail=f"档案状态已经是 {request.status}",
        )
    
    # 只允许 active ↔ paused 的手动转换
    allowed_manual_transitions = {
        ("active", "paused"),
        ("paused", "active"),
    }
    
    if (current_status, request.status) not in allowed_manual_transitions:
        raise HTTPException(
            status_code=400,
            detail=f"不允许从 {current_status} 手动改为 {request.status}",
        )
    
    # 执行状态转换
    try:
        result = transition_profile_status(
            profile_id=request.profile_id,
            from_status=current_status,
            to_status=request.status,
            reason=request.reason or "user_manual",
            details={},
            source_dsn=source_dsn,
            source_table_name=source_table_name,
        )
        
        return UpdateStatusResponse(
            status="success",
            message=f"档案状态已更新为 {request.status}",
            profile_id=request.profile_id,
            new_status=request.status,
            previous_status=current_status,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"状态更新失败: {str(e)}",
        )
```

**大白话解释**：
就像相亲群里，给每个用户加两个按钮："暂停档案"和"恢复档案"。用户工作忙的时候点暂停，档案就不展示了；等忙完了点恢复，档案又重新开始推荐。不用注销账号，随时可以回来。

---

#### ✅ 改进5：状态转换审计日志

**目的**：记录所有状态转换，便于追踪和统计

**实现**：新增数据库表 profile_status_audit

**数据库表设计**：

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

**日志记录服务**：

```python
# 文件：profile_status_service.py

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
        
        import json
        from datetime import datetime
        
        # 连接数据库
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
```

**大白话解释**：
就像相亲群的管理日志，记录每个人状态变化的原因和时间。比如：
- 小明 2024-06-20 从"正在找"改成"暂停"，原因是"用户手动"
- 小红 2024-06-25 从"正在找"改成"已匹配"，原因是"匹配成功，和ID123456匹配"
- 小刚 2024-09-01 从"暂停"改成"归档"，原因是"90天不活跃"

这样管理员可以查看统计：这个月有多少人匹配成功？有多少人因为工作忙暂停？有多少人长期不来被归档？

---

#### ✅ 改进6：状态转换核心服务

**目的**：统一的状态转换逻辑，验证规则、更新数据库、记录日志

**实现位置**：新增 profile_status_service.py

**核心服务代码**：

```python
# 文件：profile_status_service.py

"""档案状态转换服务

统一管理 profile_status 的状态转换逻辑：
- 状态转换规则验证
- 数据库更新
- 审计日志记录
- 通知推送
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from profile_service import apply_profile_updates
from profile_status_audit_log import ProfileStatusAuditLog


# 允许的状态转换规则
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "active": {"paused", "matched", "archived"},
    "matched": {"active", "archived"},
    "paused": {"active", "archived"},
    "archived": set(),  # archived 不能转换到其他状态
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
        reason: 转换原因（match_success/match_end/auto_archive/user_manual/admin_action）
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
        updates={"profile_status": to_status},
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
    
    # 4. 推送通知（可选）
    if reason == "match_success":
        _send_match_success_notification(profile_id, details)
    elif reason == "auto_archive_inactive":
        _send_archive_notification(profile_id, details)
    
    return {
        "status": "success",
        "profile_id": profile_id,
        "from_status": from_status,
        "to_status": to_status,
        "reason": reason,
        "occurred_at": datetime.now().isoformat(),
    }


def _send_match_success_notification(profile_id: int, details: dict[str, Any]) -> None:
    """发送匹配成功通知"""
    # TODO: 实现通知推送逻辑
    pass


def _send_archive_notification(profile_id: int, details: dict[str, Any]) -> None:
    """发送归档通知"""
    # TODO: 实现通知推送逻辑
    pass


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

**大白话解释**：
就像相亲群的规则管理员，负责：
1. 检查转换是否允许（比如归档状态不能改回活跃）
2. 更新群成员的状态
3. 在日志里记录这次改动
4. 发通知告诉用户（匹配成功发恭喜，归档发提醒）

---

### 状态转换规则矩阵

```
┌─────────────┬─────────────────────────────────────┐
│ 当前状态     │ 允许转换的目标状态                  │
├─────────────┼─────────────────────────────────────┤
│ active      │ paused, matched, archived           │
│ matched     │ active, archived                    │
│ paused      │ active, archived                    │
│ archived    │ （不允许转换）                      │
└─────────────┴─────────────────────────────────────┘

转换原因分类：
• match_success: 匹配成功（自动）
• match_end: 匹配关系结束（自动）
• auto_archive_inactive: 长期不活跃归档（自动）
• user_manual: 用户手动操作（暂停/恢复）
• admin_action: 管理员操作（封禁/解封）
• user_unregister: 用户注销
```

---

## 实施计划

### Phase 1：核心服务（1周）

**任务**：
1. 创建 profile_status_service.py
2. 创建 profile_status_audit_log.py
3. 创建数据库表 profile_status_audit
4. 编写单元测试

**验收标准**：
- 状态转换逻辑正确
- 审计日志正确记录
- 单元测试覆盖率 > 80%

---

### Phase 2：自动转换逻辑（1周）

**任务**：
1. 实现匹配成功自动更新逻辑
2. 实现匹配关系结束恢复逻辑
3. 实现长期不活跃自动归档脚本
4. 配置定时任务

**验收标准**：
- 匹配成功后双方状态自动改为 matched
- 关系结束后双方状态自动恢复为 active
- 90天不活跃用户自动归档

---

### Phase 3：前端接口（1周）

**任务**：
1. 实现后端 HTTP API 接口
2. 实现前端暂停/恢复按钮
3. 实现前端状态显示
4. 编写API文档

**验收标准**：
- 用户可以手动暂停档案
- 用户可以手动恢复档案
- 前端显示当前状态和操作按钮

---

### Phase 4：测试与灰度发布（1周）

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
• status_transition_success_rate: 状态转换成功率
• status_transition_count_{from_to}: 各转换路径的数量
• auto_match_success_count: 自动匹配成功转换次数
• auto_archive_count: 自动归档次数
• user_manual_pause_count: 用户手动暂停次数
• user_manual_resume_count: 用户手动恢复次数
```

### 系统指标

```
• status_transition_latency: 状态转换耗时
• audit_log_write_latency: 审计日志写入耗时
• auto_archive_script_duration: 自动归档脚本执行时长
```

---

## 预期收益

### ✅ 用户体验提升

- 匹配成功后自动改为 matched，不再收到打扰推荐
- 分手后自动恢复为 active，可以重新找对象
- 工作忙可以随时暂停，不用注销账号

### ✅ 系统质量提升

- 推荐池更干净：只有真正想找对象的人
- 自动清理长期不活跃用户
- 状态转换有审计日志，便于追踪

### ✅ 业务数据提升

- 减少用户流失：分手后可以重新找，工作忙可以暂停
- 提高匹配成功率：推荐的都是活跃用户
- 提高用户满意度：系统不打扰已匹配用户

---

## 大白话总结

### 改进前的问题

就像相亲群没有管理员：
- 两个人都同意了，群主还继续给他们推新人（打扰）
- 两个人分手了，群主不知道，还是不给推新人（用户流失）
- 半年不来的人还在群里占位置（资源浪费）
- 工作忙想休息的人只能退群（流失）

### 改进后的效果

就像相亲群有了智能管理员：

**自动管理**：
- 两个人匹配成功 → 管理员自动把他们改成"已有对象"状态
- 两个人分手了 → 管理员自动改回"正在找对象"，可以重新找人
- 半年不来的人 → 管理员自动把资料收起来归档

**用户自主**：
- 给用户加"暂停档案"按钮 → 工作忙可以暂停，不用退群
- 给用户加"恢复档案"按钮 → 等忙完了可以恢复，继续找人

**记录追踪**：
- 管理员在日志里记录每次状态变化 → 可以统计和追踪
- 知道多少人匹配成功、多少人暂停、多少人归档

**最终效果**：
- 推荐的都是真正想找对象的人（活跃用户）
- 不打扰已经找到对象的人（matched用户）
- 不推荐给不来的人（archived用户）
- 用户可以随时暂停和恢复（自主权）
- 分手后可以重新找对象（减少流失）

---

## 完整的状态转换流程图

```
用户注册
    ↓
[自动] 设置为 active
    ↓
正常使用 → 系统推荐候选人
    ↓
    ├→ [用户手动] 点击暂停 → 改为 paused
    │       ↓
    │   暂停期间（不推荐）
    │       ↓
    │   [用户手动] 点击恢复 → 改回 active
    │
    ├→ [自动] 匹配成功 → 改为 matched
    │       ↓
    │   匹配期间（不推荐）
    │       ↓
    │       ├→ [自动] 关系结束 → 改回 active
    │       └
    │       └→ [自动] 长期不活跃 → 改为 archived
    │
    ├→ [自动] 90天不活跃 → 改为 archived
    │       ↓
    │   归档状态（不推荐，不可恢复）
    │
    └→ [管理员] 违规封禁 → 改为 archived
```

---

## 代码位置规划

```
新增文件：
├─ profile_status_service.py （核心服务）
├─ profile_status_audit_log.py （审计日志）
├─ scripts/auto_archive_inactive_profiles.py （自动归档脚本）
├─ external-systems/partner-http-gateway/profile_status_service.py （HTTP API）
└─ frontend/her-app/components/profile/profile-status-control.tsx （前端组件）

修改文件：
├─ match_domain/ledger.py （添加状态转换调用）
├─ outer_system_mysql_schema.py （添加审计表）
└─ partner_search/search_matching.py （已修改：状态显示中文）

数据库：
├─ profiles 表：profile_status 字段（已有）
└─ profile_status_audit 表：状态转换日志（新增）
```

---

## 总结

这个改进方案解决了当前档案状态转换的所有问题：

1. ✅ 匹配成功自动更新为 matched
2. ✅ 长期不活跃自动归档
3. ✅ 匹配关系结束自动恢复为 active
4. ✅ 用户手动暂停/恢复接口
5. ✅ 状态转换审计日志
6. ✅ 统一的状态转换核心服务

实施后，系统将自动管理用户档案状态，提升用户体验和系统质量，减少用户流失。