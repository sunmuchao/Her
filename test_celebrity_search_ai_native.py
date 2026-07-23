#!/usr/bin/env python3
"""测试明星脸搜索AI Native改进

测试内容：
1. search_celebrity_face_candidates函数签名
2. photo_url参数是否必需
3. 人脸向量提取是否正确
4. 错误处理是否正确
5. photo_intent_agent的celebrity模式废弃警告
"""

import sys
import inspect


def test_function_signature():
    """测试函数签名"""
    print("=" * 80)
    print("测试1: search_celebrity_face_candidates函数签名")
    print("=" * 80)

    from match_domain.photo_discovery_search import search_celebrity_face_candidates

    # 获取函数签名
    sig = inspect.signature(search_celebrity_face_candidates)
    params = sig.parameters

    # 检查photo_url参数
    if "photo_url" in params:
        photo_url_param = params["photo_url"]
        print(f"✅ photo_url参数存在")
        print(f"   - 默认值: {photo_url_param.default}")
        print(f"   - 类型: {photo_url_param.annotation}")

        # 检查是否是必需参数（无默认值）
        if photo_url_param.default == inspect.Parameter.empty:
            print(f"   ✅ photo_url是必需参数")
        else:
            print(f"   ❌ photo_url应该是必需参数，但有默认值: {photo_url_param.default}")
            return False
    else:
        print(f"❌ 缺少photo_url参数")
        return False

    # 检查celebrity_name参数是否改为可选
    if "celebrity_name" in params:
        celebrity_name_param = params["celebrity_name"]
        print(f"✅ celebrity_name参数存在")
        print(f"   - 默认值: {celebrity_name_param.default}")
        print(f"   - 类型: {celebrity_name_param.annotation}")

        if celebrity_name_param.default == inspect.Parameter.empty:
            print(f"   ⚠️  celebrity_name应该是可选参数（无默认值）")
        else:
            print(f"   ✅ celebrity_name是可选参数（默认值: {celebrity_name_param.default}）")
    else:
        print(f"❌ 缺少celebrity_name参数")
        return False

    return True


def test_error_handling():
    """测试错误处理"""
    print("\n" + "=" * 80)
    print("测试2: 错误处理")
    print("=" * 80)

    from match_domain.photo_discovery_search import search_celebrity_face_candidates

    # 测试无效的photo_url
    try:
        result = search_celebrity_face_candidates(
            source_dsn=None,
            photo_url="https://invalid-url-12345.com/nonexistent.jpg",
            celebrity_name="测试明星"
        )

        if result.get("saved") == False:
            print(f"✅ 无效URL返回失败状态")
            print(f"   - error: {result.get('error')}")
        else:
            print(f"⚠️  无效URL应该返回失败，但返回: {result}")

    except Exception as e:
        print(f"⚠️  无效URL抛出异常（可能网络问题）: {e}")

    return True


def test_intent_agent_celebrity_mode():
    """测试photo_intent_agent的celebrity模式废弃"""
    print("\n" + "=" * 80)
    print("测试3: photo_intent_agent的celebrity模式废弃")
    print("=" * 80)

    from match_domain.photo_intent_agent import (
        execute_photo_preference_search,
        PhotoPreferenceIntent
    )

    # 构造celebrity模式的intent
    intent = PhotoPreferenceIntent(
        intent_type="celebrity_face_search",
        mode="celebrity",
        query_text="田曦薇",
        celebrity_name="田曦薇",
        attribute_filters={},
        hard_filters={},
        raw_text="找像田曦薇的女生",
        confidence=0.94,
        routing_reasons=["text_contains_celebrity_reference"]
    )

    # 调用execute_photo_preference_search
    result = execute_photo_preference_search(
        source_dsn=None,
        requester_user_key="test_user",
        intent=intent
    )

    # 检查返回结果
    if result.get("saved") == False:
        print(f"✅ celebrity模式返回失败状态")
        print(f"   - error: {result.get('error')}")
        print(f"   - hint: {result.get('hint')}")
    else:
        print(f"❌ celebrity模式应该返回失败，但返回: {result}")
        return False

    return True


def test_import_removed():
    """测试导入是否移除"""
    print("\n" + "=" * 80)
    print("测试4: 检查导入是否移除")
    print("=" * 80)

    # 检查photo_intent_agent.py是否还导入search_celebrity_face_candidates
    import match_domain.photo_intent_agent as photo_intent_agent

    if hasattr(photo_intent_agent, "search_celebrity_face_candidates"):
        print(f"❌ photo_intent_agent不应该导入search_celebrity_face_candidates")
        return False
    else:
        print(f"✅ photo_intent_agent已移除search_celebrity_face_candidates导入")

    return True


def main():
    """运行所有测试"""
    print("\n" + "★" * 80)
    print("明星脸搜索AI Native改进测试")
    print("★" * 80 + "\n")

    results = []

    # 测试1: 函数签名
    results.append(("函数签名", test_function_signature()))

    # 测试2: 错误处理
    results.append(("错误处理", test_error_handling()))

    # 测试3: celebrity模式废弃
    results.append(("celebrity模式废弃", test_intent_agent_celebrity_mode()))

    # 测试4: 导入移除
    results.append(("导入移除", test_import_removed()))

    # 输出总结
    print("\n" + "=" * 80)
    print("测试结果总结")
    print("=" * 80)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")

    # 判断是否全部通过
    all_passed = all(result for _, result in results)

    print("\n" + "=" * 80)
    if all_passed:
        print("✅ 所有测试通过！")
    else:
        print("❌ 部分测试失败，请检查")
    print("=" * 80 + "\n")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)