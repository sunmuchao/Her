#!/bin/bash
# 设置百炼API环境变量（用于发现页Agent）

# 方案1：设置DASHSCOPE_API_KEY（推荐）
# 这样base_url解析函数会自动推断使用百炼API URL
export DASHSCOPE_API_KEY="${HER_DISCOVERY_AGENT_API_KEY:-${OPENAI_API_KEY:-sk-ovzhkaH...}}"

# 方案2：直接设置HER_DISCOVERY_AGENT_BASE_URL（可选）
# 如果方案1不生效，可以直接设置base_url
export HER_DISCOVERY_AGENT_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"

echo "✅ 百炼API环境变量已设置"
echo "DASHSCOPE_API_KEY: ${DASHSCOPE_API_KEY:0:10}..."
echo "HER_DISCOVERY_AGENT_BASE_URL: ${HER_DISCOVERY_AGENT_BASE_URL}"