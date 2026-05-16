"""Location-preference semantics helpers for persona-memory-sync."""

from __future__ import annotations

import re
from typing import Any, Iterable, List, Optional

from her_time_utils import clean_text

from .field_normalization import split_multi_value, unique_ordered


LOCATION_NUANCE_MARKERS = (
    "稳定留沪",
    "双城过渡",
    "异地",
    "长期异地",
    "短期异地",
    "近距离",
    "落地计划",
    "落地异地",
    "同城",
    "周边",
    "通勤",
    "落地",
)

LONG_DISTANCE_BLOCK_PATTERNS = (
    re.compile(r"(?:不接受|不考虑|不能接受|不想)[^，。；]{0,8}长期异地"),
    re.compile(r"长期[^，。；]{0,8}异地[^，。；]{0,8}(?:不接受|不考虑|不行|免谈)"),
    re.compile(r"长期不落地异地"),
)

REGIONAL_CITY_EXPANSIONS = {
    "江浙沪": ("上海", "苏州", "无锡", "南京", "杭州", "常州", "宁波"),
}

CITY_PREFERENCE_PATTERNS = (
    re.compile(
        r"(?P<phrase>(?P<cities>[\u4e00-\u9fff]{2,4}(?:或|/|、|和|及)[\u4e00-\u9fff]{2,4})(?:都可以|都可|均可|优先))"
    ),
    re.compile(r"(?P<phrase>(?P<city>[\u4e00-\u9fff]{2,4})优先)"),
    re.compile(r"(?P<phrase>(?P<city>[\u4e00-\u9fff]{2,4})(?:都可以|都可|均可))"),
)

CITY_TOKEN_BLOCKLIST = {
    "江浙沪",
    "异地",
    "长期",
    "短期",
    "原则",
    "关系",
    "现实",
    "正常",
    "推进",
    "沟通",
    "计划",
    "见面",
    "稳定",
    "留沪",
    "同城",
    "周边",
    "通勤",
    "落地",
}

CITY_TOKEN_BLOCK_SUBSTRINGS = {
    "范围",
    "地区",
    "城市",
    "周边",
}


def split_text_segments(value: Any) -> List[str]:
    text = clean_text(value)
    if not text:
        return []
    segments: List[str] = []
    for block in re.split(r"[。；;\n]+", text):
        for part in re.split(r"[，,]+", block):
            normalized = clean_text(part.strip("，,。；; "))
            if normalized:
                segments.append(normalized)
    return unique_ordered(segments)


def normalize_city_token(value: Any) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    if text.endswith("市") and len(text) >= 3:
        text = text[:-1]
    if not re.fullmatch(r"[\u4e00-\u9fff]{2,4}", text):
        return None
    if text in CITY_TOKEN_BLOCKLIST:
        return None
    if any(marker in text for marker in CITY_TOKEN_BLOCK_SUBSTRINGS):
        return None
    return text


def extract_city_preference_phrase_from_semantics(semantics_text: Any) -> Optional[str]:
    semantics = clean_text(semantics_text) or ""
    if not semantics:
        return None
    for segment in split_text_segments(semantics):
        for pattern in CITY_PREFERENCE_PATTERNS:
            match = pattern.search(segment)
            if not match:
                continue
            phrase = clean_text(match.group("phrase"))
            city_tokens = [
                normalize_city_token(token)
                for token in re.split(
                    r"(?:或|/|、|和|及)",
                    match.groupdict().get("cities") or match.groupdict().get("city") or "",
                )
            ]
            city_tokens = [token for token in city_tokens if token]
            if city_tokens:
                return phrase
    return None


def extract_region_preference_phrase_from_semantics(semantics_text: Any) -> Optional[str]:
    semantics = clean_text(semantics_text) or ""
    if not semantics:
        return None
    for segment in split_text_segments(semantics):
        for region in REGIONAL_CITY_EXPANSIONS:
            match = re.search(rf"({re.escape(region)}(?:范围内)?优先)", segment)
            if match:
                return clean_text(match.group(1))
    return None


def extract_city_candidates_from_semantics(*texts: Any) -> List[str]:
    candidates: List[str] = []
    for text in texts:
        phrase = extract_city_preference_phrase_from_semantics(text)
        if not phrase:
            continue
        city_part = re.sub(r"(?:都可以|都可|均可|优先)$", "", phrase)
        for token in re.split(r"(?:或|/|、|和|及)", city_part):
            normalized = normalize_city_token(token)
            if normalized:
                candidates.append(normalized)
    return unique_ordered(candidates)


