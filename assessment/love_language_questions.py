"""恋爱五种语言测验题库（10题精简版）

Love Languages 理论：Gary Chapman (1995)
五种恋爱语言：
- 肯定言词 (words_of_affirmation)：需要被赞美、被鼓励、彩虹屁
- 精心时刻 (quality_time)：需要专注的陪伴、深度对话、不被打扰的时间
- 接受礼物 (receiving_gifts)：需要物质象征、小心意、纪念物
- 服务行动 (acts_of_service)：需要实际帮助、对方帮你做事、解决麻烦
- 身体接触 (physical_touch)：需要肢体接触、抱抱贴贴、牵手亲亲

设计理念：
- 恋爱场景化题目（不说学术话）
- 口语化网感表达（接地气）
- 测排序而非类型（TOP3恋爱语言）
- 极端标签机制（趣味化）
- 小雅专属回复（区别于卡片内容）
"""

from __future__ import annotations

from typing import Any

# 五种恋爱语言
LOVE_LANGUAGES = [
    "words_of_affirmation",  # 肯定言词
    "quality_time",          # 精心时刻
    "receiving_gifts",       # 接受礼物
    "acts_of_service",       # 服务行动
    "physical_touch",        # 身体接触
]

LOVE_LANGUAGE_NAMES = {
    "words_of_affirmation": "肯定言词",
    "quality_time": "精心时刻",
    "receiving_gifts": "接受礼物",
    "acts_of_service": "服务行动",
    "physical_touch": "身体接触",
}

# 每种语言的题目范围（每语言2题）
LOVE_LANGUAGE_QUESTION_RANGES = {
    "words_of_affirmation": (0, 2),   # 第1-2题测肯定言词
    "quality_time": (2, 4),           # 第3-4题测精心时刻
    "receiving_gifts": (4, 6),        # 第5-6题测接受礼物
    "acts_of_service": (6, 8),        # 第7-8题测服务行动
    "physical_touch": (8, 10),        # 第9-10题测身体接触
}

# 维度反馈文案（SBTI 毒舌风格版本）
LOVE_LANGUAGE_FEEDBACKS = {
    "words_of_affirmation": {
        "high": "无成本白嫖大师认证。一句'宝你真好看'就能让你免费干三天家务。夸你是让TA开心最快的方式——零成本高效益。但也别光听甜言蜜语要看TA为你做了啥。",
        "medium": "有点喜欢被夸，偶尔夸你你会很开心。学会欣赏TA的其他表达方式——人家可能嘴笨但心诚。",
        "low": "对夸奖不太敏感，夸你你觉得没啥更喜欢实际行动。你是个务实派——别光看行动也要听TA说。",
    },
    "quality_time": {
        "high": "网瘾戒断所教官认证。约会时敢看一眼手机你今天就别想活着走出这家餐厅。放下手机专心陪是让TA开心最快的方式。但也别光要陪伴要看TA为你做了啥。",
        "medium": "有点喜欢陪伴，偶尔深度聊你会很开心。学会欣赏TA的其他表达方式——人家可能不善表达但行动实在。",
        "low": "对陪伴不太敏感，陪你你觉得没啥更喜欢独立行动。你是个独立派——但也别太独立让对方觉得你不在乎。",
    },
    "receiving_gifts": {
        "high": "人形吞金兽认证。不要问TA爱不爱你，看你送的包是不是限定款。送小心意是让TA开心最快的方式。但也别光要物质要看TA为你做了啥。",
        "medium": "有点喜欢礼物，偶尔送你你会很开心。学会欣赏TA的其他表达方式——人家可能不送礼但陪伴实在。",
        "low": "对礼物不太敏感，送你你觉得没啥更喜欢实际陪伴。你是个实在派——别光看物质也要看TA的心意。",
    },
    "acts_of_service": {
        "high": "巨婴饲养员认证。核心需求是找个能帮你通马桶交电费的爹系妈系工具人。帮TA做事是让TA开心最快的方式。但也别光要行动要看TA为你说了啥。",
        "medium": "有点喜欢对方帮你做事，偶尔帮你你会很开心。学会欣赏TA的其他表达方式——人家可能不做事但嘴甜实在。",
        "low": "对服务行动不太敏感，帮你你觉得没啥更喜欢情感交流。你是个情感派——别光看情感也要看TA的行动。",
    },
    "physical_touch": {
        "high": "人形章鱼认证。夏天体温39度也必须像胶水一样粘在对方身上。抱抱贴贴是让TA开心最快的方式。但也别光要肢体接触要看TA为你做了啥。",
        "medium": "有点喜欢肢体接触，偶尔抱你你会很开心。学会欣赏TA的其他表达方式——人家可能不黏但做事实在。",
        "low": "对肢体接触不太敏感，抱你你觉得没啥更喜欢精神交流。你是个精神派——别光看精神也要看TA的身体表达。",
    },
}

