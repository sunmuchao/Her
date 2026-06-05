"""OEJTS 1.2 (Open Extended Jungian Type Scales) 核心测评引擎

基于 Open Psychometrics 的 OEJTS 1.2 开发
- Cronbach's α = 0.84（信度极高）
- 复测一致性 = 0.89（效度极高）
- 48 题核心题库（每个维度 12 题）

题目已翻译为中文并改编为恋爱场景风格
"""

from __future__ import annotations

from typing import Any

# OEJTS 四个维度
DIMENSIONS = ["ei", "sn", "tf", "jp"]

DIMENSION_NAMES = {
    "ei": "外向 / 内向",
    "sn": "实感 / 直觉",
    "tf": "思考 / 情感",
    "jp": "判断 / 知觉",
}

# OEJTS 每个维度 12 题（共 48 题）
DIMENSION_QUESTION_COUNT = 12
TOTAL_QUESTIONS = 48

# 维度反馈阈值（基于 OEJTS 标准）
DIMENSION_THRESHOLDS = {
    "high": 70,    # 强倾向第一特质
    "medium": 40,  # 平衡
    "low": 40,     # 强倾向第二特质
}


def _build_oejts_questions() -> list[dict[str, Any]]:
    """构建 OEJTS 48 题恋爱场景题库

    基于 OEJTS 高区分度题目（区分度 > 0.7），翻译并改编为恋爱场景风格
    每个维度 12 题，优先选择高区分度题目

    题目来源：Open Psychometrics OEJTS 1.2
    - 区分度 > 1.05：橙红色标记（最高效题目）
    - 区分度 > 0.7：salmon 标记（高效题目）
    - 区分度 > 0.35：粉色标记（有效题目）
    """

    questions = []
    index = 0

    # ========== EI 维度（外向/内向）12 题 ==========
    # 高区分度题目：1.37E, 1.33E, 1.26I, 1.24I, 1.17I, 1.12E, 1.04E, 0.98I, 0.92I, 0.89I, 0.84T, 0.72E

    ei_questions = [
        # 1. 基于 OEJTS: "listens more; talks more" (1.37E) - 最高区分度
        {
            "index": index,
            "dimension": "ei",
            "text": "和Crush连麦聊天时，你更倾向于？",
            "options": [
                {"label": "A", "text": "滔滔不绝分享我的故事和想法，对方主要负责倾听", "score": 5},
                {"label": "B", "text": "我说的稍微多一点，但也会认真听对方说", "score": 4},
                {"label": "C", "text": "看情况，有时我多说有时对方多说", "score": 3},
                {"label": "D", "text": "更愿意听对方说，偶尔插几句", "score": 2},
                {"label": "E", "text": "安静听对方讲，主要用表情包和简短回复", "score": 1},
            ],
            "oejts_original": "listens more; talks more",
            "oejts_discrimination": 1.37,
        },

        # 2. 基于 OEJTS: "somber; enthusiastic" (1.33E)
        {
            "index": index,
            "dimension": "ei",
            "text": "Crush发消息说'今天心情不太好'，你的第一反应是？",
            "options": [
                {"label": "A", "text": "立刻回复一大串安慰话，外加语音通话邀请", "score": 5},
                {"label": "B", "text": "热情回复，问发生什么了，表达关心", "score": 4},
                {"label": "C", "text": "正常回复，问一下情况", "score": 3},
                {"label": "D", "text": "想一下怎么回复，简单表达关心", "score": 2},
                {"label": "E", "text": "静静思考一下，回复一句简短的安慰", "score": 1},
            ],
            "oejts_original": "somber; enthusiastic",
            "oejts_discrimination": 1.33,
        },

        # 3. 基于 OEJTS: "friendly; distant" (1.26I)
        {
            "index": index,
            "dimension": "ei",
            "text": "刚进入一个相亲群，群里气氛很活跃，你会？",
            "options": [
                {"label": "A", "text": "立刻打招呼，主动参与话题，成为群里的活跃分子", "score": 5},
                {"label": "B", "text": "礼貌打招呼，适度参与话题", "score": 4},
                {"label": "C", "text": "先观察一下，看有没有感兴趣的话题", "score": 3},
                {"label": "D", "text": "默默围观，偶尔回复一句", "score": 2},
                {"label": "E", "text": "全程潜水，等红娘单独介绍对象", "score": 1},
            ],
            "oejts_original": "friendly; distant",
            "oejts_discrimination": 1.26,
        },

        # 4. 基于 OEJTS: "energetic; mellow" (1.24I)
        {
            "index": index,
            "dimension": "ei",
            "text": "周末约会计划确定后，你的心情是？",
            "options": [
                {"label": "A", "text": "兴奋！开始规划穿搭、路线，主动提议多个备选方案", "score": 5},
                {"label": "B", "text": "挺期待，会提前准备一下", "score": 4},
                {"label": "C", "text": "正常，看对方安排就行", "score": 3},
                {"label": "D", "text": "平静，到时候直接去就行", "score": 2},
                {"label": "E", "text": "有点紧张，希望不要太复杂的活动", "score": 1},
            ],
            "oejts_original": "energetic; mellow",
            "oejts_discrimination": 1.24,
        },

        # 5. 基于 OEJTS: "enthusiastic; deliberate" (1.17I)
        {
            "index": index,
            "dimension": "ei",
            "text": "对象突然提议'我们下周去旅行吧'，你的反应是？",
            "options": [
                {"label": "A", "text": "太棒了！立刻开始搜索目的地和攻略", "score": 5},
                {"label": "B", "text": "好主意！先讨论去哪里", "score": 4},
                {"label": "C", "text": "可以考虑，看看时间安排", "score": 3},
                {"label": "D", "text": "先想一下可行性，再回复", "score": 2},
                {"label": "E", "text": "等等，我们需要先讨论一下时间和预算", "score": 1},
            ],
            "oejts_original": "enthusiastic; deliberate",
            "oejts_discrimination": 1.17,
        },

        # 6. 基于 OEJTS: "manipulates things behind the scenes; leads from the front" (1.12E)
        {
            "index": index,
            "dimension": "ei",
            "text": "想让对象做某件事（比如戒烟/运动），你会？",
            "options": [
                {"label": "A", "text": "直接说出来，一起讨论怎么执行", "score": 5},
                {"label": "B", "text": "提建议，说这样做的好处", "score": 4},
                {"label": "C", "text": "看情况，有时直接说有时暗示", "score": 3},
                {"label": "D", "text": "侧面引导，比如转发相关文章", "score": 2},
                {"label": "E", "text": "默默创造条件，让对方自己意识到", "score": 1},
            ],
            "oejts_original": "manipulates things behind the scenes; leads from the front",
            "oejts_discrimination": 1.12,
        },

        # 7. 基于 OEJTS: "cautious; bold" (1.04E)
        {
            "index": index,
            "dimension": "ei",
            "text": "第一次见Crush的朋友，你会？",
            "options": [
                {"label": "A", "text": "主动打招呼，很快融入话题", "score": 5},
                {"label": "B", "text": "礼貌介绍自己，积极参与话题", "score": 4},
                {"label": "C", "text": "正常社交，看朋友聊什么话题", "score": 3},
                {"label": "D", "text": "先观察，等对方朋友cue我", "score": 2},
                {"label": "E", "text": "紧张，希望Crush能帮我说几句", "score": 1},
            ],
            "oejts_original": "cautious; bold",
            "oejts_discrimination": 1.04,
        },

        # 8. 基于 OEJTS: "likes small talk; hates small talk" (0.98I)
        {
            "index": index,
            "dimension": "ei",
            "text": "约会刚开始的闲聊环节（天气/工作/周末），你觉得？",
            "options": [
                {"label": "A", "text": "挺好的，轻松话题能快速热场", "score": 5},
                {"label": "B", "text": "还行，先聊轻松话题再聊深度", "score": 4},
                {"label": "C", "text": "看情况，有时喜欢有时觉得浪费时间", "score": 3},
                {"label": "D", "text": "有点无聊，希望能快速进入有趣话题", "score": 2},
                {"label": "E", "text": "完全不想聊这些，希望能直接说点有意义的", "score": 1},
            ],
            "oejts_original": "likes small talk; hates small talk",
            "oejts_discrimination": 0.98,
        },

        # 9. 基于 OEJTS: "confident; unsure" (0.92I)
        {
            "index": index,
            "dimension": "ei",
            "text": "对象问你'你觉得我们合适吗'，你的反应是？",
            "options": [
                {"label": "A", "text": "当然合适！我们这么合拍", "score": 5},
                {"label": "B", "text": "我觉得挺合适的，你觉得呢？", "score": 4},
                {"label": "C", "text": "需要再相处看看", "score": 3},
                {"label": "D", "text": "嗯...我需要想一下", "score": 2},
                {"label": "E", "text": "突然不确定了，开始反思我们的问题", "score": 1},
            ],
            "oejts_original": "confident; unsure",
            "oejts_discrimination": 0.92,
        },

        # 10. 基于 OEJTS: "talks over a decision with other people; makes it alone" (0.89I)
        {
            "index": index,
            "dimension": "ei",
            "text": "要不要和Crush表白，你会？",
            "options": [
                {"label": "A", "text": "找闺蜜/兄弟讨论，听取多方意见", "score": 5},
                {"label": "B", "text": "和朋友聊一下，但主要还是自己决定", "score": 4},
                {"label": "C", "text": "看情况，有时问朋友有时自己想", "score": 3},
                {"label": "D", "text": "自己思考，偶尔和朋友提一下", "score": 2},
                {"label": "E", "text": "完全自己决定，不喜欢让别人知道", "score": 1},
            ],
            "oejts_original": "talks over a decision with other people; makes it alone",
            "oejts_discrimination": 0.89,
        },

        # 11. 基于 OEJTS: "like to listen to stories; likes to tell stories" (0.94E)
        {
            "index": index,
            "dimension": "ei",
            "text": "约会时的聊天模式，你更倾向于？",
            "options": [
                {"label": "A", "text": "我讲我的故事和经历，让对方了解我", "score": 5},
                {"label": "B", "text": "我讲的稍微多点，但也会问对方的故事", "score": 4},
                {"label": "C", "text": "轮流讲，互相分享", "score": 3},
                {"label": "D", "text": "更愿意听对方讲，偶尔补充几句", "score": 2},
                {"label": "E", "text": "安静听对方的故事，主要提问而不是分享", "score": 1},
            ],
            "oejts_original": "like to listen to stories; likes to tell stories",
            "oejts_discrimination": 0.94,
        },

        # 12. 基于 OEJTS: "has deep interests; has many interests" (0.72E)
        {
            "index": index,
            "dimension": "ei",
            "text": "你的兴趣爱好特点是？",
            "options": [
                {"label": "A", "text": "兴趣广泛，喜欢尝试各种新鲜事物", "score": 5},
                {"label": "B", "text": "有好几个兴趣，涉猎比较广", "score": 4},
                {"label": "C", "text": "有一些兴趣，不算多也不算少", "score": 3},
                {"label": "D", "text": "专注几个兴趣，投入比较深", "score": 2},
                {"label": "E", "text": "一两个核心兴趣，投入大量时间深入研究", "score": 1},
            ],
            "oejts_original": "has deep interests; has many interests",
            "oejts_discrimination": 0.72,
        },
    ]

    # ========== SN 维度（实感/直觉）12 题 ==========
    # 高区分度题目：0.75N, 0.72N, 0.73N, 0.63N, 0.61S, 0.52N, etc.

    sn_questions = [
        # 1. 基于 OEJTS: "interested in realities; interested in possibilities" (0.75N)
        {
            "index": index,
            "dimension": "sn",
            "text": "聊未来的生活规划，你更关注？",
            "options": [
                {"label": "A", "text": "具体的计划：什么时候买房、职业发展路径、实际可行性", "score": 5},
                {"label": "B", "text": "实际目标为主，也会想一些可能性", "score": 4},
                {"label": "C", "text": "既看具体计划也看未来发展空间", "score": 3},
                {"label": "D", "text": "未来的可能性：可能会怎样、理想的生活状态", "score": 2},
                {"label": "E", "text": "天马行空的想象：多种可能性、创意的生活方式", "score": 1},
            ],
            "oejts_original": "interested in realities; interested in possibilities",
            "oejts_discrimination": 0.75,
        },

        # 2. 基于 OEJTS: "focused on the present; focused on the future" (0.72N)
        {
            "index": index,
            "dimension": "sn",
            "text": "约会时，你更关注？",
            "options": [
                {"label": "A", "text": "当下的体验：现在的氛围、细节、感受、具体发生的事", "score": 5},
                {"label": "B", "text": "当前体验为主，也会想这次约会对未来关系的影响", "score": 4},
                {"label": "C", "text": "既享受当下也思考未来", "score": 3},
                {"label": "D", "text": "未来的发展：这次约会意味着什么、后续怎么发展", "score": 2},
                {"label": "E", "text": "长远想象：如果在一起会怎样、各种未来场景", "score": 1},
            ],
            "oejts_original": "focused on the present; focused on the future",
            "oejts_discrimination": 0.72,
        },

        # 3. 基于 OEJTS: "realistic; imaginative" (0.63N)
        {
            "index": index,
            "dimension": "sn",
            "text": "对象说'以后我们开个咖啡馆吧'，你的反应是？",
            "options": [
                {"label": "A", "text": "分析可行性：资金、选址、风险、市场竞争", "score": 5},
                {"label": "B", "text": "先想实际问题，再畅想一下", "score": 4},
                {"label": "C", "text": "既考虑现实也想象美好场景", "score": 3},
                {"label": "D", "text": "畅想咖啡馆的样子：装修风格、氛围、客群", "score": 2},
                {"label": "E", "text": "天马行空想象：各种创意概念、独特体验、未来连锁", "score": 1},
            ],
            "oejts_original": "realistic; imaginative",
            "oejts_discrimination": 0.63,
        },

        # 4. 基于 OEJTS: "likes knowing all the facts; likes filling in the blanks" (0.52N)
        {
            "index": index,
            "dimension": "sn",
            "text": "了解Crush的过去，你更想知道？",
            "options": [
                {"label": "A", "text": "具体事实：谈过几次恋爱、为什么分手、现任情况", "score": 5},
                {"label": "B", "text": "事实为主，也会推测一些细节", "score": 4},
                {"label": "C", "text": "既问事实也推测可能性", "score": 3},
                {"label": "D", "text": "大致了解事实，更喜欢推测TA的性格特点", "score": 2},
                {"label": "E", "text": "不想问太多细节，喜欢观察推测TA的真实想法", "score": 1},
            ],
            "oejts_original": "likes knowing all the facts; likes filling in the blanks",
            "oejts_discrimination": 0.52,
        },

        # 5. 基于 OEJTS: "focuses on the big picture; takes care of the little details" (0.61S)
        {
            "index": index,
            "dimension": "sn",
            "text": "安排约会行程，你更关注？",
            "options": [
                {"label": "A", "text": "大方向：去哪个区域、主要活动类型、整体氛围", "score": 5},
                {"label": "B", "text": "大概框架为主，细节到时看情况", "score": 4},
                {"label": "C", "text": "既考虑大方向也注意细节", "score": 3},
                {"label": "D", "text": "具体细节：餐厅评价、路线、天气、时间节点", "score": 2},
                {"label": "E", "text": "非常细节：备选方案、紧急预案、每一站的时间安排", "score": 1},
            ],
            "oejts_original": "focuses on the big picture; takes care of the little details",
            "oejts_discrimination": 0.61,
        },

        # 6. 基于 OEJTS: "interested in realities; interested in possibilities" (0.42P)
        {
            "index": index,
            "dimension": "sn",
            "text": "对象抱怨工作，你更倾向于？",
            "options": [
                {"label": "A", "text": "了解具体情况：什么问题、谁的问题、怎么解决", "score": 5},
                {"label": "B", "text": "先听事实，再给一些思路", "score": 4},
                {"label": "C", "text": "既听事实也帮TA分析可能性", "score": 3},
                {"label": "D", "text": "帮TA想象各种可能性：跳槽、转行、创业", "score": 2},
                {"label": "E", "text": "天马行空畅想：完全不同的职业道路、人生可能性", "score": 1},
            ],
            "oejts_original": "interested in realities; interested in possibilities",
            "oejts_discrimination": 0.42,
        },

        # 7. 基于 OEJTS: "concrete; abstract" (0.73N)
        {
            "index": index,
            "dimension": "sn",
            "text": "聊到'理想的爱情'，你会怎么描述？",
            "options": [
                {"label": "A", "text": "具体场景：一起做饭、周末散步、互相照顾的日常", "score": 5},
                {"label": "B", "text": "具体为主，偶尔会说一些理想化的描述", "score": 4},
                {"label": "C", "text": "既有具体画面也有抽象理念", "score": 3},
                {"label": "D", "text": "抽象理念：互相理解、灵魂契合、共同成长", "score": 2},
                {"label": "E", "text": "高度抽象：命运的安排、宇宙的连接、精神共鸣", "score": 1},
            ],
            "oejts_original": "concrete; abstract",
            "oejts_discrimination": 0.73,
        },

        # 8. 基于 OEJTS: "practical; conceptual" (0.61S)
        {
            "index": index,
            "dimension": "sn",
            "text": "对象说'我想改变一下我们的关系模式'，你会？",
            "options": [
                {"label": "A", "text": "先问具体怎么改，有哪些实际的调整方案", "score": 5},
                {"label": "B", "text": "了解具体想法，再看可行性", "score": 4},
                {"label": "C", "text": "既问具体细节也理解背后的理念", "score": 3},
                {"label": "D", "text": "思考TA为什么会有这种想法，背后的理念是什么", "score": 2},
                {"label": "E", "text": "从概念层面思考关系的本质和可能性", "score": 1},
            ],
            "oejts_original": "practical; conceptual",
            "oejts_discrimination": 0.61,
        },

        # 9. 基于 OEJTS: "trusts experience; trusts inspiration" (0.69N)
        {
            "index": index,
            "dimension": "sn",
            "text": "判断一个人是否值得交往，你更相信？",
            "options": [
                {"label": "A", "text": "过去的经验：这类人我遇到过，知道靠不靠谱", "score": 5},
                {"label": "B", "text": "经验为主，偶尔也会凭直觉", "score": 4},
                {"label": "C", "text": "经验和直觉并重", "score": 3},
                {"label": "D", "text": "直觉感觉：第一次见面就有感觉，说不清为什么", "score": 2},
                {"label": "E", "text": "强烈的灵感：就是知道TA是对的人，不用理性分析", "score": 1},
            ],
            "oejts_original": "trusts experience; trusts inspiration",
            "oejts_discrimination": 0.69,
        },

        # 10. 基于 OEJTS: "step by step; leaps" (0.58N)
        {
            "index": index,
            "dimension": "sn",
            "text": "关系发展中，你更倾向哪种方式？",
            "options": [
                {"label": "A", "text": "循序渐进：先聊天、再见面、慢慢了解、逐步深入", "score": 5},
                {"label": "B", "text": "一步一步来，偶尔会有跳跃式的进展", "score": 4},
                {"label": "C", "text": "既有稳定的节奏也会有突然的进展", "score": 3},
                {"label": "D", "text": "跳跃式：突然发现很投缘，很快进入深度交流", "score": 2},
                {"label": "E", "text": "完全凭感觉：可能第一次见面就觉得是一辈子的缘分", "score": 1},
            ],
            "oejts_original": "step by step; leaps",
            "oejts_discrimination": 0.58,
        },

        # 11. 基于 OEJTS: "standard; unusual" (0.54N)
        {
            "index": index,
            "dimension": "sn",
            "text": "你更倾向找什么样的对象？",
            "options": [
                {"label": "A", "text": "主流标准：稳定工作、家庭背景合适、性格靠谱", "score": 5},
                {"label": "B", "text": "主流为主，但也要有点特别的地方", "score": 4},
                {"label": "C", "text": "既看重基本条件也欣赏独特性", "score": 3},
                {"label": "D", "text": "有点特别：不按常理出牌、思维独特、生活方式不一样", "score": 2},
                {"label": "E", "text": "非常独特：完全不同于主流，有自己的精神世界", "score": 1},
            ],
            "oejts_original": "standard; unusual",
            "oejts_discrimination": 0.54,
        },

        # 12. 基于 OEJTS: "works with things; works with ideas" (0.47N)
        {
            "index": index,
            "dimension": "sn",
            "text": "约会活动选择，你更喜欢？",
            "options": [
                {"label": "A", "text": "具体活动：一起做饭、运动、手工、逛展览、看电影", "score": 5},
                {"label": "B", "text": "具体活动为主，偶尔聊深度话题", "score": 4},
                {"label": "C", "text": "具体活动和深度交流都喜欢", "score": 3},
                {"label": "D", "text": "深度交流：找个地方聊人生、聊理念、聊未来", "score": 2},
                {"label": "E", "text": "纯粹的思想碰撞：哲学讨论、精神探索、灵魂对话", "score": 1},
            ],
            "oejts_original": "works with things; works with ideas",
            "oejts_discrimination": 0.47,
        },
    ]

    # ========== TF 维度（思考/情感）12 题 ==========
    # 高区分度题目：1.17F, 1.18F, 0.84T, 0.71F, etc.

    tf_questions = [
        # 1. 基于 OEJTS: "uses reason; uses instinct" (1.17F) - 高区分度
        {
            "index": index,
            "dimension": "tf",
            "text": "选择伴侣时，你更看重？",
            "options": [
                {"label": "A", "text": "理性分析：条件匹配、价值观一致、长期可行性、现实因素", "score": 5},
                {"label": "B", "text": "理性为主，也会考虑感觉和心动", "score": 4},
                {"label": "C", "text": "理性分析和心动感觉并重", "score": 3},
                {"label": "D", "text": "直觉和感觉：心动的感觉、化学反应、眼缘", "score": 2},
                {"label": "E", "text": "完全凭感觉：一定要有强烈的心动和眼缘", "score": 1},
            ],
            "oejts_original": "uses reason; uses instinct",
            "oejts_discrimination": 1.17,
        },

        # 2. 基于 OEJTS: "when judging others, considers intent; only considers outcome" (0.64T)
        {
            "index": index,
            "dimension": "tf",
            "text": "对象做了一件让你不舒服的事，你更倾向于？",
            "options": [
                {"label": "A", "text": "先问TA为什么这样做，了解TA的动机和想法", "score": 5},
                {"label": "B", "text": "先了解动机，再判断行为是否合理", "score": 4},
                {"label": "C", "text": "既考虑动机也看结果影响", "score": 3},
                {"label": "D", "text": "主要看这件事对我的实际影响", "score": 2},
                {"label": "E", "text": "不管动机是什么，结果让我不舒服就是问题", "score": 1},
            ],
            "oejts_original": "when judging others, considers intent; only considers outcome",
            "oejts_discrimination": 0.64,
        },

        # 3. 基于 OEJTS: "criticism leads to feelings of guilt; criticism leads to feelings of anger" (0.56T)
        {
            "index": index,
            "dimension": "tf",
            "text": "对象批评你的某个行为，你的第一反应是？",
            "options": [
                {"label": "A", "text": "内疚反思：是不是我做得不好？TA说得有道理吗？", "score": 5},
                {"label": "B", "text": "先反思自己，再想TA的批评是否客观", "score": 4},
                {"label": "C", "text": "既反思自己也分析TA的批评逻辑", "score": 3},
                {"label": "D", "text": "有点不爽：TA凭什么这么说我？", "score": 2},
                {"label": "E", "text": "生气反驳：TA的批评不合理，我要解释清楚", "score": 1},
            ],
            "oejts_original": "criticism leads to feelings of guilt; criticism leads to feelings of anger",
            "oejts_discrimination": 0.56,
        },

        # 4. 基于 OEJTS: "cares if something is good or bad; cares if something is true or false" (0.67T)
        {
            "index": index,
            "dimension": "tf",
            "text": "对象分享一个观点（比如'婚姻应该是...'), 你更关注？",
            "options": [
                {"label": "A", "text": "这个观点是否符合事实、逻辑是否成立", "score": 5},
                {"label": "B", "text": "先看观点是否合理，再想TA为什么这么想", "score": 4},
                {"label": "C", "text": "既看观点合理性也关注TA的感受", "score": 3},
                {"label": "D", "text": "TA为什么会有这种想法，背后的感受是什么", "score": 2},
                {"label": "E", "text": "TA表达这个观点时的情绪和需求，这才是重点", "score": 1},
            ],
            "oejts_original": "cares if something is good or bad; cares if something is true or false",
            "oejts_discrimination": 0.67,
        },

        # 5. 基于 OEJTS: "feels others' emotions; thinks about others' emotions" (1.18F) - 高区分度
        {
            "index": index,
            "dimension": "tf",
            "text": "对象说'我今天工作好累'，你的反应是？",
            "options": [
                {"label": "A", "text": "共情感受：辛苦了，抱抱，发生什么了？", "score": 5},
                {"label": "B", "text": "先表达关心，再问具体情况", "score": 4},
                {"label": "C", "text": "既表达关心也了解情况", "score": 3},
                {"label": "D", "text": "问清楚原因：为什么累？是工作量大还是人际关系？", "score": 2},
                {"label": "E", "text": "分析问题：工作累可以怎么解决，要不要考虑换工作", "score": 1},
            ],
            "oejts_original": "feels others' emotions; thinks about others' emotions",
            "oejts_discrimination": 1.18,
        },

        # 6. 基于 OEJTS: "values harmony; values truth" (0.84T)
        {
            "index": index,
            "dimension": "tf",
            "text": "对象说了一个你不认同的观点，你会？",
            "options": [
                {"label": "A", "text": "直接说出我的不同看法，真理越辩越明", "score": 5},
                {"label": "B", "text": "表达不同观点，但注意措辞", "score": 4},
                {"label": "C", "text": "看情况，有时会说有时会保留意见", "score": 3},
                {"label": "D", "text": "委婉表达，避免直接冲突", "score": 2},
                {"label": "E", "text": "不想破坏氛围，还是顺着TA说吧", "score": 1},
            ],
            "oejts_original": "values harmony; values truth",
            "oejts_discrimination": 0.84,
        },

        # 7. 基于 OEJTS: "merciful; just" (0.71F)
        {
            "index": index,
            "dimension": "tf",
            "text": "对象犯了一个明显的错误（比如记错纪念日），你会？",
            "options": [
                {"label": "A", "text": "理解TA，谁都会犯错，不放心上", "score": 5},
                {"label": "B", "text": "原谅TA，但会表达这件事对我很重要", "score": 4},
                {"label": "C", "text": "既理解TA也说明这件事的重要性", "score": 3},
                {"label": "D", "text": "指出这个问题，希望TA能记住", "score": 2},
                {"label": "E", "text": "这是原则问题，必须认真讨论怎么避免", "score": 1},
            ],
            "oejts_original": "merciful; just",
            "oejts_discrimination": 0.71,
        },

        # 8. 基于 OEJTS: "prefers to keep the peace; prefers to resolve issues" (0.67T)
        {
            "index": index,
            "dimension": "tf",
            "text": "两人有分歧时，你更倾向于？",
            "options": [
                {"label": "A", "text": "彻底讨论清楚，找出问题根源和解决方案", "score": 5},
                {"label": "B", "text": "讨论问题，但注意方式和语气", "score": 4},
                {"label": "C", "text": "看情况，有时讨论有时先放下", "score": 3},
                {"label": "D", "text": "先缓和气氛，等情绪过去了再说", "score": 2},
                {"label": "E", "text": "不想争执，各退一步维持和谐", "score": 1},
            ],
            "oejts_original": "prefers to keep the peace; prefers to resolve issues",
            "oejts_discrimination": 0.67,
        },

        # 9. 基于 OEJTS: "accepts things as they are; wants to change things" (0.62T)
        {
            "index": index,
            "dimension": "tf",
            "text": "看到对象有一些你不喜欢的习惯，你会？",
            "options": [
                {"label": "A", "text": "提出改进建议，希望TA能调整", "score": 5},
                {"label": "B", "text": "委婉表达，看看TA愿不愿意改", "score": 4},
                {"label": "C", "text": "看情况，有些会提有些自己消化", "score": 3},
                {"label": "D", "text": "试着理解TA，习惯很难改", "score": 2},
                {"label": "E", "text": "接受TA本来的样子，爱就要包容", "score": 1},
            ],
            "oejts_original": "accepts things as they are; wants to change things",
            "oejts_discrimination": 0.62,
        },

        # 10. 基于 OEJTS: "thinks through decisions; feels through decisions" (0.59F)
        {
            "index": index,
            "dimension": "tf",
            "text": "决定是否和这个人在一起，你更看重？",
            "options": [
                {"label": "A", "text": "整体感觉和心动：有感觉比什么都重要", "score": 5},
                {"label": "B", "text": "感觉为主，也会考虑现实因素", "score": 4},
                {"label": "C", "text": "感觉和现实因素都重要", "score": 3},
                {"label": "D", "text": "现实因素为主，感觉可以培养", "score": 2},
                {"label": "E", "text": "理性分析：条件匹配度、价值观一致性、长期可行性", "score": 1},
            ],
            "oejts_original": "thinks through decisions; feels through decisions",
            "oejts_discrimination": 0.59,
        },

        # 11. 基于 OEJTS: "hard-hearted; soft-hearted" (0.71F)
        {
            "index": index,
            "dimension": "tf",
            "text": "前任回头找你复合，但当初是TA提的分手，你会？",
            "options": [
                {"label": "A", "text": "坚决拒绝，当初为什么分手现在还是会分手", "score": 5},
                {"label": "B", "text": "理性分析，看当初分手的原因是否解决了", "score": 4},
                {"label": "C", "text": "犹豫不决，既看理性也看感情", "score": 3},
                {"label": "D", "text": "心里会软，想给TA一个机会", "score": 2},
                {"label": "E", "text": "容易心软，毕竟曾经有感情，想再试试", "score": 1},
            ],
            "oejts_original": "hard-hearted; soft-hearted",
            "oejts_discrimination": 0.71,
        },

        # 12. 基于 OEJTS: "objective; subjective" (0.55T)
        {
            "index": index,
            "dimension": "tf",
            "text": "朋友说你的对象可能不太适合你，你会？",
            "options": [
                {"label": "A", "text": "认真听取，客观分析朋友的观察是否准确", "score": 5},
                {"label": "B", "text": "听朋友怎么说，但自己判断", "score": 4},
                {"label": "C", "text": "既考虑朋友意见也相信自己的感受", "score": 3},
                {"label": "D", "text": "我知道朋友是为我好，但感情是我自己的事", "score": 2},
                {"label": "E", "text": "感情是主观的，我相信自己的感觉和判断", "score": 1},
            ],
            "oejts_original": "objective; subjective",
            "oejts_discrimination": 0.55,
        },
    ]

    # ========== JP 维度（判断/知觉）12 题 ==========

    jp_questions = [
        # 1. 基于 OEJTS: "prepares; improvises" (1.43P) - 最高区分度题目！
        {
            "index": index,
            "dimension": "jp",
            "text": "约会前一天，你会？",
            "options": [
                {"label": "A", "text": "提前规划路线、备选方案、查天气、确认时间，安排妥当", "score": 5},
                {"label": "B", "text": "大致规划一下，留点弹性空间", "score": 4},
                {"label": "C", "text": "简单计划一下，到时看情况调整", "score": 3},
                {"label": "D", "text": "不想太死板，到时候随机应变，看心情", "score": 2},
                {"label": "E", "text": "完全随性，想到哪就去哪，不喜欢计划", "score": 1},
            ],
            "oejts_original": "prepares; improvises",
            "oejts_discrimination": 1.43,
        },

        # 2. 基于 OEJTS: "organized; chaotic" (1.15P) - 高区分度
        {
            "index": index,
            "dimension": "jp",
            "text": "你的微信聊天习惯是？",
            "options": [
                {"label": "A", "text": "消息及时回复，重要信息置顶或收藏，定期清理", "score": 5},
                {"label": "B", "text": "大部分消息及时回复，偶尔会忘记", "score": 4},
                {"label": "C", "text": "看情况回复，有时快有时慢", "score": 3},
                {"label": "D", "text": "经常忘记回复，消息堆积很多", "score": 2},
                {"label": "E", "text": "消息很乱，经常找不到重要对话，想起来才回复", "score": 1},
            ],
            "oejts_original": "organized; chaotic",
            "oejts_discrimination": 1.15,
        },

        # 3. 基于 OEJTS: "commits; keeps options open" (0.87P)
        {
            "index": index,
            "dimension": "jp",
            "text": "对象问'这周末确定要约会吗'，你的反应是？",
            "options": [
                {"label": "A", "text": "当然确定！我会提前安排好时间", "score": 5},
                {"label": "B", "text": "确定，但会留一点调整空间以防万一", "score": 4},
                {"label": "C", "text": "基本确定，到时看有没有突发情况", "score": 3},
                {"label": "D", "text": "先答应，但可能临时有变化", "score": 2},
                {"label": "E", "text": "不想太早确定，到时看心情和状态", "score": 1},
            ],
            "oejts_original": "commits; keeps options open",
            "oejts_discrimination": 0.87,
        },

        # 4. 基于 OEJTS: "sticks to the plan; adapts the plan on the fly" (0.49E)
        {
            "index": index,
            "dimension": "jp",
            "text": "约会当天突然下雨，原计划的户外活动取消，你会？",
            "options": [
                {"label": "A", "text": "按备选方案执行，早就想好室内替代活动", "score": 5},
                {"label": "B", "text": "快速调整到室内活动，尽量保持原定节奏", "score": 4},
                {"label": "C", "text": "和对象商量换个活动，灵活处理", "score": 3},
                {"label": "D", "text": "临时找个室内地方，随性换个计划", "score": 2},
                {"label": "E", "text": "干脆改期或者就在家躺平，反正不想折腾", "score": 1},
            ],
            "oejts_original": "sticks to the plan; adapts the plan on the fly",
            "oejts_discrimination": 0.49,
        },

        # 5. 基于 OEJTS: "prefers structure; prefers flexibility" (0.92P)
        {
            "index": index,
            "dimension": "jp",
            "text": "对于周末约会，你更倾向于？",
            "options": [
                {"label": "A", "text": "提前几天确定具体时间和安排，心里有数", "score": 5},
                {"label": "B", "text": "大致确定时间，具体安排到时再说", "score": 4},
                {"label": "C", "text": "看情况，有时提前确定有时临时决定", "score": 3},
                {"label": "D", "text": "当天早上再决定做什么，不想太早规划", "score": 2},
                {"label": "E", "text": "随性一点，到时候看心情决定", "score": 1},
            ],
            "oejts_original": "prefers structure; prefers flexibility",
            "oejts_discrimination": 0.92,
        },

        # 6. 基于 OEJTS: "schedules; goes with the flow" (0.88P)
        {
            "index": index,
            "dimension": "jp",
            "text": "两人一起旅行，你更喜欢哪种方式？",
            "options": [
                {"label": "A", "text": "详细的行程表：每天去哪、吃什么、住哪都规划好",                "score": 5},
                {"label": "B", "text": "大致行程框架，留一些弹性时间", "score": 4},
                {"label": "C", "text": "有基本安排，但可以灵活调整", "score": 3},
                {"label": "D", "text": "只有大致方向，到时随性探索", "score": 2},
                {"label": "E", "text": "完全随性，走到哪算哪，不喜欢被计划束缚", "score": 1},
            ],
            "oejts_original": "schedules; goes with the flow",
            "oejts_discrimination": 0.88,
        },

        # 7. 基于 OEJTS: "makes decisions quickly; deliberates" (0.76J)
        {
            "index": index,
            "dimension": "jp",
            "text": "选择约会餐厅，你会？",
            "options": [
                {"label": "A", "text": "快速决定，选一个评分不错的就去了", "score": 5},
                {"label": "B", "text": "看几家对比一下，选最合适的", "score": 4},
                {"label": "C", "text": "会考虑一会儿，但不会拖太久", "score": 3},
                {"label": "D", "text": "比较纠结，想多看几家", "score": 2},
                {"label": "E", "text": "很难决定，经常让对象来选", "score": 1},
            ],
            "oejts_original": "makes decisions quickly; deliberates",
            "oejts_discrimination": 0.76,
        },

        # 8. 基于 OEJTS: "follows through; distracted" (0.71P)
        {
            "index": index,
            "dimension": "jp",
            "text": "你计划学习一项新技能（比如学做菜），通常会？",
            "options": [
                {"label": "A", "text": "按计划执行，坚持到学会为止", "score": 5},
                {"label": "B", "text": "大部分能坚持，偶尔会断断续续", "score": 4},
                {"label": "C", "text": "看情况，有时坚持有时放弃", "score": 3},
                {"label": "D", "text": "经常被其他事情吸引，学学停停", "score": 2},
                {"label": "E", "text": "很容易被新的兴趣吸引，难以坚持到底", "score": 1},
            ],
            "oejts_original": "follows through; distracted",
            "oejts_discrimination": 0.71,
        },

        # 9. 基于 OEJTS: "works first; plays first" (0.68J)
        {
            "index": index,
            "dimension": "jp",
            "text": "周末有工作任务和约会，你会？",
            "options": [
                {"label": "A", "text": "先完成工作，再安心约会", "score": 5},
                {"label": "B", "text": "优先处理工作，但也会安排约会时间", "score": 4},
                {"label": "C", "text": "看情况平衡，尽量两者兼顾", "score": 3},
                {"label": "D", "text": "先约会放松，晚上回来处理工作", "score": 2},
                {"label": "E", "text": "想先享受周末，工作的事情之后再想", "score": 1},
            ],
            "oejts_original": "works first; plays first",
            "oejts_discrimination": 0.68,
        },

        # 10. 基于 OEJTS: "finishes things; leaves things unfinished" (0.65P)
        {
            "index": index,
            "dimension": "jp",
            "text": "关于'未完成的感情'（比如暧昧过但没确定的关系），你会？",
            "options": [
                {"label": "A", "text": "会主动推进关系，要么确定要么放下", "score": 5},
                {"label": "B", "text": "倾向于明确关系，但也会等待时机", "score": 4},
                {"label": "C", "text": "看情况，有时主动有时被动", "score": 3},
                {"label": "D", "text": "不太急着确定，维持现状也行", "score": 2},
                {"label": "E", "text": "经常保持模糊状态，不太想明确", "score": 1},
            ],
            "oejts_original": "finishes things; leaves things unfinished",
            "oejts_discrimination": 0.65,
        },

        # 11. 基于 OEJTS: "makes lists; avoids lists" (0.59P)
        {
            "index": index,
            "dimension": "jp",
            "text": "关于'理想伴侣清单'（列出你想要的条件），你的态度是？",
            "options": [
                {"label": "A", "text": "有清晰的清单，会对照条件筛选", "score": 5},
                {"label": "B", "text": "有一些基本标准，但不会太严格", "score": 4},
                {"label": "C", "text": "有几条底线，其他看感觉", "score": 3},
                {"label": "D", "text": "不喜欢列清单，感觉对了就行", "score": 2},
                {"label": "E", "text": "完全不信这些，每段感情都是独特的", "score": 1},
            ],
            "oejts_original": "makes lists; avoids lists",
            "oejts_discrimination": 0.59,
        },

        # 12. 基于 OEJTS: "methodical; spontaneous" (0.54P)
        {
            "index": index,
            "dimension": "jp",
            "text": "约会时的风格，你更像哪种？",
            "options": [
                {"label": "A", "text": "有条理：提前准备话题、安排路线、考虑细节", "score": 5},
                {"label": "B", "text": "有一些准备，但不会太刻意", "score": 4},
                {"label": "C", "text": "看情况，有时准备有时随性", "score": 3},
                {"label": "D", "text": "不太准备，到时候看感觉聊什么", "score": 2},
                {"label": "E", "text": "完全随性，最讨厌刻意准备，想说什么说什么", "score": 1},
            ],
            "oejts_original": "methodical; spontaneous",
            "oejts_discrimination": 0.54,
        },
    ]

    # 合并所有题目
    questions = ei_questions + sn_questions + tf_questions + jp_questions

    # 为每个题目设置正确的 index
    for i, question in enumerate(questions):
        question["index"] = i

    return questions


