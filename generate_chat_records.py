"""
生成真实的聊天记录数据
为无锡女性用户创建真实的相亲交友对话记录
"""

import pymysql
import random
import uuid
import json
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

# 聊天模板 - 按阶段分类
CHAT_TEMPLATES = {
    '初次问候': {
        '女': [
            "你好呀，很高兴认识你 😊",
            "你好，看到你的资料觉得很有缘分",
            "哈喽，我是{name}，很高兴能和你聊天",
            "你好呀，你是做什么工作的呢？",
            "嗨，看到你也住在无锡，觉得可以聊聊",
        ],
        '男': [
            "你好！很高兴认识你，我是{name}",
            "你好呀，看到你的照片觉得很漂亮",
            "哈喽，无锡这边最近天气不错呢",
            "你好，我是{name},在{job}工作",
            "你好呀，很高兴能有机会和你聊天",
        ]
    },
    '工作生活': {
        '女': [
            "我在{job}工作，平时比较忙，但周末会放松一下",
            "我平时喜欢看书、逛街，偶尔也会去健身房",
            "工作虽然累，但我觉得充实的生活更有意义",
            "我在一家{industry}公司上班，每天朝九晚五",
            "我是一名{job}，工作时间比较规律",
        ],
        '男': [
            "我在{job}，平时加班不多，有时间做自己喜欢的事",
            "我平时喜欢运动，周末会去跑步或者打球",
            "我在{industry}行业工作，发展还不错",
            "我是一名{job},工作虽然忙但收入还可以",
            "我在无锡待了{years}年了，已经习惯了这里的生活",
        ]
    },
    '兴趣爱好': {
        '女': [
            "我特别喜欢{hobby},周末经常去{location}",
            "我平时喜欢看综艺和追剧，你呢？",
            "我最近在学习{skill},感觉挺有意思的",
            "我喜欢旅游，去过{places}几个城市",
            "我是个吃货，无锡这边好吃的我都去过",
        ],
        '男': [
            "我平时喜欢{hobby},是个{hobby_type}爱好者",
            "我最近在研究{skill},感觉挺有意思的",
            "我喜欢看电影，周末经常去电影院",
            "我是个运动达人，每周都会健身{times}次",
            "我喜欢自驾游，开车去过不少地方",
        ]
    },
    '约会邀约': {
        '女': [
            "周末有空吗？我们可以见个面聊聊天",
            "听说无锡最近有个不错的{event},有空一起去吗？",
            "你周末一般做什么呢？要不要一起吃个饭？",
            "我对{location}很感兴趣，有机会一起去吗？",
            "我们聊了这么久，感觉挺投缘的，要不要见个面？",
        ],
        '男': [
            "周末有空吗？我想请你去吃{food}",
            "听说{location}不错，周末一起去走走？",
            "我们聊得挺开心的，要不要见面聊聊？",
            "我周末想去{location},你有兴趣一起去吗？",
            "无锡这边有个{event},我们可以一起去看看",
        ]
    },
    '深入交流': {
        '女': [
            "我觉得两个人在一起最重要的是{value}",
            "你对未来有什么规划呢？",
            "我觉得{topic}这件事很重要",
            "你是怎么看待{topic}的？",
            "我觉得相处久了才能看出一个人的真实性格",
        ],
        '男': [
            "我觉得两个人需要{value}才能长久",
            "我希望未来能{plan},你觉得怎么样？",
            "我对{topic}的看法是{opinion}",
            "我觉得相处需要真诚，不能有欺骗",
            "我希望找一个能一起{activity}的人",
        ]
    },
    '日常关心': {
        '女': [
            "今天工作辛苦吗？",
            "最近天气变了，要注意保暖哦",
            "周末怎么安排的呀？",
            "你最近在忙什么呢？",
            "听说你那边{event},还好吗？",
        ],
        '男': [
            "你今天怎么样，工作顺利吗？",
            "最近注意身体，别太累了",
            "周末有什么计划吗？",
            "最近看到一个好玩的{thing},分享给你",
            "你最近心情怎么样？",
        ]
    },
    '感情表达': {
        '女': [
            "和你聊天感觉很舒服 😊",
            "我觉得我们挺投缘的",
            "你给我的感觉很真诚",
            "我很期待和你见面",
            "我觉得你是一个{trait}的人",
        ],
        '男': [
            "和你聊天让我觉得很开心",
            "我觉得我们很有共同点",
            "你给我的印象很好",
            "我很希望能和你进一步了解",
            "我觉得你是一个{trait}的女生",
        ]
    },
    '拒绝/结束': {
        '女': [
            "抱歉，我觉得我们可能不太合适",
            "我最近比较忙，可能没有太多时间聊天",
            "谢谢你，但我觉得我们性格不太合",
            "我需要再考虑一下",
            "我们还是先做朋友吧",
        ],
        '男': [
            "理解，如果不合适也没关系",
            "好的，那我们先各自了解一段时间",
            "明白，祝你早日找到合适的人",
            "没关系，我们还可以做朋友",
            "理解你的想法，谢谢你的坦诚",
        ]
    }
}

