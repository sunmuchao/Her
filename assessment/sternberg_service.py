"""Sternberg triangular love assessment service."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from assessment.sternberg_questions import (
    QUESTIONS_PER_DIMENSION,
    STERNBERG_DIMENSION_NAMES,
    TOTAL_QUESTIONS,
    calculate_all_scores,
    get_dimension_feedback,
    get_question,
)
from assessment.result_store import merge_personality_summary, store_assessment_result
from persona_memory_sync.persona_memory_lib import (
    mysql_connect,
    parse_mysql_source,
    quote_mysql_ident,
    release_persona_connection,
)


ASSESSMENT_TYPE_STERNBERG = "sternberg_triangular_love"
ASSESSMENT_SESSION_FIELD = "assessment.session"
ASSESSMENT_RESULT_FIELD = "assessment.result"
ASSESSMENT_INTERPRETATION_FIELD = "assessment.interpretation"
ASSESSMENT_XIAOYA_MESSAGE_FIELD = "assessment.xiaoya_message"


@dataclass(frozen=True)
class SternbergAssessmentSession:
    assessment_id: str
    assessment_type: str
    user_key: str
    status: str
    created_at: str


def _resolve_source(source: str | None) -> tuple[str, str]:
    parsed = parse_mysql_source(source)
    return str(parsed["source"]), str(parsed["table"])


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


def _save_observation(
    cursor: Any,
    *,
    observation_table: str,
    user_key: str,
    field_name: str,
    field_value: Any,
    assessment_id: str,
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
        VALUES (%s, NULL, %s, %s, 'explicit', 100, %s, %s, 'assessment', 'insert', 1, 0, %s)
        """,
        (
            user_key,
            field_name,
            _json(field_value) if isinstance(field_value, (dict, list)) else str(field_value),
            evidence_text,
            assessment_id,
            _now(),
        ),
    )


def _session_payload(assessment_id: str, user_key: str, *, status: str = "in_progress") -> dict[str, Any]:
    return {
        "assessment_id": assessment_id,
        "assessment_type": ASSESSMENT_TYPE_STERNBERG,
        "user_key": user_key,
        "status": status,
        "total_questions": TOTAL_QUESTIONS,
        "created_at": _now(),
    }


def _load_session_and_answers(
    cursor: Any,
    *,
    observation_table: str,
    assessment_id: str,
) -> tuple[SternbergAssessmentSession | None, dict[int, dict[str, Any]], dict[str, Any]]:
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
    session: SternbergAssessmentSession | None = None
    answers: dict[int, dict[str, Any]] = {}
    result: dict[str, Any] = {}
    for row in rows:
        field_name = str((row.get("field_name") if isinstance(row, dict) else row[0]) or "")
        field_value = row.get("field_value") if isinstance(row, dict) else row[1]
        user_key = str(row.get("user_key") if isinstance(row, dict) else row[3] or "")
        data = _parse_json(field_value)
        if field_name == ASSESSMENT_SESSION_FIELD:
            created_at = row.get("created_at") if isinstance(row, dict) else row[2]
            session = SternbergAssessmentSession(
                assessment_id=str(data.get("assessment_id") or assessment_id),
                assessment_type=str(data.get("assessment_type") or ASSESSMENT_TYPE_STERNBERG),
                user_key=str(data.get("user_key") or user_key),
                status=str(data.get("status") or "in_progress"),
                created_at=str(data.get("created_at") or created_at or ""),
            )
        elif field_name.startswith("assessment.answer."):
            try:
                answers[int(field_name.rsplit(".", 1)[-1])] = data
            except ValueError:
                continue
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


