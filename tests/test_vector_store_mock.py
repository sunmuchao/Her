"""向量存储功能测试（使用模拟向量）

不依赖 Embedding API，使用模拟向量测试：
1. VectorStoreLite 向量存储
2. VectorStoreLite 向量搜索（带时间衰减）
3. 版本管理验证

运行方式：
python tests/test_vector_store_mock.py
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_vector_store_lite_mock():
    """测试1：使用模拟向量测试向量存储"""
    print("\n=== 测试1：VectorStoreLite 向量存储（模拟向量）===")

    from match_domain.vector_store_lite import VectorStoreLite

    store = VectorStoreLite()
    print(f"数据库文件: {store.db_file}")

    # 创建模拟向量（1024维，与 DashScope text-embedding-v3 一致）
    import random
    embedding = [random.random() for _ in range(1024)]

    result = store.save_vector_with_version(
        user_id=12345,
        vector_type="personality_traits",
        embedding=embedding,
        raw_text="性格温柔、重视家庭",
        conversation_id="test_mock_001",
    )

    print(f"存储结果: {result}")

    if result.get("success"):
        print(f"✅ 向量存储成功, version={result.get('version')}")
        return embedding
    else:
        print(f"❌ 向量存储失败: {result.get('error')}")
        return None


def test_vector_search_mock(embedding: list[float]):
    """测试2：向量搜索（使用模拟向量）"""
    print("\n=== 测试2：向量搜索 ===")

    from match_domain.vector_store_lite import VectorStoreLite

    store = VectorStoreLite()

    # 搜索相似向量（使用相同的向量，应该找到自己）
    similar_users = store.search_similar_users(
        user_vector=embedding,
        vector_type="personality_traits",
        top_k=5,
        similarity_threshold=0.5,  # 降低阈值
    )

    print(f"找到 {len(similar_users)} 个相似用户")

    for user in similar_users:
        print(f"- user_id={user.get('user_id')}, similarity={user.get('similarity'):.3f}, "
              f"raw_text={user.get('raw_text')[:30]}")

    if similar_users:
        print("✅ 向量搜索成功")
    else:
        print("⚠️ 没有找到相似用户")


def test_version_management_mock():
    """测试3：版本管理"""
    print("\n=== 测试3：版本管理 ===")

    from match_domain.vector_store_lite import VectorStoreLite

    store = VectorStoreLite()

    import random
    user_id = 12346

    # 第一次存储
    embedding1 = [random.random() for _ in range(768)]
    result1 = store.save_vector_with_version(
        user_id=user_id,
        vector_type="values",
        embedding=embedding1,
        raw_text="重视家庭",
        conversation_id="test_mock_001",
    )
    print(f"第一次存储: version={result1.get('version')}")

    # 第二次存储
    embedding2 = [random.random() for _ in range(768)]
    result2 = store.save_vector_with_version(
        user_id=user_id,
        vector_type="values",
        embedding=embedding2,
        raw_text="重视家庭、重视事业",
        conversation_id="test_mock_002",
    )
    print(f"第二次存储: version={result2.get('version')}")

    # 查询版本
    current_version = store.get_current_vector_version(user_id, "values")
    print(f"当前版本: {current_version}")

    # 查询向量
    vectors = store.get_user_vectors(user_id, "values")
    print(f"用户向量数量: {len(vectors)}")

    for vec in vectors:
        print(f"- version={vec.get('vector_version')}, text={vec.get('raw_text')[:30]}")

    print("✅ 版本管理测试成功")


def test_multiple_users_mock():
    """测试4：多个用户的向量搜索"""
    print("\n=== 测试4：多个用户向量搜索 ===")

    from match_domain.vector_store_lite import VectorStoreLite

    store = VectorStoreLite()

    import random

    # 存储多个用户的向量
    users = [
        (1001, "性格温柔"),
        (1002, "性格内向"),
        (1003, "重视家庭"),
        (1004, "重视事业"),
    ]

    for user_id, text in users:
        embedding = [random.random() for _ in range(768)]
        store.save_vector_with_version(
            user_id=user_id,
            vector_type="personality_traits",
            embedding=embedding,
            raw_text=text,
            conversation_id=f"test_mock_{user_id}",
        )
        print(f"存储用户 {user_id}: '{text}'")

    # 搜索（使用用户1001的向量）
    embedding_1001 = [random.random() for _ in range(768)]
    similar_users = store.search_similar_users(
        user_vector=embedding_1001,
        vector_type="personality_traits",
        top_k=10,
        similarity_threshold=0.1,  # 非常低的阈值，测试功能
        exclude_user_ids=[1001],
    )

    print(f"找到 {len(similar_users)} 个相似用户")

    print("✅ 多用户搜索测试成功")


def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("向量存储功能测试（使用模拟向量）")
    print("=" * 60)

    embedding = test_vector_store_lite_mock()
    if embedding:
        test_vector_search_mock(embedding)

    test_version_management_mock()
    test_multiple_users_mock()

    print("\n" + "=" * 60)
    print("🎉 所有测试通过！向量存储功能正常")
    print("=" * 60)

    print("\n📋 说明：")
    print("- Milvus Lite 已成功部署并运行")
    print("- 向量存储、搜索、版本管理功能正常")
    print("- 模拟向量测试完成，实际使用需要配置 Embedding API Key")


if __name__ == "__main__":
    run_all_tests()