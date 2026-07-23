"""Capability-oriented wrappers for discovery visual search."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from .photo_intent_agent import (
    PhotoPreferenceIntent,
    build_photo_recommendation_explanation,
    build_visual_search_plan,
)
from .visual_retrieval_orchestrator import execute_visual_candidate_retrieval

_VISUAL_REFERENCE_MARKERS = (
    "刚才那张",
    "上一张图",
    "上面那张图",
    "上述图片",
    "这张图",
    "那张图",
    "这种感觉",
    "这种风格",
    "按那张继续找",
    "照着刚才",
)
_VISUAL_SEARCH_REQUEST_MARKERS = (
    "按脸",
    "长得像",
    "像这张",
    "这种感觉",
    "这种风格",
    "参考人物",
    "明星",
)
_VISUAL_REFINEMENT_MARKERS = (
    "不要太",
    "一点",
    "换成",
    "改成",
    "换到",
    "改到",
    "继续找",
    "再找",
    "还是",
)
_VISUAL_STYLE_KEYWORDS = (
    "温柔",
    "成熟",
    "长发",
    "短发",
    "知性",
    "清冷",
    "甜美",
    "可爱",
    "高级",
    "自然",
    "干净",
    "气质",
    "酷",
    "少女",
)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_visual_context_payload(value: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(value or {})
    if payload.get("active_reference_image") is not None or payload.get("active_visual_intent") is not None:
        return payload
    active_reference = dict(payload.get("active_reference") or {})
    active_preference = dict(payload.get("active_preference") or {})
    active_constraints = dict(payload.get("active_constraints") or {})
    last_result = dict(payload.get("last_result") or {})
    return {
        "active_reference_image": {
            "source": active_reference.get("source"),
            "mime_type": active_reference.get("mime_type"),
            "role": active_reference.get("role"),
            "updated_at": active_reference.get("updated_at"),
        },
        "active_visual_intent": {
            "mode": active_preference.get("legacy_mode"),
            "intent_type": active_preference.get("intent_type"),
            "query_text": active_preference.get("query_text"),
            "raw_text": active_preference.get("raw_text"),
            "celebrity_name": active_preference.get("celebrity_name"),
            "updated_at": active_preference.get("updated_at"),
        },
        "active_constraints": active_constraints,
        "last_result_group_id": last_result.get("result_group_id"),
        "last_result_profile_ids": list(last_result.get("profile_ids") or []),
        "last_query_text": last_result.get("query_text"),
        "updated_at": payload.get("updated_at"),
    }


def _looks_like_city_name(value: str) -> bool:
    normalized = _normalize_text(value)
    if not normalized or len(normalized) > 8:
        return False
    return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z]{2,8}", normalized))


def _dedupe_text_list(values: Sequence[str], *, max_items: int) -> list[str]:
    items: list[str] = []
    for raw in values:
        text = _normalize_text(raw)
        if not text or text in items:
            continue
        items.append(text)
        if len(items) >= max_items:
            break
    return items


def analyze_visual_reference(
    *,
    text: str | None,
    image_source: str | None,
    visual_memory: Mapping[str, Any] | None = None,
    client_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return build_visual_search_plan(
        text=text,
        image_source=image_source,
        visual_context=_normalize_visual_context_payload(visual_memory),
        client_context=dict(client_context or {}),
    )


def retrieve_visual_candidates(
    *,
    source_dsn: str | None,
    requester_user_key: str,
    image_source: str | None = None,
    requester_profile_id: int | None = None,
    top_k: int = 20,
    intent: PhotoPreferenceIntent | None = None,
    visual_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return execute_visual_candidate_retrieval(
        source_dsn=source_dsn,
        requester_user_key=requester_user_key,
        image_source=image_source,
        requester_profile_id=requester_profile_id,
        top_k=top_k,
        intent=intent,
        visual_plan=visual_plan,
    )


def explain_visual_match(
    *,
    intent: PhotoPreferenceIntent,
    candidate_row: Mapping[str, Any] | None,
    matched_reasons: Sequence[str] | None = None,
) -> dict[str, Any]:
    return build_photo_recommendation_explanation(
        intent=intent,
        candidate_row=candidate_row,
        matched_reasons=matched_reasons,
    )


def looks_like_visual_reference_followup(text: str | None) -> bool:
    normalized = _normalize_text(text)
    return bool(normalized and any(marker in normalized for marker in _VISUAL_REFERENCE_MARKERS))


def looks_like_visual_refinement(text: str | None) -> bool:
    normalized = _normalize_text(text)
    return bool(normalized and any(marker in normalized for marker in _VISUAL_REFINEMENT_MARKERS))


def looks_like_visual_search_request(text: str | None) -> bool:
    normalized = _normalize_text(text)
    return bool(normalized and any(marker in normalized for marker in _VISUAL_SEARCH_REQUEST_MARKERS))


def parse_visual_refinement_constraints(text: str | None) -> dict[str, Any]:
    normalized = _normalize_text(text)
    if not normalized:
        return {
            "attribute_filters": {},
            "hard_filters": {},
            "style_keywords": [],
            "appearance_notes": [],
            "refinement_texts": [],
        }
    style_keywords = [keyword for keyword in _VISUAL_STYLE_KEYWORDS if keyword in normalized]
    appearance_notes = list(style_keywords)
    for item in re.findall(r"不要太([^\s，。,\\.；;]{1,8})", normalized):
        note = f"不要太{_normalize_text(item)}"
        if note and note not in appearance_notes:
            appearance_notes.append(note)
    city_match = re.search(r"(?:换成|改成|换到|改到)([\u4e00-\u9fffA-Za-z]{2,8})(?:的)?", normalized)
    city = _normalize_text(city_match.group(1)) if city_match else ""
    hard_filters: dict[str, Any] = {}
    if _looks_like_city_name(city):
        hard_filters["cities"] = [city]
    return {
        "attribute_filters": {},
        "hard_filters": hard_filters,
        "style_keywords": _dedupe_text_list(style_keywords, max_items=8),
        "appearance_notes": _dedupe_text_list(appearance_notes, max_items=8),
        "refinement_texts": [normalized],
    }


def merge_visual_constraints(
    *,
    existing: Mapping[str, Any] | None,
    incoming_attribute_filters: Mapping[str, Any] | None,
    incoming_hard_filters: Mapping[str, Any] | None,
    refinement: Mapping[str, Any] | None,
    updated_at: str,
) -> dict[str, Any]:
    current = dict(existing or {})
    merged_attribute_filters = dict(current.get("attribute_filters") or {})
    merged_attribute_filters.update(dict(incoming_attribute_filters or {}))
    merged_attribute_filters.update(dict((refinement or {}).get("attribute_filters") or {}))

    merged_hard_filters = dict(current.get("hard_filters") or {})
    merged_hard_filters.update(dict(incoming_hard_filters or {}))
    merged_hard_filters.update(dict((refinement or {}).get("hard_filters") or {}))

    return {
        "attribute_filters": merged_attribute_filters,
        "hard_filters": merged_hard_filters,
        "style_keywords": _dedupe_text_list(
            list(current.get("style_keywords") or []) + list((refinement or {}).get("style_keywords") or []),
            max_items=8,
        ),
        "appearance_notes": _dedupe_text_list(
            list(current.get("appearance_notes") or []) + list((refinement or {}).get("appearance_notes") or []),
            max_items=8,
        ),
        "refinement_texts": _dedupe_text_list(
            list(current.get("refinement_texts") or []) + list((refinement or {}).get("refinement_texts") or []),
            max_items=12,
        ),
        "updated_at": updated_at,
    }


__all__ = [
    "analyze_visual_reference",
    "explain_visual_match",
    "looks_like_visual_reference_followup",
    "looks_like_visual_refinement",
    "looks_like_visual_search_request",
    "merge_visual_constraints",
    "parse_visual_refinement_constraints",
    "retrieve_visual_candidates",
]
