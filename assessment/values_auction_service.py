"""
价值观拍卖会服务

实现单人拍卖和双人拍卖的核心逻辑。
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from assessment.values_auction_lots import (
    ASSESSMENT_TYPE_VALUES_AUCTION,
    VALUES_AUCTION_DUAL_SESSION_FIELD,
    VALUES_AUCTION_INTERPRETATION_FIELD,
    VALUES_AUCTION_RESULT_FIELD,
    VALUES_AUCTION_SESSION_FIELD,
    VALUES_AUCTION_LOTS,
    LOT_ID_TO_TITLE,
    LOT_COUNT,
    TOTAL_CHIPS,
    MIN_BID,
    MAX_BID,
    AUCTION_DIMENSIONS,
    calculate_hidden_values,
    get_top_hidden_values,
    classify_value_type_from_hidden,
    get_value_type_info,
    xiaoya_message_from_result,  # 新增：小雅消息生成
)
from persona_memory_sync.persona_memory_lib import (
    apply_persona_patch,
    fetch_persona,
    mysql_connect,
    normalize_patch,
    parse_mysql_source,
    quote_mysql_ident,
    release_persona_connection,
)


# ============================================================
# 辅助函数
# ============================================================

def _resolve_source(source: str | None) -> tuple[str, str]:
    """解析数据源"""
    parsed = parse_mysql_source(source)
    normalized_source = str(parsed["source"])
    table = str(parsed["table"])
    return normalized_source, table


def _now() -> str:
    """获取当前时间字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    """序列化为JSON"""
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_json(value: Any) -> dict[str, Any]:
    """解析JSON"""
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        data = json.loads(str(value))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _generate_assessment_id() -> str:
    """生成测评ID"""
    return f"va_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _generate_session_id() -> str:
    """生成双人session ID"""
    return f"dual_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _save_observation(
    cursor: Any,
    *,
    observation_table: str,
    user_key: str,
    field_name: str,
    field_value: Any,
    conversation_ref: str,
    source_channel: str = "values_auction",
    source_type: str = "explicit",
    evidence_text: str = "",
) -> None:
    """写入 observation 表，绕开 persona patch 的字段白名单。"""
    cursor.execute(
        f"DELETE FROM {quote_mysql_ident(observation_table)} WHERE user_key = %s AND conversation_ref = %s AND field_name = %s",
        (user_key, conversation_ref, field_name),
    )
    cursor.execute(
        f"""
        INSERT INTO {quote_mysql_ident(observation_table)}
          (user_key, persona_id, field_name, field_value, source_type, confidence_score,
           evidence_text, conversation_ref, source_channel, action_type, applied_to_persona,
           applied_to_profile, created_at)
        VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, 'insert', 1, 0, %s)
        """,
        (
            user_key,
            field_name,
            _json(field_value) if isinstance(field_value, (dict, list)) else str(field_value),
            source_type,
            100,
            evidence_text,
            conversation_ref,
            source_channel,
            _now(),
        ),
    )


def _persist_dual_session(
    cursor: Any,
    *,
    observation_table: str,
    session: dict[str, Any],
    conversation_ref: str,
    evidence_text: str,
) -> None:
    """将同一份双人 session 同步写入双方 observation，避免双方读取到不同状态。"""
    for participant_key in (
        str(session.get("user_a_key") or "").strip(),
        str(session.get("user_b_key") or "").strip(),
    ):
        if not participant_key:
            continue
        _save_observation(
            cursor,
            observation_table=observation_table,
            user_key=participant_key,
            field_name=VALUES_AUCTION_DUAL_SESSION_FIELD,
            field_value=session,
            conversation_ref=conversation_ref,
            evidence_text=evidence_text,
        )


@dataclass(frozen=True)
class ValuesAuctionSession:
    """拍卖会话数据类"""
    assessment_id: str
    user_key: str
    status: str  # pending | in_progress | completed
    created_at: str


@dataclass(frozen=True)
class DualAuctionSession:
    """双人拍卖会话数据类"""
    session_id: str
    user_a_key: str
    user_b_key: str
    user_a_status: str  # pending | in_progress | done
    user_b_status: str
    created_at: str


# ============================================================
# 单人拍卖服务
# ============================================================