# 构建题库
OEJTS_QUESTIONS = _build_oejts_questions()


def calculate_dimension_score(answers: list[int], dimension: str) -> float:
    """计算单个维度的得分（OEJTS 标准算法）

    Args:
        answers: 答案列表（48个答案，每个答案为选项分数 1-5）
        dimension: 维度代码（ei/sn/tf/jp）

    Returns:
        维度得分（0-100），高分表示第一特质倾向，低分表示第二特质倾向
        例如：ei维度，高分表示外向(E)倾向，低分表示内向(I)倾向
    """
    # 获取该维度的题目范围
    dimension_start = DIMENSIONS.index(dimension) * DIMENSION_QUESTION_COUNT
    dimension_end = dimension_start + DIMENSION_QUESTION_COUNT

    # 获取该维度的答案
    dimension_answers = answers[dimension_start:dimension_end]

    # 计算总分
    total = sum(dimension_answers)

    # OEJTS 标准化公式：
    # - 每题分数范围：1-5（共12题）
    # - 总分范围：12-60
    # - 中位数：36（平衡状态）
    # - 转换为 0-100 分制
    # - 36分 → 50（平衡），60分 → 100（第一特质），12分 → 0（第二特质）

    score = (total - 36) / (60 - 36) * 50 + 50
    # 简化为：score = (total - 36) / 24 * 50 + 50
    # 或：score = (total - 12) / 48 * 100

    return round(score, 1)


