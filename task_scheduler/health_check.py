"""Scheduler 增强健康检查模块"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

LOGGER = logging.getLogger(__name__)


class SchedulerHealthChecker:
    """Scheduler 健康检查器"""

    def __init__(self, scheduler_instance: Any = None):
        self.scheduler = scheduler_instance
        self.start_time = time.time()

    def check_database_connections(self) -> dict[str, Any]:
        """检查数据库连接状态"""
        checks = {}
        databases = {
            "recommendation": os.environ.get("HER_SCHED_RECOMMENDATION_DB"),
            "matchmaking": os.environ.get("HER_SCHED_MATCHMAKING_DB"),
            "chat": os.environ.get("HER_SCHED_CHAT_DB"),
        }

        for name, dsn in databases.items():
            if not dsn:
                checks[name] = {"status": "not_configured"}
                continue

            try:
                import sqlalchemy
                engine = sqlalchemy.create_engine(dsn)
                with engine.connect() as conn:
                    conn.execute(sqlalchemy.text("SELECT 1"))
                checks[name] = {"status": "healthy"}
            except Exception as e:
                LOGGER.warning(f"Database {name} health check failed: {e}")
                checks[name] = {"status": "unhealthy", "error": str(e)}

        return checks

    def check_gateway_internal(self) -> dict[str, Any]:
        """检查 Gateway Internal 可用性"""
        gateway_url = os.environ.get("GATEWAY_INTERNAL_URL")
        if not gateway_url:
            return {"status": "not_configured"}

        try:
            import requests
            start = time.time()
            # 发送简单的 JSON-RPC ping 请求
            response = requests.post(
                gateway_url,
                json={"method": "ping", "params": [], "id": 1},
                timeout=2,
            )
            latency = (time.time() - start) * 1000

            if response.status_code == 200:
                return {"status": "healthy", "latency_ms": round(latency, 2)}
            else:
                return {"status": "unhealthy", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            LOGGER.warning(f"Gateway Internal health check failed: {e}")
            return {"status": "unreachable", "error": str(e)}

    def get_uptime(self) -> dict[str, Any]:
        """获取服务运行时间"""
        uptime_seconds = time.time() - self.start_time
        return {
            "uptime_seconds": round(uptime_seconds, 2),
            "uptime_human": self._format_uptime(uptime_seconds),
        }

    def _format_uptime(self, seconds: float) -> str:
        """格式化运行时间"""
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"

    def full_health_check(self) -> dict[str, Any]:
        """完整健康检查"""
        checks = {
            "database": self.check_database_connections(),
            "gateway_internal": self.check_gateway_internal(),
        }

        # 判断整体健康状态
        all_healthy = all(
            check.get("status") in ("healthy", "not_configured")
            for service_checks in checks.values()
            for check in service_checks.values()
            if isinstance(check, dict)
        )

        return {
            "status": "healthy" if all_healthy else "degraded",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "uptime": self.get_uptime(),
            "checks": checks,
            "config": {
                "job_interval_seconds": int(os.environ.get("HER_SCHED_INTERVAL_SECONDS", "60") or "60"),
                "databases_configured": sum(1 for db in checks["database"].values() if db.get("status") != "not_configured"),
            },
        }

    def to_json(self) -> str:
        """返回 JSON 格式的健康状态"""
        return json.dumps(self.full_health_check(), ensure_ascii=False)