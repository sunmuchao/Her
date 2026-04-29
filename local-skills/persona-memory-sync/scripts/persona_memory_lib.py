#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qs, unquote, urlparse


MYSQL_SCHEMES = {"mysql", "mysql+pymysql"}
DEFAULT_SOURCE_ENV = "PERSONA_MEMORY_MYSQL_SOURCE"
DEFAULT_PROFILE_TABLE = "profiles"
DEFAULT_PERSONA_TABLE = "user_personas"
DEFAULT_OBSERVATION_TABLE = "user_persona_observations"
DEFAULT_PUBLIC_VIEW = "public_profile_view"

USER_PERSONA_FIELDS = {
    "profile_id",
    "display_name",
    "self_gender",
    "self_age",
    "self_city",
    "self_district",
    "self_height",
    "self_education",
    "self_income_wan",
    "self_job",
    "self_marital_status",
    "self_has_children",
    "self_smoking",
    "self_drinking",
    "self_relationship_goal",
    "target_gender",
    "target_age_min",
    "target_age_max",
    "target_cities",
    "target_height_min",
    "target_height_max",
    "target_education_min",
    "target_income_min_wan",
    "target_income_max_wan",
    "target_marital_statuses",
    "target_accept_partner_children",
    "target_accept_long_distance",
    "target_want_children",
    "target_marriage_timeline",
    "must_have_tags",
    "must_not_have_tags",
    "preferred_traits",
    "disliked_traits",
    "persona_summary_internal",
    "preference_summary_internal",
    "public_profile_summary_draft",
    "public_preference_summary_draft",
}

LIST_FIELDS = {
    "target_cities",
    "target_marital_statuses",
    "must_have_tags",
    "must_not_have_tags",
    "preferred_traits",
    "disliked_traits",
}

INT_FIELDS = {
    "profile_id",
    "self_age",
    "self_height",
    "self_income_wan",
    "target_age_min",
    "target_age_max",
    "target_height_min",
    "target_height_max",
    "target_income_min_wan",
    "target_income_max_wan",
}

BOOL_FIELDS = {
    "self_has_children",
}

EXPLICIT_ONLY_FIELDS = {
    "profile_id",
    "display_name",
    "self_gender",
    "self_age",
    "self_city",
    "self_district",
    "self_height",
    "self_education",
    "self_income_wan",
    "self_job",
    "self_marital_status",
    "self_has_children",
    "self_smoking",
    "self_drinking",
    "self_relationship_goal",
    "target_gender",
    "target_age_min",
    "target_age_max",
    "target_cities",
    "target_height_min",
    "target_height_max",
    "target_education_min",
    "target_income_min_wan",
    "target_income_max_wan",
    "target_marital_statuses",
    "target_accept_partner_children",
    "target_accept_long_distance",
    "target_want_children",
    "target_marriage_timeline",
}

INFERENCE_MUTABLE_LIST_FIELDS = {
    "must_have_tags",
    "must_not_have_tags",
    "preferred_traits",
    "disliked_traits",
}

STRONG_INFERENCE_MUTABLE_SCALARS = {
    "persona_summary_internal",
    "preference_summary_internal",
    "public_profile_summary_draft",
    "public_preference_summary_draft",
}

PERSONA_TO_PROFILE_FIELD_MAP = {
    "self_gender": "gender",
    "self_age": "age",
    "self_city": "city",
    "self_district": "district",
    "self_height": "height",
    "self_education": "education",
    "self_job": "job",
    "self_marital_status": "marital_status",
    "self_has_children": "has_children",
    "self_smoking": "smoking",
    "self_drinking": "drinking",
    "self_relationship_goal": "relationship_goal",
    "target_age_min": "preferred_age_min",
    "target_age_max": "preferred_age_max",
    "target_cities": "preferred_cities",
    "target_height_min": "preferred_height_min",
    "target_height_max": "preferred_height_max",
    "target_education_min": "preferred_education_min",
    "target_income_min_wan": "preferred_income_min_wan",
    "target_income_max_wan": "preferred_income_max_wan",
}

PROFILE_EXTENSION_COLUMNS = {
    "matcher_traits_json": "JSON NULL",
    "matcher_preferences_json": "JSON NULL",
    "matcher_risks_json": "JSON NULL",
    "matcher_summary_internal": "TEXT NULL",
    "public_personality": "TEXT NULL",
    "public_values": "TEXT NULL",
    "public_notes": "TEXT NULL",
}