def _feedback_payload(answered_count: int, scores: dict[str, float]) -> dict[str, Any]:
    dimension_index = (answered_count // QUESTIONS_PER_DIMENSION) - 1
    dimensions = ["intimacy", "passion", "commitment"]
    if not (0 <= dimension_index < len(dimensions)):
        return {}
    dimension = dimensions[dimension_index]
    return {
        "dimension": dimension,
        "dimension_name": STERNBERG_DIMENSION_NAMES[dimension],
        "score": float(scores.get(dimension, 0.0)),
        "feedback_text": get_dimension_feedback(dimension, float(scores.get(dimension, 0.0))),
    }


def _dimension_rows(scores: dict[str, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension in ["intimacy", "passion", "commitment"]:
        score = float(scores.get(dimension, 0.0))
        level = "high" if score >= 70 else "medium" if score >= 40 else "low"
        trait = {
            "intimacy": {"high": "深入靠近", "medium": "逐步打开", "low": "仍在保留"},
            "passion": {"high": "火花强烈", "medium": "心动适中", "low": "克制观察"},
            "commitment": {"high": "长期投入", "medium": "稳步确认", "low": "暂不绑定"},
        }[dimension][level]
        rows.append({"key": dimension, "name": STERNBERG_DIMENSION_NAMES[dimension], "score": score, "level": level, "trait": trait})
    return rows


def _labels(scores: dict[str, float]) -> list[str]:
    labels: list[str] = []
    for dimension in ("intimacy", "passion", "commitment"):
        score = float(scores.get(dimension, 0.0))
        if score >= 70:
            labels.append(f"{STERNBERG_DIMENSION_NAMES[dimension]}较高")
        elif score <= 30:
            labels.append(f"{STERNBERG_DIMENSION_NAMES[dimension]}较低")
        else:
            labels.append(f"{STERNBERG_DIMENSION_NAMES[dimension]}中等")
    return labels


def _extreme_tags(scores: dict[str, float]) -> list[dict[str, str]]:
    tags: list[dict[str, str]] = []
    if scores.get("intimacy", 0) >= 80:
        tags.append({"tag": "亲密感很强", "description": "你会明显在意能不能互相理解、支持和贴近。"})
    if scores.get("passion", 0) >= 80:
        tags.append({"tag": "心动浓度高", "description": "关系里的吸引和热烈感对你很重要。"})
    if scores.get("commitment", 0) >= 80:
        tags.append({"tag": "承诺感很重", "description": "一旦认真，你会很自然地把未来也一起考虑进去。"})
    return tags


def _interpretation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    scores = result.get("scores") or {}
    sorted_dims = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    lead = STERNBERG_DIMENSION_NAMES.get(sorted_dims[0][0], "某个成分") if sorted_dims else "某个成分"
    low = STERNBERG_DIMENSION_NAMES.get(sorted_dims[-1][0], "某个成分") if sorted_dims else "某个成分"
    return {
        "summary": f"按斯腾伯格爱情三元论来看，你当前的爱主要由三条线构成：亲密、激情、承诺。你的结果里，{lead}相对更突出，{low}相对更弱。",
        "love_style": "三元论的标准读法是分别看三条分数，而不是先把人硬分成某一种爱情类型。",
        "match_suggestions": [
            "亲密较高时，通常更看重被理解、被支持和能不能真正靠近。",
            "激情较高时，通常更在意吸引力、浪漫感和强烈心动是否存在。",
            "承诺较高时，通常更在意关系是否稳定、能否进入长期投入。 ",
        ],
        "relationship_drive": f"当前更值得关注的是 {lead} 这一成分如何影响你对关系的主观体验与判断。",
        "communication_advice": "解释结果时请优先看三条分数本身，再看它们之间是否均衡，而不是把它当成固定爱情人设。",
        "card_tip": "TLS-15 的标准输出是三维结构分数。",
        "disclaimer": "依据来源：Sternberg Triangular Love Theory 与 TLS-15 题项结构。本产品在题项结构上遵循 TLS-15，并采用 1-9 的作答量尺来贴近公开验证研究；结果应主要理解为亲密、激情、承诺三维结构分数。",
        "extreme_tags": _extreme_tags(scores),
    }


def _build_xiaoya_message(result: dict[str, Any]) -> str:
    scores = result.get("scores") or {}
    sorted_dims = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    top_dim = sorted_dims[0][0] if scores else "intimacy"
    second_dim = sorted_dims[1][0] if len(sorted_dims) > 1 else "passion"
    low_dim = sorted_dims[-1][0] if scores else "commitment"
    top_name = STERNBERG_DIMENSION_NAMES.get(top_dim, "某个成分")
    second_name = STERNBERG_DIMENSION_NAMES.get(second_dim, "另一条线")
    low_name = STERNBERG_DIMENSION_NAMES.get(low_dim, "某个成分")
    return (
        "亲爱的，结果出来啦，我先陪你看重点。\n"
        "你这次的爱情三元结果里，"
        f"**{top_name}** 和 **{second_name}** 相对更高，**{low_name}** 相对更低。\n"
        "==重点是==：三元论看的不是给你判成哪一种固定爱情类型，而是看 **亲密、激情、承诺** 这三条线现在分别高不高、均不均衡。\n"
        "再往下说一点，你很多时候可能会是这种感觉：\n"
        f"- **{top_name}** 更突出，说明这条线最容易主导你现在对关系的主观体验。\n"
        f"- **{second_name}** 也在线，所以你不是单靠某一个成分在推进关系。\n"
        f"- **{low_name}** 相对靠后，通常意味着这部分暂时不是你这段关系里最强的支撑点。\n"
        "- 真正有用的不是给这段关系贴一个总标签，而是看三条线哪里强、哪里弱、哪里不均衡。\n\n"
        "放到关系里，你可以重点看这几件事：\n"
        f"- 如果 **{top_name}** 一路带节奏，你会最先从这一块感受到满足或落差。\n"
        f"- **{second_name}** 会决定你是不是还能把这段关系往更稳或更深的方向推一步。\n"
        f"- 如果 **{low_name}** 偏低，很多纠结不一定是“没感觉”，也可能只是这条线还没真正长出来。\n\n"
        "如果你愿意，我下一条还能继续陪你拆：这三条里哪一条最容易让你上头，哪一条又最容易让你在关系里不踏实。"
    )


def start_sternberg_assessment(*, source: str | None, user_key: str, observation_table: str = "user_persona_observations") -> dict[str, Any]:
    normalized_source, _ = _resolve_source(source)
    assessment_id = f"sternberg_{uuid.uuid4().hex[:12]}"
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            _save_observation(cursor, observation_table=observation_table, user_key=user_key, field_name=ASSESSMENT_SESSION_FIELD, field_value=_session_payload(assessment_id, user_key), assessment_id=assessment_id, evidence_text="sternberg assessment started")
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)
    return {
        "card_type": "assessment_intro",
        "assessment_type": ASSESSMENT_TYPE_STERNBERG,
        "assessment_id": assessment_id,
        "intro_data": {
            "title": "爱情三元论测评",
            "description": "基于 TLS-15 结构，看看你当前关系里的亲密、激情与承诺分别有多强。",
            "duration": "3-4分钟 · 15题",
            "reward": "获取爱情结构快照",
        },
    }


def get_or_create_sternberg_assessment(*, source: str | None, user_key: str, observation_table: str = "user_persona_observations") -> dict[str, Any]:
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT conversation_ref, field_value
                FROM {quote_mysql_ident(observation_table)}
                WHERE user_key = %s
                  AND field_name = %s
                  AND source_channel = 'assessment'
                  AND JSON_EXTRACT(field_value, '$.assessment_type') = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_key, ASSESSMENT_SESSION_FIELD, f'"{ASSESSMENT_TYPE_STERNBERG}"'),
            )
            row = cursor.fetchone()
            if row:
                data = _parse_json(row.get("field_value") if isinstance(row, dict) else row[1])
                assessment_id = str(row.get("conversation_ref") if isinstance(row, dict) else row[0])
                if data.get("status") == "in_progress":
                    session, answers, _ = _load_session_and_answers(cursor, observation_table=observation_table, assessment_id=assessment_id)
                    if session and len(answers) < TOTAL_QUESTIONS:
                        answered_count = len(answers)
                        return {
                            "card_type": "assessment_intro",
                            "assessment_type": ASSESSMENT_TYPE_STERNBERG,
                            "assessment_id": assessment_id,
                            "intro_data": {
                                "title": "继续上次的测评",
                                "description": f"已答 {answered_count} 题，还有 {TOTAL_QUESTIONS - answered_count} 题",
                                "duration": "继续测评",
                                "reward": "上次进度已保存",
                            },
                            "resumed": True,
                            "answered_count": answered_count,
                        }
    finally:
        release_persona_connection(normalized_source, conn)
    return start_sternberg_assessment(source=source, user_key=user_key, observation_table=observation_table)


