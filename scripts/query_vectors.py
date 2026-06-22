"""通用向量查询脚本"""
import sys
import os
sys.path.insert(0, '/Users/sunmuchao/Downloads/Her')

from match_domain.vector_store_lite import VectorStoreLite, VECTOR_TYPES_CONFIG


def query_user_vectors(user_id: int, vector_type: str = None):
    """查询用户向量数据

    Args:
        user_id: 用户ID
        vector_type: 向量类型(可选,不指定则查询所有)
    """
    # 修正：使用正确的向量库路径（与VectorStoreLite默认路径一致）
    db_file = "./milvus_lite_data/user_vectors.db"
    vector_store = VectorStoreLite(db_file=db_file)

    try:
        print("=" * 80)
        print(f"查询向量库: user_id={user_id}")
        print("=" * 80)

        # 查询
        vectors = vector_store.get_user_vectors(
            user_id=user_id,
            vector_type=vector_type
        )

        if not vectors:
            print(f"❌ 未找到 user_id={user_id} 的数据")
            if vector_type:
                print(f"   向量类型: {vector_type}")
            return

        # 打印结果
        print(f"✅ 找到 {len(vectors)} 条数据")
        for vec in vectors:
            print(f"\n向量类型: {vec.get('vector_type')}")
            print(f"  文本: {vec.get('raw_text')}")
            print(f"  版本: {vec.get('vector_version')}")
            print(f"  创建时间: {vec.get('create_time')}")

    finally:
        vector_store.close()


def list_all_vector_types():
    """列出所有向量类型及配置"""
    print("支持的向量类型:")
    print("=" * 80)
    for vtype, config in VECTOR_TYPES_CONFIG.items():
        print(f"\n{vtype}:")
        print(f"  衰减周期: {config.get('decay_days')}天")
        print(f"  衰减曲线: {config.get('decay_curve')}")
        print(f"  最低权重: {config.get('min_factor')}")
        print(f"  最大版本数: {config.get('max_version_count')}")
        print(f"  清理天数: {config.get('cleanup_days')}天")
        print(f"  说明: {config.get('description')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='查询向量库')
    parser.add_argument('--user-id', type=int, help='用户ID')
    parser.add_argument('--type', help='向量类型(可选)')
    parser.add_argument('--list-types', action='store_true', help='列出所有向量类型')

    args = parser.parse_args()

    if args.list_types:
        list_all_vector_types()
    elif args.user_id:
        query_user_vectors(args.user_id, args.type)
    else:
        parser.print_help()