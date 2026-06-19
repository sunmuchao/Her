#!/usr/bin/env python3
"""
生成5位候选人的完整Discovery Session聊天记录SQL语句
包括：李欣琪、陈佳悦、冯静雯（新session）
张安萌、陈以心（补充现有session）
"""

import json
from datetime import datetime, timedelta
import uuid

def generate_session_id():
    """生成session_id"""
    return f"discovery-session-{uuid.uuid4().hex[:12]}"

def escape_json(obj):
    """转义JSON字符串用于SQL"""
    return json.dumps(obj).replace("'", "''").replace("\\", "\\\\")

def generate_li_xinqi_sql():
    """李欣琪 - 回避型依恋"""
    session_id = generate_session_id()
    profile_id = 573
    created_at = datetime(2026, 6, 10, 14, 30, 0)

    sql_lines = []

    # 创建session
    sql_lines.append(f"""
INSERT INTO discovery_agent_sessions
(session_id, requester_id, profile_id, status, phase, state_json, latest_view_json, created_at, updated_at)
VALUES ('{session_id}', {profile_id}, {profile_id}, 'active', 'results_shown', '{escape_json({})}', '{escape_json({})}', '{created_at}', '{created_at}');
""")

    # Turn 1: session_opened
    agent_decision = {
        'assistant_message': '我根据你刚填的资料筛了几位，你先看看有没有眼缘。觉得不合适，随时跟我说。',
        'criteria_labels': ['无锡', '男', '27-32岁', '认真恋爱'],
        'phase': 'results_shown',
        'result_group_title': '根据你的资料，先给你看这些',
        'selected_candidates': [
            {'profile_id': 8931, 'reason_summary': '30岁产品经理，情绪稳定理性，社交圈简单'},
            {'profile_id': 7724, 'reason_summary': '29岁药师，温和有责任感，工作稳定'},
            {'profile_id': 6726, 'reason_summary': '32岁教师，边界清楚有主见，尊重彼此空间'}
        ],
        'suggested_actions': []
    }

    view_snapshot = {
        'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
        'criteria_chips': [
            {'chip_id': 'chip-1', 'label': '无锡'},
            {'chip_id': 'chip-2', 'label': '男'},
            {'chip_id': 'chip-3', 'label': '27-32岁'},
            {'chip_id': 'chip-4', 'label': '认真恋爱'}
        ],
        'timeline': [
            {'item_type': 'assistant_message', 'body': '我根据你刚填的资料筛了几位...', 'created_at': created_at.isoformat()},
            {'item_type': 'result_group', 'title': '根据你的资料，先给你看这些', 'cards': [
                {'profile_id': 8931, 'title': '张辰瑞 30'},
                {'profile_id': 7724, 'title': '赵浩衡 29'},
                {'profile_id': 6726, 'title': '赵思凯 32'}
            ]}
        ]
    }

    sql_lines.append(f"""
INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('{session_id}', 'session_opened', NULL, '{escape_json(agent_decision)}', '{escape_json(view_snapshot)}', '{created_at}');
""")

    # Turn 2-5: 用户对话
    dialogues = [
        {
            'time_offset': timedelta(minutes=5),
            'user_message': '我比较看重边界感，不喜欢对方太黏人，希望能有自己的空间',
            'agent_message': '收到。我注意到你提到边界感，这点很重要。你希望对方能理解你需要独立空间，不强制分享所有事情，对吗？我帮你把这点加到筛选条件里。',
            'phase': 'collecting_preferences'
        },
        {
            'time_offset': timedelta(minutes=8),
            'user_message': '对，而且我希望对方有自己的爱好和朋友圈，不要每天都要在一起',
            'agent_message': '明白了，欣琪。你希望的是一种成熟独立的关系模式，两个人都有自己的生活和空间，但关键时刻能彼此支持。我重新调整了一下筛选，这次给你推荐几位更符合你期待的：',
            'phase': 'results_shown'
        },
        {
            'time_offset': timedelta(minutes=16),
            'user_message': '赵思凯看起来不错，他的边界感和独立性都比较符合',
            'agent_message': '好的，欣琪！赵思凯32岁教师，确实很符合你的要求。他的性格是边界清楚、有主见、尊重彼此空间，而且他也提到希望两个人都有独立的生活。',
            'phase': 'results_shown'
        },
        {
            'time_offset': timedelta(minutes=28),
            'user_message': '张辰瑞有点太理性了，感觉相处起来会比较冷淡',
            'agent_message': '收到，欣琪。你提到张辰瑞太理性可能显得冷淡，这点我理解。虽然理性是优点，但如果缺乏温度，确实可能影响相处感受。',
            'phase': 'results_shown'
        }
    ]

    for idx, dialogue in enumerate(dialogues):
        turn_time = created_at + dialogue['time_offset']
        agent_decision = {
            'assistant_message': dialogue['agent_message'],
            'phase': dialogue['phase'],
            'selected_candidates': [
                {'profile_id': 6726, 'reason_summary': '32岁教师，边界清楚'}
            ] if idx >= 2 else []
        }
        view_snapshot = {
            'timeline': [
                {'item_type': 'user_message', 'body': dialogue['user_message']},
                {'item_type': 'assistant_message', 'body': dialogue['agent_message']}
            ]
        }

        sql_lines.append(f"""
INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('{session_id}', 'user_message', '{dialogue['user_message']}', '{escape_json(agent_decision)}', '{escape_json(view_snapshot)}', '{turn_time}');
""")

    return '\n'.join(sql_lines)