def begin_sternberg_assessment(*, source: str | None, assessment_id: str, observation_table: str = "user_persona_observations") -> dict[str, Any]:
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            session, answers, _ = _load_session_and_answers(cursor, observation_table=observation_table, assessment_id=assessment_id)
            if session is None:
                raise ValueError("assessment not found")
            return {"card_type": "assessment_question", "assessment_id": assessment_id, "question_data": _question_payload(len(answers), assessment_id)}
    finally:
        release_persona_connection(normalized_source, conn)


def answer_sternberg_assessment(
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
            session, answers, _ = _load_session_and_answers(cursor, observation_table=observation_table, assessment_id=assessment_id)
            if session is None:
                raise ValueError("assessment not found")
            if session.user_key and session.user_key != str(user_key):
                raise ValueError("assessment does not belong to user")
            if not (0 <= question_index < TOTAL_QUESTIONS):
                raise ValueError("question_index out of range")
            if question_index not in answers and question_index != len(answers):
                raise ValueError("question sequence mismatch")
            question = get_question(question_index)
            if question is None:
                raise ValueError("question not found")
            options = {str(item["label"]).upper(): item for item in question["options"]}
            selected = options.get(str(answer).strip().upper())
            if selected is None:
                raise ValueError("invalid answer")
            _save_observation(cursor, observation_table=observation_table, user_key=user_key, field_name=f"assessment.answer.{question_index}", field_value={"question_index": question_index, "answer": str(answer).strip().upper(), "score": int(selected["score"]), "dimension": question["dimension"]}, assessment_id=assessment_id, evidence_text=f"answer for question {question_index}")
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)

    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            _session, answers, _ = _load_session_and_answers(cursor, observation_table=observation_table, assessment_id=assessment_id)
            ordered_scores = [3] * TOTAL_QUESTIONS
            for idx, payload in answers.items():
                if 0 <= idx < TOTAL_QUESTIONS:
                    ordered_scores[idx] = int(payload.get("score", 3))
            scores = calculate_all_scores(ordered_scores)
            answered_count = len(answers)
            if answered_count >= TOTAL_QUESTIONS:
                type_code = "三元结构"
                labels = _labels(scores)
                result_data = {
                    "type_code": type_code,
                    "scores": scores,
                    "dimension_rows": _dimension_rows(scores),
                    "labels": labels,
                    "interpretation_data": _interpretation_from_result({"type_code": type_code, "scores": scores}),
                    "reward": "爱情结构快照",
                    "assessment_id": assessment_id,
                }
                interpretation = result_data["interpretation_data"]
                _save_observation(cursor, observation_table=observation_table, user_key=user_key, field_name=ASSESSMENT_RESULT_FIELD, field_value=result_data, assessment_id=assessment_id, evidence_text="sternberg assessment completed")
                _save_observation(cursor, observation_table=observation_table, user_key=user_key, field_name=ASSESSMENT_INTERPRETATION_FIELD, field_value=interpretation, assessment_id=assessment_id, evidence_text="sternberg interpretation")
                _save_observation(cursor, observation_table=observation_table, user_key=user_key, field_name=ASSESSMENT_XIAOYA_MESSAGE_FIELD, field_value={"message": _build_xiaoya_message(result_data), "read": False, "assessment_type": ASSESSMENT_TYPE_STERNBERG}, assessment_id=assessment_id, evidence_text="sternberg xiaoya message")
                completed_at = _now()
                summary_payload = {
                    "assessment_id": assessment_id,
                    "type_code": type_code,
                    "scores": scores,
                    "completed_at": completed_at,
                }
                store_assessment_result(
                    source=normalized_source,
                    user_key=user_key,
                    assessment_id=assessment_id,
                    assessment_type=ASSESSMENT_TYPE_STERNBERG,
                    raw_result=result_data,
                    summary=summary_payload,
                    interpretation=interpretation,
                    completed_at=completed_at,
                    source_channel="assessment",
                )
                merge_personality_summary(
                    source=normalized_source,
                    user_key=user_key,
                    summary_key="sternberg",
                    summary_payload=summary_payload,
                    persona_table=persona_table,
                    observation_table=observation_table,
                    evidence_text=f"用户完成爱情三元论测评（{assessment_id}）",
                    conversation_ref=assessment_id,
                    source_channel="assessment",
                )
                conn.commit()
                return {"card_type": "assessment_result", "assessment_type": ASSESSMENT_TYPE_STERNBERG, "assessment_id": assessment_id, "result_data": result_data}
            if answered_count > 0 and answered_count % QUESTIONS_PER_DIMENSION == 0:
                feedback_data = _feedback_payload(answered_count, scores)
                if feedback_data:
                    return {"card_type": "assessment_feedback", "assessment_id": assessment_id, "feedback_data": feedback_data, "next_question": _question_payload(answered_count, assessment_id)}
            return {"card_type": "assessment_question", "assessment_id": assessment_id, "question_data": _question_payload(answered_count, assessment_id)}
    finally:
        release_persona_connection(normalized_source, conn)


