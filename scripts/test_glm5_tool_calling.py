"""测试 glm-5 模型是否支持 json_schema + tool calling 组合。

测试场景：
1. 只使用 tool calling（没有 json_schema）
2. 只使用 json_schema（没有 tool calling）
3. 同时使用 json_schema + tool calling

运行方式：
python scripts/test_glm5_tool_calling.py
"""

import json
import os
import sys

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from her_env import env_first

# 配置 glm-5 API
GLM5_API_KEY = env_first(
    "HER_DISCOVERY_AGENT_API_KEY",
    "DASHSCOPE_API_KEY",
    "OPENAI_API_KEY",
)
GLM5_BASE_URL = "https://coding.dashscope.aliyuncs.com/v1"
GLM5_MODEL = "glm-5"


def test_tool_calling_only():
    """测试场景1：只使用 tool calling（没有 json_schema）"""
    print("\n" + "=" * 60)
    print("测试场景1：只使用 tool calling（没有 json_schema）")
    print("=" * 60)

    from openai import OpenAI

    client = OpenAI(api_key=GLM5_API_KEY, base_url=GLM5_BASE_URL)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_candidates",
                "description": "搜索候选人。当用户说'找对象'、'推荐几个'时调用此工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "criteria": {"type": "string", "description": "搜索条件 JSON"},
                    },
                    "required": ["criteria"],
                },
            },
        }
    ]

    response = client.chat.completions.create(
        model=GLM5_MODEL,
        messages=[
            {"role": "system", "content": "你是 AI 红娘。当用户说'找对象'时，调用 search_candidates 工具。"},
            {"role": "user", "content": "我要找对象，你给我推荐几个合适的吧"},
        ],
        tools=tools,
        stream=False,
    )

    message = response.choices[0].message

    print(f"\n模型响应:")
    print(f"  content: {message.content}")
    print(f"  tool_calls: {message.tool_calls}")

    has_tool_call = message.tool_calls is not None and len(message.tool_calls) > 0

    if has_tool_call:
        print(f"\n✅ 成功：模型调用了工具")
        for tc in message.tool_calls:
            print(f"  - 工具名: {tc.function.name}")
            print(f"  - 参数: {tc.function.arguments}")
    else:
        print(f"\n❌ 失败：模型没有调用工具，直接返回了文本")

    return has_tool_call


def test_json_schema_only():
    """测试场景2：只使用 json_schema（没有 tool calling）"""
    print("\n" + "=" * 60)
    print("测试场景2：只使用 json_schema（没有 tool calling）")
    print("=" * 60)

    from openai import OpenAI

    client = OpenAI(api_key=GLM5_API_KEY, base_url=GLM5_BASE_URL)

    json_schema = {
        "name": "decision",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "phase": {"type": "string", "enum": ["searching", "results_shown"]},
                "message": {"type": "string"},
            },
            "required": ["phase", "message"],
            "additionalProperties": False,
        },
    }

    response = client.chat.completions.create(
        model=GLM5_MODEL,
        messages=[
            {"role": "system", "content": "你是 AI 红娘。用户说找对象时，phase 设为 searching。"},
            {"role": "user", "content": "我要找对象，你给我推荐几个合适的吧"},
        ],
        response_format={"type": "json_schema", "json_schema": json_schema},
        stream=False,
    )

    message = response.choices[0].message

    print(f"\n模型响应:")
    print(f"  content: {message.content[:200] if message.content else None}")

    try:
        parsed = json.loads(message.content) if message.content else None
        print(f"\n解析后的 JSON:")
        print(f"  {json.dumps(parsed, indent=2)}")
        print(f"\n✅ 成功：模型输出了符合 schema 的 JSON")
        return True
    except json.JSONDecodeError as e:
        print(f"\n❌ 失败：JSON 解析失败 - {e}")
        return False


