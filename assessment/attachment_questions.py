"""依恋风格测验题库（ECR 两维产品化版本）

底层逻辑：
- 只测两条核心维度：依恋焦虑（anxiety）/ 依恋回避（avoidance）
- 结果先输出两维连续分数，再解释为四象限倾向

外层表达：
- 保留 Her 的恋爱语境和口语化表达
- 不直接照搬学术原题
- 不用旧版强羞辱感标签
"""

from __future__ import annotations

from typing import Any

ATTACHMENT_DIMENSIONS = ["anxiety", "avoidance"]

# 兼容旧服务层循环用法；现在这里表示最终四象限结果，不再是独立计分维度
ATTACHMENT_TYPES = ["secure", "anxious", "avoidant", "fearful"]

ATTACHMENT_TYPE_NAMES = {
    "secure": "稳定靠近型",
    "anxious": "高敏确认型",
    "avoidant": "边界后撤型",
    "fearful": "拉扯矛盾型",
}

ATTACHMENT_QUESTION_RANGES = {
    "anxiety": (0, 6),
    "avoidance": (6, 12),
}

ATTACHMENT_FEEDBACKS = {
    "anxiety": {
        "high": "你对关系里的回应变化很敏感。对方一旦忽冷忽热、话少一点、状态不明，你会比很多人更快开始慌，也更想确认这段关系到底还稳不稳。",
        "medium": "你会被关系牵动，但不至于一点风吹草动就失控。只是在你真正在意的人面前，你还是会比表面看起来更需要确定感。",
        "low": "你的关系稳定感比较强。回应快慢、情绪波动这些事不会立刻把你带跑，通常你会先给对方和关系一点缓冲空间。",
    },
    "avoidance": {
        "high": "你不是没感觉，你只是很怕关系一下子贴太近。压力一上来、情绪一变重、对方想马上推进时，你会本能想往后退一点。",
        "medium": "你能靠近，也需要空间。关系顺的时候你没那么抗拒亲密，但一旦密度太高、节奏太快，你会开始需要自己的缓冲带。",
        "low": "你对亲密关系的靠近感并不排斥。被理解、被接近、被看见这件事，对你来说更多是自然发生，而不是需要立刻防御的压力。",
    },
}

