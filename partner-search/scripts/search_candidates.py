#!/usr/bin/env python3

import argparse
import os
import re
import sys
from datetime import datetime, timedelta
from urllib.parse import parse_qs, unquote, urlparse


FIELD_ALIASES = {
    "id": {"id", "编号"},
    "name": {"name", "姓名", "昵称"},
    "avatar_url": {"avatar_url", "头像", "头像地址"},
    "photo_count": {"photo_count", "照片数", "照片数量"},
    "gender": {"gender", "性别"},
    "age": {"age", "年龄"},
    "city": {"city", "城市", "所在地", "现居地"},
    "district": {"district", "区县", "区域"},
    "hometown": {"hometown", "老家", "籍贯"},
    "settlement_city": {"settlement_city", "定居城市", "长期定居城市"},
    "housing_status": {"housing_status", "住房情况"},
    "car_status": {"car_status", "车辆情况"},
    "height": {"height", "身高"},
    "education": {"education", "学历"},
    "job": {"job", "工作", "职业"},
    "income_range": {"income_range", "收入", "收入范围"},
    "relationship_goal": {"relationship_goal", "目标", "恋爱目标", "婚恋目标", "关系目标"},
    "preferred_age_min": {"preferred_age_min", "择偶年龄下限", "年龄要求下限", "偏好年龄下限", "年龄最小"},
    "preferred_age_max": {"preferred_age_max", "择偶年龄上限", "年龄要求上限", "偏好年龄上限", "年龄最大"},
    "preferred_cities": {"preferred_cities", "择偶城市", "意向城市", "期望城市", "偏好城市"},
    "preferred_height_min": {"preferred_height_min", "择偶身高下限", "身高要求下限", "偏好身高下限", "最低身高"},
    "preferred_height_max": {"preferred_height_max", "择偶身高上限", "身高要求上限", "偏好身高上限", "最高身高"},
    "preferred_education_min": {"preferred_education_min", "择偶学历下限", "最低学历", "学历要求"},
    "preferred_income_min_wan": {"preferred_income_min_wan", "择偶收入下限", "收入要求下限", "最低收入"},
    "preferred_income_max_wan": {"preferred_income_max_wan", "择偶收入上限", "收入要求上限", "最高收入"},
    "personality": {"personality", "性格"},
    "values": {"values", "价值观", "消费观"},
    "lifestyle": {"lifestyle", "生活方式", "作息"},
    "hobbies": {"hobbies", "兴趣", "爱好"},
    "smoking": {"smoking", "抽烟", "吸烟"},
    "drinking": {"drinking", "喝酒", "饮酒"},
    "long_distance": {"long_distance", "异地", "接受异地"},
    "accept_long_distance": {"accept_long_distance", "是否接受异地", "可否异地"},
    "accept_smoking": {"accept_smoking", "接受抽烟", "接受吸烟", "是否接受抽烟", "是否接受吸烟"},
    "accept_drinking": {"accept_drinking", "接受喝酒", "接受饮酒", "是否接受喝酒", "是否接受饮酒"},
    "accept_marital_status": {"accept_marital_status", "接受婚况", "可接受婚况", "可接受婚姻状态"},
    "marital_status": {"marital_status", "婚姻状态"},
    "has_children": {"has_children", "有无孩子", "是否有孩子", "是否已育"},
    "children_count": {"children_count", "孩子数量", "子女数量"},
    "children_living_with_self": {"children_living_with_self", "孩子是否同住", "子女是否同住"},
    "want_children": {"want_children", "是否想要孩子", "想要孩子", "生育计划", "孩子计划"},
    "accept_partner_children": {
        "accept_partner_children",
        "接受对方孩子",
        "是否接受对方有孩子",
        "是否接受伴侣有孩子",
    },
    "marriage_timeline": {"marriage_timeline", "结婚时间", "结婚计划", "结婚节奏"},
    "family_background": {"family_background", "家庭情况", "家庭背景"},
    "profile_status": {"profile_status", "资料状态", "档案状态"},
    "last_active_at": {"last_active_at", "最近活跃时间", "最后活跃时间"},
    "verified_level": {"verified_level", "认证等级", "认证级别"},
    "source_channel": {"source_channel", "来源渠道", "来源"},
    "created_at": {"created_at", "创建时间"},
    "updated_at": {"updated_at", "更新时间"},
    "notes": {"notes", "备注", "说明"},
}

MYSQL_SCHEMES = {"mysql", "mysql+pymysql"}
DEFAULT_MYSQL_SOURCE = os.environ.get(
    "PARTNER_SEARCH_MYSQL_SOURCE",
    "mysql://root@127.0.0.1:3307/her?table=profiles",
)
DEFAULT_MYSQL_PHOTOS_TABLE = os.environ.get(
    "PARTNER_SEARCH_MYSQL_PHOTOS_TABLE",
    "profile_photos",
)
PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d)\d{4}(\d{4})(?!\d)")
EMAIL_PATTERN = re.compile(r"(?P<local>[A-Za-z0-9._%+-]+)@(?P<domain>[A-Za-z0-9.-]+\.[A-Za-z]{2,})")
NATIONAL_ID_PATTERN = re.compile(r"(?<![\dXx])(\d{6})\d{8}(\d{3}[\dXx])(?![\dXx])")
CONTACT_HANDLE_PATTERN = re.compile(
    r"(?P<label>(?:微信(?:号)?|wechat|wx|vx|qq)\s*[:：]?\s*)(?P<handle>[A-Za-z][-_A-Za-z0-9]{5,19}|\d{5,12})",
    re.IGNORECASE,
)

def normalize_key(key):
    return re.sub(r"[\s\-]+", "_", str(key).strip().lower())


TEXT_FIELDS = [
    "name",
    "city",
    "district",
    "hometown",
    "settlement_city",
    "housing_status",
    "car_status",
    "education",
    "job",
    "income_range",
    "relationship_goal",
    "preferred_cities",
    "personality",
    "values",
    "lifestyle",
    "hobbies",
    "smoking",
    "drinking",
    "long_distance",
    "accept_long_distance",
    "accept_smoking",
    "accept_drinking",
    "accept_marital_status",
    "marital_status",
    "want_children",
    "accept_partner_children",
    "marriage_timeline",
    "family_background",
    "notes",
    "source_channel",
]

VERIFIED_LEVEL_ORDER = {
    "none": 0,
    "basic": 1,
    "photo": 2,
    "id": 3,
    "offline": 4,
}

PROFILE_STATUS_ORDER = {
    "archived": 0,
    "matched": 1,
    "paused": 2,
    "active": 3,
}

EDUCATION_ORDER = {
    "初中": 1,
    "高中": 2,
    "中专": 3,
    "大专": 4,
    "专升本": 5,
    "本科": 6,
    "硕士": 7,
    "博士": 8,
}

ACCEPTED_VALUES = {"接受", "是", "可以", "ok", "accept", "accepted"}
REJECTED_VALUES = {"不接受", "否", "不可以", "reject", "rejected"}
NEGOTIABLE_VALUES = {"可协商", "协商", "待定"}
UNKNOWN_VALUES = {"未知", "不确定", "未说明", "未填写", "unknown"}
POSITIVE_HABIT_VALUES = {"是", "偶尔", "有", "yes", "true", "1"}


def build_alias_lookup():
    lookup = {}
    for canonical, aliases in FIELD_ALIASES.items():
        for alias in aliases:
            lookup[normalize_key(alias)] = canonical
    return lookup


ALIAS_LOOKUP = build_alias_lookup()


def is_mysql_source(source):
    try:
        return urlparse(str(source)).scheme.lower() in MYSQL_SCHEMES
    except Exception:
        return False


def redact_mysql_source(source):
    text = str(source)
    try:
        parsed = urlparse(text)
    except Exception:
        return text
    if parsed.scheme.lower() not in MYSQL_SCHEMES:
        return text

    userinfo = ""
    if parsed.username:
        username = unquote(parsed.username)
        if parsed.password:
            userinfo = f"{username}:***@"
        else:
            userinfo = f"{username}@"

    host = parsed.hostname or "localhost"
    port = f":{parsed.port}" if parsed.port else ""
    query = parse_qs(parsed.query)
    safe_query_parts = []
    for key in ("table", "photos_table", "charset"):
        value = query.get(key, [None])[0]
        if value:
            safe_query_parts.append(f"{key}={value}")
    query_text = f"?{'&'.join(safe_query_parts)}" if safe_query_parts else ""
    return f"{parsed.scheme}://{userinfo}{host}{port}{parsed.path}{query_text}"


def redact_source_ref(source_ref):
    if not source_ref:
        return ""
    source, separator, table_name = str(source_ref).rpartition("#")
    if not separator:
        return redact_mysql_source(source_ref)
    redacted = redact_mysql_source(source)
    return f"{redacted}#{table_name}" if table_name else redacted


def split_keywords(value):
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[，,、;/\n]+", str(value))
    return [str(item).strip() for item in items if str(item).strip()]


def merge_keyword_args(values):
    merged = []
    for value in values or []:
        merged.extend(split_keywords(value))
    return merged


def as_lower(value):
    return str(value).strip().lower() if value is not None else ""


def as_text(value):
    return str(value).strip() if value is not None else ""


