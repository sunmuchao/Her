#!/bin/bash

# 快速验证脚本：测试 discovery_system.service 修复

set -e

echo "========================================"
echo "测试 discovery_system.service 修复"
echo "========================================"
echo ""

echo "1️⃣  运行基础测试..."
python -m pytest tests/test_discovery_service_fixes.py -v --tb=short

echo ""
echo "2️⃣  运行端到端测试..."
python -m pytest tests/test_discovery_service_fixes_e2e.py -v --tb=short

echo ""
echo "========================================"
echo "✅ 所有测试通过！"
echo "========================================"
echo ""
echo "测试文件："
echo "  - tests/test_discovery_service_fixes.py (15个测试)"
echo "  - tests/test_discovery_service_fixes_e2e.py (17个测试)"
echo ""
echo "测试报告："
echo "  - tests/TEST_REPORT_DISCOVERY_SERVICE_FIXES.md"
echo ""