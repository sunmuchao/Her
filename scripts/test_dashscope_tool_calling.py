#!/usr/bin/env python3
"""
测试 DashScope 模型是否支持同时使用 response_format: json_schema 和 tools。

运行方式：
  python scripts/test_dashscope_tool_calling.py

测试三种场景：
  1. 只有 tools（没有 response_format）
  2. 只有 response_format: json_schema（没有 tools）
  3. 同时使用 response_format: json_schema + tools
"""

import json
import os
from openai import OpenAI


def load_env():
    """从 .env 文件加载环境变量"""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()


load_env()

API_KEY = os.environ.get("HER_DISCOVERY_AGENT_API_KEY", "")
BASE_URL = os.environ.get("HER_DISCOVERY_AGENT_BASE_URL", "")
MODEL = os.environ.get("HER_DISCOVERY_AGENT_MODEL", "qwen-max")

print(f"=== 测试配置 ===")
print(f"API URL: {BASE_URL}")
print(f"API Key: {API_KEY[:10]}...{API_KEY[-10:]}")
print(f"Model: {MODEL}")
print()

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


# 定义一个简单的测试工具
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_candidates",
            "description": "搜索候选人。当用户说'找对象'、'推荐'时调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "criteria": {"type": "string", "description": "搜索条件"}
                },
                "required": ["criteria"]
            }
        }
    }
]

# 简单的 JSON schema
JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "test_output",
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {
                "phase": {"type": "string", "enum": ["searching", "results_shown"]},
                "message": {"type": "string"}
            },
            "required": ["phase", "message"]
        }
    }
}

TEST_PROMPT = """用户说：我要找对象，你给我推荐几个合适的。

请调用 search_candidates 工具来搜索候选人。"""


def test_case(name: str, use_tools: bool, use_json_schema: bool):
    """测试一个场景"""
    print(f"=== 测试场景: {name} ===")

    request_params = {
        "model": MODEL,
        "messages": [{"role": "user", "content": TEST_PROMPT}],
    }

    if use_tools:
        request_params["tools"] = TOOLS

    if use_json_schema:
        request_params["response_format"] = JSON_SCHEMA

    print(f"请求参数:")
    print(f"  - tools: {'是' if use_tools else '否'}")
    print(f"  - response_format: {'json_schema' if use_json_schema else '否'}")
    print()

    try:
        response = client.chat.completions.create(**request_params)

        # 检查是否有 tool_calls
        message = response.choices[0].message
        has_tool_call = message.tool_calls is not None and len(message.tool_calls) > 0

        print(f"响应结果:")
        print(f"  - 调用了工具: {'✅ 是' if has_tool_call else '❌ 否'}")

        if has_tool_call:
            for tc in message.tool_calls:
                print(f"  - 工具名称: {tc.function.name}")
                print(f"  - 工具参数: {tc.function.arguments}")

        if message.content:
            print(f"  - 文本内容: {message.content[:200]}...")

        print()
        return has_tool_call

    except Exception as e:
        print(f"  - 错误: {type(e).__name__}: {str(e)[:200]}")
        print()
        return False


# 运行测试
print("=" * 60)
print("开始测试 DashScope 模型的 tool calling + json_schema 支持")
print("=" * 60)
print()

# 测试 1: 只有 tools
result1 = test_case("1. 只有 tools（没有 response_format）", use_tools=True, use_json_schema=False)

# 测试 2: 只有 json_schema
result2 = test_case("2. 只有 response_format: json_schema（没有 tools）", use_tools=False, use_json_schema=True)

# 测试 3: 同时使用
result3 = test_case("3. 同时使用 tools + response_format: json_schema", use_tools=True, use_json_schema=True)

# 总结
print("=" * 60)
print("测试总结")
print("=" * 60)
print(f"场景 1（只有 tools）: {'✅ 工具调用成功' if result1 else '❌ 工具调用失败'}")
print(f"场景 2（只有 json_schema）: {'（此场景不涉及工具调用）'}")
print(f"场景 3（同时使用）: {'✅ 工具调用成功' if result3 else '❌ 工具调用失败 - 这就是问题所在！'}")
print()

if result1 and not result3:
    print("结论: DashScope 模型不支持同时使用 response_format: json_schema 和 tools")
    print("建议: 移除 response_format，只用 tools 来实现 tool calling")
elif result3:
    print("结论: DashScope 模型支持同时使用 response_format: json_schema 和 tools")
else:
    print("结论: DashScope 模型在当前配置下不支持 tool calling，请检查模型和 API 配置")