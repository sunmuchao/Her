"""依恋风格测验题库（12题精简版）

依恋理论：Bowlby (1969), Hazan & Shaver (1987)
四种依恋类型：
- 安全型 (secure)：情绪稳定，能平衡亲密和独立
- 焦虑型 (anxious)：黏人，需要很多安全感，怕被抛弃
- 回避型 (avoidant)：冷暴力大师，需要很多空间，怕被黏
- 恐惧型 (fearful)：矛盾纠结体，既想黏又怕被伤害

设计理念：
- 恋爱场景化题目（不说学术话）
- 口语化网感表达（接地气）
- 极端标签机制（趣味化）
- 小雅专属回复（区别于卡片内容）
"""

from __future__ import annotations

from typing import Any

# 四种依恋类型（SBTI 风格标签）
ATTACHMENT_TYPES = ["secure", "anxious", "avoidant", "fearful"]

ATTACHMENT_TYPE_NAMES = {
    "secure": "稳如老狗（STBL）",
    "anxious": "赛博怨妇（ANX-S）",
    "avoidant": "装死大师（FAKE-D）",
    "fearful": "反复横跳狂魔（WOC-F）",
}

# 每个类型的题目范围（每类型3题）
ATTACHMENT_QUESTION_RANGES = {
    "secure": (0, 3),      # 第1-3题测安全型倾向
    "anxious": (3, 6),     # 第4-6题测焦虑型倾向
    "avoidant": (6, 9),    # 第7-9题测回避型倾向
    "fearful": (9, 12),    # 第10-12题测恐惧型倾向
}

# 维度反馈文案（SBTI 毒舌风格版本）
ATTACHMENT_FEEDBACKS = {
    "secure": {
        "high": "稳如老狗认证。对象发疯你睡觉，主打一个无动于衷。情绪灭火器，谁遇到你都很幸运——但也别太稳定显得没心没肺。",
        "medium": "基本稳定，但偶尔也会有点黏或有点冷，看情况。别太稳定显得没心没肺，偶尔也要黏一下或情绪化一下。",
        "low": "不太稳定，容易要么黏太紧要么冷太久。学会接住对方的情绪，别太慌也别太烦，稳如老狗才是王道。",
    },
    "anxious": {
        "high": "赛博怨妇认证。回消息慢5分钟，你已脑补完出轨路线图连财产分配都想好了。醒醒，人家可能只是在忙或者在洗澡或者在打游戏——别把自己折磨疯。",
        "medium": "有点黏，有时候能独立，看对方给的安全感够不够。学会给TA空间，别黏太紧，不然你们会陷入追逐-逃跑恶性循环。",
        "low": "不咋黏，比较独立。对象回消息慢你也不在意，稳如老狗。你是个独立派，谁遇到你都很省心。",
    },
    "avoidant": {
        "high": "装死大师认证。对象黏太紧你立刻人间蒸发，冷暴力界的奥林匹克冠军。醒醒，人家只是想黏你——别太冷太久让对方觉得你不在乎。",
        "medium": "有点冷，有时候能黏，看对象是否给你足够的自由。学会给TA回应，别冷太久，不然你们会陷入追逐-逃跑恶性循环。",
        "low": "不咋冷，比较温暖。对象黏你你也能接受，黏贴型暖宝宝。你是个温暖派，谁遇到你都很幸运。",
    },
    "fearful": {
        "high": "反复横跳狂魔认证。前一秒想结婚后一秒'男人没一个好东西'，把自己和对方同时折磨疯。醒醒，你的矛盾让对方也矛盾——学会表达你的需求别矛盾太久。",
        "medium": "有点矛盾，有时候能稳定，看对象是否给你足够的安全感+自由。学会表达你的矛盾，让TA理解你既需要安全感又需要空间。",
        "low": "不咋矛盾，比较清晰，知道自己要啥。你是个清晰派，谁遇到你都很省心。",
    },
}

