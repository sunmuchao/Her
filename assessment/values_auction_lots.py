"""
价值观拍卖会拍品定义

v3.0 游戏化改进版：
- 从 20 个精简到 9 个拍品（少即是多）
- 每个拍品一句话，不超过10字（画面感 + 情绪感）
- 添加主题色和图标（游戏卡牌感）
- 设计冲突对（取舍痛感）

设计原则：
1. 具体场景比抽象词更容易产生画面
2. 具体拍品更容易逼出痛感和取舍
3. 拍品之间必须有冲突，让用户纠结
4. 一句话，1秒理解，有画面感
"""

from __future__ import annotations

from typing import Any


# ============================================================
# 隐藏价值字典（18个底层价值）
# ============================================================

HIDDEN_VALUE_KEYS: list[str] = [
    "wealth",        # 财富
    "status",        # 地位
    "power",         # 权力
    "freedom",       # 自由
    "security",      # 安全感
    "love",          # 爱情
    "loyalty",       # 忠诚
    "family",        # 家庭
    "friendship",    # 友情
    "companionship", # 陪伴
    "recognition",   # 认可
    "self_actualization",  # 自我实现
    "wisdom",        # 智慧
    "inner_peace",   # 内心平静
    "independence",  # 独立
    "altruism",      # 利他
    "social_responsibility",  # 社会责任
    "meaning",       # 意义
]


# ============================================================
# 四大维度定义
# ============================================================

AUCTION_DIMENSIONS: dict[str, str] = {
    "material_achievement": "物质与成就",
    "emotion_connection": "情感与连接",
    "self_growth": "自我与成长",
    "altruism_devotion": "利他与奉献",
}


# ============================================================
# 9 个拍品定义（v3.0 游戏化改进版）
# ============================================================

VALUES_AUCTION_LOTS: list[dict[str, Any]] = [
    # ========== A. 物质与成就（2个）==========
    {
        "lot_id": "financial_freedom",
        "title": "这辈子都不用再为钱妥协",  # 精简文案：一句话，不超过10字
        "dimension": "material_achievement",
        "hidden_values": [
            {"key": "freedom", "weight": 0.45},
            {"key": "security", "weight": 0.35},
            {"key": "independence", "weight": 0.20},
        ],
        "theme_color": "#F59E0B",  # 金色
        "icon": "💰",  # 钱袋
        "interpretation": "再也不用为生计妥协了，想做什么就做什么",  # 一句解读
        "conflict_hint": "如果保留这个，可能意味着你更看重自由，而后面的'一个不会离开你的人'代表安全感，你可能需要放弃",  # 冲突提示
    },
    {
        "lot_id": "elite_status",
        "title": "走到哪里都让人高看一眼",  # 精简文案
        "dimension": "material_achievement",
        "hidden_values": [
            {"key": "status", "weight": 0.45},
            {"key": "recognition", "weight": 0.35},
            {"key": "power", "weight": 0.20},
        ],
        "theme_color": "#9333EA",  # 紫色
        "icon": "👑",  # 勋章/皇冠
        "interpretation": "社会地位和尊重，走到哪里都有面子",
        "conflict_hint": "如果保留这个，可能意味着你更看重外部认可，而后面的'内心平静'代表自我认同，你可能需要放弃",
    },

    # ========== B. 情感与连接（3个）==========
    {
        "lot_id": "soulmate",
        "title": "一个永远不会离开你的人",  # 精简文案
        "dimension": "emotion_connection",
        "hidden_values": [
            {"key": "love", "weight": 0.45},
            {"key": "loyalty", "weight": 0.35},
            {"key": "security", "weight": 0.20},
        ],
        "theme_color": "#EF4444",  # 红色
        "icon": "❤️",  # 心形
        "interpretation": "安全感、被选择、忠诚，一个永远不会离开你的人",
        "conflict_hint": "如果保留这个，可能意味着你更看重安全感，而后面的'想做什么就做什么'代表自由，你可能需要放弃",
    },
    {
        "lot_id": "family_health",
        "title": "全家人健康平安到百岁",  # 精简文案
        "dimension": "emotion_connection",
        "hidden_values": [
            {"key": "family", "weight": 0.45},
            {"key": "security", "weight": 0.35},
            {"key": "companionship", "weight": 0.20},
        ],
        "theme_color": "#F97316",  # 橙色
        "icon": "🏠",  # 房子
        "interpretation": "家庭、稳定、照料，全家人健康平安",
        "conflict_hint": "如果保留这个，可能意味着你更看重家庭，而后面的'做一件改变世界的事'代表个人成就，你可能需要放弃",
    },
    {
        "lot_id": "deep_understanding",
        "title": "一个真正懂你的人",  # 精简文案
        "dimension": "emotion_connection",
        "hidden_values": [
            {"key": "companionship", "weight": 0.40},
            {"key": "love", "weight": 0.35},
            {"key": "understanding", "weight": 0.25},
        ],
        "theme_color": "#EC4899",  # 粉色
        "icon": "🎯",  # 目标
        "interpretation": "理解、共鸣、归属，一个真正懂你的人",
        "conflict_hint": "如果保留这个，可能意味着你更看重被理解，而后面的'不需要讨好'代表独立，你可能需要放弃",
    },

    # ========== C. 自我与成长（2个）==========
    {
        "lot_id": "total_freedom",
        "title": "想做什么就做什么，没人管",  # 精简文案
        "dimension": "self_growth",
        "hidden_values": [
            {"key": "freedom", "weight": 0.50},
            {"key": "independence", "weight": 0.30},
            {"key": "self_actualization", "weight": 0.20},
        ],
        "theme_color": "#3B82F6",  # 蓝色
        "icon": "🕊️",  # 翅膀
        "interpretation": "自由、独立、自主，想做什么就做什么",
        "conflict_hint": "如果保留这个，可能意味着你更看重自由，而前面的'一个不会离开你的人'代表安全感，这两个可能冲突",
    },
    {
        "lot_id": "inner_peace",
        "title": "内心平静，不再焦虑",  # 精简文案
        "dimension": "self_growth",
        "hidden_values": [
            {"key": "inner_peace", "weight": 0.55},
            {"key": "wisdom", "weight": 0.30},
            {"key": "meaning", "weight": 0.15},
        ],
        "theme_color": "#10B981",  # 绿色
        "icon": "🧘",  # 瑜伽
        "interpretation": "精神稳定、觉察、自足，内心平静不再焦虑",
        "conflict_hint": "如果保留这个，可能意味着你更看重内心平静，而前面的'走到哪里都让人高看一眼'代表外部认同，这两个可能冲突",
    },

    # ========== D. 利他与奉献（2个）==========
    {
        "lot_id": "change_world",
        "title": "做一件改变世界的事",  # 精简文案
        "dimension": "altruism_devotion",
        "hidden_values": [
            {"key": "altruism", "weight": 0.45},
            {"key": "social_responsibility", "weight": 0.35},
            {"key": "meaning", "weight": 0.20},
        ],
        "theme_color": "#1E40AF",  # 深蓝
        "icon": "🌍",  # 地球
        "interpretation": "意义、使命感、影响，做一件改变世界的事",
        "conflict_hint": "如果保留这个，可能意味着你更看重宏大意义，而前面的'全家人健康平安'代表个人安稳，这两个可能冲突",
    },
    {
        "lot_id": "help_many",
        "title": "默默帮助很多人",  # 精简文案
        "dimension": "altruism_devotion",
        "hidden_values": [
            {"key": "altruism", "weight": 0.55},
            {"key": "meaning", "weight": 0.30},
            {"key": "inner_peace", "weight": 0.15},
        ],
        "theme_color": "#FBBF24",  # 黄色
        "icon": "🤲",  # 手心
        "interpretation": "利他、温柔、道德，默默帮助很多人",
        "conflict_hint": "如果保留这个，可能意味着你更看重隐性的利他，而前面的'走到哪里都让人高看一眼'代表显性的社会地位，这两个可能冲突",
    },
]


# ============================================================
# 拍品 ID 到标题的映射
# ============================================================

LOT_ID_TO_TITLE: dict[str, str] = {
    lot["lot_id"]: lot["title"] for lot in VALUES_AUCTION_LOTS
}


# ============================================================
# 冲突对设计（v3.0 精简版：刻意制造的选择张力）
# ============================================================