def generate_chen_jiayue_sql():
    """陈佳悦 - 安全型依恋"""
    session_id = generate_session_id()
    profile_id = 6609
    created_at = datetime(2026, 6, 11, 15, 20, 0)

    sql_lines = []

    sql_lines.append(f"""
INSERT INTO discovery_agent_sessions
(session_id, requester_id, profile_id, status, phase, state_json, latest_view_json, created_at, updated_at)
VALUES ('{session_id}', {profile_id}, {profile_id}, 'active', 'results_shown', '{escape_json({})}', '{escape_json({})}', '{created_at}', '{created_at}');
""")

    dialogues = [
        {
            'time_offset': timedelta(minutes=0),
            'request_kind': 'session_opened',
            'user_message': None,
            'agent_message': '我根据你刚填的资料筛了几位，你先看看有没有眼缘。觉得不合适，随时跟我说。',
            'candidates': [8931, 7724, 6726]
        },
        {
            'time_offset': timedelta(minutes=6),
            'request_kind': 'user_message',
            'user_message': '我希望能找个性格温和、有责任感的人，最好是工作稳定的',
            'agent_message': '收到，佳悦。你提到希望对方性格温和、有责任感且工作稳定，这些都是建立长期关系的基础。',
            'candidates': [7724, 6726, 5701]
        },
        {
            'time_offset': timedelta(minutes=10),
            'request_kind': 'user_message',
            'user_message': '我长期在无锡定居，希望对方也有定居意向，不要经常变动',
            'agent_message': '明白了，佳悦。你在无锡长期定居，希望对方也有明确的定居计划，这样两人才能一起规划未来。',
            'candidates': [7724, 6726, 5701]
        },
        {
            'time_offset': timedelta(minutes=20),
            'request_kind': 'user_message',
            'user_message': '赵浩衡看起来不错，温和有责任感，而且也是药师工作稳定',
            'agent_message': '好的，佳悦！赵浩衡29岁药师，确实很符合你的要求。他的性格温和有责任感，而且在无锡定居多年。',
            'candidates': [7724]
        }
    ]

    for dialogue in dialogues:
        turn_time = created_at + dialogue['time_offset']
        agent_decision = {
            'assistant_message': dialogue['agent_message'],
            'phase': 'results_shown',
            'selected_candidates': [{'profile_id': c, 'reason_summary': ''} for c in dialogue['candidates']]
        }
        view_snapshot = {'timeline': []}

        sql_lines.append(f"""
INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('{session_id}', '{dialogue['request_kind']}', {f"'{dialogue['user_message']}'" if dialogue['user_message'] else 'NULL'}, '{escape_json(agent_decision)}', '{escape_json(view_snapshot)}', '{turn_time}');
""")

    return '\n'.join(sql_lines)

