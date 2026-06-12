"""
生成真实且多样化的聊天记录 - 终极版
特点：
1. 每个用户根据真实人设（年龄、职业、性格）生成独特风格
2. 对话内容丰富多变，避免模板化重复
3. 包含追问、共鸣、话题转换等真实互动
4. 对话风格各异：有的活泼、有的稳重、有的文艺
"""

import pymysql
import random
import uuid
import json
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass

# 数据库连接配置
DB_CONFIG = {
    'host': '127.0.0.1',
    'port': 3307,
    'user': 'root',
    'password': '',
    'charset': 'utf8mb4'
}

@dataclass
class UserPersona:
    """用户人设数据类"""
    user_id: str  # 用户ID
    age: int
    job: str
    education: str
    name: str
    gender: str

    # 人设类型
    persona_type: str  # 年轻活泼/温柔内敛/成熟理性/职场精英/文艺浪漫

    # 表达特征
    tone_level: float  # 语气强烈程度 0-1
    emoji_freq: float  # 表情频率 0-1
    response_speed: str  # 快/中/慢
    detail_level: str  # 详细/简洁

    # 话题偏好
    preferred_topics: List[str]  # 喜欢聊的话题
    conversation_style: str  # 主动/被动/互动型


class PersonaAnalyzer:
    """人设分析器 - 根据用户属性判断人设特征"""

    # 年龄段特征
    AGE_CHARACTERISTICS = {
        (18, 25): {
            'possible_personas': ['年轻活泼', '文艺浪漫'],
            'tone_level_range': (0.6, 0.9),
            'emoji_freq_range': (0.4, 0.8),
            'response_speed': '快',
            'detail_level_options': ['详细', '简洁'],
            'preferred_topics': ['美食', '旅行', '电影', '综艺', '打卡', '运动', '游戏'],
        },
        (26, 30): {
            'possible_personas': ['温柔内敛', '职场精英', '文艺浪漫', '成熟理性'],
            'tone_level_range': (0.3, 0.6),
            'emoji_freq_range': (0.2, 0.5),
            'response_speed': '中',
            'detail_level_options': ['详细', '简洁'],
            'preferred_topics': ['工作', '生活', '健康', '旅行', '读书', '价值观'],
        },
        (31, 40): {
            'possible_personas': ['成熟理性', '职场精英', '温柔内敛'],
            'tone_level_range': (0.2, 0.5),
            'emoji_freq_range': (0.1, 0.3),
            'response_speed': '中',
            'detail_level_options': ['简洁', '详细'],
            'preferred_topics': ['事业', '家庭', '规划', '价值观', '稳定', '结婚'],
        },
    }

    # 职业特征
    JOB_CHARACTERISTICS = {
        '程序员': {'persona_bonus': '职场精英', 'topics': ['技术', '项目', '加班', '互联网', '代码']},
        '工程师': {'persona_bonus': '职场精英', 'topics': ['技术', '项目', '研发', '制造']},
        '医生': {'persona_bonus': '温柔内敛', 'topics': ['健康', '医学', '医院', '患者', '值班']},
        '护士': {'persona_bonus': '温柔内敛', 'topics': ['护理', '健康', '医院', '病人']},
        '教师': {'persona_bonus': '温柔内敛', 'topics': ['教育', '孩子', '学校', '课程', '学生']},
        '设计师': {'persona_bonus': '文艺浪漫', 'topics': ['设计', '艺术', '创意', '灵感', '美学']},
        '律师': {'persona_bonus': '成熟理性', 'topics': ['法律', '案件', '合同', '专业']},
        '财务': {'persona_bonus': '职场精英', 'topics': ['财务', '数据', '报表', '分析']},
        '会计': {'persona_bonus': '成熟理性', 'topics': ['账务', '财务', '审计']},
        '运营': {'persona_bonus': '职场精英', 'topics': ['运营', '数据', '活动', '增长']},
        '产品': {'persona_bonus': '职场精英', 'topics': ['产品', '需求', '用户', '迭代']},
        '销售': {'persona_bonus': None, 'topics': ['客户', '业绩', '市场', '出差']},
        'HR': {'persona_bonus': '温柔内敛', 'topics': ['招聘', '团队', '人才', '面试']},
    }

    @staticmethod
    def analyze_user(user_info: Dict) -> UserPersona:
        """分析用户并生成人设"""

        user_id = user_info.get('user_id', user_info.get('id', ''))
        age = user_info.get('age', 28)
        job = user_info.get('job', '')
        education = user_info.get('education', '')
        name = user_info.get('name', '')
        gender = user_info.get('gender', '女')

        # 1. 根据年龄确定基础特征
        age_range = None
        for age_range_tuple, characteristics in PersonaAnalyzer.AGE_CHARACTERISTICS.items():
            if age_range_tuple[0] <= age <= age_range_tuple[1]:
                age_range = characteristics
                break

        if not age_range:
            age_range = PersonaAnalyzer.AGE_CHARACTERISTICS[(26, 30)]  # 默认

        # 2. 确定人设类型
        possible_personas = age_range['possible_personas']

        # 职业加成
        job_chars = PersonaAnalyzer.JOB_CHARACTERISTICS.get(job, {})
        if job_chars.get('persona_bonus'):
            bonus_persona = job_chars['persona_bonus']
            if bonus_persona in possible_personas:
                # 增加该人设的权重
                possible_personas = [bonus_persona] + [p for p in possible_personas if p != bonus_persona]

        persona_type = random.choice(possible_personas[:2])  # 优先选择前两个

        # 3. 确定表达特征
        tone_level = random.uniform(*age_range['tone_level_range'])
        emoji_freq = random.uniform(*age_range['emoji_freq_range'])
        response_speed = age_range['response_speed']
        detail_level = random.choice(age_range['detail_level_options'])

        # 4. 确定话题偏好
        preferred_topics = list(age_range['preferred_topics'])
        if job_chars.get('topics'):
            preferred_topics.extend(job_chars['topics'])

        # 5. 确定对话风格
        conversation_style = random.choice(['主动型', '被动型', '互动型'])

        return UserPersona(
            user_id=user_id,
            age=age,
            job=job,
            education=education,
            name=name,
            gender=gender,
            persona_type=persona_type,
            tone_level=tone_level,
            emoji_freq=emoji_freq,
            response_speed=response_speed,
            detail_level=detail_level,
            preferred_topics=preferred_topics[:5],  # 取前5个
            conversation_style=conversation_style,
        )


