#!/usr/env/bin python3
"""真实用户模拟测试 - 续接测试

使用已存在的session_id继续测试后续Phase
"""

from __future__ import annotations

import sys
import json
import time
from pathlib import Path
from datetime import datetime

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import requests

GATEWAY_URL = "http://127.0.0.1:8765"

# 使用刚才创建的session
SESSION_ID = "discovery-session-2bd9e1c26720"

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

    status = "✅" if passed else "❌"
    print(f"{status} [{phase}] 用户: '{user_input}'")
    if not passed:
        print(f"   预期: {expected}")
        print(f"   实际: {actual[:200]}")
        if notes:
            print(f"   备注: {notes}")
    print()

def send_turn(session_id: str, user_message: str = None) -> dict | None:
    """发送一轮对话"""
    url = f"{GATEWAY_URL}/v1/discovery/sessions/{session_id}/turns"

    headers = {
        "Content-Type": "application/json",
        "Cookie": "session_token=sess-d70ab69e25a14459",
    }

    data = {}
    if user_message:
        data["user_message"] = user_message

    try:
        print(f"\n【发送消息】'{user_message}'")
        response = requests.post(url, headers=headers, json=data, timeout=60)
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 响应成功")
            return result
        else:
            print(f"❌ 对话请求失败: {response.status_code}")
            print(f"   错误: {response.text[:500]}")
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

    return {
        "assistant_message": assistant_message,
        "candidates": candidates,
        "candidate_ids": candidate_ids,
        "phase": phase,
    }

print("\n" + "=" * 80)
print("真实用户模拟测试 - 续接测试")
print("=" * 80)
print(f"Session ID: {SESSION_ID}")

# ===== Phase 1: 模糊意图 + 口语化表达 =====

print("\n" + "=" * 80)
print("Phase 1: 模糊意图 + 口语化表达")
print("=" * 80)

# 测试1.1: 极简意图
response = send_turn(SESSION_ID, "找个对象")
info = extract_response_info(response)

expected = "询问性别、年龄、城市等必要条件"
passed = any(keyword in info["assistant_message"] for keyword in ["性别", "年龄", "城市", "什么样的", "具体", "要求"])
log_test("模糊意图", "找个对象", expected, info["assistant_message"], passed,
         "极简意图应该触发Agent追问必要条件")

time.sleep(2)

# 测试1.2: 口语化特质
response = send_turn(SESSION_ID, "找个靠谱的女生")
info = extract_response_info(response)

expected = "理解'靠谱'特质或追问具体含义"
passed = len(info["assistant_message"]) > 0
log_test("口语化表达", "找个靠谱的女生", expected, info["assistant_message"], passed,
         "口语化特质'靠谱'是否能被正确理解")

time.sleep(2)

# 测试1.3: 口语化城市
response = send_turn(SESSION_ID, "找个江浙一带的女生")
info = extract_response_info(response)

expected = "理解为江苏/浙江范围城市"
passed = any(keyword in info["assistant_message"] for keyword in ["江苏", "浙江", "苏州", "南京", "杭州", "一带", "地区"])
log_test("口语化表达", "找个江浙一带的女生", expected, info["assistant_message"], passed,
         "口语化城市'江浙一带'是否能被正确理解")

time.sleep(2)

# 测试1.4: 情绪化表达
response = send_turn(SESSION_ID, "我不想找那种很虚伪的人")
info = extract_response_info(response)

expected = "理解负面偏好，排除'虚伪'特质"
passed = any(keyword in info["assistant_message"] for keyword in ["虚伪", "真诚", "实在", "不虚伪", "排斥", "避免"])
log_test("情绪化表达", "我不想找那种很虚伪的人", expected, info["assistant_message"], passed,
         "负面偏好是否能触发exclude模式")

# ===== Phase 2: 多意图冲突 + 条件修改 =====

print("\n" + "=" * 80)
print("Phase 2: 多意图冲突 + 条件修改")
print("=" * 80)