ATTACHMENT_QUESTIONS: list[dict[str, Any]] = [
    {
        "index": 0,
        "text": "你们最近明显比之前更熟了。某天晚上，对方突然没有像前几天那样自然接住你的话，你心里最先冒出来的会更像哪一种？",
        "options": [
            {"label": "A", "text": "先当作只是节奏不一样，不会立刻往关系上想", "score": 1},
            {"label": "B", "text": "会注意到，但还能把心放回自己的事上", "score": 2},
            {"label": "C", "text": "会有点在意，开始留心是不是哪里不太一样了", "score": 3},
            {"label": "D", "text": "很容易一下子敏感起来，想知道是不是自己会错意了", "score": 4},
            {"label": "E", "text": "脑子已经开始回放前面所有细节，想确认是不是关系在变", "score": 5},
        ],
        "dimension": "anxiety",
        "reverse": False,
    },
    {
        "index": 1,
        "text": "你白天发了一条自己挺在意的消息，对方到晚上都没回。下面哪种更像你当时的内心戏？",
        "options": [
            {"label": "A", "text": "大概率是在忙，先放着，晚点再看", "score": 1},
            {"label": "B", "text": "会顺手多看几次，但不至于影响心情", "score": 2},
            {"label": "C", "text": "会慢慢开始想，是不是我这条消息哪里不太对", "score": 3},
            {"label": "D", "text": "会很容易往“是不是没那么想回我”上联想", "score": 4},
            {"label": "E", "text": "还没等对方回，我已经把最坏版本在脑子里演完了", "score": 5},
        ],
        "dimension": "anxiety",
        "reverse": False,
    },
    {
        "index": 2,
        "text": "前阵子一直是对方主动找你，这几天却明显安静下来。你通常会先怎么理解这个变化？",
        "options": [
            {"label": "A", "text": "先看现实情况，不急着往关系变冷上解释", "score": 1},
            {"label": "B", "text": "会有点在意，但更想先观察几天再说", "score": 2},
            {"label": "C", "text": "会开始琢磨，是不是你们之间的感觉有点变了", "score": 3},
            {"label": "D", "text": "很容易想到，是不是自己在对方那里的位置变轻了", "score": 4},
            {"label": "E", "text": "会被这个变化卡住，反复想是不是关系已经在往下掉", "score": 5},
        ],
        "dimension": "anxiety",
        "reverse": False,
    },
    {
        "index": 3,
        "text": "你们刚有过一点不愉快，对方之后一直没来接话、也没来缓和。你当下更接近哪种状态？",
        "options": [
            {"label": "A", "text": "先等等，觉得彼此都消化一下也正常", "score": 1},
            {"label": "B", "text": "会在意，但还能告诉自己先别放大", "score": 2},
            {"label": "C", "text": "会有点悬着，不确定这件事会不会越拖越糟", "score": 3},
            {"label": "D", "text": "会很容易慌起来，开始想是不是关系要出问题了", "score": 4},
            {"label": "E", "text": "这种没下文的状态会让我整个人都很难放松", "score": 5},
        ],
        "dimension": "anxiety",
        "reverse": False,
    },
    {
        "index": 4,
        "text": "关系升温到一个你开始认真看待的位置时，你会不会希望对方给出更明确的信号，让你知道“我们是在同一页上的”？",
        "options": [
            {"label": "A", "text": "不太需要，我更相信相处会自然把答案带出来", "score": 1},
            {"label": "B", "text": "偶尔会想确认，但不太会因此不安", "score": 2},
            {"label": "C", "text": "会有点想知道，只是未必会马上问出来", "score": 3},
            {"label": "D", "text": "会，我会更希望关系是清楚、能被确认的", "score": 4},
            {"label": "E", "text": "会，没有比较明确的回应，我很难真的松下来", "score": 5},
        ],
        "dimension": "anxiety",
        "reverse": False,
    },
    {
        "index": 5,
        "text": "如果你已经明显喜欢上一个人了，你觉得自己在这段关系里的状态通常会怎么变？",
        "options": [
            {"label": "A", "text": "喜欢会让我投入，但不太会直接影响安全感", "score": 1},
            {"label": "B", "text": "偶尔会更敏感一点，但整体还算稳", "score": 2},
            {"label": "C", "text": "会有一些变化，越在意越容易被牵动", "score": 3},
            {"label": "D", "text": "会，我在重要关系里通常比平时更容易慌", "score": 4},
            {"label": "E", "text": "会，而且这种起伏不是靠转移注意力就能轻松过去的", "score": 5},
        ],
        "dimension": "anxiety",
        "reverse": False,
    },
    {
        "index": 6,
        "text": "对方进入状态很快，想每天都聊、频繁见面，也会主动把关系往更近的方向推。你当下更接近哪种感觉？",
        "options": [
            {"label": "A", "text": "挺自然的，关系变近对我来说通常是舒服的", "score": 1},
            {"label": "B", "text": "可以接受，只是我偶尔也想保留自己的节奏", "score": 2},
            {"label": "C", "text": "会开始有点压力，想慢一点看看", "score": 3},
            {"label": "D", "text": "会本能想把距离拉开一点，不想被推太快", "score": 4},
            {"label": "E", "text": "只要密度一高起来，我就会先想退一退再说", "score": 5},
        ],
        "dimension": "avoidance",
        "reverse": False,
    },
    {
        "index": 7,
        "text": "某次聊天，对方认真问到了你那些平时不太会拿出来讲的脆弱和难处。你更容易先出现哪种反应？",
        "options": [
            {"label": "A", "text": "如果关系值得，我愿意慢慢把真实的一面打开", "score": 1},
            {"label": "B", "text": "能聊，只是会需要一点适应和铺垫", "score": 2},
            {"label": "C", "text": "会犹豫，不知道讲到哪里才算刚刚好", "score": 3},
            {"label": "D", "text": "会明显起防备，太快被看透会让我不舒服", "score": 4},
            {"label": "E", "text": "会本能把门关回去，不太想让人一下子靠这么近", "score": 5},
        ],
        "dimension": "avoidance",
        "reverse": False,
    },
    {
        "index": 8,
        "text": "吵起来的时候，对方一直追着问“你现在到底怎么想”。如果当下情绪很满，你通常会先怎么做？",
        "options": [
            {"label": "A", "text": "只要方式别太冲，我通常还愿意留在现场把话说完", "score": 1},
            {"label": "B", "text": "会觉得有点累，但大多还能继续聊下去", "score": 2},
            {"label": "C", "text": "会开始想先暂停，不太想在当下被逼着说很多", "score": 3},
            {"label": "D", "text": "会明显想后退，越被追问越不想开口", "score": 4},
            {"label": "E", "text": "我会直接把自己关掉，只想先离开那个情境", "score": 5},
        ],
        "dimension": "avoidance",
        "reverse": False,
    },
    {
        "index": 9,
        "text": "关系进入一个很黏、联系很高频、很多事情都想一起分享和同步的阶段时，你通常会更接近哪种状态？",
        "options": [
            {"label": "A", "text": "能适应，亲密关系有这种阶段对我来说不算负担", "score": 1},
            {"label": "B", "text": "大体没问题，只是偶尔也想给自己留一点喘口气的空间", "score": 2},
            {"label": "C", "text": "会开始担心自己是不是要一直维持这么高的投入", "score": 3},
            {"label": "D", "text": "会有点像被关系包得太满，想拉开一点距离", "score": 4},
            {"label": "E", "text": "我会本能往后退，不然整个人都会变得很紧绷", "score": 5},
        ],
        "dimension": "avoidance",
        "reverse": False,
    },
    {
        "index": 10,
        "text": "有一天对方突然很认真地想和你聊未来、依赖、边界、彼此需要什么。你听到这类话题时更接近哪种感受？",
        "options": [
            {"label": "A", "text": "可以聊，这类话题通常会让我觉得关系更清楚", "score": 1},
            {"label": "B", "text": "能聊，但我会希望有一点准备和缓冲", "score": 2},
            {"label": "C", "text": "会有些压力，怕一认真起来气氛就变得很重", "score": 3},
            {"label": "D", "text": "会想先躲一下，这种深入会让我不太自在", "score": 4},
            {"label": "E", "text": "会很想把话题带开，不想被推进到那么里面", "score": 5},
        ],
        "dimension": "avoidance",
        "reverse": False,
    },
    {
        "index": 11,
        "text": "就算这段关系已经很重要了，你在很多事上会不会还是习惯给自己留一手，不太愿意把重心完全交给对方？",
        "options": [
            {"label": "A", "text": "不会特别防着，重要的人本来就可以互相依靠", "score": 1},
            {"label": "B", "text": "会留一点自己的空间，但不太影响投入", "score": 2},
            {"label": "C", "text": "多少会，我习惯先给自己留一点余地", "score": 3},
            {"label": "D", "text": "会，我不太习惯把很多重心真的交到关系里", "score": 4},
            {"label": "E", "text": "会，而且这种先保留自己的习惯很难一下子放掉", "score": 5},
        ],
        "dimension": "avoidance",
        "reverse": False,
    },
]

