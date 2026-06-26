"""验证 relation_key 修复效果的端到端测试"""
#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import pathlib
from datetime import datetime

REPO_ROOT = pathlib.Path(__file__).resolve().parent
MATCHMAKING_ROOT = REPO_ROOT / "external-systems" / "partner-matchmaking-system"
RECOMMENDATION_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"
CHAT_ROOT = REPO_ROOT / "external-systems" / "partner-chat-system"

for root in (MATCHMAKING_ROOT, RECOMMENDATION_ROOT, CHAT_ROOT, REPO_ROOT):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

from matchmaking_system.storage import connect_db as connect_matchmaking_db
from matchmaking_system.proxy_intro_core import create_match_case, get_match_case, inflate_match_case
from recommendation_system.storage import connect_db as connect_recommendation_db
from recommendation_system import create_subscription, refresh_subscription
from match_domain import matchmaking_relation_key


def test_relation_key_persistence():
    """测试 relation_key 是否正确持久化到 case 表"""

    # 连接数据库
    mm_dsn = os.environ.get("PARTNER_MATCHMAKING_DB", "mysql://root@127.0.0.1:3307/her_matchmaking")
    rec_dsn = os.environ.get("PARTNER_RECOMMENDATION_DB", "mysql://root@127.0.0.1:3307/her_recommendation")

    mm_conn = connect_matchmaking_db(mm_dsn)
    rec_conn = connect_recommendation_db(rec_dsn)

    try:
        # 创建测试订阅和推荐
        now = datetime(2026, 6, 26, 15, 0, 0)

        subscription = create_subscription(
            rec_conn,
            requester_id=9999,
            self_id=9999,
            title="relation_key验证测试",
            source="mysql://test",
            criteria={"gender": "女"},
            self_profile={"age": 30, "city": "无锡"},
            now=now,
        )

        refresh_subscription(
            rec_conn,
            subscription["subscription_id"],
            now=now,
            search_runner=lambda **_: {
                "results": [
                    {
                        "id": 8888,
                        "name": "测试候选人",
                        "score": 85,
                        "fit_score": 80,
                        "confidence_score": 6,
                        "risk_score": 0,
                        "matched_on": ["同城"],
                        "reciprocal_on": [],
                        "missing_fields": [],
                        "self_profile_gaps": [],
                        "risk_flags": [],
                        "match_evidence": [],
                        "follow_up_questions": [],
                        "photo_preview": [],
                        "profile": {
                            "age": 28,
                            "city": "无锡",
                        },
                    }
                ]
            },
        )

        # 创建 match case
        case = create_match_case(
            mm_conn,
            recommendation_conn=rec_conn,
            subscription_id=subscription["subscription_id"],
            candidate_id=8888,
            now=now,
        )

        print(f"✅ 创建 case 成功: {case['case_id']}")

        # 验证 relation_key 是否持久化（直接查询数据库）
        result = mm_conn.execute(
            "SELECT relation_key FROM proxy_intro_cases WHERE case_id = %s",
            (case["case_id"],)
        )
        row = result.fetchone()
        relation_key_in_db = str(row[0] or "").strip() if row else ""

        if not relation_key_in_db:
            print("❌ 错误: relation_key 未持久化到数据库")
            return False

        print(f"✅ relation_key 已持久化: {relation_key_in_db}")

        # 验证 inflate 时能正确读取 relation_key（使用独立的连接）
        # 注意：这里需要提供正确的 recommendation_conn
        result = mm_conn.execute("SELECT * FROM proxy_intro_cases WHERE case_id = %s", (case["case_id"],))
        raw_case_data = result.fetchone()

        # 将查询结果转换为字典
        columns = result.description
        raw_case_dict = dict(zip([col[0] for col in columns], raw_case_data))

        inflated_case = inflate_match_case(raw_case_dict, conn=mm_conn, recommendation_conn=rec_conn)
        relation_key_inflated = str(inflated_case.get("relation_key") or "").strip()

        if relation_key_inflated != relation_key_in_db:
            print(f"❌ 错误: inflate 后的 relation_key 不一致")
            print(f"  数据库: {relation_key_in_db}")
            print(f"  Inflate: {relation_key_inflated}")
            return False

        print(f"✅ inflate 时正确读取 relation_key: {relation_key_inflated}")

        # 验证 relation_key 格式正确
        expected_format = "her#profile:"
        if not relation_key_in_db.startswith(expected_format):
            print(f"❌ 错误: relation_key 格式不正确: {relation_key_in_db}")
            return False

        print(f"✅ relation_key 格式正确")

        # 验证防御性逻辑（删除 recommendation 后仍能获取 relation_key）
        rec_conn.execute(
            "DELETE FROM profile_recommendations WHERE subscription_id = %s AND candidate_id = %s",
            (subscription["subscription_id"], 8888)
        )
        rec_conn.commit()

        # 再次 inflate，应该仍能从 case 获取 relation_key
        result = mm_conn.execute("SELECT * FROM proxy_intro_cases WHERE case_id = %s", (case["case_id"],))
        raw_case_data2 = result.fetchone()
        columns2 = result.description
        raw_case_dict2 = dict(zip([col[0] for col in columns2], raw_case_data2))

        inflated_case2 = inflate_match_case(raw_case_dict2, conn=mm_conn, recommendation_conn=rec_conn)
        relation_key_after_delete = str(inflated_case2.get("relation_key") or "").strip()

        if relation_key_after_delete != relation_key_in_db:
            print(f"❌ 错误: recommendation 删除后 relation_key 缺失")
            print(f"  期望: {relation_key_in_db}")
            print(f"  实际: {relation_key_after_delete}")
            return False

        print(f"✅ recommendation 删除后仍能获取 relation_key（防御性逻辑验证）")

        # 清理测试数据
        mm_conn.execute("DELETE FROM proxy_intro_cases WHERE case_id = %s", (case["case_id"],))
        mm_conn.commit()

        rec_conn.execute("DELETE FROM profile_recommendations WHERE subscription_id = %s", (subscription["subscription_id"],))
        rec_conn.execute("DELETE FROM recommendation_subscriptions WHERE subscription_id = %s", (subscription["subscription_id"],))
        rec_conn.commit()

        print("\n🎉 所有验证通过！relation_key 修复效果确认：")
        print("  ✅ 创建 case 时 relation_key 正确持久化")
        print("  ✅ inflate 时优先从 case 读取 relation_key")
        print("  ✅ relation_key 格式正确")
        print("  ✅ recommendation 缺失时防御性逻辑生效")

        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        mm_conn.close()
        rec_conn.close()


