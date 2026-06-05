"""IPIP-based Big Five assessment question bank.

Question basis:
- IPIP / ORI Big-Five Factor Markers (public-domain item pool)
- Product adaptation: keep factor meaning, translate to Chinese, unify to 5-point Likert
"""

from __future__ import annotations

from typing import Any


BIG_FIVE_DIMENSIONS = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]

BIG_FIVE_DIMENSION_NAMES = {
    "openness": "开放性",
    "conscientiousness": "尽责性",
    "extraversion": "外向性",
    "agreeableness": "宜人性",
    "neuroticism": "神经质",
}

BIG_FIVE_DIMENSION_LABELS = {
    "openness": {"high": "开放性较高", "medium": "开放性中等", "low": "开放性较低"},
    "conscientiousness": {"high": "尽责性较高", "medium": "尽责性中等", "low": "尽责性较低"},
    "extraversion": {"high": "外向性较高", "medium": "外向性中等", "low": "外向性较低"},
    "agreeableness": {"high": "宜人性较高", "medium": "宜人性中等", "low": "宜人性较低"},
    "neuroticism": {"high": "神经质较高", "medium": "神经质中等", "low": "神经质较低"},
}

def _options(option_a: str, option_b: str, option_c: str, option_d: str, option_e: str) -> list[dict[str, Any]]:
    return [
        {"label": "A", "text": option_a, "score": 1},
        {"label": "B", "text": option_b, "score": 2},
        {"label": "C", "text": option_c, "score": 3},
        {"label": "D", "text": option_d, "score": 4},
        {"label": "E", "text": option_e, "score": 5},
    ]


def _question(
    index: int,
    dimension: str,
    text: str,
    options: list[dict[str, Any]],
    *,
    reverse: bool = False,
    source_item: str,
) -> dict[str, Any]:
    return {
        "index": index,
        "dimension": dimension,
        "text": text,
        "options": options,
        "reverse": reverse,
        "source_item": source_item,
    }