ATTACHMENT_TYPE_LABELS = {
    "secure": {
        "nickname": "稳定靠近型",
        "nickname_fun": "稳稳接住派",
        "tags": [
            "关系里不容易乱猜",
            "能靠近也能给空间",
            "被在乎时能接得住",
            "冲突里不容易先失控",
        ],
    },
    "anxious": {
        "nickname": "高敏确认型",
        "nickname_fun": "回应雷达开很满",
        "tags": [
            "很在意关系有没有持续回应",
            "忽冷忽热会很消耗你",
            "越喜欢越容易被牵动",
            "清楚和稳定会让你安心",
        ],
    },
    "avoidant": {
        "nickname": "边界后撤型",
        "nickname_fun": "先缓一下派",
        "tags": [
            "压力一来会先往后退",
            "需要空间才能重新靠近",
            "不喜欢被情绪追着跑",
            "越被逼越容易沉默",
        ],
    },
    "fearful": {
        "nickname": "拉扯矛盾型",
        "nickname_fun": "想靠近也想自保",
        "tags": [
            "既怕失去也怕太近",
            "很在乎但不容易安稳",
            "关系里容易反复拉扯",
            "需要被理解也需要被放松",
        ],
    },
}


def get_question(index: int) -> dict[str, Any] | None:
    if 0 <= index < len(ATTACHMENT_QUESTIONS):
        return ATTACHMENT_QUESTIONS[index]
    return None


def get_dimension_for_question(index: int) -> str | None:
    question = get_question(index)
    if question:
        return str(question.get("dimension") or "")
    return None


