"""恋爱五种语言测评服务逻辑

参考依恋风格 attachment_service.py 的完整实现模式：
- 断点续传机制
- 每2题给该语言的反馈
- 结果写入 user_personas.self_personality_traits_json
- 小雅消息单独存储和展示
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from assessment.love_language_questions import (
    LOVE_LANGUAGE_QUESTIONS,
    LOVE_LANGUAGES,
    calculate_all_language_scores,
    get_language_feedback,
    get_question,
    get_language_info,
    get_extreme_language_tags,
    get_primary_love_language,
    get_language_ranking,
    _interpretation_from_result,
    xiaoya_message_from_result,
    calculate_love_language_match,
    LOVE_LANGUAGE_NAMES,
    LOVE_LANGUAGE_LABELS,  # 新增：恋爱语言标签定义
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


TOTAL_QUESTIONS = len(LOVE_LANGUAGE_QUESTIONS)
ASSESSMENT_TYPE_LOVE_LANGUAGE = "love_language"
ASSESSMENT_SESSION_FIELD = "assessment.session"
ASSESSMENT_RESULT_FIELD = "assessment.result"
ASSESSMENT_INTERPRETATION_FIELD = "assessment.interpretation"
ASSESSMENT_XIAOYA_MESSAGE_FIELD = "assessment.xiaoya_message"


@dataclass(frozen=True)
class LoveLanguageAssessmentSession:
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


def _dimension_rows(scores: dict[str, float]) -> list[dict[str, Any]]:
    """生成恋爱语言的维度行数据（用于雷达图显示）"""
    rows = []
    for lang_key, lang_name in LOVE_LANGUAGE_NAMES.items():
        score = float(scores.get(lang_key, 0.0))
        # 恋爱语言的level判定：high>=70, medium>=40, low<40
        level = "high" if score >= 70 else "medium" if score >= 40 else "low"
        # 使用恋爱语言标签定义中的trait
        trait = LOVE_LANGUAGE_LABELS[lang_key]["nickname"]
        rows.append(
            {
                "key": lang_key,
                "name": lang_name,
                "score": score,
                "level": level,
                "trait": trait,
            }
        )
    return rows


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
) -> tuple[LoveLanguageAssessmentSession | None, dict[int, dict[str, Any]], dict[str, Any]]:
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
    session: LoveLanguageAssessmentSession | None = None
    answers: dict[int, dict[str, Any]] = {}
    result: dict[str, Any] = {}
    for row in rows:
        field_name = str((row.get("field_name") if isinstance(row, dict) else row[0]) or "")
        field_value = row.get("field_value") if isinstance(row, dict) else row[1]
        user_key = str(row.get("user_key") if isinstance(row, dict) else row[3] or "")
        data = _parse_json(field_value)
        if field_name == ASSESSMENT_SESSION_FIELD:
            created_at = row.get("created_at") if isinstance(row, dict) else row[2]
            session = LoveLanguageAssessmentSession(
                assessment_id=str(data.get("assessment_id") or assessment_id),
                assessment_type=str(data.get("assessment_type") or ASSESSMENT_TYPE_LOVE_LANGUAGE),
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
    """反馈卡片：每答完2题给该语言的反馈"""
    # 判断当前答完了哪个语言的2题
    language = None
    if question_index == 1:  # 答完第2题（肯定言词）
        language = "words_of_affirmation"
    elif question_index == 3:  # 答完第4题（精心时刻）
        language = "quality_time"
    elif question_index == 5:  # 答完第6题（接受礼物）
        language = "receiving_gifts"
    elif question_index == 7:  # 答完第8题（服务行动）
        language = "acts_of_service"
    elif question_index == 9:  # 答完第10题（身体接触）
        language = "physical_touch"

    if language is None:
        return {}

    score = scores.get(language, 0.0)
    return {
        "dimension": language,  # 统一使用 dimension 字段（与 MBTI/依恋风格一致）
        "dimension_name": LOVE_LANGUAGE_NAMES[language],  # 统一使用 dimension_name 字段
        "score": score,
        "feedback_text": get_language_feedback(language, score),
    }


def _result_with_interpretation(result: dict[str, Any]) -> dict[str, Any]:
    """结果卡片带解读"""
    if not result:
        return {}
    if result.get("interpretation_data"):
        return result
    merged = dict(result)
    merged["interpretation_data"] = _interpretation_from_result(merged)
    return merged


def start_love_language_assessment(
    *,
    source: str | None,
    user_key: str,
    assessment_type: str = ASSESSMENT_TYPE_LOVE_LANGUAGE,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """创建新的恋爱语言测评会话"""
    if assessment_type != ASSESSMENT_TYPE_LOVE_LANGUAGE:
        raise ValueError("unsupported assessment_type")
    normalized_source, _ = _resolve_source(source)
    assessment_id = f"love_language_{uuid.uuid4().hex[:12]}"
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
                evidence_text="love language assessment started",
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)
    return {
        "card_type": "assessment_intro",
        "assessment_type": assessment_type,
        "assessment_id": assessment_id,
        "intro_data": {
            "title": "恋爱五种语言测验",
            "description": "测测你咋表达爱对方才舒服",
            "duration": "2分钟 · 10题",
            "reward": "测完了解你的恋爱表达偏好",
        },
    }


def get_or_create_love_language_assessment(
    *,
    source: str | None,
    user_key: str,
    assessment_type: str = ASSESSMENT_TYPE_LOVE_LANGUAGE,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """获取未完成的恋爱语言测评（断点续传），或者创建新测评"""
    if assessment_type != ASSESSMENT_TYPE_LOVE_LANGUAGE:
        raise ValueError("unsupported assessment_type")

    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)

    try:
        with conn.cursor() as cursor:
            # 查找用户最近的未完成恋爱语言测评
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
                (user_key, ASSESSMENT_SESSION_FIELD, f'"{ASSESSMENT_TYPE_LOVE_LANGUAGE}"'),
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

        return start_love_language_assessment(
            source=source,
            user_key=user_key,
            assessment_type=assessment_type,
            persona_table=persona_table,
            observation_table=observation_table,
        )

    finally:
        if conn:
            release_persona_connection(normalized_source, conn)


def begin_love_language_assessment(
    *,
    source: str | None,
    assessment_id: str,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """开始恋爱语言测评（返回第一题）"""
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


def answer_love_language_assessment(
    *,
    source: str | None,
    assessment_id: str,
    question_index: int,
    answer: str,
    user_key: str,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """提交恋爱语言测评答案"""
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
                    "language": question["dimension"],
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
            scores = calculate_all_language_scores(ordered_scores)

            answered_count = len(answers)
            if answered_count >= TOTAL_QUESTIONS:
                primary_language = get_primary_love_language(scores)
                language_info = get_language_info(primary_language)
                ranking = get_language_ranking(scores)
                interpretation = _interpretation_from_result(
                    {
                        "primary_language": primary_language,
                        "scores": scores,
                    }
                )
                # 先计算 extreme_labels，用于生成 labels
                extreme_labels = [
                    {
                        "language": lang,
                        "language_name": LOVE_LANGUAGE_NAMES[lang],
                        "score": score,
                        "tag": LOVE_LANGUAGE_LABELS[lang]["nickname"] + "认证 ✨",
                    }
                    for lang, score in scores.items()
                    if score >= 85  # 只有得分≥85才显示认证标签
                ]

                result_data = {
                    "type_code": primary_language,  # 添加 type_code 字段（与 MBTI/Attachment 一致）
                    "scores": scores,
                    "dimension_rows": _dimension_rows(scores),  # 添加 dimension_rows（用于雷达图）
                    "labels": [item["tag"] for item in extreme_labels if item.get("tag")] or [language_info["nickname"]],  # 添加 labels 字段
                    "primary_language": primary_language,
                    "ranking": ranking,
                    # 新标签：基于得分排序，只显示高分语言的标签
                    "sensitive_labels": [
                        {
                            "language": lang,
                            "language_name": LOVE_LANGUAGE_NAMES[lang],
                            "score": score,
                            "label": f"{LOVE_LANGUAGE_NAMES[lang]}敏感({score}分)" if score >= 70 else None,
                        }
                        for lang, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
                        if score >= 50  # 只显示得分≥50的语言
                    ],
                    # 不敏感的标签
                    "insensitive_labels": [
                        {
                            "language": lang,
                            "language_name": LOVE_LANGUAGE_NAMES[lang],
                            "score": score,
                            "label": f"{LOVE_LANGUAGE_NAMES[lang]}不敏感({score}分)" if score <= 30 else None,
                        }
                        for lang, score in sorted(scores.items(), key=lambda x: x[1], reverse=True)[-2:]
                        if score <= 30  # 只显示得分≤30的语言
                    ],
                    # 极端标签（轻量融入，只有得分≥85才显示）
                    "extreme_labels": extreme_labels,
                    "interpretation_data": interpretation,
                    "reward": "测完了解你的恋爱表达偏好",
                    "assessment_id": assessment_id,
                }
                _save_observation(
                    cursor,
                    observation_table=observation_table,
                    user_key=user_key,
                    field_name=ASSESSMENT_RESULT_FIELD,
                    field_value=result_data,
                    assessment_id=assessment_id,
                    evidence_text="love language assessment completed",
                )
                _save_observation(
                    cursor,
                    observation_table=observation_table,
                    user_key=user_key,
                    field_name=ASSESSMENT_INTERPRETATION_FIELD,
                    field_value=interpretation,
                    assessment_id=assessment_id,
                    evidence_text="love language assessment interpretation",
                )
                # 保存小雅解读消息
                xiaoya_message = xiaoya_message_from_result(
                    {
                        "primary_language": primary_language,
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
                # 写入 user_personas.self_personality_traits_json
                traits_payload = {
                    "love_language": {
                        "assessment_id": assessment_id,
                        "primary_language": primary_language,
                        "scores": scores,
                        "ranking": ranking,
                        "labels": [language_info["nickname"]] + language_info["tags"][:3],
                        "source": "assessment",
                        "completed_at": _now(),
                    }
                }
                apply_persona_patch(
                    source=normalized_source,
                    user_key=user_key,
                    source_type="explicit",
                    normalized_patch=normalize_patch(
                        {"self_personality_traits_json": _json(traits_payload)}
                    ),
                    persona_table=persona_table,
                    observation_table=observation_table,
                    evidence_text=f"用户完成恋爱五种语言测评（{assessment_id}）",
                    conversation_ref=assessment_id,
                    apply_scope="persona_only",
                    sync_profile=False,
                    source_channel="assessment",
                )
                conn.commit()
                return {
                    "card_type": "assessment_result",
                    "assessment_type": ASSESSMENT_TYPE_LOVE_LANGUAGE,  # 添加 assessment_type 字段，供前端识别测评类型
                    "assessment_id": assessment_id,
                    "result_data": result_data,
                }

            # 每2题给反馈（答完第2、4、6、8、10题）
            if answered_count in [2, 4, 6, 8, 10]:
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


def get_love_language_interpretation(
    *,
    source: str | None,
    assessment_id: str,
    user_key: str,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """获取恋爱语言测评解读"""
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
                evidence_text="love language assessment interpretation",
            )
            conn.commit()
            return {
                "card_type": "assessment_interpretation",
                "assessment_id": assessment_id,
                "interpretation_data": interpretation,
            }
    finally:
        release_persona_connection(normalized_source, conn)


def get_love_language_xiaoya_message(
    *,
    source: str | None,
    user_key: str,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """获取恋爱语言小雅解读消息"""
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
                  AND JSON_EXTRACT(field_value, '$.assessment_type') = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_key, ASSESSMENT_XIAOYA_MESSAGE_FIELD, f'"{ASSESSMENT_TYPE_LOVE_LANGUAGE}"'),
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


def get_love_language_traits(
    *,
    source: str | None,
    user_key: str,
    persona_table: str = "user_personas",
) -> dict[str, Any]:
    """获取用户的恋爱语言特质"""
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            persona = fetch_persona(cursor, persona_table, user_key=user_key)
            if not persona:
                return {"love_language": {}}
            traits = _parse_json(persona.get("self_personality_traits_json"))
            return {
                "love_language": traits.get("love_language") or {},
            }
    finally:
        release_persona_connection(normalized_source, conn)