# 12道恋爱场景化题目（口语化、网感表达）
ATTACHMENT_QUESTIONS: list[dict[str, Any]] = [
    # ===== 第1-3题：安全型倾向（测稳定感）=====
    {
        "index": 0,
        "text": "对象说'今天工作好累，被老板骂了'，你的第一反应是？",
        "options": [
            {"label": "A", "text": "先听TA说完，然后安慰TA，再问需不需要我帮忙", "score": 5},
            {"label": "B", "text": "安慰TA几句，然后说'没事，下次注意点就行'", "score": 4},
            {"label": "C", "text": "说'别想了，想点开心的，今晚吃啥？'", "score": 3},
            {"label": "D", "text": "说'我也好累啊，今天我也被骂了'", "score": 2},
            {"label": "E", "text": "不知道咋说，怕说错让TA更难受，干脆不回", "score": 1},
        ],
        "dimension": "secure",
        "reverse": False,
    },
    {
        "index": 1,
        "text": "对象突然说'我觉得你最近不太关心我了'，你的反应是？",
        "options": [
            {"label": "A", "text": "问TA具体哪感觉我不关心了，然后一起聊聊怎么改进", "score": 5},
            {"label": "B", "text": "解释我最近确实忙，但我会多关心TA的", "score": 4},
            {"label": "C", "text": "说'我没有不关心你啊，你别多想'", "score": 3},
            {"label": "D", "text": "有点委屈，觉得我也很关心TA啊TA咋这么说", "score": 2},
            {"label": "E", "text": "不知道咋回，怕说错让TA更生气，干脆沉默", "score": 1},
        ],
        "dimension": "secure",
        "reverse": False,
    },
    {
        "index": 2,
        "text": "对象和异性朋友出去玩了一整天，回来告诉你'今天好开心'，你的反应是？",
        "options": [
            {"label": "A", "text": "问TA今天玩了啥，开心就好，顺便说下次我也想去", "score": 5},
            {"label": "B", "text": "说'开心就好啊，下次叫上我呗'", "score": 4},
            {"label": "C", "text": "说'挺好的，我有自己的安排也挺开心'", "score": 3},
            {"label": "D", "text": "有点不舒服，但不说，自己默默消化", "score": 2},
            {"label": "E", "text": "很不安，担心TA是不是更喜欢那个朋友，但又不敢问", "score": 1},
        ],
        "dimension": "secure",
        "reverse": False,
    },

    # ===== 第4-6题：焦虑型倾向（测黏人度）=====
    {
        "index": 3,
        "text": "对象回消息慢了2小时，你啥状态？",
        "options": [
            {"label": "A", "text": "稳如老狗，TA可能在忙，我也有自己的事", "score": 5},
            {"label": "B", "text": "有点好奇TA在干嘛，发个表情包戳一下", "score": 4},
            {"label": "C", "text": "发了好几条消息问TA在干嘛，有点急", "score": 3},
            {"label": "D", "text": "已脑补TA是不是遇到更好的人了，是不是不爱我了", "score": 2},
            {"label": "E", "text": "连分手后的财产分配都想好了，TA完了", "score": 1},
        ],
        "dimension": "anxious",
        "reverse": True,  # 反向计分：选A(稳定)得5分(低焦虑)，选E(极度焦虑)得1分(高焦虑)
    },
    {
        "index": 4,
        "text": "对象说'周末我想和朋友去打球，不约你了'，你的反应是？",
        "options": [
            {"label": "A", "text": "挺好的，那我也找朋友出去玩，或者在家休息", "score": 5},
            {"label": "B", "text": "有点失落，但也能接受，说'那下次约'", "score": 4},
            {"label": "C", "text": "问TA能不能带上我，或者能不能早点结束再来找我", "score": 3},
            {"label": "D", "text": "很失落，觉得TA不爱我了，宁愿和朋友也不陪我", "score": 2},
            {"label": "E", "text": "很受伤，连TA是不是在骗我都在脑子里演完了", "score": 1},
        ],
        "dimension": "anxious",
        "reverse": True,  # 反向计分
    },
    {
        "index": 5,
        "text": "对象突然冷淡了一天，回消息很短，你啥感觉？",
        "options": [
            {"label": "A", "text": "可能TA今天心情不好或累了，问问TA咋了", "score": 5},
            {"label": "B", "text": "有点担心，但给TA空间，等TA自己调整", "score": 4},
            {"label": "C", "text": "有点慌，发了好几条消息问TA是不是不开心了", "score": 3},
            {"label": "D", "text": "很慌，已脑补TA是不是遇到更好的人了是不是不爱我了", "score": 2},
            {"label": "E", "text": "极度慌张，连分手后的财产分配都想好了，TA完了", "score": 1},
        ],
        "dimension": "anxious",
        "reverse": True,  # 反向计分
    },

    # ===== 第7-9题：回避型倾向（测冷暴力倾向）=====
    {
        "index": 6,
        "text": "对象想每天黏着你，每天都要见面聊天，你啥感觉？",
        "options": [
            {"label": "A", "text": "挺好的，我也喜欢黏着TA，每天见面很开心", "score": 5},
            {"label": "B", "text": "还行，能黏也能独立，看情况调整", "score": 4},
            {"label": "C", "text": "有点压力，觉得需要一点自己的空间", "score": 3},
            {"label": "D", "text": "觉得窒息，想逃跑，需要很多独立空间", "score": 2},
            {"label": "E", "text": "极度窒息，立刻冷暴力断联，TA太黏了", "score": 1},
        ],
        "dimension": "avoidant",
        "reverse": True,  # 反向计分：选A(不回避)得5分(低回避)，选E(极度回避)得1分(高回避)
    },
    {
        "index": 7,
        "text": "对象哭着说'你不心疼我，你不在乎我'，你的反应是？",
        "options": [
            {"label": "A", "text": "心疼TA，抱住TA，问TA具体哪觉得我不心疼了", "score": 5},
            {"label": "B", "text": "有点不知所措，但还是试着安慰TA", "score": 4},
            {"label": "C", "text": "有点烦，觉得TA太情绪化了，不知咋回", "score": 3},
            {"label": "D", "text": "很烦，觉得TA矫情，干脆冷暴力不回", "score": 2},
            {"label": "E", "text": "极度烦，立刻断联逃跑，TA太情绪化了", "score": 1},
        ],
        "dimension": "avoidant",
        "reverse": True,  # 反向计分
    },
    {
        "index": 8,
        "text": "对象想深度聊你们的关系、未来、三观，你啥感觉？",
        "options": [
            {"label": "A", "text": "挺好的，我也喜欢深度聊，这样能更理解彼此", "score": 5},
            {"label": "B", "text": "还行，能聊但也不会天天聊，看情况", "score": 4},
            {"label": "C", "text": "有点压力，觉得聊这些太累太深了", "score": 3},
            {"label": "D", "text": "很烦，觉得聊这些没用，干脆回避不聊", "score": 2},
            {"label": "E", "text": "极度烦，立刻冷暴力断联，TA太深了", "score": 1},
        ],
        "dimension": "avoidant",
        "reverse": True,  # 反向计分
    },

    # ===== 第10-12题：恐惧型倾向（测矛盾纠结度）=====
    {
        "index": 9,
        "text": "对象对你很好，很关心你很爱你，你啥感觉？",
        "options": [
            {"label": "A", "text": "很开心很感动，觉得被爱很幸福", "score": 5},
            {"label": "B", "text": "挺开心的，但偶尔也会有点不真实的感觉", "score": 4},
            {"label": "C", "text": "既开心又害怕，怕TA以后会对我不好", "score": 3},
            {"label": "D", "text": "很矛盾，既想黏TA又怕被伤害，不知道咋办", "score": 2},
            {"label": "E", "text": "极度矛盾，既想靠近又想逃跑，完全不知道咋办", "score": 1},
        ],
        "dimension": "fearful",
        "reverse": True,  # 反向计分：选A(不恐惧)得5分(低恐惧)，选E(极度恐惧)得1分(高恐惧)
    },
    {
        "index": 10,
        "text": "对象想和你建立深度亲密关系，想了解你的内心，你啥感觉？",
        "options": [
            {"label": "A", "text": "挺好的，我也想让TA了解我的内心", "score": 5},
            {"label": "B", "text": "还行，能聊但也不会全部敞开，看情况", "score": 4},
            {"label": "C", "text": "有点害怕，怕TA了解我后就不爱我了", "score": 3},
            {"label": "D", "text": "很矛盾，既想让TA了解又怕被伤害", "score": 2},
        {"label": "E", "text": "极度矛盾，既想敞开又想封闭，完全不知道咋办", "score": 1},
        ],
        "dimension": "fearful",
        "reverse": True,  # 反向计分
    },
    {
        "index": 11,
        "text": "对象突然对你冷淡了一天，你啥感觉？",
        "options": [
            {"label": "A", "text": "可能TA今天心情不好或累了，问问TA咋了", "score": 5},
            {"label": "B", "text": "有点担心，但给TA空间，等TA自己调整", "score": 4},
            {"label": "C", "text": "既担心TA又害怕靠近TA，不知道该问还是该等", "score": 3},
            {"label": "D", "text": "很矛盾，既想黏TA问TA咋了又怕TA更冷淡", "score": 2},
        {"label": "E", "text": "极度矛盾，既想靠近又想逃跑，完全不知道咋办", "score": 1},
        ],
        "dimension": "fearful",
        "reverse": True,  # 反向计分
    },
]

