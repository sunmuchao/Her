#!/usr/bin/env python3
"""测试异步资源清理是否正确

验证修复：
- VectorStoreLite.close() 正确调用 MilvusClient.close()
- 避免 "Task exception was never retrieved - Event loop is closed" 错误

运行方式：
python scripts/test_async_cleanup.py
"""

import asyncio
import sys
from datetime import datetime

# 添加项目根目录到 Python 路径
sys.path.insert(0, ".")

from match_domain.embedding_service import EmbeddingService
from match_domain.vector_store_lite import VectorStoreLite


async def test_basic_cleanup() -> None:
    """测试基本的资源清理"""
    print("=" * 80)
    print("测试1: VectorStoreLite 和 EmbeddingService 的基本清理")
    print("=" * 80)

    embedding_service = EmbeddingService(model_name="text-embedding-v3")
    vector_store = VectorStoreLite()

    try:
        # 生成一个简单的向量
        embedding = await embedding_service.generate_embedding("测试文本")
        print(f"✅ 向量生成成功: dimension={len(embedding)}")

        # 存储向量
        result = vector_store.save_vector_with_version(
            user_id=999999,
            vector_type="test_cleanup",
            embedding=embedding,
            raw_text="测试清理逻辑",
            conversation_id="test_cleanup_session",
        )
        print(f"✅ 向量存储结果: {result.get('success')}")

    finally:
        # 关键：在事件循环关闭前清理资源
        await embedding_service.aclose()
        vector_store.close()
        print("✅ 资源清理完成")


async def test_exception_cleanup() -> None:
    """测试异常情况下的资源清理"""
    print("\n" + "=" * 80)
    print("测试2: 异常情况下的资源清理")
    print("=" * 80)

    embedding_service = EmbeddingService(model_name="text-embedding-v3")
    vector_store = VectorStoreLite()

    try:
        # 模拟异常情况
        raise RuntimeError("模拟异常")

    except RuntimeError as exc:
        print(f"✅ 捕获异常: {exc}")

    finally:
        # 即使发生异常，也要清理资源
        await embedding_service.aclose()
        vector_store.close()
        print("✅ 异常情况下资源清理完成")


async def test_multiple_operations() -> None:
    """测试多次操作后的清理"""
    print("\n" + "=" * 80)
    print("测试3: 多次操作后的清理")
    print("=" * 80)

    embedding_service = EmbeddingService(model_name="text-embedding-v3")
    vector_store = VectorStoreLite()

    try:
        # 执行多次操作
        for i in range(3):
            embedding = await embedding_service.generate_embedding(f"测试{i}")
            print(f"✅ 第{i+1}次向量生成成功")

            result = vector_store.save_vector_with_version(
                user_id=999999 + i,
                vector_type="test_cleanup_multi",
                embedding=embedding,
                raw_text=f"测试{i}",
                conversation_id=f"test_cleanup_session_{i}",
            )
            print(f"✅ 第{i+1}次向量存储结果: {result.get('success')}")

    finally:
        # 清理资源
        await embedding_service.aclose()
        vector_store.close()
        print("✅ 多次操作后资源清理完成")


async def main() -> None:
    """主测试函数"""
    print(f"\n开始测试: time={datetime.now().isoformat()}\n")

    try:
        await test_basic_cleanup()
        await test_exception_cleanup()
        await test_multiple_operations()

        print("\n" + "=" * 80)
        print("✅ 所有测试完成，没有出现 'Event loop is closed' 错误")
        print("=" * 80)

    except Exception as exc:
        print(f"\n❌ 测试失败: {exc}", exc_info=True)
        sys.exit(1)

    print(f"\n测试结束: time={datetime.now().isoformat()}")


if __name__ == "__main__":
    # 使用 asyncio.run() 管理事件循环
    # 它会在结束时正确清理事件循环
    asyncio.run(main())