PROFILE_SYNC_PERSONA_FIELDS = set(PERSONA_TO_PROFILE_FIELD_MAP) | {
    "display_name",
    "self_income_wan",
    "target_accept_long_distance",
    "target_accept_partner_children",
    "target_marital_statuses",
    "target_gender",
    "target_want_children",
    "target_marriage_timeline",
    "must_have_tags",
    "must_not_have_tags",
    "preferred_traits",
    "disliked_traits",
    "persona_summary_internal",
    "preference_summary_internal",
    "public_profile_summary_draft",
    "public_preference_summary_draft",
}

RAW_NEGATIVE_TO_MATCHER = {
    "绿茶": {
        "boundary_clarity_risk": "high",
        "multi_thread_ambiguity_risk": "high",
        "attention_seeking_tendency": "high",
    },
    "拜金": {
        "material_expectation_level": "high",
        "spending_values_mismatch_risk": "high",
    },
    "冷暴力": {
        "communication_shutdown_risk": "high",
        "conflict_repair_capacity": "low",
    },
    "暧昧不清": {
        "commitment_clarity": "low",
        "ambiguity_risk": "high",
    },
    "抽烟": {
        "partner_smoking_tolerance": "low",
    },
}

POSITIVE_TAG_TO_MATCHER = {
    "情绪稳定": {
        "emotional_stability_priority": "high",
    },
    "愿意沟通": {
        "communication_directness_preference": "high",
        "repair_orientation_priority": "high",
    },
    "沟通": {
        "communication_directness_preference": "high",
    },
    "消费观正常": {
        "spending_values_alignment_priority": "high",
    },
    "同城": {
        "same_city_priority": "high",
    },
}

PUBLIC_SAFE_NEGATIVE_NOTES = {
    "暧昧不清": "不喜欢长期拉扯型相处",
    "冷暴力": "希望沟通方式更稳定直接",
    "绿茶": "关系边界希望更清晰",
    "拜金": "消费观需要更加一致",
    "抽烟": "对生活方式和习惯有较明确要求",
}

PUBLIC_SAFE_TAG_MAP = {
    "愿意沟通": "沟通顺畅",
    "沟通": "沟通顺畅",
    "消费观正常": "消费观一致",
}


def resolve_mysql_source(source: Optional[str] = None) -> str:
    resolved = source or os.environ.get(DEFAULT_SOURCE_ENV)
    if resolved:
        return resolved
    raise ValueError(
        "No MySQL source configured. Pass --source mysql://user:pass@host:3306/db?table=profiles "
        f"or set {DEFAULT_SOURCE_ENV}."
    )


def parse_mysql_source(source: Optional[str] = None) -> Dict[str, Any]:
    source = resolve_mysql_source(source)
    parsed = urlparse(str(source))
    if parsed.scheme.lower() not in MYSQL_SCHEMES:
        raise ValueError(f"Unsupported MySQL source: {source}")

    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise ValueError("MySQL source must include a database name.")

    query = parse_qs(parsed.query)
    return {
        "source": source,
        "host": parsed.hostname or "127.0.0.1",
        "port": parsed.port or 3306,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "database": database,
        "table": query.get("table", [DEFAULT_PROFILE_TABLE])[0],
        "charset": query.get("charset", ["utf8mb4"])[0],
    }


def mysql_connect(source: Optional[str] = None):
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ValueError("PyMySQL is required. Install it with `python3 -m pip install pymysql`.") from exc

    config = parse_mysql_source(source)
    kwargs = {
        "host": config["host"],
        "port": config["port"],
        "database": config["database"],
        "charset": config["charset"],
        "cursorclass": pymysql.cursors.DictCursor,
    }
    if config["user"] is not None:
        kwargs["user"] = config["user"]
    if config["password"] is not None:
        kwargs["password"] = config["password"]
    return pymysql.connect(**kwargs)


def quote_mysql_ident(identifier: str) -> str:
    return "`" + str(identifier).replace("`", "``") + "`"


def persona_field_affects_profile(field_name: str) -> bool:
    return field_name in PROFILE_SYNC_PERSONA_FIELDS


def now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def as_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    match = re.search(r"-?\d+", str(value))
    return int(match.group()) if match else None


def normalize_boolish(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, int):
        return 1 if value else 0
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "y", "是", "有"}:
        return 1
    if lowered in {"0", "false", "no", "n", "否", "无"}:
        return 0
    return None