def as_int(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    match = re.search(r"-?\d+", str(value))
    return int(match.group()) if match else None


def normalize_bool(value):
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    lowered = as_lower(value)
    if lowered in {"1", "true", "yes", "y", "是", "有"}:
        return True
    if lowered in {"0", "false", "no", "n", "否", "无"}:
        return False
    return None


def normalize_acceptance_state(value):
    if value is None or value == "":
        return "missing"
    lowered = as_lower(value)
    if lowered in ACCEPTED_VALUES:
        return "accepted"
    if lowered in REJECTED_VALUES:
        return "rejected"
    if lowered in NEGOTIABLE_VALUES:
        return "negotiable"
    if lowered in UNKNOWN_VALUES:
        return "unknown"
    normalized = normalize_bool(value)
    if normalized is True:
        return "accepted"
    if normalized is False:
        return "rejected"
    return "unknown"


def habit_requires_acceptance(value):
    return as_lower(value) in POSITIVE_HABIT_VALUES


def as_datetime(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def education_rank(value):
    return EDUCATION_ORDER.get(str(value).strip()) if value else None


def verified_rank(value):
    return VERIFIED_LEVEL_ORDER.get(as_lower(value), 0)


def profile_status_rank(value):
    return PROFILE_STATUS_ORDER.get(as_lower(value), 0)


def parse_income_range_to_wan(value):
    if value is None:
        return (None, None)
    numbers = [int(item) for item in re.findall(r"\d+", str(value))]
    if not numbers:
        return (None, None)
    if len(numbers) == 1:
        return (numbers[0], numbers[0])
    return (min(numbers[0], numbers[1]), max(numbers[0], numbers[1]))


def effective_has_children(record):
    direct = normalize_bool(record.get("has_children"))
    if direct is not None:
        return direct
    marital_status = as_lower(record.get("marital_status"))
    if "已育" in marital_status:
        return True
    if marital_status in {"未婚", "离异未育"}:
        return False
    return None


def effective_activity_datetime(record):
    for field in ("last_active_at", "updated_at", "created_at"):
        parsed = as_datetime(record.get(field))
        if parsed is not None:
            return parsed
    return None


def format_datetime(value):
    parsed = as_datetime(value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S") if parsed else None


def mask_value(value, left=2, right=2, mask="***"):
    text = str(value)
    if not text:
        return text
    if len(text) <= left + right:
        if len(text) <= 2:
            return "*" * len(text)
        return text[:1] + mask
    suffix = text[-right:] if right > 0 else ""
    return text[:left] + mask + suffix


def redact_sensitive_text(value):
    if value is None or value == "":
        return value

    text = str(value)
    text = PHONE_PATTERN.sub(lambda match: f"{match.group(1)}****{match.group(2)}", text)
    text = NATIONAL_ID_PATTERN.sub(
        lambda match: f"{match.group(1)}********{match.group(2)}",
        text,
    )
    text = EMAIL_PATTERN.sub(
        lambda match: f"{mask_value(match.group('local'), left=1, right=0)}@{match.group('domain')}",
        text,
    )
    text = CONTACT_HANDLE_PATTERN.sub(
        lambda match: f"{match.group('label')}{mask_value(match.group('handle'), left=2, right=2)}",
        text,
    )
    return text


def normalize_record(raw):
    record = {}
    for key, value in raw.items():
        canonical = ALIAS_LOOKUP.get(normalize_key(key), normalize_key(key))
        record[canonical] = value

    if "source_file" not in record:
        record["source_file"] = ""

    for key, value in list(record.items()):
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                value = None
        record[key] = value

    if record.get("age") is not None:
        match = re.search(r"\d+", str(record["age"]))
        record["age"] = int(match.group()) if match else None

    if record.get("height") is not None:
        match = re.search(r"\d+", str(record["height"]))
        record["height"] = int(match.group()) if match else None

    record["combined_text"] = build_combined_text(record)
    return record


def build_combined_text(record):
    parts = []
    for key in TEXT_FIELDS:
        value = record.get(key)
        if value:
            parts.append(str(value))
    return " | ".join(parts).lower()


def parse_mysql_source(source, table_name=None):
    parsed = urlparse(str(source))
    if parsed.scheme.lower() not in MYSQL_SCHEMES:
        raise ValueError(f"Unsupported MySQL source: {source}")

    database = unquote(parsed.path.lstrip("/"))
    if not database:
        raise ValueError("MySQL source must include a database name, for example mysql://user:pass@host:3306/db")

    query = parse_qs(parsed.query)
    resolved_table = table_name or query.get("table", [None])[0]
    photos_table = query.get("photos_table", [DEFAULT_MYSQL_PHOTOS_TABLE])[0]
    charset = query.get("charset", ["utf8mb4"])[0]
    unix_socket = query.get("unix_socket", [None])[0]

    config = {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "user": unquote(parsed.username) if parsed.username else None,
        "password": unquote(parsed.password) if parsed.password else None,
        "database": database,
        "table": resolved_table,
        "photos_table": photos_table,
        "charset": charset,
    }
    if unix_socket:
        config["unix_socket"] = unquote(unix_socket)
    return config


def quote_mysql_ident(identifier):
    return "`" + str(identifier).replace("`", "``") + "`"


def resolve_mysql_columns(conn, database, table):
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
        mapping = {}
        for row in cursor.fetchall():
            actual = row["column_name"]
            canonical = ALIAS_LOOKUP.get(normalize_key(actual), normalize_key(actual))
            mapping.setdefault(canonical, actual)
        return mapping


def build_mysql_prefilter(criteria, canonical_to_actual, include_ids=None):
    include_ids = [item for item in (include_ids or []) if item is not None]
    if include_ids and "id" not in canonical_to_actual:
        return None

    base_clauses = []
    base_params = []

    def text_expr(actual):
        return f"COALESCE({quote_mysql_ident(actual)}, '')"

    def defaulted_text_expr(actual):
        return f"COALESCE(NULLIF({text_expr(actual)}, ''), %s)"

    def add_exact(canonical, value, allow_missing=False):
        actual = canonical_to_actual.get(canonical)
        if actual is None or value is None:
            return
        expr = text_expr(actual)
        if allow_missing:
            base_clauses.append(f"({expr} = %s OR {expr} = '')")
        else:
            base_clauses.append(f"{expr} = %s")
        base_params.append(as_text(value))

    def add_in(canonical, values, allow_missing=False, default_value=None):
        actual = canonical_to_actual.get(canonical)
        normalized = [as_text(item) for item in values or [] if as_text(item)]
        if actual is None or not normalized:
            return
        placeholders = ", ".join(["%s"] * len(normalized))
        if default_value is not None:
            expr = defaulted_text_expr(actual)
            base_clauses.append(f"{expr} IN ({placeholders})")
            base_params.append(as_text(default_value))
        else:
            expr = text_expr(actual)
            if allow_missing:
                base_clauses.append(f"({expr} IN ({placeholders}) OR {expr} = '')")
            else:
                base_clauses.append(f"{expr} IN ({placeholders})")
        base_params.extend(normalized)

    def add_numeric_bound(canonical, operator, value, allow_missing=False):
        actual = canonical_to_actual.get(canonical)
        if actual is None or value is None:
            return
        clause = f"{quote_mysql_ident(actual)} {operator} %s"
        if allow_missing:
            clause = f"({quote_mysql_ident(actual)} IS NULL OR {clause})"
        base_clauses.append(clause)
        base_params.append(value)

    add_exact("gender", criteria.get("gender"), allow_missing=True)
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
    add_in("verified_level", criteria.get("verified_levels"), default_value="none")
    add_numeric_bound("photo_count", ">=", criteria.get("photo_count_min"), allow_missing=True)

    if criteria.get("has_children") is not None:
        add_numeric_bound("has_children", "=", int(criteria["has_children"]), allow_missing=True)

    if criteria.get("verified_level_min"):
        actual = canonical_to_actual.get("verified_level")
        if actual is not None:
            required_rank = verified_rank(criteria["verified_level_min"])
            allowed_levels = [
                level
                for level, rank in VERIFIED_LEVEL_ORDER.items()
                if rank >= required_rank
            ]
            placeholders = ", ".join(["%s"] * len(allowed_levels))
            base_clauses.append(
                f"{defaulted_text_expr(actual)} IN ({placeholders})"
            )
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
    include_params = []
    if include_ids:
        actual_id = canonical_to_actual["id"]
        placeholders = ", ".join(["%s"] * len(include_ids))
        include_where = f"{quote_mysql_ident(actual_id)} IN ({placeholders})"
        include_params.extend(include_ids)

    if base_where and include_where:
        return f" WHERE ({base_where}) OR ({include_where})", base_params + include_params
    if base_where:
        return f" WHERE {base_where}", base_params
    if include_where:
        return f" WHERE {include_where}", include_params
    return "", []


def load_mysql(source, table_name=None, criteria=None, include_ids=None):
    try:
        import pymysql
    except ImportError as exc:
        raise ValueError("MySQL support requires PyMySQL. Install it with `pip install pymysql`.") from exc

    config = parse_mysql_source(source, table_name=table_name)
    connect_kwargs = {
        "host": config["host"],
        "port": config["port"],
        "database": config["database"],
        "charset": config["charset"],
        "cursorclass": pymysql.cursors.DictCursor,
    }
    if config.get("user") is not None:
        connect_kwargs["user"] = config["user"]
    if config.get("password") is not None:
        connect_kwargs["password"] = config["password"]
    if config.get("unix_socket"):
        connect_kwargs["unix_socket"] = config["unix_socket"]

    conn = pymysql.connect(**connect_kwargs)
    try:
        table = config["table"] or detect_mysql_profile_table(conn, config["database"])
        if not table:
            raise ValueError(f"Could not detect a candidate table in MySQL database {config['database']}")
        canonical_to_actual = resolve_mysql_columns(conn, config["database"], table)
        prefilter = build_mysql_prefilter(criteria or {}, canonical_to_actual, include_ids=include_ids)
        if prefilter is None:
            where_clause, params = "", []
        else:
            where_clause, params = prefilter
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {quote_mysql_ident(table)}{where_clause}",
                params,
            )
            rows = cursor.fetchall()
        return [
            normalize_record(dict(row, source_file=f"{source}#{table}"))
            for row in rows
        ]
    finally:
        conn.close()


def load_mysql_photo_previews(source, profile_ids, table_name=None, photos_table_name=None, preview_count=3):
    if preview_count <= 0 or not profile_ids:
        return {}

    try:
        import pymysql
    except ImportError as exc:
        raise ValueError("MySQL support requires PyMySQL. Install it with `pip install pymysql`.") from exc

    config = parse_mysql_source(source, table_name=table_name)
    photo_table = photos_table_name or config.get("photos_table") or DEFAULT_MYSQL_PHOTOS_TABLE
    connect_kwargs = {
        "host": config["host"],
        "port": config["port"],
        "database": config["database"],
        "charset": config["charset"],
        "cursorclass": pymysql.cursors.DictCursor,
    }
    if config.get("user") is not None:
        connect_kwargs["user"] = config["user"]
    if config.get("password") is not None:
        connect_kwargs["password"] = config["password"]
    if config.get("unix_socket"):
        connect_kwargs["unix_socket"] = config["unix_socket"]

    conn = pymysql.connect(**connect_kwargs)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name AS column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                (config["database"], photo_table),
            )
            photo_columns = {row["column_name"] for row in cursor.fetchall()}
            if "profile_id" not in photo_columns or "photo_url" not in photo_columns:
                raise ValueError(
                    f"MySQL photos table {config['database']}.{photo_table} must contain profile_id and photo_url columns."
                )

            placeholders = ", ".join(["%s"] * len(profile_ids))
            order_parts = ["`profile_id` ASC"]
            if "is_primary" in photo_columns:
                order_parts.append("CASE WHEN `is_primary` = 1 THEN 0 ELSE 1 END")
            elif "photo_type" in photo_columns:
                order_parts.append("CASE WHEN `photo_type` = 'avatar' THEN 0 ELSE 1 END")
            if "sort_order" in photo_columns:
                order_parts.append("`sort_order` ASC")
            if "id" in photo_columns:
                order_parts.append("`id` ASC")

            cursor.execute(
                f"""
                SELECT `profile_id`, `photo_url`
                FROM {quote_mysql_ident(photo_table)}
                WHERE `profile_id` IN ({placeholders})
                ORDER BY {", ".join(order_parts)}
                """,
                profile_ids,
            )

            previews = {}
            for row in cursor.fetchall():
                profile_id = as_int(row.get("profile_id"))
                photo_url = row.get("photo_url")
                if profile_id is None or not photo_url:
                    continue
                previews.setdefault(profile_id, [])
                if len(previews[profile_id]) < preview_count:
                    previews[profile_id].append(photo_url)
            return previews
    finally:
        conn.close()


def detect_mysql_profile_table(conn, database):
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

        scored_tables = []
        for table in tables:
            cursor.execute(
                """
                SELECT column_name AS column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                (database, table),
            )
            columns = {normalize_key(row["column_name"]) for row in cursor.fetchall()}
            canonical_columns = {ALIAS_LOOKUP.get(column, column) for column in columns}
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


def load_source(source, table_name=None, criteria=None, include_ids=None):
    if not is_mysql_source(source):
        raise ValueError(
            "Unsupported source type. Use a MySQL DSN such as mysql://user:pass@host:3306/db?table=profiles"
        )
    return load_mysql(
        source,
        table_name=table_name,
        criteria=criteria,
        include_ids=include_ids,
    )


def build_criteria_from_args(args):
    criteria = {}

    if args.gender:
        criteria["gender"] = str(args.gender).strip().lower()

    for key in ("age_min", "age_max", "height_min", "height_max"):
        value = getattr(args, key)
        if value is not None:
            criteria[key] = value

    cities = merge_keyword_args(args.city)
    if cities:
        criteria["cities"] = cities
    districts = merge_keyword_args(args.district)
    if districts:
        criteria["districts"] = districts
    settlement_cities = merge_keyword_args(args.settlement_city)
    if settlement_cities:
        criteria["settlement_cities"] = settlement_cities

    relationship_goals = merge_keyword_args(args.relationship_goal)
    if relationship_goals:
        criteria["relationship_goals"] = relationship_goals

    must_have = merge_keyword_args(args.must_have)
    if must_have:
        criteria["must_have"] = must_have

    must_not_have = merge_keyword_args(args.must_not_have)
    if must_not_have:
        criteria["must_not_have"] = must_not_have

    prefer = merge_keyword_args(args.prefer)
    if prefer:
        criteria["prefer"] = prefer

    if args.smoking:
        criteria["smoking"] = args.smoking
    if args.drinking:
        criteria["drinking"] = args.drinking
    if args.long_distance:
        criteria["long_distance"] = args.long_distance
    if args.housing_status:
        criteria["housing_statuses"] = merge_keyword_args(args.housing_status)
    if args.car_status:
        criteria["car_statuses"] = merge_keyword_args(args.car_status)
    if args.marital_status:
        criteria["marital_statuses"] = merge_keyword_args(args.marital_status)
    if args.has_children is not None:
        criteria["has_children"] = bool(args.has_children)
    if args.want_children:
        criteria["want_children"] = args.want_children
    if args.accept_partner_children:
        criteria["accept_partner_children"] = args.accept_partner_children
    if args.marriage_timeline:
        criteria["marriage_timelines"] = merge_keyword_args(args.marriage_timeline)
    criteria["profile_statuses"] = merge_keyword_args(args.profile_status) or ["active"]
    if args.active_within_days is not None:
        criteria["active_within_days"] = args.active_within_days
    if args.verified_level_min:
        criteria["verified_level_min"] = args.verified_level_min
    if args.verified_level:
        criteria["verified_levels"] = merge_keyword_args(args.verified_level)
    if args.photo_count_min is not None:
        criteria["photo_count_min"] = args.photo_count_min
    criteria["exclude_ids"] = {item for item in args.exclude_id or []}

    return criteria


def build_self_profile_from_args(args, records):
    profile = {}

    if args.self_id is not None:
        matched = next((record for record in records if as_int(record.get("id")) == args.self_id), None)
        if not matched:
            raise ValueError(f"Could not find self profile id {args.self_id} in the selected source.")
        profile.update(strip_internal_fields(matched))
        income_min, income_max = parse_income_range_to_wan(matched.get("income_range"))
        profile["income_min_wan"] = income_min
        profile["income_max_wan"] = income_max

    overlays = {
        "age": args.self_age,
        "city": args.self_city,
        "height": args.self_height,
        "education": args.self_education,
        "marital_status": args.self_marital_status,
        "smoking": args.self_smoking,
        "drinking": args.self_drinking,
    }
    for key, value in overlays.items():
        if value is not None:
            profile[key] = value

    if args.self_income_wan is not None:
        profile["income_min_wan"] = args.self_income_wan
        profile["income_max_wan"] = args.self_income_wan
    if args.self_has_children is not None:
        profile["has_children"] = bool(args.self_has_children)

    if not profile:
        return None

    if args.self_id is not None:
        profile["id"] = args.self_id
    profile["has_children"] = normalize_bool(profile.get("has_children"))
    return profile


def exact_match(value, expected):
    return as_lower(value) == as_lower(expected)


def match_any_exact(value, candidates):
    lowered = as_lower(value)
    return lowered in {as_lower(item) for item in candidates}


def income_range_overlaps(min_value, max_value, required_min, required_max):
    if min_value is None and max_value is None:
        return None
    candidate_min = min_value if min_value is not None else max_value
    candidate_max = max_value if max_value is not None else min_value
    if required_min is not None and candidate_max is not None and candidate_max < required_min:
        return False
    if required_max is not None and candidate_min is not None and candidate_min > required_max:
        return False
    return True


def activity_score_info(record):
    active_at = effective_activity_datetime(record)
    if active_at is None:
        return (0, None, None)

    now = datetime.now()
    age = now - active_at
    if age <= timedelta(days=7):
        return (12, "7天内活跃", active_at)
    if age <= timedelta(days=30):
        return (8, "30天内活跃", active_at)
    if age <= timedelta(days=90):
        return (4, "90天内活跃", active_at)
    return (0, "90天前活跃", active_at)


def verified_score_info(record):
    level = record.get("verified_level") or "none"
    rank = verified_rank(level)
    labels = {
        0: "未认证",
        1: "基础认证",
        2: "照片认证",
        3: "实名认证",
        4: "线下核验",
    }
    return (rank * 2, labels.get(rank, "未认证"), rank)


def evaluate_reciprocal_compatibility(record, self_profile):
    if not self_profile:
        return {
            "matched_on": [],
            "missing_fields": [],
            "risk_flags": [],
            "score_bonus": 0,
        }

    reasons = []
    missing_fields = []
    risk_flags = []
    score_bonus = 0

    self_age = as_int(self_profile.get("age"))
    pref_age_min = as_int(record.get("preferred_age_min"))
    pref_age_max = as_int(record.get("preferred_age_max"))
    if pref_age_min is not None or pref_age_max is not None:
        if self_age is None:
            missing_fields.append("self_age")
        elif pref_age_min is not None and self_age < pref_age_min:
            return None
        elif pref_age_max is not None and self_age > pref_age_max:
            return None
        else:
            reasons.append("对方年龄偏好命中")
            score_bonus += 10

    pref_cities = split_keywords(record.get("preferred_cities"))
    self_city = self_profile.get("city")
    if pref_cities:
        if not self_city:
            missing_fields.append("self_city")
        elif not match_any_exact(self_city, pref_cities):
            return None
        else:
            reasons.append("对方城市偏好命中")
            score_bonus += 10

    self_height = as_int(self_profile.get("height"))
    pref_height_min = as_int(record.get("preferred_height_min"))
    pref_height_max = as_int(record.get("preferred_height_max"))
    if pref_height_min is not None or pref_height_max is not None:
        if self_height is None:
            missing_fields.append("self_height")
        elif pref_height_min is not None and self_height < pref_height_min:
            return None
        elif pref_height_max is not None and self_height > pref_height_max:
            return None
        else:
            reasons.append("对方身高偏好命中")
            score_bonus += 6

    pref_education_min = record.get("preferred_education_min")
    if pref_education_min:
        self_education = self_profile.get("education")
        self_rank = education_rank(self_education)
        required_rank = education_rank(pref_education_min)
        if not self_education:
            missing_fields.append("self_education")
        elif self_rank is None or required_rank is None:
            if not exact_match(self_education, pref_education_min):
                return None
        elif self_rank < required_rank:
            return None
        else:
            reasons.append("对方学历偏好命中")
            score_bonus += 6

    pref_income_min = as_int(record.get("preferred_income_min_wan"))
    pref_income_max = as_int(record.get("preferred_income_max_wan"))
    if pref_income_min is not None or pref_income_max is not None:
        self_income_min = as_int(self_profile.get("income_min_wan"))
        self_income_max = as_int(self_profile.get("income_max_wan"))
        overlap = income_range_overlaps(self_income_min, self_income_max, pref_income_min, pref_income_max)
        if overlap is None:
            missing_fields.append("self_income_wan")
        elif overlap is False:
            return None
        else:
            reasons.append("对方收入偏好命中")
            score_bonus += 6

    accepted_statuses = split_keywords(record.get("accept_marital_status"))
    if accepted_statuses:
        self_status = self_profile.get("marital_status")
        if not self_status:
            missing_fields.append("self_marital_status")
        elif not match_any_exact(self_status, accepted_statuses):
            return None
        else:
            reasons.append("对方可接受婚况命中")
            score_bonus += 8

    self_has_children = normalize_bool(self_profile.get("has_children"))
    accept_partner_children = normalize_acceptance_state(record.get("accept_partner_children"))
    if accept_partner_children != "missing":
        if self_has_children is None:
            missing_fields.append("self_has_children")
        elif self_has_children:
            if accept_partner_children == "rejected":
                return None
            if accept_partner_children == "accepted":
                reasons.append("对方接受你有孩子")
                score_bonus += 8
            elif accept_partner_children == "negotiable":
                risk_flags.append("对方对子女情况仅可协商")
            else:
                risk_flags.append("对方对子女接受度未知")

    self_smoking = self_profile.get("smoking")
    accept_smoking = normalize_acceptance_state(record.get("accept_smoking"))
    if accept_smoking != "missing":
        if not self_smoking:
            missing_fields.append("self_smoking")
        elif habit_requires_acceptance(self_smoking):
            if accept_smoking == "rejected":
                return None
            if accept_smoking == "accepted":
                reasons.append("对方接受你的抽烟习惯")
                score_bonus += 4
            elif accept_smoking == "negotiable":
                risk_flags.append("对方对抽烟仅可协商")
            else:
                risk_flags.append("对方对抽烟接受度未知")

    self_drinking = self_profile.get("drinking")
    accept_drinking = normalize_acceptance_state(record.get("accept_drinking"))
    if accept_drinking != "missing":
        if not self_drinking:
            missing_fields.append("self_drinking")
        elif habit_requires_acceptance(self_drinking):
            if accept_drinking == "rejected":
                return None
            if accept_drinking == "accepted":
                reasons.append("对方接受你的喝酒习惯")
                score_bonus += 4
            elif accept_drinking == "negotiable":
                risk_flags.append("对方对喝酒仅可协商")
            else:
                risk_flags.append("对方对喝酒接受度未知")

    candidate_city = record.get("city")
    accept_long_distance = normalize_acceptance_state(record.get("accept_long_distance"))
    if self_city and candidate_city and as_lower(self_city) != as_lower(candidate_city):
        if accept_long_distance == "rejected":
            return None
        if accept_long_distance == "accepted":
            reasons.append("对方接受异地")
            score_bonus += 4
        elif accept_long_distance == "negotiable":
            risk_flags.append("对方异地仅可协商")
        else:
            risk_flags.append("对方异地接受度未知")

    return {
        "matched_on": reasons,
        "missing_fields": missing_fields,
        "risk_flags": risk_flags,
        "score_bonus": score_bonus,
    }


def evaluate_candidate(record, criteria):
    reasons = []
    reciprocal_reasons = []
    missing_fields = []
    risk_flags = []
    score = 0

    if as_int(record.get("id")) in criteria.get("exclude_ids", set()):
        return None

    profile_status = record.get("profile_status")
    allowed_statuses = criteria.get("profile_statuses") or ["active"]
    if not profile_status:
        missing_fields.append("profile_status")
    else:
        if not match_any_exact(profile_status, allowed_statuses):
            return None
        reasons.append(f"状态 {profile_status}")
        score += 4

    active_at = effective_activity_datetime(record)
    if criteria.get("active_within_days") is not None:
        if active_at is None:
            missing_fields.append("last_active_at")
            return None
        if active_at < datetime.now() - timedelta(days=criteria["active_within_days"]):
            return None

    if criteria.get("verified_level_min"):
        if verified_rank(record.get("verified_level")) < verified_rank(criteria["verified_level_min"]):
            return None

    age = record.get("age")
    if criteria.get("age_min") is not None:
        if age is None:
            missing_fields.append("age")
        elif age < criteria["age_min"]:
            return None
        else:
            reasons.append(f"年龄 {age}")
            score += 15
    if criteria.get("age_max") is not None:
        if age is None:
            if "age" not in missing_fields:
                missing_fields.append("age")
        elif age > criteria["age_max"]:
            return None

    height = record.get("height")
    if criteria.get("height_min") is not None:
        if height is None:
            missing_fields.append("height")
        elif height < criteria["height_min"]:
            return None
        else:
            score += 5
    if criteria.get("height_max") is not None:
        if height is None:
            if "height" not in missing_fields:
                missing_fields.append("height")
        elif height > criteria["height_max"]:
            return None

    if criteria.get("gender"):
        gender = as_lower(record.get("gender"))
        if not gender:
            missing_fields.append("gender")
        elif gender != criteria["gender"]:
            return None
        else:
            reasons.append(f"性别 {record.get('gender')}")
            score += 10

    if criteria.get("cities"):
        city = as_lower(record.get("city"))
        if not city:
            missing_fields.append("city")
        elif city not in [as_lower(item) for item in criteria["cities"]]:
            return None
        else:
            reasons.append(f"城市 {record.get('city')}")
            score += 20

    if criteria.get("districts"):
        district = as_lower(record.get("district"))
        if not district:
            missing_fields.append("district")
        elif district not in [as_lower(item) for item in criteria["districts"]]:
            return None
        else:
            reasons.append(f"区域 {record.get('district')}")
            score += 8

    if criteria.get("settlement_cities"):
        settlement_city = as_lower(record.get("settlement_city"))
        if not settlement_city:
            missing_fields.append("settlement_city")
        elif settlement_city not in [as_lower(item) for item in criteria["settlement_cities"]]:
            return None
        else:
            reasons.append(f"定居 {record.get('settlement_city')}")
            score += 8

    if criteria.get("relationship_goals"):
        goal = as_lower(record.get("relationship_goal"))
        if not goal:
            missing_fields.append("relationship_goal")
        elif goal not in [as_lower(item) for item in criteria["relationship_goals"]]:
            return None
        else:
            reasons.append(f"目标 {record.get('relationship_goal')}")
            score += 15

    combined_text = record.get("combined_text", "")

    if criteria.get("must_have"):
        for keyword in criteria["must_have"]:
            if keyword.lower() not in combined_text:
                return None
            reasons.append(f"包含 {keyword}")
            score += 8

    if criteria.get("must_not_have"):
        for keyword in criteria["must_not_have"]:
            if keyword.lower() in combined_text:
                return None

    for keyword in criteria.get("prefer", []):
        if keyword.lower() in combined_text:
            reasons.append(f"偏好命中 {keyword}")
            score += 6

    if criteria.get("smoking"):
        smoking = as_lower(record.get("smoking"))
        desired = as_lower(criteria["smoking"])
        if not smoking:
            missing_fields.append("smoking")
        elif smoking != desired:
            return None
        else:
            score += 8

    if criteria.get("drinking"):
        drinking = as_lower(record.get("drinking"))
        desired = as_lower(criteria["drinking"])
        if not drinking:
            missing_fields.append("drinking")
        elif drinking != desired:
            return None
        else:
            score += 5

    if criteria.get("long_distance"):
        long_distance = as_lower(record.get("long_distance"))
        desired = as_lower(criteria["long_distance"])
        if not long_distance:
            missing_fields.append("long_distance")
        elif long_distance != desired:
            return None
        else:
            score += 8

    if criteria.get("housing_statuses"):
        housing_status = record.get("housing_status")
        if not housing_status:
            missing_fields.append("housing_status")
        elif not match_any_exact(housing_status, criteria["housing_statuses"]):
            return None
        else:
            reasons.append(f"住房 {housing_status}")
            score += 6

    if criteria.get("car_statuses"):
        car_status = record.get("car_status")
        if not car_status:
            missing_fields.append("car_status")
        elif not match_any_exact(car_status, criteria["car_statuses"]):
            return None
        else:
            reasons.append(f"车辆 {car_status}")
            score += 4

    if criteria.get("marital_statuses"):
        marital_status = record.get("marital_status")
        if not marital_status:
            missing_fields.append("marital_status")
        elif not match_any_exact(marital_status, criteria["marital_statuses"]):
            return None
        else:
            reasons.append(f"婚况 {marital_status}")
            score += 10

    if criteria.get("has_children") is not None:
        has_children = effective_has_children(record)
        if has_children is None:
            missing_fields.append("has_children")
        elif has_children != criteria["has_children"]:
            return None
        else:
            reasons.append("子女情况命中")
            score += 10

    if criteria.get("want_children"):
        want_children = record.get("want_children")
        if not want_children:
            missing_fields.append("want_children")
        elif not exact_match(want_children, criteria["want_children"]):
            return None
        else:
            reasons.append(f"生育计划 {want_children}")
            score += 8

    if criteria.get("accept_partner_children"):
        accept_partner_children = record.get("accept_partner_children")
        if not accept_partner_children:
            missing_fields.append("accept_partner_children")
        elif not exact_match(accept_partner_children, criteria["accept_partner_children"]):
            return None
        else:
            reasons.append(f"接受对方孩子 {accept_partner_children}")
            score += 6

    if criteria.get("marriage_timelines"):
        marriage_timeline = record.get("marriage_timeline")
        if not marriage_timeline:
            missing_fields.append("marriage_timeline")
        elif not match_any_exact(marriage_timeline, criteria["marriage_timelines"]):
            return None
        else:
            reasons.append(f"结婚节奏 {marriage_timeline}")
            score += 8

    if criteria.get("verified_levels"):
        verified_level = record.get("verified_level") or "none"
        if not match_any_exact(verified_level, criteria["verified_levels"]):
            return None
        reasons.append(f"认证 {verified_level}")
        score += 4

    if criteria.get("photo_count_min") is not None:
        photo_count = as_int(record.get("photo_count"))
        if photo_count is None:
            missing_fields.append("photo_count")
        elif photo_count < criteria["photo_count_min"]:
            return None
        else:
            reasons.append(f"照片 {photo_count}张")
            score += min(photo_count, 6)

    if not reasons:
        reasons.append("基础条件未提供，按资料完整度保留")

    reciprocal = evaluate_reciprocal_compatibility(record, criteria.get("self_profile"))
    if reciprocal is None:
        return None
    reciprocal_reasons.extend(reciprocal["matched_on"])
    missing_fields.extend(reciprocal["missing_fields"])
    risk_flags.extend(reciprocal["risk_flags"])
    score += reciprocal["score_bonus"]

    verified_score, verified_label, verified_sort_rank = verified_score_info(record)
    score += verified_score
    if verified_sort_rank > 0:
        reasons.append(verified_label)
    else:
        risk_flags.append("未认证")

    activity_bonus, activity_label, activity_dt = activity_score_info(record)
    score += activity_bonus
    if activity_label and activity_bonus > 0:
        reasons.append(activity_label)
    elif activity_dt is None:
        risk_flags.append("活跃时间未知")
    elif activity_label:
        risk_flags.append(activity_label)

    completeness = sum(1 for field in TEXT_FIELDS if record.get(field))
    score += min(completeness, 10)

    return {
        "id": record.get("id"),
        "name": record.get("name") or "未命名",
        "score": score,
        "matched_on": unique_ordered(reasons),
        "reciprocal_on": unique_ordered(reciprocal_reasons),
        "missing_fields": unique_ordered(missing_fields),
        "risk_flags": unique_ordered(risk_flags),
        "profile": strip_internal_fields(record),
        "source_file": record.get("source_file"),
        "verified_rank": verified_sort_rank,
        "activity_sort_ts": int(activity_dt.timestamp()) if activity_dt else 0,
        "profile_status_rank": profile_status_rank(profile_status),
    }


def unique_ordered(items):
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def strip_internal_fields(record):
    cleaned = {}
    for key, value in record.items():
        if key in {"combined_text", "source_file"}:
            continue
        cleaned[key] = value
    return cleaned


def result_sort_key(result):
    return (
        result["score"],
        result["verified_rank"],
        result["activity_sort_ts"],
        result["profile_status_rank"],
    )


def attach_photo_previews(results, preview_count, photos_table_name=None):
    if preview_count <= 0 or not results:
        return

    grouped_profile_ids = {}
    for result in results:
        profile_id = as_int(result.get("id"))
        source_file = result.get("source_file") or ""
        source, _, table_name = source_file.rpartition("#")
        if profile_id is None or not source:
            continue
        group_key = (source, table_name or None)
        grouped_profile_ids.setdefault(group_key, [])
        if profile_id not in grouped_profile_ids[group_key]:
            grouped_profile_ids[group_key].append(profile_id)

    preview_lookup = {}
    for group_key, profile_ids in grouped_profile_ids.items():
        source, table_name = group_key
        try:
            preview_lookup[group_key] = load_mysql_photo_previews(
                source,
                profile_ids,
                table_name=table_name,
                photos_table_name=photos_table_name,
                preview_count=preview_count,
            )
        except Exception as exc:
            print(
                f"WARN: skipping photo previews for {redact_mysql_source(source)}#{table_name or ''}: {exc}",
                file=sys.stderr,
            )
            preview_lookup[group_key] = {}

    for result in results:
        profile_id = as_int(result.get("id"))
        source_file = result.get("source_file") or ""
        source, _, table_name = source_file.rpartition("#")
        previews = preview_lookup.get((source, table_name or None), {}).get(profile_id, [])
        if previews:
            result["photo_preview"] = previews


def format_text(results):
    lines = []
    for index, result in enumerate(results, start=1):
        profile = result["profile"]
        headline = (
            f"{index}. {result['name']} | score={result['score']} | "
            f"{profile.get('age', '未知')}岁 | {profile.get('city', '城市未知')} | "
            f"{profile.get('job', '工作未知')}"
        )
        lines.append(headline)
        meta_parts = []
        if profile.get("profile_status"):
            meta_parts.append(f"status={profile.get('profile_status')}")
        if profile.get("verified_level"):
            meta_parts.append(f"verified={profile.get('verified_level')}")
        if profile.get("photo_count") is not None:
            meta_parts.append(f"photos={profile.get('photo_count')}")
        active_at = format_datetime(profile.get("last_active_at") or profile.get("updated_at") or profile.get("created_at"))
        if active_at:
            meta_parts.append(f"active_at={active_at}")
        if meta_parts:
            lines.append(f"   meta: {' | '.join(meta_parts)}")
        if result.get("photo_preview"):
            lines.append(f"   photo_preview: {', '.join(result['photo_preview'])}")
        if result["matched_on"]:
            lines.append(f"   matched_on: {', '.join(result['matched_on'])}")
        if result["reciprocal_on"]:
            lines.append(f"   reciprocal_on: {', '.join(result['reciprocal_on'])}")
        if result["missing_fields"]:
            lines.append(f"   missing_fields: {', '.join(result['missing_fields'])}")
        if result["risk_flags"]:
            lines.append(f"   risk_flags: {', '.join(result['risk_flags'])}")
        notes = profile.get("notes")
        if notes:
            lines.append(f"   notes: {redact_sensitive_text(notes)}")
        if result.get("source_file"):
            lines.append(f"   source: {redact_source_ref(result['source_file'])}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Search profile sources for partner candidates.")
    parser.add_argument(
        "--source",
        action="append",
        help=(
            "MySQL DSN such as mysql://user:pass@host:3306/db?table=profiles. "
            f"Repeatable. Defaults to {DEFAULT_MYSQL_SOURCE}."
        ),
    )
    parser.add_argument("--table", help="MySQL table name when the table is not included in the DSN.")
    parser.add_argument("--gender", help="Filter by gender.")
    parser.add_argument("--age-min", type=int, help="Minimum age.")
    parser.add_argument("--age-max", type=int, help="Maximum age.")
    parser.add_argument("--height-min", type=int, help="Minimum height in cm.")
    parser.add_argument("--height-max", type=int, help="Maximum height in cm.")
    parser.add_argument("--city", action="append", help="Allowed city. Repeat or use comma-separated values.")
    parser.add_argument("--district", action="append", help="Allowed district. Repeat or use comma-separated values.")
    parser.add_argument(
        "--settlement-city",
        action="append",
        help="Allowed long-term settlement city. Repeat or use comma-separated values.",
    )
    parser.add_argument(
        "--relationship-goal",
        action="append",
        help="Allowed relationship goal. Repeat or use comma-separated values.",
    )
    parser.add_argument("--must-have", action="append", help="Required keyword. Repeat or use comma-separated values.")
    parser.add_argument(
        "--must-not-have",
        action="append",
        help="Excluded keyword. Repeat or use comma-separated values.",
    )
    parser.add_argument("--prefer", action="append", help="Preferred keyword. Repeat or use comma-separated values.")
    parser.add_argument("--smoking", help="Exact smoking preference, for example 否.")
    parser.add_argument("--drinking", help="Exact drinking preference, for example 否.")
    parser.add_argument("--long-distance", help="Exact long-distance preference, for example 不接受.")
    parser.add_argument(
        "--housing-status",
        action="append",
        help="Allowed housing status. Repeat or use comma-separated values.",
    )
    parser.add_argument(
        "--car-status",
        action="append",
        help="Allowed car status. Repeat or use comma-separated values.",
    )
    parser.add_argument(
        "--marital-status",
        action="append",
        help="Allowed candidate marital status. Repeat or use comma-separated values.",
    )
    parser.add_argument("--has-children", type=int, choices=[0, 1], help="Filter whether the candidate has children.")
    parser.add_argument("--want-children", help="Candidate child plan, for example 想要 or 可协商.")
    parser.add_argument(
        "--accept-partner-children",
        help="Candidate acceptance of a partner who already has children.",
    )
    parser.add_argument(
        "--marriage-timeline",
        action="append",
        help="Allowed marriage timeline. Repeat or use comma-separated values.",
    )
    parser.add_argument(
        "--profile-status",
        action="append",
        help="Allowed profile status. Defaults to active. Repeat or use comma-separated values.",
    )
    parser.add_argument("--active-within-days", type=int, help="Require recent activity within N days.")
    parser.add_argument(
        "--verified-level-min",
        choices=["none", "basic", "photo", "id", "offline"],
        help="Minimum verification level.",
    )
    parser.add_argument(
        "--verified-level",
        action="append",
        help="Exact allowed verification level. Repeat or use comma-separated values.",
    )
    parser.add_argument("--photo-count-min", type=int, help="Minimum required photo count.")
    parser.add_argument(
        "--photo-preview-count",
        type=int,
        default=0,
        help="Return the top N photo URLs from the MySQL photos table for each result.",
    )
    parser.add_argument(
        "--photos-table",
        help="MySQL photos table name when not using the default profile_photos or DSN photos_table query param.",
    )
    parser.add_argument("--self-id", type=int, help="Use an existing profile id as your own profile for reciprocal matching.")
    parser.add_argument("--self-age", type=int, help="Your age for reciprocal matching.")
    parser.add_argument("--self-city", help="Your city for reciprocal matching.")
    parser.add_argument("--self-height", type=int, help="Your height in cm for reciprocal matching.")
    parser.add_argument("--self-education", help="Your education for reciprocal matching.")
    parser.add_argument("--self-income-wan", type=int, help="Your annual income in 万 for reciprocal matching.")
    parser.add_argument("--self-marital-status", help="Your marital status for reciprocal matching.")
    parser.add_argument("--self-has-children", type=int, choices=[0, 1], help="Whether you have children for reciprocal matching.")
    parser.add_argument("--self-smoking", help="Your smoking habit for reciprocal matching.")
    parser.add_argument("--self-drinking", help="Your drinking habit for reciprocal matching.")
    parser.add_argument("--exclude-id", action="append", type=int, help="Profile id to exclude from results. Repeatable.")
    parser.add_argument("--limit", type=int, default=10, help="Maximum number of results to return.")
    args = parser.parse_args()

    try:
        criteria = build_criteria_from_args(args)
        records = []
        sources = args.source or [DEFAULT_MYSQL_SOURCE]
        include_ids = [args.self_id] if args.self_id is not None else []
        for source in sources:
            records.extend(
                load_source(
                    source,
                    table_name=args.table,
                    criteria=criteria,
                    include_ids=include_ids,
                )
            )
        self_profile = build_self_profile_from_args(args, records)
        if self_profile:
            criteria["self_profile"] = self_profile
        if args.self_id is not None:
            criteria["exclude_ids"].add(args.self_id)
        results = []
        for record in records:
            evaluated = evaluate_candidate(record, criteria)
            if evaluated:
                results.append(evaluated)
        results.sort(key=result_sort_key, reverse=True)
        results = results[: args.limit]
        attach_photo_previews(results, args.photo_preview_count, photos_table_name=args.photos_table)

        if results:
            print(format_text(results))
        else:
            print("No matches found.")
    except Exception as exc:  # pragma: no cover - CLI path
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