CONFLICT_PAIRS: list[dict[str, Any]] = [
    {
        "pair_id": "freedom_vs_security",
        "lot_a": "total_freedom",
        "lot_b": "soulmate",
        "conflict_type": "自由 vs 安全感",
        "description": "想做什么就做什么，还是一个不会离开你的人？自由和安全感，只能选一个",
        "intensity": "high",  # 高冲突强度
    },
    {
        "pair_id": "status_vs_peace",
        "lot_a": "elite_status",
        "lot_b": "inner_peace",
        "conflict_type": "外部认同 vs 内心平静",
        "description": "走到哪里都让人高看一眼，还是内心平静不再焦虑？外部认同和内心平静，只能选一个",
        "intensity": "high",
    },
    {
        "pair_id": "world_vs_family",
        "lot_a": "change_world",
        "lot_b": "family_health",
        "conflict_type": "宏大意义 vs 个人安稳",
        "description": "做一件改变世界的事，还是全家人健康平安？宏大意义和个人安稳，只能选一个",
        "intensity": "medium",
    },
    {
        "pair_id": "money_vs_understanding",
        "lot_a": "financial_freedom",
        "lot_b": "deep_understanding",
        "conflict_type": "物质自由 vs 情感理解",
        "description": "这辈子都不用再为钱妥协，还是一个真正懂你的人？物质自由和情感理解，只能选一个",
        "intensity": "medium",
    },
    {
        "pair_id": "status_vs_altruism",
        "lot_a": "elite_status",
        "lot_b": "help_many",
        "conflict_type": "显性地位 vs 隐性利他",
        "description": "走到哪里都让人高看一眼，还是默默帮助很多人？显性地位和隐性利他，只能选一个",
        "intensity": "medium",
    },
]


# ============================================================
# 配置常量（v3.0 游戏化改进版）
# ============================================================

TOTAL_CHIPS = 10       # 总筹码数（保留，用于筹码分配模式）
MIN_BID = 0            # 最小出价
MAX_BID = 5            # 最大出价（单拍品，防止独占）
LOT_COUNT = 9          # 拍品数量（从20精简到9）
MAX_KEEP = 3           # 最终只能保留3个拍品（核心取舍机制）

# 新增：逐个展示模式的配置
SEQUENTIAL_DISPLAY = True  # 启用逐个展示模式（一次只展示一个拍品）
SHOW_PROGRESS = True      # 显示进度（"第3件拍品（共9件）")
SHOW_TENSION_HINTS = True # 显示紧张感提示（名额有限提示）
SHOW_CONFLICT_HINTS = True # 显示冲突提示（帮助理解取舍）

ASSESSMENT_TYPE_VALUES_AUCTION = "values_auction"
VALUES_AUCTION_SESSION_FIELD = "values_auction.session"
VALUES_AUCTION_RESULT_FIELD = "values_auction.result"
VALUES_AUCTION_INTERPRETATION_FIELD = "values_auction.interpretation"
VALUES_AUCTION_DUAL_SESSION_FIELD = "values_auction.dual_session"


# ============================================================
# 隐藏价值计算函数
# ============================================================

def calculate_hidden_values(
    bids: list[dict[str, Any]]
) -> dict[str, float]:
    """
    根据出价计算隐藏价值权重分布

    Args:
        bids: 出价列表，每个元素包含 lot_id 和 chips

    Returns:
        隐藏价值权重分布（归一化后）
    """
    if not bids:
        return {}

    # 获取拍品的隐藏价值映射
    lot_hidden_values: dict[str, list[dict[str, Any]]] = {
        lot["lot_id"]: lot["hidden_values"] for lot in VALUES_AUCTION_LOTS
    }

    # 累加每个隐藏价值的权重
    value_scores: dict[str, float] = {}
    total_chips = 0

    for bid in bids:
        lot_id = bid.get("lot_id", "")
        chips = bid.get("chips", 0)

        if chips == 0:
            continue

        hidden_values = lot_hidden_values.get(lot_id, [])
        for hv in hidden_values:
            key = hv.get("key", "")
            weight = hv.get("weight", 0)

            if key:
                value_scores[key] = value_scores.get(key, 0) + chips * weight

        total_chips += chips

    # 归一化
    if total_chips > 0:
        for key in value_scores:
            value_scores[key] = round(value_scores[key] / total_chips, 2)

    return value_scores


