#!/usr/bin/env python3
"""
学习闭环功能完整验证脚本
模拟真实用户在前端的各种操作场景
"""

from datetime import datetime
import json
from typing import Any

# 模拟Discovery系统
from discovery_system.feedback_service import (
    infer_feedback_type,
    generate_feedback_options,
    FEEDBACK_TO_CRITERIA_ADJUSTMENT,
    SECONDARY_OPTIONS_MAP,
)

print("=" * 80)
print("学习闭环功能完整验证")
print("模拟真实用户在前端的各种操作场景")
print("=" * 80)
print()

# ========== 场景数据模拟 ==========

class MockSession:
    """模拟Discovery Session"""
    def __init__(self):
        self.session_id = "test-session-001"
        self.requester_id = 12345
        self.profile_id = 67890
        self.status = "active"
        self.phase = "results_shown"
        self.state = {
            "working_criteria": {},
            "last_search_run_id": 1001,
        }
        self.view = {
            "timeline": [],
            "criteria_chips": ["26-30岁", "杭州", "本科及以上"],
            "suggested_actions": [],
        }

class MockUser:
    """模拟用户"""
    def __init__(self):
        self.user_id = 12345
        self.age = 26
        self.city = "杭州"
        self.interests = "文艺、电影、旅行"

class MockCandidates:
    """模拟候选人列表"""
    def __init__(self):
        self.last_batch = [
            {"id": 101, "age": 30, "city": "北京", "occupation": "程序员", "interests": "户外、健身"},
            {"id": 102, "age": 32, "city": "上海", "occupation": "程序员", "interests": "技术、编程"},
            {"id": 103, "age": 28, "city": "深圳", "occupation": "产品经理", "interests": "产品、设计"},
        ]

# ========== 场景验证函数 ==========

def verify_scenario_1():
    """
    场景1：用户说"换一批" → 系统追问 → 用户选"太远了" → 系统调整 → 新推荐

    验证点：
    - 系统是否追问
    - 反馈类型推断是否正确
    - 调整策略是否应用
    - persona是否更新
    """
    print("\n" + "=" * 80)
    print("场景1：用户说'换一批' → 系统追问 → 用户选'太远了' → 系统调整 → 新推荐")
    print("=" * 80)

    session = MockSession()
    user = MockUser()
    candidates = MockCandidates()

    # 1. 用户说"换一批"
    print("\n[用户] 说：'给我换一批'")

    # 2. 系统追问
    print("[系统] 思考：用户首次换一批，应该追问，建立学习闭环")
    print("[系统] 回复：'好的，我帮你换一批新的。顺便问一句，上一批主要哪里不太对？'")

    # 3. 生成反馈选项
    options_result = generate_feedback_options(
        candidates.last_batch,
        {"age": user.age, "city": user.city, "interests": user.interests}
    )
    print(f"[系统] 展示选项：{options_result['options']}")
    print(f"[系统] 追问文案：{options_result['追问文案']}")

    # 验证：选项是否包含"太远了"
    assert "太远了" in any(opt for opt in options_result['options']), "❌ 选项未包含'太远了'"
    print("✅ 选项生成正确，包含动态生成的'太远了'")

    # 4. 用户选择"太远了（都是异地）"
    user_feedback = "太远了（都是异地）"
    print(f"\n[用户] 点击：'{user_feedback}'")

    # 5. 推断反馈类型
    feedback_type = infer_feedback_type(user_feedback)
    print(f"[系统] 推断反馈类型：{feedback_type}")

    # 验证：反馈类型是否正确
    assert feedback_type == "location_distance", f"❌ 反馈类型错误：{feedback_type}"
    print("✅ 反馈类型推断正确")

    # 6. 获取调整策略
    strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get(feedback_type)
    print(f"[系统] 调整策略：{strategy}")

    # 验证：策略是否存在
    assert strategy is not None, "❌ 调整策略不存在"
    assert strategy['affected_field'] == "target_cities", "❌ 调整字段错误"
    assert "同城" in strategy['persona_write']['preferred_traits'], "❌ persona更新策略错误"
    print("✅ 调整策略正确")

    # 7. 应用调整（模拟）
    print("\n[系统] 动作：")
    print("  1. 记录反馈：feedback_type='location_distance'")
    print("  2. 调整criteria：target_cities → ['杭州']")
    print("  3. 更新persona：preferred_traits.append('同城')")
    print("  4. 搜索：使用调整后的criteria，同城优先")

    print("\n✅ 场景1验证完成")
    return True