def test_existing_cases():
    """验证现有 cases 的 relation_key 状态"""

    mm_dsn = os.environ.get("PARTNER_MATCHMAKING_DB", "mysql://root@127.0.0.1:3307/her_matchmaking")
    mm_conn = connect_matchmaking_db(mm_dsn)

    try:
        # 检查现有 cases 的 relation_key（使用兼容的execute方式）
        result = mm_conn.execute("""
            SELECT case_id, requester_id, candidate_id, relation_key
            FROM proxy_intro_cases
            WHERE relation_key IS NULL OR relation_key = ''
        """)
        empty_cases = list(result.fetchall())

        if len(empty_cases) > 0:
            print(f"❌ 发现 {len(empty_cases)} 个 cases 的 relation_key 为空")
            for case in empty_cases:
                print(f"  case_id: {case[0]}")
            return False

        print(f"✅ 所有现有 cases 都有 relation_key")

        # 统计总数
        result = mm_conn.execute("SELECT COUNT(*) as cnt FROM proxy_intro_cases")
        total = list(result.fetchone())[0]
        print(f"  总计 {total} 个 cases")

        # 显示示例
        result = mm_conn.execute("SELECT case_id, relation_key FROM proxy_intro_cases LIMIT 3")
        samples = list(result.fetchall())
        print(f"\n示例数据：")
        for case in samples:
            print(f"  {case[0]}: {case[1]}")

        return True

    except Exception as e:
        print(f"❌ 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        mm_conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("relation_key 修复效果端到端验证")
    print("=" * 60)

    # 先验证现有数据
    print("\n【步骤1】验证现有 cases 的 relation_key 状态")
    existing_ok = test_existing_cases()

    # 再验证新创建的 case
    print("\n【步骤2】验证新创建 case 的 relation_key 持久化")
    new_case_ok = test_relation_key_persistence()

    print("\n" + "=" * 60)
    if existing_ok and new_case_ok:
        print("✅ 验证成功！relation_key 修复完全有效")
        print("=" * 60)
        sys.exit(0)
    else:
        print("❌ 验证失败！需要检查修复代码")
        print("=" * 60)
        sys.exit(1)