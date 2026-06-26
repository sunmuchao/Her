"""依恋风格测评服务逻辑

参考 MBTI service.py 的完整实现模式：
- 断点续传机制
- 每3题给维度反馈
- 结果写入 user_personas.self_personality_traits_json
- 小雅消息单独存储和展示
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from assessment.attachment_questions import (
    ATTACHMENT_QUESTIONS,
    calculate_all_scores,
    get_dimension_feedback,
    get_question,
    get_type_info,
    get_extreme_tags,
    get_primary_attachment_type,
    _interpretation_from_result,
    xiaoya_message_from_result,
    calculate_love_match,
)
from assessment.result_store import merge_personality_summary, store_assessment_result
from persona_memory_sync.persona_memory_lib import (
    fetch_persona,
    mysql_connect,
    parse_mysql_source,
    quote_mysql_ident,
    release_persona_connection,
)


TOTAL_QUESTIONS = len(ATTACHMENT_QUESTIONS)
ASSESSMENT_TYPE_ATTACHMENT = "attachment_style"
ASSESSMENT_SESSION_FIELD = "assessment.session"
ASSESSMENT_RESULT_FIELD = "assessment.result"
ASSESSMENT_INTERPRETATION_FIELD = "assessment.interpretation"
ASSESSMENT_XIAOYA_MESSAGE_FIELD = "assessment.xiaoya_message"


ATTACHMENT_DIMENSION_LABELS = {
    "anxiety": "关系不安度",
    "avoidance": "亲密后撤度",
}


ATTACHMENT_DIMENSION_TRAITS = {
    "anxiety": {"high": "回应敏感", "medium": "容易牵动", "low": "稳定感较强"},
    "avoidance": {"high": "边界警觉", "medium": "慢热靠近", "low": "靠近自如"},
}


@dataclass(frozen=True)
class AttachmentAssessmentSession:
    assessment_id: str
    assessment_type: str
    user_key: str
    status: str
    created_at: str


def _resolve_source(source: str | None) -> tuple[str, str]:
    parsed = parse_mysql_source(source)
    normalized_source = str(parsed["source"])
    table = str(parsed["table"])
    return normalized_source, table


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _parse_json(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        data = json.loads(str(value))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _session_payload(
    assessment_id: str,
    assessment_type: str,
    user_key: str,
    *,
    status: str = "in_progress",
) -> dict[str, Any]:
    return {
        "assessment_id": assessment_id,
        "assessment_type": assessment_type,
        "user_key": user_key,
        "status": status,
        "total_questions": TOTAL_QUESTIONS,
        "created_at": _now(),
    }


def _save_observation(
    cursor: Any,
    *,
    observation_table: str,
    user_key: str,
    field_name: str,
    field_value: Any,
    assessment_id: str,
    source_type: str = "explicit",
    evidence_text: str = "",
) -> None:
    cursor.execute(
        f"DELETE FROM {quote_mysql_ident(observation_table)} WHERE user_key = %s AND conversation_ref = %s AND field_name = %s",
        (user_key, assessment_id, field_name),
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
            assessment_id,
            "assessment",
            _now(),
        ),
    )


def _load_session_and_answers(
    cursor: Any,
    *,
    observation_table: str,
    assessment_id: str,
) -> tuple[AttachmentAssessmentSession | None, dict[int, dict[str, Any]], dict[str, Any]]:
    cursor.execute(
        f"""
        SELECT field_name, field_value, created_at, user_key
        FROM {quote_mysql_ident(observation_table)}
        WHERE conversation_ref = %s
        ORDER BY created_at ASC, id ASC
        """,
        (assessment_id,),
    )
    rows = cursor.fetchall() or []
    session: AttachmentAssessmentSession | None = None
    answers: dict[int, dict[str, Any]] = {}
    result: dict[str, Any] = {}
    for row in rows:
        field_name = str((row.get("field_name") if isinstance(row, dict) else row[0]) or "")
        field_value = row.get("field_value") if isinstance(row, dict) else row[1]
        user_key = str(row.get("user_key") if isinstance(row, dict) else row[3] or "")
        data = _parse_json(field_value)
        if field_name == ASSESSMENT_SESSION_FIELD:
            created_at = row.get("created_at") if isinstance(row, dict) else row[2]
            session = AttachmentAssessmentSession(
                assessment_id=str(data.get("assessment_id") or assessment_id),
                assessment_type=str(data.get("assessment_type") or ASSESSMENT_TYPE_ATTACHMENT),
                user_key=str(data.get("user_key") or user_key),
                status=str(data.get("status") or "in_progress"),
                created_at=str(data.get("created_at") or created_at or ""),
            )
        elif field_name.startswith("assessment.answer."):
            try:
                question_index = int(field_name.rsplit(".", 1)[-1])
            except ValueError:
                continue
            answers[question_index] = data
        elif field_name == ASSESSMENT_RESULT_FIELD:
            result = _result_with_interpretation(data)
    return session, answers, result


def _question_payload(question_index: int, assessment_id: str) -> dict[str, Any]:
    question = get_question(question_index)
    if question is None:
        raise ValueError("question not found")
    return {
        "current_question": question_index + 1,
        "total_questions": TOTAL_QUESTIONS,
        "question_text": question["text"],
        "options": question["options"],
        "progress": int(round(((question_index + 1) / TOTAL_QUESTIONS) * 100)),
        "assessment_id": assessment_id,
    }


def _feedback_payload(question_index: int, scores: dict[str, float]) -> dict[str, Any]:
    """反馈卡片：答完 6 题给一次阶段反馈"""
    dimension = None
    if question_index == 5:
        dimension = "anxiety"
    elif question_index == 11:
        dimension = "avoidance"

    if dimension is None:
        return {}

    score = scores.get(dimension, 0.0)
    return {
        "dimension": dimension,
        "dimension_name": ATTACHMENT_DIMENSION_LABELS[dimension],
        "score": score,
        "feedback_text": get_dimension_feedback(dimension, score),
    }


def _dimension_rows(scores: dict[str, float]) -> list[dict[str, Any]]:
    """生成维度得分列表"""
    rows = []
    for dimension in ("anxiety", "avoidance"):
        score = float(scores.get(dimension, 0.0))
        rows.append(
            {
                "key": dimension,
                "name": ATTACHMENT_DIMENSION_LABELS[dimension],
                "score": score,
                "level": "high" if score >= 70 else "medium" if score >= 40 else "low",
                "trait": ATTACHMENT_DIMENSION_TRAITS[dimension]["high" if score >= 70 else "medium" if score >= 40 else "low"],
            }
        )
    return rows


def _result_with_interpretation(result: dict[str, Any]) -> dict[str, Any]:
    """结果卡片带解读"""
    if not result:
        return {}
    if result.get("interpretation_data"):
        return result
    merged = dict(result)
    merged["interpretation_data"] = _interpretation_from_result(merged)
    return merged


def _quadrant_payload(scores: dict[str, float], type_code: str) -> dict[str, Any]:
    return {
        "x_key": "avoidance",
        "x_name": ATTACHMENT_DIMENSION_LABELS["avoidance"],
        "x_score": float(scores.get("avoidance", 0.0)),
        "y_key": "anxiety",
        "y_name": ATTACHMENT_DIMENSION_LABELS["anxiety"],
        "y_score": float(scores.get("anxiety", 0.0)),
        "type_code": type_code,
        "type_name": get_type_info(type_code).get("nickname", type_code),
        "quadrants": {
            "top_left": {"type_code": "anxious", "label": get_type_info("anxious").get("nickname", "高敏确认型")},
            "top_right": {"type_code": "fearful", "label": get_type_info("fearful").get("nickname", "拉扯矛盾型")},
            "bottom_left": {"type_code": "secure", "label": get_type_info("secure").get("nickname", "稳定靠近型")},
            "bottom_right": {"type_code": "avoidant", "label": get_type_info("avoidant").get("nickname", "边界后撤型")},
        },
    }


def start_attachment_assessment(
    *,
    source: str | None,
    user_key: str,
    assessment_type: str = ASSESSMENT_TYPE_ATTACHMENT,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """创建新的依恋风格测评会话"""
    if assessment_type != ASSESSMENT_TYPE_ATTACHMENT:
        raise ValueError("unsupported assessment_type")
    normalized_source, _ = _resolve_source(source)
    assessment_id = f"attachment_{uuid.uuid4().hex[:12]}"
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=user_key,
                field_name=ASSESSMENT_SESSION_FIELD,
                field_value=_session_payload(assessment_id, assessment_type, user_key),
                assessment_id=assessment_id,
                evidence_text="attachment assessment started",
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)
    return {
        "card_type": "assessment_intro",
        "assessment_type": assessment_type,
        "assessment_id": assessment_id,
        "intro_data": {
            "title": "相处模式测验",
            "description": "测测你在关系里更容易慌，还是更容易退",
            "duration": "3分钟 · 12题",
            "reward": "适合的相处模式",
        },
    }


def get_or_create_attachment_assessment(
    *,
    source: str | None,
    user_key: str,
    assessment_type: str = ASSESSMENT_TYPE_ATTACHMENT,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """获取未完成的依恋风格测评（断点续传），或者创建新测评"""
    if assessment_type != ASSESSMENT_TYPE_ATTACHMENT:
        raise ValueError("unsupported assessment_type")

    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)

    try:
        with conn.cursor() as cursor:
            # 查找用户最近的未完成依恋风格测评
            cursor.execute(
                f"""
                SELECT conversation_ref, field_value, created_at
                FROM {quote_mysql_ident(observation_table)}
                WHERE user_key = %s
                  AND field_name = %s
                  AND source_channel = 'assessment'
                  AND JSON_EXTRACT(field_value, '$.assessment_type') = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_key, ASSESSMENT_SESSION_FIELD, f'"{ASSESSMENT_TYPE_ATTACHMENT}"'),
            )
            recent_session = cursor.fetchone()

            if recent_session:
                session_data = _parse_json(
                    recent_session.get("field_value") if isinstance(recent_session, dict) else recent_session[1]
                )
                assessment_id = str(
                    recent_session.get("conversation_ref") if isinstance(recent_session, dict) else recent_session[0]
                )

                if session_data.get("status") == "in_progress":
                    session, answers, _result = _load_session_and_answers(
                        cursor,
                        observation_table=observation_table,
                        assessment_id=assessment_id,
                    )

                    if session and len(answers) < TOTAL_QUESTIONS:
                        answered_count = len(answers)
                        return {
                            "card_type": "assessment_intro",
                            "assessment_id": assessment_id,
                            "intro_data": {
                                "title": "继续上次的测评",
                                "description": f"已答 {answered_count} 题，还有 {TOTAL_QUESTIONS - answered_count} 题",
                                "duration": "继续测评",
                                "reward": "上次退出时已保存进度，点击继续",
                            },
                            "resumed": True,
                            "answered_count": answered_count,
                        }

        release_persona_connection(normalized_source, conn)
        conn = None

        return start_attachment_assessment(
            source=source,
            user_key=user_key,
            assessment_type=assessment_type,
            persona_table=persona_table,
            observation_table=observation_table,
        )

    finally:
        if conn:
            release_persona_connection(normalized_source, conn)


