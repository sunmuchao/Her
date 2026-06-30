#!/bin/bash
# Her 项目完整修复脚本
# 解决 gateway 服务无法启动的问题

set -e  # 遇到错误立即退出

echo "========================================="
echo "🔧 Her 项目完整修复流程"
echo "========================================="

# 步骤 1: 检查 Docker 是否运行
echo ""
echo "步骤 1: 检查 Docker daemon 状态..."
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker daemon 未运行，请先启动 Docker Desktop"
    exit 1
fi
echo "✅ Docker daemon 正常"

# 步骤 2: 清理旧的 MySQL 数据
echo ""
echo "步骤 2: 清理旧的 MySQL 数据..."
docker compose down mysql || true
docker volume rm her_mysql_data || true
echo "✅ MySQL 数据已清理"

# 步骤 3: 重新构建所有镜像
echo ""
echo "步骤 3: 重新构建所有镜像（使用最新 Dockerfile）..."
docker compose build --no-cache bootstrap gateway-public gateway-internal gateway-ops scheduler
echo "✅ 镜像构建完成"

# 步骤 4: 启动 MySQL
echo ""
echo "步骤 4: 启动 MySQL（使用新认证配置）..."
docker compose up -d mysql
sleep 20
docker compose logs mysql --tail=20
echo "✅ MySQL 已启动"

# 步骤 5: 启动 bootstrap
echo ""
echo "步骤 5: 启动 bootstrap 服务..."
docker compose up -d bootstrap
sleep 15
docker compose logs bootstrap --tail=30
echo "✅ Bootstrap 已执行"

# 步骤 6: 启动所有 gateway 服务
echo ""
echo "步骤 6: 启动所有 gateway 服务..."
docker compose up -d gateway-public gateway-internal gateway-ops
sleep 10
echo "✅ Gateway 服务已启动"

# 步骤 7: 启动 scheduler
echo ""
echo "步骤 7: 启动 scheduler 服务..."
docker compose up -d scheduler
sleep 5
echo "✅ Scheduler 已启动"

# 步骤 8: 启动前端
echo ""
echo "步骤 8: 启动前端服务..."
docker compose --profile frontend up -d frontend
echo "✅ Frontend 已启动"

# 步骤 9: 最终验证
echo ""
echo "========================================="
echo "📊 最终服务状态验证"
echo "========================================="
docker compose ps

echo ""
echo "========================================="
echo "🎉 修复完成！"
echo "========================================="
echo "所有服务应该已正常启动"
echo ""
echo "验证命令："
echo "  docker compose ps          # 查看服务状态"
echo "  docker compose logs        # 查看服务日志"
echo ""