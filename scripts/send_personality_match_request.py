#!/usr/bin/env python3
"""发送性格匹配请求：验证向量筛选"""

import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import requests

session_id = "discovery-session-24c51b50ae64"

url = f"http://127.0.0.1:8765/v1/discovery/sessions/{session_id}/turns"

headers = {
    "Content-Type": "application/json",
    "Cookie": "session_token=sess-d70ab69e25a14459",
}

data = {
    "user_message": "我想找温柔，有上进心的女生",
}

print("=" * 80)
print("【发送性格匹配请求】")
print(f"Session: {session_id}")
print(f"Message: 我想找温柔，有上进心的女生")
print("=" * 80)

try:
    response = requests.post(url, headers=headers, json=data, timeout=90)

    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("✅ 请求成功！正在检查向量筛选日志...")
    else:
        print(f"❌ 请求失败")
        print(response.text[:500])

except Exception as exc:
    print(f"❌ 异常: {exc}")

print("=" * 80)