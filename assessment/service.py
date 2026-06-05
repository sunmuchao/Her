from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# 改用 OEJTS 适配器（集成权威开源项目）
from assessment.oejts_adapter_service import (
    build_intro_card,
    build_question_card,
    build_feedback_card,
    build_result_card,
    build_dimension_rows,
)
from assessment.oejts_engine import (
    TOTAL_QUESTIONS,
    DIMENSIONS,
    calculate_all_scores,
    get_dimension_feedback,
)
from assessment.love_style_generator import (
    get_type_info,
    get_extreme_tags,
    calculate_love_match,
    _type_code_from_scores as mbti_type_code,
    get_labels as mbti_labels,
    get_interpretation as mbti_interpretation,
    get_xiaoya_message as mbti_xiaoya_message,  # 重命名避免与下面函数冲突
)
from assessment.result_store import merge_personality_summary, store_assessment_result
from persona_memory_sync.persona_memory_lib import (
    fetch_persona,
    mysql_connect,
    parse_mysql_source,
    quote_mysql_ident,
    release_persona_connection,
)


ASSESSMENT_TYPE_MBTI = "mbti_16"
ASSESSMENT_SESSION_FIELD = "assessment.session"
ASSESSMENT_RESULT_FIELD = "assessment.result"
ASSESSMENT_INTERPRETATION_FIELD = "assessment.interpretation"
ASSESSMENT_XIAOYA_MESSAGE_FIELD = "assessment.xiaoya_message"


DIMENSION_LABELS = {
    "ei": "社交能量",
    "sn": "关注焦点",
    "tf": "决策方式",
    "jp": "生活节奏",
}

DIMENSION_TRAITS = {
    "ei": {"high": "社交达人", "medium": "灵活切换", "low": "独处爱好者"},
    "sn": {"high": "务实派", "medium": "事实与氛围并重", "low": "氛围感派"},
    "tf": {"high": "逻辑派", "medium": "道理与感受平衡", "low": "感受派"},
    "jp": {"high": "计划派", "medium": "计划弹性兼顾", "low": "随性派"},
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
    """使用 OEJTS 适配器构建题目数据"""
    return build_question_card(question_index, assessment_id)["question_data"]


def _feedback_payload(question_index: int, scores: dict[str, float]) -> dict[str, Any]:
    """使用 OEJTS 适配器构建反馈数据"""
    # 确定刚完成的维度（每12题一个维度）
    dimension_index = question_index // 12
    dimension = DIMENSIONS[dimension_index] if dimension_index < len(DIMENSIONS) else DIMENSIONS[-1]
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
    """使用题库模块的类型码计算"""
    return mbti_type_code(scores)


def _labels_from_scores(scores: dict[str, float]) -> list[str]:
    """使用题库模块的标签生成"""
    return mbti_labels(scores)


def _interpretation_from_result(result: dict[str, Any]) -> dict[str, Any]:
    """生成恋爱说明书式解读"""
    return mbti_interpretation(result)


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
    """创建新的测评会话

    注意：每次点击MBTI都会创建新的测评会话，
    用户可以从第1题重新开始。旧的测评数据保留在数据库中，
    但前端只显示当前最新的测评会话。
    """
    if assessment_type != ASSESSMENT_TYPE_MBTI:
        raise ValueError("unsupported assessment_type")
    normalized_source, _ = _resolve_source(source)
    assessment_id = f"mbti_{uuid.uuid4().hex[:12]}"
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            # 保存新的测评会话（不删除旧数据，避免卡顿）
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
            "title": "MBTI 恋爱测试",
            "description": "测测你在恋爱中是哪一型",
            "duration": "10-15分钟 · 48题",
            "reward": "性格匹配",
        },
    }