# 测试2.1: 意图叠加
response = send_turn(SESSION_ID, "我想找个温柔的，但也不要太内向")
info = extract_response_info(response)

expected = "理解为多维度筛选（温柔 + 不太内向）"
passed = any(keyword in info["assistant_message"] for keyword in ["温柔", "内向", "活泼", "开朗", "外向"])
log_test("多意图冲突", "我想找个温柔的，但也不要太内向", expected, info["assistant_message"], passed,
         "多意图是否能同时被理解")

time.sleep(2)

# 测试2.2: 意图反转
response = send_turn(SESSION_ID, "刚才说找个温柔的，但我又想想，还是找个活泼的吧")
info = extract_response_info(response)

expected = "更新条件，搜索'活泼'特质"
passed = any(keyword in info["assistant_message"] for keyword in ["活泼", "开朗", "外向", "更新", "调整"])
log_test("意图反转", "刚才说找个温柔的，但我又想想，还是找个活泼的吧", expected, info["assistant_message"], passed,
         "意图反转是否能正确更新条件")

time.sleep(2)

# 测试2.3: 意图否定
response = send_turn(SESSION_ID, "不要苏州的，也不要上海的")
info = extract_response_info(response)

expected = "排除苏州和上海两个城市"
passed = any(keyword in info["assistant_message"] for keyword in ["苏州", "上海", "其他城市", "排除", "不要", "避免"])
log_test("意图否定", "不要苏州的，也不要上海的", expected, info["assistant_message"], passed,
         "双重否定是否能正确排除")

# ===== Phase 3: 历史候选人引用（Agent幻觉测试） =====

print("\n" + "=" * 80)
print("Phase 3: 历史候选人引用（Agent幻觉测试）")
print("=" * 80)

# 先搜索一批候选人
response = send_turn(SESSION_ID, "找个苏州的25-30岁的温柔女生")
info = extract_response_info(response)

if info["candidates"]:
    print(f"\n✅ 找到 {len(info['candidates'])} 位候选人:")
    for i, candidate in enumerate(info["candidates"][:3], 1):
        print(f"   {i}. {candidate['title']} (ID: {candidate['profile_id']})")

    first_round_ids = info["candidate_ids"]
    first_candidate_id = info["candidates"][0]["profile_id"]

    time.sleep(2)

    # 搜索新的候选人
    print("\n【测试3.1】候选人切换 - 搜索新候选人")
    response = send_turn(SESSION_ID, "换个候选人看看")
    info = extract_response_info(response)

    if info["candidates"]:
        print(f"\n✅ 新一轮找到 {len(info['candidates'])} 位候选人:")
        for i, candidate in enumerate(info["candidates"][:3], 1):
            print(f"   {i}. {candidate['title']} (ID: {candidate['profile_id']})")

        second_round_ids = info["candidate_ids"]

        # 验证候选人切换
        same_as_first = any(id in second_round_ids for id in first_round_ids[:1])
        passed = not same_as_first
        log_test("候选人切换", "换个候选人看看", "第二轮应该展示新候选人", f"第一轮ID: {first_round_ids[:3]}, 第二轮ID: {second_round_ids[:3]}", passed,
                 "候选人切换是否正常工作")

        time.sleep(2)

        # Agent幻觉测试
        print("\n【测试3.2】Agent幻觉测试 - 引用第一轮候选人")
        response = send_turn(SESSION_ID, f"候选人{first_candidate_id}的性格怎么样？")
        info = extract_response_info(response)

        expected = "提示候选人已不在当前结果中"
        mentions_first_candidate = str(first_candidate_id) in info["assistant_message"]
        passed = not mentions_first_candidate
        log_test("Agent幻觉", f"候选人{first_candidate_id}的性格怎么样？", expected, info["assistant_message"], passed,
                 "⚠️ 如果Agent返回了第一轮候选人信息，说明存在幻觉风险")

    else:
        print("❌ 没有找到新候选人，无法测试跨轮次引用")