def start_values_auction(
    *,
    user_key: str,
    source: str | None = None,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """
    开始价值观拍卖（单人模式）

    Returns:
        介绍卡片数据
    """
    assessment_id = _generate_assessment_id()
    normalized_source, _ = _resolve_source(source)
    session_data = {
        "assessment_id": assessment_id,
        "assessment_type": ASSESSMENT_TYPE_VALUES_AUCTION,
        "user_key": user_key,
        "status": "pending",
        "created_at": _now(),
    }
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=user_key,
                field_name=VALUES_AUCTION_SESSION_FIELD,
                field_value=session_data,
                conversation_ref=assessment_id,
                evidence_text="values auction started",
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)

    # 返回介绍卡片
    return {
        "card_type": "values_auction_intro",
        "assessment_id": assessment_id,
        "intro_data": {
            "title": "价值观拍卖会",
            "description": "你有10个筹码，竞拍你最想要的人生\n不可能全都拿到，必须取舍",
            "total_chips": TOTAL_CHIPS,
            "lot_count": LOT_COUNT,
            "dimensions": AUCTION_DIMENSIONS,
            "duration": "约2分钟",
            "reward": "解锁三观匹配分析",
        },
    }


def get_lots_list(
    *,
    assessment_id: str,
) -> dict[str, Any]:
    """
    获取拍品列表卡片

    Returns:
        拍品列表卡片数据（按维度分组）
    """
    # 按维度分组拍品
    lots_by_dimension: dict[str, list[dict[str, Any]]] = {}
    for lot in VALUES_AUCTION_LOTS:
        dimension = lot.get("dimension", "other")
        if dimension not in lots_by_dimension:
            lots_by_dimension[dimension] = []
        lots_by_dimension[dimension].append({
            "lot_id": lot.get("lot_id", ""),
            "title": lot.get("title", ""),
            "dimension": dimension,
        })

    return {
        "card_type": "values_auction_lots",
        "assessment_id": assessment_id,
        "lots_data": {
            "lots": VALUES_AUCTION_LOTS,
            "lots_by_dimension": lots_by_dimension,
            "dimensions": AUCTION_DIMENSIONS,
            "total_chips": TOTAL_CHIPS,
            "min_bid": MIN_BID,
            "max_bid": MAX_BID,
        },
    }


def validate_bids(bids: list[dict[str, Any]]) -> tuple[bool, str]:
    """
    校验竞拍结果

    Returns:
        (是否有效, 错误信息)
    """
    if not bids:
        return False, "竞拍结果为空"

    # 校验总筹码
    total_chips = sum(b.get("chips", 0) for b in bids)
    if total_chips > TOTAL_CHIPS:
        return False, f"筹码总数超过{TOTAL_CHIPS}"

    # 校验每个拍品的筹码范围
    for bid in bids:
        chips = bid.get("chips", 0)
        if chips < MIN_BID or chips > MAX_BID:
            lot_id = bid.get("lot_id", "unknown")
            return False, f"拍品 {lot_id} 的筹码数 {chips} 不在有效范围"

    # 校验拍品ID是否有效
    valid_lot_ids = {lot["lot_id"] for lot in VALUES_AUCTION_LOTS}
    for bid in bids:
        lot_id = bid.get("lot_id", "")
        if lot_id not in valid_lot_ids:
            return False, f"无效的拍品ID: {lot_id}"

    return True, ""


