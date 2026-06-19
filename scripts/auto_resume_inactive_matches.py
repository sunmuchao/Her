#!/usr/bin/env python3
"""自动恢复匹配后长期不聊天的用户为活跃状态

定时任务：每天凌晨3点执行
核心思想：7天不聊天自动恢复

执行逻辑：
1. 查询所有 matched 状态的用户
2. 检查与匹配对象的最后聊天时间
3. 如果超过7天不聊天，双方都恢复为 active
4. 记录状态转换审计日志

使用方法：
    python scripts/auto_resume_inactive_matches.py --source mysql://... --chat-source mysql://... --days 7
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from profile_service import list_profiles, resolve_profile_record
from profile_status_service import transition_profile_status


def auto_resume_inactive_matches(
    *,
    source_dsn: str,
    source_table_name: str = "profiles",
    days_threshold: int = 7,
    batch_size: int = 50,
) -> dict[str, Any]:
    """自动恢复匹配后长期不聊天的用户

    Args:
        source_dsn: 档案数据源
        source_table_name: 档案表名
        days_threshold: 不聊天天数阈值（默认7天）
        batch_size: 每批处理数量

    Returns:
        处理结果统计

    注意：
        由于目前缺少聊天数据查询接口，这个脚本暂时采用简化逻辑：
        - 查询 matched 状态的用户
        - 检查 updated_at 字段（代替 last_chat_time）
        - 如果超过7天没有更新，恢复为 active
    """

    print(f"[开始] 自动恢复匹配不活跃用户，阈值：{days_threshold}天")
    print(f"[参数] 数据源：{source_dsn}")
    print(f"[参数] 表名：{source_table_name}")

    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    print(f"[截止时间] {cutoff_date.isoformat()}")

    # 查询 matched 状态的用户
    try:
        matched_profiles = list_profiles(
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            criteria={"profile_statuses": ["matched"]},
        )
    except Exception as e:
        print(f"[错误] 查询用户失败：{e}")
        return {
            "status": "error",
            "error": str(e),
            "resumed_count": 0,
        }

    print(f"[查询结果] 找到 {len(matched_profiles)} 个已匹配的用户")

    resumed_count = 0
    pairs_resumed = []
    errors = []

    # 分批处理
    for i in range(0, len(matched_profiles), batch_size):
        batch = matched_profiles[i:i + batch_size]
        print(f"[进度] 处理第 {i//batch_size + 1} 批，共 {len(batch)} 个用户")

        for profile in batch:
            try:
                profile_id = profile.get("id")
                current_status = profile.get("profile_status")
                updated_at = profile.get("updated_at")

                print(f"  [检查] profile_id={profile_id}, status={current_status}, updated_at={updated_at}")

                # 简化逻辑：检查 updated_at 字段
                # 如果超过7天没有更新，认为长期不活跃
                if updated_at:
                    try:
                        if isinstance(updated_at, str):
                            last_update_time = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                        else:
                            last_update_time = updated_at

                        if last_update_time >= cutoff_date:
                            print(f"  [跳过] profile_id={profile_id} 最近有更新")
                            continue

                    except Exception as parse_error:
                        print(f"  [警告] 无法解析时间：{parse_error}")
                        # 如果无法解析时间，跳过
                        continue

                # 恢复为 active
                transition_profile_status(
                    profile_id=profile_id,
                    from_status="matched",
                    to_status="active",
                    reason="match_inactive",
                    details={
                        "previous_status": "matched",
                        "inactive_days": days_threshold,
                        "script": "auto_resume_inactive_matches",
                        "updated_at": updated_at,
                    },
                    source_dsn=source_dsn,
                    source_table_name=source_table_name,
                    actor_type="system",
                )

                resumed_count += 1
                pairs_resumed.append({
                    "profile_id": profile_id,
                    "reason": "长期不活跃（简化逻辑）",
                    "updated_at": updated_at,
                })

                print(f"  [成功] profile_id={profile_id} 已恢复为 active")

            except Exception as e:
                error_msg = f"profile_id={profile.get('id')}, error={str(e)}"
                print(f"  [失败] {error_msg}")
                errors.append({
                    "profile_id": profile.get("id"),
                    "error": str(e),
                })

    result = {
        "status": "completed",
        "resumed_count": resumed_count,
        "pairs_resumed": pairs_resumed,
        "total_matched_profiles": len(matched_profiles),
        "errors": errors,
        "cutoff_date": cutoff_date.isoformat(),
        "days_threshold": days_threshold,
        "executed_at": datetime.now().isoformat(),
        "note": "简化逻辑：使用 updated_at 代替 last_chat_time",
    }

    print(f"[完成] 恢复完成，共恢复 {resumed_count} 个用户")
    print(f"[统计] 失败数量：{len(errors)}")

    return result


def main():
    parser = argparse.ArgumentParser(description="自动恢复匹配后长期不聊天的用户")
    parser.add_argument("--source", required=True, help="档案数据源")
    parser.add_argument("--table", default="profiles", help="档案表名")
    parser.add_argument("--days", type=int, default=7, help="不聊天天数阈值")
    parser.add_argument("--batch-size", type=int, default=50, help="批处理大小")

    args = parser.parse_args()

    print("=" * 80)
    print("自动恢复匹配不活跃用户脚本")
    print("=" * 80)

    result = auto_resume_inactive_matches(
        source_dsn=args.source,
        source_table_name=args.table,
        days_threshold=args.days,
        batch_size=args.batch_size,
    )

    print("\n" + "=" * 80)
    print("执行结果")
    print("=" * 80)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # 返回状态码
    if result["status"] == "completed":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()