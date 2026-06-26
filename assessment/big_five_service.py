"""Big Five assessment service based on IPIP public-domain items."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from assessment.big_five_questions import (
    BIG_FIVE_DIMENSIONS,
    BIG_FIVE_DIMENSION_LABELS,
    BIG_FIVE_DIMENSION_NAMES,
    QUESTIONS_PER_DIMENSION,
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


ASSESSMENT_TYPE_BIG_FIVE = "big_five"
ASSESSMENT_SESSION_FIELD = "assessment.session"
ASSESSMENT_RESULT_FIELD = "assessment.result"
ASSESSMENT_INTERPRETATION_FIELD = "assessment.interpretation"
ASSESSMENT_XIAOYA_MESSAGE_FIELD = "assessment.xiaoya_message"


@dataclass(frozen=True)
class BigFiveAssessmentSession:
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
        "assessment_type": ASSESSMENT_TYPE_BIG_FIVE,
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
) -> tuple[BigFiveAssessmentSession | None, dict[int, dict[str, Any]], dict[str, Any]]:
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
    session: BigFiveAssessmentSession | None = None
    answers: dict[int, dict[str, Any]] = {}
    result: dict[str, Any] = {}
    for row in rows:
        field_name = str((row.get("field_name") if isinstance(row, dict) else row[0]) or "")
        field_value = row.get("field_value") if isinstance(row, dict) else row[1]
        user_key = str(row.get("user_key") if isinstance(row, dict) else row[3] or "")
        data = _parse_json(field_value)
        if field_name == ASSESSMENT_SESSION_FIELD:
            created_at = row.get("created_at") if isinstance(row, dict) else row[2]
            session = BigFiveAssessmentSession(
                assessment_id=str(data.get("assessment_id") or assessment_id),
                assessment_type=str(data.get("assessment_type") or ASSESSMENT_TYPE_BIG_FIVE),
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
    if not (0 <= dimension_index < len(BIG_FIVE_DIMENSIONS)):
        return {}
    dimension = BIG_FIVE_DIMENSIONS[dimension_index]
    return {
        "dimension": dimension,
        "dimension_name": BIG_FIVE_DIMENSION_NAMES[dimension],
        "score": float(scores.get(dimension, 0.0)),
        "feedback_text": get_dimension_feedback(dimension, float(scores.get(dimension, 0.0))),
    }


def _dimension_rows(scores: dict[str, float]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for dimension in BIG_FIVE_DIMENSIONS:
        score = float(scores.get(dimension, 0.0))
        level = "high" if score >= 70 else "medium" if score >= 40 else "low"
        rows.append(
            {
                "key": dimension,
                "name": BIG_FIVE_DIMENSION_NAMES[dimension],
                "score": score,
                "level": level,
                "trait": BIG_FIVE_DIMENSION_LABELS[dimension][level],
            }
        )
    return rows


def _build_big_five_labels(scores: dict[str, float]) -> list[str]:
    labels: list[str] = []
    for dimension in BIG_FIVE_DIMENSIONS:
        score = float(scores.get(dimension, 0.0))
        if score >= 70:
            labels.append(f"{BIG_FIVE_DIMENSION_NAMES[dimension]}较高")
        elif score <= 30:
            labels.append(f"{BIG_FIVE_DIMENSION_NAMES[dimension]}较低")
        else:
            labels.append(f"{BIG_FIVE_DIMENSION_NAMES[dimension]}中等")
    return labels


def _extreme_tags(scores: dict[str, float]) -> list[dict[str, str]]:
    tags: list[dict[str, str]] = []
    if scores.get("conscientiousness", 0) >= 80:
        tags.append({"tag": "计划感很强", "description": "你对节奏、承诺和执行通常是有要求的。"})
    if scores.get("agreeableness", 0) >= 80:
        tags.append({"tag": "关系润滑度高", "description": "你很容易顾及感受，也更擅长把气氛放柔和。"})
    if scores.get("openness", 0) >= 80:
        tags.append({"tag": "新鲜感需求高", "description": "你容易被有趣、成长和变化感吸引。"})
    if scores.get("neuroticism", 0) <= 20:
        tags.append({"tag": "稳定感在线", "description": "你不太容易因为波动立刻失衡。"})
    if scores.get("neuroticism", 0) >= 80:
        tags.append({"tag": "感受牵动强", "description": "你会更快感到压力和关系里的变化。"})
    return tags


def _interpretation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    scores = result.get("scores") or {}
    sorted_dims = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    lead = BIG_FIVE_DIMENSION_NAMES.get(sorted_dims[0][0], "某个维度") if sorted_dims else "多个维度"
    support = BIG_FIVE_DIMENSION_NAMES.get(sorted_dims[1][0], "另一个维度") if len(sorted_dims) > 1 else "另一个维度"
    low_dim = BIG_FIVE_DIMENSION_NAMES.get(sorted_dims[-1][0], "某个维度") if sorted_dims else "某个维度"
    return {
        "summary": f"你的结果显示，{lead}和{support}相对更高，{low_dim}相对更低。大五强调的是五个连续维度的相对水平，而不是把人归成固定类型。",
        "love_style": "这份结果更适合用来理解你在行为、情绪和人际风格上的一般倾向，而不只限于亲密关系场景。",
        "match_suggestions": [
            f"{BIG_FIVE_DIMENSION_NAMES['neuroticism']}较高时，通常更容易体验到压力和担忧。",
            f"{BIG_FIVE_DIMENSION_NAMES['conscientiousness']}较高时，通常更有计划性和自我约束。",
            f"{BIG_FIVE_DIMENSION_NAMES['agreeableness']}较高时，通常更重视合作与他人感受。",
        ],
        "relationship_drive": f"当前最值得优先关注的，是 {lead} 与 {support} 这两个维度如何共同影响你的日常行为与人际风格。",
        "communication_advice": "阅读结果时请以五个维度的连续分数为主，而不是把自己理解成某一种固定人格类型。",
        "card_tip": "大五的标准解释单位是维度，不是类型。",
        "disclaimer": "依据来源：IPIP Big-Five Factor Markers 公有领域题项框架。本产品做了中文与产品交互改写，但结果解释仍以五个连续维度为核心，不提供权威原量表并不存在的人格类型划分。",
        "extreme_tags": _extreme_tags(scores),
    }


def _build_xiaoya_message(result: dict[str, Any]) -> str:
    scores = result.get("scores") or {}
    sorted_dims = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    lead = sorted_dims[0][0] if sorted_dims else "conscientiousness"
    support = sorted_dims[1][0] if len(sorted_dims) > 1 else "openness"
    low = sorted_dims[-1][0] if sorted_dims else "neuroticism"
    lead_name = BIG_FIVE_DIMENSION_NAMES.get(lead, "某个维度")
    support_name = BIG_FIVE_DIMENSION_NAMES.get(support, "另一个维度")
    low_name = BIG_FIVE_DIMENSION_NAMES.get(low, "某个维度")
    return (
        "亲爱的，结果出来啦，我先陪你看重点。\n"
        f"你这次的大五结果里，**{lead_name}** 和 **{support_name}** 相对更高，**{low_name}** 相对更低。\n"
        "==重点是==：大五看的是五个连续维度的相对水平，不是把人分成固定类型，也不代表谁更好。\n"
        "再往下说一点，你很多时候可能会是这种感觉：\n"
        f"- 在 **{lead_name}** 这一维上，你更容易稳定地表现出对应倾向。\n"
        f"- **{support_name}** 会进一步放大你的日常表达方式和人际风格。\n"
        f"- **{low_name}** 相对靠后，说明这一维对你的影响通常没前两项那么强。\n"
        "- 真正有用的不是给自己贴一个人设，而是知道自己在哪些维度更高、哪些维度更低。\n\n"
        "放到关系里，你可以重点看这几件事：\n"
        f"- **{lead_name}** 会最明显地影响你靠近别人、处理节奏或表达自己的方式。\n"
        f"- **{support_name}** 往往决定你在稳定性、合作感或社交投入上的补充风格。\n"
        f"- 如果 **{low_name}** 偏低或偏高带来摩擦，通常更适合靠观察场景去理解，而不是直接把自己归成某一种人。\n\n"
        "如果你愿意，我下一条还能继续陪你拆：这五个维度里，哪一维最容易在关系里拖你后腿，哪一维又最容易成为你的优势。"
    )


def start_big_five_assessment(*, source: str | None, user_key: str, observation_table: str = "user_persona_observations") -> dict[str, Any]:
    normalized_source, _ = _resolve_source(source)
    assessment_id = f"big_five_{uuid.uuid4().hex[:12]}"
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=user_key,
                field_name=ASSESSMENT_SESSION_FIELD,
                field_value=_session_payload(assessment_id, user_key),
                assessment_id=assessment_id,
                evidence_text="big five assessment started",
            )
        conn.commit()
    finally:
        release_persona_connection(normalized_source, conn)
    return {
        "card_type": "assessment_intro",
        "assessment_type": ASSESSMENT_TYPE_BIG_FIVE,
        "assessment_id": assessment_id,
        "intro_data": {
            "title": "大五人格特质测评",
            "description": "基于 IPIP 公有领域题库，查看你的开放性、尽责性、外向性、宜人性与情绪敏感度画像。",
            "duration": "8-10分钟 · 50题",
            "reward": "获取连续人格画像",
        },
    }


def get_or_create_big_five_assessment(*, source: str | None, user_key: str, observation_table: str = "user_persona_observations") -> dict[str, Any]:
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
                (user_key, ASSESSMENT_SESSION_FIELD, f'"{ASSESSMENT_TYPE_BIG_FIVE}"'),
            )
            row = cursor.fetchone()
            if row:
                data = _parse_json(row.get("field_value") if isinstance(row, dict) else row[1])
                assessment_id = str(row.get("conversation_ref") if isinstance(row, dict) else row[0])
                if data.get("status") == "in_progress":
                    session, answers, _ = _load_session_and_answers(
                        cursor, observation_table=observation_table, assessment_id=assessment_id
                    )
                    if session and len(answers) < TOTAL_QUESTIONS:
                        answered_count = len(answers)
                        return {
                            "card_type": "assessment_intro",
                            "assessment_type": ASSESSMENT_TYPE_BIG_FIVE,
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
    return start_big_five_assessment(source=source, user_key=user_key, observation_table=observation_table)


def begin_big_five_assessment(*, source: str | None, assessment_id: str, observation_table: str = "user_persona_observations") -> dict[str, Any]:
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


def answer_big_five_assessment(
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
            _save_observation(
                cursor,
                observation_table=observation_table,
                user_key=user_key,
                field_name=f"assessment.answer.{question_index}",
                field_value={
                    "question_index": question_index,
                    "answer": str(answer).strip().upper(),
                    "score": int(selected["score"]),
                    "dimension": question["dimension"],
                    "reverse": bool(question.get("reverse")),
                },
                assessment_id=assessment_id,
                evidence_text=f"answer for question {question_index}",
            )
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
                type_code = "大五画像"
                labels = _build_big_five_labels(scores)
                result_data = {
                    "type_code": type_code,
                    "scores": scores,
                    "dimension_rows": _dimension_rows(scores),
                    "labels": labels,
                    "interpretation_data": _interpretation_from_result({"scores": scores, "type_code": type_code}),
                    "reward": "连续人格画像",
                    "assessment_id": assessment_id,
                }
                interpretation = result_data["interpretation_data"]
                xiaoya_message = _build_xiaoya_message(result_data)
                _save_observation(cursor, observation_table=observation_table, user_key=user_key, field_name=ASSESSMENT_RESULT_FIELD, field_value=result_data, assessment_id=assessment_id, evidence_text="big five assessment completed")
                _save_observation(cursor, observation_table=observation_table, user_key=user_key, field_name=ASSESSMENT_INTERPRETATION_FIELD, field_value=interpretation, assessment_id=assessment_id, evidence_text="big five interpretation")
                _save_observation(
                    cursor,
                    observation_table=observation_table,
                    user_key=user_key,
                    field_name=ASSESSMENT_XIAOYA_MESSAGE_FIELD,
                    field_value={"message": xiaoya_message, "read": False, "assessment_type": ASSESSMENT_TYPE_BIG_FIVE},
                    assessment_id=assessment_id,
                    evidence_text="big five xiaoya message",
                )
                completed_at = _now()
                summary_payload = {
                    "assessment_id": assessment_id,
                    "scores": scores,
                    "completed_at": completed_at,
                }
                store_assessment_result(
                    source=normalized_source,
                    user_key=user_key,
                    assessment_id=assessment_id,
                    assessment_type=ASSESSMENT_TYPE_BIG_FIVE,
                    raw_result=result_data,
                    summary=summary_payload,
                    interpretation=interpretation,
                    completed_at=completed_at,
                    source_channel="assessment",
                )
                merge_personality_summary(
                    source=normalized_source,
                    user_key=user_key,
                    summary_key="big_five",
                    summary_payload=summary_payload,
                    persona_table=persona_table,
                    observation_table=observation_table,
                    evidence_text=f"用户完成大五人格测评（{assessment_id}）",
                    conversation_ref=assessment_id,
                    source_channel="assessment",
                )
                conn.commit()

                # ✅ 修复：清理画像缓存，确保Agent能看到最新的大五人格结果
                # 根因：_cached_load_persona_for_discovery使用了lru_cache缓存画像数据
                #       测试完成后，画像写入数据库，但缓存未清理，Agent看到旧数据
                # 解决：画像更新后清理缓存，下次查询时重新从数据库加载
                try:
                    from partner_search.personality_traits_reader import clear_traits_cache
                    clear_traits_cache()
                    _logger.info("【画像缓存清理】user_key=%s assessment_id=%s", user_key, assessment_id)
                except Exception as cache_error:
                    _logger.warning("【画像缓存清理失败】user_key=%s error=%s", user_key, cache_error)

                return {"card_type": "assessment_result", "assessment_type": ASSESSMENT_TYPE_BIG_FIVE, "assessment_id": assessment_id, "result_data": result_data}
            if answered_count > 0 and answered_count % QUESTIONS_PER_DIMENSION == 0:
                feedback_data = _feedback_payload(answered_count, scores)
                if feedback_data:
                    return {
                        "card_type": "assessment_feedback",
                        "assessment_id": assessment_id,
                        "feedback_data": feedback_data,
                        "next_question": _question_payload(answered_count, assessment_id),
                    }
            return {"card_type": "assessment_question", "assessment_id": assessment_id, "question_data": _question_payload(answered_count, assessment_id)}
    finally:
        release_persona_connection(normalized_source, conn)


def get_big_five_interpretation(*, source: str | None, assessment_id: str, user_key: str, observation_table: str = "user_persona_observations") -> dict[str, Any]:
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


def get_big_five_xiaoya_message(*, source: str | None, user_key: str, observation_table: str = "user_persona_observations") -> dict[str, Any]:
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
                (user_key, ASSESSMENT_XIAOYA_MESSAGE_FIELD, "big_five_%"),
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