BIG_FIVE_QUESTIONS: list[dict[str, Any]] = [
    _question(0, "openness", "和喜欢的人聊到天马行空的话题时，你通常会？", _options("很快觉得飘，想把话题拉回现实", "能接一点，但不会聊太深", "看状态，有时能聊有时会跳开", "会顺着展开，越聊越有画面", "会很兴奋地继续脑补，脑子里像开了小剧场"), source_item="Have a vivid imagination."),
    _question(1, "openness", "一次约会结束后，你更可能怎么消化这段经历？", _options("差不多过了就过了，很少回想", "偶尔想一下，但不会停留太久", "看当天感受，有时会回味", "会反复想细节和自己的感受", "会自己慢慢复盘很久，连气氛变化都想一遍"), source_item="Spend time reflecting on things."),
    _question(2, "openness", "对方突然分享一个你从没接触过的新观念，你通常会？", _options("第一反应是听不进去，也懒得懂", "能听，但理解起来比较慢", "先听听看，再决定要不要继续想", "通常能比较快抓到重点", "会很快理解，还会顺手延展出别的想法"), source_item="Am quick to understand things."),
    _question(3, "openness", "如果对方聊的是很抽象的人生观、关系观，你会？", _options("很容易进入状态，甚至会越聊越起劲", "大体能跟上，也愿意继续想", "看表达方式，能懂一部分", "能勉强听，但还是觉得费劲", "很难跟上，会明显想结束这个话题"), reverse=True, source_item="Have difficulty understanding abstract ideas."),
    _question(4, "openness", "朋友来问你“约会还能怎么玩出新意”，你的反应更像？", _options("我通常想不出什么新花样", "偶尔有一两个点子", "看人，看场景", "我经常能很快想到不少主意", "这种题我最来劲，脑子里会一下冒出很多方案"), source_item="Am full of ideas."),
    _question(5, "openness", "当聊天开始往“概念、意义、抽象关系”走时，你通常会？", _options("会被这种抽象讨论明显激活", "通常还能聊进去", "一半一半", "除非对方很会聊，不然兴趣不大", "会本能地觉得无聊，想换话题"), reverse=True, source_item="Am not interested in abstract ideas."),
    _question(6, "openness", "一起策划一次特别的纪念日，你在出主意这件事上通常是？", _options("基本靠别人带，我很少有好点子", "偶尔能补充一点", "正常发挥，不算特别多", "经常能想到让人眼前一亮的安排", "我往往就是那个能想出整套惊喜方案的人"), source_item="Have excellent ideas."),
    _question(7, "openness", "对方忽然想和你认真聊聊“亲密关系的底层逻辑”，你会？", _options("这种理论向话题会让我越聊越上头", "通常愿意聊，而且能聊出点东西", "看当天状态", "能听一下，但兴趣不高", "第一反应是别聊这个，太虚了"), reverse=True, source_item="Am not interested in theoretical discussions."),
    _question(8, "openness", "在表达复杂感受时，你更常出现哪种情况？", _options("总觉得词不达意，只能说个大概", "能说明白，但词比较普通", "正常表达，够用就行", "常能找到比较准确细致的说法", "我经常能用很贴切甚至偏细腻的词把感受讲清楚"), source_item="Use difficult words."),
    _question(9, "openness", "聊到“如果以后我们的人生是另一种版本”这种假设题时，你通常会？", _options("这种假设题我很容易自动脑补出完整剧情", "通常能顺着想下去", "看场景", "能勉强接一点，但不算自然", "脑子很难起画面，基本接不上"), reverse=True, source_item="Do not have a good imagination."),
    _question(10, "conscientiousness", "约会前一天，你通常会怎么准备？", _options("临到出门才开始想", "只做最基本的准备", "看心情，准备程度不固定", "会提前把时间、路线、穿搭想好", "通常会提前安排得很妥当，尽量不让现场手忙脚乱"), source_item="Am always prepared."),
    _question(11, "conscientiousness", "第一次去对方常去的地方见面，你通常会？", _options("基本不看细节，到了再说", "只关注最核心的信息", "重要细节会看，其余随缘", "会留意很多细节，避免出差错", "细节会提前记得很清楚，连小环节都不太会漏"), source_item="Pay attention to details."),
    _question(12, "conscientiousness", "如果你们约好这个月要固定见面 / 联系，你更像？", _options("很难稳定执行，常常随缘", "有计划，但经常改来改去", "大致能跟着走", "通常会按约定节奏推进", "我会把节奏安排得比较稳，并尽量照着执行"), source_item="Follow a schedule."),
    _question(13, "conscientiousness", "日常相处里，你的随身物品或聊天待办通常是？", _options("我通常收得挺有条理，临时要找也很快", "大多数时候放得比较顺手", "一般般，不算特别乱", "偶尔会乱，得临时翻找", "经常东一件西一件，自己都找不到"), reverse=True, source_item="Leave my belongings around."),
    _question(14, "conscientiousness", "给喜欢的人准备礼物或惊喜时，你通常会？", _options("差不多就行，很少反复打磨", "会改一点，但不会花太多时间", "看重要程度", "会认真修一修，想做到更好", "会一直磨到自己觉得足够妥帖才停"), source_item="Continue until everything is perfect."),
    _question(15, "conscientiousness", "关系里该你处理的事，比如回消息、兑现答应的安排，你更像？", _options("只要是我答应的，通常都会尽量落实", "大多数时候会主动负责", "看事情大小", "有时会拖，别人催了再动", "容易拖着不做，甚至躲过去"), reverse=True, source_item="Shirk my duties."),
    _question(16, "conscientiousness", "你更喜欢哪种约会 / 相处状态？", _options("太有秩序会让我烦，最好完全随缘", "稍微有点安排就够了", "都可以", "我会更偏好清楚一点的节奏和安排", "有条理会让我很安心，越清晰越舒服"), source_item="Like order."),
    _question(17, "conscientiousness", "本来打算认真处理关系里的一个问题时，你通常会？", _options("我一般会尽快处理，不太会让时间空耗过去", "通常不会拖太久", "有时拖，有时能推进", "常常拖到很后面", "很容易被别的事带跑，最后没做"), reverse=True, source_item="Waste my time."),
    _question(18, "conscientiousness", "如果你想把一段关系认真推进，你通常会？", _options("很少主动规划，想到哪算哪", "会有一点想法，但不稳定", "看对方节奏", "会列出比较明确的安排并尽量照做", "我会先想清楚步骤，再比较稳定地推进"), source_item="Make plans and stick to them."),
    _question(19, "conscientiousness", "面对一件必须处理但不太想碰的事，比如解释误会、确认安排，你通常会？", _options("我一般能比较快进入处理状态", "通常还是能把自己推进去", "看事情急不急", "要磨一阵子才会动", "很难开始，能拖就拖"), reverse=True, source_item="Find it difficult to get down to work."),
    _question(20, "extraversion", "刚加上有好感的人，你更可能？", _options("基本等对方先开口", "只有很确定时才会主动", "看对方给的信号", "通常能自然地先开启话题", "我大多会主动把聊天打开，不太怕冷场"), source_item="Start conversations."),
    _question(21, "extraversion", "一群人一起聚会时，你通常会把自己放在什么位置？", _options("很容易在场上变活跃", "能正常参与，也不太会躲", "看熟悉度", "更偏向在边上观察", "我通常会待在背景里，不太想被看见"), reverse=True, source_item="Keep in the background."),
    _question(22, "extraversion", "第一次见对方的朋友或家人时，你通常会？", _options("通常会明显不自在，要很久才能放松", "会比较拘谨", "看现场氛围", "有点紧张，但总体放得开", "很自在，很快能进入状态"), source_item="Feel comfortable around people."),
    _question(23, "extraversion", "到了一个新的社交场合，你结识新朋友通常是？", _options("很难，除非别人先来找我", "要慢慢来，不太容易热起来", "看有没有共同话题", "通常不算难", "我一般很快就能和人熟起来"), source_item="Make friends easily."),
    _question(24, "extraversion", "跟喜欢的人出去时，你在聊天里通常是？", _options("通常挺能聊，气氛靠我也没问题", "多数时候能说得比较开", "差不多五五开", "不算太多话，要热起来才会说", "大多比较安静，主要听对方说"), reverse=True, source_item="Don't talk a lot."),
    _question(25, "extraversion", "一群人要定行程或做决定时，你更可能？", _options("完全不想带头，别人定就好", "除非没人动，不然我不太上", "看场景", "需要时我会主动站出来", "我通常不介意先把节奏带起来"), source_item="Take charge."),
    _question(26, "extraversion", "在不太熟的人面前，你更常出现哪种状态？", _options("很放松，不太会卡住", "有一点点别扭，但还好", "看人", "经常会不自在", "我很容易在人际场合里绷住或局促"), reverse=True, source_item="Often feel uncomfortable around others."),
    _question(27, "extraversion", "如果喜欢的人把你拉进话题中心，大家都在看你，你通常会？", _options("我通常很不想成为关注焦点", "会有点想往后退", "一般般", "不排斥，还能接住", "会很享受，被注意也没关系"), source_item="Don't mind being the center of attention."),
    _question(28, "extraversion", "看到想认识的人时，你更可能？", _options("会自然上前搭话", "如果时机合适会主动靠近", "看当天状态", "要做很多心理建设", "我通常很难主动走过去认识对方"), reverse=True, source_item="Find it difficult to approach others."),
    _question(29, "extraversion", "在一段刚开始的关系里，你通常谁先推进节奏？", _options("我常常会先动起来", "我能主动一点", "差不多谁来都行", "更多是等对方带节奏", "我通常会先观望，等别人开路"), reverse=True, source_item="Wait for others to lead the way."),
    _question(30, "agreeableness", "对方状态不对但嘴上说没事时，你通常会？", _options("大多不会细想，尊重对方不说", "会问一句，但不会追", "看关系深浅", "会比较在意对方真实感受", "我通常会认真感知并照顾对方情绪"), source_item="Sympathize with others' feelings."),
    _question(31, "agreeableness", "朋友或对象临时需要你搭把手时，你更像？", _options("除非很必要，不然我不太愿意挪时间", "会帮，但心里会比较计较", "看事情大小", "通常愿意腾一点时间出来", "只要我帮得上，基本会尽量去帮"), source_item="Take time out for others."),
    _question(32, "agreeableness", "做决定时，比如定见面地点、节奏安排，你通常会先想到？", _options("先按我方便的来", "主要看我自己，顺手再顾一下别人", "两边都会看", "会明显把对方感受放进来", "我经常会先考虑别人会不会舒服"), source_item="Think of others first."),
    _question(33, "agreeableness", "别人跟你讲烦心事时，你通常会？", _options("我大多会真心想了解对方到底怎么了", "通常愿意认真听一会儿", "看关系和状态", "会听，但投入不多", "兴趣不大，常常想赶紧结束"), reverse=True, source_item="Am not interested in other people's problems."),
    _question(34, "agreeableness", "第一次见面时，你给人的感觉通常更接近？", _options("别人容易觉得我有距离", "要相处一下才会放松", "看场合", "通常还算让人自在", "我往往很快就能让对方放松下来"), source_item="Make people feel at ease."),
    _question(35, "agreeableness", "吵起来的时候，你的表达更可能是？", _options("再生气我也会尽量不往伤人那边说", "通常会克制一下", "看情绪上头程度", "偶尔会口不择言", "容易说很冲甚至很伤人的话"), reverse=True, source_item="Insult people."),
    _question(36, "agreeableness", "关系稳定后，你对“主动关心对方近况”这件事通常是？", _options("很少主动问，除非有事", "偶尔会想起来问一下", "看忙不忙", "会比较自然地关心", "我通常会主动问对方最近过得怎么样"), source_item="Inquire about others' well-being."),
    _question(37, "agreeableness", "在多数人际关系里，你通常是？", _options("容易和人起摩擦", "关系能维持，但不算特别顺", "一般般", "大多能和人相处得不错", "我通常和大部分人都能保持挺好的关系"), source_item="Am on good terms with nearly everyone."),
    _question(38, "agreeableness", "看到别人明显难过或窘迫时，你通常会？", _options("我一般会很在乎对方当下的感受", "会有些在意", "看情况", "知道对方难受，但不太想介入", "常常没什么感觉，也不会特别在意"), reverse=True, source_item="Feel little concern for others."),
    _question(39, "agreeableness", "身边的人情绪低落时，你更可能？", _options("我通常不知道怎么安慰", "能安慰一点，但比较生硬", "看人", "一般能找到合适的话和方式", "我通常很知道怎么把人慢慢安抚下来"), source_item="Know how to comfort others."),
    _question(40, "neuroticism", "关系里一旦事情多、节奏乱，你通常会？", _options("基本还能稳住", "会有点紧，但问题不大", "看事情多严重", "很容易明显有压力", "我通常很快就会被压力顶上来"), source_item="Get stressed out easily."),
    _question(41, "neuroticism", "对方回消息慢、态度变淡一点时，你通常会？", _options("很少多想", "偶尔会担心一下", "看前因后果", "会忍不住反复想", "脑子容易立刻开很多担心分支"), source_item="Worry about things."),
    _question(42, "neuroticism", "一点小变动，比如临时改计划、语气不对，你通常会？", _options("基本不太受影响", "会注意到，但还能过去", "看当天状态", "比较容易被打扰到", "我通常很容易被这种变化搅动情绪"), source_item="Am easily disturbed."),
    _question(43, "neuroticism", "在大多数关系阶段里，你的底层状态更像？", _options("我大部分时候是松弛的，不太容易一直悬着", "多数时候还算放松", "一半一半", "偶尔能松，但总体还是绷着", "经常紧绷，很难真的放松"), reverse=True, source_item="Am relaxed most of the time."),
    _question(44, "neuroticism", "一旦情绪和关系问题撞在一起，你通常会？", _options("通常不太会被情绪整个卷走", "大多还能慢慢缓回来", "看事情大小", "常常会觉得有点扛不住", "很容易一下被情绪淹住"), source_item="Get overwhelmed by emotions."),
    _question(45, "neuroticism", "相处里遇到一点不顺时，你更可能？", _options("很容易被惹到", "有时会明显烦躁", "看具体情况", "大多还能忍住", "我通常不太容易因为小事就被点着"), reverse=True, source_item="Rarely get irritated."),
    _question(46, "neuroticism", "当你察觉到一点不确定，比如关系没那么稳时，你通常会？", _options("通常不会一下就进入防御状态", "能感觉到，但不至于太被带走", "看信号强不强", "会比较警觉", "很容易有被威胁或不安全的感觉"), source_item="Feel threatened easily."),
    _question(47, "neuroticism", "关系里一有烦心事，你通常会？", _options("我通常不太会一直陷在自己的问题里", "大多还能抽离一下", "看事情大小", "会卡一阵子", "很容易被困住，脑子反复转"), source_item="Get caught up in my problems."),
    _question(48, "neuroticism", "最近一段时间里，你的情绪底色通常更像？", _options("低落感挺常见", "偶尔会闷下来", "一般般", "大多数时候还行", "我其实很少掉进明显的沮丧里"), reverse=True, source_item="Seldom feel blue."),
    _question(49, "neuroticism", "在关系波动里，你的情绪变化通常是？", _options("我通常不太会频繁大起大落", "整体还算稳定", "看阶段", "有明显波动", "起伏很大，很容易一下高一下低"), source_item="Change my mood a lot."),
]