# 10道恋爱场景化题目（口语化、网感表达）
LOVE_LANGUAGE_QUESTIONS: list[dict[str, Any]] = [
    # ===== 第1-2题：肯定言词（测对夸奖的敏感度）=====
    {
        "index": 0,
        "text": "对象突然夸你'今天真好看，穿搭绝了'，你啥感觉？",
        "options": [
            {"label": "A", "text": "感动到哭，TA终于注意到我的穿搭了，开心到想发朋友圈", "score": 5},
            {"label": "B", "text": "挺开心的，觉得TA很细心，会更黏TA一点", "score": 4},
            {"label": "C", "text": "还行吧，夸一句没啥，但也会回一句'你也好看'", "score": 3},
            {"label": "D", "text": "没啥感觉，夸一句而已，不用太在意", "score": 2},
            {"label": "E", "text": "有点尴尬，夸我穿搭干啥，不如帮我解决实际问题", "score": 1},
        ],
        "dimension": "words_of_affirmation",
        "reverse": False,
    },
    {
        "index": 1,
        "text": "你今天工作很累，对象发消息说'辛苦了，你真的很努力，我心疼你'，你啥感觉？",
        "options": [
            {"label": "A", "text": "感动到哭，TA懂我的辛苦，瞬间觉得累也值得了", "score": 5},
            {"label": "B", "text": "挺感动的，觉得TA很体贴，心情好很多", "score": 4},
            {"label": "C", "text": "还行，安慰一句挺好的，但也没啥特别的", "score": 3},
            {"label": "D", "text": "没啥感觉，嘴上说说而已，不如帮我搞定麻烦事", "score": 2},
            {"label": "E", "text": "有点烦，心疼我干啥，不如给我买杯咖啡实在", "score": 1},
        ],
        "dimension": "words_of_affirmation",
        "reverse": False,
    },

    # ===== 第3-4题：精心时刻（测对陪伴的敏感度）=====
    {
        "index": 2,
        "text": "对象放下手机，专注陪你深度聊三观、未来、梦想，你啥感觉？",
        "options": [
            {"label": "A", "text": "感动到哭，TA终于愿意深度聊了，觉得灵魂被看见", "score": 5},
            {"label": "B", "text": "挺开心的，觉得TA很用心，会更想黏TA", "score": 4},
            {"label": "C", "text": "还行，深度聊挺好的，但也没啥特别的", "score": 3},
            {"label": "D", "text": "没啥感觉，聊三观干啥，不如一起去吃饭", "score": 2},
            {"label": "E", "text": "有点烦，聊这么多干啥，不如各自玩手机舒服", "score": 1},
        ],
        "dimension": "quality_time",
        "reverse": False,
    },
    {
        "index": 3,
        "text": "对象说'周末我想专心陪你，不接工作电话不看手机'，你啥感觉？",
        "options": [
            {"label": "A", "text": "感动到哭，TA愿意放下手机专心陪我，觉得被重视", "score": 5},
            {"label": "B", "text": "挺感动的，觉得TA很用心，周末会很开心", "score": 4},
            {"label": "C", "text": "还行，专心陪挺好的，但也没啥特别的", "score": 3},
            {"label": "D", "text": "没啥感觉，专心陪干啥，各自舒服就行", "score": 2},
            {"label": "E", "text": "有点烦，不看手机干啥，有急事咋办，不如各自玩手机", "score": 1},
        ],
        "dimension": "quality_time",
        "reverse": False,
    },

    # ===== 第5-6题：接受礼物（测对物质的敏感度）=====
    {
        "index": 4,
        "text": "对象突然送你一个小心意（比如你喜欢的零食、小饰品），你啥感觉？",
        "options": [
            {"label": "A", "text": "感动到哭，TA记得我喜欢啥，觉得被用心对待", "score": 5},
            {"label": "B", "text": "挺开心的，觉得TA很细心，会更想黏TA", "score": 4},
            {"label": "C", "text": "还行，送小心意挺好的，但也没啥特别的", "score": 3},
            {"label": "D", "text": "没啥感觉，送个东西而已，不用太在意", "score": 2},
            {"label": "E", "text": "有点尴尬，送东西干啥，不如陪我聊聊天实在", "score": 1},
        ],
        "dimension": "receiving_gifts",
        "reverse": False,
    },
    {
        "index": 5,
        "text": "纪念日对象送你一个精心准备的礼物（不是贵的但是有意义的），你啥感觉？",
        "options": [
            {"label": "A", "text": "感动到哭，TA花心思准备礼物，觉得被重视被爱", "score": 5},
            {"label": "B", "text": "挺感动的，觉得TA很用心，会很珍惜这个礼物", "score": 4},
            {"label": "C", "text": "还行，送礼物挺好的，但也没啥特别的", "score": 3},
            {"label": "D", "text": "没啥感觉，送礼物而已，不用太在意", "score": 2},
            {"label": "E", "text": "有点烦，送礼物干啥，不如帮我解决实际问题实在", "score": 1},
        ],
        "dimension": "receiving_gifts",
        "reverse": False,
    },

    # ===== 第7-8题：服务行动（测对实际行动的敏感度）=====
    {
        "index": 6,
        "text": "你今天很累，对象主动帮你搞定了麻烦事（比如帮你洗衣服、帮你处理工作问题），你啥感觉？",
        "options": [
            {"label": "A", "text": "感动到哭，TA帮我搞定麻烦事，觉得被照顾被心疼", "score": 5},
            {"label": "B", "text": "挺感动的，觉得TA很体贴，会很感激TA", "score": 4},
            {"label": "C", "text": "还行，帮我做事挺好的，但也没啥特别的", "score": 3},
            {"label": "D", "text": "没啥感觉，帮我做事而已，不用太感激", "score": 2},
            {"label": "E", "text": "有点尴尬，帮我做事干啥，不如夸我两句实在", "score": 1},
        ],
        "dimension": "acts_of_service",
        "reverse": False,
    },
    {
        "index": 7,
        "text": "对象说'你今天休息，家务我来做，你去躺平'，你啥感觉？",
        "options": [
            {"label": "A", "text": "感动到哭，TA让我休息帮我做家务，觉得被心疼", "score": 5},
            {"label": "B", "text": "挺感动的，觉得TA很体贴，会很开心去休息", "score": 4},
            {"label": "C", "text": "还行，帮我做家务挺好的，但也没啥特别的", "score": 3},
            {"label": "D", "text": "没啥感觉，做家务而已，不用太感激", "score": 2},
            {"label": "E", "text": "有点烦，做家务干啥，不如陪我深度聊聊实在", "score": 1},
        ],
        "dimension": "acts_of_service",
        "reverse": False,
    },

    # ===== 第9-10题：身体接触（测对肢体接触的敏感度）=====
    {
        "index": 8,
        "text": "对象突然抱住你，说'我就是想抱抱你'，你啥感觉？",
        "options": [
            {"label": "A", "text": "感动到哭，TA突然抱我，觉得被爱被需要", "score": 5},
            {"label": "B", "text": "挺开心的，觉得TA很黏我，会更想黏TA", "score": 4},
            {"label": "C", "text": "还行，抱一下挺好的，但也没啥特别的", "score": 3},
            {"label": "D", "text": "没啥感觉，抱一下而已，不用太在意", "score": 2},
            {"label": "E", "text": "有点尴尬，突然抱干啥，不如帮我解决麻烦事实在", "score": 1},
        ],
        "dimension": "physical_touch",
        "reverse": False,
    },
    {
        "index": 9,
        "text": "约会时对象一直牵着你的手，偶尔亲亲你的脸，你啥感觉？",
        "options": [
            {"label": "A", "text": "感动到哭，TA一直黏我，觉得被爱被重视", "score": 5},
            {"label": "B", "text": "挺开心的，觉得TA很黏我，约会会很甜", "score": 4},
            {"label": "C", "text": "还行，牵手亲亲挺好的，但也没啥特别的", "score": 3},
            {"label": "D", "text": "没啥感觉，牵手亲亲而已，不用太在意", "score": 2},
            {"label": "E", "text": "有点烦，一直黏干啥，不如深度聊聊三观实在", "score": 1},
        ],
        "dimension": "physical_touch",
        "reverse": False,
    },
]

