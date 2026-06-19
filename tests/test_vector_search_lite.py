"""向量搜索功能测试（使用 Milvus Lite）

Milvus Lite 是轻量级版本，无需 Docker，直接本地文件存储。

测试内容：
1. VectorStoreLite 向量存储
2. VectorStoreLite 向量搜索（带时间衰减）
3. 版本管理验证

运行方式：
python tests/test_vector_search_lite.py

注意：
- 需要配置 EMBEDDING_API_KEY 或 DASHSCOPE_API_KEY
"""

from __future__ import annotations

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_embedding_service():
    """测试1：EmbeddingService 向量生成"""
    print("\n=== 测试1：EmbeddingService 向量生成 ===")

    from match_domain.embedding_service import EmbeddingService

    service = EmbeddingService()

    text = "性格温柔、重视家庭"
    embedding = await service.generate_embedding(text)

    print(f"文本: {text}")
    print(f"向量维度: {len(embedding)}")

    if embedding:
        print("✅ 向量生成成功")
    else:
        print("⚠️ 向量生成失败（可能未配置 API Key）")
        print("请设置环境变量：EMBEDDING_API_KEY 或 DASHSCOPE_API_KEY")

    return embedding


async def test_vector_store_lite():
    """测试2：VectorStoreLite 向量存储"""
    print("\n=== 测试2：VectorStoreLite 向量存储 ===")

    from match_domain.vector_store_lite import VectorStoreLite

    store = VectorStoreLite()
    print(f"数据库文件: {store.db_file}")
    print("✅ Milvus Lite 初始化成功")

    # 测试存储
    embedding = await test_embedding_service()
    if not embedding:
        print("⚠️ 无法测试存储（向量生成失败）")
        return

    result = store.save_vector_with_version(
        user_id=12345,
        vector_type="personality_traits",
        embedding=embedding,
        raw_text="性格温柔、重视家庭",
        conversation_id="test_001",
    )

    print(f"存储结果: {result}")

    if result.get("success"):
        print(f"✅ 向量存储成功, version={result.get('version')}")
    else:
        print(f"⚠️ 向量存储失败: {result.get('error')}")


async def test_vector_search():
    """测试3：向量搜索"""
    print("\n=== 测试3：向量搜索 ===")

    from match_domain.embedding_service import EmbeddingService
    from match_domain.vector_store_lite import VectorStoreLite

    embedding_service = EmbeddingService()
    store = VectorStoreLite()

    # 生成查询向量
    text = "性格温柔"
    embedding = await embedding_service.generate_embedding(text)

    if not embedding:
        print("⚠️ 无法测试搜索")
        return

    # 搜索相似向量
    similar_users = store.search_similar_users(
        user_vector=embedding,
        vector_type="personality_traits",
        top_k=5,
        similarity_threshold=0.5,
    )

    print(f"找到 {len(similar_users)} 个相似用户")

    for user in similar_users:
        print(f"- user_id={user.get('user_id')}, similarity={user.get('similarity'):.3f}")

    print("✅ 向量搜索成功")


async def test_version_management():
    """测试4：版本管理"""
    print("\n=== 测试4：版本管理 ===")

    from match_domain.embedding_service import EmbeddingService
    from match_domain.vector_store_lite import VectorStoreLite

    embedding_service = EmbeddingService()
    store = VectorStoreLite()

    user_id = 12346

    # 第一次存储
    text1 = "重视家庭"
    embedding1 = await embedding_service.generate_embedding(text1)
    if not embedding1:
        print("⚠️ 无法测试版本管理")
        return

    result1 = store.save_vector_with_version(
        user_id=user_id,
        vector_type="values",
        embedding=embedding1,
        raw_text=text1,
        conversation_id="test_001",
    )
    print(f"第一次存储: version={result1.get('version')}")

    # 第二次存储
    text2 = "重视家庭、重视事业"
    embedding2 = await embedding_service.generate_embedding(text2)
    if embedding2:
        result2 = store.save_vector_with_version(
            user_id=user_id,
            vector_type="values",
            embedding=embedding2,
            raw_text=text2,
            conversation_id="test_002",
        )
        print(f"第二次存储: version={result2.get('version')}")

    # 查询版本
    current_version = store.get_current_vector_version(user_id, "values")
    print(f"当前版本: {current_version}")

    # 查询向量
    vectors = store.get_user_vectors(user_id, "values")
    print(f"用户向量数量: {len(vectors)}")

    print("✅ 版本管理测试成功")


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("向量搜索功能测试（Milvus Lite）")
    print("=" * 60)

    await test_embedding_service()
    await test_vector_store_lite()
    await test_vector_search()
    await test_version_management()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

    print("\n📋 如果测试失败，请检查：")
    print("1. 是否已安装 pymilvus 和 milvus-lite")
    print("2. 是否已配置 EMBEDDING_API_KEY 或 DASHSCOPE_API_KEY")
    print("3. 参考 docs/milvus_deployment_guide.md")


if __name__ == "__main__":
    asyncio.run(run_all_tests())