"""MySQL-backed source loading helpers for partner search."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Mapping

from mysql_source_config import parse_mysql_source_config
from outer_system_mysql_schema import quote_mysql_ident as mysql_quote_ident

from match_domain.onboarding_search import expand_search_gender_values


SEARCH_PROFILE_PROJECTION_FIELDS = frozenset(
    {
        "id",
        "name",
        "avatar_url",
        "photo_count",
        "gender",
        "age",
        "city",
        "district",
        "hometown",
        "settlement_city",
        "housing_status",
        "car_status",
        "height",
        "education",
        "job",
        "income_range",
        "income_min_wan",
        "income_max_wan",
        "relationship_goal",
        "preferred_age_min",
        "preferred_age_max",
        "preferred_cities",
        "preferred_height_min",
        "preferred_height_max",
        "preferred_age_strictness",
        "preferred_height_strictness",
        "preferred_education_min",
        "preferred_education_strictness",
        "preferred_income_min_wan",
        "preferred_income_max_wan",
        "preferred_income_strictness",
        "personality",
        "values",
        "lifestyle",
        "hobbies",
        "life_routine",
        "communication_style",
        "dating_pace",
        "expression_style",
        "relationship_capacity",
        "interaction_comfort",
        "patience_level",
        "life_texture",
        "career_intensity",
        "exercise_habit",
        "growth_signal",
        "warmth_style",
        "aesthetic_expression",
        "conversation_resonance",
        "personal_presence",
        "lightness_humor",
        "consumption_attitude",
        "chat_texture",
        "commitment_clarity",
        "relationship_execution",
        "blended_family_readiness",
        "smoking",
        "drinking",
        "long_distance",
        "accept_long_distance",
        "location_preference_semantics",
        "accept_smoking",
        "accept_drinking",
        "accept_marital_status",
        "accept_marital_status_strength",
        "accept_marital_status_semantics",
        "marital_status",
        "has_children",
        "children_count",
        "children_living_with_self",
        "want_children",
        "accept_partner_children",
        "accept_partner_children_strength",
        "accept_partner_children_semantics",
        "requires_partner_accept_my_children",
        "marriage_timeline",
        "family_background",
        "profile_status",
        "last_active_at",
        "verified_level",
        "photo_verification_level",
        "live_video_verified",
        "education_verification_status",
        "job_verification_status",
        "income_verification_status",
        "city_verification_status",
        "marital_status_verification_status",
        "children_verification_status",
        "relationship_goal_verification_status",
        "profile_review_status",
        "job_change_count_30d",
        "city_change_count_30d",
        "income_change_count_30d",
        "source_channel",
        "created_at",
        "updated_at",
        "notes",
        "matcher_traits_json",
        "matcher_preferences_json",
        "matcher_risks_json",
    }
)


@dataclass(frozen=True)
class SearchSourceRuntime:
    alias_lookup: Mapping[str, str]
    verified_level_order: Mapping[str, int]
    photo_verification_level_order: Mapping[str, int]
    default_mysql_photos_table: str
    as_int: Callable[[Any], int | None]
    as_lower: Callable[[Any], str]
    as_text: Callable[[Any], str]
    normalize_key: Callable[[Any], str]
    verified_rank: Callable[[Any], int]
    photo_verification_rank: Callable[[Any], int]
    normalize_record: Callable[[dict[str, Any]], dict[str, Any]]
    build_source_file_ref: Callable[[str | None, str | None], str]
    split_source_file_ref: Callable[[str | None], tuple[str, str | None]]
    redact_mysql_source: Callable[[str], str]
    resolve_profile_source: Callable[[str | None, str | None], tuple[str | None, str | None]]
    detect_profile_table: Callable[..., str | None]
    list_profile_columns: Callable[..., list[str]]
    list_profile_previews: Callable[..., dict[int, list[str]]]
    list_profiles: Callable[..., list[dict[str, Any]]]
    load_mysql_photo_previews_fn: Callable[..., dict[int, list[str]]] | None = None


def parse_mysql_source(
    runtime: SearchSourceRuntime,
    source: str,
    table_name: str | None = None,
) -> dict[str, Any]:
    try:
        return parse_mysql_source_config(
            source,
            source_label="MySQL source",
            table_name=table_name,
            default_photos_table_name=runtime.default_mysql_photos_table,
            default_host="localhost",
        )
    except ValueError as exc:
        if str(exc) == "MySQL source must include a database name.":
            raise ValueError(
                "MySQL source must include a database name, for example mysql://user:pass@host:3306/db"
            ) from exc
        raise


def quote_mysql_ident(identifier: str) -> str:
    return mysql_quote_ident(identifier)


def resolve_mysql_columns(
    runtime: SearchSourceRuntime,
    conn: Any,
    database: str,
    table: str,
) -> dict[str, str]:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT column_name AS column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (database, table),
        )
        mapping: dict[str, str] = {}
        for row in cursor.fetchall():
            actual = row["column_name"]
            canonical = runtime.alias_lookup.get(runtime.normalize_key(actual), runtime.normalize_key(actual))
            mapping.setdefault(canonical, actual)
        return mapping


def build_mysql_prefilter(
    runtime: SearchSourceRuntime,
    criteria: Mapping[str, Any],
    canonical_to_actual: Mapping[str, str],
    include_ids: list[Any] | None = None,
    include_ids_mode: str = "or",
) -> tuple[str, list[Any]] | None:
    include_ids = [item for item in (include_ids or []) if item is not None]
    include_ids_mode = runtime.as_lower(include_ids_mode) or "or"
    if include_ids_mode not in {"or", "only"}:
        raise ValueError("include_ids_mode must be either 'or' or 'only'.")
    if include_ids and "id" not in canonical_to_actual:
        return None

    base_clauses: list[str] = []
    base_params: list[Any] = []

    def text_expr(actual: str) -> str:
        return f"COALESCE({quote_mysql_ident(actual)}, '')"

    def defaulted_text_expr(actual: str) -> str:
        return f"COALESCE(NULLIF({text_expr(actual)}, ''), %s)"

    def add_exact(canonical: str, value: Any, allow_missing: bool = False) -> None:
        actual = canonical_to_actual.get(canonical)
        if actual is None or value is None:
            return
        expr = text_expr(actual)
        if allow_missing:
            base_clauses.append(f"({expr} = %s OR {expr} = '')")
        else:
            base_clauses.append(f"{expr} = %s")
        base_params.append(runtime.as_text(value))

    def add_in(
        canonical: str,
        values: Any,
        allow_missing: bool = False,
        default_value: Any = None,
    ) -> None:
        actual = canonical_to_actual.get(canonical)
        normalized = [runtime.as_text(item) for item in values or [] if runtime.as_text(item)]
        if actual is None or not normalized:
            return
        placeholders = ", ".join(["%s"] * len(normalized))
        if default_value is not None:
            expr = defaulted_text_expr(actual)
            base_clauses.append(f"{expr} IN ({placeholders})")
            base_params.append(runtime.as_text(default_value))
        else:
            expr = text_expr(actual)
            if allow_missing:
                base_clauses.append(f"({expr} IN ({placeholders}) OR {expr} = '')")
            else:
                base_clauses.append(f"{expr} IN ({placeholders})")
        base_params.extend(normalized)

    def add_not_in(canonical: str, values: Any) -> None:
        actual = canonical_to_actual.get(canonical)
        normalized = [runtime.as_text(item) for item in values or [] if runtime.as_text(item)]
        if actual is None or not normalized:
            return
        placeholders = ", ".join(["%s"] * len(normalized))
        base_clauses.append(f"{text_expr(actual)} NOT IN ({placeholders})")
        base_params.extend(normalized)

    def add_numeric_bound(canonical: str, operator: str, value: Any, allow_missing: bool = False) -> None:
        actual = canonical_to_actual.get(canonical)
        if actual is None or value is None:
            return
        clause = f"{quote_mysql_ident(actual)} {operator} %s"
        if allow_missing:
            clause = f"({quote_mysql_ident(actual)} IS NULL OR {clause})"
        base_clauses.append(clause)
        base_params.append(value)

    gender_values = expand_search_gender_values(criteria.get("gender"))
    if gender_values:
        add_in("gender", gender_values, allow_missing=True)
    add_numeric_bound("age", ">=", criteria.get("age_min"), allow_missing=True)
    add_numeric_bound("age", "<=", criteria.get("age_max"), allow_missing=True)
    add_numeric_bound("height", ">=", criteria.get("height_min"), allow_missing=True)
    add_numeric_bound("height", "<=", criteria.get("height_max"), allow_missing=True)
    add_in("city", criteria.get("cities"), allow_missing=True)
    add_in("district", criteria.get("districts"), allow_missing=True)
    add_in("settlement_city", criteria.get("settlement_cities"), allow_missing=True)
    add_in("relationship_goal", criteria.get("relationship_goals"), allow_missing=True)
    add_exact("smoking", criteria.get("smoking"), allow_missing=True)
    add_exact("drinking", criteria.get("drinking"), allow_missing=True)
    add_exact("long_distance", criteria.get("long_distance"), allow_missing=True)
    add_in("housing_status", criteria.get("housing_statuses"), allow_missing=True)
    add_in("car_status", criteria.get("car_statuses"), allow_missing=True)
    add_in("marital_status", criteria.get("marital_statuses"), allow_missing=True)
    add_exact("want_children", criteria.get("want_children"), allow_missing=True)
    add_exact("accept_partner_children", criteria.get("accept_partner_children"), allow_missing=True)
    add_in("marriage_timeline", criteria.get("marriage_timelines"), allow_missing=True)
    add_in("profile_status", criteria.get("profile_statuses") or ["active"], allow_missing=True)
    add_not_in("source_channel", criteria.get("exclude_source_channels"))
    add_in("verified_level", criteria.get("verified_levels"), default_value="none")
    add_in("photo_verification_level", criteria.get("photo_verification_levels"), default_value="none")
    add_numeric_bound("photo_count", ">=", criteria.get("photo_count_min"), allow_missing=True)

    if criteria.get("has_children") is not None:
        add_numeric_bound("has_children", "=", int(criteria["has_children"]), allow_missing=True)

    if criteria.get("verified_level_min"):
        actual = canonical_to_actual.get("verified_level")
        if actual is not None:
            required_rank = runtime.verified_rank(criteria["verified_level_min"])
            allowed_levels = [
                level
                for level, rank in runtime.verified_level_order.items()
                if rank >= required_rank
            ]
            placeholders = ", ".join(["%s"] * len(allowed_levels))
            base_clauses.append(f"{defaulted_text_expr(actual)} IN ({placeholders})")
            base_params.append("none")
            base_params.extend(allowed_levels)

    if criteria.get("photo_verification_level_min"):
        actual = canonical_to_actual.get("photo_verification_level")
        if actual is not None:
            required_rank = runtime.photo_verification_rank(criteria["photo_verification_level_min"])
            allowed_levels = [
                level
                for level, rank in runtime.photo_verification_level_order.items()
                if rank >= required_rank
            ]
            placeholders = ", ".join(["%s"] * len(allowed_levels))
            base_clauses.append(f"{defaulted_text_expr(actual)} IN ({placeholders})")
            base_params.append("none")
            base_params.extend(allowed_levels)

    if criteria.get("active_within_days") is not None:
        activity_fields = [
            canonical_to_actual.get(field)
            for field in ("last_active_at", "updated_at", "created_at")
            if canonical_to_actual.get(field)
        ]
        if activity_fields:
            cutoff = datetime.now() - timedelta(days=criteria["active_within_days"])
            coalesced_activity = ", ".join(quote_mysql_ident(field) for field in activity_fields)
            base_clauses.append(f"COALESCE({coalesced_activity}) >= %s")
            base_params.append(cutoff.strftime("%Y-%m-%d %H:%M:%S"))

    base_where = " AND ".join(f"({clause})" for clause in base_clauses)

    include_where = ""
    include_params: list[Any] = []
    if include_ids:
        actual_id = canonical_to_actual["id"]
        placeholders = ", ".join(["%s"] * len(include_ids))
        include_where = f"{quote_mysql_ident(actual_id)} IN ({placeholders})"
        include_params.extend(include_ids)

    if include_where and include_ids_mode == "only":
        return f" WHERE {include_where}", include_params
    if base_where and include_where:
        return f" WHERE ({base_where}) OR ({include_where})", base_params + include_params
    if base_where:
        return f" WHERE {base_where}", base_params
    if include_where:
        return f" WHERE {include_where}", include_params
    return "", []


def load_mysql(
    runtime: SearchSourceRuntime,
    source: str,
    table_name: str | None = None,
    criteria: Mapping[str, Any] | None = None,
    include_ids: list[Any] | None = None,
    include_ids_mode: str = "or",
) -> list[dict[str, Any]]:
    return [
        row
        for batch in iter_load_mysql_batches(
            runtime,
            source,
            table_name=table_name,
            criteria=criteria,
            include_ids=include_ids,
            include_ids_mode=include_ids_mode,
        )
        for row in batch
    ]


def iter_load_mysql_batches(
    runtime: SearchSourceRuntime,
    source: str,
    table_name: str | None = None,
    criteria: Mapping[str, Any] | None = None,
    include_ids: list[Any] | None = None,
    include_ids_mode: str = "or",
):
    config = parse_mysql_source(runtime, source, table_name=table_name)
    normalized_source, normalized_table = runtime.resolve_profile_source(source, config.get("table"))
    effective_source = normalized_source or str(source)
    table = normalized_table or runtime.detect_profile_table(source_dsn=effective_source)
    if not table:
        raise ValueError(f"Could not detect a candidate table in MySQL database {config['database']}")

    canonical_to_actual: dict[str, str] = {}
    for actual in runtime.list_profile_columns(source_dsn=effective_source, source_table_name=table):
        canonical = runtime.alias_lookup.get(runtime.normalize_key(actual), runtime.normalize_key(actual))
        canonical_to_actual.setdefault(canonical, actual)
    selected_columns = [
        actual
        for canonical, actual in canonical_to_actual.items()
        if canonical in SEARCH_PROFILE_PROJECTION_FIELDS
    ]
    if "id" in canonical_to_actual and canonical_to_actual["id"] not in selected_columns:
        selected_columns.append(canonical_to_actual["id"])

    prefilter = build_mysql_prefilter(
        runtime,
        criteria or {},
        canonical_to_actual,
        include_ids=include_ids,
        include_ids_mode=include_ids_mode,
    )
    if prefilter is None:
        where_clause, params = "", []
    else:
        where_clause, params = prefilter
    normalized_where = where_clause.replace("%s", "?")
    from her_env import env_int
    from profile_service import iter_profile_batches

    batch_size = env_int("PARTNER_SEARCH_PROFILE_BATCH_SIZE", 500)
    persona_batch_size = env_int("PARTNER_SEARCH_PERSONA_BATCH_SIZE", max(batch_size * 4, batch_size))
    try:
        from match_domain.persona_loader import load_personas_by_profile_ids
    except Exception:  # noqa: BLE001
        load_personas_by_profile_ids = None  # type: ignore[assignment,misc]

    try:
        from match_domain.reciprocal_preferences import merge_persona_into_profile_record
    except Exception:  # noqa: BLE001
        merge_persona_into_profile_record = None  # type: ignore[assignment,misc]

    pending_rows: list[dict[str, Any]] = []
    pending_profile_ids: list[int] = []
    normalize_record = runtime.normalize_record
    source_file_ref = runtime.build_source_file_ref(effective_source, table)

    def flush_pending_rows() -> list[dict[str, Any]]:
        if not pending_rows:
            return []
        personas_by_profile: dict[int, dict[str, Any]] = {}
        if pending_profile_ids and load_personas_by_profile_ids is not None:
            try:
                unique_profile_ids = list(dict.fromkeys(pending_profile_ids))
                personas_by_profile = load_personas_by_profile_ids(
                    source=effective_source,
                    profile_ids=unique_profile_ids,
                )
            except Exception:  # noqa: BLE001
                personas_by_profile = {}

        batch_records: list[dict[str, Any]] = []
        append_record = batch_records.append
        for row in pending_rows:
            profile_id = int(row["id"]) if row.get("id") is not None else None
            persona_row = personas_by_profile.get(profile_id) if profile_id is not None else None
            row_dict = row
            if persona_row is not None and merge_persona_into_profile_record is not None:
                row_dict = merge_persona_into_profile_record(row_dict, persona_row)
            if row_dict is row:
                row_dict["source_file"] = source_file_ref
            else:
                row_dict = dict(row_dict)
                row_dict["source_file"] = source_file_ref
            append_record(normalize_record(row_dict))

        pending_rows.clear()
        pending_profile_ids.clear()
        return batch_records

    for batch in iter_profile_batches(
        source_dsn=effective_source,
        source_table_name=table,
        where_clause=normalized_where,
        params=params,
        selected_columns=selected_columns,
        batch_size=batch_size,
    ):
        pending_rows.extend(batch)
        pending_profile_ids.extend(int(row["id"]) for row in batch if row.get("id") is not None)
        if len(pending_profile_ids) >= persona_batch_size:
            normalized_batch = flush_pending_rows()
            if normalized_batch:
                yield normalized_batch

    normalized_batch = flush_pending_rows()
    if normalized_batch:
        yield normalized_batch


def load_mysql_photo_previews(
    runtime: SearchSourceRuntime,
    source: str,
    profile_ids: list[Any],
    table_name: str | None = None,
    photos_table_name: str | None = None,
    preview_count: int = 3,
) -> dict[int, list[str]]:
    if preview_count <= 0 or not profile_ids:
        return {}

    config = parse_mysql_source(runtime, source, table_name=table_name)
    return runtime.list_profile_previews(
        source_dsn=source,
        source_table_name=config.get("table"),
        photos_table_name=photos_table_name or config.get("photos_table") or runtime.default_mysql_photos_table,
        profile_ids=[item for item in profile_ids if item is not None],
        preview_count=preview_count,
    )


def detect_mysql_profile_table(
    runtime: SearchSourceRuntime,
    conn: Any,
    database: str,
) -> str | None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name AS table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            ORDER BY table_name
            """,
            (database,),
        )
        tables = [row["table_name"] for row in cursor.fetchall()]

        scored_tables: list[tuple[str, int]] = []
        for table in tables:
            cursor.execute(
                """
                SELECT column_name AS column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                (database, table),
            )
            columns = {runtime.normalize_key(row["column_name"]) for row in cursor.fetchall()}
            canonical_columns = {runtime.alias_lookup.get(column, column) for column in columns}
            score = 0
            for required, weight in {
                "id": 2,
                "name": 2,
                "gender": 2,
                "age": 2,
                "city": 2,
                "profile_status": 1,
                "verified_level": 1,
            }.items():
                if required in canonical_columns:
                    score += weight
            scored_tables.append((table, score))

        if not scored_tables:
            return None

        best_score = max(score for _, score in scored_tables)
        if best_score <= 0:
            return None

        best_tables = [table for table, score in scored_tables if score == best_score]
        if len(best_tables) > 1:
            raise ValueError(
                "Ambiguous MySQL candidate tables: "
                + ", ".join(best_tables)
                + ". Specify ?table=... in the DSN or pass --table."
            )
        return best_tables[0]


def load_source(
    runtime: SearchSourceRuntime,
    source: str,
    *,
    is_mysql_source: Callable[[str], bool],
    table_name: str | None = None,
    criteria: Mapping[str, Any] | None = None,
    include_ids: list[Any] | None = None,
    include_ids_mode: str = "or",
) -> list[dict[str, Any]]:
    if not is_mysql_source(source):
        raise ValueError(
            "Unsupported source type. Use a MySQL DSN such as mysql://user:pass@host:3306/db?table=profiles"
        )
    return load_mysql(
        runtime,
        source,
        table_name=table_name,
        criteria=criteria,
        include_ids=include_ids,
        include_ids_mode=include_ids_mode,
    )


def iter_load_source_batches(
    runtime: SearchSourceRuntime,
    source: str,
    *,
    is_mysql_source: Callable[[str], bool],
    table_name: str | None = None,
    criteria: Mapping[str, Any] | None = None,
    include_ids: list[Any] | None = None,
    include_ids_mode: str = "or",
):
    if not is_mysql_source(source):
        raise ValueError(
            "Unsupported source type. Use a MySQL DSN such as mysql://user:pass@host:3306/db?table=profiles"
        )
    yield from iter_load_mysql_batches(
        runtime,
        source,
        table_name=table_name,
        criteria=criteria,
        include_ids=include_ids,
        include_ids_mode=include_ids_mode,
    )


def attach_photo_previews(
    runtime: SearchSourceRuntime,
    results: list[dict[str, Any]],
    preview_count: int,
    photos_table_name: str | None = None,
) -> None:
    if preview_count <= 0 or not results:
        return

    grouped_profile_ids: dict[tuple[str, str | None], list[int]] = {}
    for result in results:
        profile_id = runtime.as_int(result.get("id"))
        source_file = result.get("source_file") or ""
        source, table_name = runtime.split_source_file_ref(source_file)
        if profile_id is None or not source:
            continue
        group_key = (source, table_name or None)
        grouped_profile_ids.setdefault(group_key, [])
        if profile_id not in grouped_profile_ids[group_key]:
            grouped_profile_ids[group_key].append(profile_id)

    preview_lookup: dict[tuple[str, str | None], dict[int, list[str]]] = {}
    for group_key, profile_ids in grouped_profile_ids.items():
        source, table_name = group_key
        try:
            load_photo_previews = runtime.load_mysql_photo_previews_fn or (
                lambda source_arg, ids_arg, **kwargs: load_mysql_photo_previews(
                    runtime,
                    source_arg,
                    ids_arg,
                    **kwargs,
                )
            )
            preview_lookup[group_key] = load_photo_previews(
                source,
                profile_ids,
                table_name=table_name,
                photos_table_name=photos_table_name,
                preview_count=preview_count,
            )
        except Exception as exc:  # noqa: BLE001 - keep CLI warning behavior
            preview_lookup[group_key] = {}
            runtime_warning = (
                f"WARN: skipping photo previews for "
                f"{runtime.redact_mysql_source(source)}#{table_name or ''}: {exc}"
            )
            print(runtime_warning, file=sys.stderr)

    for result in results:
        profile_id = runtime.as_int(result.get("id"))
        source_file = result.get("source_file") or ""
        source, table_name = runtime.split_source_file_ref(source_file)
        previews = preview_lookup.get((source, table_name or None), {}).get(profile_id, [])
        if previews:
            result["photo_preview"] = previews


__all__ = [
    "SearchSourceRuntime",
    "attach_photo_previews",
    "build_mysql_prefilter",
    "detect_mysql_profile_table",
    "iter_load_mysql_batches",
    "iter_load_source_batches",
    "load_mysql",
    "load_mysql_photo_previews",
    "load_source",
    "parse_mysql_source",
    "quote_mysql_ident",
    "resolve_mysql_columns",
]