def calculate_dimension_score(answers: list[int], dimension: str) -> float:
    start, end = ATTACHMENT_QUESTION_RANGES.get(dimension, (0, 0))
    if start == end:
        return 0.0
    dimension_answers = answers[start:end]
    if not dimension_answers:
        return 0.0
    total = sum(dimension_answers)
    min_total = len(dimension_answers)
    max_total = len(dimension_answers) * 5
    score = ((total - min_total) / (max_total - min_total)) * 100
    return round(max(0, min(100, score)), 1)


def calculate_all_scores(answers: list[int]) -> dict[str, float]:
    return {
        dimension: calculate_dimension_score(answers, dimension)
        for dimension in ATTACHMENT_DIMENSIONS
    }


def get_dimension_feedback(dimension: str, score: float) -> str:
    feedbacks = ATTACHMENT_FEEDBACKS.get(dimension, {})
    if score >= 70:
        return str(feedbacks.get("high", ""))
    if score >= 40:
        return str(feedbacks.get("medium", ""))
    return str(feedbacks.get("low", ""))


def get_extreme_tags(scores: dict[str, float]) -> list[dict[str, str]]:
    tags: list[dict[str, str]] = []
    anxiety = float(scores.get("anxiety", 50))
    avoidance = float(scores.get("avoidance", 50))

    if anxiety >= 80:
        tags.append({"tag": "回应敏感", "description": "关系一旦重要起来，你会很快从回应变化里感觉到风向不对。"})
    elif anxiety <= 20:
        tags.append({"tag": "稳定感在线", "description": "你不太会被一点点回应波动牵着跑，关系里的基础稳定感比较强。"})

    if avoidance >= 80:
        tags.append({"tag": "边界警觉", "description": "一旦关系密度太高、压力太满，你会本能想先把自己往后撤一点。"})
    elif avoidance <= 20:
        tags.append({"tag": "靠近自如", "description": "被理解、被接近、被看见这件事，对你来说整体是可承接的。"})

    if anxiety >= 70 and avoidance >= 70:
        tags.append({"tag": "拉扯感明显", "description": "你既容易被关系牵动，也容易在压力大时先自我保护。"})

    return tags


def get_primary_attachment_type(scores: dict[str, float]) -> str:
    anxiety = float(scores.get("anxiety", 50))
    avoidance = float(scores.get("avoidance", 50))
    anxiety_high = anxiety >= 60
    avoidance_high = avoidance >= 60

    if anxiety_high and avoidance_high:
        return "fearful"
    if anxiety_high:
        return "anxious"
    if avoidance_high:
        return "avoidant"
    return "secure"


def get_type_info(type_code: str) -> dict[str, Any]:
    return ATTACHMENT_TYPE_LABELS.get(
        type_code,
        {
            "nickname": type_code,
            "tags": [f"依恋风格:{type_code}"],
        },
    )


def _relationship_drive(type_code: str) -> str:
    mapping = {
        "secure": "你通常能同时接受亲近和独立。对你来说，关系更像是可以互相依靠，而不是必须反复确认或反复设防。",
        "anxious": "你会更在意关系里的可得性和回应感。越在意一个人，你越希望关系是清楚、稳定、能被确认的。",
        "avoidant": "你会更在意关系里有没有足够的空间和自主感。比起被快速拉近，你更容易在能保留节奏时放松下来。",
        "fearful": "你一方面很在意关系能不能给你确定感，另一方面又会对太快、太满的亲近保持警觉，所以容易同时出现想靠近和想后退。",
    }
    return mapping.get(type_code, "")


def _triggers(type_code: str) -> str:
    mapping = {
        "secure": "真正会让你不舒服的，往往是长期失去回应、持续不可靠，或者关系里一直讲不清楚、修复不起来。",
        "anxious": "你更容易被回应变少、关系变模糊、冲突后迟迟没有修复，或者对方忽近忽远的信号触发。",
        "avoidant": "你更容易被推进得太快、被要求立刻袒露很多情绪，或被持续追问和高密度黏连触发。",
        "fearful": "你两边都可能被触发: 关系一模糊你会不安，关系一贴太近你又会警觉，所以很容易进入拉扯状态。",
    }
    return mapping.get(type_code, "")