# 极端标签机制（SBTI 毒舌风格）
EXTREME_TAGS = {
    # 赛博怨妇极端：连体婴认证
    "anxious_high": {
        "threshold": 85,
        "tag": "连体婴认证",
        "description": "回消息慢5分钟，你已脑补完出轨路线图连分手后财产分配都想好了。醒醒，人家可能只是在忙。",
    },
    "anxious_low": {
        "threshold": 15,
        "tag": "独立冷淡认证",
        "description": "对象回消息慢你也不在意，对象冷淡你也不慌，稳如老狗。你是个独立派。",
    },

    # 装死大师极端：洞穴伪人认证
    "avoidant_high": {
        "threshold": 85,
        "tag": "洞穴伪人认证",
        "description": "冷暴力界的奥林匹克冠军，对象黏太紧立刻人间蒸发，一有冲突直接断联。",
    },
    "avoidant_low": {
        "threshold": 15,
        "tag": "黏贴型暖宝宝认证",
        "description": "对象黏你你也能接受，对象情绪化你会安慰，对象想深度聊你也能聊。你是个温暖派。",
    },

    # 反复横跳狂魔极端：矛盾纠结认证
    "fearful_high": {
        "threshold": 85,
        "tag": "反复横跳认证",
        "description": "前一秒想结婚后一秒'男人没一个好东西'，把自己和对方同时折磨疯。醒醒，你的矛盾让对方也矛盾。",
    },
    "fearful_low": {
        "threshold": 15,
        "tag": "清晰稳定认证",
        "description": "知道自己要啥，对象对你好你很开心，对象冷淡你会问TA咋了，不矛盾不纠结。你是个清晰派。",
    },

    # 稳如老狗极端：情绪灭火器认证
    "secure_high": {
        "threshold": 85,
        "tag": "情绪灭火器认证",
        "description": "对象发疯你睡觉，主打一个无动于衷，恋爱里的情绪稳定大师。但也别太稳定显得没心没肺。",
    },
    "secure_low": {
        "threshold": 15,
        "tag": "情绪过山车认证",
        "description": "要么黏太紧要么冷太久，对象说啥你容易慌或烦，情绪波动大。学会稳如老狗才是王道。",
    },
}

# 四种依恋类型的恋爱说明书（SBTI 毒舌风格）
ATTACHMENT_TYPE_LABELS = {
    "secure": {
        "nickname": "稳如老狗（STBL）",
        "nickname_fun": "情绪灭火器",
        "tags": [
            "对象发疯你睡觉",
            "主打一个无动于衷",
            "恋爱里的情绪稳定大师",
            "谁遇到你都很幸运",
            "但也别太稳定显得没心没肺",
        ],
        "love_manual": {
            "strengths": ["情绪稳定，对象发疯你睡觉，主打一个无动于衷。谁遇到你都很幸运。"],
            "weaknesses": ["有时候太稳定，对象可能会觉得你不够热情或不够在乎——别太稳定显得没心没肺。"],
            "best_match": [
                "任何类型都能配",
                "为啥配：你太稳定了，能适应任何类型，对方黏你能接住，对方冷你能给空间",
                "日常场景：对象黏你你也能黏，对象冷你你也能冷，看情况调整",
                "吵架场景：对象情绪化你能稳住，对象冷暴力你能给空间",
                "注意：别太稳定显得没热情，偶尔也要黏一下或情绪化一下",
                "【判官判词】：你是恋爱里的万能适配器，谁遇到你都很幸运，但别太稳定显得没心没肺——偶尔也要演一下'我很在乎'。",
            ],
            "caution_match": [
                "反复横跳狂魔（WOC-F）",
                "为啥磨合：TA太矛盾，你太稳定，TA可能会觉得你不懂TA的矛盾",
                "日常冲突：TA既想黏又怕被伤害，你太稳定TA可能觉得你不够在乎",
                "吵架场景：TA矛盾纠结，你稳如老狗，TA可能觉得你不懂TA",
                "怎么磨合：学会理解TA的矛盾，别太稳定显得没心没肺，偶尔也要表现出矛盾",
                "【判官避坑】：如果你遇到了反复横跳狂魔，别太稳定显得没心没肺，学会理解TA的矛盾，偶尔也要表现出你的在乎——不然TA会把你也折磨疯。",
            ],
            "love_red_flags": [
                "对象觉得你太稳定不够热情会让你困惑",
                "吵架时对象情绪化你稳如老狗会让TA觉得你不懂TA",
                "对象觉得你不够在乎会让你委屈",
            ],
            "love_sweet_points": [
                "对象感激你的稳定会让你觉得被认可",
                "吵架时对象能理解你的稳定会让你觉得被理解",
                "对象说'有你我很安心'会让你觉得有意义",
            ],
        },
    },
    "anxious": {
        "nickname": "赛博怨妇（ANX-S）",
        "nickname_fun": "连体婴",
        "tags": [
            "回消息慢5分钟已脑补出轨路线图",
            "连分手后财产分配都想好了",
            "对方只回'嗯'你会瞬间熄火",
            "需要很多安全感很多确认",
            "极度黏人极度需要回应",
        ],
        "love_manual": {
            "strengths": ["很在乎对方，能给对方很多关心和爱意——但也别黏太紧让对方窒息。"],
            "weaknesses": ["太黏太需要安全感，回消息慢5分钟你已脑补完出轨路线图连财产分配都想好了。醒醒，人家可能只是在忙。"],
            "best_match": [
                "稳如老狗（STBL）",
                "为啥配：TA太稳定了，能接住你的所有黏和慌，给你很多安全感",
                "日常场景：你黏TA TA能接住，你慌TA能稳住你，给你很多确认",
                "吵架场景：你慌TA稳住你，你脑补TA澄清，给你很多安全感",
                "注意：别黏太紧让TA窒息，学会给TA一些空间",
                "【判官判词】：如果你刷到了这种稳如老狗的情绪灭火器，TA会用稳定接住你的所有慌张，别黏太紧给TA空间——不然你们会陷入追逐-逃跑恶性循环。",
            ],
            "caution_match": [
                "装死大师（FAKE-D）",
                "为啥磨合：追逐-逃跑恶性循环，你黏TA冷，你更慌TA更冷",
                "日常冲突：你黏TA觉得窒息冷暴力，你更慌TA更冷",
                "吵架场景：你慌TA冷暴力，你更慌TA更冷，恶性循环",
                "怎么磨合：学会给TA空间，别黏太紧，学会独立",
                "【判官避坑】：如果你遇到了装死大师，别黏太紧给TA空间学会独立，不然你们会陷入追逐-逃跑恶性循环——你更慌TA更冷TA更冷你更慌，死循环。",
            ],
            "love_red_flags": [
                "对象回消息慢会让你脑补出轨路线图",
                "对象冷淡一秒会让你慌到窒息",
                "对象不给你安全感会让你崩溃",
            ],
            "love_sweet_points": [
                "对象给你很多安全感会让你感动到哭",
                "对象回消息快会让你觉得被在乎",
                "对象说'我在呢别慌'会让你瞬间软化",
            ],
        },
    },
    "avoidant": {
        "nickname": "装死大师（FAKE-D）",
        "nickname_fun": "洞穴伪人",
        "tags": [
            "冷暴力界的奥林匹克冠军",
            "对象黏太紧立刻人间蒸发",
            "一有冲突直接断联",
            "需要很多很多空间",
            "极度回避极度需要独立",
        ],
        "love_manual": {
            "strengths": ["能给对方很多空间和自由，不黏不控制——但也别冷太久让对方觉得你不在乎。"],
            "weaknesses": ["太冷太需要空间，对象黏太紧你觉得窒息要逃跑。醒醒，人家只是想黏你——别太冷太久。"],
            "best_match": [
                "稳如老狗（STBL）",
                "为啥配：TA太稳定了，能给你很多空间，不黏你不控制你",
                "日常场景：你需要空间TA给你空间，你冷TA能理解不慌",
                "吵架场景：你冷暴力TA给空间，你逃跑TA不追，等你回来",
                "注意：别冷太久让TA觉得你不在乎，学会偶尔黏一下",
                "【判官判词】：如果你刷到了这种稳如老狗的情绪灭火器，TA会用稳定接住你的所有冷暴力，别冷太久给TA回应——不然你们会陷入追逐-逃跑恶性循环。",
            ],
            "caution_match": [
                "赛博怨妇（ANX-S）",
                "为啥磨合：追逐-逃跑恶性循环，TA黏你冷，TA更慌你更冷",
                "日常冲突：TA黏你觉得窒息冷暴力，TA更慌你更冷",
                "吵架场景：TA慌你冷暴力，TA更慌你更冷，恶性循环",
                "怎么磨合：学会给TA回应，别冷太久，学会黏一下",
                "【判官避坑】：如果你遇到了赛博怨妇，别冷太久给TA回应学会黏一下，不然你们会陷入追逐-逃跑恶性循环——TA更慌你更冷你更冷TA更慌，死循环。",
            ],
            "love_red_flags": [
                "对象黏太紧会让你觉得窒息要逃跑",
                "对象情绪化会让你立刻冷暴力断联",
                "对象不给你空间会让你崩溃",
            ],
            "love_sweet_points": [
                "对象给你很多空间会让你觉得被理解",
                "对象不黏你会让你觉得舒服",
                "对象说'我给你空间'会让你瞬间软化",
            ],
        },
    },
    "fearful": {
        "nickname": "反复横跳狂魔（WOC-F）",
        "nickname_fun": "既想黏又怕被伤害",
        "tags": [
            "前一秒想结婚后一秒'男人没一个好东西'",
            "把自己和对方同时折磨疯",
            "既想靠近又想逃跑",
            "对象对你好你既开心又害怕",
            "完全不知道咋办",
        ],
        "love_manual": {
            "strengths": ["很在乎对方，能感受到对方的情绪和需求——但也别矛盾太久让对方困惑。"],
            "weaknesses": ["太矛盾太纠结，前一秒想结婚后一秒'男人没一个好东西'，把自己和对方同时折磨疯。醒醒，你的矛盾让对方也矛盾。"],
            "best_match": [
                "稳如老狗（STBL）",
                "为啥配：TA太稳定了，能理解你的矛盾，给你安全感+空间",
                "日常场景：你矛盾TA能理解，你既想黏又怕TA能接住你",
                "吵架场景：你矛盾纠结TA稳住你，给你安全感+空间",
                "注意：别矛盾太久让TA困惑，学会表达你的需求",
                "【判官判词】：如果你刷到了这种稳如老狗的情绪灭火器，TA会用稳定接住你的所有矛盾，别矛盾太久表达需求——不然TA会把你也折磨疯。",
            ],
            "caution_match": [
                "赛博怨妇（ANX-S）或装死大师（FAKE-D）",
                "为啥磨合：你本来就矛盾，TA黏或冷会让你更矛盾更纠结",
                "日常冲突：你既想黏又怕，TA黏你你更怕TA冷你更慌",
                "吵架场景：你矛盾TA黏或冷，你更矛盾更纠结",
                "怎么磨合：学会表达你的矛盾，让TA理解你既需要安全感又需要空间",
                "【判官避坑】：如果你遇到了赛博怨妇或装死大师，学会表达你的矛盾，让TA理解你既需要安全感又需要空间——不然你会把TA也折磨疯。",
            ],
            "love_red_flags": [
                "对象对你好会让你既开心又害怕",
                "对象冷淡会让你既想靠近又想逃跑",
                "你完全不知道咋办会让你崩溃",
            ],
            "love_sweet_points": [
                "对象理解你的矛盾会让你感动到哭",
                "对象给你安全感+空间会让你觉得被理解",
                "对象说'我理解你的矛盾'会让你瞬间软化",
            ],
        },
    },
}

