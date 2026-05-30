#!/bin/bash
# Gateway 启动脚本 - 使用 Gunicorn 并正确加载 .env

cd /Users/sunmuchao/Downloads/Her

# 加载 .env 文件
if [ -f .env ]; then
    echo "加载 .env 配置..."
    export $(grep -v '^#' .env | xargs)
fi

# 启动 Gunicorn
cd external-systems/partner-http-gateway

echo "启动 Gunicorn Gateway..."
nohup gunicorn -c gunicorn_config.py gateway.app:application > ../../.run/logs/gunicorn.log 2>&1 &

echo "等待 3 秒验证..."
sleep 3

# 检查进程
if ps aux | grep -q "[g]unicorn"; then
    echo "✅ Gunicorn 已启动"
    ps aux | grep gunicorn | grep -v grep | wc -l | xargs echo "Worker 进程数量:"
else
    echo "❌ Gunicorn 启动失败"
fi