else:
    print("❌ 没有找到候选人，无法测试Agent幻觉")

# ===== Phase 4: 深层次需求挖掘 =====

print("\n" + "=" * 80)
print("Phase 4: 深层次需求挖掘")
print("=" * 80)

# 测试4.1: 情感需求表达
response = send_turn(SESSION_ID, "我之前受过伤，希望能找个给我安全感的人")
info = extract_response_info(response)

expected = "理解情感需求'需要安全感'"
passed = any(keyword in info["assistant_message"] for keyword in ["安全感", "稳定", "可靠", "成熟", "受过伤"])
log_test("深层次需求", "我之前受过伤，希望能找个给我安全感的人", expected, info["assistant_message"], passed,
         "情感需求是否能被正确理解")

time.sleep(2)

# 测试4.2: 价值观匹配
response = send_turn(SESSION_ID, "我很重视家庭，希望找个同样重视家庭的人")
info = extract_response_info(response)

expected = "理解价值观'重视家庭'"
passed = any(keyword in info["assistant_message"] for keyword in ["家庭", "家庭观念", "顾家", "重视"])
log_test("价值观匹配", "我很重视家庭，希望找个同样重视家庭的人", expected, info["assistant_message"], passed,
         "价值观需求是否能被正确理解")

time.sleep(2)

# 测试4.3: 生活方式匹配
response = send_turn(SESSION_ID, "我作息很规律，早睡早起，希望找个同样规律的人")
info = extract_response_info(response)

expected = "理解生活方式'作息规律'"
passed = any(keyword in info["assistant_message"] for keyword in ["作息", "规律", "早睡", "生活节奏", "习惯"])
log_test("生活方式匹配", "我作息很规律，早睡早起，希望找个同样规律的人", expected, info["assistant_message"], passed,
         "生活方式需求是否能被正确理解")

# ===== Phase 5: 极端条件 + 边界场景 =====

print("\n" + "=" * 80)
print("Phase 5: 极端条件 + 边界场景")
print("=" * 80)

# 测试5.1: 极窄年龄范围
response = send_turn(SESSION_ID, "找个26岁零3个月的女生")
info = extract_response_info(response)

expected = "提示年龄范围过窄或放宽范围"
passed = any(keyword in info["assistant_message"] for keyword in ["范围", "放宽", "年龄", "26", "调整", "太窄", "精确"])
log_test("极端条件", "找个26岁零3个月的女生", expected, info["assistant_message"], passed,
         "极窄年龄范围是否能被合理处理")

time.sleep(2)

# 测试5.2: 条件缺失
response = send_turn(SESSION_ID, "找个温柔的女生")
info = extract_response_info(response)

expected = "询问城市、年龄等缺失条件"
passed = any(keyword in info["assistant_message"] for keyword in ["城市", "年龄", "地区", "多大", "范围", "哪里"])
log_test("条件缺失", "找个温柔的女生", expected, info["assistant_message"], passed,
         "条件缺失是否能触发追问")

time.sleep(2)

# 测试5.3: 条件矛盾
response = send_turn(SESSION_ID, "找个苏州的上海女生")
info = extract_response_info(response)

expected = "提示条件矛盾"
passed = any(keyword in info["assistant_message"] for keyword in ["矛盾", "冲突", "苏州", "上海", "选择", "只能"])
log_test("条件矛盾", "找个苏州的上海女生", expected, info["assistant_message"], passed,
         "条件矛盾是否能被识别")

# ===== 打印总结 =====

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

# ===== 保存测试报告 =====

report_path = Path(__file__).parent / "real_user_test_report_phase1-5.json"

with open(report_path, "w", encoding="utf-8") as f:
    json.dump(test_log, f, indent=2, ensure_ascii=False)

print(f"\n✅ 测试报告已保存: {report_path}")
print("\n测试完成！")