"""
实际更新数据库中的推荐卡片数据

执行方法: python scripts/actual_update_requester_summary.py
"""

import json
import sys
from pathlib import Path
import pymysql

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from match_domain.onboarding_search import _RELATIONSHIP_GOAL_DISPLAY
import re


def update_requester_summary(requester_summary: dict) -> dict:
    """更新 requester_summary 字段"""
    if not requester_summary:
        return requester_summary

    updated = dict(requester_summary)

    # 1. 年龄字段：从 age_bracket 提取实际年龄
    age_bracket = updated.get('age_bracket', '')
    if age_bracket and '-' in age_bracket:
        match = re.match(r'(\d+)-(\d+)', age_bracket)
        if match:
            age = int(match.group(1))
            updated['age'] = f"{age}岁"
            updated['age_bracket'] = f"{age}岁"

    # 2. 关系目标字段：映射为中文
    relationship_goal_raw = updated.get('relationship_goal', '')
    if relationship_goal_raw:
        relationship_goal_cn = _RELATIONSHIP_GOAL_DISPLAY.get(
            relationship_goal_raw,
            _RELATIONSHIP_GOAL_DISPLAY.get(relationship_goal_raw.lower(), relationship_goal_raw)
        )
        updated['relationship_goal'] = relationship_goal_cn
        updated['relationship_goal_raw'] = relationship_goal_raw

    # 3. 重新构建 summary_text
    summary_parts = []
    for field in ['age', 'city', 'education', 'occupation', 'relationship_goal']:
        value = updated.get(field)
        if value:
            summary_parts.append(value)

    if summary_parts:
        updated['summary_text'] = '；'.join(summary_parts)

    # 4. 确保 matched_on 字段存在
    if 'matched_on' not in updated:
        updated['matched_on'] = []

    return updated


def update_outreach_payload(outreach_payload: dict) -> dict:
    """更新 outreach_payload 中的 requester_summary"""
    if not outreach_payload:
        return outreach_payload

    updated = dict(outreach_payload)
    requester_summary = updated.get('requester_summary')

    if requester_summary:
        updated['requester_summary'] = update_requester_summary(requester_summary)

    return updated


def main():
    """主函数：实际更新数据库"""
    print("=" * 60)
    print("实际更新数据库中的推荐卡片数据")
    print("=" * 60)
    print()

    # 读取数据库配置（从 .env.local）
    import os
    from dotenv import load_dotenv

    load_dotenv('.env.local')

    db_host = '127.0.0.1'
    db_user = 'root'
    db_password = ''
    db_database = 'her_matchmaking'
    db_port = 3307

    print(f"数据库配置:")
    print(f"  host: {db_host}")
    print(f"  user: {db_user}")
    print(f"  database: {db_database}")
    print()

    # 连接数据库
    try:
        conn = pymysql.connect(
            host=db_host,
            port=db_port,
            user=db_user,
            password=db_password,
            database=db_database,
            charset='utf8mb4'
        )
        print("✅ 数据库连接成功")
        print()

    except Exception as e:
        print(f"❌ 数据库连接失败: {e}")
        print()
        print("📋 可能的原因:")
        print("1. 数据库密码配置错误（检查 .env.local 文件）")
        print("2. 数据库服务未启动")
        print("3. 数据库不存在")
        print()
        return

    cursor = conn.cursor()

    # 查询所有案件
    cursor.execute("SELECT case_id, outreach_payload_json FROM proxy_intro_cases")
    rows = cursor.fetchall()

    print(f"✅ 查询到 {len(rows)} 个案件")
    print()

    updated_count = 0

    for row in rows:
        case_id = row[0]
        payload_json = row[1]

        if not payload_json:
            continue

        try:
            payload = json.loads(payload_json)
            updated_payload = update_outreach_payload(payload)

            # 更新数据库
            updated_json = json.dumps(updated_payload, ensure_ascii=False)
            cursor.execute(
                "UPDATE proxy_intro_cases SET outreach_payload_json = %s WHERE case_id = %s",
                (updated_json, case_id)
            )

            updated_count += 1
            print(f"  ✅ 更新案件 {case_id}")

        except Exception as e:
            print(f"  ❌ 更新案件 {case_id} 失败: {e}")

    conn.commit()
    conn.close()

    print()
    print("=" * 60)
    print(f"✅ 更新完成！共更新 {updated_count} 个案件")
    print("=" * 60)
    print()

    print("📋 下一步:")
    print("1. 刷新浏览器，查看推荐卡片显示效果")
    print("2. 应该看到'28岁'、'先谈恋爱'、'本科；同城'等中文信息")


if __name__ == "__main__":
    main()