class RealisticConversationGenerator:
    """真实对话生成器"""

    # 无锡本地特色话题
    WUXI_LOCAL_TOPICS = {
        '景点': [
            '鼋头渚看樱花', '蠡湖公园散步', '南禅寺逛逛', '惠山古镇品茶',
            '灵山大佛祈福', '梅园赏花', '太湖边骑行', '清名桥夜景',
            '拈花湾打卡', '荡口古镇', '锡惠公园', '龙背山森林公园'
        ],
        '美食': [
            '无锡小笼包', '太湖三白', '阳山水蜜桃', '无锡排骨',
            '玉兰饼', '梅花糕', '糖芋头', '三鲜馄饨',
            '万达美食街', '恒隆餐厅', '苏宁美食', '南禅寺小吃'
        ],
        '商圈': [
            '万达广场逛街', '恒隆购物', '苏宁广场', '万象城',
            '八佰伴', '海岸城', '茂业百货'
        ],
        '活动': [
            '蠡湖灯光节', '鼋头渚樱花节', '太湖马拉松', '无锡电影节',
            '灵山新年祈福', '惠山庙会'
        ],
        '日常': [
            '早上去南禅寺买菜', '周末去鼋头渚散步', '下班后去蠡湖跑步',
            '假期去太湖边玩', '晚上去万达吃饭', '下午去图书馆看书'
        ],
    }

    # 通用话题库（分类详细）
    TOPIC_LIBRARY = {
        '美食': {
            '话题': ['最近发现一家好吃的{food}', '你喜欢什么口味', '周末去吃{food}吧', '{location}那边有什么好吃的'],
            '追问': ['那边人多吗', '价格怎么样', '值得去吗', '需要预约吗'],
            '共鸣': ['我也喜欢吃{food}', '那边确实不错', '下次一起去'],
            'food_options': ['火锅', '日料', '西餐', '烧烤', '海鲜', '甜点', '咖啡', '奶茶', '轻食', '中餐', '私房菜', '网红餐厅'],
            'location_options': ['万达', '恒隆', '南禅寺', '苏宁'],
        },
        '旅行': {
            '话题': ['想去{city}玩', '你去过{city}吗', '最近有什么旅行计划', '喜欢自驾还是跟团'],
            '追问': ['那边好玩吗', '去了几天', '有什么推荐的', '花费多少'],
            '共鸣': ['我也想去{city}', '那地方很美', '下次可以一起去'],
            'city_options': ['上海', '杭州', '苏州', '南京', '成都', '云南', '日本', '泰国', '三亚', '厦门', '青岛'],
        },
        '运动健身': {
            '话题': ['我最近开始{sport}', '你喜欢运动吗', '每周健身几次', '{location}那边适合{sport}'],
            '追问': ['练了多久了', '效果怎么样', '在哪练的', '一个人还是和朋友'],
            '共鸣': ['我也喜欢{sport}', '运动确实重要', '我们可以一起去'],
            'sport_options': ['瑜伽', '跑步', '健身', '游泳', '羽毛球', '网球', '骑行', '爬山', '舞蹈'],
            'location_options': ['蠡湖公园', '健身房', '体育馆', '太湖边'],
        },
        '兴趣爱好': {
            '话题': ['我最近在学{hobby}', '你平时有什么爱好', '周末一般做什么', '我喜欢{hobby}'],
            '追问': ['学了多久', '感觉怎么样', '难吗', '在哪学的'],
            '共鸣': ['我也想学{hobby}', '那个挺有意思的', '可以教我吗'],
            'hobby_options': ['摄影', '画画', '插花', '烘焙', '弹琴', '书法', '茶艺', '园艺', '手工', '读书', '看电影', '追剧', '听音乐', '玩游戏'],
        },
        '工作生活': {
            '话题': ['我在{job}工作', '平时工作忙吗', '工作压力怎么样', '周末怎么放松'],
            '追问': ['做了多久了', '工作内容是什么', '加班多吗', '收入怎么样'],
            '共鸣': ['我工作也差不多', '理解你', '工作确实累'],
            'job_options': ['互联网公司', '医院', '学校', '银行', '国企', '外企', '创业公司'],
        },
        '价值观': {
            '话题': ['你觉得{value}重要吗', '你理想的生活是什么样的', '对{topic}怎么看'],
            '追问': ['为什么这么想', '有具体的标准吗', '你怎么做到的'],
            '共鸣': ['我也这么认为', '我们观点很像', '你说的很对'],
            'value_options': ['家庭', '事业', '健康', '自由', '稳定', '成长', '真诚', '信任'],
            'topic_options': ['婚姻', '孩子', '金钱', '生活方式', '婆媳关系', '异地恋'],
        },
        '约会邀约': {
            '话题': ['周末有空吗', '我们去{location}吧', '想请你吃饭', '见面聊聊怎么样'],
            '追问': ['那天方便吗', '几点合适', '你喜欢什么', '需要准备什么'],
            '共鸣': ['好的没问题', '我很期待', '可以安排'],
            'location_options': ['万达吃饭', '恒隆逛街', '蠡湖散步', '鼋头渚', '看电影', '喝咖啡', '南禅寺逛逛'],
        },
        '日常关心': {
            '话题': ['今天怎么样', '最近还好吗', '工作别太累了', '注意身体'],
            '追问': ['发生什么了', '需要帮忙吗', '怎么解决的'],
            '共鸣': ['理解你', '辛苦了', '别太担心'],
        },
        '情感表达': {
            '话题': ['和你聊天很开心', '我觉得我们挺合的', '你给人的感觉很好', '我很{emotion}'],
            '追问': ['真的吗', '为什么', '你确定吗'],
            '共鸣': ['我也是', '感觉很好', '继续了解吧'],
            'emotion_options': ['期待', '开心', '感动', '安心', '珍惜'],
        },
    }

    # 人设特色表达方式
    PERSONA_EXPRESSIONS = {
        '年轻活泼': {
            '语气词': ['～', '呀', '呢', '哈哈', '好呀', '对呀', '嗯嗯', '嘿嘿', '哇'],
            '表情符号': ['😊', '😄', '🎉', '👍', '💕', '✨', '🌟', '😋', '🥰', '嘻'],
            '开场方式': ['哈喽～', '你好呀', '嗨', '嘿', '你好～'],
            '表达特点': '活泼开朗，多用语气词和表情',
            '句式偏好': ['！', '～', '...哈哈'],
            '话题偏好': ['美食', '旅行', '打卡', '综艺', '运动'],
            '回复特点': '快，热情，会追问细节',
        },
        '温柔内敛': {
            '语气词': ['嗯', '好的', '呢', '哦', '呀'],
            '表情符号': ['😊', '🌸', '🍃', '☀️', '温'],
            '开场方式': ['你好', '很高兴认识你', '你好呀'],
            '表达特点': '温和体贴，语气温和',
            '句式偏好': ['...', '，'],
            '话题偏好': ['生活', '健康', '读书', '家庭', '价值观'],
            '回复特点': '适中，善解人意，会共鸣',
        },
        '成熟理性': {
            '语气词': ['嗯', '好的', '理解', '可以'],
            '表情符号': ['👌', '👍', '🙂', ''],
            '开场方式': ['你好', '你好，我是{name}', '你好，看到你的资料'],
            '表达特点': '简洁务实，言简意赅',
            '句式偏好': ['。'],
            '话题偏好': ['事业', '规划', '家庭', '稳定', '价值观'],
            '回复特点': '适中偏慢，内容实在，问关键问题',
        },
        '职场精英': {
            '语气词': ['嗯', '好的', '确实', '理解'],
            '表情符号': ['👍', '👌', '📊', ''],
            '开场方式': ['你好', '你好，我是{name}', '你好，很高兴认识你'],
            '表达特点': '专业高效，有目标',
            '句式偏好': ['，', '。'],
            '话题偏好': ['事业', '发展', '效率', '成长', '目标'],
            '回复特点': '适中，简洁明了，谈实际内容',
        },
        '文艺浪漫': {
            '语气词': ['～', '呢', '呀', '嗯', '觉得'],
            '表情符号': ['✨', '🌸', '📖', '🎨', '🎵', '📷', '💫'],
            '开场方式': ['你好呀', '你好，看到你的照片很有感觉', '你好，觉得我们可能有缘分'],
            '表达特点': '有诗意，感性',
            '句式偏好': ['～', '...'],
            '话题偏好': ['艺术', '旅行', '摄影', '读书', '音乐'],
            '回复特点': '适中，语气柔和，谈感受',
        },
    }

    # 对话阶段模板（更详细）
    CONVERSATION_PHASES = [
        {
            'name': '开场问候',
            'duration': (2, 4),
            'weight': 1.0,
            'content_types': ['问候', '简单介绍', '资料评论', '寒暄'],
        },
        {
            'name': '工作生活',
            'duration': (3, 6),
            'weight': 0.9,
            'content_types': ['工作介绍', '日常分享', '压力话题', '放松方式'],
        },
        {
            'name': '兴趣爱好',
            'duration': (4, 8),
            'weight': 0.8,
            'content_types': ['爱好分享', '共同话题', '具体活动', '推荐交流'],
        },
        {
            'name': '深入了解',
            'duration': (3, 5),
            'weight': 0.7,
            'content_types': ['价值观探讨', '家庭话题', '规划交流', '性格聊'],
        },
        {
            'name': '日常关心',
            'duration': (2, 4),
            'weight': 0.6,
            'content_types': ['关心问候', '生活细节', '心情分享'],
        },
        {
            'name': '约会邀约',
            'duration': (3, 5),
            'weight': 0.5,
            'content_types': ['试探邀约', '具体安排', '时间确认', '地点商量'],
        },
        {
            'name': '情感表达',
            'duration': (2, 4),
            'weight': 0.4,
            'content_types': ['好感表达', '期待分享', '关系确认'],
        },
    ]

    def __init__(self, female_persona: UserPersona, male_persona: UserPersona):
        self.female_persona = female_persona
        self.male_persona = male_persona
        self.conversation_history: List[Dict] = []
        self.used_messages: set = set()  # 避免重复

    def _get_persona_expression(self, persona: UserPersona) -> Dict:
        """获取人设的表达方式"""
        return self.PERSONA_EXPRESSIONS.get(persona.persona_type, self.PERSONA_EXPRESSIONS['温柔内敛'])

    def _apply_persona_style(self, message: str, persona: UserPersona, add_emoji: bool = True) -> str:
        """应用人设风格到消息"""

        expression = self._get_persona_expression(persona)

        # 1. 根据语气强度添加语气词
        if persona.tone_level > 0.6:
            # 高语气强度：活泼型
            if random.random() < 0.4:
                suffixes = ['～', '呀', '呢', '哈哈']
                message = message.rstrip('。') + random.choice(suffixes)
        elif persona.tone_level > 0.3:
            # 中语气强度：温和型
            if random.random() < 0.3:
                suffixes = ['呢', '哦', '呀']
                message = message.rstrip('。') + random.choice(suffixes)

        # 2. 根据表情频率添加表情符号
        if add_emoji and persona.emoji_freq > 0.3:
            if random.random() < persona.emoji_freq * 0.5:
                emoji_list = expression['表情符号']
                # 选择合适的表情
                if '开心' in message or '高兴' in message or '期待' in message:
                    emoji = random.choice(['😊', '😄', '🎉', '💕'])
                elif '好' in message:
                    emoji = random.choice(['👍', '👌', '😊'])
                else:
                    emoji = random.choice(emoji_list[:5])  # 使用前5个常用表情
                message = message + emoji

        return message

    def _select_topic(self, persona: UserPersona, phase_name: str) -> Tuple[str, Dict]:
        """根据人设和阶段选择话题"""

        # 从人设偏好话题中选择
        preferred_topics = persona.preferred_topics

        # 根据阶段选择合适的话题库
        topic_library = self.TOPIC_LIBRARY

        # 匹配话题
        for topic_name in preferred_topics:
            if topic_name in topic_library:
                topic_data = topic_library[topic_name]
                return topic_name, topic_data

        # 默认返回工作生活话题
        return '工作生活', topic_library['工作生活']

    def _fill_topic_template(self, template: str, topic_data: Dict) -> str:
        """填充话题模板中的变量"""

        result = template

        # 填充各种变量
        for key, options in topic_data.items():
            if key.endswith('_options'):
                placeholder = '{' + key.replace('_options', '') + '}'
                if placeholder in result:
                    result = result.replace(placeholder, random.choice(options))

        return result

    def _generate_topic_message(self, persona: UserPersona, phase_name: str) -> str:
        """生成话题消息"""

        # 选择话题
        topic_name, topic_data = self._select_topic(persona, phase_name)

        # 选择话题类型（话题/追问/共鸣）
        message_type = random.choices(
            ['话题', '追问', '共鸣'],
            weights=[0.6, 0.2, 0.2]
        )[0]

        # 获取模板列表
        templates = topic_data.get(message_type, topic_data.get('话题', []))
        if not templates:
            templates = ['我最近在关注这个话题']

        # 选择一个模板并填充
        template = random.choice(templates)
        message = self._fill_topic_template(template, topic_data)

        # 应用人设风格
        message = self._apply_persona_style(message, persona)

        return message

    def _generate_phase_message(
        self,
        persona: UserPersona,
        phase_name: str,
        turn: int,
        is_responding: bool = False,
        previous_message: Optional[str] = None
    ) -> str:
        """生成特定阶段的消息"""

        # 防止重复
        max_attempts = 3
        for attempt in range(max_attempts):

            if phase_name == '开场问候':
                if turn == 0:
                    expression = self._get_persona_expression(persona)
                    greeting = random.choice(expression['开场方式'])
                    message = self._apply_persona_style(greeting, persona, add_emoji=True)
                elif turn == 1:
                    message = f"我是{persona.name}，很高兴认识你"
                    message = self._apply_persona_style(message, persona)
                else:
                    # 评论资料或寒暄
                    profile_comments = [
                        '看到你的资料觉得不错',
                        '照片挺好看的',
                        '感觉挺有缘分的',
                        '你是无锡本地人吗',
                        '看你也在无锡，想认识一下',
                    ]
                    message = random.choice(profile_comments)
                    message = self._apply_persona_style(message, persona)

            elif phase_name == '工作生活':
                # 根据职业生成话题
                if persona.job:
                    job_specific_messages = [
                        f"我在{persona.job}工作",
                        f"做{persona.job}这个工作挺有意思的",
                        f"我是{persona.job}，平时接触{random.choice(['技术', '业务', '客户', '项目'])}比较多",
                    ]
                    message = random.choice(job_specific_messages)
                else:
                    general_messages = [
                        '平时工作还行',
                        '工作压力适中',
                        '周末会放松一下',
                        '我作息比较规律',
                    ]
                    message = random.choice(general_messages)

                message = self._apply_persona_style(message, persona)

            elif phase_name == '兴趣爱好':
                # 使用话题生成器
                message = self._generate_topic_message(persona, phase_name)

            elif phase_name == '深入了解':
                # 价值观话题
                value_topics = [
                    '你觉得两个人相处最重要的是什么',
                    '你对未来的规划是什么',
                    '你觉得家庭重要吗',
                    '你是怎么看待婚姻的',
                    '你理想的生活是什么样的',
                    '你对事业和家庭怎么平衡',
                ]
                message = random.choice(value_topics)
                message = self._apply_persona_style(message, persona, add_emoji=False)

            elif phase_name == '日常关心':
                caring_messages = [
                    '今天怎么样',
                    '最近还好吗',
                    '工作别太累了',
                    '注意身体',
                    '最近有什么新鲜事',
                    '天气变化了，注意保暖',
                ]
                message = random.choice(caring_messages)
                message = self._apply_persona_style(message, persona)

            elif phase_name == '约会邀约':
                if turn == 0:
                    invitation_messages = [
                        '有空我们可以见个面',
                        '周末出来走走怎么样',
                        '想请你吃饭',
                        '我们见面聊聊吧',
                    ]
                    message = random.choice(invitation_messages)
                else:
                    # 具体安排
                    wuxi_activities = self.WUXI_LOCAL_TOPICS['商圈'] + self.WUXI_LOCAL_TOPICS['景点']
                    activity = random.choice(wuxi_activities)
                    message = f"我们去{activity}吧"

                message = self._apply_persona_style(message, persona)

            elif phase_name == '情感表达':
                emotion_messages = [
                    '和你聊天很开心',
                    '我觉得我们挺合的',
                    '你给人的感觉很好',
                    '我很期待和你见面',
                    '感觉我们有很多共同点',
                ]
                message = random.choice(emotion_messages)
                message = self._apply_persona_style(message, persona, add_emoji=True)

            else:
                # 默认话题
                message = self._generate_topic_message(persona, phase_name)

            # 检查是否重复
            message_hash = hashlib.md5(message.encode()).hexdigest()[:8]
            if message_hash not in self.used_messages:
                self.used_messages.add(message_hash)
                return message

        # 如果尝试多次都重复，生成一个默认回复
        default_messages = ['嗯', '好的', '理解', '谢谢', '可以']
        return random.choice(default_messages)

    def _generate_response(
        self,
        persona: UserPersona,
        previous_message: str,
        phase_name: str
    ) -> str:
        """根据上一条消息生成回复"""

        # 1. 简单的共鸣回复
        if '喜欢' in previous_message or '想' in previous_message:
            empathetic_responses = [
                '我也喜欢',
                '我也觉得不错',
                '那挺好的',
                '可以啊',
            ]
            message = random.choice(empathetic_responses)
            message = self._apply_persona_style(message, persona)
            return message

        # 2. 针对问题的回答
        if '?' in previous_message or '吗' in previous_message:
            question_responses = [
                '嗯，是的',
                '我觉得挺好的',
                '我也有同感',
                '可以接受',
                '我觉得重要',
            ]
            message = random.choice(question_responses)
            message = self._apply_persona_style(message, persona)
            return message

        # 3. 话题转换回复
        if random.random() < 0.3:
            # 30%概率转换话题
            return self._generate_topic_message(persona, phase_name)

        # 4. 默认回复
        default_responses = [
            '嗯',
            '好的',
            '理解',
            '那不错',
            '确实',
        ]
        message = random.choice(default_responses)
        message = self._apply_persona_style(message, persona)
        return message

    def generate_full_conversation(
        self,
        conv_length: int = 30
    ) -> Tuple[List[Dict], str]:
        """生成完整对话"""

        messages = []

        # 确定对话走向
        conversation_outcomes = {
            '积极继续': {'weight': 0.5, 'status': 'active', 'end_phases': ['开场问候', '工作生活', '兴趣爱好', '深入了解', '约会邀约']},
            '成功匹配': {'weight': 0.25, 'status': 'matched', 'end_phases': ['开场问候', '工作生活', '兴趣爱好', '深入了解', '约会邀约', '情感表达']},
            '友好暂停': {'weight': 0.15, 'status': 'paused', 'end_phases': ['开场问候', '工作生活', '兴趣爱好']},
            '婉拒结束': {'weight': 0.10, 'status': 'paused', 'end_phases': ['开场问候', '工作生活']},
        }

        outcome_type = random.choices(
            list(conversation_outcomes.keys()),
            weights=[o['weight'] for o in conversation_outcomes.values()]
        )[0]

        outcome = conversation_outcomes[outcome_type]

        # 构建阶段序列
        phase_sequence = []
        for phase in self.CONVERSATION_PHASES:
            if phase['name'] in outcome['end_phases']:
                duration = random.randint(*phase['duration'])
                phase_sequence.extend([phase['name']] * duration)

        # 调整到目标长度
        while len(phase_sequence) < conv_length:
            phase_sequence.append('日常关心')

        phase_sequence = phase_sequence[:conv_length]

        # 生成消息
        current_time = datetime.now() - timedelta(days=random.randint(1, 60), hours=random.randint(0, 12))

        for i, phase_name in enumerate(phase_sequence):
            # 确定发言者
            if i == 0:
                gender = '女'  # 女生先发起
            elif random.random() < 0.12:  # 12%概率连续发言
                gender = messages[-1]['gender']
            else:
                gender = '男' if messages[-1]['gender'] == '女' else '女'

            # 获取人设
            if gender == '女':
                persona = self.female_persona
                author_id = self.female_persona.user_id
            else:
                persona = self.male_persona
                author_id = self.male_persona.user_id

            # 生成消息内容
            turn_in_phase = sum(1 for j in range(i) if phase_sequence[j] == phase_name and messages[j]['gender'] == gender)

            if i > 0 and random.random() < 0.6:  # 60%概率回复上一条消息
                previous_message = messages[-1]['content']
                message = self._generate_response(persona, previous_message, phase_name)
            else:
                message = self._generate_phase_message(persona, phase_name, turn_in_phase)

            # 时间间隔（根据回复速度调整）
            if persona.response_speed == '快':
                time_gap = random.randint(1, 20)
            elif persona.response_speed == '慢':
                time_gap = random.randint(30, 120)
            else:
                time_gap = random.randint(5, 60)

            current_time = current_time + timedelta(minutes=time_gap)

            messages.append({
                'gender': gender,
                'author_id': author_id,
                'content': message,
                'created_at': current_time,
                'phase': phase_name,
                'persona': persona.persona_type,
            })

        thread_status = outcome['status']

        return messages, thread_status