# 极端标签机制（某种语言得分≥85）
EXTREME_LANGUAGE_TAGS = {
    "words_of_affirmation_high": {
        "threshold": 85,
        "tag": "彩虹屁大师认证",
        "description": "夸你你会感动到哭，对方赞美是你感受到被爱的最强信号 ✨",
    },
    "quality_time_high": {
        "threshold": 85,
        "tag": "深度对话控认证",
        "description": "陪你深度聊你会感动到哭，专注陪伴是你感受到被爱的最强信号 ✨",
    },
    "receiving_gifts_high": {
        "threshold": 85,
        "tag": "小心意收藏家认证",
        "description": "送你小心意你会感动到哭，物质象征是你感受到被爱的最强信号 ✨",
    },
    "acts_of_service_high": {
        "threshold": 85,
        "tag": "行动派爱人认证",
        "description": "帮你搞定麻烦事你会感动到哭，实际帮助是你感受到被爱的最强信号 ✨",
    },
    "physical_touch_high": {
        "threshold": 85,
        "tag": "黏贴型恋人认证",
        "description": "突然抱你你会感动到哭，肢体接触是你感受到被爱的最强信号 ✨",
    },
}

# 五种恋爱语言的标签和说明书（SBTI 毒舌风格）
LOVE_LANGUAGE_LABELS = {
    "words_of_affirmation": {
        "nickname": "无成本白嫖大师",
        "nickname_fun": "夸夸群群主",
        "tags": [
            "一句'宝你真好看'就能让你免费干三天家务",
            "只喜欢听好话",
            "嘴上说说比实际行动更让你心动",
            "恋爱里的白嫖爱好者",
            "别光听甜言蜜语也要看TA为你做了啥"
        ],
        "love_manual": {
            "how_to_love": [
                "多夸TA：夸TA的穿搭、夸TA的努力、夸TA的细心",
                "多鼓励：TA遇到困难时说'我相信你能搞定'",
                "多表达爱：嘴上说'我爱你''我心疼你''你很重要'",
                "注意：别只夸不行动，偶尔也要帮TA做事或送小心意",
            ],
            "red_flags": [
                "对象不夸你会让你觉得不被重视",
                "对象只行动不夸你会让你觉得没被看见",
                "吵架时TA沉默不说话会让你更难受",
            ],
            "sweet_points": [
                "对象夸你你会瞬间软化",
                "对象说'我心疼你'你会感动到哭",
                "吵架时TA哄你说好听的话你会瞬间原谅",
            ],
            # 新增：惹毛该人格的100种死法
            "piss_off_guide": [
                "TA深度聊人生三观时，回一句'哈哈，6'",
                "TA分享日常你只回'嗯'",
                "吵架时沉默不说话让TA更难受"
            ],
            "match_suggestion": "找个愿意夸你表达爱的对象，但也学会欣赏TA的实际行动——人家可能嘴笨但心诚",
        },
    },
    "quality_time": {
        "nickname": "网瘾戒断所教官",
        "nickname_fun": "专注陪伴派",
        "tags": [
            "约会时敢看一眼手机，你今天就别想活着走出这家餐厅",
            "需要很多专注的陪伴",
            "放下手机专心陪比送礼物更让你心动",
            "恋爱里的网瘾戒断所",
            "别光要陪伴也要看TA为你做了啥"
        ],
        "love_manual": {
            "how_to_love": [
                "放下手机：专心陪TA，不看手机不接工作电话",
                "深度聊：聊三观、聊未来、聊梦想、聊内心",
                "专注陪伴：约会时专心陪TA，不被打扰",
                "注意：别只陪不表达，偶尔也要夸TA或抱TA",
            ],
            "red_flags": [
                "对象玩手机不陪你会让你觉得不被重视",
                "对象各玩各的不深度聊会让你觉得没灵魂",
                "约会时TA一直看手机会让你很失望",
            ],
            "sweet_points": [
                "对象放下手机陪你你会感动到哭",
                "对象深度聊三观你会觉得灵魂被看见",
                "约会时TA专心陪你你会很开心",
            ],
            # 新增：惹毛该人格的100种死法
            "piss_off_guide": [
                "约会时一直看手机不接工作电话",
                "各玩各的不深度聊让你觉得没灵魂",
                "陪TA时玩手机让TA觉得很失望"
            ],
            "match_suggestion": "找个愿意放下手机专心陪你的对象，但也学会欣赏TA的其他表达方式——人家可能不善表达但行动实在",
        },
    },
    "receiving_gifts": {
        "nickname": "人形吞金兽",
        "nickname_fun": "礼品回收站",
        "tags": [
            "不要问TA爱不爱你，看你送的包是不是限定款",
            "需要很多物质象征",
            "小礼物比甜言蜜语更让你心动",
            "恋爱里的吞金兽",
            "别光要物质也要看TA为你做了啥"
        ],
        "love_manual": {
            "how_to_love": [
                "送小心意：TA喜欢的零食、小饰品、纪念物",
                "纪念日礼物：精心准备有意义的礼物（不一定要贵）",
                "惊喜礼物：突然送TA小礼物让TA开心",
                "注意：别只送不陪，偶尔也要专心陪TA或夸TA",
            ],
            "red_flags": [
                "对象不送你会让你觉得不被重视",
                "纪念日没礼物会让你很失望",
                "对象觉得送东西没用会让你委屈",
            ],
            "sweet_points": [
                "对象送你小心意你会感动到哭",
                "纪念日TA精心准备礼物你会很开心",
                "TA记得你喜欢啥会让你觉得被用心对待",
            ],
            # 新增：惹毛该人格的100种死法
            "piss_off_guide": [
                "纪念日没礼物让TA很失望",
                "送的东西不是限定款让TA觉得不被重视",
                "觉得送东西没用让TA委屈"
            ],
            "match_suggestion": "找个愿意送你小礼物的对象，但也学会欣赏TA的其他表达方式——人家可能不送礼但陪伴实在",
        },
    },
    "acts_of_service": {
        "nickname": "巨婴饲养员",
        "nickname_fun": "实际帮助派",
        "tags": [
            "核心需求是找个能帮TA通马桶交电费的爹系妈系工具人",
            "需要很多实际帮助",
            "实际行动比甜言蜜语更让你心动",
            "恋爱里的巨婴饲养员",
            "别光要行动也要看TA为你说了啥"
        ],
        "love_manual": {
            "how_to_love": [
                "帮TA做事：帮TA搞定麻烦事、帮TA做家务、帮TA解决问题",
                "主动帮忙：TA累的时候主动说'我来做你去休息'",
                "实际行动：别光说爱，用行动证明",
                "注意：别只帮不表达，偶尔也要夸TA或陪TA",
            ],
            "red_flags": [
                "对象不帮你会让你觉得不被心疼",
                "TA光说爱不做事会让你觉得没诚意",
                "你累的时候TA不帮忙会让你很失望",
            ],
            "sweet_points": [
                "对象帮你搞定麻烦事你会感动到哭",
                "TA说'我来做你去休息'你会很开心",
                "你累的时候TA主动帮忙你会觉得很贴心",
            ],
            # 新增：惹毛该人格的100种死法
            "piss_off_guide": [
                "光说爱不做事让TA觉得没诚意",
                "TA累的时候不帮忙让TA很失望",
                "不帮TA搞定麻烦事让TA觉得不被心疼"
            ],
            "match_suggestion": "找个愿意帮你做事的对象，但也学会欣赏TA的其他表达方式——人家可能不做事但嘴甜实在",
        },
    },
    "physical_touch": {
        "nickname": "人形章鱼",
        "nickname_fun": "皮肤饥渴症",
        "tags": [
            "夏天体温39度也必须像胶水一样粘在对方身上",
            "需要很多肢体接触",
            "抱抱贴贴是让你开心最快的方式",
            "恋爱里的章鱼",
            "别光要肢体接触也要看TA为你做了啥"
        ],
        "love_manual": {
            "how_to_love": [
                "多抱抱：突然抱TA说'我就是想抱你'",
                "多贴贴：约会时牵手、亲亲、黏着TA",
                "肢体接触：用肢体表达爱，不只是嘴上说",
                "注意：别只黏不表达，偶尔也要夸TA或陪TA深度聊",
            ],
            "red_flags": [
                "对象不黏你会让你觉得不被爱",
                "TA不抱你你会觉得冷淡",
                "约会时TA不牵手你会很失望",
            ],
            "sweet_points": [
                "对象突然抱你你会感动到哭",
                "约会时TA一直黏你你会很开心",
                "TA用肢体表达爱你会觉得很甜",
            ],
            # 新增：惹毛该人格的100种死法
            "piss_off_guide": [
                "约会时不牵手让TA很失望",
                "不黏TA让TA觉得冷淡",
                "不抱TA让TA觉得不被爱"
            ],
            "match_suggestion": "找个愿意黏你的对象，但也学会欣赏TA的其他表达方式——人家可能不黏但做事实在",
        },
    },
}

