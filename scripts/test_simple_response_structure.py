#!/usr/bin/env python3
"""简单测试：查看 Agent 的完整响应结构"""

import sys
import json
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import requests

GATEWAY_URL = "http://127.0.0.1:8765"

def test():
    # 创建会话
    headers = {"Cookie": "session_token=sess-simple-test-001"}

    # 创建会话
    response = requests.post(
        f"{GATEWAY_URL}/v1/discovery/sessions",
        headers=headers,
        json={"session_type": "discovery", "requester_id": 10040},
        timeout=30
    )

    if response.status_code not in [200, 201]:
        print(f"创建会话失败: {response.status_code}")
        print(response.text)
        return

    session_id = response.json().get("session", {}).get("session_id")
    print(f"会话ID: {session_id}")

    # 发送消息
    response = requests.post(
        f"{GATEWAY_URL}/v1/discovery/sessions/{session_id}/turns",
        headers=headers,
        json={"user_message": "我想找个温柔的，但也不要太内向"},
        timeout=120
    )

    if response.status_code != 200:
        print(f"发送消息失败: {response.status_code}")
        print(response.text)
        return

    result = response.json()

    # 打印完整响应结构
    print("\n" + "=" * 80)
    print("完整响应结构：")
    print("=" * 80)
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    test()