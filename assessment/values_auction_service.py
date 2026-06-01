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

from assessment.values_traits import (
    ASSESSMENT_TYPE_VALUES_AUCTION,
    VALUES_AUCTION_DUAL_SESSION_FIELD,
    VALUES_AUCTION_INTERPRETATION_FIELD,
    VALUES_AUCTION_RESULT_FIELD,
    VALUES_AUCTION_SESSION_FIELD,
    VALUES_AUCTION_TRAITS,
    TRAIT_ID_TO_NAME,
    TOTAL_CHIPS,
    MIN_BID,
    MAX_BID,
    TRAIT_COUNT,
    classify_value_type,
    get_value_type_info,
    get_trait_interpretation,
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
            "description": "你有10个筹码，竞拍你最看重的特质\n不可能全都拿到，必须取舍",
            "total_chips": TOTAL_CHIPS,
            "trait_count": TRAIT_COUNT,
            "duration": "约2分钟",
            "reward": "解锁三观匹配分析",
        },
    }


def get_traits_list(
    *,
    assessment_id: str,
) -> dict[str, Any]:
    """
    获取特质列表卡片

    Returns:
        特质列表卡片数据
    """
    return {
        "card_type": "values_auction_traits",
        "assessment_id": assessment_id,
        "traits_data": {
            "traits": VALUES_AUCTION_TRAITS,
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

    # 校验每个特质的筹码范围
    for bid in bids:
        chips = bid.get("chips", 0)
        if chips < MIN_BID or chips > MAX_BID:
            trait_id = bid.get("trait_id", "unknown")
            return False, f"特质 {trait_id} 的筹码数 {chips} 不在有效范围"

    # 校验特质ID是否有效
    valid_trait_ids = {t["trait_id"] for t in VALUES_AUCTION_TRAITS}
    for bid in bids:
        trait_id = bid.get("trait_id", "")
        if trait_id not in valid_trait_ids:
            return False, f"无效的特质ID: {trait_id}"

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
        bid["trait_name"] = TRAIT_ID_TO_NAME.get(bid.get("trait_id", ""), bid.get("trait_id", ""))

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

    # 3. 分类价值观类型
    value_type = classify_value_type(sorted_bids)

    # 4. 提取top3和放弃的特质
    top3 = sorted_bids[:3]
    for trait in top3:
        trait["interpretation"] = get_trait_interpretation(
            trait.get("trait_id", ""),
            trait.get("chips", 0)
        )

    abandoned = [b.get("trait_name", b.get("trait_id", "")) for b in sorted_bids if b.get("chips", 0) == 0]

    # 5. 构建结果数据
    result_data = {
        "assessment_id": assessment_id,
        "assessed_at": _now(),
        "config": {
            "total_chips": TOTAL_CHIPS,
            "trait_count": TRAIT_COUNT,
        },
        "bids": sorted_bids,
        "value_type": value_type,
        "value_labels": [b.get("trait_name", "") for b in top3 if b.get("chips", 0) > 0],
        "top3": top3,
        "abandoned": abandoned,
        "confidence": 0.85,
    }

    # 6. 写入偏好表
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

    # 7. 返回结果卡片
    return {
        "card_type": "values_auction_result",
        "assessment_id": assessment_id,
        "result_data": {
            "bids": sorted_bids,
            "value_type": value_type,
            "value_labels": result_data["value_labels"],
            "top3": top3,
            "abandoned": abandoned,
            "reward": "解锁三观匹配分析",
        },
    }


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

    # 2. 获取价值观类型信息
    value_type = values_auction.get("value_type", "综合型")
    type_info = get_value_type_info(value_type)

    top3 = values_auction.get("top3", [])

    # 3. 构建解读数据（这里用预定义模板，后续可接入AI）
    interpretation_data = {
        "summary": type_info.get("description", ""),
        "love_style": type_info.get("love_style", ""),
        "match_suggestions": [
            type_info.get("match_suggestion", ""),
        ],
        "caution_traits": [
            type_info.get("caution", ""),
        ],
        "top3_analysis": [
            {
                "trait_name": t.get("trait_name", ""),
                "chips": t.get("chips", 0),
                "interpretation": t.get("interpretation", ""),
            }
            for t in top3
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
        特质列表卡片 + 复用选项（如果用户做过）
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
            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=user_key,
                field_name=VALUES_AUCTION_DUAL_SESSION_FIELD,
                field_value=session_data,
                conversation_ref=session_id,
                evidence_text="dual values auction started",
            )
            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=partner_key,
                field_name=VALUES_AUCTION_DUAL_SESSION_FIELD,
                field_value=session_data,
                conversation_ref=session_id,
                evidence_text="dual values auction started",
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)

    # 查用户是否做过
    last_result = get_last_result(user_key=user_key, source=source)
    user_has_done = last_result is not None

    # 返回特质列表卡片 + 内部状态
    return {
        "card_type": "values_auction_traits",
        "assessment_id": _generate_assessment_id(),
        "session_id": session_id,
        "traits_data": {
            "traits": VALUES_AUCTION_TRAITS,
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
    value_type = classify_value_type(sorted_bids)

    user_result = {
        "bids": sorted_bids,
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
            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=user_key,
                field_name=VALUES_AUCTION_DUAL_SESSION_FIELD,
                field_value=session,
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
                            "trait_name": b.get("trait_name", ""),
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
    value_type = last_result.get("value_type", "")

    user_result = {
        "bids": sorted_bids,
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
            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=user_key,
                field_name=VALUES_AUCTION_DUAL_SESSION_FIELD,
                field_value=session,
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
                            "trait_name": b.get("trait_name", ""),
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
        匹配分析卡片
    """
    user_a_result = session.get("user_a_result", {})
    user_b_result = session.get("user_b_result", {})

    user_a_key = session.get("user_a_key", "")
    user_b_key = session.get("user_b_key", "")

    # 1. 提取双方数据
    a_bids = user_a_result.get("bids", [])
    b_bids = user_b_result.get("bids", [])

    a_value_type = user_a_result.get("value_type", "")
    b_value_type = user_b_result.get("value_type", "")

    a_top3 = user_a_result.get("top3", [])
    b_top3 = user_b_result.get("top3", [])

    # 2. 计算共鸣点（双方都看重的特质）
    a_top_traits = {b.get("trait_id", "") for b in a_top3 if b.get("chips", 0) >= 2}
    b_top_traits = {b.get("trait_id", "") for b in b_top3 if b.get("chips", 0) >= 2}
    common_traits = list(a_top_traits & b_top_traits)

    top3_common = [TRAIT_ID_TO_NAME.get(t, t) for t in common_traits]

    # 3. 计算差异点
    a_chips_map = {b.get("trait_id", ""): b.get("chips", 0) for b in a_bids}
    b_chips_map = {b.get("trait_id", ""): b.get("chips", 0) for b in b_bids}

    conflicts = []

    # 检查价值观冲突
    # 如果A最看重的特质，B出价很低
    if a_top3:
        a_top_trait = a_top3[0].get("trait_id", "")
        a_top_chips = a_top3[0].get("chips", 0)
        b_chips_for_a_top = b_chips_map.get(a_top_trait, 0)

        if a_top_chips >= 4 and b_chips_for_a_top <= 1:
            conflicts.append({
                "type": "value_gap",
                "description": f"A最看重'{TRAIT_ID_TO_NAME.get(a_top_trait, a_top_trait)}'（{a_top_chips}筹码），B只投了{b_chips_for_a_top}筹码",
                "suggestion": f"B可能不够看重{TRAIT_ID_TO_NAME.get(a_top_trait, a_top_trait)}，A可能会感到不安",
            })

    # 反向检查
    if b_top3:
        b_top_trait = b_top3[0].get("trait_id", "")
        b_top_chips = b_top3[0].get("chips", 0)
        a_chips_for_b_top = a_chips_map.get(b_top_trait, 0)

        if b_top_chips >= 4 and a_chips_for_b_top <= 1:
            conflicts.append({
                "type": "value_gap",
                "description": f"B最看重'{TRAIT_ID_TO_NAME.get(b_top_trait, b_top_trait)}'（{b_top_chips}筹码），A只投了{a_chips_for_b_top}筹码",
                "suggestion": f"A可能不够看重{TRAIT_ID_TO_NAME.get(b_top_trait, b_top_trait)}，B可能会不满",
            })

    # 4. 判断匹配类型
    if len(common_traits) >= 2 and len(conflicts) == 0:
        match_type = "高度契合"
    elif len(common_traits) >= 1 and len(conflicts) <= 1:
        match_type = "中等契合"
    elif len(conflicts) >= 2:
        match_type = "需要磨合"
    else:
        match_type = "一般契合"

    # 5. 生成AI解读（预定义模板，后续可接入AI）
    ai_interpretation = f"""
你们的三观整体上是{match_type}。

【共鸣点】
{f"你们都看重：{', '.join(top3_common)}" if top3_common else "你们的价值观差异较大，但也有交集"}

【差异点】
{chr(10).join([f"- {c.get('description', '')}" for c in conflicts]) if conflicts else "你们的价值观差异不大"}

【相处建议】
- 多沟通彼此的价值观，理解对方的出发点
- 在差异中寻找平衡，不要试图改变对方
"""

    # 6. 构建匹配数据
    match_data = {
        "session_id": session_id,
        "user1": {
            "user_key": user_a_key,
            "value_type": a_value_type,
            "top3": [
                {
                    "trait_id": b.get("trait_id", ""),
                    "trait_name": b.get("trait_name", ""),
                    "chips": b.get("chips", 0),
                }
                for b in a_top3
            ],
        },
        "user2": {
            "user_key": user_b_key,
            "value_type": b_value_type,
            "top3": [
                {
                    "trait_id": b.get("trait_id", ""),
                    "trait_name": b.get("trait_name", ""),
                    "chips": b.get("chips", 0),
                }
                for b in b_top3
            ],
        },
        "match_type": match_type,
        "top3_common": top3_common,
        "conflicts": conflicts,
        "ai_interpretation": ai_interpretation,
    }

    # 7. 返回匹配分析卡片
    return {
        "card_type": "values_match_analysis",
        "session_id": session_id,
        "match_data": match_data,
    }