def split_multi_value(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[，,、;/\n|]+", str(value))
    result: List[str] = []
    seen = set()
    for item in items:
        text = clean_text(item)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def csv_from_items(items: Iterable[str]) -> Optional[str]:
    normalized = split_multi_value(list(items))
    return ",".join(normalized) if normalized else None


def items_from_csv(value: Any) -> List[str]:
    return split_multi_value(value)


def parse_patch_json(raw_json: Optional[str] = None, patch_file: Optional[str] = None) -> Dict[str, Any]:
    if bool(raw_json) == bool(patch_file):
        raise ValueError("Provide exactly one of --patch-json or --patch-file.")
    if patch_file:
        with open(patch_file, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return json.loads(raw_json or "{}")


def normalize_patch(patch: Dict[str, Any]) -> Dict[str, Any]:
    normalized: Dict[str, Any] = {}
    for key, value in patch.items():
        if key not in USER_PERSONA_FIELDS:
            raise ValueError(f"Unsupported persona field: {key}")
        if key in LIST_FIELDS:
            normalized[key] = csv_from_items(split_multi_value(value))
        elif key in BOOL_FIELDS:
            normalized[key] = normalize_boolish(value)
        elif key in INT_FIELDS:
            normalized[key] = as_int(value)
        else:
            normalized[key] = clean_text(value)
    return normalized


def merge_persona(existing: Optional[Dict[str, Any]], patch: Dict[str, Any], source_type: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    existing = deepcopy(existing or {})
    merged = deepcopy(existing)
    field_results: List[Dict[str, Any]] = []

    if source_type not in {"explicit", "strong_inference", "weak_inference"}:
        raise ValueError(f"Unsupported source_type: {source_type}")

    for field_name, new_value in patch.items():
        old_value = merged.get(field_name)
        action_type = "skip"
        applied = False
        note = ""

        if source_type == "weak_inference":
            note = "weak_inference_only"
        elif field_name in LIST_FIELDS:
            old_items = items_from_csv(old_value)
            new_items = items_from_csv(new_value)
            if source_type == "explicit":
                candidate_value = csv_from_items(new_items)
            elif field_name in INFERENCE_MUTABLE_LIST_FIELDS:
                candidate_value = csv_from_items(old_items + new_items)
            else:
                candidate_value = old_value
                note = "explicit_only_list"
            if candidate_value != old_value and note == "":
                merged[field_name] = candidate_value
                action_type = "insert" if old_value in {None, ""} else "update"
                applied = True
            elif note == "":
                note = "no_change"
        else:
            if source_type == "explicit":
                candidate_value = new_value
            elif field_name in STRONG_INFERENCE_MUTABLE_SCALARS:
                candidate_value = new_value
            elif field_name in EXPLICIT_ONLY_FIELDS:
                candidate_value = old_value
                note = "explicit_only_scalar"
            else:
                candidate_value = old_value
                note = "not_mutable"
            if note == "" and candidate_value != old_value:
                merged[field_name] = candidate_value
                action_type = "insert" if old_value in {None, ""} else "update"
                applied = True
            elif note == "":
                note = "no_change"

        field_results.append(
            {
                "field_name": field_name,
                "old_value": old_value,
                "new_value": new_value,
                "stored_value": merged.get(field_name),
                "action_type": action_type,
                "applied_to_persona": applied,
                "note": note,
            }
        )

    merged["updated_at"] = now_string()
    if source_type == "explicit":
        merged["last_confirmed_at"] = merged["updated_at"]
    elif source_type == "strong_inference":
        merged["last_inferred_at"] = merged["updated_at"]
    return merged, field_results


def income_wan_to_range(value: Any) -> Optional[str]:
    amount = as_int(value)
    if amount is None:
        return None
    if amount <= 10:
        return "0-10万/年"
    floor = max(0, (amount // 5) * 5 - 4)
    ceiling = floor + 9
    if amount % 5 == 0:
        floor = amount - 4
        ceiling = amount + 5
    return f"{floor}-{ceiling}万/年"


def append_matcher_features(target: Dict[str, Any], feature_map: Dict[str, Any]) -> None:
    for key, value in feature_map.items():
        target[key] = value


def build_matcher_payload(persona: Dict[str, Any]) -> Dict[str, Optional[str]]:
    must_have = items_from_csv(persona.get("must_have_tags"))
    must_not_have = items_from_csv(persona.get("must_not_have_tags"))
    preferred_traits = items_from_csv(persona.get("preferred_traits"))
    disliked_traits = items_from_csv(persona.get("disliked_traits"))
    target_cities = items_from_csv(persona.get("target_cities"))
    target_statuses = items_from_csv(persona.get("target_marital_statuses"))

    matcher_traits = {
        "self_city": persona.get("self_city"),
        "self_relationship_goal": persona.get("self_relationship_goal"),
        "self_smoking": persona.get("self_smoking"),
        "self_drinking": persona.get("self_drinking"),
        "same_city_priority": "high" if len(target_cities) == 1 else "normal",
    }
    matcher_preferences = {
        "target_gender": persona.get("target_gender"),
        "target_cities": target_cities,
        "target_age_min": persona.get("target_age_min"),
        "target_age_max": persona.get("target_age_max"),
        "target_height_min": persona.get("target_height_min"),
        "target_height_max": persona.get("target_height_max"),
        "target_education_min": persona.get("target_education_min"),
        "target_income_min_wan": persona.get("target_income_min_wan"),
        "target_income_max_wan": persona.get("target_income_max_wan"),
        "target_marital_statuses": target_statuses,
        "target_accept_partner_children": persona.get("target_accept_partner_children"),
        "target_accept_long_distance": persona.get("target_accept_long_distance"),
        "must_have_tags": must_have,
        "preferred_traits": preferred_traits,
    }
    matcher_risks = {
        "must_not_have_tags": must_not_have,
        "disliked_traits": disliked_traits,
    }

    for tag in must_have + preferred_traits:
        append_matcher_features(matcher_preferences, POSITIVE_TAG_TO_MATCHER.get(tag, {}))
    for tag in must_not_have + disliked_traits:
        append_matcher_features(matcher_risks, RAW_NEGATIVE_TO_MATCHER.get(tag, {}))

    summary_parts = []
    if clean_text(persona.get("persona_summary_internal")):
        summary_parts.append(clean_text(persona.get("persona_summary_internal")))
    if clean_text(persona.get("preference_summary_internal")):
        summary_parts.append(clean_text(persona.get("preference_summary_internal")))
    if must_have:
        summary_parts.append("must_have: " + ", ".join(must_have))
    if must_not_have:
        summary_parts.append("must_not_have: " + ", ".join(must_not_have))

    return {
        "matcher_traits_json": json.dumps(matcher_traits, ensure_ascii=False, sort_keys=True),
        "matcher_preferences_json": json.dumps(matcher_preferences, ensure_ascii=False, sort_keys=True),
        "matcher_risks_json": json.dumps(matcher_risks, ensure_ascii=False, sort_keys=True),
        "matcher_summary_internal": " | ".join(part for part in summary_parts if part) or None,
    }


def public_safe_tag(tag: str) -> str:
    return PUBLIC_SAFE_TAG_MAP.get(tag, tag)


def build_public_profile(persona: Dict[str, Any]) -> Dict[str, Optional[str]]:
    must_have = [public_safe_tag(tag) for tag in items_from_csv(persona.get("must_have_tags"))]
    must_not_have = items_from_csv(persona.get("must_not_have_tags"))

    public_personality = clean_text(persona.get("public_profile_summary_draft"))
    public_values = clean_text(persona.get("public_preference_summary_draft"))

    if not public_personality:
        fragments = []
        if persona.get("self_city"):
            fragments.append(f"{persona['self_city']}本地")
        if persona.get("self_relationship_goal"):
            fragments.append(f"{persona['self_relationship_goal']}导向")
        if persona.get("self_smoking") == "否":
            fragments.append("生活方式相对稳定")
        public_personality = "，".join(fragments) or "资料在持续完善中"

    if not public_values:
        key_tags = must_have[:3]
        if key_tags:
            public_values = "看重" + "、".join(key_tags)
            if persona.get("target_accept_long_distance") == "不接受":
                public_values += "，更适合同城稳定推进的关系"
        else:
            public_values = "看重稳定、真诚和可持续的相处方式"

    notes = []
    if persona.get("target_accept_long_distance") == "不接受":
        notes.append("更适合同城稳定发展的关系")
    for raw_tag in must_not_have:
        safe_note = PUBLIC_SAFE_NEGATIVE_NOTES.get(raw_tag)
        if safe_note and safe_note not in notes:
            notes.append(safe_note)
    public_notes = "；".join(notes[:3]) if notes else None

    return {
        "public_personality": public_personality,
        "public_values": public_values,
        "public_notes": public_notes,
    }


def build_profile_payload(persona: Dict[str, Any], existing_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    existing_profile = existing_profile or {}
    payload: Dict[str, Any] = {}
    for persona_field, profile_field in PERSONA_TO_PROFILE_FIELD_MAP.items():
        value = persona.get(persona_field)
        if value is not None:
            payload[profile_field] = value

    if persona.get("self_income_wan") is not None:
        payload["income_range"] = income_wan_to_range(persona.get("self_income_wan"))
    if persona.get("target_accept_long_distance") is not None:
        payload["long_distance"] = persona.get("target_accept_long_distance")
        payload["accept_long_distance"] = persona.get("target_accept_long_distance")
    if persona.get("target_accept_partner_children") is not None:
        payload["accept_partner_children"] = persona.get("target_accept_partner_children")
    if persona.get("target_marital_statuses") is not None:
        payload["accept_marital_status"] = persona.get("target_marital_statuses")

    public_payload = build_public_profile(persona)
    matcher_payload = build_matcher_payload(persona)
    payload.update(public_payload)
    payload.update(matcher_payload)
    must_have = items_from_csv(persona.get("must_have_tags"))
    must_not_have = items_from_csv(persona.get("must_not_have_tags"))
    preferred_traits = items_from_csv(persona.get("preferred_traits"))
    disliked_traits = items_from_csv(persona.get("disliked_traits"))

    internal_personality = (
        clean_text(persona.get("persona_summary_internal"))
        or clean_text(existing_profile.get("personality"))
        or public_payload["public_personality"]
    )

    if clean_text(persona.get("preference_summary_internal")):
        internal_values = clean_text(persona.get("preference_summary_internal"))
    else:
        value_fragments = []
        if must_have:
            value_fragments.append("看重" + "、".join(must_have[:3]))
        if preferred_traits:
            value_fragments.append("偏好" + "、".join(preferred_traits[:3]))
        if persona.get("target_accept_long_distance") == "不接受":
            value_fragments.append("异地推进需要同城前提")
        internal_values = (
            "；".join(value_fragments)
            or clean_text(existing_profile.get("values"))
            or public_payload["public_values"]
        )

    internal_note_parts = []
    if must_not_have:
        internal_note_parts.append("明确避开" + "、".join(must_not_have[:3]))
    if disliked_traits:
        internal_note_parts.append("不太接受" + "、".join(disliked_traits[:3]))
    if persona.get("target_marital_statuses"):
        internal_note_parts.append(f"可接受婚况={persona.get('target_marital_statuses')}")
    if persona.get("target_accept_partner_children"):
        internal_note_parts.append(f"对子女情况={persona.get('target_accept_partner_children')}")
    internal_notes = (
        "；".join(internal_note_parts)
        or clean_text(existing_profile.get("notes"))
        or matcher_payload["matcher_summary_internal"]
        or public_payload["public_notes"]
    )

    payload["personality"] = internal_personality
    payload["values"] = internal_values
    payload["notes"] = internal_notes
    payload["name"] = clean_text(persona.get("display_name")) or clean_text(existing_profile.get("name")) or clean_text(persona.get("user_key")) or "未命名"
    payload["source_channel"] = clean_text(existing_profile.get("source_channel")) or "persona-memory-sync"
    payload["profile_status"] = clean_text(existing_profile.get("profile_status")) or "active"
    payload["verified_level"] = clean_text(existing_profile.get("verified_level")) or "none"
    payload["last_active_at"] = now_string()
    return payload


def mark_profile_sync_results(
    field_results: List[Dict[str, Any]],
    *,
    synced_profile: bool,
) -> List[Dict[str, Any]]:
    for item in field_results:
        item["applied_to_profile"] = bool(
            synced_profile
            and item.get("applied_to_persona")
            and persona_field_affects_profile(item.get("field_name", ""))
        )
    return field_results


def insert_profile_stub(cursor, profile_table: str, payload: Dict[str, Any]) -> int:
    cursor.execute(
        f"""
        INSERT INTO {quote_mysql_ident(profile_table)}
          (name, profile_status, verified_level, source_channel, last_active_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            payload["name"],
            payload["profile_status"],
            payload["verified_level"],
            payload["source_channel"],
            payload["last_active_at"],
        ),
    )
    profile_id = getattr(cursor, "lastrowid", None)
    if not profile_id:
        raise ValueError(
            f"Could not allocate a profile id from {profile_table}. Ensure profiles.id is AUTO_INCREMENT."
        )
    return int(profile_id)


def build_public_profile_view_sql(profile_table: str = DEFAULT_PROFILE_TABLE, view_name: str = DEFAULT_PUBLIC_VIEW) -> str:
    profile_table_q = quote_mysql_ident(profile_table)
    view_name_q = quote_mysql_ident(view_name)
    return f"""
CREATE OR REPLACE VIEW {view_name_q} AS
SELECT
  id,
  name,
  avatar_url,
  photo_count,
  gender,
  age,
  city,
  district,
  height,
  education,
  job,
  income_range,
  relationship_goal,
  COALESCE(public_personality, personality) AS personality,
  COALESCE(public_values, `values`) AS `values`,
  COALESCE(public_notes, notes) AS notes
FROM {profile_table_q}
""".strip()