def expand_regional_target_cities(target_cities: Any, *texts: Any) -> List[str]:
    cities = split_multi_value(target_cities)
    combined_text = " ".join(clean_text(text) or "" for text in texts)
    expanded = list(cities) + extract_city_candidates_from_semantics(*texts)
    for region, region_cities in REGIONAL_CITY_EXPANSIONS.items():
        if region in combined_text:
            expanded.extend(region_cities)
    return unique_ordered(expanded)


def infer_target_long_distance_value(explicit_value: Any, semantics_text: Any) -> Optional[str]:
    explicit = clean_text(explicit_value)
    semantics = clean_text(semantics_text) or ""
    if not semantics:
        return explicit

    allows_short_term = any(
        marker in semantics for marker in ("短期异地可了解", "短期通勤型距离", "短期通勤", "稳定留沪")
    )
    dual_city_transition = any(
        marker in semantics for marker in ("双城过渡", "近距离", "通勤", "见面成本不能太高")
    )
    long_term_cautious = "长期异地比较谨慎" in semantics
    blocks_long_term = any(pattern.search(semantics) for pattern in LONG_DISTANCE_BLOCK_PATTERNS)

    if explicit == "可协商":
        if long_term_cautious:
            return "短期通勤可了解，长期异地谨慎"
        if allows_short_term or dual_city_transition or blocks_long_term:
            return "近距离可推进，长期异地不接受"
    if explicit == "不接受":
        if allows_short_term and blocks_long_term:
            return "短期可了解，长期异地不接受"
        if (
            any(marker in semantics for marker in ("近距离", "见面成本不能太高", "稳定留沪"))
            or (
                "落地计划" in semantics
                and any(marker in semantics for marker in ("可以沟通", "可沟通", "可了解", "能看"))
            )
        ) and "明确不接受长期异地" not in semantics:
            return "近距离可推进，长期异地不接受"
        if dual_city_transition and blocks_long_term and "短期过渡" not in semantics:
            return "近距离可推进，长期异地不接受"
    return explicit


def canonicalize_long_distance_state(value: Any) -> Optional[str]:
    text = clean_text(value)
    if not text:
        return None
    if text in {"接受", "不接受", "可协商", "未知"}:
        return text

    if "短期通勤" in text or ("通勤" in text and "谨慎" in text):
        return "短期通勤可了解，长期异地谨慎"
    if "短期可了解" in text and any(pattern.search(text) for pattern in LONG_DISTANCE_BLOCK_PATTERNS):
        return "短期可了解，长期异地不接受"
    if any(
        marker in text
        for marker in ("近距离", "双城过渡", "稳定留沪", "见面成本不能太高")
    ) and (
        any(pattern.search(text) for pattern in LONG_DISTANCE_BLOCK_PATTERNS)
        or "不接受远距离异地" in text
        or "长期异地不接受" in text
    ):
        return "近距离可推进，长期异地不接受"
    if "长期异地比较谨慎" in text:
        return "短期通勤可了解，长期异地谨慎"

    has_transition_allowance = any(
        marker in text
        for marker in (
            "短期异地",
            "短期通勤",
            "短期可了解",
            "短期过渡",
            "通勤型距离",
            "近距离",
            "落地计划",
            "双城过渡",
            "稳定留沪",
        )
    )
    if has_transition_allowance or "谨慎" in text:
        return "可协商"
    if "不接受异地" in text or any(pattern.search(text) for pattern in LONG_DISTANCE_BLOCK_PATTERNS):
        return "不接受"
    if "接受" in text:
        return "接受"
    return text


def build_public_city_preference_phrase(known_cities: Iterable[str], semantics_text: Any) -> Optional[str]:
    semantic_phrase = extract_city_preference_phrase_from_semantics(semantics_text)
    region_phrase = extract_region_preference_phrase_from_semantics(semantics_text)
    cities = [city for city in known_cities if clean_text(city)]
    semantics = clean_text(semantics_text) or ""

    base_phrase: Optional[str] = None
    if semantic_phrase:
        base_phrase = semantic_phrase
    elif region_phrase:
        base_phrase = region_phrase
    elif cities:
        if len(cities) == 1:
            base_phrase = f"{cities[0]}优先"
        elif len(cities) == 2:
            suffix = "都可以" if "都可以" in semantics else "优先"
            base_phrase = f"{cities[0]}或{cities[1]}{suffix}"
        else:
            base_phrase = "、".join(cities[:3]) + "优先"

    suffixes: List[str] = []
    if "稳定留沪" in semantics:
        suffixes.append("也接受明确留沪")
    if "双城过渡" in semantics:
        if "见面成本" in semantics:
            suffixes.append("也接受低成本双城过渡")
        else:
            suffixes.append("也接受双城过渡")

    if not base_phrase:
        if suffixes:
            return "，".join(unique_ordered(suffixes))
        return None

    for suffix in unique_ordered(suffixes):
        if suffix not in base_phrase:
            base_phrase += f"，{suffix}"
    return base_phrase


