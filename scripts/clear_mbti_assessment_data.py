#!/usr/bin/env python3
"""清除 MBTI 测评数据脚本

用于清除旧的 MBTI 测评结果，让用户重新测评时能看到最新的解读内容。
"""

import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from persona_memory_sync.persona_memory_lib import (
    mysql_connect,
    release_persona_connection,
    quote_mysql_ident,
)


def clear_mbti_assessment_data(
    source: str = "local",
    user_key: str | None = None,
    clear_all: bool = False,
):
    """清除 MBTI 测评数据

    Args:
        source: 数据源（local/partner_mysql 等）
        user_key: 指定用户 key，如果为 None 且 clear_all=False，则清除所有用户
        clear_all: 是否清除所有用户的测评数据
    """
    conn = mysql_connect(source)
    observation_table = "user_persona_observations"

    try:
        with conn.cursor() as cursor:
            if clear_all:
                # 清除所有 MBTI 测评数据
                print("清除所有用户的 MBTI 测评数据...")
                cursor.execute(
                    f"""
                    DELETE FROM {quote_mysql_ident(observation_table)}
                    WHERE field_name LIKE 'assessment%%'
                    """
                )
                deleted_count = cursor.rowcount
                print(f"已删除 {deleted_count} 条测评数据")

            elif user_key:
                # 清除指定用户的测评数据
                print(f"清除用户 {user_key} 的 MBTI 测评数据...")
                cursor.execute(
                    f"""
                    DELETE FROM {quote_mysql_ident(observation_table)}
                    WHERE user_key = %s AND field_name LIKE 'assessment%%'
                    """,
                    (user_key,)
                )
                deleted_count = cursor.rowcount
                print(f"已删除 {deleted_count} 条测评数据")

            else:
                # 清除所有用户的测评数据（默认行为）
                print("清除所有用户的 MBTI 测评数据...")
                cursor.execute(
                    f"""
                    DELETE FROM {quote_mysql_ident(observation_table)}
                    WHERE field_name LIKE 'assessment%%'
                    """
                )
                deleted_count = cursor.rowcount
                print(f"已删除 {deleted_count} 条测评数据")

            conn.commit()
            print("清除完成！")

    except Exception as e:
        print(f"清除失败: {e}")
        conn.rollback()
        raise
    finally:
        release_persona_connection(source, conn)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="清除 MBTI 测评数据")
    parser.add_argument("--source", default="local", help="数据源")
    parser.add_argument("--user-key", help="指定用户 key")
    parser.add_argument("--all", action="store_true", help="清除所有用户的测评数据")

    args = parser.parse_args()

    clear_mbti_assessment_data(
        source=args.source,
        user_key=args.user_key,
        clear_all=args.all,
    )