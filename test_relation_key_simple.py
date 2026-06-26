#!/usr/bin/env python3
"""简化版 relation_key 验证脚本"""

import os
import sys

# 验证现有数据状态
print("=" * 60)
print("relation_key 修复效果验证")
print("=" * 60)

print("\n【验证1】检查现有 cases 的 relation_key 状态")
os.system("""
mysql -h 127.0.0.1 -P 3307 -u root her_matchmaking -e "
SELECT 
    COUNT(*) as total_cases,
    COUNT(relation_key) as has_relation_key,
    COUNT(*) - COUNT(relation_key) as empty_count
FROM proxy_intro_cases;
"
""")

print("\n【验证2】查看 relation_key 格式示例")
os.system("""
mysql -h 127.0.0.1 -P 3307 -u root her_matchmaking -e "
SELECT case_id, requester_id, candidate_id, relation_key
FROM proxy_intro_cases
LIMIT 5;
"
""")

print("\n【验证3】检查是否有空的 relation_key")
os.system("""
mysql -h 127.0.0.1 -P 3307 -u root her_matchmaking -e "
SELECT case_id, requester_id, candidate_id
FROM proxy_intro_cases
WHERE relation_key IS NULL OR relation_key = ''
LIMIT 10;
"
""")

print("\n" + "=" * 60)
print("✅ 验证完成！")
print("=" * 60)
