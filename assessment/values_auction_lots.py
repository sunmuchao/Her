"""
价值观拍卖会拍品定义

v4.0 Schwartz 骨架版：
- 前台继续使用游戏化拍品
- 后台映射到 Schwartz 10 价值
- 输出 4 个高阶方向和内部张力
"""

from __future__ import annotations

from typing import Any


SCHWARTZ_VALUE_KEYS: list[str] = [
    "self_direction",
    "stimulation",
    "hedonism",
    "achievement",
    "power",
    "security",
    "conformity",
    "tradition",
    "benevolence",
    "universalism",
]

# 为兼容旧字段名保留导出
HIDDEN_VALUE_KEYS = SCHWARTZ_VALUE_KEYS

SCHWARTZ_VALUE_LABELS: dict[str, str] = {
    "self_direction": "自我导向",
    "stimulation": "刺激",
    "hedonism": "享乐",
    "achievement": "成就",
    "power": "权力",
    "security": "安全",
    "conformity": "顺从",
    "tradition": "传统",
    "benevolence": "仁爱",
    "universalism": "普遍主义",
}

HIGHER_ORDER_LABELS: dict[str, str] = {
    "openness_to_change": "开放变化",
    "conservation": "保守维持",
    "self_enhancement": "自我提升",
    "self_transcendence": "超越自我",
}

SCHWARTZ_TO_HIGHER_ORDER: dict[str, tuple[tuple[str, float], ...]] = {
    "self_direction": (("openness_to_change", 1.0),),
    "stimulation": (("openness_to_change", 1.0),),
    "hedonism": (("openness_to_change", 0.5), ("self_enhancement", 0.5)),
    "achievement": (("self_enhancement", 1.0),),
    "power": (("self_enhancement", 1.0),),
    "security": (("conservation", 1.0),),
    "conformity": (("conservation", 1.0),),
    "tradition": (("conservation", 1.0),),
    "benevolence": (("self_transcendence", 1.0),),
    "universalism": (("self_transcendence", 1.0),),
}

OPPOSING_VALUE_PAIRS: list[tuple[str, str]] = [
    ("self_direction", "conformity"),
    ("stimulation", "security"),
    ("achievement", "benevolence"),
    ("power", "universalism"),
]

AUCTION_DIMENSIONS: dict[str, str] = {
    "material_achievement": "物质与成就",
    "emotion_connection": "情感与连接",
    "self_growth": "自我与成长",
    "altruism_devotion": "利他与奉献",
}