TOTAL_QUESTIONS = len(BIG_FIVE_QUESTIONS)
QUESTIONS_PER_DIMENSION = TOTAL_QUESTIONS // len(BIG_FIVE_DIMENSIONS)


def get_question(index: int) -> dict[str, Any] | None:
    if 0 <= index < TOTAL_QUESTIONS:
        return BIG_FIVE_QUESTIONS[index]
    return None


def score_answer(question: dict[str, Any], answer_score: int) -> int:
    if bool(question.get("reverse")):
        return 6 - answer_score
    return answer_score


def calculate_dimension_score(answers: list[int], dimension: str) -> float:
    values = [
        score_answer(question, answers[question["index"]])
        for question in BIG_FIVE_QUESTIONS
        if question["dimension"] == dimension and question["index"] < len(answers)
    ]
    if not values:
        return 0.0
    minimum = len(values)
    maximum = len(values) * 5
    total = sum(values)
    score = ((total - minimum) / (maximum - minimum)) * 100
    return round(max(0.0, min(100.0, score)), 1)


def calculate_all_scores(answers: list[int]) -> dict[str, float]:
    return {dimension: calculate_dimension_score(answers, dimension) for dimension in BIG_FIVE_DIMENSIONS}


def get_dimension_feedback(dimension: str, score: float) -> str:
    if dimension == "openness":
        if score >= 70:
            return "你的开放性相对较高，通常更容易接受新观念，也更愿意接触抽象、复杂或富有想象力的内容。"
        if score >= 40:
            return "你的开放性处于中间水平，通常既能理解新观点，也保留对熟悉方式的偏好。"
        return "你的开放性相对较低，通常更偏向熟悉、具体、可执行的事物，而不是抽象或高度变化的内容。"
    if dimension == "conscientiousness":
        if score >= 70:
            return "你的尽责性相对较高，通常更有条理，也更倾向于提前准备、按计划推进任务。"
        if score >= 40:
            return "你的尽责性处于中间水平，既能保持一定秩序，也保留灵活调整的空间。"
        return "你的尽责性相对较低，通常更随性，也更可能在计划、秩序或任务持续性上表现得弱一些。"
    if dimension == "extraversion":
        if score >= 70:
            return "你的外向性相对较高，通常更主动、更健谈，也更容易在社交场合中感到自在。"
        if score >= 40:
            return "你的外向性处于中间水平，是否主动表达或社交投入，通常会随着场景而变化。"
        return "你的外向性相对较低，通常更安静，也更可能偏好低刺激或较少输出的社交方式。"
    if dimension == "agreeableness":
        if score >= 70:
            return "你的宜人性相对较高，通常更愿意体谅他人、合作相处，也更关注人际和谐。"
        if score >= 40:
            return "你的宜人性处于中间水平，既能顾及他人，也会在必要时坚持自己的立场。"
        return "你的宜人性相对较低，通常会更直接，也更不容易优先考虑他人的感受或人际和谐。"
    if score >= 70:
        return "你的神经质相对较高，通常更容易体验到压力、担忧、情绪波动或不稳定感。"
    if score >= 40:
        return "你的神经质处于中间水平，可能会有情绪波动，但整体仍保留一定的自我调节能力。"
    return "你的神经质相对较低，通常情绪更稳定，也更不容易被压力和负面体验迅速带走。"
