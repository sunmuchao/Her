"""
生成真实且个性化的聊天记录 - 智能版
根据用户人设特征生成不同风格的聊天内容
"""

import pymysql
import random
import uuid
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

# 数据库连接配置
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3307,
    'user': 'root',
    'password': '',
    'charset': 'utf8mb4'
}

# 用户人设模板 - 根据年龄、职业、性格特征分类
USER_PERSONA_TEMPLATES = {
    # 年轻活泼型（23-26岁）
    '年轻活泼': {
        '女': {
            '问候风格': ['哈喽～', '你好呀', '嗨', '嘿', '你好～'],
            '表达习惯': ['哈哈', '呀', '呢', '～', '好呀', '对呀'],
            '常用话题': [
                ('周末', '周末有什么好玩的吗？'),
                ('美食', '最近发现一家超好吃的{food}'),
                ('综艺', '你最近看什么综艺了吗？'),
                ('打卡', '想去{location}打卡拍照'),
                ('运动', '最近在学瑜伽，挺好玩的'),
                ('旅行', '想去{city}玩，有空一起去吗'),
            ],
            '性格特质': ['开朗', '活泼', '有趣', '好玩', '爱笑'],
            '回复节奏': '快，常带语气词',
        },
        '男': {
            '问候风格': ['哈喽', '你好呀', '嗨', '你好', '嘿'],
            '表达习惯': ['哈哈', '呀', '呢', '挺', '还行'],
            '常用话题': [
                ('运动', '周末去打球或者跑步？'),
                ('电影', '最近那部电影挺好看的'),
                ('美食', '听说{location}那边新开了家店'),
                ('旅行', '我也想去{city}玩'),
                ('游戏', '平时玩游戏吗'),
            ],
            '性格特质': ['阳光', '开朗', '有趣', '随和'],
            '回复节奏': '快，直接',
        }
    },

    # 温柔内敛型（26-30岁）
    '温柔内敛': {
        '女': {
            '问候风格': ['你好', '很高兴认识你', '你好呀', '你好，很高兴见到你'],
            '表达习惯': ['嗯', '好的', '谢谢', '辛苦了', '理解'],
            '常用话题': [
                ('工作', '平时工作怎么样？'),
                ('生活', '周末一般怎么放松？'),
                ('读书', '最近在看{book_type}'),
                ('健康', '最近要注意身体哦'),
                ('家庭', '你觉得家庭重要吗'),
                ('价值观', '我觉得{value}很重要'),
            ],
            '性格特质': ['温柔', '体贴', '细心', '理解', '包容'],
            '回复节奏': '适中，语气温和',
        },
        '男': {
            '问候风格': ['你好', '很高兴认识你', '你好呀', '你好，我是{name}'],
            '表达习惯': ['嗯', '好的', '理解', '谢谢', '辛苦了'],
            '常用话题': [
                ('工作', '我工作还算稳定'),
                ('规划', '对未来有什么规划？'),
                ('家庭', '我很看重家庭'),
                ('健康', '注意身体别太累'),
                ('价值观', '我觉得{value}很重要'),
            ],
            '性格特质': ['稳重', '体贴', '细心', '有责任心'],
            '回复节奏': '适中，语气平和',
        }
    },

    # 成熟理性型（30-35岁）
    '成熟理性': {
        '女': {
            '问候风格': ['你好', '你好，想了解一下你', '你好，看到你的资料'],
            '表达习惯': ['嗯', '理解', '好的', '明白', '可以'],
            '常用话题': [
                ('事业', '你的事业发展怎么样？'),
                ('规划', '你对未来有什么明确规划？'),
                ('价值观', '我们价值观是否一致'),
                ('家庭', '你对家庭的看法是什么'),
                ('稳定', '我希望生活稳定'),
                ('结婚', '你对结婚有什么想法'),
            ],
            '性格特质': ['理性', '成熟', '稳重', '有规划', '务实'],
            '回复节奏': '适中偏慢，言简意赅',
        },
        '男': {
            '问候风格': ['你好', '你好，我是{name}', '你好，很高兴认识你'],
            '表达习惯': ['嗯', '理解', '好的', '明白', '确实'],
            '常用话题': [
                ('事业', '我事业稳定，收入{level}'),
                ('规划', '我有明确的职业规划'),
                ('家庭', '我很重视家庭建设'),
                ('结婚', '我是认真来找另一半的'),
                ('稳定', '生活需要稳定'),
            ],
            '性格特质': ['成熟', '稳重', '有规划', '理性', '务实'],
            '回复节奏': '适中偏慢，内容实在',
        }
    },

    # 文艺浪漫型（各年龄段）
    '文艺浪漫': {
        '女': {
            '问候风格': ['你好呀', '你好，看到你的照片很有感觉', '你好，觉得我们可能有缘分'],
            '表达习惯': ['～', '呢', '呀', '嗯嗯', '觉得'],
            '常用话题': [
                ('艺术', '我喜欢{art_type}'),
                ('阅读', '最近在看{book}'),
                ('旅行', '想去{city}感受不同的文化'),
                ('音乐', '你喜欢什么类型的音乐'),
                ('摄影', '我喜欢去{location}拍照'),
                ('生活', '我觉得生活需要有诗意'),
            ],
            '性格特质': ['文艺', '浪漫', '有想法', '感性'],
            '回复节奏': '适中，语气柔和',
        },
        '男': {
            '问候风格': ['你好', '你好，你的气质很好', '你好，很高兴认识你'],
            '表达习惯': ['～', '呢', '觉得', '嗯', '喜欢'],
            '常用话题': [
                ('艺术', '我对{art_type}很感兴趣'),
                ('旅行', '我喜欢去有文化底蕴的地方'),
                ('摄影', '我喜欢摄影，记录生活'),
                ('音乐', '我喜欢听{music_type}'),
                ('阅读', '平时喜欢看书'),
            ],
            '性格特质': ['文艺', '有品位', '感性', '浪漫'],
            '回复节奏': '适中，语气柔和',
        }
    },

    # 职场精英型（28-35岁，特定职业）
    '职场精英': {
        '女': {
            '问候风格': ['你好', '你好，很高兴认识你', '你好，我是{name}'],
            '表达习惯': ['嗯', '好的', '可以', '理解', '确实'],
            '常用话题': [
                ('职业', '我在{industry}行业工作'),
                ('发展', '你的职业发展怎么样'),
                ('效率', '我平时工作比较高效'),
                ('成长', '我觉得需要不断成长'),
                ('平衡', '工作和生活需要平衡'),
            ],
            '性格特质': ['专业', '高效', '上进', '有目标'],
            '回复节奏': '快，简洁明了',
        },
        '男': {
            '问候风格': ['你好', '你好，我是{name}，在{job}工作', '你好，很高兴认识你'],
            '表达习惯': ['嗯', '好的', '确实', '理解', '可以'],
            '常用话题': [
                ('职业', '我在{industry}，发展还不错'),
                ('成就', '我最近完成了一个{achievement}'),
                ('规划', '我对职业有明确规划'),
                ('成长', '持续学习和成长很重要'),
                ('效率', '我注重效率和质量'),
            ],
            '性格特质': ['专业', '上进', '有目标', '稳重'],
            '回复节奏': '适中，内容实在',
        }
    },
}

