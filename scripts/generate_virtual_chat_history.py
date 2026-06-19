#!/usr/bin/env python3
"""
生成5位候选人的完整Discovery Session聊天记录
包括：李欣琪、陈佳悦、冯静雯、张安萌、陈以心
"""

import json
from datetime import datetime, timedelta
import mysql.connector

# 数据库连接配置
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3307,
    'user': 'root',
    'database': 'her_discovery',
    'charset': 'utf8mb4'
}

# 候选人信息
CANDIDATES = {
    573: {
        'name': '李欣琪',
        'age': 30,
        'city': '无锡',
        'job': '公务员',
        'education': '硕士',
        'personality': '乐观, 安静, 边界感强',
        'attachment': '回避型',
        'mbti': 'ISTJ'
    },
    6609: {
        'name': '陈佳悦',
        'age': 32,
        'city': '无锡',
        'job': '药师',
        'education': '本科',
        'personality': '情绪稳定, 有责任感, 温和',
        'attachment': '安全型',
        'mbti': 'ISTJ'
    },
    3611: {
        'name': '冯静雯',
        'age': 32,
        'city': '无锡',
        'job': '软件测试',
        'education': '硕士',
        'personality': '细腻, 慢热, 有责任感',
        'attachment': '焦虑型',
        'mbti': 'ISFJ'
    },
    2701: {
        'name': '张安萌',
        'age': 27,
        'city': '无锡',
        'job': '采购',
        'education': '本科',
        'personality': '情绪稳定, 温和, 善沟通',
        'attachment': '安全型',
        'mbti': 'ESFJ'
    },
    6209: {
        'name': '陈以心',
        'age': 30,
        'city': '无锡',
        'job': '产品运营',
        'education': '硕士',
        'personality': '情绪稳定, 开朗, 有责任感',
        'attachment': '安全型',
        'mbti': 'ESTJ'
    }
}

# 男性候选人池（无锡地区）
MALE_POOL = [
    {'id': 1318, 'name': '胡嘉衡', 'age': 29, 'job': '会计'},
    {'id': 7724, 'name': '赵浩衡', 'age': 29, 'job': '药师'},
    {'id': 2288, 'name': '孙承骁', 'age': 28, 'job': '采购'},
    {'id': 8931, 'name': '张辰瑞', 'age': 30, 'job': '产品经理'},
    {'id': 7132, 'name': '吴承衡', 'age': 33, 'job': '审计'},
    {'id': 8481, 'name': '高奕轩', 'age': 29, 'job': '药师'},
    {'id': 6726, 'name': '赵思凯', 'age': 32, 'job': '教师'},
    {'id': 5701, 'name': '胡宇阳', 'age': 30, 'job': '教师'},
    {'id': 9452, 'name': '黄亦凯', 'age': 29, 'job': 'UI设计'},
]

def generate_session_id():
    """生成session_id"""
    import uuid
    return f"discovery-session-{uuid.uuid4().hex[:12]}"

def create_session(conn, session_id, profile_id, created_at):
    """创建discovery session"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO discovery_agent_sessions
        (session_id, requester_id, profile_id, status, phase, state_json, latest_view_json, created_at, updated_at)
        VALUES (%s, %s, %s, 'active', 'results_shown', '{}', '{}', %s, %s)
    """, (session_id, profile_id, profile_id, created_at, created_at))
    conn.commit()

def create_turn(conn, session_id, request_kind, user_message, agent_decision, view_snapshot, created_at, search_run_id=None):
    """创建对话轮次"""
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO discovery_agent_turns
        (session_id, request_kind, user_message_text, agent_decision_json, view_snapshot_json, search_run_id, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (session_id, request_kind, user_message, json.dumps(agent_decision), json.dumps(view_snapshot), search_run_id, created_at))
    turn_id = cursor.lastrowid
    conn.commit()
    return turn_id

def generate_li_xinqi_session():
    """
    李欣琪 - 回避型依恋
    特点：边界感强，乐观安静，倾向独立空间
    """
    session_id = generate_session_id()
    profile_id = 573
    created_at = datetime(2026, 6, 10, 14, 30, 0)

    conn = mysql.connector.connect(**DB_CONFIG)

    # 创建session
    create_session(conn, session_id, profile_id, created_at)

    turns = []

    # Turn 1: session_opened
    turns.append({
        'request_kind': 'session_opened',
        'user_message': None,
        'agent_decision': {
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
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'criteria_chips': [
                {'chip_id': 'chip-1', 'label': '无锡'},
                {'chip_id': 'chip-2', 'label': '男'},
                {'chip_id': 'chip-3', 'label': '27-32岁'},
                {'chip_id': 'chip-4', 'label': '认真恋爱'}
            ],
            'suggested_actions': [],
            'timeline': [
                {
                    'item_type': 'assistant_message',
                    'body': '我根据你刚填的资料筛了几位，你先看看有没有眼缘。觉得不合适，随时跟我说。',
                    'created_at': created_at.isoformat()
                },
                {
                    'item_type': 'result_group',
                    'title': '根据你的资料，先给你看这些',
                    'cards': [
                        {'profile_id': 8931, 'title': '张辰瑞 30', 'subtitle': '无锡 · 产品经理', 'match_score': 115},
                        {'profile_id': 7724, 'title': '赵浩衡 29', 'subtitle': '无锡 · 药师', 'match_score': 110},
                        {'profile_id': 6726, 'title': '赵思凯 32', 'subtitle': '无锡 · 教师', 'match_score': 108}
                    ]
                }
            ]
        },
        'created_at': created_at
    })

    # Turn 2: 用户表达边界感偏好
    created_at += timedelta(minutes=5)
    turns.append({
        'request_kind': 'user_message',
        'user_message': '我比较看重边界感，不喜欢对方太黏人，希望能有自己的空间',
        'agent_decision': {
            'assistant_message': '收到。我注意到你提到边界感，这点很重要。你希望对方能理解你需要独立空间，不强制分享所有事情，对吗？我帮你把这点加到筛选条件里。',
            'criteria_labels': ['无锡', '男', '27-32岁', '认真恋爱', '尊重彼此空间'],
            'phase': 'collecting_preferences',
            'selected_candidates': [],
            'suggested_actions': [
                {'label': '继续补充年龄范围', 'style': 'secondary'},
                {'label': '继续补充性格偏好', 'style': 'secondary'}
            ]
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'criteria_chips': [
                {'chip_id': 'chip-1', 'label': '无锡'},
                {'chip_id': 'chip-2', 'label': '男'},
                {'chip_id': 'chip-3', 'label': '27-32岁'},
                {'chip_id': 'chip-4', 'label': '认真恋爱'},
                {'chip_id': 'chip-5', 'label': '尊重彼此空间'}
            ],
            'timeline': [
                {'item_type': 'assistant_message', 'body': '...'},
                {'item_type': 'user_message', 'body': '我比较看重边界感，不喜欢对方太黏人，希望能有自己的空间'},
                {'item_type': 'assistant_message', 'body': '收到。我注意到你提到边界感...'}
            ]
        },
        'created_at': created_at
    })

    # Turn 3: 用户继续表达
    created_at += timedelta(minutes=3)
    turns.append({
        'request_kind': 'user_message',
        'user_message': '对，而且我希望对方有自己的爱好和朋友圈，不要每天都要在一起',
        'agent_decision': {
            'assistant_message': '明白了，欣琪。你希望的是一种成熟独立的关系模式，两个人都有自己的生活和空间，但关键时刻能彼此支持。我重新调整了一下筛选，这次给你推荐几位更符合你期待的：',
            'criteria_labels': ['无锡', '男', '27-32岁', '认真恋爱', '尊重彼此空间', '独立自主'],
            'phase': 'results_shown',
            'selected_candidates': [
                {'profile_id': 6726, 'reason_summary': '32岁教师，边界清楚有主见，喜欢独立思考'},
                {'profile_id': 8931, 'reason_summary': '30岁产品经理，理性独立，社交圈简单'},
                {'profile_id': 7132, 'reason_summary': '33岁审计，工作独立，有自己的爱好'}
            ],
            'suggested_actions': [
                {'label': '看看更多', 'style': 'primary'},
                {'label': '调整条件', 'style': 'ghost'}
            ]
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'timeline': [
                {'item_type': 'assistant_message', 'body': '明白了，欣琪...'},
                {'item_type': 'result_group', 'title': '根据你的要求，重新筛选', 'cards': [
                    {'profile_id': 6726, 'title': '赵思凯 32', 'match_score': 125},
                    {'profile_id': 8931, 'title': '张辰瑞 30', 'match_score': 120},
                    {'profile_id': 7132, 'title': '吴承衡 33', 'match_score': 115}
                ]}
            ]
        },
        'created_at': created_at
    })

    # Turn 4: 用户选择候选人
    created_at += timedelta(minutes=8)
    turns.append({
        'request_kind': 'user_message',
        'user_message': '赵思凯看起来不错，他的边界感和独立性都比较符合',
        'agent_decision': {
            'assistant_message': '好的，欣琪！赵思凯32岁教师，确实很符合你的要求。他的性格是边界清楚、有主见、尊重彼此空间，而且他也提到希望两个人都有独立的生活。我帮你打开他的资料页，你可以详细看看他的介绍和照片。',
            'criteria_labels': ['无锡', '男', '27-32岁', '认真恋爱', '尊重彼此空间', '独立自主'],
            'phase': 'results_shown',
            'selected_candidates': [{'profile_id': 6726, 'reason_summary': '32岁教师，边界清楚有主见'}],
            'suggested_actions': [
                {'label': '查看赵思凯资料', 'style': 'primary'},
                {'label': '继续看其他人', 'style': 'secondary'}
            ]
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'timeline': [
                {'item_type': 'assistant_message', 'body': '好的，欣琪！赵思凯...'}
            ]
        },
        'created_at': created_at
    })

    # Turn 5: 用户拒绝候选人
    created_at += timedelta(minutes=12)
    turns.append({
        'request_kind': 'user_message',
        'user_message': '张辰瑞有点太理性了，感觉相处起来会比较冷淡',
        'agent_decision': {
            'assistant_message': '收到，欣琪。你提到张辰瑞太理性可能显得冷淡，这点我理解。虽然理性是优点，但如果缺乏温度，确实可能影响相处感受。我帮你排除掉他，重新看看其他人：',
            'criteria_labels': ['无锡', '男', '27-32岁', '认真恋爱', '尊重彼此空间', '独立自主', '有温度'],
            'phase': 'results_shown',
            'selected_candidates': [
                {'profile_id': 6726, 'reason_summary': '32岁教师，边界清楚有温度'},
                {'profile_id': 7132, 'reason_summary': '33岁审计，独立理性但温和'},
                {'profile_id': 7724, 'reason_summary': '29岁药师，温和有责任感'}
            ],
            'suggested_actions': [
                {'label': '看看更多', 'style': 'primary'},
                {'label': '调整条件', 'style': 'ghost'}
            ]
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'timeline': [
                {'item_type': 'assistant_message', 'body': '收到，欣琪...'}
            ]
        },
        'created_at': created_at
    })

    # 写入数据库
    for turn in turns:
        create_turn(conn, session_id, turn['request_kind'], turn['user_message'],
                   turn['agent_decision'], turn['view_snapshot'], turn['created_at'])

    conn.close()
    print(f"✅ 李欣琪 session创建完成: {session_id}")

