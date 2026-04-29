#!/usr/bin/env python3

import argparse
import re


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
    "interaction_comfort": "VARCHAR(32)",
    "patience_level": "VARCHAR(32)",
    "life_texture": "VARCHAR(32)",
    "career_intensity": "VARCHAR(32)",
    "exercise_habit": "VARCHAR(32)",
    "growth_signal": "VARCHAR(32)",
    "warmth_style": "VARCHAR(32)",
    "aesthetic_expression": "VARCHAR(32)",
    "conversation_resonance": "VARCHAR(32)",
    "personal_presence": "VARCHAR(32)",
    "lightness_humor": "VARCHAR(32)",
    "consumption_attitude": "VARCHAR(32)",
    "chat_texture": "VARCHAR(32)",
    "commitment_clarity": "VARCHAR(32)",
    "relationship_execution": "VARCHAR(32)",
    "blended_family_readiness": "VARCHAR(32)",
    "accept_marital_status_strength": "VARCHAR(32)",
    "accept_partner_children_strength": "VARCHAR(32)",
}

ALL_NEW_COLUMNS = dict(STRICTNESS_COLUMNS, **STRUCTURED_COLUMNS)

BACKFILL_UPDATE_COLUMNS = [
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
]

CURATED_SOURCE_CHANNELS = {"高质量补池"}

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
    "审计",
}

STABLE_JOBS = {
    "公务员",
    "事业单位职员",
    "教师",
    "行政",
    "高校行政",
    "财务",
    "会计",
    "法务",
    "采购",
    "国企职员",
}

BRAINY_JOBS = {
    "产品经理",
    "后端工程师",
    "前端工程师",
    "软件测试",
    "数据分析",
    "产品运营",
    "AI研究员",
    "用户研究负责人",
    "政策研究员",
    "城市策略顾问",
    "产业战略经理",
    "商业分析经理",
    "业务发展负责人",
    "战略咨询经理",
    "AI产品经理",
    "医疗器械产品经理",
}

