"""定时任务调度器：定期检查无活动会话

使用场景：
- 每5分钟检查一次
- 发现超过30分钟无活动的会话，触发摘要处理

部署方式：
1. 内嵌模式：在应用启动时启动定时任务（适合单机部署）
2. 外部调度：使用 cron 或 Celery 调度（适合分布式部署）

示例：
# 内嵌模式
from match_domain.session_end_scheduler import start_inactive_session_checker

# 启动定时任务
await start_inactive_session_checker(storage, interval_minutes=5)
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any

_logger = logging.getLogger(__name__)


async def start_inactive_session_checker(
    storage: Any,
    *,
    interval_minutes: int = 5,
    inactive_threshold_minutes: int = 30,
    dsn: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> asyncio.Task[None]:
    """启动定时任务：定期检查无活动会话

    Args:
        storage: DiscoveryStorage 对象
        interval_minutes: 检查间隔（分钟），默认5分钟
        inactive_threshold_minutes: 无活动阈值（分钟），默认30分钟

        dsn: 数据库连接字符串
        llm_base_url: LLM API地址
        llm_api_key: LLM API密钥
        llm_model: LLM模型名称

    Returns:
        asyncio.Task 对象（后台运行的定时任务）
    """
    async def _check_loop():
        _logger.info(
            f"启动无活动会话检查定时任务: "
            f"interval={interval_minutes}分钟, "
            f"threshold={inactive_threshold_minutes}分钟"
        )

        while True:
            try:
                # 等待下一次检查
                await asyncio.sleep(interval_minutes * 60)

                _logger.info(f"定时检查触发: time={datetime.now()}")

                # 检查无活动会话
                from match_domain.session_end_trigger import check_inactive_sessions

                tasks = check_inactive_sessions(
                    storage=storage,
                    inactive_threshold_minutes=inactive_threshold_minutes,
                    dsn=dsn,
                    llm_base_url=llm_base_url,
                    llm_api_key=llm_api_key,
                    llm_model=llm_model,
                )

                _logger.info(f"本次检查触发 {len(tasks)} 个处理任务")

                # 不等待任务完成，继续下一个循环
                # 任务会在后台异步执行

            except asyncio.CancelledError:
                _logger.info("定时任务被取消，停止检查")
                break
            except Exception as exc:
                _logger.error(f"定时检查失败: error={exc}")
                # 继续下一次循环，不中断

    # 创建后台任务
    task = asyncio.create_task(
        _check_loop(),
        name="inactive_session_checker",
    )

    _logger.info(f"定时任务已启动: task_name={task.name}")

    return task


def stop_inactive_session_checker(task: asyncio.Task[None]) -> None:
    """停止定时任务

    Args:
        task: start_inactive_session_checker 返回的任务对象
    """
    if task and not task.done():
        task.cancel()
        _logger.info(f"定时任务已取消: task_name={task.name}")


async def run_once_inactive_session_check(
    storage: Any,
    *,
    inactive_threshold_minutes: int = 30,
    dsn: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> list[asyncio.Task[dict[str, Any]]]:
    """单次检查（不启动定时任务）

    使用场景：
