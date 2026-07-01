#!/bin/bash

# 智能重建脚本：只重建修改过的服务

echo "=== 智能重建脚本 ==="

# 检测修改过的服务
MODIFIED_SERVICES=""

# 检查 SSE Server 是否修改
if git diff --name-only HEAD~1 | grep -q "external-systems/sse-server"; then
    echo "✓ SSE Server 有修改"
    MODIFIED_SERVICES="$MODIFIED_SERVICES sse-server"
fi

# 检查 Discovery/Matchmaking/Recommendation 是否修改
if git diff --name-only HEAD~1 | grep -qE "partner-discovery-system|partner-matchmaking-system|partner-recommendation-system"; then
    echo "✓ Gateway 相关服务有修改"
    MODIFIED_SERVICES="$MODIFIED_SERVICES gateway-public gateway-internal gateway-ops"
fi

# 检查前端是否修改
if git diff --name-only HEAD~1 | grep -q "frontend"; then
    echo "✓ 前端有修改"
    MODIFIED_SERVICES="$MODIFIED_SERVICES frontend"
fi

# 如果有修改的服务
if [ -n "$MODIFIED_SERVICES" ]; then
    echo ""
    echo "重建服务: $MODIFIED_SERVICES"
    
    # 停止服务
    docker compose stop $MODIFIED_SERVICES
    
    # 重建服务（利用缓存）
    docker compose build $MODIFIED_SERVICES
    
    # 重启服务
    docker compose up -d $MODIFIED_SERVICES
    
    echo ""
    echo "=== 重建完成 ==="
    docker compose ps $MODIFIED_SERVICES
else
    echo "没有检测到修改的服务"
fi
