"""Render-model helpers for the discovery page."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import os
from typing import Any


def _format_created_at(created_at: datetime | None) -> str | None:
    if created_at is None:
        return None
    return created_at.isoformat()


def assistant_message(
    item_id: str,
    body: str,
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "item_type": "assistant_message",
        "item_id": item_id,
        "body": body,
    }
    formatted = _format_created_at(created_at)
    if formatted is not None:
        item["created_at"] = formatted
    return item


def assessment_result(
    item_id: str,
    card: dict[str, Any],
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "item_type": "assessment_result",
        "item_id": item_id,
        "card": card,
    }
    formatted = _format_created_at(created_at)
    if formatted is not None:
        item["created_at"] = formatted
    return item


def assessment_suggest(
    item_id: str,
    card: dict[str, Any],
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """构建测评引导卡片。"""
    item: dict[str, Any] = {
        "item_type": "assessment_suggest",
        "item_id": item_id,
        "card": card,
    }
    formatted = _format_created_at(created_at)
    if formatted is not None:
        item["created_at"] = formatted
    return item


def user_message(
    item_id: str,
    body: str,
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "item_type": "user_message",
        "item_id": item_id,
        "body": body,
    }
    formatted = _format_created_at(created_at)
    if formatted is not None:
        item["created_at"] = formatted
    return item


def result_group(item_id: str, title: str, cards: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "item_type": "result_group",
        "item_id": item_id,
        "title": title,
        "cards": cards,
    }


def criteria_chip(chip_id: str, label: str) -> dict[str, Any]:
    return {
        "chip_id": chip_id,
        "label": label,
    }


def suggested_action(
    action_id: str,
    label: str,
    style: str = "secondary",
    semantic_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "action_id": action_id,
        "label": label,
        "style": style,
    }
    if semantic_payload:
        result["semantic_payload"] = semantic_payload
    return result


def composer(placeholder: str, disabled: bool = False) -> dict[str, Any]:
    return {
        "placeholder": placeholder,
        "disabled": disabled,
    }


def clone_view(view: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(view)


def _personality_card_badges_enabled() -> bool:
    raw = str(os.environ.get("HER_DISCOVERY_PERSONALITY_CARD_BADGES_ENABLED") or "").strip().lower()
    if not raw:
        return True
    return raw not in {"0", "false", "off", "no"}


def build_candidate_card(candidate: dict[str, Any], *, reason_summary: str = "") -> dict[str, Any]:
    """构建候选人卡片

    改进：添加字段验证，确保字段符合规范

    Args:
        candidate: 候选人数据字典
        reason_summary: 推荐理由（可选）

    Returns:
        候选人卡片字典

    字段规范参考：
    docs/field_spec.md
    """
    profile = dict(candidate.get("profile") or {})
    profile_id = int(candidate.get("id") or 0)
    name = str(candidate.get("name") or "未命名")
    age = profile.get("age")
    city = profile.get("city")
    job = profile.get("job")
    education = profile.get("education")
    title_parts = [name]
    if age not in (None, ""):
        title_parts.append(str(age))
    subtitle_parts = [str(part).strip() for part in (city, job, education) if str(part or "").strip()]
    photo_preview = list(candidate.get("photo_preview") or [])

    # === Phase 1: 构建候选人卡片 ===
    # ✅ 修复：将整数score转换为0-1范围的match_score
    # 搜索算法返回整数score（如118），前端期望浮点数match_score（0-1范围）
    # 假设最大分数是200（基于搜索算法的累加项：每项2-20分，最多10-15个维度）
    raw_score = candidate.get("score") or candidate.get("fit_score") or 0
    max_score = 200  # 搜索算法的最大可能分数
    # 转换为0-1范围，并clamp到合理范围
    match_score = min(1.0, max(0.0, raw_score / max_score))

    card: dict[str, Any] = {
        "card_id": f"candidate-{profile_id}",
        "profile_id": profile_id,
        "title": " ".join(title_parts).strip(),
        "subtitle": " · ".join(subtitle_parts),
        "cover_image_url": photo_preview[0] if photo_preview else None,
        "match_score": match_score,  # ✅ 使用转换后的match_score
        "trust_badges": _build_trust_badges(candidate),
        "reason_summary": reason_summary or _default_reason_summary(candidate),
        "match_highlights": _build_match_highlights(candidate, reason_summary=reason_summary),
        "personality_reasoning": deepcopy(candidate.get("personality_reasoning") or {}),
        "personality_bonus": candidate.get("personality_bonus"),
        "base_score": candidate.get("base_score"),
        "personality_scoring_trace": deepcopy(candidate.get("personality_scoring_trace") or {}),
        "open_profile_action": {
            "type": "open_profile",
            "profile_id": profile_id,
        },
    }

    # === Phase 2: 注入 personality_traits（如果存在）===
    personality_traits = candidate.get("personality_traits")
    if personality_traits and _personality_card_badges_enabled():
        card["personality_match_context"] = personality_traits
        availability = candidate.get("personality_availability") or personality_traits.get("availability")
        if availability:
            card["personality_availability"] = availability
    personality_reasons = list((candidate.get("personality_reasoning") or {}).get("reasons") or [])
    if personality_reasons:
        card["personality_reasons"] = personality_reasons[:3]

    # === Phase 3: 字段验证（新增）===
    from .field_validator import validate_candidate_card, log_validation_errors

    errors = validate_candidate_card(card)
    if errors:
        log_validation_errors(
            errors,
            context=f"构建候选人卡片: profile_id={profile_id}, name={name}"
        )

    return card


def _build_trust_badges(candidate: dict[str, Any]) -> list[str]:
    badges: list[str] = []
    for item in list(candidate.get("verification_items") or []):
        if item.get("status") == "verified":
            label = str(item.get("label") or "").strip()
            if label and label not in badges:
                badges.append(label)
        if len(badges) >= 2:
            break
    if not badges:
        verified_label = str(candidate.get("verified_label") or "").strip()
        if verified_label:
            badges.append(verified_label)
    return badges


def _default_reason_summary(candidate: dict[str, Any]) -> str:
    personality_summary = str((candidate.get("personality_reasoning") or {}).get("summary") or "").strip()
    if personality_summary:
        return personality_summary
    matched_on = [str(item).strip() for item in list(candidate.get("matched_on") or []) if str(item or "").strip()]
    if matched_on:
        return "、".join(matched_on[:3])
    trust_headline = str((candidate.get("trust_summary") or {}).get("headline") or "").strip()
    if trust_headline:
        return trust_headline
    return "红娘建议你先看这位的整体资料。"


def _build_match_highlights(candidate: dict[str, Any], *, reason_summary: str = "") -> list[str]:
    highlights: list[str] = []

    for item in list(candidate.get("matched_on") or []):
        value = str(item or "").strip()
        if value and value not in highlights:
            highlights.append(value)
        if len(highlights) >= 3:
            break

    for item in list((candidate.get("personality_reasoning") or {}).get("reasons") or []):
        value = str(item or "").strip()
        if value and value not in highlights:
            highlights.append(value)
        if len(highlights) >= 4:
            break

    summary = str(reason_summary or "").strip() or str((candidate.get("personality_reasoning") or {}).get("summary") or "").strip()
    if not highlights and summary:
        highlights.append(summary)

    return highlights[:4]


def build_profile_detail_view_from_payload(
    candidate: dict[str, Any],
    *,
    matchmaker_notes: list[str] | None = None,
) -> dict[str, Any]:
    profile = dict(candidate.get("profile") or {})
    name = str(candidate.get("name") or profile.get("name") or "未命名")
    return {
        "hero": {
            "name": name,
            "age": profile.get("age"),
            "city": profile.get("city"),
            "headline": _build_detail_headline(profile),
        },
        "photo_gallery": _build_photo_gallery(candidate, profile),
        "verified_sections": _build_verified_sections(candidate),
        "self_reported_sections": _build_self_reported_sections(candidate),
        "caution_sections": _build_caution_sections(candidate),
        "matchmaker_notes": _build_matchmaker_notes(candidate, matchmaker_notes=matchmaker_notes),
    }


def _build_detail_headline(profile: dict[str, Any]) -> str:
    parts = [
        str(item).strip()
        for item in (
            profile.get("job"),
            profile.get("education"),
            profile.get("relationship_goal"),
        )
        if str(item or "").strip()
    ]
    if parts:
        return " · ".join(parts[:3])
    if str(profile.get("settlement_city") or "").strip():
        return f"长期定居 {str(profile.get('settlement_city')).strip()}"
    return "先看整体资料，再决定要不要继续聊。"


def _build_photo_gallery(candidate: dict[str, Any], profile: dict[str, Any]) -> list[dict[str, Any]]:
    photo_urls: list[str] = []
    for value in list(candidate.get("photo_preview") or []) + [profile.get("avatar_url")]:
        url = str(value or "").strip()
        if url and url not in photo_urls:
            photo_urls.append(url)
    return [{"image_url": url} for url in photo_urls]


def _build_verified_sections(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    verified_items = [
        _format_verification_item(item)
        for item in list(candidate.get("verification_items") or [])
        if item.get("status") == "verified"
    ]
    if not verified_items:
        return []
    return [{"title": "已核验信息", "items": verified_items}]


def _build_self_reported_sections(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    profile = dict(candidate.get("profile") or {})
    sections: list[dict[str, Any]] = []
    notes_summary = str(candidate.get("notes_summary") or "").strip()
    if notes_summary:
        sections.append(
            {
                "title": _intro_section_title(profile),
                "items": [notes_summary],
            }
        )

    basics: list[str] = []
    for value in (
        _detail_line("身高", _format_height(profile.get("height"))),
        _detail_line("长期定居", profile.get("settlement_city")),
        _detail_line("老家", profile.get("hometown")),
        _detail_line("婚况", profile.get("marital_status")),
        _detail_line("子女情况", _format_children(profile)),
        _detail_line("收入", _format_income(profile)),
        _detail_line("抽烟", profile.get("smoking")),
        _detail_line("喝酒", profile.get("drinking")),
        _detail_line("兴趣", profile.get("hobbies")),
    ):
        if value:
            basics.append(value)
    if basics:
        sections.append(
            {
                "title": "资料要点",
                "items": basics,
            }
        )
    return sections


def _build_caution_sections(candidate: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    caution_items = _clean_text_list(candidate.get("caution_items"))
    if caution_items:
        sections.append(
            {
                "title": "你需要知道",
                "items": caution_items,
            }
        )
    trust_actions = _clean_text_list(candidate.get("trust_actions"))
    if trust_actions:
        sections.append(
            {
                "title": "建议先确认",
                "items": trust_actions,
            }
        )
    return sections


def _build_matchmaker_notes(
    candidate: dict[str, Any],
    *,
    matchmaker_notes: list[str] | None = None,
) -> list[str]:
    explicit_notes = _clean_text_list(matchmaker_notes)
    if explicit_notes:
        return explicit_notes

    matched_on = _clean_text_list(candidate.get("matched_on"))
    if matched_on:
        return [f"红娘这一轮主要看中：{'、'.join(matched_on[:3])}。"]

    trust_headline = str((candidate.get("trust_summary") or {}).get("headline") or "").strip()
    if trust_headline:
        return [trust_headline]
    return []


def _intro_section_title(profile: dict[str, Any]) -> str:
    gender = str(profile.get("gender") or "").strip()
    if gender == "男":
        return "他的自我介绍"
    if gender == "女":
        return "她的自我介绍"
    return "TA的自我介绍"


def _format_verification_item(item: dict[str, Any]) -> str:
    summary = str(item.get("summary") or "").strip()
    if summary:
        return summary
    return str(item.get("label") or "").strip()


def _detail_line(label: str, value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return f"{label}：{text}"


def _format_height(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return f"{value}cm"


def _format_children(profile: dict[str, Any]) -> str | None:
    has_children = profile.get("has_children")
    if has_children in (0, False, "0"):
        return "未育"
    if has_children in (1, True, "1"):
        count = profile.get("children_count")
        if count not in (None, ""):
            return f"已育 {count} 个"
        return "已育"
    return None


def _format_income(profile: dict[str, Any]) -> str | None:
    for value in (
        profile.get("income_range"),
        profile.get("income"),
    ):
        text = str(value or "").strip()
        if text:
            return text
    income_min = profile.get("income_min_wan")
    income_max = profile.get("income_max_wan")
    if income_min in (None, "") and income_max in (None, ""):
        return None
    if income_min in (None, ""):
        return f"{income_max}万/年"
    if income_max in (None, ""):
        return f"{income_min}万/年"
    if income_min == income_max:
        return f"{income_min}万/年"
    return f"{income_min}-{income_max}万/年"


def _clean_text_list(values: Any) -> list[str]:
    cleaned: list[str] = []
    for value in list(values or []):
        text = str(value or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned
