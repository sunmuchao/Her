"""
生成真实的聊天记录数据 - 增强版
为无锡女性用户创建真实的相亲交友对话记录
"""

import pymysql
import random
import uuid
import json
import re
from datetime import datetime, timedelta
from typing import List, Dict, Any

# 数据库连接配置
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3307,
    'user': 'root',
    'password': '',
    'charset': 'utf8mb4'
}

# 聊天模板 - 按阶段分类，更加真实和口语化
CHAT_TEMPLATES = {
    '初次问候': {
        '女': [
            "你好呀，看到你的资料觉得挺不错的",
            "你好，很高兴认识你",
            "哈喽，周末愉快呀",
            "你好呀，我是{name}",
            "你好，看到你也住在无锡，想认识一下",
            "嗨，最近怎么样？",
            "你好呀，看你照片挺阳光的",
        ],
        '男': [
            "你好！很高兴认识你，我是{name}",
            "你好呀，无锡这边最近天气还不错",
            "哈喽，你也在无锡吗？",
            "你好，看到你的资料觉得很有缘分",
            "你好呀，我是{name}，在{job}工作",
            "你好，很高兴能有机会和你聊天",
            "嗨，周末有什么计划吗？",
        ]
    },
    '工作生活': {
        '女': [
            "我在{job}工作，平时挺忙的",
            "我上班时间比较规律，周末有空",
            "我是一名{job}，每天朝九晚五",
            "工作虽然累，但我觉得充实的生活更有意义",
            "我在一家{industry}公司上班",
            "平时工作压力还行，周末会放松一下",
            "我平时喜欢看书、逛街",
        ],
        '男': [
            "我在{job}，平时加班不多",
            "我在{industry}行业工作",
            "我是一名{job}，工作时间比较灵活",
            "我在无锡待了好几年了，已经习惯了这里的生活",
            "我工作还算稳定，收入也不错",
            "平时工作忙，周末有空做自己喜欢的事",
            "我在一家互联网公司做技术",
        ]
    },
    '兴趣爱好': {
        '女': [
            "我特别喜欢{hobby}，周末经常去",
            "我平时喜欢看综艺和追剧",
            "我最近在学习{skill}，感觉挺有意思的",
            "我喜欢旅游，去过好几个城市",
            "我是个吃货，无锡这边好吃的我都去过",
            "我喜欢瑜伽和健身",
            "周末我会去{location}散步",
            "我喜欢看电影，最近看了好几部",
        ],
        '男': [
            "我平时喜欢{hobby}，是个运动爱好者",
            "我最近在研究{skill}",
            "我喜欢看电影，周末经常去电影院",
            "我是个运动达人，每周都会健身",
            "我喜欢自驾游，开车去过不少地方",
            "我平时喜欢打球和跑步",
            "周末我会去{location}走走",
            "我喜欢摄影，经常出去拍照",
        ]
    },
    '日常关心': {
        '女': [
            "今天工作辛苦吗？",
            "最近天气变了，要注意保暖哦",
            "周末怎么安排的呀？",
            "你最近在忙什么呢？",
            "晚上早点休息，别熬夜了",
            "最近心情怎么样？",
            "工作别太累了，注意身体",
            "天气不错，有空出去走走",
        ],
        '男': [
            "你今天怎么样，工作顺利吗？",
            "最近注意身体，别太累了",
            "周末有什么计划吗？",
            "最近看到一个好玩的，分享给你",
            "天气不错，想去{location}走走",
            "晚上早点休息",
            "工作别太辛苦了",
            "最近有什么新鲜事吗？",
        ]
    },
    '深入交流': {
        '女': [
            "我觉得两个人在一起最重要的是互相理解",
            "你对未来有什么规划呢？",
            "我觉得价值观这件事很重要",
            "你是怎么看待婚姻的？",
            "我觉得相处久了才能看出一个人的真实性格",
            "我希望找一个能一起旅行的人",
            "你觉得两个人怎么相处比较好？",
            "我比较看重家庭",
        ],
        '男': [
            "我觉得两个人需要彼此信任才能长久",
            "我希望未来能有自己的小家",
            "我对婚姻的看法是认真对待",
            "我觉得相处需要真诚",
            "我希望找一个能一起运动的人",
            "我觉得共同成长很重要",
            "你理想的生活是什么样的？",
            "我比较看重事业和家庭平衡",
        ]
    },
    '约会邀约': {
        '女': [
            "周末有空吗？我们可以见个面",
            "听说无锡最近有个不错的活动，有空一起去吗？",
            "你周末一般做什么呢？要不要一起吃个饭？",
            "我们对彼此都挺了解了，要不要见个面？",
            "周末想去{location}走走，你有兴趣吗？",
            "听说有家新开的{food}不错，一起去试试？",
            "我们聊了这么久，感觉挺投缘的",
        ],
        '男': [
            "周末有空吗？我想请你去吃饭",
            "听说{location}不错，周末一起去走走？",
            "我们聊得挺开心的，要不要见面聊聊？",
            "我周末想去{location}，你有兴趣一起去吗？",
            "无锡这边有个美食节，我们可以一起去看看",
            "好久没出去玩了，周末有空吗？",
            "想请你吃个饭，有空吗？",
        ]
    },
    '感情表达': {
        '女': [
            "和你聊天感觉很舒服",
            "我觉得我们挺投缘的",
            "你给我的感觉很真诚",
            "我很期待和你见面",
            "我觉得你是一个很稳重的人",
            "聊了这么久，感觉你挺不错的",
            "我觉得我们有很多共同点",
        ],
        '男': [
            "和你聊天让我觉得很开心",
            "我觉得我们很有共同点",
            "你给我的印象很好",
            "我很希望能和你进一步了解",
            "我觉得你是一个温柔的女生",
            "聊了这么久，感觉我们挺合的",
            "我很期待周末见面",
        ]
    },
    '期待': {
        '女': [
            "我很期待周末见面",
            "好的，那我们周六见",
            "我会准备好去的",
            "周末见，我很期待",
            "好的，到时候见",
            "期待和你见面",
        ],
        '男': [
            "好的，周六我会准时去",
            "期待和你见面",
            "我会提前准备好",
            "周末见，我很期待",
            "好的，到时候见",
            "我会安排好的",
        ]
    },
    '拒绝/结束': {
        '女': [
            "抱歉，我觉得我们可能不太合适",
            "我最近比较忙，可能没有太多时间聊天",
            "谢谢你，但我觉得我们性格不太合",
            "我需要再考虑一下",
            "我们还是先做朋友吧",
            "谢谢你的时间，但我觉得我们不太合适",
        ],
        '男': [
            "理解，如果不合适也没关系",
            "好的，那我们先各自了解一段时间",
            "明白，祝你早日找到合适的人",
            "没关系，我们还可以做朋友",
            "理解你的想法，谢谢你的坦诚",
            "好的，祝你一切顺利",
        ]
    },
    '友好': {
        '女': [
            "好的，谢谢你理解",
            "嗯，我们还是保持联系吧",
            "好的，有事可以找我",
            "没关系，我们还可以做朋友",
            "好的，祝你一切顺利",
        ],
        '男': [
            "好的，希望我们能保持联系",
            "没问题，有需要可以找我",
            "好的，祝你一切顺利",
            "好的，我们还是朋友",
            "没问题，保持联系",
        ]
    }
}

# 常用词库
WORD_BANK = {
    'hobby': ['瑜伽', '跑步', '健身', '游泳', '看书', '追剧', '旅行', '摄影', '烘焙', '画画', '弹钢琴', '看电影'],
    'location': ['蠡湖公园', '鼋头渚', '南禅寺', '灵山大佛', '太湖', '惠山古镇', '梅园', '万达广场', '恒隆广场', '清名桥'],
    'food': ['火锅', '日料', '西餐', '中餐', '烧烤', '海鲜', '甜点', '咖啡'],
    'industry': ['IT', '金融', '教育', '医疗', '互联网', '制造业', '房地产', '新能源'],
    'skill': ['插花', '烘焙', '摄影', '游泳', '健身', '外语', '画画'],
    'job': ['会计', '审计', '教师', '医生', '护士', '程序员', '设计师', '销售', '运营', 'HR', '律师', '工程师'],
}

# 用户人设类型（用于生成不同风格的对话）
USER_PERSONAS = {
    '活泼开朗': {
        '女': ['你好呀～', '哈哈，真的吗？', '太有意思了！', '周末一起去玩吧！', '我觉得你挺有趣的'],
        '男': ['哈哈，是啊', '你也很有趣', '周末一起去玩', '你性格真好', '我很喜欢你的开朗'],
    },
    '温柔体贴': {
        '女': ['你好，很高兴认识你', '你辛苦了', '要注意身体哦', '我理解你的想法', '谢谢你'],
        '男': ['你真温柔', '谢谢你关心', '你让我感觉很温暖', '你是个好女孩', '我很喜欢你的性格'],
    },
    '理性务实': {
        '女': ['你好，我想了解一下你的情况', '你对未来有什么规划？', '我觉得价值观很重要', '我们可以先了解一段时间'],
        '男': ['我事业稳定', '我有明确的规划', '我觉得你很理性', '我们可以慢慢了解', '我很看重家庭'],
    },
    '文艺浪漫': {
        '女': ['你好呀，看到你的资料很有感觉', '我喜欢看书和看电影', '周末想去{location}走走', '我觉得生活需要有诗意'],
        '男': ['你很有气质', '我也喜欢文艺', '我们可以一起去{location}', '你的想法很美好', '我很欣赏你'],
    }
}