def _stabilizers(type_code: str) -> str:
    mapping = {
        "secure": "稳定、可靠、愿意互相支持的关系会让你更自在。你通常不需要很多额外确认，持续在场就够了。",
        "anxious": "持续回应、明确表达和冲突后的修复，会明显帮你把注意力从“会不会失去”拉回到关系本身。",
        "avoidant": "当对方尊重你的节奏、不把亲近变成压迫，同时又保持稳定可靠时，你会更愿意慢慢靠近。",
        "fearful": "既有稳定回应，又给你缓冲空间，不过度逼近的关系，最容易让你一点点放下防御。",
    }
    return mapping.get(type_code, "")


def _common_misread(type_code: str) -> str:
    mapping = {
        "secure": "你有时会把很多事情先自己消化掉，结果别人未必看得出来，你其实也需要回应和支持。",
        "anxious": "当线索不够清楚时，你会更倾向先把它理解成关系在降温，而不是普通的忙碌或节奏变化。",
        "avoidant": "当压力上来时，你可能会过早把需要和情绪收起来。对方看到的常常是距离，不一定看得到你的真实负担。",
        "fearful": "你可能会一边想确认关系，一边又很快把自己收回去。外面看到的是信号反复，里面其实是又想靠近又怕受伤。",
    }
    return mapping.get(type_code, "")


def _fit_people(type_code: str) -> list[str]:
    mapping = {
        "secure": [
            "能稳定回应，也愿意保留彼此独立空间的人。",
            "冲突里愿意直接沟通、修复，而不是长期失联或冷处理的人。",
            "关系投入比较一致，不需要靠拉扯制造存在感的人。",
        ],
        "anxious": [
            "回应相对稳定、不会忽冷忽热的人。",
            "愿意把关系状态说清楚，冲突后愿意修复的人。",
            "能理解你对确定感的需要，不会把确认需求一概打成“太黏”或“太多”的人。",
        ],
        "avoidant": [
            "尊重节奏和边界，不会一上来高密度推进的人。",
            "既稳定在场，又不过度追问和逼近的人。",
            "能把亲近做成可协商的过程，而不是压迫式证明关系的人。",
        ],
        "fearful": [
            "既能给稳定回应，又能给缓冲空间的人。",
            "情绪稳定、边界清楚，不会一会儿逼近一会儿抽离的人。",
            "愿意慢慢建立信任，能同时接住你的靠近和后撤信号的人。",
        ],
    }
    return mapping.get(type_code, [])


def _friction_people(type_code: str) -> list[str]:
    mapping = {
        "secure": [
            "长期模糊、承诺和行动经常对不上的人。",
            "习惯用冷暴力、失联或反复试探来推进关系的人。",
        ],
        "anxious": [
            "长期忽冷忽热、经常失联、把回应交给你猜的人。",
            "一遇到冲突就消失，或把你的不安当成负担的人。",
        ],
        "avoidant": [
            "刚开始就高密度黏连、持续追问、要求立刻深聊的人。",
            "把边界理解成拒绝，越感到不安越加速逼近的人。",
        ],
        "fearful": [
            "本身也很不稳定，时近时远、时冷时热的人。",
            "要么长期失联，要么一上来就高压推进，没有缓冲区的人。",
        ],
    }
    return mapping.get(type_code, [])


def _ecr_basis(type_code: str) -> list[str]:
    shared = [
        "ECR / ECR-R 把成人亲密关系里的差异主要放在两条连续维度上看：关系不安度（anxiety）和亲密后撤度（avoidance）。",
        "这类结果更适合解释“你在什么情境下容易被触发、什么互动更容易让你稳定”，不是给人下永久结论。",
    ]
    if type_code == "secure":
        shared.append("低不安、低后撤的人，通常更能在亲近和独立之间保持弹性，也更容易把冲突导向修复。")
    elif type_code == "anxious":
        shared.append("高不安更常见的机制是：对拒绝、冷淡和不可得线索更警觉，更容易放大关系里的不确定感。")
    elif type_code == "avoidant":
        shared.append("高后撤更常见的机制是：在亲密压力升高时更倾向拉开距离、压低暴露和依赖感。")
    else:
        shared.append("高不安和高后撤同时偏高时，常见表现就是既想靠近确认，又会在压力上来时本能自保。")
    return shared


def _communication_advice(type_code: str, anxiety: float, avoidance: float) -> str:
    advice: list[str] = []
    if anxiety >= 60:
        advice.append("把你需要的回应说具体，比如你想知道关系状态、还是想要更稳定的反馈。")
    if avoidance >= 60:
        advice.append("想退的时候别直接消失，先留一句边界说明，比如“我想缓一下，晚点继续聊”。")
    if 40 <= anxiety < 60 and 40 <= avoidance < 60:
        advice.append("你更适合把节奏、边界和需求提前讲清楚，而不是等误会堆起来再解释。")
    if not advice:
        advice.append("继续保持这种相对稳定的靠近能力，同时别省略自己的需要。")
    return " ".join(advice[:2])


