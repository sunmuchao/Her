#!/usr/bin/env python3
"""真实用户模拟测试：长时间复杂对话测试

测试目标：
1. 模拟真实用户行为（不确定意图、多话题切换、边缘场景）
2. 验证搜索、画像写入、推荐理由等逻辑
3. 记录所有发现的问题（只测试不修复）

测试场景：
- Phase 1: 模糊意图 + 口语化表达
- Phase 2: 多意图冲突 + 条件修改
- Phase 3: 历史候选人引用（Agent幻觉测试）
- Phase 4: 深层次需求挖掘
- Phase 5: 极端条件 + 边界场景
"""

from __future__ import annotations

import sys
import json
import time
import uuid
from pathlib import Path
from datetime import datetime

# 确保 her repo 在 sys.path 中
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import requests

# Gateway地址
GATEWAY_URL = "http://127.0.0.1:8765"

# 测试记录
test_log = []

def log_test(phase: str, user_input: str, expected: str, actual: str, passed: bool, notes: str = ""):
    """记录测试结果"""
    test_log.append({
        "timestamp": datetime.now().isoformat(),
        "phase": phase,
        "user_input": user_input,
        "expected": expected,
        "actual": actual,
        "passed": passed,
        "notes": notes,
    })

    # 实时打印结果
    status = "✅" if passed else "❌"
    print(f"{status} [{phase}] 用户: '{user_input}'")
    if not passed:
        print(f"   预期: {expected}")
        print(f"   实际: {actual[:200]}")
        if notes:
            print(f"   备注: {notes}")
    print()