def calculate_all_scores(answers: list[int]) -> dict[str, float]:
    """计算所有四个维度的得分

    Args:
        answers: 答案列表（48个答案）

    Returns:
        四个维度的得分字典，如 {"ei": 65.2, "sn": 40.5, "tf": 72.3, "jp": 35.8}
    """
    if len(answers) != TOTAL_QUESTIONS:
        raise ValueError(f"答案数量必须为 {TOTAL_QUESTIONS}，当前为 {len(answers)}")

    scores = {}
    for dimension in DIMENSIONS:
        scores[dimension] = calculate_dimension_score(answers, dimension)

    return scores


def get_type_code(scores: dict[str, float]) -> str:
    """根据四个维度得分判定 MBTI 类型代码

    Args:
        scores: 四个维度得分

    Returns:
        MBTI 类型代码（如 "ENFP", "INTJ"）
    """
    return "".join([
        "E" if scores.get("ei", 50) >= 50 else "I",
        "S" if scores.get("sn", 50) >= 50 else "N",
        "T" if scores.get("tf", 50) >= 50 else "F",
        "J" if scores.get("jp", 50) >= 50 else "P",
    ])


def get_question(index: int) -> dict[str, Any]:
    """获取指定索引的题目

    Args:
        index: 题目索引（0-47）

    Returns:
        题目数据
    """
    if index < 0 or index >= TOTAL_QUESTIONS:
        raise ValueError(f"题目索引必须在 0-{TOTAL_QUESTIONS-1} 范围内")

    return OEJTS_QUESTIONS[index]