def fill_template(template: str, user_info: Dict[str, Any]) -> str:
    """填充模板中的占位符"""
    result = template

    # 替换所有 {key} 格式的占位符
    for key, values in WORD_BANK.items():
        pattern = '{' + key + '}'
        if pattern in result:
            result = result.replace(pattern, random.choice(values))

    # 替换用户特定信息
    if '{name}' in result:
        result = result.replace('{name}', user_info.get('name', ''))
    if '{job}' in result and user_info.get('job'):
        # 如果用户有 job，用用户的 job 替换
        result = result.replace('{job}', user_info.get('job', random.choice(WORD_BANK['job'])))

    return result


def get_user_persona(age: int) -> str:
    """根据年龄判断用户人设类型"""
    if age < 26:
        return random.choice(['活泼开朗', '文艺浪漫'])
    elif age < 30:
        return random.choice(['活泼开朗', '温柔体贴', '理性务实'])
    else:
        return random.choice(['温柔体贴', '理性务实', '文艺浪漫'])


def generate_conversation(
    female_user: Dict[str, Any],
    male_user: Dict[str, Any],
    conv_length: int = 20
) -> List[Dict[str, Any]]:
    """生成一段对话记录"""

    messages = []

    # 获取用户人设
    female_persona = get_user_persona(female_user.get('age', 28))
    male_persona = get_user_persona(male_user.get('age', 30))

    # 选择对话类型（正常/拒绝/友好结束）
    conv_type = random.choices(
        ['正常', '拒绝', '友好'],
        weights=[70, 15, 15]
    )[0]

    # 根据对话类型确定阶段序列
    if conv_type == '正常':
        # 正常对话的阶段分布
        stage_weights = {
            '初次问候': 2,
            '工作生活': 3,
            '兴趣爱好': 4,
            '日常关心': 3,
            '深入交流': 3,
            '约会邀约': 2,
            '感情表达': 2,
            '期待': 1
        }
    elif conv_type == '拒绝':
        stage_weights = {
            '初次问候': 2,
            '工作生活': 2,
            '兴趣爱好': 2,
            '深入交流': 2,
            '拒绝/结束': 1
        }
    else:  # 友好
        stage_weights = {
            '初次问候': 2,
            '工作生活': 2,
            '兴趣爱好': 2,
            '日常关心': 1,
            '友好': 1
        }

    # 根据权重分配消息到各个阶段
    stages = []
    for stage, weight in stage_weights.items():
        count = int(conv_length * weight / sum(stage_weights.values()))
        for _ in range(count):
            stages.append(stage)

    # 如果消息数不足，补充最后一个阶段
    while len(stages) < conv_length:
        stages.append(stages[-1])

    # 随机打乱部分阶段的顺序（使对话更自然）
    # 但保持初次问候在最前面
    if conv_type == '正常':
        # 中间阶段可以适度随机
        middle_stages = stages[2:min(8, len(stages)-2)]
        random.shuffle(middle_stages)
        stages[2:min(8, len(stages)-2)] = middle_stages

    # 生成消息
    current_time = datetime.now() - timedelta(days=random.randint(1, 60), hours=random.randint(0, 12))

    used_templates = set()  # 记录已使用的模板，避免重复

    for i, stage in enumerate(stages):
        # 确定发言者（轮流发言，偶尔连续发言）
        if i == 0:
            gender = '女'  # 女生先发起
        elif random.random() < 0.12:  # 12% 概率连续发言
            gender = messages[-1]['gender']
        else:
            gender = '男' if messages[-1]['gender'] == '女' else '女'

        # 选择模板
        templates = CHAT_TEMPLATES.get(stage, {}).get(gender, [])
        if not templates:
            templates = CHAT_TEMPLATES['日常关心'].get(gender, [])

        # 尝试选择未使用的模板
        available_templates = [t for t in templates if (stage, gender, t) not in used_templates]
        if not available_templates:
            available_templates = templates

        template = random.choice(available_templates)
        used_templates.add((stage, gender, template))

        # 填充模板
        user_info = female_user if gender == '女' else male_user
        content = fill_template(template, user_info)

        # 添加人设特色（30%概率）
        if random.random() < 0.3:
            persona_templates = USER_PERSONAS.get(female_persona if gender == '女' else male_persona, {}).get(gender, [])
            if persona_templates:
                persona_content = fill_template(random.choice(persona_templates), user_info)
                # 可能附加人设特色内容
                if random.random() < 0.5:
                    content = content + ' ' + persona_content

        # 时间间隔（1-60 分钟）
        time_gap = random.randint(1, 60)
        current_time = current_time + timedelta(minutes=time_gap)

        messages.append({
            'gender': gender,
            'author_id': female_user['id'] if gender == '女' else male_user['id'],
            'content': content,
            'created_at': current_time,
            'stage': stage
        })

    return messages


