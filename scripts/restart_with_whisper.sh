#!/usr/bin/env bash
#
# 智能一键启动脚本 - 自动检测并下载 Whisper 模型
#
# 功能：
# 1. 停止本地服务栈
# 2. 检测 Whisper 模型是否已下载
# 3. 如果未下载，自动下载模型（使用镜像）
# 4. 启动本地服务栈
#
# Usage:
#   ./scripts/restart_with_whisper.sh [--with-scheduler]
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
VENV_PY="${VENV_DIR}/bin/python"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

WITH_SCHEDULER=0

usage() {
  cat <<'EOF'
Usage: scripts/restart_with_whisper.sh [--with-scheduler]

智能一键启动脚本，自动检测并下载 Whisper 模型：

  1. 停止本地服务栈
  2. 检测 Whisper 模型是否已下载
  3. 自动下载模型（如果未下载）
  4. 启动本地服务栈

参数：
  --with-scheduler  启动任务调度器（可选）

日志位置：.run/logs/
PID 文件：.run/pids/
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-scheduler)
      WITH_SCHEDULER=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

echo ""
echo "======================================================================"
echo "智能一键启动脚本 - Whisper 语音识别集成"
echo "======================================================================"
echo ""

# 检查虚拟环境
if [[ ! -x "${VENV_PY}" ]]; then
  echo "${RED}✗ Python 虚拟环境不存在${NC}"
  echo ""
  echo "请先运行开发环境设置脚本："
  echo "  bash scripts/dev_setup.sh"
  exit 1
fi

echo "${GREEN}✓ Python 虚拟环境已就绪${NC}"
echo ""

# 步骤 1：停止本地服务栈
echo "${BLUE}步骤 1：停止本地服务栈${NC}"
echo "----------------------------------------------------------------------"
bash "${SCRIPT_DIR}/stop_local_stack.sh"
echo ""

# 步骤 2：检测 Whisper 模型
echo "${BLUE}步骤 2：检测 Whisper 模型${NC}"
echo "----------------------------------------------------------------------"

# 读取环境变量中的模型大小配置
MODEL_SIZE="small"  # 默认使用 small 模型
if [[ -f "${REPO_ROOT}/.env" ]]; then
  MODEL_SIZE=$(grep WHISPER_MODEL_SIZE "${REPO_ROOT}/.env" 2>/dev/null | cut -d'=' -f2 | tr -d ' ' || echo "small")
fi

# 模型缓存目录
CACHE_DIR="$HOME/.cache/huggingface/hub/models--Systran--faster-whisper-${MODEL_SIZE}"

echo "模型大小配置: ${MODEL_SIZE}"
echo "模型缓存目录: ${CACHE_DIR}"

# 检查模型是否已下载
if [[ -d "${CACHE_DIR}/snapshots" ]]; then
  # 检查是否有实际的模型文件
  SNAPSHOT_COUNT=$(find "${CACHE_DIR}/snapshots" -type f -name "*.bin" 2>/dev/null | wc -l)

  if [[ ${SNAPSHOT_COUNT} -gt 0 ]]; then
    echo "${GREEN}✓ Whisper 模型已存在 (${SNAPSHOT_COUNT} 个文件)${NC}"
    echo "无需重新下载"
  else
    echo "${YELLOW}⚠ 模型目录存在但文件不完整${NC}"
    echo "需要重新下载..."
    MODEL_EXISTS=0
  fi
else
  echo "${YELLOW}⚠ Whisper 模型未下载${NC}"
  echo "开始自动下载..."
  MODEL_EXISTS=0
fi

# 步骤 3：自动下载模型（如果未存在）
if [[ ${MODEL_EXISTS:-1} -eq 0 ]]; then
  echo ""
  echo "${BLUE}步骤 3：自动下载 Whisper 模型${NC}"
  echo "----------------------------------------------------------------------"

  # 设置环境变量
  export KMP_DUPLICATE_LIB_OK=TRUE  # 修复 OpenMP 冲突

  echo "使用配置："
  echo "  - 模型大小: ${MODEL_SIZE}"
  echo "  - HF 镜像: https://hf-mirror.com"
  echo "  - 预估时间: 1-2 分钟"
  echo ""

  # 运行预热脚本
  "${VENV_PY}" "${SCRIPT_DIR}/preload_whisper_model.py"

  if [[ $? -eq 0 ]]; then
    echo ""
    echo "${GREEN}✓ Whisper 模型下载成功${NC}"
  else
    echo ""
    echo "${RED}✗ Whisper 模型下载失败${NC}"
    echo ""
    echo "可能的解决方案："
    echo "  1. 检查网络连接"
    echo "  2. 尝试其他镜像站点：export HF_ENDPOINT=https://huggingface.co"
    echo "  3. 手动下载模型：python scripts/preload_whisper_model.py"
    echo ""
    echo "${YELLOW}将继续启动服务，但语音识别功能可能需要首次下载模型${NC}"
  fi
else
  echo ""
  echo "${BLUE}步骤 3：跳过模型下载（已存在）${NC}"
  echo "----------------------------------------------------------------------"
fi

# 步骤 4：启动本地服务栈
echo ""
echo "${BLUE}步骤 4：启动本地服务栈${NC}"
echo "----------------------------------------------------------------------"

SCHEDULER_ARG=""
if [[ "${WITH_SCHEDULER}" == "1" ]]; then
  SCHEDULER_ARG="--with-scheduler"
fi

bash "${SCRIPT_DIR}/start_local_stack.sh" ${SCHEDULER_ARG}

echo ""
echo "======================================================================"
echo "${GREEN}✅ 智能启动完成${NC}"
echo "======================================================================"
echo ""
echo "服务状态："
echo "  - MySQL:         运行中"
echo "  - SSE Server:     运行中 (http://127.0.0.1:8081)"
echo "  - Gateway:        运行中 (http://127.0.0.1:8765)"
echo "  - Frontend:       运行中 (http://127.0.0.1:3000)"
if [[ "${WITH_SCHEDULER}" == "1" ]]; then
  echo "  - Scheduler:      运行中"
fi
echo ""
echo "Whisper 语音识别："
if [[ -d "${CACHE_DIR}/snapshots" ]]; then
  echo "  - 状态: ${GREEN}已就绪${NC}（模型已缓存）"
  echo "  - 可以立即使用语音识别功能"
else
  echo "  - 状态: ${YELLOW}首次使用时需要下载${NC}"
  echo "  - 建议：手动运行 python scripts/preload_whisper_model.py"
fi
echo ""
echo "日志位置："
echo "  - Gateway:  ${REPO_ROOT}/.run/logs/gateway.log"
echo "  - Frontend: ${REPO_ROOT}/.run/logs/frontend.log"
echo ""
echo "下一步："
echo "  1. 打开浏览器访问 http://127.0.0.1:3000"
echo "  2. 进入发现页测试语音识别"
echo "  3. 按住麦克风说话，松开自动发送"
echo ""