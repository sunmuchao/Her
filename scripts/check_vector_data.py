#!/usr/bin/env python3
"""检查向量库数据"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保 her repo 在 sys.path 中
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from match_domain.vector_store_lite import VectorStoreLite

vector_store = VectorStoreLite()

try:
    # 查询向量库数据
    profile_ids = [10002, 10005, 10006, 10007, 10008, 10009, 10010, 10011, 10016]
    vector_types = [
        "personality_traits",
        "values",
        "life_attitude",
        "partner_expectation",
        "partner_personality_preference",
        "partner_relationship_pacing",
        "partner_lifestyle_preference",
        "emotional_needs",
    ]

    print("=" * 80)
    print("【向量库数据统计】")
    print("=" * 80)

    for profile_id in profile_ids:
        vectors = vector_store.get_user_vectors(profile_id)
        print(f"profile_id={profile_id}: {len(vectors)} 条向量数据")
        for v in vectors:
            print(f"  - {v.get('vector_type')}: {v.get('raw_text')[:50]}...")

    # 统计总数
    total_vectors = 0
    for profile_id in profile_ids:
        vectors = vector_store.get_user_vectors(profile_id)
        total_vectors += len(vectors)

    print("=" * 80)
    print(f"【总计】{total_vectors} 条向量数据")
    print("=" * 80)

finally:
    vector_store.close()