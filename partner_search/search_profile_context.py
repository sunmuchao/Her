"""Request criteria and self-profile normalization for partner search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence


REQUEST_SEQUENCE_CRITERIA_ALIASES = {
    "cities": ("cities", "city"),
    "districts": ("districts", "district"),
    "settlement_cities": ("settlement_cities", "settlement_city"),
    "relationship_goals": ("relationship_goals", "relationship_goal"),
    "must_have": ("must_have",),
    "must_not_have": ("must_not_have", "must_not_have"),
    "prefer": ("prefer",),
    "housing_statuses": ("housing_statuses", "housing_status"),
    "car_statuses": ("car_statuses", "car_status"),
    "marital_statuses": ("marital_statuses", "marital_status"),
    "marriage_timelines": ("marriage_timelines", "marriage_timeline"),
    "profile_statuses": ("profile_statuses", "profile_status"),
    "verified_levels": ("verified_levels", "verified_level"),
    "photo_verification_levels": ("photo_verification_levels", "photo_verification_level"),
    "required_known_fields": ("required_known_fields", "require_known"),
}

REQUEST_SCALAR_CRITERIA_ALIASES = {
    "gender": ("gender",),
    "age_min": ("age_min",),
    "age_max": ("age_max",),
    "height_min": ("height_min",),
    "height_max": ("height_max",),
    "smoking": ("smoking",),
    "drinking": ("drinking",),
    "long_distance": ("long_distance",),
    "want_children": ("want_children",),
    "accept_partner_children": ("accept_partner_children",),
    "accept_marital_status_strength": ("accept_marital_status_strength",),
    "accept_partner_children_strength": ("accept_partner_children_strength",),
    "active_within_days": ("active_within_days",),
    "verified_level_min": ("verified_level_min",),
    "photo_verification_level_min": ("photo_verification_level_min",),
    "photo_count_min": ("photo_count_min",),
    "has_children": ("has_children",),
}


@dataclass(frozen=True)
class SearchProfileContextRuntime:
    as_int: Callable[[Any], int | None]
    as_lower: Callable[[Any], str]
    as_text: Callable[[Any], str]
    normalize_bool: Callable[[Any], bool | None]
    merge_keyword_args: Callable[[Any], list[str]]
    merge_keyword_values: Callable[[Any], list[str]]
    split_must_have_keywords: Callable[[Any], tuple[list[str], list[str]]]
    unique_ordered: Callable[[Any], list[Any]]
    first_defined: Callable[[Mapping[str, Any], Sequence[str]], Any]
    alias_lookup: Mapping[str, str]
    normalize_key: Callable[[Any], str]
    normalize_record: Callable[[dict[str, Any]], dict[str, Any]]
    build_combined_text: Callable[[dict[str, Any]], str]
    strip_internal_fields: Callable[[dict[str, Any]], dict[str, Any]]
    parse_income_range_to_wan: Callable[[Any], tuple[int | None, int | None]]
    redact_source_ref: Callable[[Any], str]


def build_criteria_from_args(
    runtime: SearchProfileContextRuntime,
    args: Any,
) -> dict[str, Any]:
    criteria: dict[str, Any] = {}

    if args.gender:
        criteria["gender"] = str(args.gender).strip().lower()

    for key in ("age_min", "age_max", "height_min", "height_max"):
        value = getattr(args, key)
        if value is not None:
            criteria[key] = value

    cities = runtime.merge_keyword_args(args.city)
    if cities:
        criteria["cities"] = cities
    districts = runtime.merge_keyword_args(args.district)
    if districts:
        criteria["districts"] = districts
    settlement_cities = runtime.merge_keyword_args(args.settlement_city)
    if settlement_cities:
        criteria["settlement_cities"] = settlement_cities

    relationship_goals = runtime.merge_keyword_args(args.relationship_goal)
    if relationship_goals:
        criteria["relationship_goals"] = relationship_goals

    must_not_have = runtime.merge_keyword_args(args.must_not_have)
    if must_not_have:
        criteria["must_not_have"] = must_not_have

    must_have = runtime.merge_keyword_args(args.must_have)
    hard_must_have, soft_must_have = runtime.split_must_have_keywords(must_have)
    if hard_must_have:
        criteria["must_have"] = hard_must_have

    prefer = runtime.merge_keyword_args(args.prefer)
    if soft_must_have:
        prefer = runtime.unique_ordered(prefer + soft_must_have)
    if prefer:
        criteria["prefer"] = prefer

    if args.smoking:
        criteria["smoking"] = args.smoking
    if args.drinking:
        criteria["drinking"] = args.drinking
    if args.long_distance:
        criteria["long_distance"] = args.long_distance
    if args.housing_status:
        criteria["housing_statuses"] = runtime.merge_keyword_args(args.housing_status)
    if args.car_status:
        criteria["car_statuses"] = runtime.merge_keyword_args(args.car_status)
    if args.marital_status:
        criteria["marital_statuses"] = runtime.merge_keyword_args(args.marital_status)
    if args.has_children is not None:
        criteria["has_children"] = bool(args.has_children)
    if args.want_children:
        criteria["want_children"] = args.want_children
    if args.accept_partner_children:
        criteria["accept_partner_children"] = args.accept_partner_children
    accept_marital_status_strength = getattr(args, "accept_marital_status_strength", None)
    if accept_marital_status_strength:
        criteria["accept_marital_status_strength"] = accept_marital_status_strength
    accept_partner_children_strength = getattr(args, "accept_partner_children_strength", None)
    if accept_partner_children_strength:
        criteria["accept_partner_children_strength"] = accept_partner_children_strength
    if args.marriage_timeline:
        criteria["marriage_timelines"] = runtime.merge_keyword_args(args.marriage_timeline)
    criteria["profile_statuses"] = runtime.merge_keyword_args(args.profile_status) or ["active"]
    if args.active_within_days is not None:
        criteria["active_within_days"] = args.active_within_days
    if args.verified_level_min:
        criteria["verified_level_min"] = args.verified_level_min
    if args.verified_level:
        criteria["verified_levels"] = runtime.merge_keyword_args(args.verified_level)
    photo_verification_level_min = getattr(args, "photo_verification_level_min", None)
    if photo_verification_level_min:
        criteria["photo_verification_level_min"] = photo_verification_level_min
    photo_verification_level = getattr(args, "photo_verification_level", None)
    if photo_verification_level:
        criteria["photo_verification_levels"] = runtime.merge_keyword_args(photo_verification_level)
    if args.photo_count_min is not None:
        criteria["photo_count_min"] = args.photo_count_min
    required_known_fields = [
        runtime.alias_lookup.get(runtime.normalize_key(field), runtime.normalize_key(field))
        for field in runtime.merge_keyword_args(getattr(args, "require_known", None))
    ]
    if required_known_fields:
        criteria["required_known_fields"] = required_known_fields
    criteria["exclude_ids"] = {item for item in args.exclude_id or []}
    exclude_source_channels = runtime.merge_keyword_args(getattr(args, "exclude_source_channel", None))
    if exclude_source_channels:
        criteria["exclude_source_channels"] = {
            item for item in (runtime.as_lower(value) for value in exclude_source_channels) if item
        }

    return criteria


def normalize_request_criteria(
    runtime: SearchProfileContextRuntime,
    criteria: Mapping[str, Any] | None,
) -> dict[str, Any]:
    criteria = dict(criteria or {})
    normalized: dict[str, Any] = {}

    scalar_values = {}
    for target_key, aliases in REQUEST_SCALAR_CRITERIA_ALIASES.items():
        scalar_values[target_key] = runtime.first_defined(criteria, aliases)

    if scalar_values["gender"]:
        normalized["gender"] = runtime.as_text(scalar_values["gender"]).lower()

    for key in ("age_min", "age_max", "height_min", "height_max", "active_within_days", "photo_count_min"):
        value = runtime.as_int(scalar_values.get(key))
        if value is not None:
            normalized[key] = value

    for key in (
        "smoking",
        "drinking",
        "long_distance",
        "want_children",
        "accept_partner_children",
        "accept_marital_status_strength",
        "accept_partner_children_strength",
        "verified_level_min",
        "photo_verification_level_min",
    ):
        value = scalar_values.get(key)
        if value is not None and value != "":
            normalized[key] = value

    has_children = runtime.normalize_bool(scalar_values.get("has_children"))
    if has_children is not None:
        normalized["has_children"] = has_children

    for target_key, aliases in REQUEST_SEQUENCE_CRITERIA_ALIASES.items():
        values = runtime.merge_keyword_values(runtime.first_defined(criteria, aliases))
        if not values:
            continue
        if target_key == "required_known_fields":
            normalized[target_key] = [
                runtime.alias_lookup.get(runtime.normalize_key(field), runtime.normalize_key(field))
                for field in values
            ]
        else:
            normalized[target_key] = values

    must_have = normalized.pop("must_have", [])
    hard_must_have, soft_must_have = runtime.split_must_have_keywords(must_have)
    if hard_must_have:
        normalized["must_have"] = hard_must_have
    prefer = normalized.get("prefer", [])
    if soft_must_have:
        prefer = runtime.unique_ordered(prefer + soft_must_have)
    if prefer:
        normalized["prefer"] = prefer

    exclude_ids = runtime.first_defined(criteria, ("exclude_ids", "exclude_id"))
    if exclude_ids is None:
        normalized["exclude_ids"] = set()
    elif isinstance(exclude_ids, (list, tuple, set)):
        normalized["exclude_ids"] = {
            item for item in (runtime.as_int(value) for value in exclude_ids) if item is not None
        }
    else:
        exclude_id = runtime.as_int(exclude_ids)
        normalized["exclude_ids"] = {exclude_id} if exclude_id is not None else set()

    exclude_source_channels = runtime.first_defined(criteria, ("exclude_source_channels", "exclude_source_channel"))
    if exclude_source_channels is None:
        normalized["exclude_source_channels"] = set()
    elif isinstance(exclude_source_channels, (list, tuple, set)):
        normalized["exclude_source_channels"] = {
            item for item in (runtime.as_lower(value) for value in exclude_source_channels) if item
        }
    else:
        exclude_source_channel = runtime.as_lower(exclude_source_channels)
        normalized["exclude_source_channels"] = (
            {exclude_source_channel} if exclude_source_channel else set()
        )

    if not normalized.get("profile_statuses"):
        normalized["profile_statuses"] = ["active"]

    if "exclude_record_refs" in criteria and criteria["exclude_record_refs"] is not None:
        normalized["exclude_record_refs"] = set(criteria["exclude_record_refs"])

    if "self_profile" in criteria and criteria["self_profile"]:
        normalized["self_profile"] = normalize_self_profile_input(runtime, criteria["self_profile"])

    return normalized


def resolve_self_profile_record(
    runtime: SearchProfileContextRuntime,
    self_id: int,
    records: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    matched_records = [record for record in records if runtime.as_int(record.get("id")) == self_id]
    if not matched_records:
        raise ValueError(f"Could not find self profile id {self_id} in the selected source.")
    distinct_sources = runtime.unique_ordered(record.get("source_file") or "" for record in matched_records)
    if len(distinct_sources) > 1:
        readable_sources = [runtime.redact_source_ref(source) or "<unknown source>" for source in distinct_sources]
        raise ValueError(
            f"Self profile id {self_id} is ambiguous across multiple sources: "
            + ", ".join(readable_sources)
            + ". Narrow --source or use a unique id."
        )
    return matched_records[0]


def normalize_self_profile_input(
    runtime: SearchProfileContextRuntime,
    profile: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not profile:
        return None
    if not any(value is not None and value != "" for value in profile.values()):
        return None

    normalized = runtime.normalize_record(dict(profile))
    income_wan = runtime.as_int(normalized.get("income_wan"))
    if income_wan is not None:
        normalized["income_min_wan"] = income_wan
        normalized["income_max_wan"] = income_wan

    if normalized.get("income_min_wan") is None and normalized.get("income_max_wan") is None:
        income_min, income_max = runtime.parse_income_range_to_wan(normalized.get("income_range"))
        if income_min is not None:
            normalized["income_min_wan"] = income_min
        if income_max is not None:
            normalized["income_max_wan"] = income_max

    normalized["has_children"] = runtime.normalize_bool(normalized.get("has_children"))
    normalized["combined_text"] = runtime.build_combined_text(normalized)
    return normalized


def build_self_profile(
    runtime: SearchProfileContextRuntime,
    records: Sequence[Mapping[str, Any]],
    self_id: int | None = None,
    profile_input: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    profile: dict[str, Any] = {}

    if self_id is not None:
        matched = resolve_self_profile_record(runtime, self_id, records)
        profile.update(runtime.strip_internal_fields(dict(matched)))
        profile["source_file"] = matched.get("source_file") or ""
        income_min, income_max = runtime.parse_income_range_to_wan(matched.get("income_range"))
        profile["income_min_wan"] = income_min
        profile["income_max_wan"] = income_max

    normalized_input = normalize_self_profile_input(runtime, profile_input)
    if normalized_input:
        existing_source = profile.get("source_file") or ""
        profile.update(runtime.strip_internal_fields(normalized_input))
        if existing_source and not profile.get("source_file"):
            profile["source_file"] = existing_source

    if not profile:
        return None

    if self_id is not None:
        profile["id"] = self_id
    profile["has_children"] = runtime.normalize_bool(profile.get("has_children"))
    profile["combined_text"] = runtime.build_combined_text(profile)
    return profile


def build_self_profile_input_from_args(args: Any) -> dict[str, Any]:
    profile_input = {
        "age": args.self_age,
        "city": args.self_city,
        "height": args.self_height,
        "education": args.self_education,
        "job": getattr(args, "self_job", None),
        "marital_status": args.self_marital_status,
        "smoking": args.self_smoking,
        "drinking": args.self_drinking,
    }
    if args.self_income_wan is not None:
        profile_input["income_wan"] = args.self_income_wan
    if args.self_has_children is not None:
        profile_input["has_children"] = bool(args.self_has_children)
    return profile_input


def build_self_profile_from_args(
    runtime: SearchProfileContextRuntime,
    args: Any,
    records: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    return build_self_profile(
        runtime,
        records,
        self_id=args.self_id,
        profile_input=build_self_profile_input_from_args(args),
    )


__all__ = [
    "SearchProfileContextRuntime",
    "build_criteria_from_args",
    "build_self_profile",
    "build_self_profile_from_args",
    "build_self_profile_input_from_args",
    "normalize_request_criteria",
    "normalize_self_profile_input",
    "resolve_self_profile_record",
]