# 小雅专属回复内容（SBTI 毒舌判官风格——互联网嘴替/闺蜜判官）
XIAOYA_LOVE_LANGUAGE_MESSAGES = {
    "words_of_affirmation": {
        "greeting": "测出来了，你是「无成本白嫖大师」。🎉",
        "identity": "一句'宝你真好看'就能让你免费干三天家务。",
        "quirk": "恋爱中的你就像个白嫖爱好者，对象夸你'今天真好看'你会感动到哭，对象说'辛苦了我心疼你'你会瞬间软化。夸你是让TA开心最快的方式——零成本高效益。",
        "crush": "暗恋时的你：对象夸你一句你开心一整天，对象不夸你你觉得TA不爱你。但实际操作：继续装死，等TA先夸你。醒醒，人家可能只是不善表达。",
        "breakup": "分手后的你：前1周难过到窒息，第2周脑补TA从来没夸过你，第3周'我值得被夸'，然后用半年时间慢慢放下。",
        "suggestion": "💡 判官判词：下次遇到心动的人，别只等TA夸你，学会欣赏TA的实际行动。别光听甜言蜜语也要看TA为你做了啥——人家可能嘴笨但心诚。",
    },
    "quality_time": {
        "greeting": "测出来了，你是「网瘾戒断所教官」。🎉",
        "identity": "约会时敢看一眼手机，你今天就别想活着走出这家餐厅。",
        "quirk": "恋爱中的你就像个网瘾戒断所，对象放下手机陪你聊三观你会感动到哭，对象说'周末专心陪你'你会瞬间软化。放下手机专心陪是让TA开心最快的方式。",
        "crush": "暗恋时的你：对象陪你深度聊你开心一整天，对象玩手机不陪你你觉得TA不爱你。但实际操作：继续装死，等TA先放下手机。醒醒，人家可能只是需要放松。",
        "breakup": "分手后的你：前1周难过到窒息，第2周脑补TA从来没深度陪你，第3周'我值得被专心陪'，然后用半年时间慢慢放下。",
        "suggestion": "💡 判官判词：下次遇到心动的人，别只等TA放下手机，学会欣赏TA的其他表达方式。别光要陪伴也要看TA为你做了啥——人家可能不善表达但行动实在。",
    },
    "receiving_gifts": {
        "greeting": "测出来了，你是「人形吞金兽」。🎉",
        "identity": "不要问TA爱不爱你，看你送的包是不是限定款。",
        "quirk": "恋爱中的你就像个吞金兽，对象送你小心意你会感动到哭，纪念日TA精心准备礼物你会瞬间软化。送小心意是让TA开心最快的方式——但别光要物质要看TA为你做了啥。",
        "crush": "暗恋时的你：对象送你小礼物你开心一整天，对象不送你觉得TA不爱你。但实际操作：继续装死，等TA先送你。醒醒，人家可能只是不善送礼。",
        "breakup": "分手后的你：前1周难过到窒息，第2周脑补TA从来没送过你，第3周'我值得被送礼物'，然后用半年时间慢慢放下。",
        "suggestion": "💡 判官判词：下次遇到心动的人，别只等TA送礼物，学会欣赏TA的其他表达方式。别光要物质也要看TA为你做了啥——人家可能不送礼但陪伴实在。",
    },
    "acts_of_service": {
        "greeting": "测出来了，你是「巨婴饲养员」。🎉",
        "identity": "核心需求是找个能帮你通马桶交电费的爹系妈系工具人。",
        "quirk": "恋爱中的你就像个巨婴饲养员，对象帮你搞定麻烦事你会感动到哭，TA说'我来做你去休息'你会瞬间软化。帮TA做事是让TA开心最快的方式——但别光要行动要看TA为你说了啥。",
        "crush": "暗恋时的你：对象帮你做事你开心一整天，对象不帮你你觉得TA不爱你。但实际操作：继续装死，等TA先帮你。醒醒，人家可能只是不善动手。",
        "breakup": "分手后的你：前1周难过到窒息，第2周脑补TA从来没帮过你，第3周'我值得被帮'，然后用半年时间慢慢放下。",
        "suggestion": "💡 判官判词：下次遇到心动的人，别只等TA帮你做事，学会欣赏TA的其他表达方式。别光要行动也要看TA为你说了啥——人家可能不做事但嘴甜实在。",
    },
    "physical_touch": {
        "greeting": "测出来了，你是「人形章鱼」。🎉",
        "identity": "夏天体温39度也必须像胶水一样粘在对方身上。",
        "quirk": "恋爱中的你就像个章鱼，对象突然抱你你会感动到哭，约会时TA一直黏你你会瞬间软化。抱抱贴贴是让TA开心最快的方式——但别光要肢体接触要看TA为你做了啥。",
        "crush": "暗恋时的你：对象抱你你开心一整天，对象不黏你觉得TA不爱你。但实际操作：继续装死，等TA先抱你。醒醒，人家可能只是不善黏人。",
        "breakup": "分手后的你：前1周难过到窒息，第2周脑补TA从来没黏过你，第3周'我值得被黏'，然后用半年时间慢慢放下。",
        "suggestion": "💡 判官判词：下次遇到心动的人，别只等TA黏你，学会欣赏TA的其他表达方式。别光要肢体接触也要看TA为你做了啥——人家可能不黏但做事实在。",
    },
}


def get_question(index: int) -> dict[str, Any] | None:
    """获取指定索引的题目"""
    if 0 <= index < len(LOVE_LANGUAGE_QUESTIONS):
        return LOVE_LANGUAGE_QUESTIONS[index]
    return None


def get_dimension_for_question(index: int) -> str | None:
    """获取题目所属的维度（恋爱语言）"""
    question = get_question(index)
    if question:
        return str(question.get("dimension") or "")
    return None


def calculate_language_score(answers: list[int], language: str) -> float:
    """计算某个恋爱语言的得分（0-100分）"""
    start, end = LOVE_LANGUAGE_QUESTION_RANGES.get(language, (0, 0))
    if start == end:
        return 0.0
    language_answers = answers[start:end]
    if not language_answers:
        return 0.0

    total = sum(language_answers)
    score = (total - 2) / 8 * 100  # 2分(最低)→0分, 10分(最高)→100分

    return round(max(0, min(100, score)), 1)


def calculate_all_language_scores(answers: list[int]) -> dict[str, float]:
    """计算所有恋爱语言的得分"""
    return {
        language: calculate_language_score(answers, language)
        for language in LOVE_LANGUAGES
    }


def get_language_ranking(scores: dict[str, float]) -> list[dict[str, Any]]:
    """获取恋爱语言排序（TOP5）"""
    sorted_languages = sorted(
        scores.items(),
        key=lambda x: x[1],
        reverse=True
    )
    ranking = []
    for idx, (language, score) in enumerate(sorted_languages):
        language_info = LOVE_LANGUAGE_LABELS.get(language, {})
        ranking.append({
            "rank": idx + 1,
            "language": language,
            "language_name": LOVE_LANGUAGE_NAMES[language],
            "score": score,
            "nickname": language_info.get("nickname", language),
            "level": "high" if score >= 70 else "medium" if score >= 40 else "low",
        })
    return ranking


def get_primary_love_language(scores: dict[str, float]) -> str:
    """判断主要恋爱语言（得分最高的语言）"""
    if not scores:
        return "words_of_affirmation"
    return max(scores, key=scores.get)


def get_language_feedback(language: str, score: float) -> str:
    """获取恋爱语言反馈文案"""
    feedbacks = LOVE_LANGUAGE_FEEDBACKS.get(language, {})
    if score >= 70:
        return str(feedbacks.get("high", ""))
    if score >= 40:
        return str(feedbacks.get("medium", ""))
    return str(feedbacks.get("low", ""))


def get_extreme_language_tags(scores: dict[str, float]) -> list[dict[str, str]]:
    """计算极端标签（某种语言得分≥85）"""
    extreme_tags = []
    for language in LOVE_LANGUAGES:
        score = scores.get(language, 0)
        high_key = f"{language}_high"
        if high_key in EXTREME_LANGUAGE_TAGS and score >= EXTREME_LANGUAGE_TAGS[high_key]["threshold"]:
            extreme_tags.append({
                "tag": EXTREME_LANGUAGE_TAGS[high_key]["tag"],
                "description": EXTREME_LANGUAGE_TAGS[high_key]["description"],
            })
    return extreme_tags


def get_language_info(language: str) -> dict[str, Any]:
    """获取恋爱语言标签和说明书"""
    return LOVE_LANGUAGE_LABELS.get(
        language,
        {
            "nickname": LOVE_LANGUAGE_NAMES[language],
            "tags": [f"恋爱语言:{LOVE_LANGUAGE_NAMES[language]}"],
            "love_manual": {
                "how_to_love": ["用这种语言表达爱对方会很开心"],
                "red_flags": ["对方不用这种语言会让你失望"],
                "sweet_points": ["对方用这种语言你会感动"],
                "match_suggestion": "找个能用你的语言表达爱的对象",
            },
        },
    )


def _interpretation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    """生成恋爱密码式解读（不强调类型标签）

    核心转变：
    - 从"你的主恋爱语言是XX"转向"你最敏感的爱的信号"
    - 从"TOP3排序"转向"敏感信号 vs 不敏感信号"
    - 从"如何让TA开心"转向"让对方感受到爱 vs 对方不懂你的信号"
    """
    scores = dict(result.get("scores") or {})
    ranking = get_language_ranking(scores)
    primary_language = str(result.get("primary_language") or get_primary_love_language(scores))
    primary_info = get_language_info(primary_language)

    # 获取五种语言的得分
    words_score = scores.get("words_of_affirmation", 50)
    time_score = scores.get("quality_time", 50)
    gifts_score = scores.get("receiving_gifts", 50)
    acts_score = scores.get("acts_of_service", 50)
    touch_score = scores.get("physical_touch", 50)

    # 极端标签（轻量融入，不再高亮）
    extreme_tags = get_extreme_language_tags(scores)

    # 构建恋爱密码描述（根据主要语言）
    summary = "你很在意对方怎么表达爱。"

    # 找出最敏感和不敏感的信号
    sorted_languages = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    most_sensitive = sorted_languages[0]
    least_sensitive = sorted_languages[-1]

    # 根据最敏感的语言生成描述
    if most_sensitive[1] >= 85:
        summary += f"{LOVE_LANGUAGE_NAMES[most_sensitive[0]]}让你最心动，对方用这种方式表达爱你会感动到哭。"
    elif most_sensitive[1] >= 70:
        summary += f"{LOVE_LANGUAGE_NAMES[most_sensitive[0]]}让你很开心，对方用这种方式表达爱你会觉得很被爱。"
    else:
        summary += "你对各种表达方式都比较平衡，没有特别敏感或不敏感的。"

    # 最敏感的爱的信号
    sensitive_signals = "\n\n**🎯 你最敏感的爱的信号：**\n"
    for i, (lang, score) in enumerate(sorted_languages[:3]):
        lang_name = LOVE_LANGUAGE_NAMES[lang]
        lang_info = LOVE_LANGUAGE_LABELS.get(lang, {})
        nickname = lang_info.get("nickname", lang_name)

        sensitive_signals += f"\n{lang_name}（{score}分敏感）\n"

        # 根据语言类型给出具体描述
        if lang == "words_of_affirmation":
            if score >= 85:
                sensitive_signals += "夸你你会感动到哭，这是让你最感受到被爱的信号。\n彩虹屁大师认证 ✨"
            elif score >= 70:
                sensitive_signals += "对方夸你你会很开心，这是你感受到被爱的重要信号。"
            else:
                sensitive_signals += "对方夸你你觉得还行，没有特别心动。"
        elif lang == "quality_time":
            if score >= 85:
                sensitive_signals += "对方陪你深度聊你会感动到哭，这是让你最感受到被爱的信号。\n深度对话控认证 ✨"
            elif score >= 70:
                sensitive_signals += "对方陪你深度聊你会很开心，这是你感受到被爱的重要信号。"
            else:
                sensitive_signals += "对方陪你你觉得还行，没有特别心动。"
        elif lang == "receiving_gifts":
            if score >= 85:
                sensitive_signals += "对方送你小心意你会感动到哭，这是让你最感受到被爱的信号。\n小心意收藏家认证 ✨"
            elif score >= 70:
                sensitive_signals += "对方送你小心意你会很开心，这是你感受到被爱的重要信号。"
            else:
                sensitive_signals += "对方送你小心意你觉得还行，没有特别心动。"
        elif lang == "acts_of_service":
            if score >= 85:
                sensitive_signals += "对方帮你搞定麻烦事你会感动到哭，这是让你最感受到被爱的信号。\n行动派爱人认证 ✨"
            elif score >= 70:
                sensitive_signals += "对方帮你做事你会很开心，这是你感受到被爱的重要信号。"
            else:
                sensitive_signals += "对方帮你做事你觉得还行，没有特别心动。"
        elif lang == "physical_touch":
            if score >= 85:
                sensitive_signals += "对方突然抱你你会感动到哭，这是让你最感受到被爱的信号。\n黏贴型恋人认证 ✨"
            elif score >= 70:
                sensitive_signals += "对方抱你你会很开心，这是你感受到被爱的重要信号。"
            else:
                sensitive_signals += "对方抱你你觉得还行，没有特别心动。"

    # 不敏感的信号
    insensitive_signals = "\n\n**💬 你不敏感的信号：**\n"
    for i, (lang, score) in enumerate(sorted_languages[-2:]):
        lang_name = LOVE_LANGUAGE_NAMES[lang]

        insensitive_signals += f"\n{lang_name}（{score}分）\n"

        # 根据语言类型给出具体描述
        if lang == "words_of_affirmation":
            if score <= 15:
                insensitive_signals += "对方夸你你觉得没啥，不如帮你解决麻烦事实在。"
            else:
                insensitive_signals += "对方夸你你觉得没啥，不如实际陪伴实在。"
        elif lang == "quality_time":
            if score <= 15:
                insensitive_signals += "对方陪你深度聊你觉得没啥，不如帮你解决麻烦事实在。"
            else:
                insensitive_signals += "对方陪你你觉得没啥，不如独立做事实在。"
        elif lang == "receiving_gifts":
            if score <= 15:
                insensitive_signals += "对方送你小心意你觉得没啥，不如帮你解决麻烦事实在。"
            else:
                insensitive_signals += "对方送你小心意你觉得没啥，不如实际陪伴实在。"
        elif lang == "acts_of_service":
            if score <= 15:
                insensitive_signals += "对方帮你做事你觉得没啥，不如夸你两句实在。"
            else:
                insensitive_signals += "对方帮你做事你觉得没啥，不如深度聊聊三观实在。"
        elif lang == "physical_touch":
            if score <= 15:
                insensitive_signals += "对方抱你你觉得没啥，不如深度聊聊三观实在。肢体接触不敏感认证 ✨"
            else:
                insensitive_signals += "对方抱你你觉得没啥，不如实际陪伴实在。"

    # 让对方感受到你的爱（根据主语言）
    express_love = "\n\n**💝 让对方感受到你的爱：**\n"
    if primary_language == "words_of_affirmation":
        express_love += "多夸TA、多鼓励TA，TA遇到困难说「我相信你能搞定」，TA分享日常要认真回应不要只回「嗯」。"
    elif primary_language == "quality_time":
        express_love += "放下手机专心陪TA，陪TA深度聊三观、聊未来、聊梦想，约会时不看手机不接工作电话。"
    elif primary_language == "receiving_gifts":
        express_love += "送TA小心意（TA喜欢的零食、小饰品），纪念日精心准备有意义的礼物（不一定要贵）。"
    elif primary_language == "acts_of_service":
        express_love += "帮TA搞定麻烦事，TA累的时候主动说「我来做你去休息」，用行动证明爱。"
    elif primary_language == "physical_touch":
        express_love += "突然抱TA说「我就是想抱你」，约会时牵手亲亲黏着TA，用肢体表达爱。"

    # 对方不懂你的信号（根据主语言）
    misunderstood_signals = "\n\n**⚠️ 对方不懂你的信号：**\n"
    if primary_language == "words_of_affirmation":
        misunderstood_signals += "TA不夸你你会觉得不被爱，TA光做事不夸你会觉得没被看见，TA沉默不说话你会更难受。"
    elif primary_language == "quality_time":
        misunderstood_signals += "TA玩手机不陪你会让你觉得不被重视，TA各玩各的不深度聊会让你觉得没灵魂，约会时TA一直看手机会让你很失望。"
    elif primary_language == "receiving_gifts":
        misunderstood_signals += "TA不送你会让你觉得不被重视，纪念日没礼物会让你很失望，TA觉得送东西没用会让你委屈。"
    elif primary_language == "acts_of_service":
        misunderstood_signals += "TA不帮你会让你觉得不被心疼，TA光说爱不做事会让你觉得没诚意，你累的时候TA不帮忙会让你很失望。"
    elif primary_language == "physical_touch":
        misunderstood_signals += "TA不黏你会让你觉得不被爱，TA不抱你你会觉得冷淡，约会时TA不牵手你会很失望。"

    # 具体场景建议
    specific_scenarios = "\n\n**💌 具体场景建议：**\n"
    love_manual = primary_info["love_manual"]

    # 日常相处
    specific_scenarios += "\n✅ 日常相处：\n"
    for suggestion in love_manual["how_to_love"][:2]:
        specific_scenarios += f"   - {suggestion}\n"

    # 冲突场景
    if "love_red_flags" in love_manual:
        specific_scenarios += "\n⚠️ 冲突场景：\n"
        for flag in love_manual["love_red_flags"][:1]:
            specific_scenarios += f"   - {flag}\n"

    # 脱单免责声明
    disclaimer = "\n\n**【使用本说明书的脱单安全须知】**\n"
    disclaimer += "【储藏条件】 建议放置在能用你的恋爱语言表达爱的环境中。\n"
    disclaimer += "【不良反应】 强行配对可能会导致恋爱语言不通鸡同鸭讲。\n"
    disclaimer += "【红娘提示】 说明书仅供脱单参考，吵架时请勿将本报告作为呈堂证供。"

    return {
        "summary": summary,
        "sensitive_signals": sensitive_signals,
        "insensitive_signals": insensitive_signals,
        "express_love": express_love,
        "misunderstood_signals": misunderstood_signals,
        "specific_scenarios": specific_scenarios,
        "extreme_tags": extreme_tags,  # 保留但不再高亮
        "ranking": ranking,  # 保留排序数据用于前端展示
        "disclaimer": disclaimer,
    }


def xiaoya_message_from_result(result: dict[str, Any]) -> str:
    """生成小雅风格的恋爱语言解读消息。"""
    scores = dict(result.get("scores") or {})
    primary_language = str(result.get("primary_language") or get_primary_love_language(scores))
    primary_info = get_language_info(primary_language)
    ranking = get_language_ranking(scores)
    top3 = ranking[:3]
    bottom2 = ranking[-2:]
    love_manual = primary_info.get("love_manual", {})

    if primary_language == "words_of_affirmation":
        pattern = "你对“被看见、被肯定、被认真回应”特别敏感，话说对了，你会很快软下来。"
        match = "最适合你的人，通常不是只会做事的人，而是愿意表达、愿意确认、也愿意把喜欢说出来的人。"
        risk = "你最容易误判的，是把“不擅长表达”直接等同于“不够爱你”。"
    elif primary_language == "quality_time":
        pattern = "你真正要的不是陪着而已，而是对方把注意力、时间和情绪都给到你。"
        match = "最适合你的人，通常愿意腾出完整时间陪你，也愿意认真聊关系、聊感受、聊未来。"
        risk = "你最容易受伤的点，是对方人在你旁边，但心根本没在场。"
    elif primary_language == "receiving_gifts":
        pattern = "你在意的从来不只是礼物本身，而是那种“我被惦记、被郑重对待”的感觉。"
        match = "最适合你的人，通常会记得细节，愿意花心思准备小惊喜，也懂仪式感对你的意义。"
        risk = "你最容易委屈的点，是对方觉得这些都不重要，但你会把它理解成不够上心。"
    elif primary_language == "acts_of_service":
        pattern = "你判断爱意时很看行动，谁愿意替你分担、替你落地，你就会觉得这个人靠谱。"
        match = "最适合你的人，通常执行力强，愿意照顾细节，也会在你累的时候主动顶上。"
        risk = "你最容易失望的点，是对方嘴上很会说，但关键时刻总是没动作。"
    else:
        pattern = "你对身体靠近和真实触感特别敏感，抱抱、牵手、靠近，对你来说都不是小事。"
        match = "最适合你的人，通常不抗拒亲密接触，也愿意用身体语言表达喜欢和安抚。"
        risk = "你最容易误会的点，是对方没那么黏，你就会下意识觉得关系降温了。"

    message = "亲爱的，恋爱语言这题我也给你翻译一下。\n\n"
    message += f"你最主要的恋爱语言是 **{LOVE_LANGUAGE_NAMES[primary_language]}（{primary_info.get('nickname', '')}）**。\n"
    message += f"{pattern}\n\n"
    message += "**如果放进关系里看，你最容易被这些信号打动：**\n"
    for item in top3:
        message += f"- {item['language_name']}：{item['score']:.0f} 分，这基本就是你最容易感受到爱的通道\n"
    message += "\n"
    message += "**相对没那么打动你的信号：**\n"
    for item in bottom2:
        message += f"- {item['language_name']}：{item['score']:.0f} 分，如果对方只会这一套，你可能会觉得“也还好”\n"
    message += "\n"
    message += "**说匹配，我会这样建议你：**\n"
    message += f"- {match}\n"
    suggestion = str(love_manual.get("match_suggestion") or "")
    if suggestion:
        message += f"- 现实一点说：{suggestion.rstrip('。')}。\n"
    message += "\n"
    message += "**我给你的实战建议：**\n"
    if primary_language == "words_of_affirmation":
        advice = [
            "别只等对方来夸你，你也可以直接告诉对方，什么样的回应会让你感觉被爱。",
            "遇到嘴笨但行动稳定的人，先别急着判死刑，看看TA是不是在用别的方式对你好。",
            "你自己表达爱时，也别吝啬语言确认，这会让关系升温得很快。",
        ]
    elif primary_language == "quality_time":
        advice = [
            "你可以直接说你要的不是“在一起待着”，而是“认真陪我一会儿”。",
            "约会里如果你很在意专注度，提前讲清楚，比一个人默默失望更有用。",
            "也别只盯着陪伴时长，能不能深度连接，对你更重要。",
        ]
    elif primary_language == "receiving_gifts":
        advice = [
            "你可以直接告诉对方，你在意的是心意和被惦记，不一定非得贵。",
            "别把礼物这件事憋成委屈，仪式感对你重要，就坦白说。",
            "同时也记得看一眼，对方有没有用陪伴、行动或时间在认真对你。",
        ]
    elif primary_language == "acts_of_service":
        advice = [
            "你最吃行动，那就要学会把“我需要你帮我什么”说具体，对方才接得住。",
            "别默默记账，觉得TA不帮就是不爱，很多人不是不愿意，只是不知道你在等什么。",
            "你也很适合找那种说到做到的人，这会让你长期更有安全感。",
        ]
    else:
        advice = [
            "你可以直接告诉对方，你对肢体接触的需求是什么，不然对方很可能根本猜不到。",
            "别把对方偶尔不黏自动理解成冷淡，先看TA整体有没有在靠近你。",
            "你自己表达爱的时候，身体语言对你是优势，用好了很容易让关系变甜。",
        ]
    for index, item in enumerate(advice, start=1):
        message += f"{index}. {item}\n"
    message += "\n"
    message += f"**我再提醒你一个高频风险点：**\n{risk}\n\n"
    message += "你要是愿意，我下一条可以继续帮你拆：你最适合和哪种恋爱语言的人谈，最容易鸡同鸭讲的又是哪种。"
    return message