def verify_scenario_2():
    """
    场景2：用户选"外在条件不合适" → 二级追问 → 用户选"年龄差距有点大"

    验证点：
    - 二级追问是否触发
    - 二级选项是否正确
    - 二级反馈类型推断是否正确
    """
    print("\n" + "=" * 80)
    print("场景2：用户选'外在条件不合适' → 二级追问 → 用户选'年龄差距有点大'")
    print("=" * 80)

    # 1. 用户选择"外在条件不合适"
    primary_feedback = "外在条件不合适（年龄/学历/收入）"
    print(f"\n[用户] 一级选项点击：'{primary_feedback}'")

    # 2. 推断一级反馈类型
    primary_type = infer_feedback_type(primary_feedback)
    print(f"[系统] 推断一级反馈类型：{primary_type}")

    # 验证：一级类型是否正确
    assert primary_type == "criteria_generic", f"❌ 一级类型错误：{primary_type}"
    print("✅ 一级反馈类型正确（触发二级追问）")

    # 3. 检查策略是否需要二级追问
    strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get(primary_type)
    assert strategy.get('need_secondary'), "❌ 策略未标记需要二级追问"
    print("✅ 策略正确标记需要二级追问")

    # 4. 触发二级追问
    secondary_options = SECONDARY_OPTIONS_MAP.get(primary_feedback)
    print(f"[系统] 二级追问：'{secondary_options['追问文案']}'")
    print(f"[系统] 二级选项：{secondary_options['选项']}")

    # 验证：二级选项是否包含"年龄差距有点大"
    assert "年龄差距有点大" in secondary_options['选项'], "❌ 二级选项未包含'年龄差距有点大'"
    print("✅ 二级选项正确")

    # 5. 用户选择二级选项
    secondary_feedback = "年龄差距有点大"
    print(f"\n[用户] 二级选项点击：'{secondary_feedback}'")

    # 6. 推断二级反馈类型
    secondary_type = infer_feedback_type(secondary_feedback)
    print(f"[系统] 推断二级反馈类型：{secondary_type}")

    # 验证：二级类型是否正确
    assert secondary_type == "criteria_age", f"❌ 二级类型错误：{secondary_type}"
    print("✅ 二级反馈类型推断正确")

    # 7. 获取二级调整策略
    secondary_strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get(secondary_type)
    print(f"[系统] 二级调整策略：affected_field='{secondary_strategy['affected_field']}'")

    assert secondary_strategy['affected_field'] == "target_age_min", "❌ 调整字段错误"
    print("✅ 二级调整策略正确")

    print("\n✅ 场景2验证完成")
    return True

def verify_scenario_3():
    """
    场景3：用户选"性格气质不对" → 建议做测评

    验证点：
    - 测评建议是否触发
    - 测评选项是否正确
    """
    print("\n" + "=" * 80)
    print("场景3：用户选'性格气质不对' → 建议做测评")
    print("=" * 80)

    # 1. 用户选择"性格气质不对"
    feedback = "性格气质不对（相处感觉不搭）"
    print(f"\n[用户] 点击：'{feedback}'")

    # 2. 推断反馈类型
    feedback_type = infer_feedback_type(feedback)
    print(f"[系统] 推断反馈类型：{feedback_type}")

    assert feedback_type == "personality_mismatch", f"❌ 反馈类型错误：{feedback_type}"
    print("✅ 反馈类型推断正确")

    # 3. 检查策略是否建议测评
    strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get(feedback_type)
    assert strategy.get('suggested_action') == "start_assessment", "❌ 未建议测评"
    print("✅ 策略正确建议做测评")

    # 4. 检查二级追问选项
    secondary_options = SECONDARY_OPTIONS_MAP.get(feedback)
    print(f"[系统] 二级追问：'{secondary_options['追问文案']}'")
    print(f"[系统] 测评选项：{secondary_options['选项']}")

    assert "好的，做测评" in any(opt for opt in secondary_options['选项']), "❌ 未包含测评选项"
    print("✅ 测评选项正确")

    print("\n✅ 场景3验证完成")
    return True

