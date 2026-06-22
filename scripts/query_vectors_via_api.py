"""通过HTTP API查询向量数据（不占用数据库文件）"""
import requests
import json


def query_user_vectors_via_api(user_id: int, vector_type: str = None):
    """通过HTTP API查询用户向量数据

    Args:
        user_id: 用户ID
        vector_type: 向量类型(可选)
    """
    # 假设 gateway 服务运行在 localhost:8000
    base_url = "http://localhost:8000"

    print("=" * 80)
    print(f"通过API查询向量库: user_id={user_id}")
    print("=" * 80)

    try:
        # 调用API查询
        # 注意：这里需要根据实际的API接口调整
        response = requests.post(
            f"{base_url}/api/vector/query",
            json={
                "user_id": user_id,
                "vector_type": vector_type
            },
            timeout=10
        )

        if response.status_code != 200:
            print(f"❌ API调用失败: {response.status_code}")
            print(f"   错误信息: {response.text}")
            return

        data = response.json()

        if not data.get("vectors"):
            print(f"❌ 未找到 user_id={user_id} 的数据")
            return

        vectors = data["vectors"]
        print(f"✅ 找到 {len(vectors)} 条数据")

        for vec in vectors:
            print(f"\n向量类型: {vec.get('vector_type')}")
            print(f"  文本: {vec.get('raw_text')}")
            print(f"  版本: {vec.get('vector_version')}")
            print(f"  创建时间: {vec.get('create_time')}")

    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到 gateway 服务")
        print("   请确认服务是否运行在 localhost:8000")
    except Exception as e:
        print(f"❌ 查询失败: {e}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='通过API查询向量库')
    parser.add_argument('--user-id', type=int, required=True, help='用户ID')
    parser.add_argument('--type', help='向量类型(可选)')
    parser.add_argument('--port', type=int, default=8000, help='服务端口')

    args = parser.parse_args()

    query_user_vectors_via_api(args.user_id, args.type)