# 职业相关的专业话题
JOB_SPECIFIC_TOPICS = {
    '医生': ['医院', '患者', '健康', '医学', '值班', '手术'],
    '护士': ['护理', '病人', '值班', '医院', '健康'],
    '教师': ['学生', '教育', '课程', '学校', '孩子'],
    '程序员': ['技术', '代码', '项目', '开发', '加班', '互联网'],
    '设计师': ['设计', '创意', '美学', '作品', '灵感'],
    '财务': ['财务', '报表', '数据', '分析', '公司'],
    '销售': ['客户', '业绩', '市场', '销售', '出差'],
    '律师': ['案件', '法律', '客户', '法庭', '合同'],
    '运营': ['运营', '活动', '数据', '用户', '增长'],
    'HR': ['招聘', '人才', '面试', '团队', '企业文化'],
    '产品': ['产品', '需求', '用户', '迭代', '上线'],
    '会计': ['账务', '审计', '报表', '财务', '税务'],
    '工程师': ['技术', '工程', '项目', '研发', '制造'],
}

# 无锡本地话题
WUXI_TOPICS = {
    '景点': ['鼋头渚', '蠡湖公园', '南禅寺', '惠山古镇', '灵山大佛', '梅园', '太湖', '清名桥'],
    '美食': ['无锡小笼', '排骨', '太湖三白', '阳山水蜜桃', '锡惠公园小吃', '万达美食', '恒隆餐厅'],
    '商圈': ['万达广场', '恒隆广场', '苏宁广场', '万象城', '八佰伴'],
    '活动': ['蠡湖灯光节', '鼋头渚樱花节', '灵山祈福', '太湖马拉松', '无锡电影节'],
}

