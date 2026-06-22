#!/usr/bin/env python3
"""测试对话请求：验证向量筛选是否生效"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保 her repo 在 sys.path 中
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import requests
import json

# 构造请求
url = "http://127.0.0.1:8765/v1/discovery/sessions/discovery-session-96013893d0f2/turns"

headers = {
    "Content-Type": "application/json",
    "Cookie": "session_token=sess-d70ab69e25a14459",  # 使用之前的session token
}

data = {
    "user_message": "我想找温柔，有上进心的",  # 直接传user_message字段
}

print("=" * 80)
print("【发送对话请求】")
print("=" * 80)
print(f"URL: {url}")
print(f"Message: 我想找温柔，有上进心的")
print()

try:
    response = requests.post(url, headers=headers, json=data, timeout=30)

    print("【响应状态】")
    print(f"Status Code: {response.status_code}")
    print()

    if response.status_code == 200:
        result = response.json()
        print("【响应内容】")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:500])
        print()
        print("✅ 请求成功！请检查gateway.log日志查看向量筛选详情")
    else:
        print("❌ 请求失败")
        print(response.text)

except Exception as exc:
    print(f"❌ 请求异常: {exc}")

print("=" * 80)