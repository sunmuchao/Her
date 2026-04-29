#!/usr/bin/env python3

import argparse


STRICTNESS_COLUMNS = {
    "preferred_age_strictness": "VARCHAR(16)",
    "preferred_height_strictness": "VARCHAR(16)",
    "preferred_education_strictness": "VARCHAR(16)",
    "preferred_income_strictness": "VARCHAR(16)",
}

STRUCTURED_COLUMNS = {
    "life_routine": "VARCHAR(32)",
    "communication_style": "VARCHAR(32)",
    "dating_pace": "VARCHAR(32)",
    "expression_style": "VARCHAR(32)",
    "relationship_capacity": "VARCHAR(32)",
    "accept_marital_status_strength": "VARCHAR(32)",
    "accept_partner_children_strength": "VARCHAR(32)",
}

ALL_NEW_COLUMNS = dict(STRICTNESS_COLUMNS, **STRUCTURED_COLUMNS)

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

CREATIVE_JOBS = {
    "品牌策划",
    "设计师",
    "UI设计",
    "新媒体运营",
    "翻译",
}

BUSY_JOBS = {
    "医生",
    "护士",
    "外贸业务",
    "课程顾问",
    "新媒体运营",
}


def parse_args():
    parser = argparse.ArgumentParser(description="Backfill partner-search enrichment fields into MySQL profiles.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3307)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="")
    parser.add_argument("--database", default="her")
    parser.add_argument("--table", default="profiles")
    parser.add_argument("--charset", default="utf8mb4")
    return parser.parse_args()


def split_items(value):
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def has_any(texts, candidates):
    haystack = " ".join(str(item or "") for item in texts)
    return any(candidate in haystack for candidate in candidates)


def unique_keep_order(items):
    seen = set()
    result = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def pseudo_bucket(profile_id, salt):
    return (int(profile_id) * 37 + salt * 17) % 100


def infer_strictness(profile):
    profile_id = int(profile["id"])
    age = int(profile.get("age") or 0)
    gender = profile.get("gender") or ""
    education = profile.get("education") or ""
    relationship_goal = profile.get("relationship_goal") or ""
    values = profile.get("values") or ""
    personality = profile.get("personality") or ""

    value_texts = [values, personality]
    pragmatic = has_any(value_texts, {"务实", "消费观正常", "不喜欢攀比"})
    boundary = has_any(value_texts, {"边界清楚", "边界感强", "理性"})
    serious = relationship_goal == "结婚导向"
    high_edu = EDUCATION_ORDER.get(education, 0) >= EDUCATION_ORDER["硕士"]

    age_bucket = pseudo_bucket(profile_id, 1)
    height_bucket = pseudo_bucket(profile_id, 2)
    edu_bucket = pseudo_bucket(profile_id, 3)
    income_bucket = pseudo_bucket(profile_id, 4)

    if serious and boundary and age >= 31 and age_bucket < 28:
        age_strictness = "硬性"
    elif serious or age >= 29:
        age_strictness = "可放宽"
    else:
        age_strictness = "仅参考"

    if gender == "女" and serious and boundary and height_bucket < 18:
        height_strictness = "硬性"
    elif gender == "女" or age >= 30:
        height_strictness = "可放宽"
    else:
        height_strictness = "仅参考"

    if serious and high_edu and boundary and edu_bucket < 24:
        education_strictness = "硬性"
    elif high_edu or serious:
        education_strictness = "可放宽"
    else:
        education_strictness = "仅参考"

    if pragmatic or relationship_goal == "先接触看看":
        income_strictness = "仅参考"
    elif serious and boundary and income_bucket < 18:
        income_strictness = "硬性"
    else:
        income_strictness = "可放宽"

    return {
        "preferred_age_strictness": age_strictness,
        "preferred_height_strictness": height_strictness,
        "preferred_education_strictness": education_strictness,
        "preferred_income_strictness": income_strictness,
    }


def infer_acceptance(profile):
    profile_id = int(profile["id"])
    age = int(profile.get("age") or 0)
    relationship_goal = profile.get("relationship_goal") or ""
    marital_status = profile.get("marital_status") or ""
    values = profile.get("values") or ""
    personality = profile.get("personality") or ""
    accept_marital_status = split_items(profile.get("accept_marital_status"))
    accept_partner_children = (profile.get("accept_partner_children") or "未知").strip()

    serious = relationship_goal in {"认真恋爱", "结婚导向"}
    mature = age >= 32 or serious
    very_mature = age >= 35 or marital_status.startswith("离异")
    family_oriented = has_any(
        [values, personality],
        {"重视家庭", "愿意共同经营生活", "对感情认真", "有责任感", "顾家", "真诚", "稳定踏实"},
    )

    marital_bucket = pseudo_bucket(profile_id, 5)
    child_bucket = pseudo_bucket(profile_id, 6)

    statuses = accept_marital_status or ["未婚"]
    if marital_status.startswith("离异"):
        statuses = unique_keep_order(statuses + ["离异未育", "离异已育"])
    else:
        if mature and family_oriented and marital_bucket < 72:
            statuses = unique_keep_order(statuses + ["离异未育"])
        if very_mature and family_oriented and marital_bucket < 32:
            statuses = unique_keep_order(statuses + ["离异已育"])

    if "离异已育" in statuses:
        marital_strength = "明确接受" if very_mature and family_oriented else "谨慎接受"
    elif "离异未育" in statuses:
        marital_strength = "谨慎接受" if mature else "短期可聊"
    else:
        marital_strength = "未知"

    if marital_status.startswith("离异"):
        accept_partner_children = "接受"
        child_strength = "明确接受" if family_oriented else "谨慎接受"
    elif accept_partner_children == "接受":
        child_strength = "明确接受" if mature and family_oriented else "谨慎接受"
    elif accept_partner_children == "可协商":
        if very_mature and family_oriented and child_bucket < 48:
            accept_partner_children = "接受"
            child_strength = "谨慎接受"
        else:
            child_strength = "谨慎接受"
    elif accept_partner_children == "不接受":
        if very_mature and family_oriented and child_bucket < 18:
            accept_partner_children = "可协商"
            child_strength = "短期可聊"
        else:
            child_strength = "未知"
    else:
        if mature and family_oriented and child_bucket < 26:
            accept_partner_children = "可协商"
            child_strength = "短期可聊"
        else:
            child_strength = "未知"

    return {
        "accept_marital_status": ", ".join(unique_keep_order(statuses)),
        "accept_marital_status_strength": marital_strength,
        "accept_partner_children": accept_partner_children,
        "accept_partner_children_strength": child_strength,
    }


def infer_structured_style(profile):
    relationship_goal = profile.get("relationship_goal") or ""
    marriage_timeline = profile.get("marriage_timeline") or ""
    job = profile.get("job") or ""
    personality = profile.get("personality") or ""
    values = profile.get("values") or ""
    lifestyle = profile.get("lifestyle") or ""
    hobbies = profile.get("hobbies") or ""
    notes = profile.get("notes") or ""

    texts = [personality, values, lifestyle, hobbies, notes]

    if has_any(texts, {"生活规律", "规律作息", "不熬夜", "养生", "作息规律"}):
        life_routine = "生活规律"
    elif job in BUSY_JOBS:
        life_routine = "节奏偏忙但可协调"
    elif has_any(texts, {"偏宅", "喜欢做饭", "爱逛菜场", "干净整洁"}):
        life_routine = "生活稳定"
    else:
        life_routine = "正常作息"

    if has_any(texts, {"善沟通", "能沟通", "沟通顺畅"}):
        communication_style = "主动沟通"
    elif has_any(texts, {"慢热"}):
        communication_style = "慢热少话"
    elif has_any(texts, {"理性", "边界清楚", "边界感强"}):
        communication_style = "理性直接"
    else:
        communication_style = "稳定沟通"

    if relationship_goal == "先接触看看" or has_any(texts, {"慢热"}):
        dating_pace = "慢热推进"
    elif relationship_goal == "结婚导向" or marriage_timeline in {"半年内", "1年内"}:
        dating_pace = "认真推进"
    else:
        dating_pace = "自然推进"

    if job in CREATIVE_JOBS or has_any(texts, {"摄影", "画画", "看展", "咖啡"}):
        expression_style = "会表达有生活感"
    elif has_any(texts, {"理性", "安静"}):
        expression_style = "理性克制"
    elif has_any(texts, {"务实", "稳定踏实", "顾家"}):
        expression_style = "务实直接"
    else:
        expression_style = "自然表达"

    if has_any(texts, {"对感情认真", "愿意共同经营生活", "重视家庭"}) and relationship_goal != "先接触看看":
        relationship_capacity = "稳定投入关系"
    elif relationship_goal == "结婚导向":
        relationship_capacity = "认真经营关系"
    elif relationship_goal == "先接触看看":
        relationship_capacity = "先熟悉再投入"
    else:
        relationship_capacity = "自然稳定投入"

    return {
        "life_routine": life_routine,
        "communication_style": communication_style,
        "dating_pace": dating_pace,
        "expression_style": expression_style,
        "relationship_capacity": relationship_capacity,
    }


def ensure_columns(conn, table_name):
    with conn.cursor() as cursor:
        cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
        existing = {row["Field"] for row in cursor.fetchall()}
        for column, column_type in ALL_NEW_COLUMNS.items():
            if column in existing:
                continue
            cursor.execute(
                f"ALTER TABLE `{table_name}` ADD COLUMN `{column}` {column_type} NULL"
            )


def main():
    args = parse_args()
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover
        raise SystemExit("PyMySQL is required to backfill profile enrichment fields.") from exc

    conn = pymysql.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
        charset=args.charset,
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        ensure_columns(conn, args.table)
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT `id`, `age`, `gender`, `education`, `job`, `relationship_goal`, `marriage_timeline`,
                       `personality`, `values`, `lifestyle`, `hobbies`, `notes`, `marital_status`,
                       `accept_marital_status`, `accept_partner_children`
                FROM `{args.table}`
                """
            )
            rows = cursor.fetchall()

        updates = []
        for row in rows:
            enriched = {}
            enriched.update(infer_strictness(row))
            enriched.update(infer_acceptance(row))
            enriched.update(infer_structured_style(row))
            enriched["id"] = row["id"]
            updates.append(enriched)

        update_columns = [
            "preferred_age_strictness",
            "preferred_height_strictness",
            "preferred_education_strictness",
            "preferred_income_strictness",
            "accept_marital_status",
            "accept_marital_status_strength",
            "accept_partner_children",
            "accept_partner_children_strength",
            "life_routine",
            "communication_style",
            "dating_pace",
            "expression_style",
            "relationship_capacity",
        ]
        assignments = ", ".join(f"`{column}`=%s" for column in update_columns)
        sql = f"UPDATE `{args.table}` SET {assignments} WHERE `id`=%s"

        with conn.cursor() as cursor:
            cursor.executemany(
                sql,
                [
                    tuple(item[column] for column in update_columns) + (item["id"],)
                    for item in updates
                ],
            )
        conn.commit()
        print(f"Backfilled {len(updates)} profiles in {args.database}.{args.table}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