def generate_chen_jiayue_session():
    """
    陈佳悦 - 安全型依恋
    特点：情绪稳定，有责任感，温和
    """
    session_id = generate_session_id()
    profile_id = 6609
    created_at = datetime(2026, 6, 11, 15, 20, 0)

    conn = mysql.connector.connect(**DB_CONFIG)
    create_session(conn, session_id, profile_id, created_at)

    turns = []

    # Turn 1: session_opened
    turns.append({
        'request_kind': 'session_opened',
        'user_message': None,
        'agent_decision': {
            'assistant_message': '我根据你刚填的资料筛了几位，你先看看有没有眼缘。觉得不合适，随时跟我说。',
            'criteria_labels': ['无锡', '男', '28-35岁', '认真恋爱'],
            'phase': 'results_shown',
            'result_group_title': '根据你的资料，先给你看这些',
            'selected_candidates': [
                {'profile_id': 7724, 'reason_summary': '29岁药师，情绪稳定有责任感'},
                {'profile_id': 8931, 'reason_summary': '30岁产品经理，理性开朗'},
                {'profile_id': 6726, 'reason_summary': '32岁教师，温和稳重'}
            ],
            'suggested_actions': []
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'criteria_chips': [
                {'chip_id': 'chip-1', 'label': '无锡'},
                {'chip_id': 'chip-2', 'label': '男'},
                {'chip_id': 'chip-3', 'label': '28-35岁'},
                {'chip_id': 'chip-4', 'label': '认真恋爱'}
            ],
            'timeline': [
                {
                    'item_type': 'assistant_message',
                    'body': '我根据你刚填的资料筛了几位...',
                    'created_at': created_at.isoformat()
                },
                {
                    'item_type': 'result_group',
                    'title': '根据你的资料，先给你看这些',
                    'cards': [
                        {'profile_id': 7724, 'title': '赵浩衡 29'},
                        {'profile_id': 8931, 'title': '张辰瑞 30'},
                        {'profile_id': 6726, 'title': '赵思凯 32'}
                    ]
                }
            ]
        },
        'created_at': created_at
    })

    # Turn 2: 用户表达期望
    created_at += timedelta(minutes=6)
    turns.append({
        'request_kind': 'user_message',
        'user_message': '我希望能找个性格温和、有责任感的人，最好是工作稳定的',
        'agent_decision': {
            'assistant_message': '收到，佳悦。你提到希望对方性格温和、有责任感且工作稳定，这些都是建立长期关系的基础。我帮你调整筛选，重点看这几位：',
            'criteria_labels': ['无锡', '男', '28-35岁', '认真恋爱', '温和', '有责任感', '工作稳定'],
            'phase': 'results_shown',
            'selected_candidates': [
                {'profile_id': 7724, 'reason_summary': '29岁药师，温和有责任感，工作稳定'},
                {'profile_id': 6726, 'reason_summary': '32岁教师，温和稳重，体制内'},
                {'profile_id': 5701, 'reason_summary': '30岁教师，情绪稳定顾家'}
            ],
            'suggested_actions': [
                {'label': '看看更多', 'style': 'primary'},
                {'label': '调整条件', 'style': 'ghost'}
            ]
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'timeline': [
                {'item_type': 'assistant_message', 'body': '收到，佳悦...'}
            ]
        },
        'created_at': created_at
    })

    # Turn 3: 用户表达长期定居意向
    created_at += timedelta(minutes=4)
    turns.append({
        'request_kind': 'user_message',
        'user_message': '我长期在无锡定居，希望对方也有定居意向，不要经常变动',
        'agent_decision': {
            'assistant_message': '明白了，佳悦。你在无锡长期定居，希望对方也有明确的定居计划，这样两人才能一起规划未来。我把这点加入筛选条件，给你推荐几位在无锡有长期打算的：',
            'criteria_labels': ['无锡', '男', '28-35岁', '认真恋爱', '温和', '有责任感', '无锡定居'],
            'phase': 'results_shown',
            'selected_candidates': [
                {'profile_id': 7724, 'reason_summary': '29岁药师，无锡定居多年'},
                {'profile_id': 6726, 'reason_summary': '32岁教师，无锡本地人'},
                {'profile_id': 5701, 'reason_summary': '30岁教师，长期无锡定居'}
            ],
            'suggested_actions': [
                {'label': '看看更多', 'style': 'primary'},
                {'label': '调整条件', 'style': 'ghost'}
            ]
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'timeline': [
                {'item_type': 'assistant_message', 'body': '明白了，佳悦...'}
            ]
        },
        'created_at': created_at
    })

    # Turn 4: 用户选择候选人
    created_at += timedelta(minutes=10)
    turns.append({
        'request_kind': 'user_message',
        'user_message': '赵浩衡看起来不错，温和有责任感，而且也是药师工作稳定',
        'agent_decision': {
            'assistant_message': '好的，佳悦！赵浩衡29岁药师，确实很符合你的要求。他的性格温和有责任感，而且在无锡定居多年，工作稳定。最重要的是你们都是医药行业，可能有更多共同话题。我帮你打开他的资料页看看？',
            'criteria_labels': ['无锡', '男', '28-35岁', '认真恋爱', '温和', '有责任感', '无锡定居'],
            'phase': 'results_shown',
            'selected_candidates': [{'profile_id': 7724, 'reason_summary': '29岁药师，温和有责任感'}],
            'suggested_actions': [
                {'label': '查看赵浩衡资料', 'style': 'primary'},
                {'label': '继续看其他人', 'style': 'secondary'}
            ]
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'timeline': [
                {'item_type': 'assistant_message', 'body': '好的，佳悦！赵浩衡...'}
            ]
        },
        'created_at': created_at
    })

    # 写入数据库
    for turn in turns:
        create_turn(conn, session_id, turn['request_kind'], turn['user_message'],
                   turn['agent_decision'], turn['view_snapshot'], turn['created_at'])

    conn.close()
    print(f"✅ 陈佳悦 session创建完成: {session_id}")

