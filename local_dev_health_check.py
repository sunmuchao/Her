"""Local development environment service availability checker.

This module provides automatic health checks for required services
and helpful startup instructions when services are unavailable.
"""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

REQUIRED_SERVICES = {
    "mysql": {
        "port": 3307,
        "description": "MySQL database (关系 ledger / 推荐 / 匹配 / 聊天)",
        "docker_compose_service": "mysql",
        "startup_hint": "docker compose up -d mysql",
    },
    "minio": {
        "port": 9000,
        "description": "MinIO media storage (图片上传)",
        "docker_compose_service": "minio",
        "startup_hint": "docker compose up -d minio",
    },
    "signaling": {
        "port": 8765,
        "description": "WebRTC signaling server (视频通话)",
        "docker_compose_service": "signaling-server",
        "startup_hint": "docker compose up -d signaling-server",
    },
}


def check_port_available(host: str, port: int) -> bool:
    """Check if a port is accepting connections."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            return result == 0
    except OSError:
        return False


def check_docker_running() -> bool:
    """Check if Docker daemon is running."""
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def check_service_health(service_name: str) -> dict[str, Any]:
    """Check health status of a required service."""
    service_info = REQUIRED_SERVICES.get(service_name)
    if not service_info:
        return {"available": False, "error": f"Unknown service: {service_name}"}

    port = service_info["port"]
    host = "127.0.0.1"

    available = check_port_available(host, port)

    return {
        "service": service_name,
        "available": available,
        "port": port,
        "host": host,
        "description": service_info["description"],
        "docker_service": service_info["docker_compose_service"],
        "startup_hint": service_info["startup_hint"],
    }


def print_startup_guide(unavailable_services: list[dict[str, Any]]) -> None:
    """Print helpful startup instructions for unavailable services."""
    if not unavailable_services:
        return

    print("\n" + "=" * 70)
    print("⚠️  本地开发环境服务可用性检查")
    print("=" * 70)
    print("\n以下服务未运行,请按指引启动:\n")

    docker_running = check_docker_running()

    if not docker_running:
        print("【第一步】启动 Docker Desktop")
        print("  → Docker daemon 未运行,请先启动 Docker Desktop 应用")
        print("  → 等待 Docker 图标变绿后再继续\n")

    print("【第二步】启动缺失的服务")
    for svc in unavailable_services:
        status = "❌" if not svc["available"] else "✅"
        print(f"\n{status} {svc['service']} (端口 {svc['port']})")
        print(f"   说明: {svc['description']}")
        if not svc["available"]:
            print(f"   启动: {svc['startup_hint']}")

    print("\n" + "=" * 70)
    print("【快速启动所有服务】")
    print("  docker compose up -d")
    print("=" * 70 + "\n")


def check_all_services(verbose: bool = True) -> bool:
    """Check all required services and print guidance if needed."""
    unavailable = []

    for service_name in REQUIRED_SERVICES:
        health = check_service_health(service_name)
        if not health["available"]:
            unavailable.append(health)
            if verbose:
                LOGGER.warning(
                    "Service %s unavailable at %s:%s",
                    service_name,
                    health["host"],
                    health["port"],
                )

    if unavailable and verbose:
        print_startup_guide(unavailable)

    return len(unavailable) == 0


def enforce_service_available(service_name: str) -> None:
    """Raise error if a specific service is not available."""
    health = check_service_health(service_name)
    if not health["available"]:
        print_startup_guide([health])
        raise RuntimeError(
            f"Required service {service_name} is not available at "
            f"{health['host']}:{health['port']}. "
            f"Start it with: {health['startup_hint']}"
        )


def quick_minio_check() -> bool:
    """Quick check specifically for MinIO (image upload dependency)."""
    return check_port_available("127.0.0.1", 9000)


__all__ = [
    "check_all_services",
    "check_service_health",
    "check_docker_running",
    "enforce_service_available",
    "quick_minio_check",
    "REQUIRED_SERVICES",
]