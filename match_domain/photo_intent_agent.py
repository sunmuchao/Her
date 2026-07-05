"""Photo preference intent parsing and explanation services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .appearance_features import build_match_explanation_payload
from .appearance_search import CelebrityReferenceGallery
from .photo_discovery_search import (
    search_celebrity_face_candidates,
    search_hybrid_photo_candidates,
    search_similar_face_candidates,
    search_style_candidates,
)


@dataclass(frozen=True)
class PhotoPreferenceIntent:
    intent_type: str
    mode: str
    query_text: str
    attribute_filters: dict[str, Any]
    hard_filters: dict[str, Any] = field(default_factory=dict)
    celebrity_name: str | None = None
    raw_text: str = ""
    confidence: float = 0.0
    routing_reasons: list[str] = field(default_factory=list)
    image_understanding: dict[str, Any] = field(default_factory=dict)


def _infer_image_understanding(
    *,
    text: str,
    image_source: str | None = None,
) -> dict[str, Any]:
    normalized = str(text or "").strip()
    lowered = normalized.lower()
    has_image = bool(str(image_source or "").strip())
    likely_reference_role = "text_only"
    if has_image and not normalized:
        likely_reference_role = "image_reference_unknown_goal"
    elif has_image and any(token in normalized for token in ("像这张脸", "五官", "脸型", "长相", "本人")):
        likely_reference_role = "face_reference"
    elif has_image and any(token in normalized for token in ("感觉", "风格", "气质", "穿搭", "氛围", "类型")):
        likely_reference_role = "style_reference"
    elif has_image:
        likely_reference_role = "image_reference_need_agent_judgement"
    text_signals = {
        "mentions_face": any(token in normalized for token in ("脸", "五官", "脸型", "长相")),
        "mentions_style": any(token in normalized for token in ("感觉", "风格", "气质", "氛围", "穿搭", "类型")),
        "mentions_celebrity": bool(CelebrityReferenceGallery.extract_name_candidates(normalized)),
        "mentions_comparison": any(token in lowered for token in ("像", "like", "similar")),
    }
    return {
        "has_image": has_image,
        "likely_reference_role": likely_reference_role,
        "text_signals": text_signals,
    }


def detect_photo_preference_intent(
    text: str,
    *,
    image_source: str | None = None,
) -> PhotoPreferenceIntent:
    normalized = str(text or "").strip()
    lowered = normalized.lower()
    attribute_filters: dict[str, Any] = {}
    query_parts: list[str] = []
    routing_reasons: list[str] = []
    image_understanding = _infer_image_understanding(text=normalized, image_source=image_source)
    has_image = bool(str(image_source or "").strip())

    if "阳光" in normalized or "sunny" in lowered:
        attribute_filters["sunny_score"] = {"min": 65}
        query_parts.append("阳光")
    if "清爽" in normalized or "clean" in lowered:
        attribute_filters["clean_score"] = {"min": 68}
        query_parts.append("清爽")
    if "成熟" in normalized or "mature" in lowered:
        attribute_filters["mature_score"] = {"min": 65}
        query_parts.append("成熟")
    if "温柔" in normalized or "gentle" in lowered:
        attribute_filters["gentle_score"] = {"min": 62}
        query_parts.append("温柔")
    if "幼态" in normalized or "可爱" in normalized:
        attribute_filters["youthfulness_score"] = {"min": 62}
        query_parts.append("幼态")
    if "眼睛大" in normalized:
        attribute_filters["eye_size_score"] = {"min": 68}
        query_parts.append("眼睛大")

    celebrity_candidates = CelebrityReferenceGallery.extract_name_candidates(normalized)
    celebrity_name = celebrity_candidates[0] if celebrity_candidates else None
    if celebrity_name:
        routing_reasons.append("text_contains_celebrity_reference")
    if any(token in normalized for token in ("像这张脸", "像这个人", "同款脸")):
        routing_reasons.append("text_explicitly_requests_face_match")
        return PhotoPreferenceIntent(
            intent_type="face_similarity_search",
            mode="face",
            query_text=normalized,
            attribute_filters=attribute_filters,
            hard_filters={},
            raw_text=normalized,
            confidence=0.96,
            routing_reasons=routing_reasons,
            image_understanding=image_understanding,
        )
    if celebrity_name and not has_image:
        return PhotoPreferenceIntent(
            intent_type="celebrity_face_search",
            mode="celebrity",
            query_text=celebrity_name,
            celebrity_name=celebrity_name,
            attribute_filters=attribute_filters,
            hard_filters={},
            raw_text=normalized,
            confidence=0.94,
            routing_reasons=routing_reasons,
            image_understanding=image_understanding,
        )
    if celebrity_name and has_image:
        routing_reasons.append("image_plus_celebrity_text_needs_hybrid_reference")
        return PhotoPreferenceIntent(
            intent_type="hybrid_photo_search",
            mode="hybrid",
            query_text=normalized or celebrity_name,
            celebrity_name=celebrity_name,
            attribute_filters=attribute_filters,
            hard_filters={},
            raw_text=normalized,
            confidence=0.86,
            routing_reasons=routing_reasons,
            image_understanding=image_understanding,
        )

    explicit_face_request = any(token in normalized for token in ("五官", "脸型", "长相", "像本人"))
    explicit_style_request = any(token in normalized for token in ("感觉", "风格", "气质", "氛围", "穿搭", "类型"))
    if explicit_face_request and not explicit_style_request:
        routing_reasons.append("text_emphasizes_face_features")
        return PhotoPreferenceIntent(
            intent_type="face_similarity_search",
            mode="face",
            query_text=normalized,
            attribute_filters=attribute_filters,
            hard_filters={},
            raw_text=normalized,
            confidence=0.88,
            routing_reasons=routing_reasons,
            image_understanding=image_understanding,
        )
    if has_image and (explicit_style_request or attribute_filters):
        routing_reasons.append("image_with_style_or_attribute_constraints")
        return PhotoPreferenceIntent(
            intent_type="style_similarity_search" if explicit_style_request else "hybrid_photo_search",
            mode="style" if explicit_style_request else "hybrid",
            query_text=" ".join(query_parts) or normalized or "自然 顺眼",
            attribute_filters=attribute_filters,
            hard_filters={},
            raw_text=normalized,
            confidence=0.78 if explicit_style_request else 0.7,
            routing_reasons=routing_reasons,
            image_understanding=image_understanding,
        )
    if has_image:
        routing_reasons.append("image_attached_without_explicit_mode_use_agent_auto_judgement")
        return PhotoPreferenceIntent(
            intent_type="hybrid_photo_search",
            mode="hybrid",
            query_text=normalized or "自动理解这张图",
            attribute_filters=attribute_filters,
            hard_filters={},
            raw_text=normalized,
            confidence=0.62,
            routing_reasons=routing_reasons,
            image_understanding=image_understanding,
        )
    routing_reasons.append("fallback_to_style_text_search")
    return PhotoPreferenceIntent(
        intent_type="style_similarity_search",
        mode="style",
        query_text=" ".join(query_parts) or normalized or "自然 顺眼",
        attribute_filters=attribute_filters,
        hard_filters={},
        raw_text=normalized,
        confidence=0.58 if normalized else 0.4,
        routing_reasons=routing_reasons,
        image_understanding=image_understanding,
    )


def translate_intent_to_search_plan(intent: PhotoPreferenceIntent) -> dict[str, Any]:
    payload = {
        "intent_type": intent.intent_type,
        "mode": intent.mode,
        "query_text": intent.query_text,
        "attribute_filters": dict(intent.attribute_filters),
        "hard_filters": dict(intent.hard_filters),
        "confidence": round(float(intent.confidence or 0.0), 4),
        "routing_reasons": list(intent.routing_reasons),
        "image_understanding": dict(intent.image_understanding),
    }
    if intent.celebrity_name:
        payload["celebrity_name"] = intent.celebrity_name
    if intent.mode == "style":
        payload["search_strategy"] = "appearance_vector_plus_tags"
    elif intent.mode == "celebrity":
        payload["search_strategy"] = "celebrity_reference_face"
    elif intent.mode == "hybrid":
        payload["search_strategy"] = "face_plus_style_hybrid"
    else:
        payload["search_strategy"] = "reference_face_similarity"
    return payload


def execute_photo_preference_search(
    *,
    source_dsn: str | None,
    requester_user_key: str,
    intent: PhotoPreferenceIntent,
    image_source: str | None = None,
    requester_profile_id: int | None = None,
    top_k: int = 20,
) -> dict[str, Any]:
    if intent.mode == "celebrity":
        return search_celebrity_face_candidates(
            source_dsn=source_dsn,
            celebrity_name=str(intent.celebrity_name or intent.query_text),
            requester_profile_id=requester_profile_id,
            top_k=top_k,
            attribute_filters=intent.attribute_filters,
        )
    if intent.mode == "hybrid":
        return search_hybrid_photo_candidates(
            source_dsn=source_dsn,
            requester_user_key=requester_user_key,
            image_source=str(image_source or "").strip() or intent.query_text,
            requester_profile_id=requester_profile_id,
            top_k=top_k,
            attribute_filters=intent.attribute_filters,
            query_text=intent.query_text,
        )
    if intent.mode == "face":
        return search_similar_face_candidates(
            source_dsn=source_dsn,
            requester_user_key=requester_user_key,
            image_source=str(image_source or "").strip() or intent.query_text,
            requester_profile_id=requester_profile_id,
            top_k=top_k,
            attribute_filters=intent.attribute_filters,
        )
    return search_style_candidates(
        source_dsn=source_dsn,
        image_source=str(image_source or "").strip() or intent.query_text,
        requester_profile_id=requester_profile_id,
        top_k=top_k,
        attribute_filters=intent.attribute_filters,
    )


def build_photo_recommendation_explanation_prompt(
    *,
    intent: PhotoPreferenceIntent,
    candidate_row: Mapping[str, Any] | None,
    matched_reasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    candidate = dict(candidate_row or {})
    appearance_summary = str(candidate.get("appearance_summary") or "").strip() or "暂无外貌摘要"
    candidate_name = str(
        candidate.get("display_name")
        or candidate.get("name")
        or candidate.get("nickname")
        or "候选人"
    ).strip() or "候选人"
    filter_hints = [
        f"{field_name}:{value}"
        for field_name, value in sorted(dict(intent.attribute_filters).items())
    ]
    hard_filter_hints = [
        f"{field_name}:{value}"
        for field_name, value in sorted(dict(intent.hard_filters).items())
    ]
    instructions = [
        "你是发现页的外貌解释助手。",
        "输出要自然、克制，不能直接断言对方真实长相，只能描述'更贴近用户偏好'。",
        "优先解释整体感觉，再解释具体命中点，最后再补充基础匹配理由。",
        "如果是明星参考，只能说'整体神态/氛围接近'，不能说'就是像本人'。",
    ]
    user_context = [
        f"用户意图模式: {intent.mode}",
        f"用户原始描述: {intent.raw_text or intent.query_text}",
        f"Agent 置信度: {round(float(intent.confidence or 0.0), 3)}",
        f"Agent 路由原因: {', '.join(intent.routing_reasons) or '无'}",
        f"外貌软条件: {', '.join(filter_hints) or '无'}",
        f"硬条件: {', '.join(hard_filter_hints) or '无'}",
        f"候选人: {candidate_name}",
        f"候选人外貌摘要: {appearance_summary}",
        f"基础匹配理由: {', '.join(str(item) for item in list(matched_reasons or [])) or '无'}",
    ]
    return {
        "system_prompt": "\n".join(instructions),
        "user_prompt": "\n".join(user_context),
        "prompt_version": "photo-explanation-v1",
        "facts": {
            "intent_mode": intent.mode,
            "intent_type": intent.intent_type,
            "candidate_name": candidate_name,
            "appearance_summary": appearance_summary,
            "attribute_filters": dict(intent.attribute_filters),
            "hard_filters": dict(intent.hard_filters),
            "confidence": round(float(intent.confidence or 0.0), 4),
            "routing_reasons": list(intent.routing_reasons),
            "image_understanding": dict(intent.image_understanding),
            "matched_reasons": list(matched_reasons or []),
        },
    }


def build_photo_recommendation_explanation(
    *,
    intent: PhotoPreferenceIntent,
    candidate_row: Mapping[str, Any] | None,
    matched_reasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    candidate = dict(candidate_row or {})
    prompt_payload = build_photo_recommendation_explanation_prompt(
        intent=intent,
        candidate_row=candidate,
        matched_reasons=matched_reasons,
    )
    appearance_summary = str(candidate.get("appearance_summary") or "").strip()
    highlights: list[str] = []
    if intent.celebrity_name:
        highlights.append(f"整体神态会让人联想到{intent.celebrity_name}")
    if appearance_summary:
        highlights.append(appearance_summary)
    for field_name in intent.attribute_filters:
        label = field_name.replace("_score", "")
        highlights.append(f"{label}方向更贴近你的描述")
    payload = build_match_explanation_payload(
        matched_on=list(matched_reasons or []),
        appearance_reasoning={
            "summary": (
                f"这位的长相风格更贴近你说的“{intent.query_text}”"
                if intent.mode != "celebrity"
                else f"这位的整体观感更接近你提到的{intent.celebrity_name}"
            ),
            "highlights": highlights,
        },
    )
    payload["intent_type"] = intent.intent_type
    payload["mode"] = intent.mode
    payload["prompt"] = prompt_payload
    return payload


__all__ = [
    "PhotoPreferenceIntent",
    "build_photo_recommendation_explanation_prompt",
    "build_photo_recommendation_explanation",
    "detect_photo_preference_intent",
    "execute_photo_preference_search",
    "translate_intent_to_search_plan",
]
