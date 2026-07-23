"""会话结束处理触发器：集成到 discovery_system

触发时机：
1. 新建会话时：处理用户的上一个会话
2. 30分钟无活动：定时检查（后续迭代）
3. 会话销毁时：显式调用 close_session

集成方式：
- 在 service.py 的 create_session 中调用
- 在需要关闭会话的地方调用 close_session_and_process
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timedelta
from typing import Any

_logger = logging.getLogger(__name__)


def process_previous_session_on_new_session(
    requester_id: int,
    profile_id: int,
    *,
    current_session_id: str | None = None,  # ✅ 新增：传入刚创建的会话 ID，用于过滤
    storage: Any,
    conversation_type: str = "discovery",
    dsn: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> threading.Thread | None:
    """新建会话或切换会话时，异步处理上一个会话的新增内容

    使用场景：
    - 用户开始新对话时，处理上一个会话的新增内容
    - 用户切换会话时，处理切换前会话的新增内容
    - 避免阻塞新建会话/切换会话的主流程

    增量处理逻辑：
    - 检查上一个会话是否有新增内容（updated_at > processed_at）
    - 如果有新增内容，只处理新增部分（不重复处理）
    - 处理完成后，更新 processed_at 为会话的 updated_at

    Args:
        requester_id: 用户ID
        profile_id: 画像ID
        current_session_id: 当前刚创建的会话ID（用于排除，避免误处理新会话）
        storage: DiscoveryStorage 对象
        conversation_type: 对话类型

        dsn: 数据库连接字符串
        llm_base_url: LLM API地址
        llm_api_key: LLM API密钥
        llm_model: LLM模型名称

    Returns:
        threading.Thread 对象（如果存在上一个会话且有新增内容）
    """
    from match_domain.session_end_processor import trigger_session_end_processing

    try:
        # 查询用户的上一个会话（已完成的或最新的）
        previous_sessions = storage.list_sessions_by_profile_id(
            profile_id=profile_id,
            limit=5,
            status="active",  # 先只处理 active 状态的会话
        )

        if not previous_sessions:
            _logger.info(f"用户 {requester_id} 没有上一个会话需要处理")
            return None

        # ✅ 修复：排除刚创建的会话（如果传入 current_session_id）
        # 避免把新会话误当作上一个会话处理
        if current_session_id:
            previous_sessions = [
                s for s in previous_sessions
                if s.session_id != current_session_id
            ]
            if not previous_sessions:
                _logger.info(
                    f"用户 {requester_id} 的上一个会话已被过滤 "
                    f"(current_session_id={current_session_id})"
                )
                return None

        # 取第一个会话（最新更新的，已排除当前新会话）
        previous_session = previous_sessions[0]

        # ✅ 新增：检查是否有新增内容（增量处理）
        has_new_content = False
        if previous_session.processed_at is None:
            # 第一次处理：processed_at 为空，说明从未处理过
            has_new_content = True
            _logger.info(
                f"会话 {previous_session.session_id} 从未处理过，需要处理全部内容"
            )
        elif previous_session.updated_at > previous_session.processed_at:
            # 有新增内容：updated_at > processed_at
            has_new_content = True
            _logger.info(
                f"会话 {previous_session.session_id} 有新增内容 "
                f"(updated_at={previous_session.updated_at}, "
                f"processed_at={previous_session.processed_at})"
            )
        else:
            # 无新增内容：updated_at <= processed_at
            _logger.info(
                f"会话 {previous_session.session_id} 无新增内容，跳过处理 "
                f"(updated_at={previous_session.updated_at}, "
                f"processed_at={previous_session.processed_at})"
            )
            return None

        if not has_new_content:
            return None

        _logger.info(
            f"新建会话触发上一个会话处理: "
            f"requester_id={requester_id}, "
            f"current_session_id={current_session_id}, "
            f"previous_session_id={previous_session.session_id}, "
            f"has_new_content={has_new_content}"
        )

        # 异步触发处理
        task = trigger_session_end_processing(
            session_id=previous_session.session_id,
            requester_id=requester_id,
            profile_id=profile_id,
            conversation_type=conversation_type,
            dsn=dsn,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            # ✅ 新增：传入 processed_at，用于增量处理
            processed_at=previous_session.processed_at,
            # ✅ 新增：传入 storage，用于处理完成后更新 processed_at
            storage=storage,
        )

        return task

    except Exception as exc:
        _logger.error(f"处理上一个会话失败: requester_id={requester_id}, error={exc}")
        return None


def process_session_if_has_new_content(
    session_id: str,
    requester_id: int,
    profile_id: int,
    *,
    storage: Any,
    conversation_type: str = "discovery",
    dsn: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> threading.Thread | None:
    """检查并处理指定会话的新增内容（用于切换会话时）

    使用场景：
    - 切换会话时，检查切换前的会话是否有新增内容
    - 关闭会话时，检查关闭的会话是否有新增内容

    增量处理逻辑：
    - 检查会话是否有新增内容（updated_at > processed_at）
    - 如果有新增内容，只处理新增部分（不重复处理）
    - 处理完成后，更新 processed_at 为会话的 updated_at

    Args:
        session_id: 要检查的会话ID
        requester_id: 用户ID
        profile_id: 画像ID
        storage: DiscoveryStorage 对象
        conversation_type: 对话类型
        dsn: 数据库连接字符串
        llm_base_url: LLM API地址
        llm_api_key: LLM API密钥
        llm_model: LLM模型名称

    Returns:
        threading.Thread 对象（如果有新增内容）
    """
    from match_domain.session_end_processor import trigger_session_end_processing

    try:
        # 获取会话
        session = storage.get_session(session_id)
        if not session:
            _logger.warning(f"会话 {session_id} 不存在，跳过处理")
            return None

        # ✅ 检查是否有新增内容
        has_new_content = False
        if session.processed_at is None:
            # 第一次处理：processed_at 为空，说明从未处理过
            has_new_content = True
            _logger.info(
                f"会话 {session_id} 从未处理过，需要处理全部内容"
            )
        elif session.updated_at > session.processed_at:
            # 有新增内容：updated_at > processed_at
            has_new_content = True
            _logger.info(
                f"会话 {session_id} 有新增内容 "
                f"(updated_at={session.updated_at}, "
                f"processed_at={session.processed_at})"
            )
        else:
            # 无新增内容：updated_at <= processed_at
            _logger.info(
                f"会话 {session_id} 无新增内容，跳过处理 "
                f"(updated_at={session.updated_at}, "
                f"processed_at={session.processed_at})"
            )
            return None

        if not has_new_content:
            return None

        _logger.info(
            f"切换会话触发处理: "
            f"session_id={session_id}, "
            f"requester_id={requester_id}, "
            f"has_new_content={has_new_content}"
        )

        # 异步触发处理
        task = trigger_session_end_processing(
            session_id=session_id,
            requester_id=requester_id,
            profile_id=profile_id,
            conversation_type=conversation_type,
            dsn=dsn,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
            # ✅ 传入 processed_at，用于增量处理
            processed_at=session.processed_at,
            # ✅ 传入 storage，用于处理完成后更新 processed_at
            storage=storage,
        )

        return task

    except Exception as exc:
        _logger.error(f"处理会话 {session_id} 失败: requester_id={requester_id}, error={exc}")
        return None


def close_session_and_process(
    session_id: str,
    requester_id: int,
    profile_id: int,
    *,
    storage: Any,
    conversation_type: str = "discovery",
    now: datetime | None = None,
    dsn: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> dict[str, Any]:
    """关闭会话并触发摘要处理

    使用场景：
    - 用户主动关闭会话
    - 系统判断会话应该结束

    Args:
        session_id: 会话ID
        requester_id: 用户ID
        profile_id: 画像ID
        storage: DiscoveryStorage 对象
        conversation_type: 对话类型
        now: 当前时间

        dsn: 数据库连接字符串
        llm_base_url: LLM API地址
        llm_api_key: LLM API密钥
        llm_model: LLM模型名称

    Returns:
        关闭结果，包含：
        - closed: 是否成功关闭
        - processing_triggered: 是否触发处理
        - task_name: 异步任务名称（如果触发）
    """
    from match_domain.session_end_processor import trigger_session_end_processing

    current = now or datetime.now()

    try:
        # Step 1：关闭会话（更新状态）
        session = storage.get_session(session_id)
        if not session:
            return {
                "closed": False,
                "error": "session_not_found",
                "message": "会话不存在",
            }

        if session.status != "active":
            return {
                "closed": False,
                "error": "already_closed",
                "message": "会话已关闭",
            }

        # 更新会话状态
        session.status = "closed"
        session.updated_at = current
        storage.save_session(session)

        _logger.info(f"会话已关闭: session_id={session_id}")

        # Step 2：异步触发摘要处理
        task = trigger_session_end_processing(
            session_id=session_id,
            requester_id=requester_id,
            profile_id=profile_id,
            conversation_type=conversation_type,
            dsn=dsn,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
        )

        return {
            "closed": True,
            "processing_triggered": task is not None,
            "task_name": task.get_name() if task else None,
        }

    except Exception as exc:
        _logger.error(f"关闭会话失败: session_id={session_id}, error={exc}")
        return {
            "closed": False,
            "error": "exception",
            "message": str(exc)[:200],
        }


def check_inactive_sessions(
    *,
    storage: Any,
    inactive_threshold_minutes: int = 30,
    dsn: str | None = None,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> list[threading.Thread]:
    """检查无活动的会话，触发摘要处理

    使用场景：
    - 定时任务（如每5分钟检查一次）
    - 发现超过30分钟无活动的会话，触发处理

    Args:
        storage: DiscoveryStorage 对象
        inactive_threshold_minutes: 无活动阈值（分钟）

        dsn: 数据库连接字符串
        llm_base_url: LLM API地址
        llm_api_key: LLM API密钥
        llm_model: LLM模型名称

    Returns:
        触发的线程任务列表
    """
    from match_domain.session_end_processor import trigger_session_end_processing

    tasks: list[threading.Thread] = []

    try:
        _logger.info(f"开始检查无活动会话（阈值: {inactive_threshold_minutes}分钟）")

        current = datetime.now()
        threshold = timedelta(minutes=inactive_threshold_minutes)
        cutoff_time = current - threshold

        # 查询所有 active 且 updated_at 早于 cutoff_time 的会话
        inactive_sessions = storage.list_all_active_sessions(
            limit=50,  # 每次最多处理50个
            updated_before=cutoff_time,
        )

        _logger.info(f"发现 {len(inactive_sessions)} 个无活动会话")

        for session in inactive_sessions:
            # 异步触发处理
            task = trigger_session_end_processing(
                session_id=session.session_id,
                requester_id=session.requester_id,
                profile_id=session.profile_id,
                conversation_type="discovery",
                dsn=dsn,
                llm_base_url=llm_base_url,
                llm_api_key=llm_api_key,
                llm_model=llm_model,
            )

            if task:
                tasks.append(task)
                _logger.info(
                    f"触发无活动会话处理: session_id={session.session_id}, "
                    f"last_activity={session.updated_at}"
                )

        return tasks

    except Exception as exc:
        _logger.error(f"检查无活动会话失败: error={exc}")
        return []


__all__ = [
    "process_previous_session_on_new_session",
    "close_session_and_process",
    "check_inactive_sessions",
]