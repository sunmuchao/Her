"""Reciprocal preference matching helpers for partner search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class SearchReciprocalRuntime:
    as_int: Callable[[Any], int | None]
    as_lower: Callable[[Any], str]
    as_text: Callable[[Any], str]
    normalize_bool: Callable[[Any], bool | None]
    split_keywords: Callable[[Any], list[str]]
    parse_json_object: Callable[[Any], dict[str, Any]]
    unique_ordered: Callable[[Any], list[Any]]
    build_rejection_reason: Callable[[Any, Any], str]
    normalize_strictness_state: Callable[[Any], str]
    soft_preference_risk_flag: Callable[[str, str], str | None]
    reciprocal_city_preference_risk_flag: Callable[[str, str], str | None]
    normalize_acceptance_state: Callable[[Any], str]
    location_semantics_risk_flags: Callable[[dict[str, Any]], list[str]]
    education_rank: Callable[[Any], int | None]
    marital_status_match_options: Callable[[dict[str, Any]], list[str]]
    normalize_acceptance_strength: Callable[[Any], str]
    marital_acceptance_risk_flag: Callable[[str, str], str | None]
    children_acceptance_risk_flag: Callable[[str, str, str], str]
    habit_requires_acceptance: Callable[[Any], bool]


def exact_match(runtime: SearchReciprocalRuntime, value: Any, expected: Any) -> bool:
    return runtime.as_lower(value) == runtime.as_lower(expected)


def match_any_exact(runtime: SearchReciprocalRuntime, value: Any, candidates: list[Any]) -> bool:
    lowered = runtime.as_lower(value)
    return lowered in {runtime.as_lower(item) for item in candidates}


def income_range_overlaps(
    min_value: int | None,
    max_value: int | None,
    required_min: int | None,
    required_max: int | None,
) -> bool | None:
    if min_value is None and max_value is None:
        return None
    candidate_min = min_value if min_value is not None else max_value
    candidate_max = max_value if max_value is not None else min_value
    if required_min is not None and candidate_max is not None and candidate_max < required_min:
        return False
    if required_max is not None and candidate_min is not None and candidate_min > required_max:
        return False
    return True


def matcher_preference_tags(
    runtime: SearchReciprocalRuntime,
    record: dict[str, Any],
) -> list[str]:
    preferences = record.get("matcher_preferences")
    if not isinstance(preferences, dict):
        preferences = runtime.parse_json_object(record.get("matcher_preferences_json"))
    tags: list[str] = []
    for key in ("must_have_tags", "preferred_traits"):
        value = preferences.get(key)
        if isinstance(value, list):
            tags.extend(value)
        else:
            tags.extend(runtime.split_keywords(value))
    return list(runtime.unique_ordered(tags))


def evaluate_reciprocal_compatibility(
    runtime: SearchReciprocalRuntime,
    record: dict[str, Any],
    self_profile: dict[str, Any] | None,
    diagnostics: bool = False,
    reciprocal_mode: str = "strict",
) -> dict[str, Any] | None:
    from match_domain.reciprocal_preferences import enrich_record_for_reciprocal

    record = enrich_record_for_reciprocal(record)
    def fail(reason: str, detail: Any = None) -> dict[str, Any] | None:
        if not diagnostics:
            return None
        return {
            "matched": False,
            "matched_on": [],
            "missing_fields": [],
            "risk_flags": [],
            "score_bonus": 0,
            "reject_reason": runtime.build_rejection_reason(reason, detail),
        }

    if not self_profile:
        return {
            "matched": True,
            "matched_on": [],
            "missing_fields": [],
            "risk_flags": [],
            "score_bonus": 0,
            "reject_reason": None,
        }

    reasons: list[str] = []
    missing_fields: list[str] = []
    risk_flags: list[str] = []
    score_bonus = 0

    self_age = runtime.as_int(self_profile.get("age"))
    pref_age_min = runtime.as_int(record.get("preferred_age_min"))
    pref_age_max = runtime.as_int(record.get("preferred_age_max"))
    age_strictness = runtime.normalize_strictness_state(record.get("preferred_age_strictness"))
    if pref_age_min is not None or pref_age_max is not None:
        if self_age is None:
            missing_fields.append("self_age")
        elif pref_age_min is not None and self_age < pref_age_min:
            if age_strictness == "hard":
                return fail("reciprocal_age_preference")
            risk_flag = runtime.soft_preference_risk_flag("age", age_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        elif pref_age_max is not None and self_age > pref_age_max:
            if age_strictness == "hard":
                return fail("reciprocal_age_preference")
            risk_flag = runtime.soft_preference_risk_flag("age", age_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        else:
            reasons.append("对方年龄偏好命中")
            score_bonus += 10

    pref_cities = runtime.split_keywords(record.get("preferred_cities"))
    self_city = self_profile.get("city")
    if pref_cities:
        if not self_city:
            missing_fields.append("self_city")
        elif not match_any_exact(runtime, self_city, pref_cities):
            city_preference_risk = runtime.reciprocal_city_preference_risk_flag(
                runtime.normalize_acceptance_state(record.get("accept_long_distance")),
                reciprocal_mode,
            )
            if city_preference_risk:
                risk_flags.append(city_preference_risk)
                risk_flags.extend(runtime.location_semantics_risk_flags(record))
            else:
                return fail("reciprocal_city_preference")
        else:
            reasons.append("对方城市偏好命中")
            score_bonus += 10

    self_height = runtime.as_int(self_profile.get("height"))
    pref_height_min = runtime.as_int(record.get("preferred_height_min"))
    pref_height_max = runtime.as_int(record.get("preferred_height_max"))
    height_strictness = runtime.normalize_strictness_state(record.get("preferred_height_strictness"))
    if pref_height_min is not None or pref_height_max is not None:
        if self_height is None:
            missing_fields.append("self_height")
        elif pref_height_min is not None and self_height < pref_height_min:
            if height_strictness == "hard":
                return fail("reciprocal_height_preference")
            risk_flag = runtime.soft_preference_risk_flag("height", height_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        elif pref_height_max is not None and self_height > pref_height_max:
            if height_strictness == "hard":
                return fail("reciprocal_height_preference")
            risk_flag = runtime.soft_preference_risk_flag("height", height_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        else:
            reasons.append("对方身高偏好命中")
            score_bonus += 6

    pref_education_min = record.get("preferred_education_min")
    education_strictness = runtime.normalize_strictness_state(record.get("preferred_education_strictness"))
    if pref_education_min:
        self_education = self_profile.get("education")
        self_rank = runtime.education_rank(self_education)
        required_rank = runtime.education_rank(pref_education_min)
        if not self_education:
            missing_fields.append("self_education")
        elif self_rank is None or required_rank is None:
            if not exact_match(runtime, self_education, pref_education_min):
                if education_strictness == "hard":
                    return fail("reciprocal_education_preference")
                risk_flag = runtime.soft_preference_risk_flag("education", education_strictness)
                if risk_flag:
                    risk_flags.append(risk_flag)
        elif self_rank < required_rank:
            if education_strictness == "hard":
                return fail("reciprocal_education_preference")
            risk_flag = runtime.soft_preference_risk_flag("education", education_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        else:
            reasons.append("对方学历偏好命中")
            score_bonus += 6

    pref_income_min = runtime.as_int(record.get("preferred_income_min_wan"))
    pref_income_max = runtime.as_int(record.get("preferred_income_max_wan"))
    income_strictness = runtime.normalize_strictness_state(record.get("preferred_income_strictness"))
    if pref_income_min is not None or pref_income_max is not None:
        self_income_min = runtime.as_int(self_profile.get("income_min_wan"))
        self_income_max = runtime.as_int(self_profile.get("income_max_wan"))
        overlap = income_range_overlaps(
            self_income_min,
            self_income_max,
            pref_income_min,
            pref_income_max,
        )
        if overlap is None:
            missing_fields.append("self_income_wan")
        elif overlap is False:
            if income_strictness == "hard":
                return fail("reciprocal_income_preference")
            risk_flag = runtime.soft_preference_risk_flag("income", income_strictness)
            if risk_flag:
                risk_flags.append(risk_flag)
        else:
            reasons.append("对方收入偏好命中")
            score_bonus += 6

    accepted_statuses = runtime.split_keywords(record.get("accept_marital_status"))
    accept_marital_status_semantics = runtime.as_text(record.get("accept_marital_status_semantics"))
    if accepted_statuses:
        self_status = self_profile.get("marital_status")
        if not self_status:
            missing_fields.append("self_marital_status")
        elif not any(
            match_any_exact(runtime, option, accepted_statuses)
            for option in runtime.marital_status_match_options(self_profile)
        ):
            return fail("reciprocal_marital_status_preference")
        else:
            reasons.append("对方可接受婚况命中")
            score_bonus += 8
            if runtime.as_lower(self_status) not in {"", "未婚"}:
                marital_strength = runtime.normalize_acceptance_strength(
                    record.get("accept_marital_status_strength")
                )
                if marital_strength == "strong":
                    score_bonus += 2
                else:
                    marital_risk = runtime.marital_acceptance_risk_flag(
                        marital_strength,
                        accept_marital_status_semantics,
                    )
                    if marital_risk:
                        risk_flags.append(marital_risk)
    else:
        self_status = self_profile.get("marital_status")
        if self_status and runtime.as_lower(self_status) not in {"", "未婚"}:
            missing_fields.append("accept_marital_status")

    self_has_children = runtime.normalize_bool(self_profile.get("has_children"))
    accept_partner_children = runtime.normalize_acceptance_state(record.get("accept_partner_children"))
    accept_partner_children_semantics = runtime.as_text(record.get("accept_partner_children_semantics"))
    if self_has_children is None:
        if accept_partner_children != "missing":
            missing_fields.append("self_has_children")
    elif self_has_children:
        if accept_partner_children == "rejected":
            return fail("reciprocal_children_acceptance")
        if accept_partner_children == "accepted":
            reasons.append("对方接受你有孩子")
            score_bonus += 8
            children_strength = runtime.normalize_acceptance_strength(
                record.get("accept_partner_children_strength")
            )
            if children_strength == "strong":
                score_bonus += 2
            else:
                children_risk = runtime.children_acceptance_risk_flag(
                    "accepted",
                    children_strength,
                    accept_partner_children_semantics,
                )
                if children_risk:
                    risk_flags.append(children_risk)
        elif accept_partner_children in {"negotiable", "guarded"}:
            risk_flags.append(
                runtime.children_acceptance_risk_flag(
                    accept_partner_children,
                    runtime.normalize_acceptance_strength(
                        record.get("accept_partner_children_strength")
                    ),
                    accept_partner_children_semantics,
                )
            )
        elif accept_partner_children == "unknown":
            if reciprocal_mode == "fallback":
                risk_flags.append("对方对子女接受度未知")
            else:
                return fail("reciprocal_children_acceptance_unknown")
        else:
            missing_fields.append("accept_partner_children")

    self_smoking = self_profile.get("smoking")
    accept_smoking = runtime.normalize_acceptance_state(record.get("accept_smoking"))
    if not self_smoking:
        if accept_smoking != "missing":
            missing_fields.append("self_smoking")
    elif runtime.habit_requires_acceptance(self_smoking):
        if accept_smoking == "rejected":
            return fail("reciprocal_smoking_acceptance")
        if accept_smoking == "accepted":
            reasons.append("对方接受你的抽烟习惯")
            score_bonus += 4
        elif accept_smoking == "negotiable":
            risk_flags.append("对方对抽烟仅可协商")
        elif accept_smoking == "unknown":
            risk_flags.append("对方对抽烟接受度未知")
        else:
            missing_fields.append("accept_smoking")

    self_drinking = self_profile.get("drinking")
    accept_drinking = runtime.normalize_acceptance_state(record.get("accept_drinking"))
    if not self_drinking:
        if accept_drinking != "missing":
            missing_fields.append("self_drinking")
    elif runtime.habit_requires_acceptance(self_drinking):
        if accept_drinking == "rejected":
            return fail("reciprocal_drinking_acceptance")
        if accept_drinking == "accepted":
            reasons.append("对方接受你的喝酒习惯")
            score_bonus += 4
        elif accept_drinking == "negotiable":
            risk_flags.append("对方对喝酒仅可协商")
        elif accept_drinking == "unknown":
            risk_flags.append("对方对喝酒接受度未知")
        else:
            missing_fields.append("accept_drinking")

    candidate_city = record.get("city")
    accept_long_distance = runtime.normalize_acceptance_state(record.get("accept_long_distance"))
    if self_city and candidate_city and runtime.as_lower(self_city) != runtime.as_lower(candidate_city):
        if accept_long_distance == "rejected":
            return fail("reciprocal_long_distance_acceptance")
        if accept_long_distance == "accepted":
            reasons.append("对方接受异地")
            score_bonus += 4
            risk_flags.extend(runtime.location_semantics_risk_flags(record))
        elif accept_long_distance == "negotiable":
            risk_flags.append("对方异地仅可协商")
            risk_flags.extend(runtime.location_semantics_risk_flags(record))
        elif accept_long_distance == "unknown":
            risk_flags.append("对方异地接受度未知")
            risk_flags.extend(runtime.location_semantics_risk_flags(record))
        else:
            missing_fields.append("accept_long_distance")

    soft_preference_tags = matcher_preference_tags(runtime, record)
    if soft_preference_tags:
        self_text = runtime.as_lower(self_profile.get("combined_text"))
        matched_soft_tags = [tag for tag in soft_preference_tags if runtime.as_lower(tag) in self_text]
        if matched_soft_tags:
            reasons.append("对方软性偏好有重合")
            score_bonus += min(4, len(matched_soft_tags) * 2)

    return {
        "matched": True,
        "matched_on": reasons,
        "missing_fields": missing_fields,
        "risk_flags": risk_flags,
        "score_bonus": score_bonus,
        "reject_reason": None,
    }


__all__ = [
    "SearchReciprocalRuntime",
    "evaluate_reciprocal_compatibility",
    "exact_match",
    "income_range_overlaps",
    "match_any_exact",
    "matcher_preference_tags",
]