# 情感状态转换模板
RELATIONSHIP_TEMPLATES = {
    '友好': {
        '女': [
            "好的，谢谢你理解",
            "嗯，我们还是保持联系吧",
            "好的，有事可以找我",
        ],
        '男': [
            "好的，希望我们能保持联系",
            "没问题，有需要可以找我",
            "好的，祝你一切顺利",
        ]
    },
    '期待': {
        '女': [
            "我很期待周末见面 😊",
            "好的，那我们周六见！",
            "我会准备好去的，期待！",
        ],
        '男': [
            "好的，周六我会准时去",
            "期待和你见面！",
            "我会提前准备好，你放心",
        ]
    },
    '确认': {
        '女': [
            "好的，那就这样定了",
            "嗯，我会记住的",
            "好的，到时候见",
        ],
        '男': [
            "好的，我会安排好的",
            "没问题，我都记下了",
            "好的，期待那天",
        ]
    }
}

# 常用词库
WORD_BANK = {
    'hobbies': ['瑜伽', '跑步', '健身', '游泳', '瑜伽', '看书', '追剧', '旅行', '摄影', '烘焙', '画画', '弹钢琴'],
    'hobby_types': ['运动', '文艺', '户外', '美食'],
    'locations': ['蠡湖公园', '鼋头渚', '南禅寺', '灵山大佛', '太湖', '惠山古镇', '梅园', '万达广场', '恒隆广场'],
    'foods': ['火锅', '日料', '西餐', '中餐', '烧烤', '海鲜', '甜点'],
    'events': ['音乐节', '美食节', '艺术展', '电影节', '读书会'],
    'industries': ['IT', '金融', '教育', '医疗', '互联网', '制造业'],
    'skills': ['插花', '烘焙', '摄影', '游泳', '健身', '外语'],
    'values': ['互相理解', '真诚相待', '共同成长', '彼此信任', '价值观一致'],
    'topics': ['婚姻', '家庭', '事业', '孩子', '生活方式', '金钱观念'],
    'traits': ['真诚', '善良', '有责任心', '上进', '稳重', '温柔', '体贴'],
    'activities': ['旅行', '运动', '做饭', '看电影', '散步'],
    'years': ['3', '5', '8', '10'],
    'places': ['上海', '杭州', '苏州', '南京', '北京'],
    'times': ['2', '3', '4'],
    'things': ['新闻', '段子', '视频', '图片'],
    'plans': ['成家立业', '有自己的小家', '稳定下来', '好好过日子'],
    'opinions': ['顺其自然', '认真对待', '理性看待', '重视']
}


def fill_template(template: str, user_info: Dict[str, Any]) -> str:
    """填充模板中的占位符"""
    result = template
    for key, values in WORD_BANK.items():
        placeholder = key
        if placeholder in result:
            result = result.replace(placeholder, random.choice(values))

    # 替换用户特定信息
    if '{name}' in result:
        result = result.replace('{name}', user_info.get('name', ''))
    if '{job}' in result:
        result = result.replace('{job}', user_info.get('job', ''))
    if '{age}' in result:
        result = result.replace('{age}', str(user_info.get('age', '')))

    return result


