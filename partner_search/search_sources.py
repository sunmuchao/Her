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


# 性能优化：全局列名映射缓存，避免每批重复查询 information_schema
_COLUMNS_MAPPING_CACHE: dict[str, dict[str, str]] = {}


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

    # ====================================================================
    # Agent Native架构：期望匹配设计理念（统一标准）
    # ====================================================================
    # 核心原则：期望只是"期望"，不是"硬标准"
    # - 薪资期望：50w超出20-30w → 不过滤，评分处理（已实现）
    # - 身高期望：173cm超出167-172cm → 不过滤，评分处理（已实现）
    # - 年龄期望：24岁超出26-36岁 → 不过滤，评分处理（本次修改）
    # - 房况/车况期望：无房/无车 → 不过滤，评分处理（本次修改）
    # - 抽烟/喝酒期望：抽烟/喝酒 → 不过滤，评分处理（本次修改）
    # - 结婚时间线期望：2年内结婚 → 不过滤，评分处理（本次修改）
    #
    # 为什么这样设计？
    # 1. 给候选人机会：即使不完全符合期望，也可能合适
    # 2. 扩大候选人池：避免因期望限制导致候选人池过小
    # 3. 保持灵活性：用户可以根据实际情况调整期望
    # 4. 统一设计理念：所有期望条件逻辑一致
    #
    # 技术实现：
    # - 移除硬筛选（不再在SQL WHERE中过滤）
    # - 改为在评分阶段处理（search_matching.py）
    # - 通过加分/减分和风险标记来判断匹配度
    # ====================================================================

    # 1. 性别：必须硬筛选（核心条件，无法协商）
    gender_values = expand_search_gender_values(criteria.get("gender"))
    if gender_values:
        add_in("gender", gender_values, allow_missing=True)

    # 2. 年龄：改为期望匹配（差1-2岁不应硬性过滤）
    # add_numeric_bound("age", ">=", criteria.get("age_min"), allow_missing=True)  ← 移除硬筛选
    # add_numeric_bound("age", "<=", criteria.get("age_max"), allow_missing=True)  ← 移除硬筛选

    # 3. 身高：已改为期望匹配（search_matching.py）

    # 4. 城市：必须硬筛选（地理位置要求）
    add_in("city", criteria.get("cities"), allow_missing=True)
    add_in("district", criteria.get("districts"), allow_missing=True)
    add_in("settlement_city", criteria.get("settlement_cities"), allow_missing=True)

    # 5. 关系目标：必须硬筛选（核心条件）
    add_in("relationship_goal", criteria.get("relationship_goals"), allow_missing=True)

    # 6. 抽烟：改为期望匹配（习惯可以协商）
    # add_exact("smoking", criteria.get("smoking"), allow_missing=True)  ← 移除硬筛选

    # 7. 喝酒：改为期望匹配（习惯可以协商）
    # add_exact("drinking", criteria.get("drinking"), allow_missing=True)  ← 移除硬筛选

    # 8. 异地：必须硬筛选（生活方式硬性条件）
    add_exact("long_distance", criteria.get("long_distance"), allow_missing=True)

    # 9. 房况：改为期望匹配（经济条件可以协商）
    # add_in("housing_status", criteria.get("housing_statuses"), allow_missing=True)  ← 移除硬筛选

    # 10. 车况：改为期望匹配（经济条件可以协商）
    # add_in("car_status", criteria.get("car_statuses"), allow_missing=True)  ← 移除硬筛选

    # 11. 婚况：必须硬筛选（法律约束）
    add_in("marital_status", criteria.get("marital_statuses"), allow_missing=True)

    # 12. 想要孩子：必须硬筛选（重大责任）
    add_exact("want_children", criteria.get("want_children"), allow_missing=True)

    # 13. 接受对方孩子：必须硬筛选（重大责任）
    add_exact("accept_partner_children", criteria.get("accept_partner_children"), allow_missing=True)

    # 14. 结婚时间线：改为期望匹配（时间可以协商）
    # add_in("marriage_timeline", criteria.get("marriage_timelines"), allow_missing=True)  ← 移除硬筛选
    # ====================================================================
    # 用户状态筛选逻辑（新设计：所有用户都能被搜索，但状态不同排名不同）
    # ====================================================================
    # 设计理念：
    # - 旧逻辑：默认只查active状态的用户（paused/matched/inactive都被过滤掉）
    # - 新逻辑：默认查所有状态的用户，但通过排序让active用户优先推荐
    #
    # 状态优先级（从高到低）：
    # 1. active（活跃）：优先推荐（rank=2）
    # 2. paused（暂停）：可以被搜索，但排名靠后（rank=1）
    # 3. matched（已匹配）：可以被搜索，但排名靠后（rank=1）
    # 4. inactive/archived（不活跃）：可以被搜索，但排名靠后（rank=0）
    #
    # 业务价值：
    # - paused用户可能是"暂时不找对象"，但仍然可以被搜索和推荐
    # - 避免因为状态限制导致候选人池过小
    # - 给用户更多选择（即使对方暂时不活跃，也可以尝试联系）
    #
    # 技术实现：
    # - 默认查所有状态（active + matched + paused + inactive + archived）
    # - 如果用户明确指定了profile_statuses，则按用户指定的筛选
    # ====================================================================
    default_profile_statuses = ["active", "matched", "paused", "inactive", "archived"]
    add_in("profile_status", criteria.get("profile_statuses") or default_profile_statuses, allow_missing=True)
    add_not_in("source_channel", criteria.get("exclude_source_channels"))

    # ====================================================================
    # Bug修复1：排除用户自己（兜底逻辑）
    # ====================================================================
    # 问题：原有逻辑依赖 self_record_ref 对象，在某些情况下可能缺失
    # 解决：在 SQL 层添加兜底逻辑，直接通过 self_id 排除
    # 原理：id NOT IN (self_id) 确保用户自己不会出现在候选人列表中
    # ====================================================================
    exclude_ids = set(criteria.get("exclude_ids") or [])
    self_id = criteria.get("self_id")
    if self_id is not None:
        exclude_ids.add(int(self_id))
    if exclude_ids:
        add_not_in("id", exclude_ids)

    add_in("verified_level", criteria.get("verified_levels"), default_value="none")
    add_in("photo_verification_level", criteria.get("photo_verification_levels"), default_value="none")
    add_numeric_bound("photo_count", ">=", criteria.get("photo_count_min"), allow_missing=True)

    # ====================================================================
    # Agent Native架构：移除性格筛选逻辑
    # ====================================================================
    # 性格特质筛选是软约束，不应该在数据库层硬编码执行。
    #
    # Agent Native原则：
    # - 硬约束（性别、年龄、城市）：在数据库层筛选（SQL WHERE条件）
    # - 软约束（性格特质）：在Agent层自主判断（根据返回的personality_signals）
    #
    # 旧逻辑（已移除）：
    # - add_in("mbti_type", criteria.get("mbti_types"))  ← 移除
    # - add_not_in("mbti_type", criteria.get("exclude_mbti")) ← 移除
    #
    # 新逻辑：
    # - 数据库只做基础筛选，返回性格原始数据
    # - Agent收到结果后，根据personality_signals自主判断性格匹配度
    # - Agent可以灵活判断："虽然MBTI偏内向，但可能有活泼的一面"
    #
    # 好处：
    # 1. 避免参数名不匹配问题（personality_traits vs mbti_types）
    # 2. Agent有更多灵活性（可以根据对话上下文调整判断）
    # 3. 符合Agent Native原则（软约束在Agent层）
    # ====================================================================

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

    # 性能优化：使用缓存避免每批重复查询列名映射
    cache_key = f"{effective_source}#{table}"
    canonical_to_actual = _COLUMNS_MAPPING_CACHE.get(cache_key)
    if canonical_to_actual is None:
        canonical_to_actual: dict[str, str] = {}
        for actual in runtime.list_profile_columns(source_dsn=effective_source, source_table_name=table):
            canonical = runtime.alias_lookup.get(runtime.normalize_key(actual), runtime.normalize_key(actual))
            canonical_to_actual.setdefault(canonical, actual)
        _COLUMNS_MAPPING_CACHE[cache_key] = canonical_to_actual

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

    # 性能优化：提高 batch_size 默认值和 persona_batch_size，减少数据库查询次数
    batch_size = env_int("PARTNER_SEARCH_PROFILE_BATCH_SIZE", 1000)  # 从 500 提升到 1000
    # 性能优化：persona_batch_size 从 batch_size*4 改为 batch_size*10，减少查询次数
    persona_batch_size = env_int("PARTNER_SEARCH_PERSONA_BATCH_SIZE", max(batch_size * 10, batch_size))  # 从 *4 改为 *10
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
        _skip_where_validation=True,  # build_mysql_prefilter 构建的 WHERE 子句已安全验证
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
    """并行加载照片预览，消除 I/O 瓶颈。

    性能优化版本：
    - 使用 ThreadPoolExecutor 并行加载不同分组的照片
    - I/O 密集型任务适合较多线程（最多 8 个）
    - 保持原有错误处理机制
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

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

    # 并行加载照片预览（I/O 密集型，适合多线程）
    preview_lookup: dict[tuple[str, str | None], dict[int, list[str]]] = {}
    if grouped_profile_ids:
        # 根据分组数量决定线程数（I/O 密集型可以更多线程）
        max_workers = min(8, len(grouped_profile_ids))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交所有分组查询任务
            future_to_group = {}
            for group_key, profile_ids in grouped_profile_ids.items():
                source, table_name = group_key
                load_photo_previews = runtime.load_mysql_photo_previews_fn or (
                    lambda source_arg, ids_arg, **kwargs: load_mysql_photo_previews(
                        runtime,
                        source_arg,
                        ids_arg,
                        **kwargs,
                    )
                )
                future = executor.submit(
                    load_photo_previews,
                    source,
                    profile_ids,
                    table_name=table_name,
                    photos_table_name=photos_table_name,
                    preview_count=preview_count,
                )
                future_to_group[future] = group_key

            # 收集结果（并行执行，总耗时 ≈ 最慢的单次查询）
            for future in as_completed(future_to_group):
                group_key = future_to_group[future]
                try:
                    preview_lookup[group_key] = future.result()
                except Exception as exc:  # noqa: BLE001 - 保持原有错误处理
                    preview_lookup[group_key] = {}
                    source, table_name = group_key
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