# 小雅专属回复内容（SBTI 毒舌判官风格——互联网嘴替/闺蜜判官）
XIAOYA_MESSAGES = {
    "secure": {
        "greeting": "测出来了，你是「稳如老狗（STBL）」。🎉",
        "identity": "情绪灭火器，对象发疯你睡觉，主打一个无动于衷。",
        "quirk": "恋爱中的你就像个情绪灭火器，对象说'今天好累'你接住，对象说'你不关心我'你聊聊，对象说'我今天和朋友出去玩'你说开心就好。稳如老狗，不黏也不冷——但别太稳定显得没心没肺。",
        "crush": "暗恋时的你：稳如老狗，对象冷淡你不慌，对象黏你你不窒息，对象情绪化你能接住。但实际操作：偶尔也会有点黏或有点冷，看情况——别太稳定让对方觉得你不在乎。",
        "breakup": "分手后的你：稳如老狗，前1天有点难过，第2天开始反思，第3天已经调整好，第4天开始筛选下一个目标。你的深情配额只有72小时，过期概不退换。",
        "suggestion": "💡 判官判词：下次遇到心动的人，别太稳定显得没心没肺，偶尔也要演一下'我很在乎'——不然对方会觉得你是个莫得感情的AI。",
    },
    "anxious": {
        "greeting": "别看了，测出来又是「赛博怨妇（ANX-S）」。🎉",
        "identity": "回消息慢5分钟，你已脑补完出轨路线图。",
        "quirk": "恋爱中的你就像个连体婴，对象回消息慢5分钟你已脑补完是不是不爱我了是不是遇到更好的人了连分手后的财产分配都想好了。醒醒，人家可能只是在忙或者在洗澡或者在打游戏——别把自己折磨疯。",
        "crush": "暗恋时的你：对方只是顺手点赞了你的朋友圈，你连你们以后死后合葬在哪个公墓、买几等座的骨灰盒都想好了。醒醒，人家只是手滑！",
        "breakup": "分手后的你：前3天哭到窒息，第4天看到帅哥瞬间复活。你的深情配额只有72小时，过期概不退换。",
        "suggestion": "💡 判官判词：下次遇到心动的人，别黏太紧给TA空间学会独立，不然你们会陷入追逐-逃跑恶性循环——你更慌TA更冷TA更冷你更慌，死循环。",
    },
    "avoidant": {
        "greeting": "测出来了，你是「装死大师（FAKE-D）」。🎉",
        "identity": "冷暴力界的奥林匹克冠军，对象黏太紧立刻人间蒸发。",
        "quirk": "恋爱中的你就像个洞穴伪人，对象黏太紧你觉得窒息要逃跑，对象情绪化你立刻冷暴力断联，对象想深度聊你直接回避。醒醒，人家只是想黏你——别太冷太久让对方觉得你不在乎。",
        "crush": "暗恋时的你：对象黏你你觉得窒息，对象情绪化你冷暴力，对象想深度聊你回避。但实际操作：继续装死，等TA先发现你的心意——但别装太久让对方以为你死了。",
        "breakup": "分手后的你：表面冷静冷暴力，内心其实有点难过，但立刻开始独处蓄电，准备下一个目标。你的深情配额只有24小时，过期概不退换。",
        "suggestion": "💡 判官判词：下次遇到心动的人，别冷太久给TA回应学会黏一下，不然你们会陷入追逐-逃跑恶性循环——TA更慌你更冷你更冷TA更慌，死循环。",
    },
    "fearful": {
        "greeting": "测出来了，你是「反复横跳狂魔（WOC-F）」。🎉",
        "identity": "前一秒想结婚，后一秒'男人没一个好东西'，把自己和对方同时折磨疯。",
        "quirk": "恋爱中的你就像个反复横跳狂魔，对象对你好你既开心又害怕，对象冷淡你既想靠近又想逃跑，既想黏又怕被伤害。醒醒，你的矛盾让对方也矛盾——别矛盾太久把TA也折磨疯。",
        "crush": "暗恋时的你：对象对你好你既开心又害怕，对象冷淡你既想靠近又想逃跑。但实际操作：继续矛盾纠结，完全不知道咋办——醒醒，人家只是想跟你谈恋爱不是跟你玩推拉游戏。",
        "breakup": "分手后的你：前1周矛盾纠结到窒息，第2周既想联系又怕被伤害，第3周开始脑补是不是我不够好，第4周突然想通'我值得更好的'，然后用1年时间慢慢放下。你的深情配额只有168小时，过期概不退换。",
        "suggestion": "💡 判官判词：下次遇到心动的人，学会表达你的矛盾让TA理解你既需要安全感又需要空间，别矛盾太久——不然你会把TA也折磨疯。",
    },
}


def get_question(index: int) -> dict[str, Any] | None:
    """获取指定索引的题目"""
    if 0 <= index < len(ATTACHMENT_QUESTIONS):
        return ATTACHMENT_QUESTIONS[index]
    return None


def get_dimension_for_question(index: int) -> str | None:
    """获取题目所属的维度（依恋类型）"""
    question = get_question(index)
    if question:
        return str(question.get("dimension") or "")
    return None


def calculate_dimension_score(answers: list[int], dimension: str) -> float:
    """计算某个维度的得分（0-100分）

    注意：焦虑、回避、恐惧维度是反向计分
    - 选A(稳定/不焦虑/不回避/不恐惧)得5分 → 转换后得低分(20分)
    - 选E(极度焦虑/极度回避/极度恐惧)得1分 → 转换后得高分(80分)

    安全型维度是正向计分
    - 选A(稳定)得5分 → 转换后得高分(80分)
    - 选E(不稳定)得1分 → 转换后得低分(20分)
    """
    start, end = ATTACHMENT_QUESTION_RANGES.get(dimension, (0, 0))
    if start == end:
        return 0.0
    dimension_answers = answers[start:end]
    if not dimension_answers:
        return 0.0

    total = sum(dimension_answers)

    # 安全型是正向计分（高分=安全）
    if dimension == "secure":
        score = (total - 3) / 12 * 100  # 3分(最低)→0分, 15分(最高)→100分
    else:
        # 焦虑、回避、恐惧是反向计分（高分=焦虑/回避/恐惧）
        # 原始分：5分(不焦虑)→转换后得低分, 1分(极度焦虑)→转换后得高分
        score = 100 - (total - 3) / 12 * 100  # 反向转换

    return round(max(0, min(100, score)), 1)


def calculate_all_scores(answers: list[int]) -> dict[str, float]:
    """计算所有维度的得分"""
    return {
        dimension: calculate_dimension_score(answers, dimension)
        for dimension in ATTACHMENT_TYPES
    }


def get_dimension_feedback(dimension: str, score: float) -> str:
    """获取维度反馈文案"""
    feedbacks = ATTACHMENT_FEEDBACKS.get(dimension, {})
    if score >= 70:
        return str(feedbacks.get("high", ""))
    if score >= 40:
        return str(feedbacks.get("medium", ""))
    return str(feedbacks.get("low", ""))


def get_extreme_tags(scores: dict[str, float]) -> list[dict[str, str]]:
    """计算极端标签"""
    extreme_tags = []

    for attachment_type in ATTACHMENT_TYPES:
        score = scores.get(attachment_type, 50)

        # 高分极端
        high_key = f"{attachment_type}_high"
        if high_key in EXTREME_TAGS and score >= EXTREME_TAGS[high_key]["threshold"]:
            extreme_tags.append({
                "tag": EXTREME_TAGS[high_key]["tag"],
                "description": EXTREME_TAGS[high_key]["description"],
            })

        # 低分极端
        low_key = f"{attachment_type}_low"
        if low_key in EXTREME_TAGS and score <= EXTREME_TAGS[low_key]["threshold"]:
            extreme_tags.append({
                "tag": EXTREME_TAGS[low_key]["tag"],
                "description": EXTREME_TAGS[low_key]["description"],
            })

    return extreme_tags


def get_primary_attachment_type(scores: dict[str, float]) -> str:
    """判断主要依恋类型（得分最高的类型）"""
    # 安全型优先（如果安全型得分≥60，直接判定为安全型）
    if scores.get("secure", 0) >= 60:
        return "secure"

    # 否则取得分最高的非安全型类型
    non_secure_scores = {
        k: v for k, v in scores.items() if k != "secure"
    }
    if non_secure_scores:
        return max(non_secure_scores, key=non_secure_scores.get)

    return "secure"  # 默认安全型


def get_type_info(type_code: str) -> dict[str, Any]:
    """获取类型标签和恋爱说明书"""
    return ATTACHMENT_TYPE_LABELS.get(
        type_code,
        {
            "nickname": type_code,
            "tags": [f"依恋风格:{type_code}"],
            "love_manual": {
                "strengths": ["你有独特的依恋特质"],
                "weaknesses": ["恋爱中需要磨合的地方"],
                "best_match": ["能理解你的人"],
                "caution_match": ["需要多沟通的类型"],
            },
        },
    )


def _interpretation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    """生成安全感来源式解读（不强调类型标签）

    核心转变：
    - 从"你是XX类型"转向"你的安全感来源"
    - 从"优势/坑点"转向"安全感来源/关系模式/关系雷区"
    - 从"最佳匹配"转向"适合对象"
    """
    scores = dict(result.get("scores") or {})
    type_code = str(result.get("type_code") or get_primary_attachment_type(scores))
    type_info = get_type_info(type_code)

    # 获取四个维度的得分
    secure_score = scores.get("secure", 50)
    anxious_score = scores.get("anxious", 50)
    avoidant_score = scores.get("avoidant", 50)
    fearful_score = scores.get("fearful", 50)

    # 极端标签（轻量融入，不再高亮）
    extreme_tags = get_extreme_tags(scores)

    # 构建安全感来源描述（根据得分判断）
    summary = "你在恋爱里"

    # 判断稳定度
    if secure_score >= 70:
        summary += "很稳，对象说啥你都能接住，不黏也不冷。"
    elif secure_score >= 40:
        summary += "基本稳定，但有时也会有点黏或有点冷，看情况。"
    else:
        summary += "不太稳定，容易要么黏太紧要么冷太久。"

    # 构建安全感来源（根据主要类型）
    security_source = "\n\n**🎯 你的安全感来源：**\n"
    if type_code == "secure":
        security_source += "TA的稳定陪伴让你很安心，TA不冷暴力不突然消失，你就觉得很安全。"
    elif type_code == "anxious":
        security_source += "TA的快速回应让你很安心，TA秒回消息、TA主动找你、TA给你很多确认。"
    elif type_code == "avoidant":
        security_source += "TA给你足够的空间让你很安心，TA不黏你、TA理解你的独立需求。"
    elif type_code == "fearful":
        security_source += "同时需要安全感+空间，既需要TA的陪伴又需要TA的理解。"

    # 构建关系模式（根据得分）
    relationship_mode = "\n\n**🌊 你的关系模式：**\n"
    if secure_score >= 70:
        relationship_mode += "不黏也不冷，看情况调整。对象黏你你也能接住，对象冷淡你也能给空间。"
        # 轻量融入极端标签
        if secure_score >= 85:
            relationship_mode += "\n情绪稳定萨摩耶认证 ✨"
    elif anxious_score >= 70:
        relationship_mode += "很黏，对象回消息慢你会慌，对象冷淡你会脑补。黏人精认证 ✨"
    elif avoidant_score >= 70:
        relationship_mode += "很冷，对象黏太紧你会觉得窒息，对象情绪化你会冷暴力。冷暴力大师认证 ✨"
    elif fearful_score >= 70:
        relationship_mode += "很矛盾，既想黏又怕被伤害，既想靠近又想逃跑。矛盾纠结体认证 ✨"
    else:
        relationship_mode += "看情况，有时黏有时冷，有时矛盾有时稳。"

    # 构建关系雷区（根据类型）
    relationship_red_flags = "\n\n**⚡ 你的关系雷区：**\n"
    if type_code == "secure":
        relationship_red_flags += "TA冷暴力会让你很慌，TA突然消失你会脑补「是不是不爱我了」。"
    elif type_code == "anxious":
        relationship_red_flags += "TA回消息慢你会脑补「是不是不爱我了」，TA冷淡一秒你会慌到窒息。"
    elif type_code == "avoidant":
        relationship_red_flags += "TA黏太紧你会觉得窒息要逃跑，TA情绪化你会立刻冷暴力断联。"
    elif type_code == "fearful":
        relationship_red_flags += "TA对你好你既开心又害怕，TA冷淡你既想靠近又想逃跑，完全不知道咋办。"

    # 构建适合对象（根据类型）
    suitable_partner = "\n\n**💡 你适合的对象：**\n"
    if type_code == "secure":
        suitable_partner += "能给你稳定陪伴的人，不太冷暴力不太突然消失的人。不管TA是什么依恋类型，你都能适应。"
    elif type_code == "anxious":
        suitable_partner += "能快速回应你的人，秒回消息、主动找你、给你很多确认的人。最好是情绪稳定型（安全型）。"
    elif type_code == "avoidant":
        suitable_partner += "能给你足够空间的人，不黏你、理解你的独立需求的人。最好是情绪稳定型（安全型）。"
    elif type_code == "fearful":
        suitable_partner += "能理解你矛盾的人，既给你安全感又给你空间的人。最好是情绪稳定型（安全型）。"

    # 相处建议
    relationship_advice = "\n\n**💝 相处建议：**\n"
    if type_code == "secure":
        relationship_advice += "直接告诉TA你需要稳定陪伴，不要脑补直接问TA咋了，学会表达你的需求。"
    elif type_code == "anxious":
        relationship_advice += "学会给TA空间别黏太紧，别脑补直接问TA咋了，学会独立不要过度依赖。"
    elif type_code == "avoidant":
        relationship_advice += "别冷太久给TA回应，学会偶尔黏一下，学会表达你的需求。"
    elif type_code == "fearful":
        relationship_advice += "学会表达你的矛盾，让TA理解你既需要安全感又需要空间，别矛盾太久。"

    # 脱单免责声明
    disclaimer = "\n\n**【使用本说明书的脱单安全须知】**\n"
    disclaimer += "【储藏条件】 建议放置在能给足安全感+空间的理解环境中。\n"
    disclaimer += "【不良反应】 强行配对可能会导致追逐-逃跑恶性循环或矛盾纠结到窒息。\n"
    disclaimer += "【红娘提示】 说明书仅供脱单参考，吵架时请勿将本报告作为呈堂证供。"

    return {
        "summary": summary,
        "security_source": security_source,
        "relationship_mode": relationship_mode,
        "relationship_red_flags": relationship_red_flags,
        "suitable_partner": suitable_partner,
        "relationship_advice": relationship_advice,
        "extreme_tags": extreme_tags,  # 保留但不再高亮
        "disclaimer": disclaimer,
    }