def generate_conversation(
    female_user: Dict[str, Any],
    male_user: Dict[str, Any],
    conv_length: int = 20
) -> List[Dict[str, Any]]:
    """生成一段对话记录"""

    messages = []

    # 选择对话类型（正常/拒绝/友好结束）
    conv_type = random.choices(
        ['正常', '拒绝', '友好'],
        weights=[70, 15, 15]
    )[0]

    # 根据对话类型选择模板序列
    if conv_type == '正常':
        stages = ['初次问候', '工作生活', '兴趣爱好', '日常关心', '深入交流', '约会邀约', '感情表达', '期待']
        if conv_length > 30:
            stages.append('确认')
    elif conv_type == '拒绝':
        stages = ['初次问候', '工作生活', '兴趣爱好', '深入交流', '拒绝/结束']
    else:
        stages = ['初次问候', '工作生活', '兴趣爱好', '日常关心', '友好']

    # 生成消息
    stage_idx = 0
    current_time = datetime.now() - timedelta(days=random.randint(1, 60))

    for i in range(conv_length):
        # 确定当前阶段
        if i < 2:
            stage = '初次问候'
        elif i < 4:
            stage = stages[min(1, len(stages)-1)]
        else:
            progress = (i - 4) / (conv_length - 4)
            stage_idx = int(progress * (len(stages) - 2))
            stage = stages[stage_idx]

        # 确定发言者（轮流发言，偶尔连续发言）
        if i == 0:
            gender = '女'  # 女生先发起
        elif random.random() < 0.15:  # 15% 概率连续发言
            gender = messages[-1]['gender']
        else:
            gender = '男' if messages[-1]['gender'] == '女' else '女'

        # 选择模板并填充
        templates = CHAT_TEMPLATES.get(stage, {}).get(gender, [])
        if not templates:
            templates = RELATIONSHIP_TEMPLATES.get(stage, {}).get(gender, [])

        if templates:
            template = random.choice(templates)
            user_info = female_user if gender == '女' else male_user
            content = fill_template(template, user_info)
        else:
            # 如果没有模板，使用通用问候
            content = random.choice(["好的", "嗯嗯", "理解", "谢谢", "好的呢"])

        # 时间间隔（1-120 分钟）
        time_gap = random.randint(1, 120)
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
        ORDER BY id
    ''')
    female_users = [
        {
            'id': str(row[0]),  # 转为字符串
            'name': row[1],
            'age': row[2],
            'job': row[3] or '上班族',
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
        ORDER BY id
    ''')
    male_users = [
        {
            'id': str(row[0]),  # 转为字符串
            'name': row[1],
            'age': row[2],
            'job': row[3] or '上班族',
            'education': row[4],
            'status': row[5]
        }
        for row in cursor.fetchall()
    ]

    cursor.close()
    conn.close()

    return female_users, male_users


def create_chat_thread(
    cursor,
    female_id: str,
    male_id: str
) -> str:
    """创建聊天线程"""
    thread_id = f"thread-{uuid.uuid4().hex[:16]}"
    case_id = f"case-{uuid.uuid4().hex[:16]}"
    relation_key = f"relation-{female_id}-{male_id}"

    # 创建线程
    cursor.execute('''
        INSERT INTO chat_threads
        (thread_id, case_id, relation_key, status, participant_a_id, participant_b_id, metadata_json, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        thread_id,
        case_id,
        relation_key,
        'active',
        female_id,
        male_id,
        json.dumps({'source': 'match', 'created_by': 'system'}),
        datetime.now() - timedelta(days=random.randint(30, 90)),
        datetime.now() - timedelta(days=random.randint(1, 30))
    ))

    return thread_id


def insert_messages(
    cursor,
    thread_id: str,
    messages: List[Dict[str, Any]]
) -> int:
    """插入聊天消息"""
    count = 0
    for msg in messages:
        message_id = None  # 自动生成
        client_msg_id = f"client-{uuid.uuid4().hex[:16]}"

        cursor.execute('''
            INSERT INTO chat_messages
            (thread_id, author_id, message_recipient_id, visibility, source, body, client_msg_id, reply_to_message_id, metadata_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            thread_id,
            msg['author_id'],
            None,  # recipient
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
    target_count: int = 5000,
    max_threads_per_female: int = 5
) -> Dict[str, int]:
    """
    生成聊天记录

    Args:
        target_count: 目标消息数量
        max_threads_per_female: 每个女生最多创建几个聊天线程

    Returns:
        统计信息
    """
    print("正在获取用户数据...")
    female_users, male_users = get_users_from_db()

    print(f"找到 {len(female_users)} 个无锡女性用户")
    print(f"找到 {len(male_users)} 个无锡男性用户")

    # 为每个女性用户创建聊天记录
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute('USE her_chat')

    total_threads = 0
    total_messages = 0
    processed_females = 0

    print("\n开始生成聊天记录...")

    for female in female_users:
        # 随机选择 1-5 个男性用户与该女性聊天
        num_threads = random.randint(1, max_threads_per_female)

        # 随机选择男性用户
        selected_males = random.sample(male_users, min(num_threads, len(male_users)))

        for male in selected_males:
            # 创建聊天线程
            thread_id = create_chat_thread(cursor, female['id'], male['id'])
            total_threads += 1

            # 生成对话内容（15-50 条消息）
            conv_length = random.randint(15, 50)
            messages = generate_conversation(female, male, conv_length)

            # 插入消息
            msg_count = insert_messages(cursor, thread_id, messages)
            total_messages += msg_count

            if total_messages >= target_count:
                break

        processed_females += 1

        # 每100个用户提交一次
        if processed_females % 100 == 0:
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
    print("开始生成聊天记录数据")
    print("=" * 60)

    # 生成 5000 条聊天记录作为测试
    stats = generate_chat_records(target_count=5000)

    print("\n" + "=" * 60)
    print("生成完成！")
    print("=" * 60)
    print(f"处理女性用户数: {stats['processed_females']}")
    print(f"创建聊天线程数: {stats['total_threads']}")
    print(f"创建聊天消息数: {stats['total_messages']}")
    print("=" * 60)


if __name__ == '__main__':
    main()