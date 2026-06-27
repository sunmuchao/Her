#!/usr/bin/env python
"""测试推送被动推荐到discovery timeline的逻辑

运行方式：
cd /Users/sunmuchao/Downloads/Her
python test_push_proxy_intro.py

或者：
python test_push_proxy_intro.py --candidate-profile-id 2701 --requester-id 123
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


def test_push_proxy_intro_to_discovery_timeline(
    candidate_profile_id: int,
    requester_id: int,
    case_id: str,
    name: str = "测试用户",
    age: int = 28,
    city: str = "北京",
    occupation: str = "程序员",
) -> dict:
    """测试推送被动推荐到discovery timeline

    Args:
        candidate_profile_id: 候选人的profile_id（被推荐方）
        requester_id: 发起方的profile_id（想认识候选人的人）
        case_id: 案件ID
        name: 发起方姓名
        age: 发起方年龄
        city: 发起方城市
        occupation: 发起方职业

    Returns:
        测试结果（成功/失败/错误信息）
    """
    result = {
        "success": False,
        "error": None,
        "session_found": False,
        "timeline_updated": False,
        "card_inserted": False,
        "case_marked": False,
    }

    try:
        # 1. 打开discovery数据库连接
        discovery_dsn = os.environ.get(
            "PARTNER_DISCOVERY_DB",
            "mysql://root@127.0.0.1:3307/her_discovery",
        )
        print(f"【步骤1】打开discovery数据库: dsn={discovery_dsn}")
        conn = connect_mysql_repo_db(discovery_dsn, subsystem_name="discovery")

        # 2. 查询候选人的最新session
        print(f"【步骤2】查询candidate_id={candidate_profile_id}的最新session")
        row = conn.execute(
            """
            SELECT session_id, requester_id, profile_id, status, phase,
                   state_json, latest_view_json, created_at, updated_at
            FROM discovery_agent_sessions
            WHERE profile_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (int(candidate_profile_id),),
        ).fetchone()

        if not row:
            print(f"【步骤2失败】候选人没有discovery session，跳过推送")
            result["error"] = "候选人没有discovery session"
            conn.close()
            return result

        session_data = row_to_dict(row)
        print(f"【步骤2成功】找到session: session_id={session_data['session_id']}")
        result["session_found"] = True

        view_json = str(session_data.get("latest_view_json") or "{}")
        view = json_loads(view_json, {}) or {}

        # 3. 构建候选人卡片
        print(f"【步骤3】构建候选人卡片: requester_id={requester_id}, name={name}")
        candidate_card = {
            "card_id": f"candidate-{requester_id}",
            "profile_id": requester_id,
            "title": f"{name} {age}",
            "subtitle": f"{city} · {occupation}",
            "cover_image_url": None,
            "match_score": 0,
            "reason_summary": "",
            "open_profile_action": {
                "type": "open_profile",
                "profile_id": requester_id,
            },
        }

        # 4. 在timeline中插入assistant_message和result_group
        timeline = list(view.get("timeline") or [])
        print(f"【步骤4】当前timeline长度: {len(timeline)}")

        # 检查是否已经推送过
        already_pushed = any(
            str(item.get("item_id") or "").startswith(f"proxy-intro-msg-{case_id}")
            for item in timeline
        )
        if already_pushed:
            print(f"【步骤4失败】案件已推送，跳过")
            result["error"] = "案件已推送"
            conn.close()
            return result

        # 插入消息
        now = datetime.now()
        timeline.append({
            "item_type": "assistant_message",
            "item_id": f"proxy-intro-msg-{case_id}",
            "body": f"有人想认识你：{name}，{age}岁{city}{occupation}",
            "created_at": now.isoformat(),
        })

        # 插入候选人卡片
        timeline.append({
            "item_type": "result_group",
            "item_id": f"proxy-intro-group-{case_id}",
            "title": "有人想认识你",
            "cards": [candidate_card],
        })

        print(f"【步骤4成功】timeline新长度: {len(timeline)}")
        result["card_inserted"] = True

        # 5. 更新session的latest_view_json
        print(f"【步骤5】更新session: session_id={session_data['session_id']}")
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

        # 6. 标记案件为已推送（更新proxy_intro数据库）
        print(f"【步骤6】标记案件为已推送: case_id={case_id}")
        proxy_intro_dsn = os.environ.get(
            "PARTNER_MATCHMAKING_DB",
            "mysql://root@127.0.0.1:3307/her_matchmaking",
        )
        proxy_conn = connect_mysql_repo_db(proxy_intro_dsn, subsystem_name="matchmaking")

        outreach_payload = {"discovery_pushed": True}
        proxy_conn.execute(
            """
            UPDATE proxy_intro_cases
            SET outreach_payload_json = ?
            WHERE case_id = ?
            """,
            (
                json.dumps(outreach_payload, ensure_ascii=False),
                case_id,
            ),
        )
        proxy_conn.commit()
        proxy_conn.close()

        print(f"【步骤6成功】案件已标记")
        result["case_marked"] = True

        conn.close()

        result["success"] = True
        print("【测试成功】推送完成！")
        return result

    except Exception as e:
        print(f"【测试失败】错误: {e}")
        result["error"] = str(e)
        import traceback
        traceback.print_exc()
        return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="测试推送被动推荐到discovery timeline")
    parser.add_argument("--candidate-profile-id", type=int, default=2701, help="候选人的profile_id")
    parser.add_argument("--requester-id", type=int, default=123, help="发起方的profile_id")
    parser.add_argument("--case-id", type=str, default="match-case-test123", help="案件ID")
    parser.add_argument("--name", type=str, default="测试用户", help="发起方姓名")
    parser.add_argument("--age", type=int, default=28, help="发起方年龄")
    parser.add_argument("--city", type=str, default="北京", help="发起方城市")
    parser.add_argument("--occupation", type=str, default="程序员", help="发起方职业")

    args = parser.parse_args()

    print("=" * 50)
    print("开始测试推送被动推荐到discovery timeline")
    print("=" * 50)
    print(f"candidate_profile_id: {args.candidate_profile_id}")
    print(f"requester_id: {args.requester_id}")
    print(f"case_id: {args.case_id}")
    print("=" * 50)

    result = test_push_proxy_intro_to_discovery_timeline(
        candidate_profile_id=args.candidate_profile_id,
        requester_id=args.requester_id,
        case_id=args.case_id,
        name=args.name,
        age=args.age,
        city=args.city,
        occupation=args.occupation,
    )

    print("=" * 50)
    print("测试结果:")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    print("=" * 50)

    if result["success"]:
        print("✅ 测试成功！现在刷新发现页应该能看到卡片")
    else:
        print(f"❌ 测试失败: {result['error']}")