def xiaoya_message_from_result(result: dict[str, Any]) -> str:
    """生成小雅风格的解读消息（SBTI 毒舌判官风格）

    核心转变：
    - 开场白改为"测出来了，你是「XX」"
    - 直接使用 SBTI 标签
    - 毒舌判官风格，戳破幻想
    """
    scores = dict(result.get("scores") or {})
    type_code = str(result.get("type_code") or get_primary_attachment_type(scores))

    # 获取四个维度的得分
    secure_score = scores.get("secure", 50)
    anxious_score = scores.get("anxious", 50)
    avoidant_score = scores.get("avoidant", 50)
    fearful_score = scores.get("fearful", 50)

    # 直接使用 XIAOYA_MESSAGES 中的毒舌判官风格内容
    xiaoya_content = XIAOYA_MESSAGES.get(type_code)
    if not xiaoya_content:
        return "测完了，但好像出了点问题，请联系管理员～"

    # 构建毒舌判官风格的开场白
    message = f"{xiaoya_content['greeting']}\n\n"
    message += f"**{xiaoya_content['identity']}**\n\n"
    message += f"{xiaoya_content['quirk']}\n\n"

    # 关系模式（毒舌风格）
    message += "**你的关系模式：**\n"
    if secure_score >= 70:
        message += "不黏也不冷，看情况调整。对象发疯你睡觉，主打一个无动于衷。"
        if secure_score >= 85:
            message += " 情绪灭火器认证 ✨"
        message += "\n\n"
    elif anxious_score >= 70:
        message += "很黏，回消息慢5分钟你已脑补出轨路线图。连体婴认证 ✨\n\n"
    elif avoidant_score >= 70:
        message += "很冷，对象黏太紧你立刻人间蒸发。洞穴伪人认证 ✨\n\n"
    elif fearful_score >= 70:
        message += "很矛盾，前一秒想结婚后一秒'男人没一个好东西'。反复横跳认证 ✨\n\n"
    else:
        message += "看情况，有时黏有时冷，有时矛盾有时稳。\n\n"

    # 关系雷区（毒舌风格）
    message += "**你的关系雷区：**\n"
    if type_code == "secure":
        message += "TA冷暴力你会觉得困惑'为啥不直接说'，TA突然消失你会脑补'是不是不爱我了'——醒醒，人家可能只是需要空间。\n\n"
    elif type_code == "anxious":
        message += "TA回消息慢你会脑补出轨路线图，TA冷淡一秒你会慌到窒息——醒醒，人家可能只是在忙或者在洗澡。\n\n"
    elif type_code == "avoidant":
        message += "TA黏太紧你会觉得窒息要逃跑，TA情绪化你会立刻冷暴力断联——醒醒，人家只是想黏你。\n\n"
    elif type_code == "fearful":
        message += "TA对你好你既开心又害怕，TA冷淡你既想靠近又想逃跑——醒醒，你的矛盾会把TA也折磨疯。\n\n"

    # 暗恋时的你（毒舌风格）
    message += f"**暗恋时的你：**\n{xiaoya_content['crush']}\n\n"
    message += f"**分手后的你：**\n{xiaoya_content['breakup']}\n\n"

    # 判官判词
    message += f"{xiaoya_content['suggestion']}\n\n"

    message += "还想了解更多？比如你的恋爱雷点、甜点、或者具体的相处建议？继续问我呀～"

    return message


def calculate_love_match(
    user_a_scores: dict[str, float], user_b_scores: dict[str, float]
) -> dict[str, Any]:
    """计算两位用户的依恋风格匹配度

    匹配规则：
    - 安全型+任何 = 高分（安全型能适应任何类型）
    - 焦虑型+回避型 = 低分（追逐-逃跑恶性循环）
    - 恐惧型+任何 = 中低分（需要专业辅导）
    """
    match_score = 75.0  # 起始分
    dimension_analysis = {}

    a_type = get_primary_attachment_type(user_a_scores)
    b_type = get_primary_attachment_type(user_b_scores)

    # 安全型+任何 = 高分
    if a_type == "secure" or b_type == "secure":
        match_score += 15
        dimension_analysis["primary"] = "安全型配任何类型都很稳，能适应对方的依恋风格"

    # 焦虑型+回避型 = 低分（追逐-逃跑恶性循环）
    if (a_type == "anxious" and b_type == "avoidant") or \
       (a_type == "avoidant" and b_type == "anxious"):
        match_score -= 25
        dimension_analysis["primary"] = "追逐-逃跑恶性循环：焦虑型黏回避型冷，焦虑型更慌回避型更冷"

    # 恐惧型+任何 = 中低分（需要理解）
    if a_type == "fearful" or b_type == "fearful":
        match_score -= 10
        dimension_analysis["fearful"] = "恐惧型需要对方理解TA的矛盾，既需要安全感又需要空间"

    # 焦虑型+焦虑型 = 中分（可能过度依赖）
    if a_type == "anxious" and b_type == "anxious":
        match_score -= 5
        dimension_analysis["anxious"] = "双焦虑型可能会过度依赖，需要学会独立"

    # 回避型+回避型 = 低分（可能互相疏离）
    if a_type == "avoidant" and b_type == "avoidant":
        match_score -= 15
        dimension_analysis["avoidant"] = "双回避型可能会互相疏离，需要学会黏一下"

    final_score = max(0, min(100, match_score))

    if final_score >= 85:
        analysis = "🌟 依恋风格匹配度极高，你们很合适!"
    elif final_score >= 70:
        analysis = "💕 依恋风格匹配度良好，你们可以尝试"
    elif final_score >= 50:
        analysis = "⚖️ 依恋风格匹配度中等，需要多磨合多沟通"
    else:
        analysis = "⚠️ 依恋风格匹配度较低，你们需要努力才能走到一起"

    return {
        "score": round(final_score, 1),
        "analysis": analysis,
        "dimension_analysis": dimension_analysis,
        "a_type": a_type,
        "b_type": b_type,
    }