# 通用话题库
GENERAL_TOPICS = {
    '兴趣爱好': ['瑜伽', '健身', '跑步', '游泳', '看书', '追剧', '旅行', '摄影', '烘焙', '画画', '弹琴', '看电影', '打游戏', '听音乐'],
    '美食': ['火锅', '日料', '西餐', '烧烤', '海鲜', '甜点', '咖啡', '奶茶', '轻食', '中餐'],
    '运动': ['跑步', '健身', '瑜伽', '游泳', '打球', '骑行', '爬山'],
    '旅行': ['上海', '杭州', '苏州', '南京', '北京', '成都', '云南', '日本', '泰国'],
    '艺术': ['摄影', '画画', '书法', '音乐', '电影', '戏剧', '舞蹈'],
    '书籍': ['小说', '散文', '传记', '心理学', '历史', '哲学'],
    '音乐': ['流行', '古典', '民谣', '爵士', '摇滚'],
    '价值观': ['真诚', '理解', '信任', '成长', '家庭', '责任', '自由', '稳定', '尊重'],
}

# 对话阶段模板（更真实、口语化）
CONVERSATION_PHASES = {
    '开场': {
        '模板': [
            ('问候', '{greeting_style}'),
            ('自我介绍', '我是{name}，在{job}'),
            ('寒暄', '{weather_or_time}'),
            ('资料评论', '看到你的{profile_comment}'),
        ],
        '时长': 2-4,
    },
    '工作生活': {
        '模板': [
            ('工作', '{work_topic}'),
            ('日常', '{daily_topic}'),
            ('压力', '工作压力怎么样'),
            ('休息', '周末怎么放松'),
        ],
        '时长': 3-6,
    },
    '兴趣爱好': {
        '模板': [
            ('爱好分享', '我喜欢{hobby}'),
            ('共同爱好', '{shared_hobby_check}'),
            ('具体活动', '{activity}'),
            ('推荐', '推荐你去{recommend}'),
        ],
        '时长': 4-8,
    },
    '深入了解': {
        '模板': [
            ('价值观', '{value_question}'),
            ('家庭观', '{family_topic}'),
            ('未来规划', '{future_question}'),
            ('性格', '你觉得自己是什么性格'),
        ],
        '时长': 3-5,
    },
    '邀约见面': {
        '模板': [
            ('试探', '有空可以见个面'),
            ('具体邀约', '{specific_invitation}'),
            ('时间地点', '{time_location}'),
            ('确认', '好的，{confirmation}'),
        ],
        '时长': 2-4,
    },
    '关系推进': {
        '模板': [
            ('好感表达', '{good_feeling}'),
            ('期待', '期待见面'),
            ('承诺', '{commitment}'),
        ],
        '时长': 2-3,
    },
}