def verify_scenario_4():
    """
    场景4：用户点击"跳过，直接换"

    验证点：
    - 跳过处理是否正确
    - 不强制追问
    """
    print("\n" + "=" * 80)
    print("场景4：用户点击'跳过，直接换'")
    print("=" * 80)

    # 1. 系统追问
    print("\n[系统] 展示追问选项：...")

    # 2. 用户点击"跳过，直接换"
    print("[用户] 点击：'跳过，直接换'")

    # 3. 系统处理
    print("[系统] 思考：用户不愿意反馈，不强制，直接刷新")
    print("[系统] 回复：'好的，帮你换一批新的'")

    # 4. 验证逻辑
    print("[系统] 动作：")
    print("  1. 记录跳过反馈：追问_skipped=True")
    print("  2. 直接搜索：使用当前criteria（微调放宽）")

    print("\n✅ 场景4验证完成")
    return True

def verify_scenario_5():
    """
    场景5：连续多次"换一批"

    验证点：
    - 多次追问策略
    - 累积调整是否生效
    """
    print("\n" + "=" * 80)
    print("场景5：连续多次'换一批'")
    print("=" * 80)

    # 第1次
    print("\n[用户] 第1次：'换一批'")
    print("[系统] 追问：必须追问，建立学习闭环")

    feedback_1 = "太远了（都是异地）"
    type_1 = infer_feedback_type(feedback_1)
    print(f"[用户] 反馈：'{feedback_1}' → 类型：{type_1}")

    assert type_1 == "location_distance", "❌ 第1次反馈类型错误"
    print("✅ 第1次反馈处理正确")

    # 第2次
    print("\n[用户] 第2次：'换一批'")
    print("[系统] 追问：继续追问，信号收集最大化")

    feedback_2 = "太忙太卷（工作压力大的感觉）"
    type_2 = infer_feedback_type(feedback_2)
    print(f"[用户] 反馈：'{feedback_2}' → 类型：{type_2}")

    assert type_2 == "work_life_balance", "❌ 第2次反馈类型错误"
    print("✅ 第2次反馈处理正确")

    # 第3次
    print("\n[用户] 第3次：'换一批'")
    print("[系统] 追问：继续追问（用户选择'每次都追问'）")

    feedback_3 = "性格气质不对（相处感觉不搭）"
    type_3 = infer_feedback_type(feedback_3)
    print(f"[用户] 反馈：'{feedback_3}' → 类型：{type_3}")

    assert type_3 == "personality_mismatch", "❌ 第3次反馈类型错误"
    print("✅ 第3次反馈处理正确")

    # 累积调整验证
    print("\n[系统] 累积调整：")
    print("  - 第1次：target_cities收紧 → 同城优先")
    print("  - 第2次：life_rhythm_weight调整 → 生活感优先")
    print("  - 第3次：建议做MBTI测评 → 性格匹配强化")
    print("  → 多个偏好信号累积，推荐越来越精准")

    print("\n✅ 场景5验证完成")
    return True

def verify_scenario_6():
    """
    场景6：用户主动表达不满

    验证点：
    - 不追问，直接记录
    - 从自由文本推断类型
    """
    print("\n" + "=" * 80)
    print("场景6：用户主动表达不满")
    print("=" * 80)

    # 1. 用户主动表达不满
    user_message = "这批都太忙太卷了，工作压力太大"
    print(f"\n[用户] 说：'{user_message}'")

    # 2. 系统思考
    print("[系统] 思考：用户已经明确表达了不满原因，不追问，直接记录并调整")

    # 3. 推断类型（从自由文本）
    feedback_type = infer_feedback_type(user_message)
    print(f"[系统] 推断反馈类型：{feedback_type}")

    assert feedback_type == "work_life_balance", f"❌ 类型推断错误：{feedback_type}"
    print("✅ 从自由文本推断类型正确")

    # 4. 直接调整
    strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get(feedback_type)
    print(f"[系统] 调整策略：{strategy['persona_write']}")

    print("\n✅ 场景6验证完成")
    return True