def generate_feng_jingwen_session():
    """
    冯静雯 - 焦虑型依恋
    特点：细腻慢热，有责任感，需要安全感
    """
    session_id = generate_session_id()
    profile_id = 3611
    created_at = datetime(2026, 6, 12, 16, 45, 0)

    conn = mysql.connector.connect(**DB_CONFIG)
    create_session(conn, session_id, profile_id, created_at)

    turns = []

    # Turn 1: session_opened
    turns.append({
        'request_kind': 'session_opened',
        'user_message': None,
        'agent_decision': {
            'assistant_message': '我根据你刚填的资料筛了几位，你先看看有没有眼缘。觉得不合适，随时跟我说。',
            'criteria_labels': ['无锡', '男', '28-34岁', '认真恋爱'],
            'phase': 'results_shown',
            'result_group_title': '根据你的资料，先给你看这些',
            'selected_candidates': [
                {'profile_id': 7724, 'reason_summary': '29岁药师，温和有责任感'},
                {'profile_id': 6726, 'reason_summary': '32岁教师，情绪稳定'},
                {'profile_id': 8931, 'reason_summary': '30岁产品经理，理性可靠'}
            ],
            'suggested_actions': []
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'criteria_chips': [
                {'chip_id': 'chip-1', 'label': '无锡'},
                {'chip_id': 'chip-2', 'label': '男'},
                {'chip_id': 'chip-3', 'label': '28-34岁'},
                {'chip_id': 'chip-4', 'label': '认真恋爱'}
            ],
            'timeline': [
                {
                    'item_type': 'assistant_message',
                    'body': '我根据你刚填的资料筛了几位...',
                    'created_at': created_at.isoformat()
                },
                {
                    'item_type': 'result_group',
                    'title': '根据你的资料，先给你看这些',
                    'cards': [
                        {'profile_id': 7724, 'title': '赵浩衡 29'},
                        {'profile_id': 6726, 'title': '赵思凯 32'},
                        {'profile_id': 8931, 'title': '张辰瑞 30'}
                    ]
                }
            ]
        },
        'created_at': created_at
    })

    # Turn 2: 用户表达焦虑感
    created_at += timedelta(minutes=8)
    turns.append({
        'request_kind': 'user_message',
        'user_message': '我比较慢热，需要对方主动一点，不然我会很焦虑，担心他是不是不喜欢我',
        'agent_decision': {
            'assistant_message': '收到，静雯。你提到自己慢热需要对方主动，这种感受很真实。焦虑感往往源于不确定，所以你希望对方能给你清晰的安全感确认，比如主动报备行程、及时回复消息，对吗？',
            'criteria_labels': ['无锡', '男', '28-34岁', '认真恋爱', '主动沟通', '给安全感'],
            'phase': 'collecting_preferences',
            'selected_candidates': [],
            'suggested_actions': [
                {'label': '继续补充性格偏好', 'style': 'secondary'},
                {'label': '继续补充沟通习惯', 'style': 'secondary'}
            ]
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'timeline': [
                {'item_type': 'assistant_message', 'body': '收到，静雯...'}
            ]
        },
        'created_at': created_at
    })

    # Turn 3: 用户继续表达
    created_at += timedelta(minutes=3)
    turns.append({
        'request_kind': 'user_message',
        'user_message': '对，我希望他能主动分享日常，不要让我总是猜测他的想法',
        'agent_decision': {
            'assistant_message': '明白了，静雯。你希望的是一种透明度高的关系，对方愿意主动分享日常和想法，让你不用猜测。这种沟通模式确实能减少很多焦虑感。我帮你找几位性格细腻、愿意主动沟通的男生：',
            'criteria_labels': ['无锡', '男', '28-34岁', '认真恋爱', '主动沟通', '细腻', '给安全感'],
            'phase': 'results_shown',
            'selected_candidates': [
                {'profile_id': 7724, 'reason_summary': '29岁药师，温和细腻，善于倾听'},
                {'profile_id': 5701, 'reason_summary': '30岁教师，情绪稳定，主动沟通'},
                {'profile_id': 1318, 'reason_summary': '29岁会计，细心善沟通'}
            ],
            'suggested_actions': [
                {'label': '看看更多', 'style': 'primary'},
                {'label': '调整条件', 'style': 'ghost'}
            ]
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'timeline': [
                {'item_type': 'assistant_message', 'body': '明白了，静雯...'}
            ]
        },
        'created_at': created_at
    })

    # Turn 4: 用户表达长期定居
    created_at += timedelta(minutes=5)
    turns.append({
        'request_kind': 'user_message',
        'user_message': '而且我有长期在无锡定居的打算，希望对方也有',
        'agent_decision': {
            'assistant_message': '收到，静雯。长期定居无锡也是个重要的安全感来源，说明对方有稳定的生活规划。我帮你筛选几位在无锡有定居打算的，这样你们可以一起规划未来：',
            'criteria_labels': ['无锡', '男', '28-34岁', '认真恋爱', '主动沟通', '无锡定居'],
            'phase': 'results_shown',
            'selected_candidates': [
                {'profile_id': 7724, 'reason_summary': '29岁药师，无锡定居，温和细腻'},
                {'profile_id': 5701, 'reason_summary': '30岁教师，无锡定居，主动沟通'},
                {'profile_id': 6726, 'reason_summary': '32岁教师，无锡本地人'}
            ],
            'suggested_actions': [
                {'label': '看看更多', 'style': 'primary'},
                {'label': '调整条件', 'style': 'ghost'}
            ]
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'timeline': [
                {'item_type': 'assistant_message', 'body': '收到，静雯...'}
            ]
        },
        'created_at': created_at
    })

    # Turn 5: 用户选择候选人
    created_at += timedelta(minutes=12)
    turns.append({
        'request_kind': 'user_message',
        'user_message': '赵浩衡看起来不错，温和细腻，而且他也是药师，工作稳定',
        'agent_decision': {
            'assistant_message': '好的，静雯！赵浩衡29岁药师，确实很符合你的要求。他的性格温和细腻，善于倾听和沟通，而且他提到愿意主动分享日常。更重要的是，他在无锡定居多年，工作稳定，这些都是给你安全感的基础。我帮你打开他的资料页看看？',
            'criteria_labels': ['无锡', '男', '28-34岁', '认真恋爱', '主动沟通', '无锡定居'],
            'phase': 'results_shown',
            'selected_candidates': [{'profile_id': 7724, 'reason_summary': '29岁药师，温和细腻'}],
            'suggested_actions': [
                {'label': '查看赵浩衡资料', 'style': 'primary'},
                {'label': '继续看其他人', 'style': 'secondary'}
            ]
        },
        'view_snapshot': {
            'composer': {'disabled': False, 'placeholder': '继续告诉红娘你的要求'},
            'timeline': [
                {'item_type': 'assistant_message', 'body': '好的，静雯！赵浩衡...'}
            ]
        },
        'created_at': created_at
    })

    # 写入数据库
    for turn in turns:
        create_turn(conn, session_id, turn['request_kind'], turn['user_message'],
                   turn['agent_decision'], turn['view_snapshot'], turn['created_at'])

    conn.close()
    print(f"✅ 冯静雯 session创建完成: {session_id}")

def main():
    print("开始生成虚拟聊天记录...")

    # 生成李欣琪的完整session
    generate_li_xinqi_session()

    # 生成陈佳悦的完整session
    generate_chen_jiayue_session()

    # 生成冯静雯的完整session
    generate_feng_jingwen_session()

    print("\n✅ 所有虚拟聊天记录生成完成！")

if __name__ == '__main__':
    main()