def generate_feng_jingwen_sql():
    """冯静雯 - 焦虑型依恋"""
    session_id = generate_session_id()
    profile_id = 3611
    created_at = datetime(2026, 6, 12, 16, 45, 0)

    sql_lines = []

    sql_lines.append(f"""
INSERT INTO discovery_agent_sessions
(session_id, requester_id, profile_id, status, phase, state_json, latest_view_json, created_at, updated_at)
VALUES ('{session_id}', {profile_id}, {profile_id}, 'active', 'results_shown', '{escape_json({})}', '{escape_json({})}', '{created_at}', '{created_at}');
""")

    dialogues = [
        {
            'time_offset': timedelta(minutes=0),
            'request_kind': 'session_opened',
            'user_message': None,
            'agent_message': '我根据你刚填的资料筛了几位，你先看看有没有眼缘。觉得不合适，随时跟我说。',
            'candidates': [7724, 6726, 8931]
        },
        {
            'time_offset': timedelta(minutes=8),
            'request_kind': 'user_message',
            'user_message': '我比较慢热，需要对方主动一点，不然我会很焦虑，担心他是不是不喜欢我',
            'agent_message': '收到，静雯。你提到自己慢热需要对方主动，这种感受很真实。焦虑感往往源于不确定，所以你希望对方能给你清晰的安全感确认。',
            'candidates': []
        },
        {
            'time_offset': timedelta(minutes=11),
            'request_kind': 'user_message',
            'user_message': '对，我希望他能主动分享日常，不要让我总是猜测他的想法',
            'agent_message': '明白了，静雯。你希望的是一种透明度高的关系，对方愿意主动分享日常和想法。',
            'candidates': [7724, 5701, 1318]
        },
        {
            'time_offset': timedelta(minutes=16),
            'request_kind': 'user_message',
            'user_message': '而且我有长期在无锡定居的打算，希望对方也有',
            'agent_message': '收到，静雯。长期定居无锡也是个重要的安全感来源。',
            'candidates': [7724, 5701, 6726]
        },
        {
            'time_offset': timedelta(minutes=28),
            'request_kind': 'user_message',
            'user_message': '赵浩衡看起来不错，温和细腻，而且他也是药师，工作稳定',
            'agent_message': '好的，静雯！赵浩衡29岁药师，温和细腻，善于倾听和沟通，而且他提到愿意主动分享日常。',
            'candidates': [7724]
        }
    ]

    for dialogue in dialogues:
        turn_time = created_at + dialogue['time_offset']
        agent_decision = {
            'assistant_message': dialogue['agent_message'],
            'phase': 'results_shown' if dialogue['candidates'] else 'collecting_preferences',
            'selected_candidates': [{'profile_id': c, 'reason_summary': ''} for c in dialogue['candidates']]
        }
        view_snapshot = {'timeline': []}

        sql_lines.append(f"""
INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('{session_id}', '{dialogue['request_kind']}', {f"'{dialogue['user_message']}'" if dialogue['user_message'] else 'NULL'}, '{escape_json(agent_decision)}', '{escape_json(view_snapshot)}', '{turn_time}');
""")

    return '\n'.join(sql_lines)

def generate_zhang_anmeng_sql():
    """张安萌 - 补充现有session"""
    session_id = 'discovery-session-ff37e68c0df5'  # 已存在的session
    created_at_base = datetime(2026, 5, 28, 18, 3, 8)  # 从"你好呀"之后继续

    sql_lines = []

    dialogues = [
        {
            'time_offset': timedelta(minutes=5),
            'user_message': '这几位看起来都还不错，不过我希望能找个性格温和善沟通的',
            'agent_message': '收到，安萌。你提到希望对方性格温和善沟通，这和你的性格很匹配。我帮你调整筛选，重点看几位沟通能力强的：',
            'candidates': [1318, 7724, 2288]
        },
        {
            'time_offset': timedelta(minutes=10),
            'user_message': '胡嘉衡看起来不错，29岁会计，而且性格温和善沟通',
            'agent_message': '好的，安萌！胡嘉衡29岁会计，确实性格温和善沟通，和你很匹配。而且他在无锡定居多年，工作稳定。',
            'candidates': [1318]
        },
        {
            'time_offset': timedelta(minutes=15),
            'user_message': '不过孙承骁也是采购，跟我职业一样，会不会更有共同话题',
            'agent_message': '你说得对，安萌！孙承骁28岁采购，和你职业相同，确实可能有更多共同话题和行业理解。我帮你看看他的详细资料：',
            'candidates': [2288]
        },
        {
            'time_offset': timedelta(minutes=20),
            'user_message': '嗯，那我先看看孙承骁的资料吧，采购同行应该挺有意思',
            'agent_message': '好的，安萌！我帮你打开孙承骁的资料页。他是28岁采购，本科学历，在无锡工作稳定。你们职业相同，确实有很多可以聊的话题。',
            'candidates': [2288]
        }
    ]

    for dialogue in dialogues:
        turn_time = created_at_base + dialogue['time_offset']
        agent_decision = {
            'assistant_message': dialogue['agent_message'],
            'phase': 'results_shown',
            'selected_candidates': [{'profile_id': c, 'reason_summary': ''} for c in dialogue['candidates']]
        }
        view_snapshot = {'timeline': []}

        sql_lines.append(f"""
INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('{session_id}', 'user_message', '{dialogue['user_message']}', '{escape_json(agent_decision)}', '{escape_json(view_snapshot)}', '{turn_time}');
""")

    return '\n'.join(sql_lines)