def sort_and_rank_bids(bids: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    排序并计算排名和百分比

    Returns:
        排序后的竞拍结果，包含 rank 和 percentage
    """
    # 按筹码降序排序
    sorted_bids = sorted(bids, key=lambda x: x.get("chips", 0), reverse=True)

    # 计算排名和百分比
    for i, bid in enumerate(sorted_bids):
        bid["rank"] = i + 1
        bid["percentage"] = round(bid.get("chips", 0) / TOTAL_CHIPS * 100, 1)
        bid["title"] = LOT_ID_TO_TITLE.get(bid.get("lot_id", ""), bid.get("lot_id", ""))

    return sorted_bids


def submit_auction_bids(
    *,
    assessment_id: str,
    user_key: str,
    bids: list[dict[str, Any]],
    source: str | None = None,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """
    提交竞拍结果（单人模式）

    Returns:
        结果卡片数据
    """
    # 1. 校验竞拍结果
    is_valid, error_msg = validate_bids(bids)
    if not is_valid:
        return {
            "card_type": "error",
            "error_data": {"message": error_msg},
        }

    # 2. 排序并计算排名
    sorted_bids = sort_and_rank_bids(bids)

    # 3. 计算隐藏价值权重分布
    hidden_values = calculate_hidden_values(sorted_bids)

    # 4. 分类价值观类型（基于隐藏价值）
    value_type = classify_value_type_from_hidden(hidden_values)
    top_hidden_values = get_top_hidden_values(hidden_values, top_n=3)

    # 5. 提取top3和放弃的拍品
    top3 = sorted_bids[:3]
    for lot in top3:
        lot["interpretation"] = get_lot_interpretation(
            lot.get("lot_id", ""),
            lot.get("chips", 0)
        )

    abandoned = [b.get("title", b.get("lot_id", "")) for b in sorted_bids if b.get("chips", 0) == 0]

    # 6. 构建结果数据
    result_data = {
        "assessment_id": assessment_id,
        "assessed_at": _now(),
        "config": {
            "total_chips": TOTAL_CHIPS,
            "lot_count": LOT_COUNT,
        },
        "bids": sorted_bids,
        "hidden_values": hidden_values,
        "top_hidden_values": top_hidden_values,
        "value_type": value_type,
        "value_labels": [b.get("title", "") for b in top3 if b.get("chips", 0) > 0],
        "top3": top3,
        "abandoned": abandoned,
        "confidence": 0.85,
    }

    # 7. 写入偏好表
    normalized_source, _ = _resolve_source(source)

    # 获取现有 personality_traits_json
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            persona = fetch_persona(cursor, persona_table, user_key=user_key) or {}
            existing_traits = _parse_json(persona.get("self_personality_traits_json", {}))
    finally:
        release_persona_connection(normalized_source, conn)

    # 合并价值观拍卖结果
    existing_traits["values_auction"] = result_data

    # 写入
    apply_persona_patch(
        source=normalized_source,
        user_key=user_key,
        source_type="explicit",
        normalized_patch=normalize_patch({
            "self_personality_traits_json": _json(existing_traits)
        }),
        persona_table=persona_table,
        observation_table=observation_table,
        apply_scope="persona_only",
        sync_profile=False,
        source_channel="values_auction",
    )

    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=user_key,
                field_name=VALUES_AUCTION_RESULT_FIELD,
                field_value=result_data,
                conversation_ref=assessment_id,
                evidence_text="values auction result recorded",
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)

    # 8. 生成小雅的解读消息
    xiaoya_message = xiaoya_message_from_result(result_data)

    # 9. 返回结果卡片 + 小雅消息
    return {
        "card_type": "values_auction_result",
        "assessment_id": assessment_id,
        "result_data": {
            "bids": sorted_bids,
            "hidden_values": hidden_values,
            "value_type": value_type,
            "value_labels": result_data["value_labels"],
            "top3": top3,
            "abandoned": abandoned,
            "reward": "解锁三观匹配分析",
        },
        "xiaoya_message": xiaoya_message,  # 新增：小雅的自然语言回复
    }


def get_lot_interpretation(lot_id: str, chips: int) -> str:
    """
    根据拍品和筹码数生成简短解读

    Args:
        lot_id: 拍品ID
        chips: 筹码数

    Returns:
        简短解读文本
    """
    title = LOT_ID_TO_TITLE.get(lot_id, lot_id)

    if chips >= 4:
        return f"你最想要的是'{title}'，这是你人生中最重要的"
    elif chips >= 2:
        return f"你很看重'{title}'，但不是唯一的选择"
    else:
        return f"你对'{title}'有一定兴趣，但愿意放弃"


def get_last_result(
    *,
    user_key: str,
    source: str | None = None,
    persona_table: str = "user_personas",
) -> dict[str, Any] | None:
    """
    获取用户上次拍卖结果（复用机制）

    Returns:
        上次拍卖结果，或 None
    """
    normalized_source, _ = _resolve_source(source)

    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            persona = fetch_persona(cursor, persona_table, user_key=user_key) or {}
    finally:
        release_persona_connection(normalized_source, conn)

    traits = _parse_json(persona.get("self_personality_traits_json", {}))
    values_auction = traits.get("values_auction", {})

    if values_auction and values_auction.get("assessment_id"):
        return values_auction

    return None


def generate_ai_interpretation(
    *,
    assessment_id: str,
    user_key: str,
    source: str | None = None,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """
    生成AI解读（单人模式）

    Returns:
        AI解读卡片数据
    """
    # 1. 获取拍卖结果
    normalized_source, _ = _resolve_source(source)

    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            persona = fetch_persona(cursor, persona_table, user_key=user_key) or {}
    finally:
        release_persona_connection(normalized_source, conn)

    traits = _parse_json(persona.get("self_personality_traits_json", {}))
    values_auction = traits.get("values_auction", {})

    if not values_auction:
        return {
            "card_type": "error",
            "error_data": {"message": "未找到拍卖结果"},
        }

    # 2. 获取隐藏价值信息
    hidden_values = values_auction.get("hidden_values", {})
    top_hidden_values = values_auction.get("top_hidden_values", [])
    value_type = values_auction.get("value_type", "综合型")
    type_info = get_value_type_info(value_type)

    top3 = values_auction.get("top3", [])

    # 3. 构建解读数据（先说拍下了什么，再说价值倾向）
    # 根据设计文档：先揭晓拍品，再归纳价值倾向
    top3_titles = [t.get("title", "") for t in top3 if t.get("chips", 0) > 0]

    # 构建解读语句
    if top3_titles:
        summary = f"你拍下了：{', '.join(top3_titles[:3])}。\n{type_info.get('description', '')}"
    else:
        summary = type_info.get("description", "")

    interpretation_data = {
        "summary": summary,
        "top3_analysis": [
            {
                "title": t.get("title", ""),
                "chips": t.get("chips", 0),
                "interpretation": t.get("interpretation", ""),
            }
            for t in top3
        ],
        "hidden_values_analysis": [
            {
                "key": hv.get("key", ""),
                "weight": hv.get("weight", 0),
            }
            for hv in top_hidden_values
        ],
        "love_style": type_info.get("love_style", ""),
        "match_suggestions": [
            type_info.get("match_suggestion", ""),
        ],
        "caution_traits": [
            type_info.get("caution", ""),
        ],
    }

    # 4. 更新偏好表（补充解读）
    existing_traits = _parse_json(persona.get("self_personality_traits_json", {}))
    existing_traits["values_auction"]["ai_interpretation"] = interpretation_data

    apply_persona_patch(
        source=normalized_source,
        user_key=user_key,
        source_type="explicit",
        normalized_patch=normalize_patch({
            "self_personality_traits_json": _json(existing_traits),
        }),
        persona_table=persona_table,
        observation_table=observation_table,
        apply_scope="persona_only",
        sync_profile=False,
        source_channel="values_auction",
    )
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=user_key,
                field_name=VALUES_AUCTION_INTERPRETATION_FIELD,
                field_value=interpretation_data,
                conversation_ref=assessment_id,
                evidence_text="values auction interpretation generated",
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)

    # 5. 返回解读卡片
    return {
        "card_type": "values_auction_interpretation",
        "assessment_id": assessment_id,
        "interpretation_data": interpretation_data,
    }


# ============================================================
# 双人拍卖服务
# ============================================================

def start_values_auction_together(
    *,
    user_key: str,
    partner_key: str,
    source: str | None = None,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """
    开始双人价值观拍卖（两人同时进入）

    Returns:
        拍品列表卡片 + 复用选项（如果用户做过）
    """
    session_id = _generate_session_id()
    normalized_source, _ = _resolve_source(source)

    # 创建双人session
    session_data = {
        "session_id": session_id,
        "user_a_key": user_key,
        "user_b_key": partner_key,
        "user_a_status": "pending",
        "user_b_status": "pending",
        "user_a_result": None,
        "user_b_result": None,
        "created_at": _now(),
        "both_done_at": None,
    }

    # 写入双方观察表
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            _persist_dual_session(
                cursor,
                observation_table=observation_table,
                session=session_data,
                conversation_ref=session_id,
                evidence_text="dual values auction started",
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)

    # 查用户是否做过
    last_result = get_last_result(user_key=user_key, source=source)
    user_has_done = last_result is not None

    # 按维度分组拍品
    lots_by_dimension: dict[str, list[dict[str, Any]]] = {}
    for lot in VALUES_AUCTION_LOTS:
        dimension = lot.get("dimension", "other")
        if dimension not in lots_by_dimension:
            lots_by_dimension[dimension] = []
        lots_by_dimension[dimension].append({
            "lot_id": lot.get("lot_id", ""),
            "title": lot.get("title", ""),
            "dimension": dimension,
        })

    # 返回拍品列表卡片 + 内部状态
    return {
        "card_type": "values_auction_lots",
        "assessment_id": _generate_assessment_id(),
        "session_id": session_id,
        "lots_data": {
            "lots": VALUES_AUCTION_LOTS,
            "lots_by_dimension": lots_by_dimension,
            "dimensions": AUCTION_DIMENSIONS,
            "total_chips": TOTAL_CHIPS,
            "min_bid": MIN_BID,
            "max_bid": MAX_BID,
        },
        "internal_state": {
            "user_has_done": user_has_done,
            "last_result": {
                "value_type": last_result.get("value_type", ""),
                "top3": last_result.get("top3", []),
            } if last_result else None,
            "partner_key": partner_key,
        },
        "is_dual_mode": True,
    }


def get_dual_session(
    *,
    session_id: str,
    user_key: str,
    source: str | None = None,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any] | None:
    """
    获取双人session数据
    """
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT field_value FROM {quote_mysql_ident(observation_table)}
            WHERE user_key = %s AND field_name = %s
              AND conversation_ref = %s
            ORDER BY created_at DESC, id DESC LIMIT 1
            """,
            (user_key, VALUES_AUCTION_DUAL_SESSION_FIELD, session_id),
        )
        row = cursor.fetchone()
        if row:
            return _parse_json(row[0] if not isinstance(row, dict) else row.get("field_value", ""))
        return None
    finally:
        release_persona_connection(normalized_source, conn)


