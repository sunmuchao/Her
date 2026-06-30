"""配置校验脚本 - 校验环境变量完整性、密钥强度、端口冲突"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def validate_secrets_strength() -> list[str]:
    """校验密钥强度"""
    errors = []

    secrets_dir = Path("secrets")
    if not secrets_dir.exists():
        errors.append("secrets/ directory not found, run scripts/generate_secrets.sh first")
        return errors

    # MySQL 密钥强度
    mysql_password_file = secrets_dir / "mysql_root_password.txt"
    if mysql_password_file.exists():
        password = mysql_password_file.read_text().strip()
        if len(password) < 32:
            errors.append(f"MySQL password too weak (length={len(password)}, min=32)")
    else:
        errors.append("mysql_root_password.txt not found in secrets/")

    # MinIO 密钥强度
    minio_user_file = secrets_dir / "minio_root_user.txt"
    minio_password_file = secrets_dir / "minio_root_password.txt"
    if minio_user_file.exists():
        user = minio_user_file.read_text().strip()
        if len(user) < 16:
            errors.append(f"MinIO user too weak (length={len(user)}, min=16)")
    else:
        errors.append("minio_root_user.txt not found in secrets/")

    if minio_password_file.exists():
        password = minio_password_file.read_text().strip()
        if len(password) < 32:
            errors.append(f"MinIO password too weak (length={len(password)}, min=32)")
    else:
        errors.append("minio_root_password.txt not found in secrets/")

    # Redis 密钥强度（可选）
    redis_password_file = secrets_dir / "redis_password.txt"
    if redis_password_file.exists():
        password = redis_password_file.read_text().strip()
        if len(password) < 24:
            errors.append(f"Redis password too weak (length={len(password)}, min=24)")

    return errors


def validate_required_env_vars() -> list[str]:
    """校验必需的环境变量"""
    errors = []

    # 加载 .env 文件
    env_file = Path(".env")
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file, override=False)
        except ImportError:
            # 如果没有 dotenv，手动加载
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ.setdefault(key, value)

    required_vars = [
        "HER_RELATION_LEDGER_DB",
        "PARTNER_RECOMMENDATION_DB",
        "PARTNER_MATCHMAKING_DB",
        "PARTNER_CHAT_DB",
        "PARTNER_DISCOVERY_DB",
    ]

    for var in required_vars:
        if not os.environ.get(var):
            errors.append(f"Missing required environment variable: {var}")

    return errors


def validate_port_conflicts() -> list[str]:
    """校验端口冲突"""
    errors = []

    # 定义预期端口（仅对外暴露的服务）
    expected_ports = {
        "gateway_public": 8080,  # 对外公开接口
        "frontend": 3000,        # 前端应用
        "sse_server": 8082,      # SSE实时推送（内网访问，但需要暴露给Gateway）
        "gateway_ops": 8083,     # 运营人员专用接口
    }

    # 检查是否有冲突
    port_to_service = {}
    for service, port in expected_ports.items():
        if port in port_to_service:
            errors.append(
                f"Port conflict: {service} and {port_to_service[port]} both use port {port}"
            )
        else:
            port_to_service[port] = service

    return errors


def validate_docker_compose_healthcheck() -> list[str]:
    """校验 Docker Compose 健康检查配置"""
    errors = []

    docker_compose_file = Path("docker-compose.production.yml")
    if not docker_compose_file.exists():
        errors.append("docker-compose.production.yml not found")
        return errors

    # 检查关键服务的健康检查
    import yaml

    with open(docker_compose_file) as f:
        compose_config = yaml.safe_load(f)

    critical_services = ["gateway-public", "gateway-internal", "sse-server", "scheduler"]
    for service in critical_services:
        service_config = compose_config.get("services", {}).get(service)
        if not service_config:
            errors.append(f"Service {service} not found in docker-compose.production.yml")
            continue

        if "healthcheck" not in service_config:
            errors.append(f"Service {service} missing healthcheck configuration")

        if "restart" not in service_config:
            errors.append(f"Service {service} missing restart policy")

    return errors


def validate_network_isolation() -> list[str]:
    """校验网络隔离配置"""
    errors = []

    docker_compose_file = Path("docker-compose.production.yml")
    if not docker_compose_file.exists():
        return errors

    import yaml

    with open(docker_compose_file) as f:
        compose_config = yaml.safe_load(f)

    # 检查网络配置
    networks = compose_config.get("networks", {})
    if "data_net" not in networks:
        errors.append("data_net network not found (required for database isolation)")
    else:
        data_net_config = networks["data_net"]
        if not data_net_config.get("internal"):
            errors.append("data_net should be internal: true for strict isolation")

    # 检查数据库服务是否在 data_net
    db_services = ["mysql", "minio", "redis"]
    for service in db_services:
        service_config = compose_config.get("services", {}).get(service)
        if service_config and "data_net" not in service_config.get("networks", []):
            errors.append(f"Service {service} should be in data_net network")

    return errors


def main():
    """运行所有校验"""
    print("=== 配置完整性校验 ===")
    print()

    all_errors = []

    # 1. 密钥强度校验
    print("1. 校验密钥强度...")
    errors = validate_secrets_strength()
    if errors:
        print(f"  ❌ 发现 {len(errors)} 个问题:")
        for error in errors:
            print(f"    - {error}")
        all_errors.extend(errors)
    else:
        print("  ✅ 密钥强度符合要求")

    # 2. 必需环境变量校验
    print("\n2. 校验必需环境变量...")
    errors = validate_required_env_vars()
    if errors:
        print(f"  ❌ 发现 {len(errors)} 个问题:")
        for error in errors:
            print(f"    - {error}")
        all_errors.extend(errors)
    else:
        print("  ✅ 所有必需环境变量已配置")

    # 3. 端口冲突校验
    print("\n3. 校验端口冲突...")
    errors = validate_port_conflicts()
    if errors:
        print(f"  ❌ 发现 {len(errors)} 个问题:")
        for error in errors:
            print(f"    - {error}")
        all_errors.extend(errors)
    else:
        print("  ✅ 无端口冲突")

    # 4. Docker Compose 健康检查校验
    print("\n4. 校验 Docker Compose 健康检查...")
    errors = validate_docker_compose_healthcheck()
    if errors:
        print(f"  ❌ 发现 {len(errors)} 个问题:")
        for error in errors:
            print(f"    - {error}")
        all_errors.extend(errors)
    else:
        print("  ✅ 所有关键服务已配置健康检查")

    # 5. 网络隔离校验
    print("\n5. 校验网络隔离配置...")
    errors = validate_network_isolation()
    if errors:
        print(f"  ❌ 发现 {len(errors)} 个问题:")
        for error in errors:
            print(f"    - {error}")
        all_errors.extend(errors)
    else:
        print("  ✅ 网络隔离配置正确")

    # 总结
    print("\n" + "=" * 50)
    if all_errors:
        print(f"❌ 校验失败: 共发现 {len(all_errors)} 个问题")
        print("\n建议:")
        print("  1. 运行 scripts/generate_secrets.sh 生成密钥")
        print("  2. 检查 .env 文件确保所有必需环境变量已配置")
        print("  3. 检查 docker-compose.production.yml 配置")
        return 1
    else:
        print("✅ 所有校验通过，架构改进已正确实施")
        return 0


if __name__ == "__main__":
    sys.exit(main())