def generate_chen_yixin_sql():
    """陈以心 - 补充现有session"""
    session_id = 'discovery-session-0f33cf41a7bd'  # 已存在的session
    created_at_base = datetime(2026, 5, 29, 11, 30, 6)  # 从session_opened之后继续

    sql_lines = []

    dialogues = [
        {
            'time_offset': timedelta(minutes=5),
            'user_message': '你好，我想看看这几位的详细信息',
            'agent_message': '你好，以心！刚才根据你的资料筛了5位无锡的男生，你可以先看看有没有眼缘。如果有觉得不错的，或者想调整筛选方向，随时跟我说～',
            'candidates': [8931, 7724, 7132, 8481, 6726]
        },
        {
            'time_offset': timedelta(minutes=8),
            'user_message': '我希望能找个开朗有责任感的人，最好是硕士学历',
            'agent_message': '收到，以心。你提到希望对方开朗有责任感，而且是硕士学历，这些条件和你都很匹配。我帮你重新筛选，重点看几位硕士学历的：',
            'candidates': [8931, 7132, 6726]
        },
        {
            'time_offset': timedelta(minutes=12),
            'user_message': '张辰瑞看起来不错，30岁产品经理，硕士学历',
            'agent_message': '好的，以心！张辰瑞30岁产品经理，硕士学历，确实符合你的要求。而且他性格开朗理性，社交圈简单。',
            'candidates': [8931]
        },
        {
            'time_offset': timedelta(minutes=18),
            'user_message': '嗯，而且我也是产品运营，和他职业相近，应该有共同话题',
            'agent_message': '你说得对，以心！你做产品运营，他做产品经理，职业确实相近，有很多可以聊的话题。我帮你打开他的资料页看看？',
            'candidates': [8931]
        }
    ]

    for dialogue in dialogues:
        turn_time = created_at_base + dialogue['time_offset']
        agent_decision = {
            'assistant_message': dialogue['agent_message'],
            'phase': 'results_shown',
            'selected_candidates': [{'profile_id': c, 'reason_summary': ''} for c in dialogue['candidates']]
        }
        view_snapshot = {'timeline': []}

        sql_lines.append(f"""
INSERT INTO discovery_agent_turns
(session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, created_at)
VALUES ('{session_id}', 'user_message', '{dialogue['user_message']}', '{escape_json(agent_decision)}', '{escape_json(view_snapshot)}', '{turn_time}');
""")

    return '\n'.join(sql_lines)

def main():
    print("开始生成虚拟聊天记录SQL...")

    sql_content = []

    sql_content.append("-- 李欣琪（回避型依恋）完整session")
    sql_content.append(generate_li_xinqi_sql())

    sql_content.append("\n-- 陈佳悦（安全型依恋）完整session")
    sql_content.append(generate_chen_jiayue_sql())

    sql_content.append("\n-- 冯静雯（焦虑型依恋）完整session")
    sql_content.append(generate_feng_jingwen_sql())

    sql_content.append("\n-- 张安萌（安全型依恋）补充现有session")
    sql_content.append(generate_zhang_anmeng_sql())

    sql_content.append("\n-- 陈以心（安全型依恋）补充现有session")
    sql_content.append(generate_chen_yixin_sql())

    # 输出到文件
    with open('/Users/sunmuchao/Downloads/Her/scripts/virtual_chat_history.sql', 'w', encoding='utf-8') as f:
        f.write('\n'.join(sql_content))

    print("✅ SQL文件生成完成：scripts/virtual_chat_history.sql")

if __name__ == '__main__':
    main()