# 对话结束类型
CONVERSATION_ENDINGS = {
    '积极继续': {
        '信号': ['期待见面', '好的', '到时候见', '保持联系'],
        '线程状态': 'active',
        '概率': 60,
    },
    '成功匹配': {
        '信号': ['我们挺合适的', '很开心认识你', '期待未来', '确认关系'],
        '线程状态': 'matched',
        '概率': 20,
    },
    '友好暂停': {
        '信号': ['先了解一段时间', '保持联系', '做朋友'],
        '线程状态': 'paused',
        '概率': 10,
    },
    '婉拒结束': {
        '信号': ['不太合适', '谢谢你的时间', '祝你找到合适的人'],
        '线程状态': 'paused',
        '概率': 10,
    },
}


def determine_persona(age: int, job: str, education: str) -> str:
    """根据年龄、职业、学历判断用户人设类型"""

    # 职业优先判断（职场精英型）
    elite_jobs = ['程序员', '工程师', '财务', '律师', '产品', '运营', '数据分析', '审计']
    if job and any(elite_word in str(job) for elite_word in elite_jobs):
        if age >= 28:
            return '职场精英'

    # 年龄判断
    if age <= 25:
        return '年轻活泼'
    elif age <= 29:
        # 可能是温柔内敛或文艺浪漫
        return random.choices(['温柔内敛', '文艺浪漫'], weights=[60, 40])[0]
    elif age <= 35:
        return random.choices(['成熟理性', '温柔内敛', '职场精英'], weights=[50, 30, 20])[0]
    else:
        return '成熟理性'


def get_persona_templates(persona: str, gender: str) -> Dict:
    """获取特定人设的模板"""
    return USER_PERSONA_TEMPLATES.get(persona, USER_PERSONA_TEMPLATES['温柔内敛'])[gender]


