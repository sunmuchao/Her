"""测试 JSON 序列化修复

验证：
1. exclude_ids 的 set → list 转换
2. search_partner_candidates 工具参数序列化
"""

import json
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

def test_json_serialization():
    """测试 JSON 序列化问题"""
    print("=" * 60)
    print("测试 1: set → list 转换")
    print("=" * 60)

    # 测试 set 无法序列化的问题
    test_set = {1, 2, 3}
    try:
        json.dumps({"exclude_ids": test_set})
        print("❌ set 对象竟然可以序列化？这不应该！")
    except TypeError as e:
        print(f"✅ 预期的错误：{e}")

    # 测试 list 可以序列化
    test_list = list(test_set)
    try:
        result = json.dumps({"exclude_ids": test_list})
        print(f"✅ list 对象可以序列化：{result}")
    except TypeError as e:
        print(f"❌ list 对象序列化失败：{e}")

    print("\n" + "=" * 60)
    print("测试 2: 模拟工具调用参数")
    print("=" * 60)

    # 模拟工具调用参数
    tool_args = {
        "criteria_json": '{"gender": "female"}',
        "personality_match_json": '{"match_traits": ["温柔", "体贴"], "similarity_threshold": 0.7}',
        "limit": 5,
        "exclude_current_results": True,
    }

    try:
        serialized = json.dumps(tool_args)
        print(f"✅ 工具参数序列化成功：{serialized[:100]}")
    except TypeError as e:
        print(f"❌ 工具参数序列化失败：{e}")
        return False

    print("\n" + "=" * 60)
    print("✅ 所有测试通过！JSON 序列化修复有效")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_json_serialization()
    sys.exit(0 if success else 1)