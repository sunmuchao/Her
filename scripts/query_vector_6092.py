"""查询向量库中user_id=6092的数据"""

import sys
import os

# 添加项目路径
sys.path.insert(0, '/Users/sunmuchao/Downloads/Her')

from match_domain.vector_store_lite import VectorStoreLite, VECTOR_TYPES_CONFIG

def query_user_vectors(user_id: int):
    """查询指定用户的向量数据"""

    print("=" * 80)
    print(f"查询向量库：user_id={user_id}")
    print("=" * 80)

    # 创建向量存储实例
    db_file = "/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway/milvus_lite_data/user_vectors.db"
    vector_store = VectorStoreLite(db_file=db_file)

    try:
        # 1. 查询所有向量类型的数据
        print("\n【查询所有向量类型】")
        print("-" * 80)
        all_vectors = vector_store.get_user_vectors(user_id)

        if not all_vectors:
            print(f"❌ 未找到 user_id={user_id} 的任何向量数据")
        else:
            print(f"✅ 找到 {len(all_vectors)} 条向量数据")
            for vec in all_vectors:
                print(f"\n向量类型: {vec.get('vector_type')}")
                print(f"  - raw_text: {vec.get('raw_text')}")
                print(f"  - vector_version: {vec.get('vector_version')}")
                print(f"  - create_time: {vec.get('create_time')}")

        # 2. 分别查询每种向量类型
        print("\n" + "=" * 80)
        print("【按向量类型详细查询】")
        print("=" * 80)

        vector_types = [
            "personality_traits",
            "values",
            "life_attitude",
            "partner_expectation",
            "partner_personality_preference",
            "partner_relationship_pacing",
            "partner_lifestyle_preference",
            "emotional_needs"
        ]

        for vtype in vector_types:
            print(f"\n向量类型: {vtype}")
            print("-" * 80)

            # 查询配置
            config = VECTOR_TYPES_CONFIG.get(vtype, {})
            print(f"配置:")
            print(f"  - decay_days: {config.get('decay_days')}天")
            print(f"  - decay_curve: {config.get('decay_curve')}")
            print(f"  - min_factor: {config.get('min_factor')}")
            print(f"  - max_version_count: {config.get('max_version_count')}")
            print(f"  - cleanup_days: {config.get('cleanup_days')}天")

            # 查询数据
            vectors = vector_store.get_user_vectors(user_id, vtype)

            if not vectors:
                print(f"❌ 无数据")
            else:
                print(f"✅ 找到 {len(vectors)} 条数据")
                for vec in vectors:
                    print(f"  - version: {vec.get('vector_version')}")
                    print(f"  - text: {vec.get('raw_text')}")
                    print(f"  - create_time: {vec.get('create_time')}")

        # 3. 总结
        print("\n" + "=" * 80)
        print("【总结】")
        print("=" * 80)

        if not all_vectors:
            print("❌ 向量库中无 user_id=6092 的数据")
            print("这就是为什么向量筛选返回0个相似用户的原因！")
        else:
            print(f"✅ 向量库中有 {len(all_vectors)} 条数据")
            print("向量筛选应该能找到相似用户")

    finally:
        vector_store.close()


if __name__ == "__main__":
    query_user_vectors(6092)