def _card_tip(type_code: str, anxiety: float, avoidance: float) -> str:
    if anxiety >= 60 and avoidance >= 60:
        return "先求稳，再谈靠近。"
    if anxiety >= 60:
        return "少一点猜测，多一点确认。"
    if avoidance >= 60:
        return "先讲边界，再谈亲近。"
    return "稳稳靠近，也别省略需要。"


def _interpretation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    scores = dict(result.get("scores") or {})
    anxiety = float(scores.get("anxiety", 50))
    avoidance = float(scores.get("avoidance", 50))
    type_code = str(result.get("type_code") or get_primary_attachment_type(scores))
    type_info = get_type_info(type_code)
    extreme_tags = get_extreme_tags(scores)

    summary_map = {
        "secure": "你整体更接近低不安、低后撤的状态: 既能靠近，也不太需要靠反复确认或反复设防来稳住关系。",
        "anxious": "你更接近高不安、低后撤的状态: 会明显在意关系有没有持续回应，但通常不会因为亲近本身就先躲开。",
        "avoidant": "你更接近低不安、高后撤的状态: 不一定特别担心被抛下，但在关系太近、太满时会更想先拉开一点。",
        "fearful": "你更接近高不安、高后撤的状态: 一方面很在意关系，另一方面又容易在压力上来时先自我保护。",
    }

    relationship_drive = _relationship_drive(type_code)
    triggers = _triggers(type_code)
    stabilizers = _stabilizers(type_code)
    common_misread = _common_misread(type_code)
    communication_advice = _communication_advice(type_code, anxiety, avoidance)
    card_tip = _card_tip(type_code, anxiety, avoidance)
    fit_people = _fit_people(type_code)
    friction_people = _friction_people(type_code)
    ecr_basis = _ecr_basis(type_code)

    return {
        "summary": summary_map.get(type_code, ""),
        "relationship_drive": relationship_drive,
        "triggers": triggers,
        "stabilizers": stabilizers,
        "common_misread": common_misread,
        "communication_advice": communication_advice,
        "card_tip": card_tip,
        "fit_people": fit_people,
        "friction_people": friction_people,
        "ecr_basis": ecr_basis,
        # compatibility fields used by some generic UI/tests
        "love_style": relationship_drive,
        "match_suggestions": [
            f"最容易被触发：{triggers}",
            f"更容易稳定下来：{stabilizers}",
            f"相处建议：{communication_advice}",
            f"更适合的人：{fit_people[0] if fit_people else ''}",
        ],
        "extreme_tags": extreme_tags,
        "disclaimer": "这份结果更适合拿来理解你的关系节奏，不适合在吵架时当证据甩对方脸上。",
        "quadrant_label": type_info.get("nickname", type_code),
    }


