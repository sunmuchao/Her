"""长时间测试 gRPC keepalive 修复

目的：验证 60 秒后不会出现 "too_many_pings" 错误
（原来的错误可能在 10-30 秒后出现）
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from match_domain.vector_store_lite import VectorStoreLite

def test_long_connection():
    """测试 60 秒连接稳定性"""
    print("=" * 60)
    print("长时间测试：60 秒连接稳定性")
    print("=" * 60)
    print("目的：验证修改 keepalive_time_ms=60000 后不会出现错误")
    print()

    try:
        store = VectorStoreLite()
        print("✅ VectorStoreLite 初始化成功")

        # 测试 60 秒（每 5 秒检查一次）
        for i in range(12):
            time.sleep(5)
            result = store._client.has_collection('user_vectors')
            elapsed = (i + 1) * 5
            print(f"  {elapsed}s: 连接正常 (has_collection={result})")

        print()
        print("=" * 60)
        print("✅ 60 秒测试完成，无 'too_many_pings' 错误")
        print("=" * 60)

        store.close()
        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_long_connection()
    sys.exit(0 if success else 1)