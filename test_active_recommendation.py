#!/usr/bin/env python
"""测试主动推荐推送流程

主动推荐流程：
1. 用户打开发现页（create_session）
2. Discovery Agent运行，搜索候选人
3. Agent调用show_candidates工具，推送候选人到timeline
4. 前端渲染候选人卡片

运行方式：
cd /Users/sunmuchao/Downloads/Her
python test_active_recommendation.py

或者指定参数：
python test_active_recommendation.py --profile-id 2701 --candidates "张三:28:北京:程序员" --candidates "李四:30:上海:工程师"
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到sys.path
HER_ROOT = Path(__file__).resolve().parent
if str(HER_ROOT) not in sys.path:
    sys.path.insert(0, str(HER_ROOT))

from outer_mysql_compat import connect_mysql_repo_db, json_dumps, json_loads, row_to_dict


def test_push_active_recommendation(
    profile_id: int,
    candidates: list[dict],
    assistant_message: str = "根据你的资料，先给你看这些",
) -> dict:
    """测试主动推荐推送

    Args:
        profile_id: 用户profile_id
        candidates: 候选人列表，每个候选人包含：
            - name: 姓名
            - age: 年龄
            - city: 城市
            - occupation: 职业
            - profile_id: 候选人profile_id（可选，默认随机生成）
        assistant_message: 小雅的推荐消息

    Returns:
        测试结果
    """
    result = {
        "success": False,
        "error": None,
        "session_found": False,
        "timeline_updated": False,
        "cards_inserted": False,
        "candidate_count": 0,
    }

    try:
        # 1. 打开discovery数据库连接
        discovery_dsn = os.environ.get(
            "PARTNER_DISCOVERY_DB",
            "mysql://root@127.0.0.1:3307/her_discovery",
        )
        print(f"【步骤1】打开discovery数据库")
        conn = connect_mysql_repo_db(discovery_dsn, subsystem_name="discovery")

        # 2. 查询用户的最新session
        print(f"【步骤2】查询profile_id={profile_id}的最新session")
        row = conn.execute(
            """
            SELECT session_id, requester_id, profile_id, status, phase,
                   state_json, latest_view_json, created_at, updated_at
            FROM discovery_agent_sessions
            WHERE profile_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (int(profile_id),),
        ).fetchone()

        if not row:
            print(f"【步骤2失败】用户没有discovery session")
            result["error"] = "用户没有discovery session"
            conn.close()
            return result

        session_data = row_to_dict(row)
        print(f"【步骤2成功】找到session: session_id={session_data['session_id']}")
        result["session_found"] = True

        view_json = str(session_data.get("latest_view_json") or "{}")
        view = json_loads(view_json, {}) or {}

        # 3. 构建候选人卡片列表
        print(f"【步骤3】构建候选人卡片: 数量={len(candidates)}")
        cards = []
        for idx, candidate in enumerate(candidates):
            # 如果没有提供profile_id，生成一个测试ID
            candidate_profile_id = candidate.get("profile_id", 10000 + idx)

            card = {
                "card_id": f"candidate-{candidate_profile_id}",
                "profile_id": candidate_profile_id,
                "title": f"{candidate['name']} {candidate.get('age', '')}",
                "subtitle": f"{candidate.get('city', '')} · {candidate.get('occupation', '')}",
                "cover_image_url": candidate.get("image", None),
                "match_score": candidate.get("match_score", 0.7),
                "reason_summary": candidate.get("reason_summary", ""),
                "match_highlights": candidate.get("match_highlights", ["同城", "年龄合适"]),
                "open_profile_action": {
                    "type": "open_profile",
                    "profile_id": candidate_profile_id,
                },
            }
            cards.append(card)

        print(f"【步骤3成功】构建了{len(cards)}个候选人卡片")
        result["candidate_count"] = len(cards)

        # 4. 在timeline中插入assistant_message和result_group
        timeline = list(view.get("timeline") or [])
        print(f"【步骤4】当前timeline长度: {len(timeline)}")

        # 插入小雅消息
        now = datetime.now()
        timeline.append({
            "item_type": "assistant_message",
            "item_id": f"msg-a-{now.strftime('%Y%m%d%H%M%S')}",
            "body": assistant_message,
            "created_at": now.isoformat(),
        })

        # 插入候选人卡片组
        timeline.append({
            "item_type": "result_group",
            "item_id": f"group-{now.strftime('%Y%m%d%H%M%S')}",
            "title": "根据你的资料，先给你看这些",
            "cards": cards,
        })

        print(f"【步骤4成功】timeline新长度: {len(timeline)}")
        result["cards_inserted"] = True

        # 5. 更新session的latest_view_json
        print(f"【步骤5】更新session")
        view["timeline"] = timeline
        updated_at = datetime.now()

        conn.execute(
            """
            UPDATE discovery_agent_sessions
            SET latest_view_json = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (
                json_dumps(view),
                updated_at,
                str(session_data["session_id"]),
            ),
        )
        conn.commit()

        print(f"【步骤5成功】session已更新")
        result["timeline_updated"] = True

        conn.close()

        result["success"] = True
        print("【测试成功】主动推荐推送完成！")
        return result

    except Exception as e:
        print(f"【测试失败】错误: {e}")
        result["error"] = str(e)
        import traceback
        traceback.print_exc()
        return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="测试主动推荐推送流程")
    parser.add_argument("--profile-id", type=int, default=2701, help="用户profile_id")
    parser.add_argument(
        "--candidates",
        type=str,
        action="append",
        help="候选人信息，格式：name:age:city:occupation",
    )
    parser.add_argument("--message", type=str, default="根据你的资料，先给你看这些", help="小雅的推荐消息")

    args = parser.parse_args()

    # 解析候选人信息
    candidates = []
    if args.candidates:
        for candidate_str in args.candidates:
            parts = candidate_str.split(":")
            if len(parts) >= 4:
                candidates.append({
                    "name": parts[0],
                    "age": parts[1],
                    "city": parts[2],
                    "occupation": parts[3],
                    "match_score": 0.75,
                    "match_highlights": ["同城", "年龄合适"],
                })
    else:
        # 默认测试候选人
        candidates = [
            {
                "name": "张三",
                "age": "28",
                "city": "北京",
                "occupation": "程序员",
                "profile_id": 10001,
                "match_score": 0.85,
                "match_highlights": ["同城", "年龄合适", "职业互补"],
            },
            {
                "name": "李四",
                "age": "30",
                "city": "上海",
                "occupation": "工程师",
                "profile_id": 10002,
                "match_score": 0.70,
                "match_highlights": ["同城", "年龄合适"],
            },
            {
                "name": "王五",
                "age": "26",
                "city": "北京",
                "occupation": "设计师",
                "profile_id": 10003,
                "match_score": 0.65,
                "match_highlights": ["同城"],
            },
        ]

    print("=" * 50)
    print("开始测试主动推荐推送流程")
    print("=" * 50)
    print(f"profile_id: {args.profile_id}")
    print(f"candidates: {len(candidates)}人")
    for idx, c in enumerate(candidates):
        print(f"  [{idx+1}] {c['name']}, {c['age']}岁, {c['city']}, {c['occupation']}")
    print("=" * 50)

    result = test_push_active_recommendation(
        profile_id=args.profile_id,
        candidates=candidates,
        assistant_message=args.message,
    )

    print("=" * 50)
    print("测试结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 50)

    if result["success"]:
        print("✅ 测试成功！现在刷新发现页应该能看到主动推荐候选人卡片")
        print(f"   - 小雅消息: {args.message}")
        print(f"   - 候选人数量: {result['candidate_count']}人")
        print(f"   - timeline新长度: {len(candidates) * 2 + 2}（增加{len(candidates) * 2}个item）")
    else:
        print(f"❌ 测试失败: {result['error']}")