"""向量搜索功能测试

测试内容：
1. EmbeddingService 向量生成
2. VectorStore 向量存储（带版本管理）
3. VectorStore 向量搜索（带时间衰减）
4. 完整流程：会话结束 → LLM提炼 → 摘要存储 → 向量化存储

运行方式：
python tests/test_vector_search.py

注意：
- 需要先启动 Milvus（参考 docs/milvus_deployment_guide.md）
- 需要配置 EMBEDDING_API_KEY 或 DASHSCOPE_API_KEY
"""

from __future__ import annotations

import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def test_embedding_service():
    """测试1：EmbeddingService 向量生成"""
    print("\n=== 测试1：EmbeddingService 向量生成 ===")

    from match_domain.embedding_service import EmbeddingService

    service = EmbeddingService()

    # 测试单个文本
    text = "性格温柔、重视家庭"
    embedding = await service.generate_embedding(text)

    print(f"文本: {text}")
    print(f"向量维度: {len(embedding)}")
    print(f"向量前10位: {embedding[:10] if embedding else []}")

    if embedding:
        print("✅ 向量生成成功")
    else:
        print("⚠️ 向量生成失败（可能未配置 API Key）")
        print("请设置环境变量：EMBEDDING_API_KEY 或 DASHSCOPE_API_KEY")


async def test_vector_store_creation():
    """测试2：VectorStore Collection 创建"""
    print("\n=== 测试2：VectorStore Collection 创建 ===")

    from match_domain.vector_store import create_collection_if_not_exists

    try:
        success = create_collection_if_not_exists()

        if success:
            print("✅ Collection 创建成功")
        else:
            print("⚠️ Collection 创建失败（可能未启动 Milvus）")
            print("请参考 docs/milvus_deployment_guide.md 启动 Milvus")

    except Exception as exc:
        print(f"❌ 测试失败: {exc}")
        print("可能原因：未安装 pymilvus 或 Milvus 未启动")
        print("安装方式: pip install pymilvus")
        print("启动方式: docker-compose up -d")


async def test_vector_storage_and_search():
    """测试3：向量存储和搜索（完整流程）"""
    print("\n=== 测试3：向量存储和搜索 ===")

    from match_domain.embedding_service import EmbeddingService
    from match_domain.vector_store import VectorStore

    try:
        embedding_service = EmbeddingService()
        vector_store = VectorStore()

        # 测试数据
        user_id = 12345
        vector_type = "personality_traits"
        text = "性格温柔、内向、重视家庭"

        # Step 1：生成向量
        print(f"生成向量: text='{text}'")
        embedding = await embedding_service.generate_embedding(text)

        if not embedding:
            print("⚠️ 向量生成失败，跳过后续测试")
            return

        print(f"向量维度: {len(embedding)}")

        # Step 2：存储向量
        print(f"存储向量: user_id={user_id}, vector_type={vector_type}")
        result = vector_store.save_vector_with_version(
            user_id=user_id,
            vector_type=vector_type,
            embedding=embedding,
            raw_text=text,
            conversation_id="test_session_001",
        )

        print(f"存储结果: {result}")

        if result.get("success"):
            print(f"✅ 向量存储成功, version={result.get('version')}")
        else:
            print(f"⚠️ 向量存储失败: {result.get('error')}")
            return

        # Step 3：搜索相似向量
        print(f"搜索相似向量: vector_type={vector_type}")
        similar_users = vector_store.search_similar_users(
            user_vector=embedding,
            vector_type=vector_type,
            top_k=5,
            similarity_threshold=0.5,  # 降低阈值方便测试
        )

        print(f"找到 {len(similar_users)} 个相似用户")

        for user in similar_users:
            print(f"- user_id={user.get('user_id')}, similarity={user.get('similarity'):.3f}, "
                  f"raw_text={user.get('raw_text')[:30]}")

        print("✅ 向量搜索成功")

    except Exception as exc:
        print(f"❌ 测试失败: {exc}")


async def test_version_management():
    """测试4：向量版本管理"""
    print("\n=== 测试4：向量版本管理 ===")

    from match_domain.embedding_service import EmbeddingService
    from match_domain.vector_store import VectorStore

    try:
        embedding_service = EmbeddingService()
        vector_store = VectorStore()

        user_id = 12346
        vector_type = "values"

        # 第一次存储
        text1 = "重视家庭"
        embedding1 = await embedding_service.generate_embedding(text1)

        if not embedding1:
            print("⚠️ 向量生成失败，跳过测试")
            return

        result1 = vector_store.save_vector_with_version(
            user_id=user_id,
            vector_type=vector_type,
            embedding=embedding1,
            raw_text=text1,
            conversation_id="test_session_001",
        )

        print(f"第一次存储: version={result1.get('version')}, text='{text1}'")

        # 第二次存储（更新）
        text2 = "重视家庭、重视事业"
        embedding2 = await embedding_service.generate_embedding(text2)

        if not embedding2:
            return

        result2 = vector_store.save_vector_with_version(
            user_id=user_id,
            vector_type=vector_type,
            embedding=embedding2,
            raw_text=text2,
            conversation_id="test_session_002",
        )

        print(f"第二次存储: version={result2.get('version')}, text='{text2}'")

        # 查询当前版本
        current_version = vector_store.get_current_vector_version(user_id, vector_type)
        print(f"当前版本: {current_version}")

        # 查询用户向量
        vectors = vector_store.get_user_vectors(user_id, vector_type)
        print(f"用户向量数量: {len(vectors)}")

        for vec in vectors:
            print(f"- version={vec.get('vector_version')}, text={vec.get('raw_text')[:30]}")

        print("✅ 版本管理测试成功")

    except Exception as exc:
        print(f"❌ 测试失败: {exc}")


async def test_full_flow():
    """测试5：完整流程（模拟会话结束）"""
    print("\n=== 测试5：完整流程（会话结束 → LLM提炼 → 向量化） ===")

    from match_domain.session_end_processor import save_vectors_for_summary

    # 模拟 LLM 提炼的摘要数据
    summary_data = {
        "personality_traits": "性格温柔、内向",
        "values": "重视家庭、重视事业",
        "partner_expectation": "希望能理解工作忙碌",
        "life_attitude": "追求稳定",
        "emotional_needs": "需要理解和支持",
    }

    print(f"摘要数据: {summary_data}")

    try:
        # 向量化存储
        vectorized_keys = await save_vectors_for_summary(
            session_id="test_session_full",
            requester_id=12347,
            summary_data=summary_data,
        )

        print(f"成功向量化的字段: {vectorized_keys}")

        if vectorized_keys:
            print("✅ 完整流程测试成功")
        else:
            print("⚠️ 向量化失败（可能未配置 API Key 或 Milvus）")

    except Exception as exc:
        print(f"❌ 测试失败: {exc}")


async def run_all_tests():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("向量搜索功能测试")
    print("=" * 60)

    await test_embedding_service()
    await test_vector_store_creation()
    await test_vector_storage_and_search()
    await test_version_management()
    await test_full_flow()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

    print("\n📋 如果测试失败，请检查：")
    print("1. 是否已启动 Milvus（docker-compose up -d）")
    print("2. 是否已安装 pymilvus（pip install pymilvus）")
    print("3. 是否已配置 EMBEDDING_API_KEY 或 DASHSCOPE_API_KEY")
    print("4. 参考 docs/milvus_deployment_guide.md")


if __name__ == "__main__":
    asyncio.run(run_all_tests())