VALUES_AUCTION_LOTS: list[dict[str, Any]] = [
    {
        "lot_id": "financial_freedom",
        "title": "这辈子都不用再为钱妥协",
        "dimension": "material_achievement",
        "hidden_values": [
            {"key": "self_direction", "weight": 0.55},
            {"key": "security", "weight": 0.45},
        ],
        "theme_color": "#F59E0B",
        "icon": "💰",
        "interpretation": "你想要的是更强的生活自主权，而不是单纯有钱。",
        "conflict_hint": "这更偏自主选择；如果你也很想要稳定陪伴，就会出现自由和依赖的拉扯。",
    },
    {
        "lot_id": "elite_status",
        "title": "走到哪里都让人高看一眼",
        "dimension": "material_achievement",
        "hidden_values": [
            {"key": "achievement", "weight": 0.6},
            {"key": "power", "weight": 0.4},
        ],
        "theme_color": "#9333EA",
        "icon": "👑",
        "interpretation": "你在意的不只是赢，而是被看见、被认可、能产生影响。",
        "conflict_hint": "这更偏成就和影响力；如果你同时很想要平静不折腾，内部会有点顶。",
    },
    {
        "lot_id": "soulmate",
        "title": "一个永远不会离开你的人",
        "dimension": "emotion_connection",
        "hidden_values": [
            {"key": "benevolence", "weight": 0.55},
            {"key": "security", "weight": 0.45},
        ],
        "theme_color": "#EF4444",
        "icon": "❤️",
        "interpretation": "你想要的是稳定投入、彼此照顾、关系里不反复试探。",
        "conflict_hint": "这更偏稳定与亲密；如果你也很想完全按自己节奏活，就容易拉扯。",
    },
    {
        "lot_id": "family_health",
        "title": "全家人健康平安到百岁",
        "dimension": "emotion_connection",
        "hidden_values": [
            {"key": "security", "weight": 0.6},
            {"key": "tradition", "weight": 0.4},
        ],
        "theme_color": "#F97316",
        "icon": "🏠",
        "interpretation": "你很重视生活底盘稳不稳，也很看重家庭责任感。",
        "conflict_hint": "这更偏守住基本盘；如果你也很想冒险折腾，会出现稳定和变化的冲突。",
    },
    {
        "lot_id": "deep_understanding",
        "title": "一个真正懂你的人",
        "dimension": "emotion_connection",
        "hidden_values": [
            {"key": "benevolence", "weight": 0.6},
            {"key": "self_direction", "weight": 0.4},
        ],
        "theme_color": "#EC4899",
        "icon": "🎯",
        "interpretation": "你不是只要陪伴，你要的是被理解、被尊重真实自我。",
        "conflict_hint": "这更偏亲密里的理解；如果你又特别怕被束缚，就要处理好边界。",
    },
    {
        "lot_id": "total_freedom",
        "title": "想做什么就做什么，没人管",
        "dimension": "self_growth",
        "hidden_values": [
            {"key": "self_direction", "weight": 0.65},
            {"key": "stimulation", "weight": 0.35},
        ],
        "theme_color": "#3B82F6",
        "icon": "🕊️",
        "interpretation": "你最看重自己决定生活的方向，不喜欢被关系和现实过度束缚。",
        "conflict_hint": "这更偏开放变化；如果你也很想要绝对稳定，就会有明显张力。",
    },
    {
        "lot_id": "inner_peace",
        "title": "内心平静，不再焦虑",
        "dimension": "self_growth",
        "hidden_values": [
            {"key": "security", "weight": 0.6},
            {"key": "hedonism", "weight": 0.4},
        ],
        "theme_color": "#10B981",
        "icon": "🧘",
        "interpretation": "你在意的是稳定、舒展、别让生活一直高压失控。",
        "conflict_hint": "这更偏安全和舒适；如果你又想一直往上冲，心里会分裂。",
    },
    {
        "lot_id": "change_world",
        "title": "做一件改变世界的事",
        "dimension": "altruism_devotion",
        "hidden_values": [
            {"key": "universalism", "weight": 0.65},
            {"key": "achievement", "weight": 0.35},
        ],
        "theme_color": "#1E40AF",
        "icon": "🌍",
        "interpretation": "你在意的不只是个人成功，还想做对更多人有价值的事。",
        "conflict_hint": "这更偏理想与影响；如果你更想守住小日子，就会有取舍。",
    },
    {
        "lot_id": "help_many",
        "title": "默默帮助很多人",
        "dimension": "altruism_devotion",
        "hidden_values": [
            {"key": "benevolence", "weight": 0.65},
            {"key": "universalism", "weight": 0.35},
        ],
        "theme_color": "#FBBF24",
        "icon": "🤲",
        "interpretation": "你更在乎善意、照顾和公平，而不是一定要高调赢。",
        "conflict_hint": "这更偏关怀与公共价值；如果你很想追求掌控感，内部会有点拧。",
    },
]

LOT_ID_TO_TITLE: dict[str, str] = {
    lot["lot_id"]: lot["title"] for lot in VALUES_AUCTION_LOTS
}