def create_session(user_id: int = 10015) -> str | None:
    """创建新会话"""
    url = f"{GATEWAY_URL}/v1/discovery/sessions"

    headers = {
        "Content-Type": "application/json",
        "Cookie": "session_token=sess-d70ab69e25a14459",
    }

    data = {
        "session_type": "discovery",
        "requester_id": user_id,
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        if response.status_code in [200, 201]:
            result = response.json()
            session_id = result.get("session", {}).get("session_id")
            print(f"✅ 会话创建成功: {session_id}")
            return session_id
        else:
            print(f"❌ 会话创建失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return None
    except Exception as e:
        print(f"❌ 会话创建异常: {e}")
        return None

def send_turn(session_id: str, user_message: str = None, action_id: str = None) -> dict | None:
    """发送一轮对话"""
    url = f"{GATEWAY_URL}/v1/discovery/sessions/{session_id}/turns"

    headers = {
        "Content-Type": "application/json",
        "Cookie": "session_token=sess-d70ab69e25a14459",
    }

    data = {}
    if user_message:
        data["user_message"] = user_message
    if action_id:
        data["action_id"] = action_id

    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"❌ 对话请求失败: {response.status_code}")
            print(f"   错误: {response.text}")
            return None
    except Exception as e:
        print(f"❌ 对话请求异常: {e}")
        return None

def extract_response_info(response: dict) -> dict:
    """提取响应关键信息"""
    if not response:
        return {}

    view = response.get("view", {})
    timeline = view.get("timeline", [])

    # 提取assistant消息
    assistant_message = ""
    for item in timeline:
        if item.get("item_type") == "assistant_message":
            assistant_message = item.get("body", "")
            break

    # 提取候选人列表
    candidates = []
    candidate_ids = []
    for item in timeline:
        if item.get("item_type") == "result_group":
            cards = item.get("cards", [])
            for card in cards:
                profile_id = card.get("profile_id")
                title = card.get("title", "")
                reason_summary = card.get("reason_summary", "")
                candidates.append({
                    "profile_id": profile_id,
                    "title": title,
                    "reason_summary": reason_summary,
                })
                if profile_id:
                    candidate_ids.append(profile_id)

    # 提取phase
    phase = response.get("phase", "")

    # 提取suggested_actions
    suggested_actions = view.get("suggested_actions", [])

    return {
        "assistant_message": assistant_message,
        "candidates": candidates,
        "candidate_ids": candidate_ids,
        "phase": phase,
        "suggested_actions": suggested_actions,
    }

def test_phase_1_fuzzy_intent(session_id: str):
    """Phase 1: 模糊意图 + 口语化表达"""
    print("\n" + "=" * 80)
    print("Phase 1: 模糊意图 + 口语化表达")
    print("=" * 80)

    # 测试1.1: 极简意图
    print("\n【测试1.1】极简意图")
    response = send_turn(session_id, "找个对象")
    info = extract_response_info(response)

    # 验证：应该询问必要条件（性别、年龄、城市等）
    expected = "询问性别、年龄、城市等必要条件"
    passed = any(keyword in info["assistant_message"] for keyword in ["性别", "年龄", "城市", "什么样的", "具体"])
    log_test("模糊意图", "找个对象", expected, info["assistant_message"], passed,
             "极简意图应该触发Agent追问必要条件")

    time.sleep(2)

    # 测试1.2: 口语化特质
    print("\n【测试1.2】口语化特质")
    response = send_turn(session_id, "找个靠谱的女生")
    info = extract_response_info(response)

    # 验证：应该尝试理解"靠谱"
    expected = "理解'靠谱'特质或追问具体含义"
    passed = len(info["assistant_message"]) > 0  # 至少有响应
    log_test("口语化表达", "找个靠谱的女生", expected, info["assistant_message"], passed,
             "口语化特质'靠谱'是否能被正确理解")

    time.sleep(2)

    # 测试1.3: 口语化城市
    print("\n【测试1.3】口语化城市")
    response = send_turn(session_id, "找个江浙一带的女生")
    info = extract_response_info(response)

    # 验证：应该理解为江苏/浙江范围
    expected = "理解为江苏/浙江范围城市"
    passed = any(keyword in info["assistant_message"] for keyword in ["江苏", "浙江", "苏州", "南京", "杭州", "一带"])
    log_test("口语化表达", "找个江浙一带的女生", expected, info["assistant_message"], passed,
             "口语化城市'江浙一带'是否能被正确理解")

    time.sleep(2)

    # 测试1.4: 情绪化表达
    print("\n【测试1.4】情绪化表达")
    response = send_turn(session_id, "我不想找那种很虚伪的人")
    info = extract_response_info(response)

    # 验证：应该使用exclude模式排除"虚伪"特质
    expected = "理解负面偏好，排除'虚伪'特质"
    passed = any(keyword in info["assistant_message"] for keyword in ["虚伪", "真诚", "实在", "不虚伪"])
    log_test("情绪化表达", "我不想找那种很虚伪的人", expected, info["assistant_message"], passed,
             "负面偏好是否能触发exclude模式")

def test_phase_2_multi_intent(session_id: str):
    """Phase 2: 多意图冲突 + 条件修改"""
    print("\n" + "=" * 80)
    print("Phase 2: 多意图冲突 + 条件修改")
    print("=" * 80)

    # 测试2.1: 意图叠加
    print("\n【测试2.1】意图叠加")
    response = send_turn(session_id, "我想找个温柔的，但也不要太内向")
    info = extract_response_info(response)

    # 验证：应该理解为多维度筛选（温柔 + 不太内向）
    expected = "理解为多维度筛选（温柔 + 不太内向）"
    passed = any(keyword in info["assistant_message"] for keyword in ["温柔", "内向", "活泼", "开朗"])
    log_test("多意图冲突", "我想找个温柔的，但也不要太内向", expected, info["assistant_message"], passed,
             "多意图是否能同时被理解")

    time.sleep(2)

    # 测试2.2: 意图反转
    print("\n【测试2.2】意图反转")
    response = send_turn(session_id, "刚才说找个温柔的，但我又想想，还是找个活泼的吧")
    info = extract_response_info(response)

    # 验证：应该更新条件，重新搜索
    expected = "更新条件，搜索'活泼'特质"
    passed = any(keyword in info["assistant_message"] for keyword in ["活泼", "开朗", "外向"])
    log_test("意图反转", "刚才说找个温柔的，但我又想想，还是找个活泼的吧", expected, info["assistant_message"], passed,
             "意图反转是否能正确更新条件")

    time.sleep(2)

    # 测试2.3: 意图否定
    print("\n【测试2.3】意图否定")
    response = send_turn(session_id, "不要苏州的，也不要上海的")
    info = extract_response_info(response)

    # 验证：应该排除多个城市
    expected = "排除苏州和上海两个城市"
    passed = any(keyword in info["assistant_message"] for keyword in ["苏州", "上海", "其他城市", "排除"])
    log_test("意图否定", "不要苏州的，也不要上海的", expected, info["assistant_message"], passed,
             "双重否定是否能正确排除")

def test_phase_3_agent_hallucination(session_id: str):
    """Phase 3: 历史候选人引用（Agent幻觉测试）"""
    print("\n" + "=" * 80)
    print("Phase 3: 历史候选人引用（Agent幻觉测试）")
    print("=" * 80)

    # 先搜索一批候选人，获取候选人ID
    print("\n【前置步骤】搜索候选人")
    response = send_turn(session_id, "找个苏州的25-30岁的温柔女生")
    info = extract_response_info(response)

    if info["candidates"]:
        print(f"✅ 找到 {len(info['candidates'])} 位候选人:")
        for i, candidate in enumerate(info["candidates"][:3], 1):
            print(f"   {i}. {candidate['title']} (ID: {candidate['profile_id']})")

        # 记录第一轮候选人ID
        first_round_ids = info["candidate_ids"]
        first_candidate_id = info["candidates"][0]["profile_id"]

        time.sleep(2)

        # 搜索新的候选人（触发候选人切换）
        print("\n【测试3.1】跨轮次引用 - 搜索新候选人")
        response = send_turn(session_id, "换个候选人看看")
        info = extract_response_info(response)

        if info["candidates"]:
            print(f"✅ 新一轮找到 {len(info['candidates'])} 位候选人:")
            for i, candidate in enumerate(info["candidates"][:3], 1):
                print(f"   {i}. {candidate['title']} (ID: {candidate['profile_id']})")

            # 记录第二轮候选人ID
            second_round_ids = info["candidate_ids"]

            # 验证：第二轮候选人应该不同于第一轮
            same_as_first = any(id in second_round_ids for id in first_round_ids[:1])
            passed = not same_as_first
            log_test("候选人切换", "换个候选人看看", "第二轮应该展示新候选人", f"第一轮ID: {first_round_ids[:3]}, 第二轮ID: {second_round_ids[:3]}", passed,
                     "候选人切换是否正常工作")

            time.sleep(2)

            # 测试3.2: 引用第一轮的候选人（Agent幻觉测试）
            print("\n【测试3.2】Agent幻觉测试 - 引用第一轮候选人")
            response = send_turn(session_id, f"候选人{first_candidate_id}的性格怎么样？")
            info = extract_response_info(response)

            # 验证：应该提示该候选人已不在当前结果中
            expected = "提示候选人已不在当前结果中"
            # 如果Agent直接返回了候选人信息，说明存在幻觉
            mentions_first_candidate = str(first_candidate_id) in info["assistant_message"]
            passed = not mentions_first_candidate  # 不应该提及第一轮候选人
            log_test("Agent幻觉", f"候选人{first_candidate_id}的性格怎么样？", expected, info["assistant_message"], passed,
                     "⚠️ 如果Agent返回了第一轮候选人信息，说明存在幻觉风险")

        else:
            print("❌ 没有找到新候选人，无法测试跨轮次引用")
            log_test("候选人切换", "换个候选人看看", "应该展示新候选人", "未找到候选人", False, "前置条件失败")

    else:
        print("❌ 没有找到候选人，无法测试Agent幻觉")
        log_test("前置条件", "找个苏州的25-30岁的温柔女生", "应该找到候选人", "未找到候选人", False, "前置条件失败")

def test_phase_4_deep_needs(session_id: str):
    """Phase 4: 深层次需求挖掘"""
    print("\n" + "=" * 80)
    print("Phase 4: 深层次需求挖掘")
    print("=" * 80)

    # 测试4.1: 情感需求表达
    print("\n【测试4.1】情感需求表达")
    response = send_turn(session_id, "我之前受过伤，希望能找个给我安全感的人")
    info = extract_response_info(response)

    # 验证：应该理解情感需求（需要安全感）
    expected = "理解情感需求'需要安全感'"
    passed = any(keyword in info["assistant_message"] for keyword in ["安全感", "稳定", "可靠", "成熟"])
    log_test("深层次需求", "我之前受过伤，希望能找个给我安全感的人", expected, info["assistant_message"], passed,
             "情感需求是否能被正确理解")

    time.sleep(2)

    # 测试4.2: 价值观匹配
    print("\n【测试4.2】价值观匹配")
    response = send_turn(session_id, "我很重视家庭，希望找个同样重视家庭的人")
    info = extract_response_info(response)

    # 验证：应该理解价值观需求
    expected = "理解价值观'重视家庭'"
    passed = any(keyword in info["assistant_message"] for keyword in ["家庭", "家庭观念", "顾家"])
    log_test("价值观匹配", "我很重视家庭，希望找个同样重视家庭的人", expected, info["assistant_message"], passed,
             "价值观需求是否能被正确理解")

    time.sleep(2)

    # 测试4.3: 生活方式匹配
    print("\n【测试4.3】生活方式匹配")
    response = send_turn(session_id, "我作息很规律，早睡早起，希望找个同样规律的人")
    info = extract_response_info(response)

    # 验证：应该理解生活方式需求
    expected = "理解生活方式'作息规律'"
    passed = any(keyword in info["assistant_message"] for keyword in ["作息", "规律", "早睡", "生活节奏"])
    log_test("生活方式匹配", "我作息很规律，早睡早起，希望找个同样规律的人", expected, info["assistant_message"], passed,
             "生活方式需求是否能被正确理解")

def test_phase_5_boundary_scenarios(session_id: str):
    """Phase 5: 极端条件 + 边界场景"""
    print("\n" + "=" * 80)
    print("Phase 5: 极端条件 + 边界场景")
    print("=" * 80)

    # 测试5.1: 极窄年龄范围
    print("\n【测试5.1】极窄年龄范围")
    response = send_turn(session_id, "找个26岁零3个月的女生")
    info = extract_response_info(response)

    # 验证：应该提示范围过窄
    expected = "提示年龄范围过窄或放宽范围"
    passed = any(keyword in info["assistant_message"] for keyword in ["范围", "放宽", "年龄", "26", "调整"])
    log_test("极端条件", "找个26岁零3个月的女生", expected, info["assistant_message"], passed,
             "极窄年龄范围是否能被合理处理")

    time.sleep(2)

    # 测试5.2: 条件缺失
    print("\n【测试5.2】条件缺失")
    response = send_turn(session_id, "找个温柔的女生")  # 缺少城市、年龄等
    info = extract_response_info(response)

    # 验证：应该询问缺失的条件
    expected = "询问城市、年龄等缺失条件"
    passed = any(keyword in info["assistant_message"] for keyword in ["城市", "年龄", "地区", "多大"])
    log_test("条件缺失", "找个温柔的女生", expected, info["assistant_message"], passed,
             "条件缺失是否能触发追问")

    time.sleep(2)

    # 测试5.3: 条件矛盾
    print("\n【测试5.3】条件矛盾")
    response = send_turn(session_id, "找个苏州的上海女生")
    info = extract_response_info(response)

    # 验证：应该提示条件矛盾
    expected = "提示条件矛盾"
    passed = any(keyword in info["assistant_message"] for keyword in ["矛盾", "冲突", "苏州", "上海", "选择"])
    log_test("条件矛盾", "找个苏州的上海女生", expected, info["assistant_message"], passed,
             "条件矛盾是否能被识别")

def save_test_report():
    """保存测试报告"""
    report_path = Path(__file__).parent / "real_user_test_report.json"

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(test_log, f, indent=2, ensure_ascii=False)

    print(f"\n✅ 测试报告已保存: {report_path}")

def print_summary():
    """打印测试总结"""
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)

    passed_count = sum(1 for item in test_log if item["passed"])
    failed_count = len(test_log) - passed_count

    print(f"\n总测试数: {len(test_log)}")
    print(f"通过: {passed_count} ✅")
    print(f"失败: {failed_count} ❌")

    if failed_count > 0:
        print("\n失败项目详情:")
        for item in test_log:
            if not item["passed"]:
                print(f"\n❌ [{item['phase']}] {item['user_input']}")
                print(f"   预期: {item['expected']}")
                print(f"   实际: {item['actual'][:200]}")
                if item['notes']:
                    print(f"   备注: {item['notes']}")

def main():
    """主测试流程"""
    print("\n" + "=" * 80)
    print("真实用户模拟测试 - 开始")
    print("=" * 80)
    print(f"测试时间: {datetime.now().isoformat()}")
    print(f"Gateway地址: {GATEWAY_URL}")

    # 1. 创建会话
    print("\n【步骤1】创建新会话")
    session_id = create_session(user_id=10015)

    if not session_id:
        print("\n❌ 测试失败：无法创建会话")
        print("   请检查Gateway是否正常运行")
        return

    # 2. 执行各阶段测试
    try:
        test_phase_1_fuzzy_intent(session_id)
        test_phase_2_multi_intent(session_id)
        test_phase_3_agent_hallucination(session_id)
        test_phase_4_deep_needs(session_id)
        test_phase_5_boundary_scenarios(session_id)
    except Exception as e:
        print(f"\n❌ 测试过程中出现异常: {e}")

    # 3. 打印总结
    print_summary()

    # 4. 保存测试报告
    save_test_report()

    print("\n测试完成！")

if __name__ == "__main__":
    main()