def generate_personalized_message(
    user_info: Dict,
    partner_info: Dict,
    phase: str,
    turn: int,
    persona: str,
    gender: str
) -> str:
    """生成个性化的聊天消息"""

    templates = get_persona_templates(persona, gender)

    # 根据阶段和轮次选择话题
    if phase == '开场':
        if turn == 0:
            # 第一条消息：问候
            greeting = random.choice(templates['问候风格'])
            return greeting
        elif turn == 1:
            # 第二条消息：简单介绍或寒暄
            if random.random() < 0.5:
                return f"我是{user_info.get('name', '')}，很高兴认识你"
            else:
                time_greetings = ['今天天气不错', '周末愉快', '晚上好', '下午好']
                return random.choice(time_greetings)
        else:
            # 评论对方资料
            profile_comments = ['照片挺好看的', '资料写得挺详细的', '看起来挺阳光的', '感觉挺有缘分的']
            return random.choice(profile_comments)

    elif phase == '工作生活':
        # 选择话题
        if random.random() < 0.6:
            # 工作话题
            job = user_info.get('job', '')
            if job and job in JOB_SPECIFIC_TOPICS:
                job_topics = JOB_SPECIFIC_TOPICS[job]
                topic = random.choice(job_topics)
                return f"我在{job}工作，平时跟{topic}打交道比较多"
            else:
                work_expressions = templates['常用话题']
                for topic_tuple in work_expressions:
                    if topic_tuple[0] == '工作':
                        return topic_tuple[1].replace('{job}', user_info.get('job', '公司'))
        else:
            # 生活话题
            life_topics = [
                '平时工作压力还行',
                '周末会去放松一下',
                '我作息比较规律',
                '平时喜欢自己做饭',
                '周末会和朋友聚聚',
            ]
            return random.choice(life_topics)

    elif phase == '兴趣爱好':
        # 根据人设选择话题
        hobby_topics = templates['常用话题']
        for topic_tuple in hobby_topics:
            if topic_tuple[0] in ['美食', '运动', '旅行', '艺术', '打卡']:
                template = topic_tuple[1]
                # 填充占位符
                if '{food}' in template:
                    template = template.replace('{food}', random.choice(GENERAL_TOPICS['美食']))
                if '{location}' in template:
                    template = template.replace('{location}', random.choice(WUXI_TOPICS['景点']))
                if '{city}' in template:
                    template = template.replace('{city}', random.choice(GENERAL_TOPICS['旅行']))
                return template

        # 通用爱好话题
        hobbies = random.choice(GENERAL_TOPICS['兴趣爱好'])
        return f"我平时喜欢{hobbies}"

    elif phase == '深入了解':
        # 价值观话题
        value_questions = [
            '你觉得两个人相处最重要的是什么',
            '你对未来有什么规划吗',
            '你觉得家庭重要吗',
            '你是怎么看待婚姻的',
            '你觉得什么样的人适合你',
        ]
        return random.choice(value_questions)

    elif phase == '邀约见面':
        if turn == 0:
            # 试探性邀约
            invitations = [
                '有空我们可以见个面',
                '聊了这么久，想见个面聊聊',
                '周末有空出来走走吗',
            ]
            return random.choice(invitations)
        elif turn == 1:
            # 具体邀约
            location = random.choice(WUXI_TOPICS['商圈'])
            activity = random.choice(['吃饭', '喝咖啡', '看电影', '逛街'])
            return f"我们可以去{location}{activity}"
        else:
            # 确认
            confirmations = ['好的，到时候见', '嗯，我会去的', '期待见面', '好的呢']
            return random.choice(confirmations)

    elif phase == '关系推进':
        # 表达好感
        good_feelings = [
            '和你聊天感觉很舒服',
            '我觉得我们挺合的',
            '你给我的感觉很好',
            '我很期待和你见面',
        ]
        return random.choice(good_feelings)

    # 默认回复
    return random.choice(['好的', '嗯', '理解', '谢谢'])


def add_persona_expression(message: str, persona: str, gender: str) -> str:
    """添加人设特色的语气词和表达"""

    templates = get_persona_templates(persona, gender)
    expressions = templates['表达习惯']

    # 根据人设添加不同的语气特征
    if persona == '年轻活泼':
        # 添加活泼的语气词
        if random.random() < 0.3:
            suffixes = ['～', '呢', '呀', '哈哈']
            message = message + random.choice(suffixes)

    elif persona == '温柔内敛':
        # 保持温和语气
        if random.random() < 0.2:
            message = message + '哦'

    elif persona == '文艺浪漫':
        # 添加文艺气息
        if random.random() < 0.25:
            suffixes = ['～', '呢', '感觉很好']
            message = message + random.choice(suffixes)

    return message