def test_json_schema_with_tool_calling():
    """测试场景3：同时使用 json_schema + tool calling"""
    print("\n" + "=" * 60)
    print("测试场景3：同时使用 json_schema + tool calling")
    print("=" * 60)

    from openai import OpenAI

    client = OpenAI(api_key=GLM5_API_KEY, base_url=GLM5_BASE_URL)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_candidates",
                "description": "搜索候选人。当用户说'找对象'、'推荐几个'时调用此工具。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "criteria": {"type": "string", "description": "搜索条件 JSON"},
                    },
                    "required": ["criteria"],
                },
            },
        }
    ]

    json_schema = {
        "name": "decision",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "phase": {"type": "string", "enum": ["searching", "results_shown"]},
                "message": {"type": "string"},
                "selected_candidates": {"type": "array", "items": {"type": "object"}},
            },
            "required": ["phase", "message", "selected_candidates"],
            "additionalProperties": False,
        },
    }

    response = client.chat.completions.create(
        model=GLM5_MODEL,
        messages=[
            {
                "role": "system",
                "content": "你是 AI 红娘。当用户说'找对象'时：\n1. 先调用 search_candidates 工具搜索\n2. 然后输出 JSON：phase=searching，message=搜索结果摘要，selected_candidates=[]",
            },
            {"role": "user", "content": "我要找对象，你给我推荐几个合适的吧"},
        ],
        tools=tools,
        response_format={"type": "json_schema", "json_schema": json_schema},
        stream=False,
    )

    message = response.choices[0].message

    print(f"\n模型响应:")
    print(f"  content: {message.content[:200] if message.content else None}")
    print(f"  tool_calls: {message.tool_calls}")

    has_tool_call = message.tool_calls is not None and len(message.tool_calls) > 0

    # 尝试解析 JSON
    try:
        parsed = json.loads(message.content) if message.content else None
        print(f"\n解析后的 JSON:")
        print(f"  {json.dumps(parsed, indent=2)[:200]}")

        # 检查 selected_candidates 是否是数组
        if parsed and "selected_candidates" in parsed:
            if parsed["selected_candidates"] is None:
                print(f"\n❌ 失败：selected_candidates 是 null，应该是数组")
            elif isinstance(parsed["selected_candidates"], list):
                print(f"\n✅ selected_candidates 是数组")
            else:
                print(f"\n❌ 失败：selected_candidates 类型错误: {type(parsed['selected_candidates'])}")
    except json.JSONDecodeError as e:
        print(f"\n❌ JSON 解析失败: {e}")

    if has_tool_call:
        print(f"\n✅ 成功：模型调用了工具")
        for tc in message.tool_calls:
            print(f"  - 工具名: {tc.function.name}")
            print(f"  - 参数: {tc.function.arguments}")
    else:
        print(f"\n❌ 失败：模型没有调用工具")

    return has_tool_call


def main():
    print("=" * 60)
    print("glm-5 模型 tool calling + json_schema 测试")
    print("=" * 60)
    print(f"模型: {GLM5_MODEL}")
    print(f"API Base: {GLM5_BASE_URL}")

    results = {}

    # 测试场景1
    results["tool_calling_only"] = test_tool_calling_only()

    # 测试场景2
    results["json_schema_only"] = test_json_schema_only()

    # 测试场景3
    results["json_schema_with_tool_calling"] = test_json_schema_with_tool_calling()

    # 总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)

    for name, success in results.items():
        status = "✅ 支持" if success else "❌ 不支持"
        print(f"  {name}: {status}")

    print("\n结论:")
    if not results["json_schema_with_tool_calling"]:
        print("  glm-5 不支持同时使用 json_schema + tool calling")
        print("  建议方案：")
        print("  1. 升级到支持 tool calling 的模型（如 Qwen3-235B）")
        print("  2. 或者移除 json_schema，使用纯 tool calling + 自然语言输出")
    else:
        print("  glm-5 支持同时使用 json_schema + tool calling ✅")


if __name__ == "__main__":
    main()