CONFLICT_PAIRS: list[dict[str, Any]] = [
    {
        "pair_id": "freedom_vs_stability",
        "lot_a": "total_freedom",
        "lot_b": "soulmate",
        "conflict_type": "开放变化 vs 稳定投入",
        "description": "既想完全按自己节奏活，也想关系绝对稳定不离场，这两种期待需要认真平衡。",
        "intensity": "high",
    },
    {
        "pair_id": "status_vs_peace",
        "lot_a": "elite_status",
        "lot_b": "inner_peace",
        "conflict_type": "持续进取 vs 稳定舒展",
        "description": "一直往上冲和维持平静舒适，通常很难同时拉满。",
        "intensity": "high",
    },
    {
        "pair_id": "world_vs_family",
        "lot_a": "change_world",
        "lot_b": "family_health",
        "conflict_type": "更大公共价值 vs 家庭基本盘",
        "description": "做更大的事和守住家里的稳，需要现实分配精力。",
        "intensity": "medium",
    },
    {
        "pair_id": "money_vs_understanding",
        "lot_a": "financial_freedom",
        "lot_b": "deep_understanding",
        "conflict_type": "生活自主权 vs 关系里的深度理解",
        "description": "越想谁都别管你，越要想清楚愿不愿意为深关系让渡一点空间。",
        "intensity": "medium",
    },
    {
        "pair_id": "status_vs_service",
        "lot_a": "elite_status",
        "lot_b": "help_many",
        "conflict_type": "赢得认可 vs 默默成全他人",
        "description": "一个更偏向上争取，一个更偏向向外照顾，两者排序往往不会完全一样。",
        "intensity": "medium",
    },
]

TOTAL_CHIPS = 10
MIN_BID = 0
MAX_BID = 3
LOT_COUNT = 9
MAX_KEEP = 3

SEQUENTIAL_DISPLAY = True
SHOW_PROGRESS = True
SHOW_TENSION_HINTS = True
SHOW_CONFLICT_HINTS = True

ASSESSMENT_TYPE_VALUES_AUCTION = "values_auction"
VALUES_AUCTION_SESSION_FIELD = "values_auction.session"
VALUES_AUCTION_RESULT_FIELD = "values_auction.result"
VALUES_AUCTION_INTERPRETATION_FIELD = "values_auction.interpretation"
VALUES_AUCTION_DUAL_SESSION_FIELD = "values_auction.dual_session"

VALUE_TYPE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "稳定关怀型": {
        "description": "你整体更偏保守维持和超越自我，既想关系可靠，也很在意彼此照顾。",
        "love_style": "你在关系里更看重稳定投入、责任感和长期可持续。",
        "match_suggestion": "建议找情绪稳定、说到做到、愿意经营日常的人。",
        "caution": "要留意自己会不会为了稳定，忍掉太多真实需求。",
    },
    "自主探索型": {
        "description": "你整体更偏开放变化，想自己决定怎么活，也不喜欢关系把人管死。",
        "love_style": "你需要空间、尊重和边界清楚的靠近方式。",
        "match_suggestion": "建议找独立、不过度控制、能接受彼此节奏不同的人。",
        "caution": "要留意自己会不会把需要空间说成不需要别人。",
    },
    "成就驱动型": {
        "description": "你整体更偏自我提升，想把自己做强，也在意外部认可和影响力。",
        "love_style": "你在关系里会自然关注成长性、能力感和现实匹配度。",
        "match_suggestion": "建议找尊重上进心、能理解目标感的人。",
        "caution": "要留意关系别只剩协作和评估，缺少情感流动。",
    },
    "理想共益型": {
        "description": "你整体更偏超越自我，比较看重善意、公平和共同价值。",
        "love_style": "你会在关系里在意彼此是否同频，是否对人和世界有基本善意。",
        "match_suggestion": "建议找愿意共情、有公共感、不是只顾自己的人。",
        "caution": "要留意自己会不会对价值一致性要求过高，忽略现实磨合。",
    },
    "稳中求进型": {
        "description": "你既看重稳定，也有明确上进心，想把生活和成就都经营好。",
        "love_style": "你会同时看关系可靠度和现实成长性，不太接受只谈感觉不谈落地。",
        "match_suggestion": "建议找务实、成熟、能一起处理现实问题的人。",
        "caution": "要留意自己是不是把伴侣也变成项目管理对象。",
    },
    "平衡成长型": {
        "description": "你的排序比较均衡，说明你不是单点极强，而是会整体评估一个人和一种生活。",
        "love_style": "你在关系里既看感受，也看边界和现实承接。",
        "match_suggestion": "建议找整体价值排序接近、愿意沟通取舍的人。",
        "caution": "要留意自己标准太分散，最后很难说清真正底线。",
    },
}