def get_or_create_assessment(
    *,
    source: str | None,
    user_key: str,
    assessment_type: str = ASSESSMENT_TYPE_MBTI,
    persona_table: str = "user_personas",
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """获取未完成的测评（断点续传），或者创建新测评

    防呆机制：用户退出App后，下次进来能接着上次的进度继续做，
    不会从第1题重新开始。

    Returns:
        - 如果有未完成的测评：返回 assessment_question，标记 resumed=True
        - 如果没有：返回 assessment_intro（新测评）
    """
    if assessment_type != ASSESSMENT_TYPE_MBTI:
        raise ValueError("unsupported assessment_type")

    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)

    try:
        with conn.cursor() as cursor:
            # 1. 查找用户最近的未完成测评
            cursor.execute(
                f"""
                SELECT conversation_ref, field_value, created_at
                FROM {quote_mysql_ident(observation_table)}
                WHERE user_key = %s
                  AND field_name = %s
                  AND source_channel = 'assessment'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_key, ASSESSMENT_SESSION_FIELD),
            )
            recent_session = cursor.fetchone()

            if recent_session:
                # 2. 解析session数据
                session_data = _parse_json(
                    recent_session.get("field_value") if isinstance(recent_session, dict) else recent_session[1]
                )
                assessment_id = str(
                    recent_session.get("conversation_ref") if isinstance(recent_session, dict) else recent_session[0]
                )

                # 3. 检查是否未完成
                if session_data.get("status") == "in_progress":
                    # 4. 加载已有的答案
                    session, answers, _result = _load_session_and_answers(
                        cursor,
                        observation_table=observation_table,
                        assessment_id=assessment_id,
                    )

                    # 5. 有进度且未完成，恢复进度
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
                            "resumed": True,  # 标记为恢复的测评
                            "answered_count": answered_count,
                        }

        # 6. 没有未完成的测评，创建新测评
        # 需要先释放连接，因为 start_assessment 会创建新连接
        release_persona_connection(normalized_source, conn)
        conn = None

        return start_assessment(
            source=source,
            user_key=user_key,
            assessment_type=assessment_type,
            persona_table=persona_table,
            observation_table=observation_table,
        )

    finally:
        if conn:
            release_persona_connection(normalized_source, conn)


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

            # 使用 OEJTS 题库
            from assessment.oejts_engine import get_question
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
                    "reward": "测完了解你的恋爱优势与雷区",
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
                # 新增：保存小雅解读消息（用于对话页面显示）
                # 使用恋爱风格生成器获取小雅消息
                xiaoya_msg_data = mbti_xiaoya_message(type_code, scores)
                xiaoya_message = xiaoya_msg_data.get("greeting", "") + "\n" + \
                                xiaoya_msg_data.get("identity", "") + "\n" + \
                                xiaoya_msg_data.get("quirk", "") + "\n" + \
                                xiaoya_msg_data.get("suggestion", "")
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
                    "scores": scores,
                    "completed_at": completed_at,
                }
                store_assessment_result(
                    source=normalized_source,
                    user_key=user_key,
                    assessment_id=assessment_id,
                    assessment_type=ASSESSMENT_TYPE_MBTI,
                    raw_result=result_data,
                    summary=traits_payload,
                    interpretation=interpretation,
                    completed_at=completed_at,
                    source_channel="assessment",
                )
                merge_personality_summary(
                    source=normalized_source,
                    user_key=user_key,
                    summary_key="mbti",
                    summary_payload=traits_payload,
                    persona_table=persona_table,
                    observation_table=observation_table,
                    evidence_text=f"用户完成 MBTI 16 型人格测评（{assessment_id}）",
                    conversation_ref=assessment_id,
                    source_channel="assessment",
                )
                conn.commit()
                return {
                    "card_type": "assessment_result",
                    "assessment_type": ASSESSMENT_TYPE_MBTI,  # 添加 assessment_type 字段，供前端识别测评类型
                    "assessment_id": assessment_id,
                    "result_data": result_data,
                }

            # 在维度结束时显示反馈（每12题一个维度）
            # EI: 1-12题, SN: 13-24题, TF: 25-36题, JP: 37-48题
            if answered_count in [12, 24, 36]:
                dimension_index = (answered_count // 12) - 1  # 刚完成的维度索引（0=EI, 1=SN, 2=TF）
                dimension = DIMENSIONS[dimension_index]
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


def get_xiaoya_message(
    *,
    source: str | None,
    user_key: str,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """获取小雅解读消息（用于在对话页面显示）

    返回：
    - 如果有未读的小雅消息，返回消息内容
    - 如果没有，返回空
    """
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            # 查找用户最近的小雅消息
            cursor.execute(
                f"""
                SELECT field_value, conversation_ref, created_at
                FROM {quote_mysql_ident(observation_table)}
                WHERE user_key = %s
                  AND field_name = %s
                  AND source_channel = 'assessment'
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


def add_xiaoya_message_to_discovery_session(
    *,
    discovery_source: str | None = None,
    discovery_service: Any | None = None,
    session_id: str,
    user_key: str,
    message: str,
    result_data: dict[str, Any] | None = None,
    assessment_type: str | None = None,  # 新增：支持多种测评类型
) -> dict[str, Any]:
    """将小雅消息添加到discovery session的对话历史

    这样消息会固定在对话流中，AI也能看到。

    Args:
        assessment_type: 测评类型，如 "mbti_16", "values_auction" 等
                        如果不提供，默认使用 MBTI 类型
    """
    from discovery_system.view_models import assistant_message, assessment_result
    if discovery_service is None:
        from discovery_system import create_default_discovery_service

        normalized_discovery_source, _ = _resolve_source(discovery_source)
        discovery_service = create_default_discovery_service(discovery_dsn=normalized_discovery_source)

    # 获取session
    session = discovery_service._require_session(session_id)

    # 确定测评类型
    actual_assessment_type = assessment_type or ASSESSMENT_TYPE_MBTI

    # 添加测评结果和小雅消息到 timeline，保证 UI 顺序和后续会话上下文一致
    item_id = discovery_service.storage.next_item_id("msg-a")
    now = datetime.now()
    timeline = list(session.view.get("timeline") or [])
    if result_data:
        # 构建结果卡片，保留原始的 card_type
        result_card = {
            "card_type": result_data.get("card_type", "assessment_result"),  # 使用原始卡片类型
            "assessment_type": actual_assessment_type,  # 添加 assessment_type 字段供前端识别
            "assessment_id": str(result_data.get("assessment_id") or ""),
            "result_data": result_data.get("result_data", result_data),  # 支持嵌套的 result_data
        }
        timeline.append(
            assessment_result(
                discovery_service.storage.next_item_id("assessment"),
                result_card,
                created_at=now,
            )
        )
    timeline.append(
        assistant_message(
            item_id,
            message,
            created_at=now,
        )
    )
    session.view["timeline"] = timeline

    # 保存session
    discovery_service.storage.save_session(session)

    return {
        "success": True,
        "message": "小雅消息已添加到对话历史",
        "item_id": item_id,
    }


def mark_xiaoya_message_read(
    *,
    source: str | None,
    user_key: str,
    assessment_id: str,
    observation_table: str = "user_persona_observations",
) -> dict[str, Any]:
    """标记小雅消息为已读"""
    normalized_source, _ = _resolve_source(source)
    conn = mysql_connect(normalized_source)
    try:
        with conn.cursor() as cursor:
            # 查找并更新消息
            cursor.execute(
                f"""
                SELECT id, field_value
                FROM {quote_mysql_ident(observation_table)}
                WHERE user_key = %s
                  AND conversation_ref = %s
                  AND field_name = %s
                LIMIT 1
                """,
                (user_key, assessment_id, ASSESSMENT_XIAOYA_MESSAGE_FIELD),
            )
            row = cursor.fetchone()
            if not row:
                return {"success": False, "message": "消息不存在"}

            data = _parse_json(row.get("field_value") if isinstance(row, dict) else row[1])
            data["read"] = True
            record_id = row.get("id") if isinstance(row, dict) else row[0]

            cursor.execute(
                f"""
                UPDATE {quote_mysql_ident(observation_table)}
                SET field_value = %s
                WHERE id = %s
                """,
                (_json(data), record_id),
            )
            conn.commit()
            return {"success": True}
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
                return {"mbti": {}, "attachment": {}, "big_five": {}, "sternberg": {}}
            traits = _parse_json(persona.get("self_personality_traits_json"))
            return {
                "mbti": traits.get("mbti") or {},
                "attachment": traits.get("attachment") or {},
                "big_five": traits.get("big_five") or {},
                "sternberg": traits.get("sternberg") or {},
            }
    finally:
        release_persona_connection(normalized_source, conn)