def get_users_from_db() -> tuple:
    """从数据库获取用户列表"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # 获取无锡女性用户
    cursor.execute('USE her')
    cursor.execute('''
        SELECT id, name, age, job, education, profile_status
        FROM profiles
        WHERE city = '无锡' AND gender = '女' AND profile_status IN ('active', 'matched')
        ORDER BY RAND()
    ''')
    female_users = [
        {
            'id': str(row[0]),  # 转为字符串
            'name': row[1],
            'age': row[2],
            'job': row[3] or random.choice(WORD_BANK['job']),
            'education': row[4],
            'status': row[5]
        }
        for row in cursor.fetchall()
    ]

    # 获取无锡男性用户
    cursor.execute('''
        SELECT id, name, age, job, education, profile_status
        FROM profiles
        WHERE city = '无锡' AND gender = '男' AND profile_status IN ('active', 'matched')
        ORDER BY RAND()
    ''')
    male_users = [
        {
            'id': str(row[0]),  # 转为字符串
            'name': row[1],
            'age': row[2],
            'job': row[3] or random.choice(WORD_BANK['job']),
            'education': row[4],
            'status': row[5]
        }
        for row in cursor.fetchall()
    ]

    cursor.close()
    conn.close()

    return female_users, male_users


def clear_existing_chats():
    """清除现有聊天记录"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute('USE her_chat')

    # 先删除依赖表的数据
    try:
        cursor.execute('DELETE FROM chat_thread_summaries')
    except:
        pass  # 表可能不存在

    try:
        cursor.execute('DELETE FROM chat_conversations')
    except:
        pass  # 表可能不存在

    cursor.execute('DELETE FROM chat_messages')
    cursor.execute('DELETE FROM chat_threads')

    conn.commit()
    cursor.close()
    conn.close()
    print("已清除现有聊天记录")


