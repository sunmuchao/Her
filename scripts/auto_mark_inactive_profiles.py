#!/usr/bin/env python3
"""自动标记长期不登录用户为不活跃状态

定时任务：每天凌晨2点执行
核心思想：30天不登录标记为不活跃

执行逻辑：
1. 查询所有 active 和 matched 状态的用户
2. 检查 last_active_at 字段
3. 如果超过30天不登录，标记为 inactive
4. 记录状态转换审计日志

使用方法：
    python scripts/auto_mark_inactive_profiles.py --source mysql://user:pass@host/db --days 30
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from profile_service import list_profiles
from profile_status_service import transition_profile_status


def auto_mark_inactive_profiles(
    *,
    source_dsn: str,
    source_table_name: str = "profiles",
    days_threshold: int = 30,
    batch_size: int = 100,
) -> dict[str, Any]:
    """自动标记长期不登录的用户为不活跃

    Args:
        source_dsn: 数据源
        source_table_name: 档案表名
        days_threshold: 不登录天数阈值（默认30天）
        batch_size: 每批处理数量

    Returns:
        处理结果统计
    """

    print(f"[开始] 自动标记不活跃用户，阈值：{days_threshold}天")
    print(f"[参数] 数据源：{source_dsn}")
    print(f"[参数] 表名：{source_table_name}")

    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    print(f"[截止时间] {cutoff_date.isoformat()}")

    # 查询长期不登录的用户（状态为 active 或 matched）
    try:
        profiles = list_profiles(
            source_dsn=source_dsn,
            source_table_name=source_table_name,
            criteria={
                "profile_statuses": ["active", "matched"],
                "last_active_before": cutoff_date,
            },
        )
    except Exception as e:
        print(f"[错误] 查询用户失败：{e}")
        return {
            "status": "error",
            "error": str(e),
            "marked_count": 0,
        }

    print(f"[查询结果] 找到 {len(profiles)} 个长期不登录的用户")

    marked_count = 0
    active_to_inactive = 0
    matched_to_inactive = 0
    errors = []

    # 分批处理
    for i in range(0, len(profiles), batch_size):
        batch = profiles[i:i + batch_size]
        print(f"[进度] 处理第 {i//batch_size + 1} 批，共 {len(batch)} 个用户")

        for profile in batch:
            try:
                current_status = profile.get("profile_status")
                profile_id = profile.get("id")
                last_active_at = profile.get("last_active_at")

                print(f"  [处理] profile_id={profile_id}, status={current_status}, last_active={last_active_at}")

                # 执行状态转换
                transition_profile_status(
                    profile_id=profile_id,
                    from_status=current_status,
                    to_status="inactive",
                    reason="auto_inactive",
                    details={
                        "last_active_at": last_active_at,
                        "inactive_days": days_threshold,
                        "script": "auto_mark_inactive_profiles",
                    },
                    source_dsn=source_dsn,
                    source_table_name=source_table_name,
                    actor_type="system",
                )

                marked_count += 1

                if current_status == "active":
                    active_to_inactive += 1
                elif current_status == "matched":
                    matched_to_inactive += 1

                print(f"  [成功] profile_id={profile_id} 已标记为 inactive")

            except Exception as e:
                error_msg = f"profile_id={profile.get('id')}, error={str(e)}"
                print(f"  [失败] {error_msg}")
                errors.append({
                    "profile_id": profile.get("id"),
                    "error": str(e),
                })

    result = {
        "status": "completed",
        "marked_count": marked_count,
        "active_to_inactive": active_to_inactive,
        "matched_to_inactive": matched_to_inactive,
        "total_profiles": len(profiles),
        "errors": errors,
        "cutoff_date": cutoff_date.isoformat(),
        "days_threshold": days_threshold,
        "executed_at": datetime.now().isoformat(),
    }

    print(f"[完成] 标记完成，共标记 {marked_count} 个用户")
    print(f"[统计] active→inactive: {active_to_inactive}")
    print(f"[统计] matched→inactive: {matched_to_inactive}")
    print(f"[统计] 失败数量: {len(errors)}")

    return result


def main():
    parser = argparse.ArgumentParser(description="自动标记长期不登录用户为不活跃")
    parser.add_argument("--source", required=True, help="数据源（如：mysql://user:pass@host/db）")
    parser.add_argument("--table", default="profiles", help="档案表名（默认：profiles）")
    parser.add_argument("--days", type=int, default=30, help="不登录天数阈值（默认：30天）")
    parser.add_argument("--batch-size", type=int, default=100, help="批处理大小（默认：100）")

    args = parser.parse_args()

    print("=" * 80)
    print("自动标记不活跃用户脚本")
    print("=" * 80)

    result = auto_mark_inactive_profiles(
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