def get_users_from_db() -> Tuple[List[Dict], List[Dict]]:
    """从数据库获取用户"""

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
            'user_id': str(row[0]),
            'id': str(row[0]),
            'name': row[1] or '',
            'age': row[2] or random.randint(24, 35),
            'job': row[3] or '',
            'education': row[4] or '',
            'gender': '女',
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
            'user_id': str(row[0]),
            'id': str(row[0]),
            'name': row[1] or '',
            'age': row[2] or random.randint(26, 38),
            'job': row[3] or '',
            'education': row[4] or '',
            'gender': '男',
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
    print("✓ 已清除现有聊天记录")


def insert_chat_data(
    cursor,
    thread_id: str,
    female_id: str,
    male_id: str,
    messages: List[Dict],
    thread_status: str
) -> int:
    """插入聊天数据"""

    # 创建线程
    case_id = f"case-{uuid.uuid4().hex[:16]}"
    relation_key = f"relation-{female_id}-{male_id}"

    # 获取第一个女性消息的人设
    female_persona = '温柔内敛'
    for msg in messages:
        if msg['gender'] == '女':
            female_persona = msg.get('persona', '温柔内敛')
            break

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
            'created_by': 'system_personalized_v3',
            'female_persona': female_persona,
            'compatibility_score': random.randint(70, 98),
            'conversation_quality': random.choice(['高质量', '中等', '一般'])
        }),
        messages[0]['created_at'] if messages else datetime.now(),
        messages[-1]['created_at'] if messages else datetime.now()
    ))

    # 插入消息
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
            None,
            json.dumps({
                'phase': msg['phase'],
                'persona': msg['persona'],
                'conversation_turn': count + 1
            }),
            msg['created_at']
        ))
        count += 1

    return count