def get_dimension_feedback(dimension: str, score: float) -> str:
    """获取维度反馈文本

    Args:
        dimension: 维度代码
        score: 维度得分

    Returns:
        维度反馈文本
    """
    # 基于 OEJTS 标准的反馈
    feedbacks = {
        "ei": {
            "high": "你更偏外向，倾向从互动和表达里获取能量。",
            "medium": "你能在独处和社交之间切换，比较灵活。",
            "low": "你更偏内向，通常喜欢安静和深入交流。",
        },
        "sn": {
            "high": "你更关注现实细节和可落地的信息。",
            "medium": "你会在具体事实和灵感想法之间平衡。",
            "low": "你更偏直觉，习惯先看趋势和可能性。",
        },
        "tf": {
            "high": "你更习惯用逻辑和标准来做判断。",
            "medium": "你会兼顾逻辑和感受，判断比较平衡。",
            "low": "你更看重关系感受和人的处境。",
        },
        "jp": {
            "high": "你更偏计划和确定性，喜欢把事情安排清楚。",
            "medium": "你能在计划和弹性之间保持平衡。",
            "low": "你更偏灵活开放，喜欢留有余地。",
        },
    }

    level = "high" if score >= DIMENSION_THRESHOLDS["high"] else "low" if score < DIMENSION_THRESHOLDS["low"] else "medium"
    return feedbacks.get(dimension, {}).get(level, "")


# 导出常量和函数
__all__ = [
    "DIMENSIONS",
    "DIMENSION_NAMES",
    "DIMENSION_QUESTION_COUNT",
    "TOTAL_QUESTIONS",
    "OEJTS_QUESTIONS",
    "calculate_dimension_score",
    "calculate_all_scores",
    "get_type_code",
    "get_question",
    "get_dimension_feedback",
]