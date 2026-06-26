#!/bin/bash

# 推荐来信已读状态测试执行脚本
# 用法：./scripts/test-recommendation-read-state.sh [phase]

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$PROJECT_ROOT/frontend/her-app"

echo "========================================="
echo "推荐来信已读状态测试"
echo "========================================="
echo ""

# 检查参数
PHASE="${1:-all}"

case "$PHASE" in
  "unit"|"1")
    echo "Phase 1: 单元测试（快速验证核心逻辑）"
    echo ""
    cd "$FRONTEND_DIR"

    echo "运行单元测试..."
    npm run test:unit tests/unit/recommendation-read-state.test.ts

    echo ""
    echo "✅ Phase 1 完成：单元测试通过"
    echo ""
    ;;

  "e2e"|"2")
    echo "Phase 2: E2E 测试（完整流程验证）"
    echo ""

    cd "$FRONTEND_DIR"

    echo "启动测试环境..."
    # 启动开发服务器（如果未启动）
    if ! curl -s http://localhost:3000 > /dev/null 2>&1; then
      echo "启动开发服务器..."
      npm run dev &
      DEV_PID=$!
      sleep 10
    fi

    echo "运行 E2E 测试..."
    npm run test:e2e tests/e2e/recommendation-read-state.spec.ts

    # 关闭开发服务器
    if [ ! -z "$DEV_PID" ]; then
      echo "关闭开发服务器..."
      kill $DEV_PID
    fi

    echo ""
    echo "✅ Phase 2 完成：E2E 测试通过"
    echo ""
    ;;

  "edge"|"3")
    echo "Phase 3: 边缘场景测试（手动验证）"
    echo ""

    echo "请手动验证以下边缘场景："
    echo ""
    echo "场景 4.1：API 失败处理"
    echo "  1. Mock API 返回错误"
    echo "  2. 点击推荐卡片"
    echo "  3. 验证红色提醒不消失"
    echo "  4. 验证错误提示显示"
    echo ""
    echo "场景 4.4：组件卸载场景"
    echo "  1. 点击卡片后立即返回上一页"
    echo "  2. 验证徽章计数更新"
    echo "  3. 验证无内存泄漏"
    echo ""
    echo "场景 5.1：大量未读卡片性能"
    echo "  1. 创建 100 个未读推荐卡片"
    echo "  2. 验证页面渲染性能"
    echo "  3. 验证点击响应速度"
    echo ""
    echo "场景 5.2：高频刷新性能"
    echo "  1. 快速连续点击 10 个卡片"
    echo "  2. 验证性能正常"
    echo "  3. 验证无重复 API 调用"
    echo ""
    ;;

  "all")
    echo "运行所有测试阶段"
    echo ""

    # Phase 1
    echo "========================================="
    echo "Phase 1: 单元测试"
    echo "========================================="
    cd "$FRONTEND_DIR"
    npm run test:unit tests/unit/recommendation-read-state.test.ts

    echo ""
    echo "✅ Phase 1 完成"
    echo ""

    # Phase 2
    echo "========================================="
    echo "Phase 2: E2E 测试"
    echo "========================================="

    # 启动开发服务器
    if ! curl -s http://localhost:3000 > /dev/null 2>&1; then
      echo "启动开发服务器..."
      npm run dev &
      DEV_PID=$!
      sleep 10
    fi

    npm run test:e2e tests/e2e/recommendation-read-state.spec.ts

    if [ ! -z "$DEV_PID" ]; then
      kill $DEV_PID
    fi

    echo ""
    echo "✅ Phase 2 完成"
    echo ""

    # Phase 3
    echo "========================================="
    echo "Phase 3: 边缘场景测试（手动验证）"
    echo "========================================="
    echo ""
    echo "请参考测试场景文档进行手动验证："
    echo "memory/recommendation-read-state-test-scenarios.md"
    echo ""

    echo "========================================="
    echo "✅ 所有测试阶段完成"
    echo "========================================="
    ;;

  *)
    echo "错误：未知阶段 '$PHASE'"
    echo ""
    echo "用法："
    echo "  $0 unit    # 只运行单元测试"
    echo "  $0 e2e     # 只运行 E2E 测试"
    echo "  $0 edge    # 边缘场景测试指南"
    echo "  $0 all     # 运行所有测试"
    echo ""
    exit 1
    ;;
esac

echo ""
echo "测试报告："
echo "  单元测试：tests/unit/recommendation-read-state.test.ts"
echo "  E2E 测试：tests/e2e/recommendation-read-state.spec.ts"
echo "  测试场景：memory/recommendation-read-state-test-scenarios.md"
echo ""