def calculate_hidden_values(bids: list[dict[str, Any]]) -> dict[str, float]:
    """根据出价计算 Schwartz 10 价值分布。"""
    if not bids:
        return {}

    lot_hidden_values: dict[str, list[dict[str, Any]]] = {
        lot["lot_id"]: lot["hidden_values"] for lot in VALUES_AUCTION_LOTS
    }
    value_scores = {key: 0.0 for key in SCHWARTZ_VALUE_KEYS}
    total_chips = 0

    for bid in bids:
        lot_id = bid.get("lot_id", "")
        chips = float(bid.get("chips", 0) or 0)
        if chips <= 0:
            continue
        for hv in lot_hidden_values.get(lot_id, []):
            key = hv.get("key", "")
            weight = float(hv.get("weight", 0) or 0)
            if key in value_scores:
                value_scores[key] += chips * weight
        total_chips += chips

    if total_chips <= 0:
        return {}

    normalized = {
        key: round(score / total_chips, 3)
        for key, score in value_scores.items()
        if score > 0
    }
    return normalized


def calculate_higher_order_values(hidden_values: dict[str, float]) -> dict[str, float]:
    """把 10 个价值汇总到 4 个高阶方向。"""
    if not hidden_values:
        return {}

    higher_order = {
        "openness_to_change": 0.0,
        "conservation": 0.0,
        "self_enhancement": 0.0,
        "self_transcendence": 0.0,
    }
    for key, score in hidden_values.items():
        for dimension, weight in SCHWARTZ_TO_HIGHER_ORDER.get(key, ()):
            higher_order[dimension] += score * weight
    return {
        key: round(value, 3)
        for key, value in higher_order.items()
        if value > 0
    }


def calculate_internal_tensions(hidden_values: dict[str, float]) -> list[dict[str, Any]]:
    """识别用户内部最明显的价值拉扯。"""
    tensions: list[dict[str, Any]] = []
    for left, right in OPPOSING_VALUE_PAIRS:
        left_score = float(hidden_values.get(left, 0))
        right_score = float(hidden_values.get(right, 0))
        if left_score >= 0.12 and right_score >= 0.12:
            tensions.append({
                "left": left,
                "right": right,
                "left_label": SCHWARTZ_VALUE_LABELS.get(left, left),
                "right_label": SCHWARTZ_VALUE_LABELS.get(right, right),
                "intensity": round(min(left_score, right_score), 3),
                "description": _build_tension_description(left, right),
            })
    tensions.sort(key=lambda item: item["intensity"], reverse=True)
    return tensions


def _build_tension_description(left: str, right: str) -> str:
    descriptions = {
        ("self_direction", "conformity"): "你既想按自己方式活，也不太想破坏关系秩序。",
        ("stimulation", "security"): "你一边想要变化和刺激，一边又怕生活失控。",
        ("achievement", "benevolence"): "你既想证明自己，也会顾虑身边人的感受和关系成本。",
        ("power", "universalism"): "你既在意掌控和影响力，也在意公平和更大的公共价值。",
    }
    return descriptions.get((left, right), "你在两种不同价值之间存在明显拉扯。")