- 手动触发检查
- 外部调度器调用（如 cron、Celery）

    Args:
        storage: DiscoveryStorage 对象
        inactive_threshold_minutes: 无活动阈值（分钟）

        dsn: 数据库连接字符串
        llm_base_url: LLM API地址
        llm_api_key: LLM API密钥
        llm_model: LLM模型名称

    Returns:
        触发的异步任务列表
    """
    from match_domain.session_end_trigger import check_inactive_sessions

    return check_inactive_sessions(
        storage=storage,
        inactive_threshold_minutes=inactive_threshold_minutes,
        dsn=dsn,
        llm_base_url=llm_base_url,
        llm_api_key=llm_api_key,
        llm_model=llm_model,
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 新增：向量重试调度器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def start_vector_retry_checker(
    storage: Any,
    *,
    interval_minutes: int = 10,
    max_retry_count: int = 3,
    dsn: str | None = None,
) -> asyncio.Task[None]:
    """启动定时任务：检查失败的向量写入并重试

    功能说明：
    - 每10分钟检查一次 vector_status='failed' 的记录
    - 自动重试失败的向量写入（最多3次）
    - 重试成功后更新状态为 'done'

    Args:
        storage: DiscoveryStorage 对象
        interval_minutes: 检查间隔（分钟），默认10分钟
        max_retry_count: 最大重试次数，默认3次
        dsn: 数据库连接字符串

    Returns:
        asyncio.Task 对象（后台运行的定时任务）
    """
    async def _retry_loop():
        _logger.info(
            f"启动向量重试检查定时任务: "
            f"interval={interval_minutes}分钟, "
            f"max_retry={max_retry_count}"
        )

        while True:
            try:
                await asyncio.sleep(interval_minutes * 60)

                _logger.info(f"向量重试检查触发: time={datetime.now()}")

                # 查询 vector_status='failed' 的记录
                from match_domain.ai_merge_handler import (
                    query_failed_vector_records,
                    retry_vector_write,
                )

                failed_records = await query_failed_vector_records(
                    dsn=dsn,
                    max_retry_count=max_retry_count,
                )

                if not failed_records:
                    _logger.info("没有需要重试的向量记录")
                    continue

                _logger.info(f"发现 {len(failed_records)} 条失败记录")

                # 尝试重试
                success_count = 0
                for record in failed_records:
                    try:
                        success = await retry_vector_write(record)
                        if success:
                            success_count += 1
                    except Exception as exc:
                        _logger.error(
                            f"重试失败: user_id={record.get('requester_id')}, "
                            f"key={record.get('summary_key')}, error={exc}"
                        )

                _logger.info(
                    f"重试完成: "
                    f"total={len(failed_records)}, success={success_count}"
                )

            except asyncio.CancelledError:
                _logger.info("向量重试定时任务被取消")
                break
            except Exception as exc:
                _logger.error(f"向量重试检查失败: error={exc}")
                # 继续下一次循环，不中断

    task = asyncio.create_task(_retry_loop(), name="vector_retry_checker")
    _logger.info(f"向量重试定时任务已启动: task_name={task.get_name()}")

    return task


def stop_vector_retry_checker(task: asyncio.Task[None]) -> None:
    """停止向量重试定时任务

    Args:
        task: start_vector_retry_checker 返回的任务对象
    """
    if task and not task.done():
        task.cancel()
        _logger.info(f"向量重试定时任务已取消: task_name={task.get_name()}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 新增：版本清理调度器
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def start_version_cleanup_checker(
    storage: Any,
    *,
    interval_hours: int = 24,  # 每24小时清理一次
    dsn: str | None = None,
) -> asyncio.Task[None]:
    """启动定时任务：定期清理旧版本向量

    功能说明：
    - 每24小时清理一次所有用户的旧版本向量
    - 根据配置保留最近的版本（如 personality_traits 保留5个）
    - 清理超过指定天数的旧版本（如 personality_traits 清理90天外的）
    - 节省存储空间，避免版本堆积

    Args:
        storage: DiscoveryStorage 对象
        interval_hours: 清理间隔（小时），默认24小时
        dsn: 数据库连接字符串（未使用，保留接口一致性）

    Returns:
        asyncio.Task 对象（后台运行的定时任务）
    """
    async def _cleanup_loop():
        _logger.info(f"启动版本清理定时任务: interval={interval_hours}小时")

        while True:
            try:
                await asyncio.sleep(interval_hours * 3600)

                _logger.info(f"版本清理触发: time={datetime.now()}")

                from match_domain.vector_store_lite import (
                    VectorStoreLite,
                    VECTOR_TYPES_CONFIG,
                )

                vector_store = VectorStoreLite()

                try:
                    # 清理每种向量类型
                    total_deleted = 0
                    for vector_type in VECTOR_TYPES_CONFIG.keys():
                        try:
                            result = vector_store.cleanup_all_users_old_versions(vector_type)
                            deleted = result.get("total_deleted", 0)
                            total_deleted += deleted

                            _logger.info(
                                f"清理完成: vector_type={vector_type}, "
                                f"users={result.get('total_users')}, "
                                f"deleted={deleted}"
                            )
                        except Exception as exc:
                            _logger.error(
                                f"清理失败: vector_type={vector_type}, "
                                f"error={exc}"
                            )

                    _logger.info(
                        f"本轮清理完成: "
                        f"total_types={len(VECTOR_TYPES_CONFIG)}, "
                        f"total_deleted={total_deleted}"
                    )
                finally:
                    # ⚠️ 重要：每次循环结束主动关闭连接
                    vector_store.close()

            except asyncio.CancelledError:
                _logger.info("版本清理定时任务被取消")
                break
            except Exception as exc:
                _logger.error(f"版本清理失败: error={exc}")
                # 继续下一次循环，不中断

    task = asyncio.create_task(_cleanup_loop(), name="version_cleanup_checker")
    _logger.info(f"版本清理定时任务已启动: task_name={task.get_name()}")

    return task


def stop_version_cleanup_checker(task: asyncio.Task[None]) -> None:
    """停止版本清理定时任务

    Args:
        task: start_version_cleanup_checker 返回的任务对象
    """
    if task and not task.done():
        task.cancel()
        _logger.info(f"版本清理定时任务已取消: task_name={task.get_name()}")


__all__ = [
    "start_inactive_session_checker",
    "stop_inactive_session_checker",
    "run_once_inactive_session_check",
    "start_vector_retry_checker",
    "stop_vector_retry_checker",
    "start_version_cleanup_checker",  # 新增
    "stop_version_cleanup_checker",  # 新增
]