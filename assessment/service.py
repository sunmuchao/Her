from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from assessment.mbti_questions import (
    MBTI_QUESTIONS,
    DIMENSIONS,
    calculate_all_scores,
    get_dimension_feedback,
    get_question,
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


TOTAL_QUESTIONS = len(MBTI_QUESTIONS)
ASSESSMENT_TYPE_MBTI = "mbti_16"
ASSESSMENT_SESSION_FIELD = "assessment.session"
ASSESSMENT_RESULT_FIELD = "assessment.result"
ASSESSMENT_INTERPRETATION_FIELD = "assessment.interpretation"


DIMENSION_LABELS = {
    "ei": "外向 E / 内向 I",
    "sn": "实感 S / 直觉 N",
    "tf": "思考 T / 情感 F",
    "jp": "判断 J / 知觉 P",
}

DIMENSION_TRAITS = {
    "ei": {"high": "外向表达", "medium": "社交灵活", "low": "安静内敛"},
    "sn": {"high": "关注细节", "medium": "事实与想法并重", "low": "偏好可能性"},
    "tf": {"high": "逻辑判断", "medium": "理性与感受平衡", "low": "重视共情"},
    "jp": {"high": "计划清晰", "medium": "计划弹性兼顾", "low": "灵活开放"},
}


@dataclass(frozen=True)
class AssessmentSession:
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
) -> tuple[AssessmentSession | None, dict[int, dict[str, Any]], dict[str, Any]]:
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
    session: AssessmentSession | None = None
    answers: dict[int, dict[str, Any]] = {}
    result: dict[str, Any] = {}
    for row in rows:
        field_name = str((row.get("field_name") if isinstance(row, dict) else row[0]) or "")
        field_value = row.get("field_value") if isinstance(row, dict) else row[1]
        user_key = str(row.get("user_key") if isinstance(row, dict) else row[3] or "")
        data = _parse_json(field_value)
        if field_name == ASSESSMENT_SESSION_FIELD:
            created_at = row.get("created_at") if isinstance(row, dict) else row[2]
            session = AssessmentSession(
                assessment_id=str(data.get("assessment_id") or assessment_id),
                assessment_type=str(data.get("assessment_type") or ASSESSMENT_TYPE_MBTI),
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
    dimension = MBTI_QUESTIONS[question_index]["dimension"]
    score = scores.get(dimension, 0.0)
    return {
        "dimension": dimension,
        "dimension_name": DIMENSION_LABELS[dimension],
        "score": score,
        "feedback_text": get_dimension_feedback(dimension, score),
    }


def _dimension_rows(scores: dict[str, float]) -> list[dict[str, Any]]:
    rows = []
    for dimension in DIMENSIONS:
        score = float(scores.get(dimension, 0.0))
        rows.append(
            {
                "key": dimension,
                "name": DIMENSION_LABELS[dimension],
                "score": score,
                "level": "high" if score >= 70 else "medium" if score >= 40 else "low",
                "trait": DIMENSION_TRAITS[dimension]["high" if score >= 70 else "medium" if score >= 40 else "low"],
            }
        )
    return rows


def _type_code_from_scores(scores: dict[str, float]) -> str:
    return "".join(
        [
            "E" if scores.get("ei", 50) >= 50 else "I",
            "S" if scores.get("sn", 50) >= 50 else "N",
            "T" if scores.get("tf", 50) >= 50 else "F",
            "J" if scores.get("jp", 50) >= 50 else "P",
        ]
    )


def _labels_from_scores(scores: dict[str, float]) -> list[str]:
    type_code = _type_code_from_scores(scores)
    labels = [f"MBTI：{type_code}"]
    for dimension in DIMENSIONS:
        score = scores.get(dimension, 0.0)
        if score >= 70 or score <= 30:
            labels.append(DIMENSION_TRAITS[dimension]["high" if score >= 70 else "low"])
    return labels[:3]


def _interpretation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    scores = dict(result.get("scores") or {})
    type_code = str(result.get("type_code") or _type_code_from_scores(scores))
    summary_parts = [f"你的结果更接近 {type_code}。"]
    if scores.get("ei", 50) >= 60:
        summary_parts.append("你在关系里通常更主动。")
    elif scores.get("ei", 50) <= 40:
        summary_parts.append("你更适合先熟起来再慢慢打开。")
    if scores.get("sn", 50) >= 60:
        summary_parts.append("你会更关注现实条件和相处细节。")
    elif scores.get("sn", 50) <= 40:
        summary_parts.append("你更容易被想法、气质和未来感吸引。")
    if scores.get("tf", 50) >= 60:
        summary_parts.append("你处理分歧时更偏讲逻辑。")
    elif scores.get("tf", 50) <= 40:
        summary_parts.append("你处理关系时更在意感受和氛围。")
    if scores.get("jp", 50) >= 60:
        summary_parts.append("你喜欢节奏明确、边界清楚的相处。")
    elif scores.get("jp", 50) <= 40:
        summary_parts.append("你更适合轻松、不被管得太死的关系。")
    return {
        "summary": "".join(summary_parts),
        "love_style": f"{type_code} 在亲密关系里更适合和沟通直接、节奏对得上的人相处。",
        "match_suggestions": [
            "先看聊天节奏和做事方式合不合拍",
            "尽早把你在意的沟通方式、见面频率和边界说清楚",
        ],
    }


def _result_with_interpretation(result: dict[str, Any]) -> dict[str, Any]:
    if not result:
        return {}
    if result.get("interpretation_data"):
        return result
    merged = dict(result)
    merged["interpretation_data"] = _interpretation_from_result(merged)
    return merged


def start_assessment(
    *,
    source: str | None,
    user_key: str,
    assessment_type: str = ASSESSMENT_TYPE_MBTI,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    if assessment_type != ASSESSMENT_TYPE_MBTI:
        raise ValueError("unsupported assessment_type")
    normalized_source, _ = _resolve_source(source)
    assessment_id = f"mbti_{uuid.uuid4().hex[:12]}"
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
                evidence_text="assessment started",
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)
    return {
        "card_type": "assessment_intro",
        "assessment_type": assessment_type,
        "assessment_id": assessment_id,
        "intro_data": {
            "title": "MBTI 16型人格测评",
            "description": "快速看清你的相处风格和关系偏好",
            "duration": "约5分钟 · 20题",
            "reward": "匹配质量提升10%",
        },
    }


def begin_assessment(
    *,
    source: str | None,
    assessment_id: str,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
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


def answer_assessment(
    *,
    source: str | None,
    assessment_id: str,
    question_index: int,
    answer: str,
    user_key: str,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
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

    # Reload after commit for deterministic output.
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
                type_code = _type_code_from_scores(scores)
                labels = _labels_from_scores(scores)
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
                    "labels": labels,
                    "interpretation_data": interpretation,
                    "reward": "匹配质量提升10%",
                    "assessment_id": assessment_id,
                }
                _save_observation(
                    cursor,
                    observation_table=observation_table,
                    user_key=user_key,
                    field_name=ASSESSMENT_RESULT_FIELD,
                    field_value=result_data,
                    assessment_id=assessment_id,
                    evidence_text="assessment completed",
                )
                _save_observation(
                    cursor,
                    observation_table=observation_table,
                    user_key=user_key,
                    field_name=ASSESSMENT_INTERPRETATION_FIELD,
                    field_value=interpretation,
                    assessment_id=assessment_id,
                    evidence_text="assessment interpretation",
                )
                traits_payload = {
                    "mbti": {
                        "assessment_id": assessment_id,
                        "type_code": type_code,
                        "scores": scores,
                        "dimension_rows": _dimension_rows(scores),
                        "labels": labels,
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
                    evidence_text=f"用户完成 MBTI 16 型人格测评（{assessment_id}）",
                    conversation_ref=assessment_id,
                    apply_scope="persona_only",
                    sync_profile=False,
                    source_channel="assessment",
                )
                conn.commit()
                return {
                    "card_type": "assessment_result",
                    "assessment_id": assessment_id,
                    "result_data": result_data,
                }

            if answered_count % 5 == 0:
                feedback_data = _feedback_payload(answered_count - 1, scores)
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


def get_assessment_interpretation(
    *,
    source: str | None,
    assessment_id: str,
    user_key: str,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
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
                evidence_text="assessment interpretation",
            )
            conn.commit()
            return {
                "card_type": "assessment_interpretation",
                "assessment_id": assessment_id,
                "interpretation_data": interpretation,
            }
    finally:
        release_persona_connection(normalized_source, conn)


def get_personality_traits(
    *,
    source: str | None,
    user_key: str,
    persona_table: str = "user_personas",
) -> dict[str, Any]:
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            persona = fetch_persona(cursor, persona_table, user_key=user_key)
            if not persona:
                return {"mbti": {}, "attachment": {}, "love_language": {}}
            traits = _parse_json(persona.get("self_personality_traits_json"))
            return {
                "mbti": traits.get("mbti") or {},
                "attachment": traits.get("attachment") or {},
                "love_language": traits.get("love_language") or {},
            }
    finally:
        release_persona_connection(normalized_source, conn)
