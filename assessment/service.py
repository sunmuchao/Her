from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from assessment.big_five_questions import (
    BIG_FIVE_QUESTIONS,
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


TOTAL_QUESTIONS = len(BIG_FIVE_QUESTIONS)
ASSESSMENT_TYPE_BIG_FIVE = "big_five"
ASSESSMENT_SESSION_FIELD = "assessment.session"
ASSESSMENT_RESULT_FIELD = "assessment.result"
ASSESSMENT_INTERPRETATION_FIELD = "assessment.interpretation"


DIMENSION_LABELS = {
    "openness": "开放性",
    "conscientiousness": "尽责性",
    "extraversion": "外向性",
    "agreeableness": "宜人性",
    "neuroticism": "神经质",
}

DIMENSION_TRAITS = {
    "openness": "喜欢新鲜感",
    "conscientiousness": "做事靠谱",
    "extraversion": "社交主动",
    "agreeableness": "温和体贴",
    "neuroticism": "情绪稳定",
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
                assessment_type=str(data.get("assessment_type") or ASSESSMENT_TYPE_BIG_FIVE),
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
            result = data
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
    dimension = BIG_FIVE_QUESTIONS[question_index]["dimension"]
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
                "trait": DIMENSION_TRAITS[dimension],
            }
        )
    return rows


def _labels_from_scores(scores: dict[str, float]) -> list[str]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    labels: list[str] = []
    for dimension, score in ranked[:3]:
        if score >= 60:
            labels.append(DIMENSION_TRAITS[dimension])
    if not labels:
        labels.append("你是一个比较均衡的人")
    return labels[:3]


def _interpretation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    scores = dict(result.get("scores") or {})
    summary_parts = []
    if scores.get("conscientiousness", 0) >= 70:
        summary_parts.append("你做事有计划，稳定可靠。")
    if scores.get("extraversion", 0) >= 70:
        summary_parts.append("你在社交中更容易主动。")
    if scores.get("agreeableness", 0) >= 70:
        summary_parts.append("你通常更温和、好相处。")
    if scores.get("openness", 0) >= 70:
        summary_parts.append("你对新鲜事物接受度高。")
    if scores.get("neuroticism", 0) <= 30:
        summary_parts.append("你面对压力时更稳。")
    if not summary_parts:
        summary_parts.append("你的性格比较均衡，适合结合具体相处来判断匹配度。")
    return {
        "summary": "".join(summary_parts),
        "love_style": "更适合和节奏稳定、沟通清楚的人相处。",
        "match_suggestions": [
            "优先找相处舒服、沟通顺畅的人",
            "把你最在意的生活节奏和边界提前说清楚",
        ],
    }


def start_assessment(
    *,
    source: str | None,
    user_key: str,
    assessment_type: str = ASSESSMENT_TYPE_BIG_FIVE,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    if assessment_type != ASSESSMENT_TYPE_BIG_FIVE:
        raise ValueError("unsupported assessment_type")
    normalized_source, _ = _resolve_source(source)
    assessment_id = f"bf_{uuid.uuid4().hex[:12]}"
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
            "title": "大五人格测试",
            "description": "了解你的性格底色",
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
                labels = _labels_from_scores(scores)
                result_data = {
                    "scores": scores,
                    "dimension_rows": _dimension_rows(scores),
                    "labels": labels,
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
                traits_payload = {
                    "big_five": {
                        "assessment_id": assessment_id,
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
                    evidence_text=f"用户完成大五人格测评（{assessment_id}）",
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

            if answered_count % 4 == 0:
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
                return {"big_five": {}, "attachment": {}, "love_language": {}}
            traits = _parse_json(persona.get("self_personality_traits_json"))
            return {
                "big_five": traits.get("big_five") or {},
                "attachment": traits.get("attachment") or {},
                "love_language": traits.get("love_language") or {},
            }
    finally:
        release_persona_connection(normalized_source, conn)
