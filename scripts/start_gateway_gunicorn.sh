#!/bin/bash
# Gateway 启动脚本 - 使用 Gunicorn 并正确加载 .env

cd /Users/sunmuchao/Downloads/Her

# 使用 python-dotenv 加载 .env（避免 export 问题）
echo "加载 .env 配置..."
python3 -c "
import os
import sys
from pathlib import Path
try:
    from dotenv import load_dotenv
    env_path = Path('.env')
    if env_path.exists():
        load_dotenv(env_path, override=True)
        print('✅ .env 已加载')
    else:
        print('❌ .env 文件不存在')
        sys.exit(1)
except ImportError:
    print('⚠️ python-dotenv 未安装，使用环境变量')
"

# 启动 Gunicorn
cd external-systems/partner-http-gateway

echo "启动 Gunicorn Gateway..."
nohup gunicorn -c gunicorn_config.py gateway.app:application > ../../.run/logs/gunicorn.log 2>&1 &

echo "等待 5 秒验证..."
sleep 5

# 检查进程
if ps aux | grep -q "[g]unicorn"; then
    echo "✅ Gunicorn 已启动"
    ps aux | grep gunicorn | grep -v grep | wc -l | xargs echo "Worker 进程数量:"

    # 测试 API
    echo "测试 API 连接..."
    if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8765/v1/profile/me?profile_id=2478 | grep -q "200"; then
        echo "✅ API 正常响应"
    else
        echo "⚠️ API 返回非 200 状态码"
    fi
else
    echo "❌ Gunicorn 启动失败，查看日志："
    tail -20 ../../.run/logs/gunicorn_error.log
fi