def get_top_hidden_values(
    hidden_values: dict[str, float],
    top_n: int = 3
) -> list[dict[str, Any]]:
    """
    获取权重最高的隐藏价值

    Args:
        hidden_values: 隐藏价值权重分布
        top_n: 返回前 N 个

    Returns:
        排序后的隐藏价值列表
    """
    sorted_values = sorted(
        hidden_values.items(),
        key=lambda x: x[1],
        reverse=True
    )

    return [
        {"key": key, "weight": weight}
        for key, weight in sorted_values[:top_n]
    ]


# ============================================================
# 价值观类型分类（基于隐藏价值）
# ============================================================

VALUE_TYPE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "安全感至上型": {
        "condition": "security >= 0.25",
        "description": "你最看重稳定和安全感，不喜欢冒险和不确定性",
        "love_style": "你在关系中需要稳定和可预测性，不喜欢突然的变化",
        "match_suggestion": "建议找同样看重安全感的人",
        "caution": "可能与'自由型'产生冲突（稳定 vs 流动）",
    },
    "自由灵魂型": {
        "condition": "freedom >= 0.25",
        "description": "你最看重自由和自主，不想被束缚",
        "love_style": "你在关系中需要空间和独立性，不喜欢被控制",
        "match_suggestion": "建议找同样看重自由的人",
        "caution": "可能与'安全感型'产生冲突（自由 vs 稳定）",
    },
    "情感连接型": {
        "condition": "love >= 0.20 or companionship >= 0.20",
        "description": "你最看重情感连接和陪伴",
        "love_style": "你在关系中需要深度连接，喜欢亲密和陪伴",
        "match_suggestion": "建议找同样看重情感的人",
        "caution": "可能与'独立型'产生冲突（依赖 vs 独立）",
    },
    "成就驱动型": {
        "condition": "status >= 0.20 or power >= 0.20",
        "description": "你最看重成就和社会地位",
        "love_style": "你在关系中看重对方的成就和社会价值",
        "match_suggestion": "建议找同样有上进心的人",
        "caution": "可能与'平静型'产生冲突（进取 vs 安逸）",
    },
    "利他奉献型": {
        "condition": "altruism >= 0.20 or social_responsibility >= 0.20",
        "description": "你最看重帮助他人和社会贡献",
        "love_style": "你在关系中看重共同的价值观和社会责任感",
        "match_suggestion": "建议找同样有奉献精神的人",
        "caution": "可能与'自我型'产生冲突（利他 vs 自我）",
    },
    "意义追寻型": {
        "condition": "meaning >= 0.20 or inner_peace >= 0.20",
        "description": "你最看重人生意义和内心平静",
        "love_style": "你在关系中看重精神层面的共鸣",
        "match_suggestion": "建议找同样追求意义的人",
        "caution": "可能与'物质型'产生冲突（精神 vs 物质）",
    },
    "综合型": {
        "condition": "其他情况",
        "description": "你的价值观分布比较均衡，多个维度都有侧重",
        "love_style": "你在关系中比较灵活，能适应不同类型的人",
        "match_suggestion": "匹配范围广，但需要找到共鸣点",
        "caution": "可能标准不够明确，需要多了解自己",
    },
}


def classify_value_type_from_hidden(
    hidden_values: dict[str, float]
) -> str:
    """
    根据隐藏价值分布分类价值观类型

    Args:
        hidden_values: 隐藏价值权重分布

    Returns:
        价值观类型名称
    """
    if not hidden_values:
        return "综合型"

    # 按优先级判断类型
    if hidden_values.get("security", 0) >= 0.25:
        return "安全感至上型"
    elif hidden_values.get("freedom", 0) >= 0.25:
        return "自由灵魂型"
    elif hidden_values.get("love", 0) >= 0.20 or hidden_values.get("companionship", 0) >= 0.20:
        return "情感连接型"
    elif hidden_values.get("status", 0) >= 0.20 or hidden_values.get("power", 0) >= 0.20:
        return "成就驱动型"
    elif hidden_values.get("altruism", 0) >= 0.20 or hidden_values.get("social_responsibility", 0) >= 0.20:
        return "利他奉献型"
    elif hidden_values.get("meaning", 0) >= 0.20 or hidden_values.get("inner_peace", 0) >= 0.20:
        return "意义追寻型"
    else:
        return "综合型"