def generate_all_chat_records(
    target_messages: int = 100000,
    threads_per_female: Tuple[int, int] = (2, 4),  # 每个女性2-4个线程
    clear_existing: bool = True
) -> Dict:
    """生成所有聊天记录"""

    if clear_existing:
        clear_existing_chats()

    print("正在获取用户数据...")
    female_users, male_users = get_users_from_db()

    print(f"✓ 找到 {len(female_users)} 个无锡女性用户")
    print(f"✓ 找到 {len(male_users)} 个无锡男性用户")
    print()

    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute('USE her_chat')

    total_threads = 0
    total_messages = 0
    processed_females = 0

    # 统计人设分布
    persona_stats = {
        '年轻活泼': 0,
        '温柔内敛': 0,
        '成熟理性': 0,
        '职场精英': 0,
        '文艺浪漫': 0,
    }

    print("开始生成个性化聊天记录...")
    print("特点：根据用户真实属性生成独特风格的对话内容")
    print()

    for female in female_users:
        # 分析女性用户人设
        female_persona_data = PersonaAnalyzer.analyze_user(female)
        persona_stats[female_persona_data.persona_type] += 1

        # 为该女性创建 2-4 个聊天线程
        num_threads = random.randint(*threads_per_female)

        # 随机选择男性用户
        available_males = [m for m in male_users if m['id'] != female['id']]
        if len(available_males) < num_threads:
            num_threads = len(available_males)

        selected_males = random.sample(available_males, num_threads)

        for male in selected_males:
            # 分析男性用户人设
            male_persona_data = PersonaAnalyzer.analyze_user(male)

            # 创建对话生成器
            generator = RealisticConversationGenerator(female_persona_data, male_persona_data)

            # 生成对话（25-45 条消息）
            conv_length = random.randint(25, 45)
            messages, thread_status = generator.generate_full_conversation(conv_length)

            # 插入数据
            thread_id = f"thread-{uuid.uuid4().hex[:16]}"
            msg_count = insert_chat_data(cursor, thread_id, female['id'], male['id'], messages, thread_status)

            total_threads += 1
            total_messages += msg_count

            if total_messages >= target_messages:
                break

        processed_females += 1

        # 每50个用户提交并报告
        if processed_females % 50 == 0:
            conn.commit()
            print(f"[进度] 已处理 {processed_females}/{len(female_users)} 个女性用户")
            print(f"       创建 {total_threads} 个线程，{total_messages} 条消息")
            print(f"       人设分布: {persona_stats}")
            print()

        if total_messages >= target_messages:
            break

    conn.commit()
    cursor.close()
    conn.close()

    print("="*50)
    print("✓ 生成完成")
    print("="*50)

    return {
        'processed_females': processed_females,
        'total_threads': total_threads,
        'total_messages': total_messages,
        'persona_stats': persona_stats,
    }


def main():
    """主函数"""

    print("="*60)
    print("    聊天记录生成器 - 终极版")
    print("="*60)
    print()
    print("特点：")
    print("  ✓ 根据用户真实属性（年龄、职业）生成独特人设")
    print("  ✓ 每个用户的对话风格各异")
    print("  ✓ 包含无锡本地话题和真实生活细节")
    print("  ✓ 对话流程自然，有追问、共鸣、话题转换")
    print("  ✓ 防止重复，每条消息都独特")
    print()
    print("="*60)
    print()

    # 生成 100,000 条聊天记录
    stats = generate_all_chat_records(
        target_messages=100000,
        threads_per_female=(2, 4),
        clear_existing=True
    )

    print()
    print("="*60)
    print("    最终统计")
    print("="*60)
    print(f"处理女性用户数: {stats['processed_females']}")
    print(f"创建聊天线程数: {stats['total_threads']}")
    print(f"创建聊天消息数: {stats['total_messages']}")
    print()
    print("人设类型分布：")
    for persona_type, count in stats['persona_stats'].items():
        if count > 0:
            print(f"  {persona_type}: {count} 个用户")
    print("="*60)


if __name__ == '__main__':
    main()