def xiaoya_message_from_result(result: dict[str, Any]) -> str:
    scores = dict(result.get("scores") or {})
    anxiety = float(scores.get("anxiety", 50))
    avoidance = float(scores.get("avoidance", 50))
    type_code = str(result.get("type_code") or get_primary_attachment_type(scores))
    type_info = get_type_info(type_code)
    interpretation = _interpretation_from_result({"scores": scores, "type_code": type_code})
    fit_people = _fit_people(type_code)
    friction_people = _friction_people(type_code)
    ecr_basis = _ecr_basis(type_code)

    if type_code == "secure":
        image = "你更像那种能接受亲近、也能保留独立的人，通常不需要靠反复确认来稳住关系。"
    elif type_code == "anxious":
        image = "你不是不能独立，你只是会更留意关系里的回应是不是稳定、是不是还在。"
    elif type_code == "avoidant":
        image = "你不是没感觉，你只是会对太快、太满、太没有缓冲的亲近更敏感。"
    else:
        image = "你会一边想确认关系，一边又会对太近或太不稳同时警觉，所以容易出现靠近和后撤并存。"

    message = "亲爱的，这次我按依恋研究里更常用的 ECR 两条轴，帮你翻译成好懂的话。\n\n"
    message += f"你这次更偏 **{type_info.get('nickname', type_code)}**。\n"
    message += f"{image}\n"
    if interpretation.get("summary"):
        message += f"{interpretation['summary']}\n"
    if interpretation.get("card_tip"):
        message += f"先记住一句：{interpretation['card_tip']}\n\n"
    else:
        message += "\n"
    message += "**关系模式**\n"
    message += f"- 你的关系驱动力更像是：{interpretation['relationship_drive']}\n"
    message += f"- 你更容易被这些情境牵动：{interpretation['triggers']}\n"
    message += f"- 更能帮你稳定下来的，通常是：{interpretation['stabilizers']}\n"
    message += f"- 你在关系里常见的卡点是：{interpretation['common_misread']}\n\n"
    message += "**匹配建议**\n"
    message += "更适合你长期相处的人，通常会更接近下面这几种：\n"
    for item in fit_people:
        message += f"- {item}\n"
    message += "\n"
    message += "需要重点磨合，或者很容易消耗你的，通常是这几类互动：\n"
    for item in friction_people:
        message += f"- {item}\n"
    message += "\n"
    message += "**相处建议**\n"
    message += f"- 如果只记一句更有用的话，那就是：{interpretation['communication_advice']}\n"
    message += "- 这不是让你压住天性，而是尽量把“猜”换成“说清楚”，把“触发后自动反应”换成“提前讲节奏和边界”。\n\n"
    message += "**为什么我这么说**\n"
    for item in ecr_basis:
        message += f"- {item}\n"
    message += "\n"
    message += "你要是愿意，我下一条可以继续帮你拆：你最适合什么样的回应方式，和哪种相处节奏最容易消耗你。"
    return message


def calculate_love_match(
    user_a_scores: dict[str, float], user_b_scores: dict[str, float]
) -> dict[str, Any]:
    """轻量 ECR 匹配说明。

    这里不再做旧版“安全型配任何都高分”的硬规则，
    改为根据双方焦虑/回避距离给出一个参考分。
    """

    a_anxiety = float(user_a_scores.get("anxiety", 50))
    a_avoidance = float(user_a_scores.get("avoidance", 50))
    b_anxiety = float(user_b_scores.get("anxiety", 50))
    b_avoidance = float(user_b_scores.get("avoidance", 50))

    anxiety_gap = abs(a_anxiety - b_anxiety)
    avoidance_gap = abs(a_avoidance - b_avoidance)

    score = 100 - (anxiety_gap * 0.35 + avoidance_gap * 0.35)
    score = max(0, min(100, round(score, 1)))

    dimension_analysis = {
        "anxiety": f"你们在关系不安度上的差值约为 {round(anxiety_gap, 1)} 分。",
        "avoidance": f"你们在亲密后撤度上的差值约为 {round(avoidance_gap, 1)} 分。",
    }

    if anxiety_gap >= 30:
        dimension_analysis["trigger"] = "一方更需要明确回应，另一方可能会低估这种不安。"
    if avoidance_gap >= 30:
        dimension_analysis["space"] = "一方更需要空间和缓冲，另一方可能会把这种后退误解成冷淡。"

    if score >= 85:
        analysis = "你们的关系节奏比较接近，天然摩擦会少一些。"
    elif score >= 70:
        analysis = "整体能磨合，但需要更清楚地讲回应需求和空间需求。"
    elif score >= 50:
        analysis = "触发点差异比较明显，适合慢一点、讲清楚一点。"
    else:
        analysis = "你们的关系触发机制差得比较远，靠猜很容易累，必须靠沟通。"

    return {
        "score": score,
        "analysis": analysis,
        "dimension_analysis": dimension_analysis,
        "a_type": get_primary_attachment_type(user_a_scores),
        "b_type": get_primary_attachment_type(user_b_scores),
    }


__all__ = [
    "ATTACHMENT_DIMENSIONS",
    "ATTACHMENT_FEEDBACKS",
    "ATTACHMENT_QUESTIONS",
    "ATTACHMENT_TYPE_LABELS",
    "ATTACHMENT_TYPE_NAMES",
    "ATTACHMENT_TYPES",
    "calculate_all_scores",
    "calculate_dimension_score",
    "calculate_love_match",
    "get_dimension_feedback",
    "get_dimension_for_question",
    "get_extreme_tags",
    "get_primary_attachment_type",
    "get_question",
    "get_type_info",
    "xiaoya_message_from_result",
    "_interpretation_from_result",
]
