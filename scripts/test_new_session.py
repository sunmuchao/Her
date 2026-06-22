#!/usr/bin/env python3
"""测试新会话：验证向量筛选是否生效"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保 her repo 在 sys.path 中
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import requests
import json
import uuid

# 创建新的会话ID
new_session_id = f"test-session-{uuid.uuid4().hex[:12]}"

# 构造请求：创建新会话
url = "http://127.0.0.1:8765/v1/discovery/sessions"

headers = {
    "Content-Type": "application/json",
    "Cookie": "session_token=sess-d70ab69e25a14459",
}

data = {
    "session_type": "discovery",
    "requester_id": 10015,  # 用户ID
}

print("=" * 80)
print("【创建新会话】")
print("=" * 80)

try:
    response = requests.post(url, headers=headers, json=data, timeout=30)

    if response.status_code == 200:
        result = response.json()
        session_id = result.get("session", {}).get("session_id")
        print(f"✅ 会话创建成功: {session_id}")

        # 发送对话请求
        turns_url = f"http://127.0.0.1:8765/v1/discovery/sessions/{session_id}/turns"

        turns_data = {
            "user_message": "我想找温柔，有上进心的女生",
        }

        print(f"\n【发送对话请求】")
        print(f"Message: 我想找温柔，有上进心的女生")

        turns_response = requests.post(turns_url, headers=headers, json=turns_data, timeout=60)

        if turns_response.status_code == 200:
            print(f"✅ 对话请求成功")
            print("\n请等待30秒后检查gateway.log日志...")
        else:
            print(f"❌ 对话请求失败: {turns_response.status_code}")
            print(turns_response.text)
    else:
        print(f"❌ 会话创建失败: {response.status_code}")
        print(response.text)

except Exception as exc:
    print(f"❌ 请求异常: {exc}")

print("=" * 80)