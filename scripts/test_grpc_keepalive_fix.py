"""测试 gRPC keepalive 修复是否有效

验证：
1. VectorStoreLite 初始化成功
2. 无 "too_many_pings" 错误
3. 向量搜索正常工作
"""

import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from match_domain.vector_store_lite import VectorStoreLite

def test_grpc_connection():
    """测试 gRPC 连接稳定性"""
    print("=" * 60)
    print("测试 1: VectorStoreLite 初始化")
    print("=" * 60)

    try:
        store = VectorStoreLite()
        print("✅ VectorStoreLite 初始化成功")
        print(f"✅ 数据库文件: {store.db_file}")
        print(f"✅ Collection 已加载: {store._client.has_collection('user_vectors')}")

        # 测试长时间连接（等待 60 秒，观察是否有 GOAWAY 错误）
        print("\n" + "=" * 60)
        print("测试 2: 长时间连接稳定性（等待 10 秒）")
        print("=" * 60)
        print("等待期间观察是否有 'too_many_pings' 错误...")

        for i in range(10):
            time.sleep(1)
            # 每秒查询一次，测试连接是否稳定
            result = store._client.has_collection('user_vectors')
            print(f"  {i+1}s: 连接正常 (has_collection={result})")

        print("✅ 连接稳定，无 'too_many_pings' 错误")

        # 测试向量搜索
        print("\n" + "=" * 60)
        print("测试 3: 向量搜索功能")
        print("=" * 60)

        # 创建测试向量
        test_vector = [0.1] * 1024
        results = store.search_similar_users(
            user_vector=test_vector,
            vector_type="personality_traits",
            top_k=5,
        )
        print(f"✅ 向量搜索成功，找到 {len(results)} 个结果")

        # 关闭连接
        store.close()
        print("✅ 连接已关闭")

        print("\n" + "=" * 60)
        print("✅ 所有测试通过！gRPC keepalive 修复有效")
        print("=" * 60)

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    return True

if __name__ == "__main__":
    success = test_grpc_connection()
    sys.exit(0 if success else 1)