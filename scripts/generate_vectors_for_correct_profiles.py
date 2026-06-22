#!/usr/bin/env python3
"""为正确的候选人（6092, 2379, 6566, 1045, 8867）生成向量数据"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# 确保 her repo 在 sys.path 中
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv(repo_root / ".env")
except ImportError:
    pass

# 直接运行已有的脚本，但传入正确的profile_id
from scripts.generate_vectors_only import generate_vectors_for_profiles

async def main():
    """为正确的候选人生成向量"""

    correct_profile_ids = [6092, 2379, 6566, 1045, 8867]
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
    print("【为正确的候选人生成向量数据】")
    print("=" * 80)
    print(f"profile_ids: {correct_profile_ids}")

    result = await generate_vectors_for_profiles(correct_profile_ids, vector_types)

    print("=" * 80)
    print("【完成】")
    print(f"成功: {result.get('success_count', 0)}")
    print(f"失败: {result.get('error_count', 0)}")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())