def contains_any_marker(texts: Iterable[Any], markers: Iterable[str]) -> bool:
    normalized_texts = [clean_text(text) or "" for text in texts]
    return any(marker in text for text in normalized_texts for marker in markers)


def has_location_signal(segment: Any, known_cities: Optional[Iterable[str]] = None) -> bool:
    text = clean_text(segment) or ""
    if not text:
        return False
    if extract_city_preference_phrase_from_semantics(text):
        return True
    if extract_region_preference_phrase_from_semantics(text):
        return True
    cities = [city for city in (known_cities or []) if clean_text(city)]
    if any(city in text for city in cities):
        return True
    return any(marker in text for marker in LOCATION_NUANCE_MARKERS)


def extract_location_semantics(
    *texts: Any,
    known_cities: Optional[Iterable[str]] = None,
) -> Optional[str]:
    segments: List[str] = []
    for text in texts:
        for segment in split_text_segments(text):
            if has_location_signal(segment, known_cities=known_cities):
                segments.append(segment)
    unique_segments = unique_ordered(segments)
    return "；".join(unique_segments) if unique_segments else None


def build_public_location_note(persona: dict[str, Any]) -> Optional[str]:
    known_cities = split_multi_value(persona.get("target_cities"))
    explicit_distance_value = clean_text(persona.get("target_accept_long_distance"))
    semantics = "；".join(
        unique_ordered(
            [
                item
                for item in (
                    clean_text(persona.get("target_location_semantics")),
                    extract_location_semantics(
                        persona.get("public_preference_summary_draft"),
                        persona.get("preference_summary_internal"),
                        known_cities=known_cities,
                    ),
                )
                if item
            ]
        )
    )
    explicit_distance_boundary = clean_text(persona.get("target_accept_long_distance")) == "不接受"
    has_landing_plan = any(marker in semantics for marker in ("落地计划", "稳定留沪", "双城过渡", "落地"))
    allows_short_term = "短期异地" in semantics
    blocks_long_term = any(pattern.search(semantics) for pattern in LONG_DISTANCE_BLOCK_PATTERNS)
    explicit_boundary_from_text = "不接受异地" in semantics or blocks_long_term
    needs_real_world_meetup = any(
        marker in semantics for marker in ("正常见面", "推进关系", "见面成本不能太高", "见面成本")
    )

    if explicit_distance_value in {
        "短期通勤可了解，长期异地谨慎",
        "短期可了解，长期异地不接受",
        "近距离可推进，长期异地不接受",
    }:
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        if city_note and city_note not in explicit_distance_value:
            return f"{city_note}；{explicit_distance_value}"
        return explicit_distance_value
    if blocks_long_term and (allows_short_term or has_landing_plan):
        note = (
            "明确不接受长期异地；如有短期过渡，需明确落地计划"
            if explicit_distance_boundary
            else "短期异地可了解，但需要明确落地计划；不接受长期异地"
        )
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if explicit_boundary_from_text and needs_real_world_meetup:
        note = "原则上不接受异地；需能正常见面并推进关系"
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if blocks_long_term:
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        note = "不接受长期异地"
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if has_landing_plan and "异地" in semantics:
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        note = "异地需有明确落地计划"
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if explicit_boundary_from_text:
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        note = "原则上不接受异地"
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if explicit_distance_boundary:
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        note = "更适合同城或近距离认真相处"
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    if any(marker in semantics for marker in ("同城", "近距离", "周边", "通勤")):
        city_note = build_public_city_preference_phrase(known_cities, semantics)
        note = "更适合同城或近距离认真相处"
        if city_note and city_note not in note:
            return f"{city_note}；{note}"
        return note
    return None


__all__ = [
    "LOCATION_NUANCE_MARKERS",
    "build_public_location_note",
    "canonicalize_long_distance_state",
    "contains_any_marker",
    "expand_regional_target_cities",
    "extract_location_semantics",
    "has_location_signal",
    "infer_target_long_distance_value",
    "split_text_segments",
]