def generate_conversation(
    female_user: Dict,
    male_user: Dict,
    conv_length: int = 30
) -> Tuple[List[Dict], str]:
    """生成一段完整的个性化对话"""

    # 确定双方人设
    female_persona = determine_persona(
        female_user.get('age', 28),
        female_user.get('job', ''),
        female_user.get('education', '')
    )
    male_persona = determine_persona(
        male_user.get('age', 30),
        male_user.get('job', ''),
        male_user.get('education', '')
    )

    messages = []

    # 确定对话走向
    ending_type = random.choices(
        list(CONVERSATION_ENDINGS.keys()),
        weights=[e['概率'] for e in CONVERSATION_ENDINGS.values()]
    )[0]

    # 根据对话走向确定阶段
    if ending_type == '积极继续':
        phases = ['开场', '工作生活', '兴趣爱好', '深入了解', '邀约见面']
    elif ending_type == '成功匹配':
        phases = ['开场', '工作生活', '兴趣爱好', '深入了解', '邀约见面', '关系推进']
    elif ending_type == '友好暂停':
        phases = ['开场', '工作生活', '兴趣爱好', '深入了解']
    else:  # 婉拒结束
        phases = ['开场', '工作生活', '兴趣爱好']

    # 生成消息
    current_time = datetime.now() - timedelta(days=random.randint(1, 60))
    phase_idx = 0
    phase_turn = 0

    for i in range(conv_length):
        # 确定当前阶段
        phase_messages = {
            '开场': 3,
            '工作生活': 5,
            '兴趣爱好': 7,
            '深入了解': 4,
            '邀约见面': 4,
            '关系推进': 3,
        }

        if phase_turn >= phase_messages.get(phases[phase_idx], 3):
            phase_idx = min(phase_idx + 1, len(phases) - 1)
            phase_turn = 0

        current_phase = phases[phase_idx]

        # 确定发言者
        if i == 0:
            gender = '女'  # 女生先发起
        elif random.random() < 0.12:  # 连续发言概率
            gender = messages[-1]['gender']
        else:
            gender = '男' if messages[-1]['gender'] == '女' else '女'

        # 获取用户信息和人设
        if gender == '女':
            user_info = female_user
            partner_info = male_user
            persona = female_persona
        else:
            user_info = male_user
            partner_info = female_user
            persona = male_persona

        # 生成消息内容
        content = generate_personalized_message(
            user_info, partner_info, current_phase, phase_turn, persona, gender
        )

        # 添加人设特色
        content = add_persona_expression(content, persona, gender)

        # 时间间隔
        time_gap = random.randint(1, 60)
        current_time = current_time + timedelta(minutes=time_gap)

        messages.append({
            'gender': gender,
            'author_id': female_user['id'] if gender == '女' else male_user['id'],
            'recipient_id': male_user['id'] if gender == '女' else female_user['id'],
            'content': content,
            'created_at': current_time,
            'phase': current_phase,
            'persona': persona,
        })

        phase_turn += 1

    # 确定线程状态
    thread_status = CONVERSATION_ENDINGS[ending_type]['线程状态']

    return messages, thread_status


def get_users_from_db() -> Tuple[List[Dict], List[Dict]]:
    """从数据库获取用户列表"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    # 获取无锡女性用户
    cursor.execute('USE her')
    cursor.execute('''
        SELECT id, name, age, job, education, profile_status
        FROM profiles
        WHERE city = '无锡' AND gender = '女' AND profile_status IN ('active', 'matched')
    ''')

    female_users = []
    for row in cursor.fetchall():
        female_users.append({
            'id': str(row[0]),
            'name': row[1],
            'age': row[2] or random.randint(24, 35),
            'job': row[3] or '',
            'education': row[4] or '',
            'status': row[5]
        })

    # 获取无锡男性用户
    cursor.execute('''
        SELECT id, name, age, job, education, profile_status
        FROM profiles
        WHERE city = '无锡' AND gender = '男' AND profile_status IN ('active', 'matched')
    ''')

    male_users = []
    for row in cursor.fetchall():
        male_users.append({
            'id': str(row[0]),
            'name': row[1],
            'age': row[2] or random.randint(26, 38),
            'job': row[3] or '',
            'education': row[4] or '',
            'status': row[5]
        })

    cursor.close()
    conn.close()

    return female_users, male_users


def clear_existing_chats():
    """清除现有聊天记录"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute('USE her_chat')

    # 先删除依赖表
    try:
        cursor.execute('DELETE FROM chat_thread_summaries')
    except:
        pass

    try:
        cursor.execute('DELETE FROM chat_conversations')
    except:
        pass

    cursor.execute('DELETE FROM chat_messages')
    cursor.execute('DELETE FROM chat_threads')

    conn.commit()
    cursor.close()
    conn.close()
    print("已清除现有聊天记录")


