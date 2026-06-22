#!/usr/bin/env python3
"""最终验证：发送性格匹配请求"""

import sys
from pathlib import Path
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import requests

session_id = "discovery-session-409993586319"
url = f"http://127.0.0.1:8765/v1/discovery/sessions/{session_id}/turns"
headers = {"Content-Type": "application/json", "Cookie": "session_token=sess-d70ab69e25a14459"}
data = {"user_message": "我想找温柔，有上进心的女生"}

print("发送性格匹配请求...")
response = requests.post(url, headers=headers, json=data, timeout=90)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    print("✅ 成功！请等待并检查向量筛选日志...")