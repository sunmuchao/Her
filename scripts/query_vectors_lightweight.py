"""轻量级向量查询：直接读取数据库文件，不启动Milvus服务

用途：当gateway服务正在运行时，避免锁冲突
方法：直接读取Parquet文件（Milvus Lite的存储格式）
"""

import os
import pandas as pd
from pathlib import Path


def query_vectors_lightweight(user_id: int, db_path: str):
    """轻量级查询向量数据（读取Parquet文件）

    Args:
        user_id: 用户ID
        db_path: 数据库文件路径
    """
    print("=" * 80)
    print(f"轻量级查询: user_id={user_id}")
    print("=" * 80)

    # Milvus Lite 数据存储在 Parquet 文件中
    db_dir = Path(db_path).parent / "user_vectors.db" / "collections" / "user_vectors"

    if not db_dir.exists():
        print(f"❌ 数据库目录不存在: {db_dir}")
        return

    # 查找所有 Parquet 文件
    parquet_files = list(db_dir.glob("*.parquet"))

    if not parquet_files:
        print(f"❌ 未找到数据文件")
        return

    print(f"✅ 找到 {len(parquet_files)} 个数据文件")

    # 读取所有数据
    all_data = []
    for pq_file in parquet_files:
        try:
            df = pd.read_parquet(pq_file)
            all_data.append(df)
        except Exception as e:
            print(f"⚠️  读取文件失败: {pq_file.name}, 错误: {e}")

    if not all_data:
        print("❌ 无法读取任何数据")
        return

    # 合并数据
    combined_df = pd.concat(all_data, ignore_index=True)

    # 过滤指定用户
    user_data = combined_df[combined_df['user_id'] == user_id]

    if user_data.empty:
        print(f"❌ 未找到 user_id={user_id} 的数据")
        return

    # 只显示激活的记录
    active_data = user_data[user_data['is_active'] == True]

    print(f"✅ 找到 {len(active_data)} 条激活的向量数据")
    print(f"   总共 {len(user_data)} 条记录（包括历史版本）")

    # 显示数据
    for idx, row in active_data.iterrows():
        print(f"\n向量类型: {row.get('vector_type')}")
        print(f"  文本: {row.get('raw_text')}")
        print(f"  版本: {row.get('vector_version')}")
        print(f"  创建时间: {row.get('create_time')}")
        print(f"  会话ID: {row.get('conversation_id')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='轻量级向量查询')
    parser.add_argument('--user-id', type=int, required=True, help='用户ID')

    args = parser.parse_args()

    db_path = "./external-systems/partner-http-gateway/milvus_lite_data/user_vectors.db"

    query_vectors_lightweight(args.user_id, db_path)