def insert_chat_data(
    cursor,
    thread_id: str,
    female_id: str,
    male_id: str,
    messages: List[Dict],
    thread_status: str
) -> int:
    """插入聊天线程和消息"""

    # 创建线程
    case_id = f"case-{uuid.uuid4().hex[:16]}"
    relation_key = f"relation-{female_id}-{male_id}"

    cursor.execute('''
        INSERT INTO chat_threads
        (thread_id, case_id, relation_key, status, participant_a_id, participant_b_id, metadata_json, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        thread_id,
        case_id,
        relation_key,
        thread_status,
        female_id,
        male_id,
        json.dumps({
            'source': 'match',
            'created_by': 'system',
            'female_persona': messages[0]['persona'] if messages else '',
            'compatibility_score': random.randint(65, 95)
        }),
        messages[0]['created_at'] if messages else datetime.now(),
        messages[-1]['created_at'] if messages else datetime.now()
    ))

    # 插入消息
    count = 0
    for msg in messages:
        client_msg_id = f"client-{uuid.uuid4().hex[:16]}"

        cursor.execute('''
            INSERT INTO chat_messages
            (thread_id, author_id, message_recipient_id, visibility, source, body, client_msg_id, reply_to_message_id, metadata_json, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            thread_id,
            msg['author_id'],
            msg['recipient_id'],
            'normal',
            'user',
            msg['content'],
            client_msg_id,
            None,
            json.dumps({
                'phase': msg['phase'],
                'persona': msg['persona']
            }),
            msg['created_at']
        ))
        count += 1

    return count


def generate_all_chat_records(
    target_messages: int = 50000,
    threads_per_female: int = 3,
    clear_existing: bool = True
) -> Dict:
    """生成所有聊天记录"""

    if clear_existing:
        clear_existing_chats()

    print("正在获取用户数据...")
    female_users, male_users = get_users_from_db()

    print(f"找到 {len(female_users)} 个无锡女性用户")
    print(f"找到 {len(male_users)} 个无锡男性用户")

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute('USE her_chat')

    total_threads = 0
    total_messages = 0

    print("\n开始生成个性化聊天记录...")

    for female_idx, female in enumerate(female_users):
        # 为每个女性用户创建 1-3 个聊天线程
        num_threads = random.randint(1, threads_per_female)

        # 随机选择男性用户
        available_males = [m for m in male_users if m['id'] != female['id']]
        selected_males = random.sample(available_males, min(num_threads, len(available_males)))

        for male in selected_males:
            # 生成对话
            conv_length = random.randint(20, 40)
            messages, thread_status = generate_conversation(female, male, conv_length)

            # 插入数据
            thread_id = f"thread-{uuid.uuid4().hex[:16]}"
            msg_count = insert_chat_data(cursor, thread_id, female['id'], male['id'], messages, thread_status)

            total_threads += 1
            total_messages += msg_count

            if total_messages >= target_messages:
                break

        # 每50个用户提交一次
        if (female_idx + 1) % 50 == 0:
            conn.commit()
            print(f"已处理 {female_idx + 1} 个女性用户，创建了 {total_threads} 个线程，{total_messages} 条消息")

        if total_messages >= target_messages:
            break

    conn.commit()
    cursor.close()
    conn.close()

    return {
        'processed_females': female_idx + 1,
        'total_threads': total_threads,
        'total_messages': total_messages
    }


def main():
    """主函数"""
    print("=" * 60)
    print("开始生成个性化聊天记录数据")
    print("特点：根据用户人设生成不同风格的聊天内容")
    print("=" * 60)

    stats = generate_all_chat_records(
        target_messages=50000,
        threads_per_female=3,
        clear_existing=True
    )

    print("\n" + "=" * 60)
    print("生成完成！")
    print("=" * 60)
    print(f"处理女性用户数: {stats['processed_females']}")
    print(f"创建聊天线程数: {stats['total_threads']}")
    print(f"创建聊天消息数: {stats['total_messages']}")
    print("=" * 60)


if __name__ == '__main__':
    main()