def get_sternberg_interpretation(*, source: str | None, assessment_id: str, user_key: str, observation_table: str = "user_persona_observations") -> dict[str, Any]:
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            session, _answers, result = _load_session_and_answers(cursor, observation_table=observation_table, assessment_id=assessment_id)
            if session is None:
                raise ValueError("assessment not found")
            if session.user_key and session.user_key != str(user_key):
                raise ValueError("assessment does not belong to user")
            if not result:
                raise ValueError("assessment result not ready")
            interpretation = result.get("interpretation_data") or _interpretation_from_result(result)
            return {"card_type": "assessment_interpretation", "assessment_id": assessment_id, "interpretation_data": interpretation}
    finally:
        release_persona_connection(normalized_source, conn)


def get_sternberg_xiaoya_message(*, source: str | None, user_key: str, observation_table: str = "user_persona_observations") -> dict[str, Any]:
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT field_value, conversation_ref
                FROM {quote_mysql_ident(observation_table)}
                WHERE user_key = %s
                  AND field_name = %s
                  AND source_channel = 'assessment'
                  AND conversation_ref LIKE %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_key, ASSESSMENT_XIAOYA_MESSAGE_FIELD, "sternberg_%"),
            )
            row = cursor.fetchone()
            if not row:
                return {"has_message": False}
            data = _parse_json(row.get("field_value") if isinstance(row, dict) else row[0])
            if not data or data.get("read"):
                return {"has_message": False}
            return {"has_message": True, "message": data.get("message") or "", "assessment_id": str(row.get("conversation_ref") if isinstance(row, dict) else row[1])}
    finally:
        release_persona_connection(normalized_source, conn)