def submit_auction_bids_together(
    *,
    session_id: str,
    user_key: str,
    bids: list[dict[str, Any]],
    source: str | None = None,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """
    提交双人拍卖结果（锁定）

    Returns:
        等待卡片 或 匹配分析卡片
    """
    # 1. 校验并排序
    is_valid, error_msg = validate_bids(bids)
    if not is_valid:
        return {
            "card_type": "error",
            "error_data": {"message": error_msg},
        }

    sorted_bids = sort_and_rank_bids(bids)
    hidden_values = calculate_hidden_values(sorted_bids)
    value_type = classify_value_type_from_hidden(hidden_values)

    user_result = {
        "bids": sorted_bids,
        "hidden_values": hidden_values,
        "value_type": value_type,
        "top3": sorted_bids[:3],
        "submitted_at": _now(),
    }

    # 2. 获取session
    session = get_dual_session(session_id=session_id, user_key=user_key, source=source)
    if not session:
        return {
            "card_type": "error",
            "error_data": {"message": "未找到双人session"},
        }

    # 3. 更新session状态
    normalized_source, _ = _resolve_source(source)

    # 确定用户是A还是B
    if session.get("user_a_key") == user_key:
        session["user_a_status"] = "done"
        session["user_a_result"] = user_result
    elif session.get("user_b_key") == user_key:
        session["user_b_status"] = "done"
        session["user_b_result"] = user_result
    else:
        return {
            "card_type": "error",
            "error_data": {"message": "用户不在session中"},
        }

    # 4. 检查对方是否完成
    partner_done = (
        session.get("user_a_status") == "done" and
        session.get("user_b_status") == "done"
    )

    # 5. 写入更新后的session
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            _persist_dual_session(
                cursor,
                observation_table=observation_table,
                session=session,
                conversation_ref=session_id,
                evidence_text="dual values auction updated",
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)

    # 同时写入用户个人结果到偏好表
    submit_auction_bids(
        assessment_id=f"{session_id}_{user_key}",
        user_key=user_key,
        bids=bids,
        source=source,
    )

    # 6. 返回结果
    if partner_done:
        # 双方都完成，生成匹配分析
        session["both_done_at"] = _now()
        return generate_match_analysis(
            session_id=session_id,
            session=session,
            source=source,
        )
    else:
        # 等待对方
        return {
            "card_type": "values_auction_waiting",
            "session_id": session_id,
            "waiting_data": {
                "message": "等待对方完成...",
                "your_result": {
                    "value_type": value_type,
                    "top3": [
                        {
                            "title": b.get("title", ""),
                            "chips": b.get("chips", 0),
                        }
                        for b in sorted_bids[:3]
                    ],
                },
                "partner_status": "答题中",
            },
        }


def check_dual_auction_status(
    *,
    session_id: str,
    user_key: str,
    source: str | None = None,
) -> dict[str, Any]:
    """
    检查双人拍卖状态（轮询）

    Returns:
        matching分析 或 等待状态
    """
    session = get_dual_session(session_id=session_id, user_key=user_key, source=source)

    if not session:
        return {
            "status": "error",
            "message": "未找到session",
        }

    partner_done = (
        session.get("user_a_status") == "done" and
        session.get("user_b_status") == "done"
    )

    if partner_done:
        return {
            "status": "both_done",
            "card_type": "values_match_analysis",
            "match_data": generate_match_analysis(
                session_id=session_id,
                session=session,
                source=source,
            ).get("match_data", {}),
        }
    else:
        return {
            "status": "waiting",
            "partner_status": "答题中",
        }


def reuse_last_result_together(
    *,
    session_id: str,
    user_key: str,
    source: str | None = None,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """
    复用上次结果（双人模式）

    Returns:
        等待卡片 或 匹配分析卡片
    """
    # 1. 获取上次结果
    last_result = get_last_result(user_key=user_key, source=source)

    if not last_result:
        return {
            "card_type": "error",
            "error_data": {"message": "没有上次结果"},
        }

    # 2. 获取session
    session = get_dual_session(session_id=session_id, user_key=user_key, source=source)

    if not session:
        return {
            "card_type": "error",
            "error_data": {"message": "未找到双人session"},
        }

    # 3. 构建用户结果
    sorted_bids = last_result.get("bids", [])
    hidden_values = last_result.get("hidden_values", {})
    value_type = last_result.get("value_type", "")

    user_result = {
        "bids": sorted_bids,
        "hidden_values": hidden_values,
        "value_type": value_type,
        "top3": sorted_bids[:3],
        "submitted_at": _now(),
        "is_reused": True,
    }

    # 4. 更新session
    normalized_source, _ = _resolve_source(source)

    if session.get("user_a_key") == user_key:
        session["user_a_status"] = "done"
        session["user_a_result"] = user_result
    elif session.get("user_b_key") == user_key:
        session["user_b_status"] = "done"
        session["user_b_result"] = user_result

    # 5. 检查对方
    partner_done = (
        session.get("user_a_status") == "done" and
        session.get("user_b_status") == "done"
    )

    # 6. 写入session
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            _persist_dual_session(
                cursor,
                observation_table=observation_table,
                session=session,
                conversation_ref=session_id,
                evidence_text="dual values auction reused",
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)

    # 7. 返回结果
    if partner_done:
        session["both_done_at"] = _now()
        return generate_match_analysis(
            session_id=session_id,
            session=session,
            source=source,
        )
    else:
        return {
            "card_type": "values_auction_waiting",
            "session_id": session_id,
            "waiting_data": {
                "message": "已复用上次结果，等待对方完成...",
                "your_result": {
                    "value_type": value_type,
                    "top3": [
                        {
                            "title": b.get("title", ""),
                            "chips": b.get("chips", 0),
                        }
                        for b in sorted_bids[:3]
                    ],
                },
                "partner_status": "答题中",
            },
        }


def generate_match_analysis(
    *,
    session_id: str,
    session: dict[str, Any],
    source: str | None = None,
) -> dict[str, Any]:
    """
    生成双人三观匹配分析

    Returns:
        匹配分析卡片（展示共鸣点、错位点、冲突风险）
    """
    user_a_result = session.get("user_a_result", {})
    user_b_result = session.get("user_b_result", {})

    user_a_key = session.get("user_a_key", "")
    user_b_key = session.get("user_b_key", "")

    # 1. 提取双方数据
    a_bids = user_a_result.get("bids", [])
    b_bids = user_b_result.get("bids", [])

    a_hidden_values = user_a_result.get("hidden_values", {})
    b_hidden_values = user_b_result.get("hidden_values", {})

    a_value_type = user_a_result.get("value_type", "")
    b_value_type = user_b_result.get("value_type", "")

    a_top3 = user_a_result.get("top3", [])
    b_top3 = user_b_result.get("top3", [])

    # 2. 计算共鸣拍品（双方都高投的拍品）
    a_top_lots = {b.get("lot_id", "") for b in a_top3 if b.get("chips", 0) >= 2}
    b_top_lots = {b.get("lot_id", "") for b in b_top3 if b.get("chips", 0) >= 2}
    common_lots = list(a_top_lots & b_top_lots)

    top3_common = [LOT_ID_TO_TITLE.get(lot_id, lot_id) for lot_id in common_lots]

    # 3. 计算错位拍品（一方高投、一方低投）
    a_chips_map = {b.get("lot_id", ""): b.get("chips", 0) for b in a_bids}
    b_chips_map = {b.get("lot_id", ""): b.get("chips", 0) for b in b_bids}

    misalignments = []
    conflicts = []

    # 检查价值观错位和冲突
    # 如果A最看重的拍品，B出价很低
    if a_top3:
        a_top_lot = a_top3[0].get("lot_id", "")
        a_top_chips = a_top3[0].get("chips", 0)
        b_chips_for_a_top = b_chips_map.get(a_top_lot, 0)

        if a_top_chips >= 4 and b_chips_for_a_top <= 1:
            conflicts.append({
                "type": "value_gap",
                "lot_id": a_top_lot,
                "description": f"你最看重'{LOT_ID_TO_TITLE.get(a_top_lot, a_top_lot)}'（{a_top_chips}筹码），TA只投了{b_chips_for_a_top}筹码",
                "suggestion": f"TA可能不够看重{LOT_ID_TO_TITLE.get(a_top_lot, a_top_lot)}，你可能会感到不安",
            })
        elif a_top_chips >= 3 and b_chips_for_a_top <= 1:
            misalignments.append({
                "type": "value_misalign",
                "lot_id": a_top_lot,
                "description": f"你看重'{LOT_ID_TO_TITLE.get(a_top_lot, a_top_lot)}'，TA不怎么在意",
            })

    # 反向检查
    if b_top3:
        b_top_lot = b_top3[0].get("lot_id", "")
        b_top_chips = b_top3[0].get("chips", 0)
        a_chips_for_b_top = a_chips_map.get(b_top_lot, 0)

        if b_top_chips >= 4 and a_chips_for_b_top <= 1:
            conflicts.append({
                "type": "value_gap",
                "lot_id": b_top_lot,
                "description": f"TA最看重'{LOT_ID_TO_TITLE.get(b_top_lot, b_top_lot)}'（{b_top_chips}筹码），你只投了{a_chips_for_b_top}筹码",
                "suggestion": f"你可能不够看重{LOT_ID_TO_TITLE.get(b_top_lot, b_top_lot)}，TA可能会不满",
            })
        elif b_top_chips >= 3 and a_chips_for_b_top <= 1:
            misalignments.append({
                "type": "value_misalign",
                "lot_id": b_top_lot,
                "description": f"TA看重'{LOT_ID_TO_TITLE.get(b_top_lot, b_top_lot)}'，你不怎么在意",
            })

    # 4. 计算隐藏价值共鸣度
    common_hidden_values = []
    for key in a_hidden_values:
        if key in b_hidden_values:
            a_weight = a_hidden_values.get(key, 0)
            b_weight = b_hidden_values.get(key, 0)
            # 如果双方都看重某个隐藏价值
            if a_weight >= 0.15 and b_weight >= 0.15:
                common_hidden_values.append({
                    "key": key,
                    "a_weight": a_weight,
                    "b_weight": b_weight,
                })

    # 5. 判断匹配类型
    if len(common_lots) >= 2 and len(conflicts) == 0:
        match_type = "高度契合"
    elif len(common_lots) >= 1 and len(conflicts) <= 1:
        match_type = "中等契合"
    elif len(conflicts) >= 2:
        match_type = "需要磨合"
    else:
        match_type = "一般契合"

    # 6. 构建匹配数据
    match_data = {
        "session_id": session_id,
        "user1": {
            "user_key": user_a_key,
            "value_type": a_value_type,
            "hidden_values": a_hidden_values,
            "top3": [
                {
                    "lot_id": b.get("lot_id", ""),
                    "title": b.get("title", ""),
                    "chips": b.get("chips", 0),
                }
                for b in a_top3
            ],
        },
        "user2": {
            "user_key": user_b_key,
            "value_type": b_value_type,
            "hidden_values": b_hidden_values,
            "top3": [
                {
                    "lot_id": b.get("lot_id", ""),
                    "title": b.get("title", ""),
                    "chips": b.get("chips", 0),
                }
                for b in b_top3
            ],
        },
        "match_type": match_type,
        "common_lots": top3_common,
        "common_hidden_values": common_hidden_values,
        "misalignments": misalignments,
        "conflicts": conflicts,
    }

    # 7. 返回匹配分析卡片
    return {
        "card_type": "values_match_analysis",
        "session_id": session_id,
        "match_data": match_data,
    }
