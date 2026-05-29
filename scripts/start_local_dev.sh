#!/bin/bash
# 本地开发环境一键启动脚本
# 用法: scripts/start_local_dev.sh [--check-only]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

echo "=== Her 本地开发环境启动检查 ==="
echo ""

# 1. 检查 Docker
echo "【1】检查 Docker daemon..."
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker daemon 未运行"
    echo ""
    echo "请先启动 Docker Desktop:"
    echo "  1. 打开 Docker Desktop 应用"
    echo "  2. 等待 Docker 图标变绿"
    echo "  3. 重新运行此脚本"
    exit 1
fi
echo "✅ Docker daemon 已运行"
echo ""

# 2. 检查服务状态
echo "【2】检查必需服务状态..."
services=("mysql:3307:MySQL 数据库" "minio:9000:MinIO 媒体存储" "signaling:8765:WebRTC 信令服务器")
need_start=()

for svc_info in "${services[@]}"; do
    IFS=':' read -r name port desc <<< "$svc_info"
    if curl -f -s "http://127.0.0.1:$port" >/dev/null 2>&1 || nc -z 127.0.0.1 "$port" >/dev/null 2>&1; then
        echo "✅ $name ($desc) - 端口 $port 已监听"
    else
        echo "❌ $name ($desc) - 端口 $port 未监听"
        need_start+=("$name")
    fi
done

echo ""

# 3. 如果只是检查模式,直接退出
if [[ "$1" == "--check-only" ]]; then
    if [ ${#need_start[@]} -eq 0 ]; then
        echo "✅ 所有必需服务已运行"
        exit 0
    else
        echo "⚠️  需要启动的服务: ${need_start[*]}"
        echo ""
        echo "启动命令:"
        echo "  docker compose up -d"
        exit 1
    fi
fi

# 4. 启动缺失的服务
if [ ${#need_start[@]} -gt 0 ]; then
    echo "【3】启动缺失的服务..."
    echo ""
    docker compose up -d
    echo ""
    echo "等待服务启动(15秒)..."
    sleep 15
fi

# 5. 最终验证
echo "【4】最终验证..."
echo ""
python3 -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from local_dev_health_check import check_all_services
success = check_all_services(verbose=True)
sys.exit(0 if success else 1)
"

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ 本地开发环境已就绪!"
    echo ""
    echo "服务访问信息:"
    echo "  MySQL:       mysql://root@127.0.0.1:3307"
    echo "  MinIO API:   http://127.0.0.1:9000"
    echo "  MinIO Console: http://127.0.0.1:9001 (用户: her_minio_admin / 密码: her_minio_password)"
    echo "  Signaling:   ws://127.0.0.1:8765"
    echo ""
    echo "Gateway 启动:"
    echo "  python -m gateway --host 127.0.0.1 --port 8080"
else
    echo ""
    echo "⚠️  部分服务启动失败,请检查日志:"
    echo "  docker compose logs"
fi