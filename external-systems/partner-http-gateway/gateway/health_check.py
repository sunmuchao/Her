"""Gateway 增强健康检查模块 - 生产级详细状态"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

LOGGER = logging.getLogger(__name__)


class HealthChecker:
    """生产级健康检查器 - 详细状态 + 连接检查"""

    def __init__(self, gateway_instance: Any):
        self.gateway = gateway_instance
        self.start_time = time.time()

    def check_database(self, pool: Any, name: str) -> dict[str, Any]:
        """检查数据库连接状态"""
        conn = None
        try:
            if pool is None:
                return {"status": "not_configured", "latency_ms": None}

            start = time.time()
            conn = pool.acquire(timeout=2.0)
            result = conn.execute("SELECT 1").fetchone()
            latency = (time.time() - start) * 1000

            return {
                "status": "healthy",
                "latency_ms": round(latency, 2),
                "result": result or {"1": 1},
            }
        except Exception as e:
            LOGGER.warning(f"Database {name} health check failed: {e}")
            return {"status": "unhealthy", "error": str(e), "latency_ms": None}
        finally:
            if conn is not None:
                try:
                    pool.release(conn)
                except Exception:
                    LOGGER.exception("Failed to release %s health-check connection", name)

    def check_minio(self) -> dict[str, Any]:
        """检查 MinIO 连接状态"""
        try:
            import requests

            endpoint = os.environ.get("MINIO_ENDPOINT", "127.0.0.1:9000")
            minio_user_file = os.environ.get("MINIO_ACCESS_KEY_FILE")
            minio_password_file = os.environ.get("MINIO_SECRET_KEY_FILE")

            # 获取认证信息
            minio_user = None
            minio_password = None

            if minio_user_file and minio_password_file:
                # 生产环境：读取密钥文件
                try:
                    with open(minio_user_file) as f:
                        minio_user = f.read().strip()
                    with open(minio_password_file) as f:
                        minio_password = f.read().strip()
                except Exception as e:
                    LOGGER.warning(f"Failed to read MinIO secrets files: {e}")
                    return {"status": "secrets_read_error", "error": str(e)}
            else:
                # 开发环境：从环境变量读取
                minio_user = os.environ.get("MINIO_ACCESS_KEY", "her_minio_admin")
                minio_password = os.environ.get("MINIO_SECRET_KEY", "her_minio_password")

            # 实际验证连接
            start = time.time()

            # 尝试访问 MinIO 健康检查端点（不需要认证）
            try:
                response = requests.get(f"http://{endpoint}/minio/health/live", timeout=3)
                latency = (time.time() - start) * 1000

                if response.status_code == 200:
                    return {"status": "healthy", "latency_ms": round(latency, 2)}
                else:
                    return {"status": "unhealthy", "error": f"HTTP {response.status_code}", "latency_ms": round(latency, 2)}
            except requests.exceptions.Timeout:
                return {"status": "timeout", "error": "Connection timeout after 3s"}
            except requests.exceptions.ConnectionError as e:
                return {"status": "unreachable", "error": str(e)}

        except Exception as e:
            LOGGER.warning(f"MinIO health check failed: {e}")
            return {"status": "error", "error": str(e)}

    def check_redis(self) -> dict[str, Any]:
        """检查 Redis 连接状态"""
        try:
            import redis as redis_module
        except ModuleNotFoundError as e:
            return {"status": "not_installed", "error": str(e)}

        try:
            host = os.environ.get("REDIS_HOST", "127.0.0.1")
            port = int(os.environ.get("REDIS_PORT", 6379))
            password_file = os.environ.get("REDIS_PASSWORD_FILE")

            # 获取Redis密码
            password = None

            if password_file:
                # 生产环境：读取密钥文件
                try:
                    with open(password_file) as f:
                        password = f.read().strip()
                except Exception as e:
                    LOGGER.warning(f"Failed to read Redis password file: {e}")
                    return {"status": "secrets_read_error", "error": str(e)}
            else:
                # 开发环境：从环境变量读取（如果有）
                password = os.environ.get("REDIS_PASSWORD")

            # 实际验证连接
            start = time.time()
            client = redis_module.Redis(
                host=host,
                port=port,
                password=password,
                socket_connect_timeout=3
            )
            client.ping()
            latency = (time.time() - start) * 1000

            return {"status": "healthy", "latency_ms": round(latency, 2)}
        except Exception as e:
            if isinstance(e, redis_module.exceptions.TimeoutError):
                return {"status": "timeout", "error": "Connection timeout after 3s"}
            if isinstance(e, redis_module.exceptions.ConnectionError):
                return {"status": "unreachable", "error": str(e)}
            LOGGER.warning(f"Redis health check failed: {e}")
            return {"status": "error", "error": str(e)}

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
            "database": {
                "recommendation": self.check_database(self.gateway._rec_pool, "recommendation"),
                "matchmaking": self.check_database(self.gateway._mm_pool, "matchmaking"),
                "chat": self.check_database(self.gateway._chat_pool, "chat"),
                "relation_ledger": self.check_database(self.gateway._ledger_pool, "relation_ledger"),
            },
            "storage": {
                "minio": self.check_minio(),
                "redis": self.check_redis(),
            },
        }

        # 判断整体健康状态
        all_healthy = all(
            check.get("status") == "healthy"
            for service_checks in checks.values()
            for check in service_checks.values()
            if check.get("status") not in {"not_configured", "not_installed"}  # 忽略未配置/未启用的可选服务
        )

        return {
            "status": "healthy" if all_healthy else "degraded",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "uptime": self.get_uptime(),
            "checks": checks,
            "config": {
                "surface": os.environ.get("PARTNER_GATEWAY_SURFACE", "unknown"),
                "jsonrpc_enabled": os.environ.get("PARTNER_GATEWAY_ENABLE_JSONRPC", "0") == "1",
                "db_pool_max": int(os.environ.get("PARTNER_GATEWAY_DB_POOL_MAX", "0") or "0"),
                "rate_limit_per_minute": int(os.environ.get("PARTNER_GATEWAY_RATE_LIMIT_PER_MINUTE", "600") or "600"),
            },
        }
