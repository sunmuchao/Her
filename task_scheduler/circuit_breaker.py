"""熔断机制 - Scheduler 调用 Gateway Internal 时的自动熔断"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

LOGGER = logging.getLogger(__name__)


@dataclass
class CircuitBreakerState:
    """熔断器状态"""
    failure_count: int = 0
    last_failure_time: float = 0.0
    is_open: bool = False  # True = 熔断打开（拒绝请求）
    last_success_time: float = 0.0


class CircuitBreaker:
    """熔断器 - 保护 Scheduler 不在 Gateway Internal 挂掉时持续报错"""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
    ):
        """
        Args:
            failure_threshold: 连续失败次数阈值，达到后熔断
            recovery_timeout: 熔断后等待恢复的超时时间（秒）
            half_open_max_calls: 半开状态下允许的最大试探调用次数
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.state = CircuitBreakerState()
        self._half_open_calls = 0

    def call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """通过熔断器调用函数

        Args:
            fn: 要调用的函数
            *args: 函数参数
            **kwargs: 函数关键字参数

        Returns:
            函数执行结果

        Raises:
            CircuitBreakerOpen: 熔断器打开时拒绝调用
        """
        current_time = time.time()

        # 检查熔断器状态
        if self.state.is_open:
            # 熔断打开状态，检查是否可以进入半开状态
            if current_time - self.state.last_failure_time >= self.recovery_timeout:
                LOGGER.info("Circuit breaker entering half-open state")
                self.state.is_open = False
                self._half_open_calls = 0
            else:
                # 熔断仍然打开，拒绝调用
                LOGGER.warning(f"Circuit breaker is open, rejecting call (will retry after {self.recovery_timeout}s)")
                raise CircuitBreakerOpen(
                    f"Circuit breaker is open, will retry after {int(self.recovery_timeout - (current_time - self.state.last_failure_time))}s"
                )

        # 执行调用
        try:
            result = fn(*args, **kwargs)
            self._on_success(current_time)
            return result
        except Exception as e:
            self._on_failure(current_time)
            raise e

    def _on_success(self, current_time: float) -> None:
        """调用成功时更新状态"""
        self.state.failure_count = 0
        self.state.last_success_time = current_time
        self.state.is_open = False
        self._half_open_calls = 0
        LOGGER.debug("Circuit breaker: call succeeded, resetting failure count")

    def _on_failure(self, current_time: float) -> None:
        """调用失败时更新状态"""
        self.state.failure_count += 1
        self.state.last_failure_time = current_time

        if self.state.failure_count >= self.failure_threshold:
            # 达到失败阈值，打开熔断器
            self.state.is_open = True
            LOGGER.warning(
                f"Circuit breaker opened after {self.state.failure_count} consecutive failures "
                f"(threshold={self.failure_threshold})"
            )
        else:
            LOGGER.warning(
                f"Circuit breaker: call failed ({self.state.failure_count}/{self.failure_threshold})"
            )

    def get_state(self) -> dict[str, Any]:
        """获取熔断器当前状态"""
        return {
            "is_open": self.state.is_open,
            "failure_count": self.state.failure_count,
            "last_failure_time": self.state.last_failure_time,
            "last_success_time": self.state.last_success_time,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }


class CircuitBreakerOpen(Exception):
    """熔断器打开异常"""
    pass


# 全局熔断器实例
_gateway_internal_breaker: CircuitBreaker | None = None


def get_gateway_internal_breaker() -> CircuitBreaker:
    """获取 Gateway Internal 熔断器实例"""
    if _gateway_internal_breaker is None:
        # 从环境变量读取配置
        failure_threshold = int(os.environ.get("HER_SCHED_CIRCUIT_BREAKER_THRESHOLD", "5") or "5")
        recovery_timeout = float(os.environ.get("HER_SCHED_CIRCUIT_BREAKER_TIMEOUT", "60") or "60")

        _gateway_internal_breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        LOGGER.info(
            f"Circuit breaker initialized: threshold={failure_threshold}, timeout={recovery_timeout}s"
        )

    return _gateway_internal_breaker


def call_gateway_internal_with_circuit_breaker(
    fn: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    """通过熔断器调用 Gateway Internal

    Args:
        fn: 要调用的函数
        *args: 函数参数
        **kwargs: 函数关键字参数

    Returns:
        函数执行结果

    Raises:
        CircuitBreakerOpen: 熔断器打开时拒绝调用
    """
    breaker = get_gateway_internal_breaker()
    return breaker.call(fn, *args, **kwargs)