UPWARD_JOBS = BRAINY_JOBS | {
    "医生",
    "法务",
    "审计",
    "银行职员",
    "招商主管",
    "药企招商主管",
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


def preserve_curated_backfill(row, enriched):
    if row.get("source_channel") not in CURATED_SOURCE_CHANNELS:
        return enriched

    merged = dict(enriched)
    for column in BACKFILL_UPDATE_COLUMNS:
        current_value = row.get(column)
        if current_value not in (None, ""):
            merged[column] = current_value
    return merged


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

    if has_any(texts, {"善沟通", "能沟通", "沟通顺畅", "能接住话", "接住话", "不冷场", "不拖节奏"}):
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

    if has_any(texts, {"好相处", "松弛", "简单真诚", "相处舒服", "不复杂", "不折腾", "不压人", "让人放松", "不端着"}):
        interaction_comfort = "相处轻松"
    elif has_any(texts, {"边界清楚", "边界感强", "尊重彼此空间"}):
        interaction_comfort = "有边界不拧巴"
    elif has_any(texts, {"安静", "慢热", "温和"}):
        interaction_comfort = "安静低压"
    elif has_any(texts, {"理性", "有主见"}):
        interaction_comfort = "需要一点磨合"
    else:
        interaction_comfort = "正常相处"

    if has_any(texts, {"有耐心", "细腻", "慢热", "温和"}):
        patience_level = "高耐心"
    elif relationship_goal in {"认真恋爱", "结婚导向"}:
        patience_level = "耐心稳定"
    elif marriage_timeline == "半年内" and communication_style == "理性直接":
        patience_level = "节奏偏快"
    else:
        patience_level = "正常耐心"

    if (
        EDUCATION_ORDER.get(profile.get("education") or "", 0) >= EDUCATION_ORDER["硕士"]
        and has_any(texts, {"阅读", "看展", "摄影", "旅行", "咖啡", "画画", "烘焙", "手工"})
        and has_any(texts, {"能沟通", "善沟通", "真诚", "会做简单家常菜", "共同经营生活"})
    ):
        life_texture = "有见识也有生活感"
    elif job in CREATIVE_JOBS or has_any(texts, {"看展", "摄影", "旅行", "咖啡", "画画", "烘焙", "阅读", "手工"}):
        life_texture = "有生活感"
    else:
        life_texture = "简单稳定"

    if job in BUSY_JOBS:
        career_intensity = "高强度但可协调"
    elif job in STABLE_JOBS:
        career_intensity = "规律稳定"
    elif job in BRAINY_JOBS:
        career_intensity = "脑力投入型"
    else:
        career_intensity = "常规稳定"

    if has_any(texts, {"健身", "爱运动", "跑步", "徒步", "游泳", "羽毛球", "瑜伽"}):
        exercise_habit = "规律运动"
    elif has_any(texts, {"散步", "周末会出门走走", "养生"}):
        exercise_habit = "轻运动"
    else:
        exercise_habit = "运动不明显"

    income_numbers = [int(item) for item in re.findall(r"\d+", str(profile.get("income_range") or ""))]
    income_max = max(income_numbers) if income_numbers else 0
    education_rank = EDUCATION_ORDER.get(profile.get("education") or "", 0)

    if (
        job in UPWARD_JOBS and income_max >= 30
    ) or (education_rank >= EDUCATION_ORDER["硕士"] and income_max >= 35):
        growth_signal = "上升明确"
    elif job in STABLE_JOBS or income_max >= 24 or education_rank >= EDUCATION_ORDER["硕士"]:
        growth_signal = "平台成熟"
    elif relationship_goal in {"认真恋爱", "结婚导向"}:
        growth_signal = "稳步发展"
    else:
        growth_signal = "稳定型"

    if has_any(texts, {"善沟通", "好相处", "爱笑", "细腻", "真诚", "能接住话", "接住话", "不冷场", "不压人", "让人放松"}) and communication_style in {"主动沟通", "稳定沟通", "慢热少话"}:
        warmth_style = "有温度会接话"
    elif has_any(texts, {"理性", "边界清楚", "边界感强", "不端着"}) and has_any(texts, {"温和", "真诚", "有耐心", "不压人", "让人放松"}):
        warmth_style = "理性但不冷"
    elif communication_style == "慢热少话" or has_any(texts, {"安静"}):
        warmth_style = "偏克制"
    else:
        warmth_style = "正常温度"

    if (job in CREATIVE_JOBS or has_any(texts, {"摄影", "看展", "画画", "咖啡", "阅读", "烘焙", "手工"})) and expression_style == "会表达有生活感":
        aesthetic_expression = "有审美输出"
    elif life_texture in {"有见识也有生活感", "有生活感"}:
        aesthetic_expression = "有生活审美"
    else:
        aesthetic_expression = "普通"

    if has_any(texts, {"聊想法", "长期成长", "看展", "阅读", "写点东西", "研究", "判断", "有观点", "把复杂问题讲得有趣"}):
        conversation_resonance = "能聊想法也能聊日常"
    elif has_any(texts, {"真诚", "善沟通", "好相处", "简单真诚", "沟通顺畅", "有耐心", "能接住话", "不冷场"}):
        conversation_resonance = "会接话也会接情绪"
    elif has_any(texts, {"务实", "稳定踏实", "重视家庭", "愿意共同经营生活"}):
        conversation_resonance = "偏务实日常"
    else:
        conversation_resonance = "偏信息交换"

    if (
        aesthetic_expression == "有审美输出"
        and has_any(texts, {"看展", "摄影", "阅读", "画画", "烘焙", "咖啡", "写点东西", "长期成长"})
    ):
        personal_presence = "有记忆点"
    elif has_any(texts, {"温和", "真诚", "有耐心", "好相处", "细腻", "不压人", "让人放松"}):
        personal_presence = "温和耐看"
    else:
        personal_presence = "偏平"

    if has_any(texts, {"幽默", "有趣", "不端着", "松弛", "会开玩笑", "把复杂问题讲得有趣", "轻松一点", "不冷场", "让人放松", "不拖节奏", "不紧绷"}):
        lightness_humor = "有点幽默不端着"
    elif has_any(texts, {"温和", "有分寸", "理性", "边界清楚", "稳重", "不压人"}):
        lightness_humor = "稳重有分寸"
    else:
        lightness_humor = "偏克制"

    if has_any(texts, {"消费观正常", "不拜金", "不喜欢攀比", "量力而行", "务实"}) and has_any(
        texts, {"边界清楚", "对感情认真", "稳定踏实", "愿意共同经营生活"}
    ):
        consumption_attitude = "清醒务实"
    elif has_any(texts, {"消费观正常", "不拜金", "不喜欢攀比"}) and has_any(
        texts, {"看展", "旅行", "咖啡", "阅读", "喜欢做饭", "播客"}
    ):
        consumption_attitude = "有取舍会生活"
    elif has_any(texts, {"稳定踏实", "重视家庭", "爱逛菜场", "喜欢做饭", "偏宅"}):
        consumption_attitude = "踏实过日子"
    else:
        consumption_attitude = "表达不明显"

    if has_any(texts, {"会开玩笑", "有趣", "把复杂问题讲得有趣", "不冷场", "脱口秀", "有梗", "不端着"}):
        chat_texture = "有梗也有内容"
    elif has_any(texts, {"能接住话", "接住话", "顺着聊", "不压人", "让人放松", "不费劲", "相处舒服"}):
        chat_texture = "顺着聊不费劲"
    elif warmth_style in {"有温度会接话", "理性但不冷"} or conversation_resonance in {
        "能聊想法也能聊日常",
        "会接话也会接情绪",
    }:
        chat_texture = "稳重顺聊"
    else:
        chat_texture = "偏功能聊天"

    if relationship_goal == "结婚导向" and marriage_timeline in {"半年内", "1年内"}:
        commitment_clarity = "明确奔着长期"
    elif has_any(texts, {"认真找长期关系", "不爱反复试探", "长期打算说清楚", "不想把时间耗在反复试探上"}):
        commitment_clarity = "明确奔着长期"
    elif relationship_goal in {"认真恋爱", "结婚导向"}:
        commitment_clarity = "愿意稳定推进"
    else:
        commitment_clarity = "先聊熟再说"

    if has_any(texts, {"聊明白", "说清楚", "提前商量", "安排说清", "边界聊透", "不爱反复试探", "不拖节奏", "现实安排"}):
        relationship_execution = "会把安排说清"
    elif commitment_clarity == "明确奔着长期" or has_any(texts, {"认真推进", "认真找长期关系", "认真相处"}):
        relationship_execution = "稳步推进不拖拉"
    elif relationship_goal == "先接触看看" or has_any(texts, {"先聊聊", "先看感觉", "慢慢了解"}):
        relationship_execution = "先聊熟再定"
    else:
        relationship_execution = "口头长期待验证"

    marital_strength = profile.get("accept_marital_status_strength") or ""
    child_strength = profile.get("accept_partner_children_strength") or ""
    accept_partner_children = profile.get("accept_partner_children") or ""
    if marital_strength == "明确接受" and child_strength == "明确接受":
        blended_family_readiness = "已想过现实安排"
    elif "明确接受" in {marital_strength, child_strength} or {"谨慎接受"} & {marital_strength, child_strength}:
        blended_family_readiness = "愿意一起商量"
    elif accept_partner_children == "可协商" or "短期可聊" in {marital_strength, child_strength}:
        blended_family_readiness = "仅口头接受"
    else:
        blended_family_readiness = "未知"

    return {
        "life_routine": life_routine,
        "communication_style": communication_style,
        "dating_pace": dating_pace,
        "expression_style": expression_style,
        "relationship_capacity": relationship_capacity,
        "interaction_comfort": interaction_comfort,
        "patience_level": patience_level,
        "life_texture": life_texture,
        "career_intensity": career_intensity,
        "exercise_habit": exercise_habit,
        "growth_signal": growth_signal,
        "warmth_style": warmth_style,
        "aesthetic_expression": aesthetic_expression,
        "conversation_resonance": conversation_resonance,
        "personal_presence": personal_presence,
        "lightness_humor": lightness_humor,
        "consumption_attitude": consumption_attitude,
        "chat_texture": chat_texture,
        "commitment_clarity": commitment_clarity,
        "relationship_execution": relationship_execution,
        "blended_family_readiness": blended_family_readiness,
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
        base_columns = [
            "id",
            "age",
            "gender",
            "education",
            "job",
            "relationship_goal",
            "marriage_timeline",
            "personality",
            "values",
            "lifestyle",
            "hobbies",
            "notes",
            "marital_status",
            "accept_marital_status",
            "accept_partner_children",
            "source_channel",
        ]
        select_columns = base_columns + [
            column for column in BACKFILL_UPDATE_COLUMNS if column not in base_columns
        ]
        with conn.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {", ".join(f"`{column}`" for column in select_columns)}
                FROM `{args.table}`
                """
            )
            rows = cursor.fetchall()

        updates = []
        for row in rows:
            enriched = {}
            enriched.update(infer_strictness(row))
            acceptance = infer_acceptance(row)
            enriched.update(acceptance)
            enriched.update(infer_structured_style(dict(row, **acceptance)))
            enriched = preserve_curated_backfill(row, enriched)
            enriched["id"] = row["id"]
            updates.append(enriched)

        assignments = ", ".join(f"`{column}`=%s" for column in BACKFILL_UPDATE_COLUMNS)
        sql = f"UPDATE `{args.table}` SET {assignments} WHERE `id`=%s"

        with conn.cursor() as cursor:
            cursor.executemany(
                sql,
                [
                    tuple(item[column] for column in BACKFILL_UPDATE_COLUMNS) + (item["id"],)
                    for item in updates
                ],
            )
        conn.commit()
        print(f"Backfilled {len(updates)} profiles in {args.database}.{args.table}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
