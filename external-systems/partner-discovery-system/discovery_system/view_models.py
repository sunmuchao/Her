"""Render-model helpers for the discovery page."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def assistant_message(item_id: str, body: str) -> dict[str, Any]:
    return {
        "item_type": "assistant_message",
        "item_id": item_id,
        "body": body,
    }


def user_message(item_id: str, body: str) -> dict[str, Any]:
    return {
        "item_type": "user_message",
        "item_id": item_id,
        "body": body,
    }


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


def suggested_action(action_id: str, label: str, style: str = "secondary") -> dict[str, Any]:
    return {
        "action_id": action_id,
        "label": label,
        "style": style,
    }


def composer(placeholder: str, disabled: bool = False) -> dict[str, Any]:
    return {
        "placeholder": placeholder,
        "disabled": disabled,
    }


def clone_view(view: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(view)


def build_candidate_card(candidate: dict[str, Any], *, reason_summary: str = "") -> dict[str, Any]:
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
    return {
        "card_id": f"candidate-{profile_id}",
        "profile_id": profile_id,
        "title": " ".join(title_parts).strip(),
        "subtitle": " · ".join(subtitle_parts),
        "cover_image_url": photo_preview[0] if photo_preview else None,
        "match_score": candidate.get("score") or candidate.get("fit_score"),
        "trust_badges": _build_trust_badges(candidate),
        "reason_summary": reason_summary or _default_reason_summary(candidate),
        "open_profile_action": {
            "type": "open_profile",
            "profile_id": profile_id,
        },
    }


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
    matched_on = [str(item).strip() for item in list(candidate.get("matched_on") or []) if str(item or "").strip()]
    if matched_on:
        return "、".join(matched_on[:3])
    trust_headline = str((candidate.get("trust_summary") or {}).get("headline") or "").strip()
    if trust_headline:
        return trust_headline
    return "红娘建议你先看这位的整体资料。"


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


def build_profile_detail_view(profile_id: int) -> dict[str, Any]:
    return {
        "hero": {
            "name": f"候选人 {profile_id}",
            "age": None,
            "city": "待接真实资料",
            "headline": "发现页资料详情骨架",
        },
        "photo_gallery": [],
        "verified_sections": [
            {
                "title": "已核验信息",
                "items": ["待接真实认证数据"],
            }
        ],
        "self_reported_sections": [
            {
                "title": "自我介绍",
                "items": ["待接真实资料正文"],
            }
        ],
        "caution_sections": [
            {
                "title": "你需要知道",
                "items": ["当前仍是 discovery 接入骨架，尚未接真实详情读模型。"],
            }
        ],
        "matchmaker_notes": [
            "这里预留给 GPT 红娘或后端读模型返回的承接说明。",
        ],
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