def begin_attachment_assessment(
    *,
    source: str | None,
    assessment_id: str,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """开始依恋风格测评（返回第一题）"""
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            session, answers, _result = _load_session_and_answers(
                cursor,
                observation_table=observation_table,
                assessment_id=assessment_id,
            )
            if session is None:
                raise ValueError("assessment not found")
            return {
                "card_type": "assessment_question",
                "assessment_id": assessment_id,
                "question_data": _question_payload(len(answers), assessment_id),
            }
    finally:
        release_persona_connection(normalized_source, conn)


def answer_attachment_assessment(
    *,
    source: str | None,
    assessment_id: str,
    question_index: int,
    answer: str,
    user_key: str,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """提交依恋风格测评答案"""
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            session, answers, _result = _load_session_and_answers(
                cursor,
                observation_table=observation_table,
                assessment_id=assessment_id,
            )
            if session is None:
                raise ValueError("assessment not found")
            if session.user_key and str(session.user_key) != str(user_key):
                raise ValueError("assessment does not belong to user")
            if not (0 <= question_index < TOTAL_QUESTIONS):
                raise ValueError("question_index out of range")
            if question_index not in answers and question_index != len(answers):
                raise ValueError("question sequence mismatch")

            question = get_question(question_index)
            if question is None:
                raise ValueError("question not found")
            options = {str(item["label"]): item for item in question["options"]}
            selected = options.get(str(answer).strip().upper())
            if selected is None:
                raise ValueError("invalid answer")

            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=user_key,
                field_name=f"assessment.answer.{question_index}",
                field_value={
                    "question_index": question_index,
                    "answer": str(answer).strip().upper(),
                    "score": selected["score"],
                    "dimension": question["dimension"],
                    "reverse": bool(question.get("reverse")),
                },
                assessment_id=assessment_id,
                evidence_text=f"answer for question {question_index}",
            )
            conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)

    # Reload after commit
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            session, answers, _result = _load_session_and_answers(
                cursor,
                observation_table=observation_table,
                assessment_id=assessment_id,
            )
            ordered_scores = [3] * TOTAL_QUESTIONS
            for index, payload in answers.items():
                if 0 <= index < TOTAL_QUESTIONS:
                    try:
                        ordered_scores[index] = int(payload.get("score", 3))
                    except (TypeError, ValueError):
                        ordered_scores[index] = 3
            scores = calculate_all_scores(ordered_scores)

            answered_count = len(answers)
            if answered_count >= TOTAL_QUESTIONS:
                type_code = get_primary_attachment_type(scores)
                type_info = get_type_info(type_code)
                interpretation = _interpretation_from_result(
                    {
                        "type_code": type_code,
                        "scores": scores,
                    }
                )
                result_data = {
                    "type_code": type_code,
                    "scores": scores,
                    "dimension_rows": _dimension_rows(scores),
                    "quadrant": _quadrant_payload(scores, type_code),
                    "labels": [type_info["nickname"]] + type_info["tags"][:3],
                    "interpretation_data": interpretation,
                    "reward": "适合的相处模式",
                    "assessment_id": assessment_id,
                }
                _save_observation(
                    cursor,
                    observation_table=observation_table,
                    user_key=user_key,
                    field_name=ASSESSMENT_RESULT_FIELD,
                    field_value=result_data,
                    assessment_id=assessment_id,
                    evidence_text="attachment assessment completed",
                )
                _save_observation(
                    cursor,
                    observation_table=observation_table,
                    user_key=user_key,
                    field_name=ASSESSMENT_INTERPRETATION_FIELD,
                    field_value=interpretation,
                    assessment_id=assessment_id,
                    evidence_text="attachment assessment interpretation",
                )
                # 保存小雅解读消息
                xiaoya_message = xiaoya_message_from_result(
                    {
                        "type_code": type_code,
                        "scores": scores,
                    }
                )
                _save_observation(
                    cursor,
                    observation_table=observation_table,
                    user_key=user_key,
                    field_name=ASSESSMENT_XIAOYA_MESSAGE_FIELD,
                    field_value={"message": xiaoya_message, "read": False},
                    assessment_id=assessment_id,
                    evidence_text="xiaoya interpretation message",
                )
                completed_at = _now()
                traits_payload = {
                    "assessment_id": assessment_id,
                    "type_code": type_code,
                    "anxiety": float(scores.get("anxiety", 0.0)),
                    "avoidance": float(scores.get("avoidance", 0.0)),
                    "completed_at": completed_at,
                }
                store_assessment_result(
                    source=normalized_source,
                    user_key=user_key,
                    assessment_id=assessment_id,
                    assessment_type=ASSESSMENT_TYPE_ATTACHMENT,
                    raw_result=result_data,
                    summary=traits_payload,
                    interpretation=interpretation,
                    completed_at=completed_at,
                    source_channel="assessment",
                )
                merge_personality_summary(
                    source=normalized_source,
                    user_key=user_key,
                    summary_key="attachment",
                    summary_payload=traits_payload,
                    persona_table=persona_table,
                    observation_table=observation_table,
                    evidence_text=f"用户完成依恋风格测评（{assessment_id}）",
                    conversation_ref=assessment_id,
                    source_channel="assessment",
                )
                conn.commit()

                # ✅ 修复：清理画像缓存，确保Agent能看到最新的依恋风格结果
                # 根因：_cached_load_persona_for_discovery使用了lru_cache缓存画像数据
                #       测试完成后，画像写入数据库，但缓存未清理，Agent看到旧数据
                # 解决：画像更新后清理缓存，下次查询时重新从数据库加载
                try:
                    from partner_search.personality_traits_reader import clear_traits_cache
                    clear_traits_cache()
                    _logger.info("【画像缓存清理】user_key=%s assessment_id=%s", user_key, assessment_id)
                except Exception as cache_error:
                    _logger.warning("【画像缓存清理失败】user_key=%s error=%s", user_key, cache_error)

                return {
                    "card_type": "assessment_result",
                    "assessment_type": ASSESSMENT_TYPE_ATTACHMENT,  # 添加 assessment_type 字段，供前端识别测评类型
                    "assessment_id": assessment_id,
                    "result_data": result_data,
                }

            # 每 6 题给一次阶段反馈
            if answered_count in [6, 12]:
                feedback_data = _feedback_payload(answered_count - 1, scores)
                if feedback_data:
                    next_index = answered_count
                    return {
                        "card_type": "assessment_feedback",
                        "assessment_id": assessment_id,
                        "feedback_data": feedback_data,
                        "next_question": _question_payload(next_index, assessment_id),
                    }

            return {
                "card_type": "assessment_question",
                "assessment_id": assessment_id,
                "question_data": _question_payload(answered_count, assessment_id),
            }
    finally:
        release_persona_connection(normalized_source, conn)


def get_attachment_interpretation(
    *,
    source: str | None,
    assessment_id: str,
    user_key: str,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """获取依恋风格测评解读"""
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            session, _answers, result = _load_session_and_answers(
                cursor,
                observation_table=observation_table,
                assessment_id=assessment_id,
            )
            if session is None:
                raise ValueError("assessment not found")
            if session.user_key and str(session.user_key) != str(user_key):
                raise ValueError("assessment does not belong to user")
            if not result:
                raise ValueError("assessment result not ready")
            interpretation = _interpretation_from_result(result)
            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=user_key,
                field_name=ASSESSMENT_INTERPRETATION_FIELD,
                field_value=interpretation,
                assessment_id=assessment_id,
                evidence_text="attachment assessment interpretation",
            )
            conn.commit()
            return {
                "card_type": "assessment_interpretation",
                "assessment_id": assessment_id,
                "interpretation_data": interpretation,
            }
    finally:
        release_persona_connection(normalized_source, conn)


def get_attachment_xiaoya_message(
    *,
    source: str | None,
    user_key: str,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """获取依恋风格小雅解读消息"""
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT field_value, conversation_ref, created_at
                FROM {quote_mysql_ident(observation_table)}
                WHERE user_key = %s
                  AND field_name = %s
                  AND source_channel = 'assessment'
                  AND conversation_ref LIKE 'attachment_%%'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_key, ASSESSMENT_XIAOYA_MESSAGE_FIELD),
            )
            row = cursor.fetchone()
            if not row:
                return {"has_message": False}

            data = _parse_json(row.get("field_value") if isinstance(row, dict) else row[0])
            if not data or data.get("read"):
                return {"has_message": False}

            return {
                "has_message": True,
                "message": data.get("message") or "",
                "assessment_id": str(row.get("conversation_ref") if isinstance(row, dict) else row[1]),
            }
    finally:
        release_persona_connection(normalized_source, conn)


def get_attachment_traits(
    *,
    source: str | None,
    user_key: str,
    persona_table: str = "user_personas",
) -> dict[str, Any]:
    """获取用户的依恋风格特质"""
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            persona = fetch_persona(cursor, persona_table, user_key=user_key)
            if not persona:
                return {"attachment": {}}
            traits = _parse_json(persona.get("self_personality_traits_json"))
            return {
                "attachment": traits.get("attachment") or {},
            }
    finally:
        release_persona_connection(normalized_source, conn)
