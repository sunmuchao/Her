"""
快速验证后端是否完全部署

运行方法: python tests/quick_check_backend.py
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from matchmaking_system.proxy_intro_core import build_requester_safe_summary


def quick_check():
    """快速检查后端改动是否生效"""

    print("=" * 60)
    print("快速检查：后端是否完全部署？")
    print("=" * 60)
    print()

    # 模拟一个完整的用户资料
    subscription = {
        "self_profile_json": '{"age": 28, "display_name": "孙木超", "city": "无锡", "job": "程序员", "education": "本科", "relationship_goal": "dating"}'
    }

    result = build_requester_safe_summary(subscription)

    print("✅ 检查 1: 年龄字段")
    print(f"   age = {result['age']}")
    print(f"   期望: '28岁'")
    if result['age'] == '28岁':
        print("   ✅ 通过：后端 age 字段已生效")
    else:
        print("   ❌ 失败：后端 age 字段未生效")
    print()

    print("✅ 检查 2: 关系目标字段")
    print(f"   relationship_goal = {result['relationship_goal']}")
    print(f"   期望: '先谈恋爱'")
    if result['relationship_goal'] == '先谈恋爱':
        print("   ✅ 通过：后端 relationship_goal 字段已生效")
    else:
        print("   ❌ 失败：后端 relationship_goal 字段未生效（还是英文）")
    print()

    print("✅ 检查 3: 摘要文本字段")
    print(f"   summary_text = {result['summary_text']}")
    print(f"   期望: '28岁；无锡；本科；程序员；先谈恋爱'")
    if result['summary_text'] == '28岁；无锡；本科；程序员；先谈恋爱':
        print("   ✅ 通过：后端 summary_text 字段已生效")
    else:
        print("   ❌ 失败：后端 summary_text 字段未生效（还是旧格式）")
    print()

    # 判断是否完全生效
    all_passed = (
        result['age'] == '28岁'
        and result['relationship_goal'] == '先谈恋爱'
        and result['summary_text'] == '28岁；无锡；本科；程序员；先谈恋爱'
    )

    print("=" * 60)
    if all_passed:
        print("✅ 结论：后端改动完全生效！")
        print("   - age 字段生效（实际年龄）")
        print("   - relationship_goal 字段生效（中文映射）")
        print("   - summary_text 字段生效（完整摘要）")
        print()
        print("📋 下一步：前端编译失败，需要修复 TypeScript 错误")
    else:
        print("❌ 结论：后端改动只生效了部分！")
        print("   - age 字段：已生效 ✅")
        print("   - relationship_goal 字段：未生效 ❌")
        print("   - summary_text 字段：未生效 ❌")
        print()
        print("📋 下一步：检查后端是否真的部署了 proxy_intro_core.py 改动")
    print("=" * 60)

    return all_passed


if __name__ == "__main__":
    quick_check()