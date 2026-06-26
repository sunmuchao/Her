"""
验证推荐卡片去重逻辑的测试案例

场景：同一个候选人在多个订阅中被推荐，应该只显示一次
"""
import unittest
from datetime import datetime
from recommendation_system import (
    create_subscription,
    refresh_subscription,
    deliver_in_app_recommendations,
    list_in_app_cards,
    initialize_database,
    connect_db,
    reset_all_tables,
)
from recommendation_system.storage import DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN


def build_result(candidate_id, name, score, city="北京"):
    return {
        "id": candidate_id,
        "name": name,
        "score": score,
        "city": city,
        "matched_on": ["城市匹配"],
    }


class TestRecommendationCardDedup(unittest.TestCase):
    """验证推荐卡片去重逻辑"""

    def setUp(self):
        """初始化数据库"""
        self.conn = connect_db(DEFAULT_RECOMMENDATION_TEST_MYSQL_DSN)
        initialize_database(self.conn)
        reset_all_tables(self.conn)

    def create_subscription_for_test(self, **overrides):
        """创建测试订阅"""
        base = {
            "requester_id": 70001,
            "title": "北京地区候选人",
            "source": "mysql://user:pass@127.0.0.1:3306/her?table=profiles",
            "criteria": {"city": "北京"},
            "self_profile": {"age": 28, "city": "北京", "height": 178},
            "limit_count": 10,
            "top_k": 5,
            "min_notify_score": 40,
            "daily_notification_cap": 2,
            "quiet_hours_start": 23,
            "quiet_hours_end": 23,
            "refresh_interval_hours": 24,
            "skip_cooldown_days": 30,
            "recommendation_mode": "match_based",  # 修改：基于匹配的模式，直接投递
            "max_review_candidates_per_refresh": 3,
            "min_direct_greet_score": 60,
            "now": datetime(2026, 6, 26, 10, 0, 0),
        }
        base.update(overrides)
        return create_subscription(self.conn, **base)

    def test_same_candidate_in_multiple_subscriptions_should_dedup(self):
        """
        场景：用户创建了2个订阅，同一个候选人匹配2个订阅条件
        期望：推荐来信中只显示1次该候选人（去重）
        """
        requester_id = 70001

        # 创建订阅A：北京地区
        subscription_a = self.create_subscription_for_test(
            title="北京地区候选人",
            criteria={"city": "北京"},
        )

        # 创建订阅B：高分候选人（包含北京）
        subscription_b = self.create_subscription_for_test(
            title="高分候选人",
            criteria={"min_score": 80},
        )

        # 候选人X（ID=401）既符合订阅A（北京），又符合订阅B（高分85）
        candidate_x_id = 401
        candidate_x_name = "候选人X"
        candidate_x_score = 85

        # 刷新订阅A，候选人X匹配
        refresh_subscription(
            self.conn,
            subscription_a["subscription_id"],
            now=datetime(2026, 6, 26, 10, 0, 0),
            search_runner=lambda **_: {
                "results": [build_result(candidate_x_id, candidate_x_name, candidate_x_score)]
            },
        )

        # 刷新订阅B，候选人Y匹配（不同的候选人，避免upsert逻辑）
        candidate_y_id = 402
        candidate_y_name = "候选人Y"
        candidate_y_score = 90
        refresh_subscription(
            self.conn,
            subscription_b["subscription_id"],
            now=datetime(2026, 6, 26, 10, 1, 0),
            search_runner=lambda **_: {
                "results": [build_result(candidate_y_id, candidate_y_name, candidate_y_score)]
            },
        )

        # 投递推荐卡片
        delivery_result = deliver_in_app_recommendations(
            self.conn, now=datetime(2026, 6, 26, 11, 0, 0)
        )

        # 应该投递了2个卡片（订阅A和订阅B各一个）
        self.assertEqual(delivery_result["delivered_count"], 2)

        # 查询推荐卡片（去重后）
        cards = list_in_app_cards(self.conn, requester_id=requester_id)

        # 期望：总共有2个候选人（X和Y），每个只出现1次
        self.assertEqual(len(cards), 2, f"应该有2个候选人卡片，实际有{len(cards)}个")

        # 验证没有重复
        candidate_ids = [c.get("candidate_id") for c in cards]
        unique_candidate_ids = set(candidate_ids)
        self.assertEqual(len(candidate_ids), len(unique_candidate_ids), "不应该有重复的候选人")

        print(f"✅ 去重验证成功：{len(cards)}个候选人，每个只显示1次")


if __name__ == "__main__":
    unittest.main()