"""档案状态转换审计日志

记录所有 profile_status 状态转换事件：
- profile_id: 档案ID
- from_status: 原状态
- to_status: 新状态
- reason: 转换原因
- details: 转换详情
- actor_type: 操作者类型
- actor_id: 操作者ID
- occurred_at: 转换时间

用于：
- 状态转换追踪
- 业务统计分析
- 问题排查定位
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from profile_service.api import _connect_profile_db, release_profile_connection


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
        """记录状态转换日志

        Args:
            profile_id: 档案ID
            from_status: 原状态
            to_status: 新状态
            reason: 转换原因
            details: 转换详情
            actor_type: 操作者类型（system/user/admin）
            actor_id: 操作者ID
            source_dsn: 数据源

        Example:
            >>> ProfileStatusAuditLog.log_transition(
            ...     profile_id=123,
            ...     from_status="active",
            ...     to_status="matched",
            ...     reason="match_success",
            ...     details={"matched_with": 456},
            ...     source_dsn="mysql://...",
            ... )
        """

        conn = _connect_profile_db(source_dsn, use_pool=False, timeout=5.0)

        try:
            # 检查审计表是否存在
            # 如果不存在，跳过日志记录（避免阻塞主流程）
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

                print(f"[审计日志] 记录成功：profile_id={profile_id}, {from_status}→{to_status}, reason={reason}")

            except Exception as e:
                # 如果表不存在或其他错误，只打印警告，不影响主流程
                print(f"[审计日志] 记录失败：{e}")
                # 不抛出异常，避免阻塞状态转换

        finally:
            release_profile_connection(source_dsn, conn)

    @staticmethod
    def query_transitions(
        *,
        profile_id: int | None = None,
        from_status: str | None = None,
        to_status: str | None = None,
        reason: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        source_dsn: str,
    ) -> list[dict[str, Any]]:
        """查询状态转换日志

        Args:
            profile_id: 档案ID（可选）
            from_status: 原状态（可选）
            to_status: 新状态（可选）
            reason: 转换原因（可选）
            start_time: 开始时间（可选）
            end_time: 结束时间（可选）
            limit: 返回数量限制
            source_dsn: 数据源

        Returns:
            状态转换日志列表

        Example:
            >>> logs = ProfileStatusAuditLog.query_transitions(
            ...     profile_id=123,
            ...     source_dsn="mysql://...",
            ... )
        """

        conn = _connect_profile_db(source_dsn, use_pool=False, timeout=5.0)

        try:
            # 构建查询条件
            conditions = []
            params = []

            if profile_id is not None:
                conditions.append("profile_id = ?")
                params.append(profile_id)

            if from_status is not None:
                conditions.append("from_status = ?")
                params.append(from_status)

            if to_status is not None:
                conditions.append("to_status = ?")
                params.append(to_status)

            if reason is not None:
                conditions.append("reason = ?")
                params.append(reason)

            if start_time is not None:
                conditions.append("occurred_at >= ?")
                params.append(start_time)

            if end_time is not None:
                conditions.append("occurred_at <= ?")
                params.append(end_time)

            # 构建SQL
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            sql = f"""
                SELECT id, profile_id, from_status, to_status, reason, details, actor_type, actor_id, occurred_at
                FROM profile_status_audit
                WHERE {where_clause}
                ORDER BY occurred_at DESC
                LIMIT ?
            """
            params.append(limit)

            results = conn.execute(sql, tuple(params)).fetchall()

            # 解析结果
            logs = []
            for row in results:
                log_entry = {
                    "id": row.get("id"),
                    "profile_id": row.get("profile_id"),
                    "from_status": row.get("from_status"),
                    "to_status": row.get("to_status"),
                    "reason": row.get("reason"),
                    "details": json.loads(row.get("details") or "{}"),
                    "actor_type": row.get("actor_type"),
                    "actor_id": row.get("actor_id"),
                    "occurred_at": row.get("occurred_at"),
                }
                logs.append(log_entry)

            return logs

        except Exception as e:
            print(f"[审计日志] 查询失败：{e}")
            return []

        finally:
            release_profile_connection(source_dsn, conn)

    @staticmethod
    def get_transition_stats(
        *,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        source_dsn: str,
    ) -> dict[str, Any]:
        """获取状态转换统计

        Args:
            start_time: 开始时间（可选）
            end_time: 结束时间（可选）
            source_dsn: 数据源

        Returns:
            状态转换统计结果

        Example:
            >>> stats = ProfileStatusAuditLog.get_transition_stats(
            ...     start_time=datetime.now() - timedelta(days=7),
            ...     source_dsn="mysql://...",
            ... )
        """

        conn = _connect_profile_db(source_dsn, use_pool=False, timeout=5.0)

        try:
            # 构建查询条件
            conditions = []
            params = []

            if start_time is not None:
                conditions.append("occurred_at >= ?")
                params.append(start_time)

            if end_time is not None:
                conditions.append("occurred_at <= ?")
                params.append(end_time)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            # 查询转换数量统计
            sql_stats = f"""
                SELECT
                    from_status,
                    to_status,
                    reason,
                    COUNT(*) as count
                FROM profile_status_audit
                WHERE {where_clause}
                GROUP BY from_status, to_status, reason
                ORDER BY count DESC
            """
            stats_results = conn.execute(sql_stats, tuple(params)).fetchall()

            # 查询总数
            sql_total = f"""
                SELECT COUNT(*) as total_count
                FROM profile_status_audit
                WHERE {where_clause}
            """
            total_result = conn.execute(sql_total, tuple(params)).fetchone()
            total_count = total_result.get("total_count", 0) if total_result else 0

            # 构建统计结果
            stats = {
                "total_count": total_count,
                "transitions": [],
                "by_reason": {},
                "by_from_status": {},
                "by_to_status": {},
            }

            for row in stats_results:
                transition = {
                    "from_status": row.get("from_status"),
                    "to_status": row.get("to_status"),
                    "reason": row.get("reason"),
                    "count": row.get("count"),
                }
                stats["transitions"].append(transition)

                # 按原因统计
                reason = row.get("reason")
                if reason not in stats["by_reason"]:
                    stats["by_reason"][reason] = 0
                stats["by_reason"][reason] += row.get("count")

                # 按原状态统计
                from_status = row.get("from_status")
                if from_status not in stats["by_from_status"]:
                    stats["by_from_status"][from_status] = 0
                stats["by_from_status"][from_status] += row.get("count")

                # 按新状态统计
                to_status = row.get("to_status")
                if to_status not in stats["by_to_status"]:
                    stats["by_to_status"][to_status] = 0
                stats["by_to_status"][to_status] += row.get("count")

            return stats

        except Exception as e:
            print(f"[审计日志] 统计失败：{e}")
            return {
                "total_count": 0,
                "transitions": [],
                "by_reason": {},
                "by_from_status": {},
                "by_to_status": {},
            }

        finally:
            release_profile_connection(source_dsn, conn)


__all__ = ["ProfileStatusAuditLog"]