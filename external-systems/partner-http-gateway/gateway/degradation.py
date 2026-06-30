"""服务降级机制 - Gateway 数据库不可用时的优雅降级"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

LOGGER = logging.getLogger(__name__)


def handle_database_unavailable(trace_id: str, database_name: str) -> tuple[int, dict[str, Any]]:
    """数据库不可用时的降级处理

    Args:
        trace_id: 请求追踪ID
        database_name: 数据库名称

    Returns:
        tuple: (status_code, error_payload)
    """
    LOGGER.warning(f"Database {database_name} unavailable, returning degraded response")

    return 503, {
        "error": "service_temporarily_unavailable",
        "message": f"数据库 {database_name} 暂时不可用，请稍后重试",
        "retry_after": 30,  # 建议30秒后重试
        "trace_id": trace_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "suggestion": "请稍后重试，或联系客服获取帮助",
    }


def handle_minio_unavailable(trace_id: str) -> tuple[int, dict[str, Any]]:
    """MinIO 不可用时的降级处理

    Args:
        trace_id: 请求追踪ID

    Returns:
        tuple: (status_code, error_payload)
    """
    LOGGER.warning("MinIO unavailable, returning degraded response")

    return 503, {
        "error": "storage_temporarily_unavailable",
        "message": "图片存储暂时不可用，您可以继续操作但无法上传或查看图片",
        "retry_after": 60,  # 建议60秒后重试
        "trace_id": trace_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "suggestion": "您可以继续使用其他功能，图片功能将在稍后恢复",
    }


def handle_gateway_internal_unavailable(trace_id: str) -> tuple[int, dict[str, Any]]:
    """Gateway Internal 不可用时的降级处理

    Args:
        trace_id: 请求追踪ID

    Returns:
        tuple: (status_code, error_payload)
    """
    LOGGER.warning("Gateway Internal unavailable, returning degraded response")

    return 503, {
        "error": "internal_service_unavailable",
        "message": "内部服务暂时不可用，请稍后重试",
        "retry_after": 30,
        "trace_id": trace_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "suggestion": "如果您是运营人员，请联系技术支持",
    }


def handle_timeout_error(trace_id: str, timeout_seconds: float) -> tuple[int, dict[str, Any]]:
    """超时错误的降级处理

    Args:
        trace_id: 请求追踪ID
        timeout_seconds: 超时时间

    Returns:
        tuple: (status_code, error_payload)
    """
    LOGGER.warning(f"Request timeout after {timeout_seconds}s")

    return 504, {
        "error": "request_timeout",
        "message": f"请求处理超时（{timeout_seconds}秒），请稍后重试",
        "trace_id": trace_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "suggestion": "请简化查询条件或稍后重试",
    }


def wrap_with_degradation(
    fn: Any,
    trace_id: str,
    *,
    database_name: str = "unknown",
    timeout_seconds: float = 30.0,
) -> tuple[int, dict[str, Any]]:
    """包装函数并添加降级逻辑

    Args:
        fn: 要执行的函数
        trace_id: 请求追踪ID
        database_name: 数据库名称
        timeout_seconds: 超时时间

    Returns:
        tuple: (status_code, payload)
    """
    import signal
    from contextlib import contextmanager

    @contextmanager
    def timeout_handler(seconds: float):
        """超时处理上下文管理器"""
        def timeout_signal_handler(signum, frame):
            raise TimeoutError(f"Operation timed out after {seconds}s")

        # 仅在支持signal的系统中使用
        try:
            signal.signal(signal.SIGALRM, timeout_signal_handler)
            signal.alarm(int(seconds))
            yield
            signal.alarm(0)  # 取消alarm
        except (ValueError, OSError):
            # macOS 不支持 SIGALRM，直接yield
            yield

    try:
        with timeout_handler(timeout_seconds):
            return fn()
    except TimeoutError:
        return handle_timeout_error(trace_id, timeout_seconds)
    except Exception as e:
        # 检查是否是数据库连接错误
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in ["connection", "database", "mysql", "timeout", "refused"]):
            return handle_database_unavailable(trace_id, database_name)
        else:
            # 其他错误，返回500
            LOGGER.error(f"Unexpected error: {e}")
            return 500, {
                "error": "internal_error",
                "message": "内部错误，请联系技术支持",
                "trace_id": trace_id,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }