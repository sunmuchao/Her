#!/usr/bin/env python3
"""实验验证：捕获Agent传递的criteria_json参数

实验设计：
1. 创建新会话
2. 发送明确的测试消息："找个26岁的苏州女生"
3. 查看日志，捕获criteria_json的具体内容
4. 验证Agent是否正确提取了性别、年龄、城市条件
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

print("\n" + "=" * 80)
print("实验验证：捕获Agent传递的criteria_json参数")
print("=" * 80)

# 创建新会话
url = f"{GATEWAY_URL}/v1/discovery/sessions"
headers = {
    "Content-Type": "application/json",
    "Cookie": "session_token=sess-d70ab69e25a14459",
}
data = {
    "session_type": "discovery",
    "requester_id": 10040,  # 新测试用户
}

try:
    print("\n【步骤1】创建新会话")
    response = requests.post(url, headers=headers, json=data, timeout=30)
    if response.status_code in [200, 201]:
        result = response.json()
        session_id = result.get("session", {}).get("session_id")
        print(f"✅ 会话创建成功: {session_id}")
    else:
        print(f"❌ 会话创建失败: {response.status_code}")
        sys.exit(1)
except Exception as e:
    print(f"❌ 会话创建异常: {e}")
    sys.exit(1)

# 发送测试消息
turns_url = f"{GATEWAY_URL}/v1/discovery/sessions/{session_id}/turns"
test_message = "找个26岁的苏州女生"  # 明确的测试消息

try:
    print(f"\n【步骤2】发送测试消息：'{test_message}'")
    print("【等待响应】（可能需要120秒）...")

    turns_response = requests.post(
        turns_url,
        headers=headers,
        json={"user_message": test_message},
        timeout=120
    )

    if turns_response.status_code == 200:
        print("✅ 响应成功")

        # 提取候选人信息
        result = turns_response.json()
        view = result.get("view", {})
        timeline = view.get("timeline", [])

        candidates = []
        for item in timeline:
            if item.get("item_type") == "result_group":
                cards = item.get("cards", [])
                for card in cards:
                    candidates.append({
                        "profile_id": card.get("profile_id"),
                        "title": card.get("title", ""),
                    })

        if candidates:
            print(f"\n【返回的候选人】找到 {len(candidates)} 位:")
            for i, c in enumerate(candidates[:5], 1):
                print(f"   {i}. {c['title']} (ID: {c['profile_id']})")

    else:
        print(f"❌ 响应失败: {turns_response.status_code}")
        print(f"   错误: {turns_response.text[:300]}")

except Exception as e:
    print(f"❌ 响应异常: {e}")

print("\n" + "=" * 80)
print("实验完成")
print("=" * 80)

print(f"\n【Session ID】{session_id}")
print(f"\n【步骤3】查看日志文件")
print("=" * 80)

# 等待5秒，让日志文件写入完成
time.sleep(5)

# 查看日志文件
log_file = Path("/Users/sunmuchao/Downloads/Her/.run/logs/gateway.log")

print(f"日志路径: {log_file}")

# 查找关键日志
print(f"\n查找Session {session_id} 的关键日志...")

key_logs = []
with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        if session_id in line:
            key_logs.append(line.strip())

# 查找工具调用参数
print("\n【关键日志1】Agent传递的criteria_json参数")
print("=" * 80)
for log in key_logs:
    if "【工具调用参数】" in log:
        print(log)
        break

# 查找解析后的criteria
print("\n【关键日志2】解析后的criteria字典")
print("=" * 80)
for log in key_logs:
    if "【解析后的criteria】" in log:
        print(log)
        break

# 查找搜索开始
print("\n【关键日志3】搜索开始时的criteria")
print("=" * 80)
for log in key_logs:
    if "【搜索开始】" in log:
        print(log)
        break

print("\n" + "=" * 80)
print("实验结果分析")
print("=" * 80)

print("\n【预期结果】")
print("如果Agent正确提取了条件，criteria_json应该包含：")
print('  {"gender": "female", "age_min": 26, "age_max": 26, "cities": ["苏州"]}')
print("或者至少包含：")
print('  {"gender": "female"}')

print("\n【实际情况】")
print("如果criteria_json是空字符串或'{}',说明：")
print("❌ Agent没有正确提取性别、年龄、城市条件")
print("❌ 导致搜索工具没有应用任何硬约束")

print("\n【验证完成】")
print(f"Session ID: {session_id}")
print(f"测试消息: '{test_message}'")
print("请查看上述日志中的criteria_json参数内容")