def get_value_type_info(value_type: str) -> dict[str, Any]:
    """
    获取价值观类型的详细信息
    """
    return VALUE_TYPE_DEFINITIONS.get(value_type, VALUE_TYPE_DEFINITIONS["综合型"])


def xiaoya_message_from_result(result: dict[str, Any]) -> str:
    """生成小雅风格的价值观拍卖会解读消息。"""
    top3 = result.get("top3", [])
    top3_titles = [t.get("title", "") for t in top3 if t.get("chips", 0) > 0]
    top_hidden_values = result.get("top_hidden_values", [])
    value_type = str(result.get("value_type") or classify_value_type_from_hidden(result.get("hidden_values", {})))
    type_info = get_value_type_info(value_type)
    hidden_labels = {
        "freedom": "自由", "security": "安全感", "love": "爱情",
        "status": "地位", "wealth": "财富", "power": "权力",
        "loyalty": "忠诚", "family": "家庭", "companionship": "陪伴",
        "recognition": "认可", "self_actualization": "自我实现",
        "wisdom": "智慧", "inner_peace": "内心平静",
        "independence": "独立", "altruism": "利他", "meaning": "意义",
        "social_responsibility": "社会责任",
    }
    top_hidden_labels = [hidden_labels.get(hv.get("key", ""), hv.get("key", "")) for hv in top_hidden_values[:3]]

    # 判断拍品的类型组合
    has_financial = "这辈子都不用再为钱妥协" in top3_titles
    has_status = "走到哪里都让人高看一眼" in top3_titles
    has_love = "一个永远不会离开你的人" in top3_titles
    has_understanding = "一个真正懂你的人" in top3_titles
    has_freedom = "想做什么就做什么，没人管" in top3_titles
    has_health = "全家人健康平安到百岁" in top3_titles
    has_peace = "内心平静，不再焦虑" in top3_titles
    has_meaning = "做一件改变世界的事" in top3_titles
    has_support = "一个无条件支持你的人" in top3_titles

    message = "亲爱的，价值观拍卖会这题，真的很能看出一个人到底在筛什么。\n\n"
    message += f"你这次整体更偏 **{value_type}**。\n"
    message += f"{type_info.get('description', '')}。\n\n"
    if top3_titles:
        message += f"你最愿意下重注的，是：{'、'.join(top3_titles[:3])}。\n"
    if top_hidden_labels:
        message += f"翻译成人话，就是你真正特别在意的是：{'、'.join(top_hidden_labels)}。\n\n"
    else:
        message += "\n"

    if has_financial and has_status and has_love:
        insight = "你一边要掌控感，一边又很怕失去关系。这种组合说明你不只想过得好，你还想在重要关系里不被抛下。"
        match = "最适合你的人，通常既有稳定度，也能理解你的成就心，不会一边享受你的优秀，一边又嫌你太强。"
        risk = "你最容易卡住的，是把关系也做成“风险管理”，结果人是留下了，亲密感却没进来。 "

    elif has_financial and has_love:
        insight = "你既要现实层面的安全，也要关系里的温度。你不是贪心，你只是很清楚：钱解决焦虑，人解决孤独。"
        match = "最适合你的人，通常既不回避现实问题，也不回避情感投入。"
        risk = "你最容易委屈的，是遇到只会给资源、不给情感的人，或者只谈感觉、不谈落地的人。"

    elif has_status and has_love:
        insight = "你很在乎被尊重，也很在乎被珍惜。你真正要的不是光鲜，而是‘我厉害的时候有人欣赏，我脆弱的时候也有人接住’。"
        match = "最适合你的人，通常既认可你的能力，也不只把你当成一个优秀的人设。"
        risk = "你最容易失望的，是别人只爱你的高光，不爱你的真实需求。"

    elif has_financial and has_freedom:
        insight = "你非常看重自主权。你想要的不是被安排得很好，而是我有能力选择自己的生活方式。"
        match = "最适合你的人，通常是边界感清楚、足够独立、不需要靠控制关系来确认安全感的人。"
        risk = "你最容易被误解的，是你明明在乎，但表达出来像“我谁都不需要”。"

    elif has_love and has_freedom:
        insight = "你对关系的要求其实很高：既要亲密，又不能窒息；既要被爱，又不能失去自己。"
        match = "最适合你的人，通常懂分寸、会靠近，也会给空间，不会把爱变成占有。"
        risk = "你最容易反复的，是一靠近就怕失去自由，一拉开又怕关系变淡。"

    elif has_love and has_understanding:
        insight = "你要的从来不只是陪伴，而是那种‘我不用解释太多，你也能懂我在意什么’的共鸣。"
        match = "最适合你的人，通常有理解力、情绪感受力，也愿意认真进入你的内心世界。"
        risk = "你最容易失落的，是关系表面没问题，但精神上始终对不上频。"

    elif has_health and has_peace:
        insight = "你现在真正想守住的，是生活的稳定感和内心的平静。对你来说，不折腾本身就是很高的价值。"
        match = "最适合你的人，通常情绪稳定、生活习惯稳、不会把关系谈成连续剧。"
        risk = "你最容易耗损的，是遇到那种把情绪起伏当热恋证明的人。"

    elif has_financial and has_health:
        insight = "你很务实，最先考虑的是生活底盘够不够稳。你对关系的要求不是花哨，而是可靠。"
        match = "最适合你的人，通常说话不浮、生活能力强、愿意一起把日子过扎实。"
        risk = "你最容易不耐烦的，是那种只有情绪价值、没有现实承担的人。"

    elif has_meaning:
        insight = "你很在意人生到底有没有更大的意义。你不太能长期待在只有吃喝住行、没有精神目标的关系里。"
        match = "最适合你的人，通常也有追求、有信念，至少愿意和你一起讨论更深层的问题。"
        risk = "你最容易失去兴趣的，是对方只关心眼前舒服，完全不在意长期价值。"

    elif has_support:
        insight = "你很需要关系里那种被托住的感觉。你未必弱，但你真的很在意‘当我扛不住时，有没有人站我这边’。"
        match = "最适合你的人，通常情绪稳定、支持欲强，也愿意在关键时刻给你后盾。"
        risk = "你最容易踩的坑，是太渴望被托住，结果忽略了关系也需要双向流动。"

    else:
        if top_hidden_labels:
            insight = f"你真正筛人的标准，其实不是表面条件，而是这些更底层的东西：{'、'.join(top_hidden_labels)}。"
            match = f"最适合你的人，通常在关系节奏和价值排序上会和你比较同频。"
            risk = type_info.get("caution", "如果价值排序差太多，再喜欢也容易越走越累。")
        else:
            insight = "你这次给出的信号比较综合，说明你挑人时不是只看一个点，而是会整体评估。"
            match = "最适合你的人，通常不是单项特别强，而是整体价值观跟你差得不远。"
            risk = "你最容易卡住的，是标准分散，最后连自己都说不清到底为什么不合适。"

    if insight.startswith("你真正筛人的标准，其实不是表面条件，而是这些更底层的东西："):
        message += f"{insight}\n\n"
    else:
        message += f"说白了，你真正在筛的不是表面条件，而是这个人能不能和你的底层价值观对上。\n{insight}\n\n"
    match_line = match
    if match_line.startswith("最适合你的人，"):
        match_line = match_line.replace("最适合你的人，", "", 1).strip()
    message += f"真要说适合你的人，通常是这种：{match_line}\n"
    message += f"你在关系里多半会更在意这件事：{type_info.get('love_style', '')}。\n"
    message += f"现实一点说，{type_info.get('match_suggestion', '').rstrip('。')}。\n\n"
    message += "我给你三条最有用的提醒：\n"
    message += "1. 看人别只听TA嘴上怎么说，要看TA会不会真的为这些价值做选择。\n"
    message += "2. 长期合适的人，不一定和你一模一样，但至少不能踩你最核心的底线。\n"
    message += "3. 你现在最该想清楚的，不是“我喜欢什么人”，而是“我绝对不要什么关系”。\n\n"
    message += f"你最容易踩的坑是：{risk.rstrip('。')}。\n\n"
    message += "你要是愿意，我下一条可以继续帮你拆：你最适合找什么样的伴侣价值观，以及你最该避开的关系模式。"
    return message