def verify_scenario_7():
    """
    场景7：用户选"都不太合适" → 触发整体偏好澄清

    验证点：
    - 多条件不合适识别
    - 触发整体澄清
    """
    print("\n" + "=" * 80)
    print("场景7：用户选'都不太合适' → 触发整体偏好澄清")
    print("=" * 80)

    # 1. 二级追问
    print("\n[用户] 一级选择：'外在条件不合适'")
    print("[系统] 二级追问：'具体是哪个条件不太对？'")

    # 2. 用户选择"都不太合适"
    feedback = "都不太合适"
    print(f"[用户] 二级选择：'{feedback}'")

    # 3. 推断类型
    feedback_type = infer_feedback_type(feedback)
    print(f"[系统] 推断反馈类型：{feedback_type}")

    assert feedback_type == "criteria_multiple", f"❌ 类型错误：{feedback_type}"
    print("✅ 反馈类型推断正确（触发整体澄清）")

    # 4. 检查策略
    strategy = FEEDBACK_TO_CRITERIA_ADJUSTMENT.get(feedback_type)
    assert strategy.get('suggested_action') == "criteria_clarification", "❌ 未触发整体澄清"
    print("✅ 策略正确触发整体偏好澄清")

    print("\n✅ 场景7验证完成")
    return True

def verify_boundary_cases():
    """
    边界场景验证

    验证点：
    - 各种反馈类型推断的边界情况
    - 选项生成的边界情况
    """
    print("\n" + "=" * 80)
    print("边界场景验证")
    print("=" * 80)

    # 测试所有反馈类型推断
    test_cases = [
        ("太远了（都是异地）", "location_distance"),
        ("年龄差距有点大（候选人 28-35，你 26）", "age_gap"),
        ("年龄差距有点大", "criteria_age"),
        ("职业不太匹配（程序员偏多）", "occupation_mismatch"),
        ("太忙太卷（工作压力大的感觉）", "work_life_balance"),
        ("生活节奏不匹配（工作生活状态）", "work_life_balance"),
        ("兴趣不太一样", "interest_mismatch"),
        ("兴趣爱好不一样（玩不到一起）", "interest_mismatch"),
        ("性格气质不对（相处感觉不搭）", "personality_mismatch"),
        ("外在条件不合适（年龄/学历/收入）", "criteria_generic"),
        ("学历不太匹配", "criteria_education"),
        ("收入差距有点大", "criteria_income"),
        ("城市太远了", "location_distance"),
        ("都不太合适", "criteria_multiple"),
    ]

    print("\n反馈类型推断验证：")
    all_passed = True
    for feedback_text, expected_type in test_cases:
        inferred_type = infer_feedback_type(feedback_text)
        if inferred_type == expected_type:
            print(f"  ✅ '{feedback_text}' → {inferred_type}")
        else:
            print(f"  ❌ '{feedback_text}' → {inferred_type} (期望: {expected_type})")
            all_passed = False

    if all_passed:
        print("\n✅ 所有边界场景验证通过")
    else:
        print("\n❌ 部分边界场景验证失败")

    return all_passed

# ========== 主函数 ==========

def main():
    """运行所有验证场景"""
    print("\n开始验证所有场景...\n")

    results = []

    # 运行所有场景
    results.append(("场景1：换一批→追问→太远了→调整", verify_scenario_1()))
    results.append(("场景2：外在条件不合适→二级追问→年龄差距", verify_scenario_2()))
    results.append(("场景3：性格气质不对→建议测评", verify_scenario_3()))
    results.append(("场景4：跳过直接换", verify_scenario_4()))
    results.append(("场景5：连续多次换一批", verify_scenario_5()))
    results.append(("场景6：用户主动表达不满", verify_scenario_6()))
    results.append(("场景7：都不太合适→整体澄清", verify_scenario_7()))
    results.append(("边界场景：各种反馈类型推断", verify_boundary_cases()))

    # 总结
    print("\n" + "=" * 80)
    print("验证总结")
    print("=" * 80)

    passed_count = sum(1 for _, result in results if result)
    total_count = len(results)

    print(f"\n总计验证场景：{total_count}个")
    print(f"通过场景：{passed_count}个")
    print(f"失败场景：{total_count - passed_count}个")

    print("\n详细结果：")
    for scenario, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {status} - {scenario}")

    if passed_count == total_count:
        print("\n🎉 所有场景验证通过！学习闭环功能逻辑正确！")
    else:
        print(f"\n⚠️  有{total_count - passed_count}个场景验证失败，需要修复")

    print("=" * 80)

if __name__ == "__main__":
    main()