def create_chat_thread(
    cursor,
    female_id: str,
    male_id: str
) -> str:
    """创建聊天线程"""
    thread_id = f"thread-{uuid.uuid4().hex[:16]}"
    case_id = f"case-{uuid.uuid4().hex[:16]}"
    relation_key = f"relation-{female_id}-{male_id}"

    # 创建线程（随机状态）
    status = random.choices(['active', 'matched', 'paused'], weights=[60, 30, 10])[0]

    cursor.execute('''
        INSERT INTO chat_threads
        (thread_id, case_id, relation_key, status, participant_a_id, participant_b_id, metadata_json, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        thread_id,
        case_id,
        relation_key,
        status,
        female_id,
        male_id,
        json.dumps({'source': 'match', 'created_by': 'system', 'compatibility_score': random.randint(60, 95)}),
        datetime.now() - timedelta(days=random.randint(30, 90)),
        datetime.now() - timedelta(days=random.randint(1, 30))
    ))

    return thread_id


def insert_messages(
    cursor,
    thread_id: str,
    messages: List[Dict[str, Any]],
    female_id: str,
    male_id: str
) -> int:
    """插入聊天消息"""
    count = 0
    for msg in messages:
        client_msg_id = f"client-{uuid.uuid4().hex[:16]}"
        recipient_id = male_id if msg['gender'] == '女' else female_id

        cursor.execute('''
            INSERT INTO chat_messages
            (thread_id, author_id, message_recipient_id, visibility, source, body, client_msg_id, reply_to_message_id, metadata_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            thread_id,
            msg['author_id'],
            recipient_id,
            'normal',
            'user',
            msg['content'],
            client_msg_id,
            None,  # reply_to
            json.dumps({'stage': msg['stage']}),
            msg['created_at']
        ))
        count += 1

    return count


def generate_chat_records(
    target_count: int = 10000,
    max_threads_per_female: int = 3,
    clear_existing: bool = True
) -> Dict[str, int]:
    """
    生成聊天记录

    Args:
        target_count: 目标消息数量
        max_threads_per_female: 每个女生最多创建几个聊天线程
        clear_existing: 是否清除现有聊天记录

    Returns:
        统计信息
    """
    if clear_existing:
        clear_existing_chats()

    print("正在获取用户数据...")
    female_users, male_users = get_users_from_db()

    print(f"找到 {len(female_users)} 个无锡女性用户")
    print(f"找到 {len(male_users)} 个无锡男性用户")

    # 连接数据库
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute('USE her_chat')

    total_threads = 0
    total_messages = 0
    processed_females = 0

    print("\n开始生成聊天记录...")

    for female in female_users:
        # 随机选择 1-3 个男性用户与该女性聊天
        num_threads = random.randint(1, max_threads_per_female)

        # 随机选择男性用户（避免重复）
        available_males = [m for m in male_users if m['id'] != female['id']]
        selected_males = random.sample(available_males, min(num_threads, len(available_males)))

        for male in selected_males:
            # 创建聊天线程
            thread_id = create_chat_thread(cursor, female['id'], male['id'])
            total_threads += 1

            # 生成对话内容（20-40 条消息）
            conv_length = random.randint(20, 40)
            messages = generate_conversation(female, male, conv_length)

            # 插入消息
            msg_count = insert_messages(cursor, thread_id, messages, female['id'], male['id'])
            total_messages += msg_count

            if total_messages >= target_count:
                break

        processed_females += 1

        # 每50个用户提交一次
        if processed_females % 50 == 0:
            conn.commit()
            print(f"已处理 {processed_females} 个女性用户，创建了 {total_threads} 个线程，{total_messages} 条消息")

        if total_messages >= target_count:
            break

    # 最后提交
    conn.commit()

    cursor.close()
    conn.close()

    return {
        'processed_females': processed_females,
        'total_threads': total_threads,
        'total_messages': total_messages
    }


def main():
    """主函数"""
    print("=" * 60)
    print("开始生成聊天记录数据（增强版）")
    print("=" * 60)

    # 生成 30000 条聊天记录（不清除现有数据，追加）
    stats = generate_chat_records(target_count=30000, clear_existing=False)

    print("\n" + "=" * 60)
    print("生成完成！")
    print("=" * 60)
    print(f"处理女性用户数: {stats['processed_females']}")
    print(f"创建聊天线程数: {stats['total_threads']}")
    print(f"创建聊天消息数: {stats['total_messages']}")
    print("=" * 60)


if __name__ == '__main__':
    main()