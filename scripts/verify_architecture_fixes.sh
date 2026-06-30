#!/bin/bash
# 验证部署架构修复效果

set -e

echo "========================================="
echo "验证部署架构修复效果"
echo "========================================="
echo ""

# 1. 验证Prometheus端口配置
echo "1. 验证Prometheus端口配置..."
if grep -q "gateway-ops:8083" config/prometheus.yml; then
    echo "✅ Gateway Ops端口配置正确（8083）"
else
    echo "❌ Gateway Ops端口配置错误"
    exit 1
fi

if grep -q "sse-server:8081" config/prometheus.yml; then
    echo "✅ SSE Server端口配置正确（8081）"
else
    echo "❌ SSE Server端口配置错误"
    exit 1
fi
echo ""

# 2. 验证Scheduler健康检查端口绑定
echo "2. 验证Scheduler健康检查端口绑定..."
if grep -q 'HTTPServer(("0.0.0.0"' task_scheduler/__main__.py; then
    echo "✅ Scheduler健康检查绑定到0.0.0.0"
else
    echo "❌ Scheduler健康检查绑定错误"
    exit 1
fi
echo ""

# 3. 验证Gunicorn依赖已添加
echo "3. 验证Gunicorn依赖已添加..."
if grep -q "gunicorn>=21.0.0" pyproject.toml; then
    echo "✅ Gunicorn依赖已添加到pyproject.toml"
else
    echo "❌ Gunicorn依赖未添加"
    exit 1
fi

if grep -q "gevent>=23.0.0" pyproject.toml; then
    echo "✅ Gevent依赖已添加到pyproject.toml"
else
    echo "❌ Gevent依赖未添加"
    exit 1
fi
echo ""

# 4. 验证docker-compose.production.yml中的Gunicorn命令
echo "4. 验证docker-compose.production.yml中的Gunicorn命令..."
if grep -q "gunicorn" docker-compose.production.yml; then
    echo "✅ Gateway使用Gunicorn启动命令"
else
    echo "❌ Gateway未使用Gunicorn"
    exit 1
fi

# 统计Gunicorn命令数量（应该有3个：gateway-public, gateway-ops, gateway-internal）
gunicorn_count=$(grep -c "gunicorn" docker-compose.production.yml)
if [ "$gunicorn_count" -ge 3 ]; then
    echo "✅ 所有Gateway服务（public/ops/internal）都使用Gunicorn"
else
    echo "❌ 只有 $gunicorn_count 个Gateway服务使用Gunicorn（预期3个）"
    exit 1
fi
echo ""

# 5. 验证健康检查支持密钥文件读取
echo "5. 验证健康检查支持密钥文件读取..."
if grep -q "with open(minio_user_file)" external-systems/partner-http-gateway/gateway/health_check.py; then
    echo "✅ MinIO健康检查支持密钥文件读取"
else
    echo "❌ MinIO健康检查不支持密钥文件"
    exit 1
fi

if grep -q "with open(password_file)" external-systems/partner-http-gateway/gateway/health_check.py; then
    echo "✅ Redis健康检查支持密钥文件读取"
else
    echo "❌ Redis健康检查不支持密钥文件"
    exit 1
fi
echo ""

# 6. 验证密钥文件存在
echo "6. 验证密钥文件存在..."
if [ -d "secrets" ]; then
    echo "✅ secrets目录存在"

    # 验证密钥文件权限
    for file in secrets/*.txt; do
        if [ -f "$file" ]; then
            perms=$(stat -f "%OLp" "$file" 2>/dev/null || stat -c "%a" "$file" 2>/dev/null)
            if [ "$perms" = "600" ]; then
                echo "✅ $(basename $file) 权限正确（600）"
            else
                echo "⚠️  $(basename $file) 权限为 $perms（预期600）"
            fi
        fi
    done
else
    echo "❌ secrets目录不存在"
    exit 1
fi
echo ""

# 7. 验证密钥强度
echo "7. 验证密钥强度..."
mysql_password=$(cat secrets/mysql_root_password.txt 2>/dev/null || echo "")
if [ ${#mysql_password} -ge 32 ]; then
    echo "✅ MySQL密码长度符合要求（${#mysql_password}字符）"
else
    echo "❌ MySQL密码长度不足（${#mysql_password}字符，预期≥32）"
    exit 1
fi

minio_password=$(cat secrets/minio_root_password.txt 2>/dev/null || echo "")
if [ ${#minio_password} -ge 32 ]; then
    echo "✅ MinIO密码长度符合要求（${#minio_password}字符）"
else
    echo "❌ MinIO密码长度不足（${#minio_password}字符，预期≥32）"
    exit 1
fi
echo ""

echo "========================================="
echo "✅ 所有验证通过！架构修复已完成"
echo "========================================="
echo ""
echo "下一步建议："
echo "1. 运行: pip install -e .[dev]  安装新依赖（gunicorn, gevent）"
echo "2. 运行: docker compose -f docker-compose.production.yml build  构建镜像"
echo "3. 运行: docker compose -f docker-compose.production.yml up -d  启动服务"
echo "4. 验证: curl http://localhost:8080/health  检查Gateway健康状态"
echo "5. 验证: curl http://localhost:9090/health  检查Scheduler健康状态"