def calculate_love_language_match(
    user_a_scores: dict[str, float], user_b_scores: dict[str, float]
) -> dict[str, Any]:
    """计算两位用户的恋爱语言匹配度

    匹配规则：
    - 主语言相同 = 高分（互相能满足）
    - 主语言互补 = 中分（可以互相学习）
    - 主语言完全不同 = 低分（可能鸡同鸭讲）
    """
    match_score = 70.0  # 起始分
    dimension_analysis = {}

    a_primary = get_primary_love_language(user_a_scores)
    b_primary = get_primary_love_language(user_b_scores)

    a_top3 = [lang for lang, score in sorted(user_a_scores.items(), key=lambda x: x[1], reverse=True)[:3]]
    b_top3 = [lang for lang, score in sorted(user_b_scores.items(), key=lambda x: x[1], reverse=True)[:3]]

    # 主语言相同 = 高分
    if a_primary == b_primary:
        match_score += 20
        dimension_analysis["primary"] = f"主恋爱语言相同：你们都是{LOVE_LANGUAGE_NAMES[a_primary]}派，互相能满足"

    # 主语言在对方的TOP3里 = 中高分
    elif a_primary in b_top3 or b_primary in a_top3:
        match_score += 10
        dimension_analysis["primary"] = f"主语言在对方的TOP3：你们能互相理解对方的表达方式"

    # 主语言完全不同 = 低分
    else:
        match_score -= 15
        dimension_analysis["primary"] = f"主语言完全不同：可能鸡同鸭讲，需要学会对方的其他语言"

    # TOP3重合度高 = 高分
    common_languages = set(a_top3) & set(b_top3)
    if len(common_languages) >= 2:
        match_score += 15
        dimension_analysis["top3"] = f"TOP3重合度高：你们有{len(common_languages)}种语言重合"

    final_score = max(0, min(100, match_score))

    if final_score >= 85:
        analysis = "🌟 恋爱语言匹配度极高，你们很合适!"
    elif final_score >= 70:
        analysis = "💕 恋爱语言匹配度良好，你们可以尝试"
    elif final_score >= 50:
        analysis = "⚖️ 恋爱语言匹配度中等，需要多磨合多沟通"
    else:
        analysis = "⚠️ 恋爱语言匹配度较低，你们需要努力才能走到一起"

    return {
        "score": round(final_score, 1),
        "analysis": analysis,
        "dimension_analysis": dimension_analysis,
        "a_primary": a_primary,
        "b_primary": b_primary,
        "a_top3": a_top3,
        "b_top3": b_top3,
    }