def get_top_hidden_values(hidden_values: dict[str, float], top_n: int = 3) -> list[dict[str, Any]]:
    sorted_values = sorted(hidden_values.items(), key=lambda item: item[1], reverse=True)
    return [{"key": key, "weight": weight} for key, weight in sorted_values[:top_n]]


def classify_value_type_from_hidden(hidden_values: dict[str, float]) -> str:
    """基于高阶方向给一个兼容旧前端的简明标签。"""
    if not hidden_values:
        return "平衡成长型"

    higher_order = calculate_higher_order_values(hidden_values)
    top_dimensions = sorted(higher_order.items(), key=lambda item: item[1], reverse=True)
    top_keys = [item[0] for item in top_dimensions[:2]]

    if "conservation" in top_keys and "self_transcendence" in top_keys:
        return "稳定关怀型"
    if "openness_to_change" in top_keys and higher_order.get("openness_to_change", 0) >= 0.3:
        return "自主探索型"
    if "self_enhancement" in top_keys and higher_order.get("self_enhancement", 0) >= 0.24:
        return "成就驱动型"
    if "self_transcendence" in top_keys and higher_order.get("self_transcendence", 0) >= 0.24:
        return "理想共益型"
    if "conservation" in top_keys and "self_enhancement" in top_keys:
        return "稳中求进型"
    return "平衡成长型"


def get_value_type_info(value_type: str) -> dict[str, Any]:
    return VALUE_TYPE_DEFINITIONS.get(value_type, VALUE_TYPE_DEFINITIONS["平衡成长型"])


def xiaoya_message_from_result(result: dict[str, Any]) -> str:
    """生成更贴近 Schwartz 结构的自然语言解读。"""
    top3 = result.get("top3", [])
    top3_titles = [item.get("title", "") for item in top3 if item.get("chips", 0) > 0]
    hidden_values = result.get("hidden_values", {})
    top_hidden_values = result.get("top_hidden_values", []) or get_top_hidden_values(hidden_values)
    higher_order_values = result.get("higher_order_values", {}) or calculate_higher_order_values(hidden_values)
    internal_tensions = result.get("internal_tensions", []) or calculate_internal_tensions(hidden_values)
    value_type = str(result.get("value_type") or classify_value_type_from_hidden(hidden_values))
    type_info = get_value_type_info(value_type)

    top_hidden_labels = [SCHWARTZ_VALUE_LABELS.get(hv.get("key", ""), hv.get("key", "")) for hv in top_hidden_values[:3]]
    higher_order_labels = [
        HIGHER_ORDER_LABELS.get(key, key)
        for key, _ in sorted(higher_order_values.items(), key=lambda item: item[1], reverse=True)[:2]
    ]

    message = "亲爱的，这题最有意思的地方，不是你选了哪几件拍品，而是你在取舍时暴露了自己最稳的价值排序。\n\n"
    message += f"这次你的整体底色更像 **{value_type}**。\n"
    message += f"{type_info.get('description', '')}\n\n"

    if top3_titles:
        message += f"你最舍不得放手的人生画面是：{'、'.join(top3_titles[:3])}。\n"
    if top_hidden_labels:
        message += f"翻译成底层价值，就是你特别在意：{'、'.join(top_hidden_labels)}。\n"
    if higher_order_labels:
        message += f"再往上一层看，你更偏：{' + '.join(higher_order_labels)}。\n\n"
    else:
        message += "\n"

    if internal_tensions:
        strongest = internal_tensions[0]
        message += f"你内心还有一股明显拉扯：一边想要{strongest.get('left_label')}，一边又舍不得{strongest.get('right_label')}。"
        message += f"{strongest.get('description', '')}\n\n"

    message += f"放到关系里看，{type_info.get('love_style', '')}\n"
    message += f"现实一点说，{type_info.get('match_suggestion', '')}\n"
    message += f"你最需要留意的是：{type_info.get('caution', '')}\n\n"
    message += "真正适合你的人，不一定和你一模一样，但至少不会反复踩你最核心的价值排序。"
    return message
