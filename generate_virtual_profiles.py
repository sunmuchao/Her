#!/usr/bin/env python3

import argparse
import csv
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from persona_memory_sync.synthetic_personality_traits import build_synthetic_personality_traits


OUTPUT_PATH = Path(__file__).resolve().parent / "virtual_profiles_10000.csv"
PHOTOS_OUTPUT_PATH = Path(__file__).resolve().parent / "virtual_profile_photos_10000.csv"
ROW_COUNT = 10_000
SEED = 20260428
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

DEFAULT_MYSQL = {
    "host": "127.0.0.1",
    "port": 3307,
    "user": "root",
    "password": "",
    "database": "her",
    "table": "profiles",
    "charset": "utf8mb4",
}

FIELDNAMES = [
    "id",
    "name",
    "avatar_url",
    "photo_count",
    "gender",
    "sexual_orientation",  # ✅ 新增：性取向字段
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
    "relationship_goal",
    "preferred_age_min",
    "preferred_age_max",
    "preferred_cities",
    "preferred_height_min",
    "preferred_height_max",
    "preferred_education_min",
    "preferred_income_min_wan",
    "preferred_income_max_wan",
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
    "has_children",
    "children_count",
    "children_living_with_self",
    "want_children",
    "accept_partner_children",
    "marriage_timeline",
    "family_background",
    "notes",
    "profile_status",
    "last_active_at",
    "verified_level",
    "source_channel",
    "created_at",
    "updated_at",
]

PHOTO_FIELDNAMES = [
    "profile_id",
    "photo_url",
    "photo_type",
    "sort_order",
    "is_primary",
    "created_at",
    "updated_at",
]

PROFILE_DB_COLUMNS = [
    "id",
    "name",
    "gender",
    "sexual_orientation",
    "age",
    "city",
    "education",
    "job",
    "income_range",
    "marital_status",
    "has_children",
    "relationship_goal",
    "profile_status",
    "verified_level",
    "photo_count",
    "life_routine",
    "communication_style",
    "values",
    "notes",
    "last_active_at",
    "public_display_name",
    "public_education",
    "public_job",
    "public_personality",
    "public_values",
    "public_notes",
]

PERSONA_DB_COLUMNS = [
    "user_key",
    "display_name",
    "profile_id",
    # 硬条件字段已删除，这些字段应该只在 profiles 表中
    # self_gender, self_age, self_city, self_district, self_height, self_education,
    # self_income_wan, self_job, self_marital_status, self_has_children,
    # self_children_count, self_children_living_with_self,
    # self_smoking, self_drinking, self_relationship_goal 已删除
    # target_gender 已移动到 profiles 表（硬条件）
    # 不可量化字段已删除：self_life_rhythm, self_work_pattern, self_expression_style, preferred_traits
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
    # preferred_traits 已删除（不可量化：性格特质偏好）
    # must_have_tags 和 must_not_have_tags 已删除
    "self_personality_traits_json",
    "created_at",
    "updated_at",
]

PHOTO_DB_COLUMNS = [
    "profile_id",
    "photo_url",
    "is_primary",
    "sort_order",
]

HER_USER_TABLES = (
    "partner_search_snapshots",
    "user_persona_observations",
    "user_personas",
    "profile_photos",
    "profiles",
)

OTHER_USER_DATABASES = (
    "her_chat",
    "her_discovery",
    "her_matchmaking",
    "her_recommendation",
    "her_relationship_ledger",
)

CITY_DISTRICTS = {
    "无锡": ["梁溪区", "滨湖区", "锡山区", "惠山区", "新吴区", "江阴市", "宜兴市"],
    "苏州": ["姑苏区", "工业园区", "高新区", "吴中区", "相城区", "昆山市", "常熟市"],
    "常州": ["天宁区", "钟楼区", "新北区", "武进区", "金坛区", "溧阳市"],
    "南京": ["玄武区", "秦淮区", "建邺区", "鼓楼区", "江宁区", "浦口区"],
    "上海": ["浦东新区", "徐汇区", "静安区", "长宁区", "闵行区", "杨浦区"],
    "杭州": ["西湖区", "拱墅区", "上城区", "滨江区", "余杭区", "萧山区"],
    "南通": ["崇川区", "通州区", "海门区", "启东市", "如皋市"],
    "扬州": ["广陵区", "邗江区", "江都区", "高邮市", "仪征市"],
    "宁波": ["海曙区", "江北区", "鄞州区", "镇海区", "北仑区", "余姚市"],
    "镇江": ["京口区", "润州区", "丹徒区", "丹阳市", "句容市"],
    "泰州": ["海陵区", "高港区", "姜堰区", "靖江市", "泰兴市"],
    "嘉兴": ["南湖区", "秀洲区", "海宁市", "桐乡市", "嘉善县"],
    "湖州": ["吴兴区", "南浔区", "德清县", "长兴县", "安吉县"],
}

NEARBY_CITIES = {
    "无锡": ["苏州", "常州", "上海", "南京"],
    "苏州": ["无锡", "上海", "嘉兴", "湖州"],
    "常州": ["无锡", "南京", "镇江", "苏州"],
    "南京": ["常州", "镇江", "扬州", "上海"],
    "上海": ["苏州", "无锡", "嘉兴", "杭州"],
    "杭州": ["嘉兴", "湖州", "上海", "宁波"],
    "南通": ["上海", "苏州", "扬州", "泰州"],
    "扬州": ["镇江", "南京", "泰州", "南通"],
    "宁波": ["杭州", "嘉兴", "湖州", "上海"],
    "镇江": ["南京", "常州", "扬州", "泰州"],
    "泰州": ["扬州", "镇江", "南通", "常州"],
    "嘉兴": ["上海", "苏州", "杭州", "湖州"],
    "湖州": ["杭州", "嘉兴", "苏州", "无锡"],
}

CITY_WEIGHTS = [
    ("无锡", 18),
    ("苏州", 11),
    ("常州", 8),
    ("南京", 7),
    ("上海", 7),
    ("杭州", 6),
    ("南通", 5),
    ("扬州", 4),
    ("宁波", 4),
    ("镇江", 3),
    ("泰州", 3),
    ("嘉兴", 2),
    ("湖州", 2),
]

HOMETOWNS = [
    "无锡", "苏州", "常州", "南京", "上海", "杭州", "南通", "扬州",
    "宁波", "镇江", "泰州", "嘉兴", "湖州", "合肥", "盐城", "绍兴",
]

MALE_SURNAMES = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴", "徐", "孙", "胡", "朱", "高"]
FEMALE_SURNAMES = MALE_SURNAMES + ["林", "何", "郭", "马", "罗", "梁", "宋", "郑", "谢", "韩", "唐", "冯", "于", "董", "萧"]
MALE_GIVEN_1 = ["宇", "泽", "辰", "子", "景", "嘉", "奕", "思", "俊", "浩", "铭", "承", "睿", "柏", "亦", "安"]
MALE_GIVEN_2 = ["轩", "阳", "航", "峰", "远", "霖", "川", "宁", "哲", "骁", "衡", "卓", "凯", "瑞", "城", "言"]
FEMALE_GIVEN_1 = ["若", "雨", "欣", "语", "可", "子", "安", "依", "书", "念", "静", "佳", "清", "梦", "以", "沐", "思", "舒", "芷", "星"]
FEMALE_GIVEN_2 = ["彤", "涵", "宁", "瑶", "然", "悦", "妍", "婷", "菲", "怡", "文", "萌", "岚", "晨", "琪", "琳", "雅", "嘉", "心", "雯"]

EDUCATION_LEVELS = ["大专", "专升本", "本科", "硕士", "博士"]
EDUCATION_RANK = {name: idx for idx, name in enumerate(EDUCATION_LEVELS, start=1)}
EDUCATION_WEIGHTS = [
    ("大专", 16),
    ("专升本", 5),
    ("本科", 50),
    ("硕士", 25),
    ("博士", 4),
]

JOBS = [
    {"title": "后端工程师", "education": ["本科", "硕士"], "income": [(24, 38), (30, 48)]},
    {"title": "前端工程师", "education": ["本科", "硕士"], "income": [(20, 34), (26, 40)]},
    {"title": "软件测试", "education": ["本科"], "income": [(15, 24), (18, 30)]},
    {"title": "数据分析", "education": ["本科", "硕士"], "income": [(18, 28), (24, 38)]},
    {"title": "产品经理", "education": ["本科", "硕士"], "income": [(18, 30), (24, 42)]},
    {"title": "产品运营", "education": ["本科", "硕士"], "income": [(14, 22), (18, 30)]},
    {"title": "品牌策划", "education": ["本科"], "income": [(14, 22), (18, 30)]},
    {"title": "新媒体运营", "education": ["本科"], "income": [(10, 18), (12, 22)]},
    {"title": "教师", "education": ["本科", "硕士"], "income": [(12, 18), (15, 24)]},
    {"title": "医生", "education": ["硕士", "博士"], "income": [(25, 40), (35, 60)]},
    {"title": "护士", "education": ["大专", "本科"], "income": [(10, 16), (12, 18)]},
    {"title": "药师", "education": ["本科", "硕士"], "income": [(12, 20), (16, 26)]},
    {"title": "公务员", "education": ["本科", "硕士"], "income": [(12, 18), (15, 24)]},
    {"title": "事业单位职员", "education": ["本科"], "income": [(10, 16), (12, 22)]},
    {"title": "银行职员", "education": ["本科", "硕士"], "income": [(14, 22), (18, 30)]},
    {"title": "审计", "education": ["本科", "硕士"], "income": [(15, 25), (18, 34)]},
    {"title": "法务", "education": ["本科", "硕士"], "income": [(16, 26), (22, 40)]},
    {"title": "行政", "education": ["大专", "本科"], "income": [(8, 12), (10, 16)]},
    {"title": "人事", "education": ["本科"], "income": [(10, 15), (12, 18)]},
    {"title": "财务", "education": ["本科", "硕士"], "income": [(12, 18), (16, 28)]},
    {"title": "会计", "education": ["本科"], "income": [(10, 16), (12, 20)]},
    {"title": "外贸业务", "education": ["本科"], "income": [(12, 20), (15, 30)]},
    {"title": "采购", "education": ["本科"], "income": [(12, 18), (15, 24)]},
    {"title": "招商主管", "education": ["本科"], "income": [(15, 24), (18, 34)]},
    {"title": "翻译", "education": ["本科", "硕士"], "income": [(12, 18), (15, 24)]},
    {"title": "设计师", "education": ["本科"], "income": [(12, 20), (15, 28)]},
    {"title": "UI设计", "education": ["本科"], "income": [(14, 22), (18, 28)]},
    {"title": "课程顾问", "education": ["大专", "本科"], "income": [(10, 16), (12, 20)]},
]

PERSONALITY_POOL = [
    "情绪稳定", "慢热", "温和", "有耐心", "边界感强", "真诚", "独立", "开朗",
    "细腻", "理性", "乐观", "善沟通", "有责任感", "顾家", "有主见", "务实",
    "安静", "爱笑", "松弛", "好相处",
]

VALUES_POOL = [
    "消费观正常", "不拜金", "务实", "三观正", "重视家庭", "愿意共同经营生活",
    "对感情认真", "边界清楚", "尊重彼此空间", "不喜欢攀比", "稳定踏实", "能沟通",
]

LIFESTYLE_POOL = [
    "生活规律", "规律作息", "不熬夜", "喜欢做饭", "爱运动", "周末会出门走走",
    "干净整洁", "喜欢咖啡馆", "偶尔短途旅行", "偏宅", "养生", "爱逛菜场",
]

HOBBIES_POOL = [
    "羽毛球", "游泳", "散步", "徒步", "瑜伽", "阅读", "烘焙", "摄影",
    "旅行", "电影", "桌游", "画画", "猫狗", "手工", "咖啡", "看展",
]

FAMILY_BACKGROUND_POOL = [
    "家庭关系简单",
    "父母在本地工作生活",
    "父母已退休",
    "独生子女，家庭氛围和睦",
    "有一个兄弟姐妹，关系不错",
    "普通家庭，重视教育",
    "家庭稳定，父母感情和睦",
]

SOURCE_CHANNEL_WEIGHTS = [
    ("app", 38),
    ("朋友介绍", 18),
    ("同事同学", 12),
    ("相亲群", 14),
    ("线下活动", 10),
    ("家人介绍", 8),
]

PROFILE_STATUS_WEIGHTS = [
    ("active", 82),
    ("paused", 8),
    ("matched", 5),
    ("archived", 5),
]

VERIFIED_WEIGHTS = {
    "app": [("none", 25), ("basic", 34), ("photo", 24), ("id", 14), ("offline", 3)],
    "相亲群": [("none", 30), ("basic", 28), ("photo", 22), ("id", 15), ("offline", 5)],
    "朋友介绍": [("none", 8), ("basic", 18), ("photo", 18), ("id", 28), ("offline", 28)],
    "家人介绍": [("none", 5), ("basic", 12), ("photo", 15), ("id", 28), ("offline", 40)],
    "同事同学": [("none", 10), ("basic", 18), ("photo", 18), ("id", 30), ("offline", 24)],
    "线下活动": [("none", 12), ("basic", 20), ("photo", 24), ("id", 24), ("offline", 20)],
}

SMOKING_WEIGHTS = [("否", 86), ("偶尔", 8), ("是", 6)]
DRINKING_WEIGHTS = [("否", 34), ("偶尔", 54), ("是", 12)]
LONG_DISTANCE_WEIGHTS = [("不接受", 46), ("可协商", 40), ("接受", 14)]
ACCEPT_BINARY_WEIGHTS = [("不接受", 44), ("可协商", 40), ("接受", 16)]
WANT_CHILDREN_WEIGHTS = [("想要", 58), ("可协商", 26), ("不要", 8), ("未知", 8)]
MARRIAGE_TIMELINE_WEIGHTS = [
    ("半年内", 8),
    ("1年内", 22),
    ("2年内", 20),
    ("合适就结婚", 34),
    ("暂不考虑", 8),
    ("未知", 8),
]
HOUSING_WEIGHTS = [("已购房", 28), ("租房", 30), ("与家人同住", 18), ("无房", 12), ("可协商", 8), ("未知", 4)]
CAR_WEIGHTS = [("有车", 34), ("无车", 36), ("计划购车", 14), ("可协商", 10), ("未知", 6)]


def weighted_choice(rng, items):
    values = [item[0] for item in items]
    weights = [item[1] for item in items]
    return rng.choices(values, weights=weights, k=1)[0]


def split_items(value):
    return [item.strip() for item in str(value).split(",") if item.strip()]


def unique_keep_order(items):
    seen = set()
    result = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def format_income_range(min_wan, max_wan):
    return f"{min_wan}-{max_wan}万/年"


def choose_gender(rng):
    return weighted_choice(rng, [("女", 53), ("男", 47)])


def choose_sexual_orientation(rng, gender):
    """生成性取向字段

    大部分用户是异性恋（90%），小部分是同性恋（10%）
    - 男性：90% like_female（喜欢女性），10% like_male（喜欢男性）
    - 女性：90% like_male（喜欢男性），10% like_female（喜欢女性）
    """
    if gender == "男":
        # 男性：90%异性恋（喜欢女性），10%同性恋（喜欢男性）
        return weighted_choice(rng, [("like_female", 90), ("like_male", 10)])
    else:
        # 女性：90%异性恋（喜欢男性），10%同性恋（喜欢女性）
        return weighted_choice(rng, [("like_male", 90), ("like_female", 10)])


def choose_name(rng, gender):
    if gender == "男":
        return rng.choice(MALE_SURNAMES) + rng.choice(MALE_GIVEN_1) + rng.choice(MALE_GIVEN_2)
    return rng.choice(FEMALE_SURNAMES) + rng.choice(FEMALE_GIVEN_1) + rng.choice(FEMALE_GIVEN_2)


def choose_photo_assets(rng, profile_id, verified_level, source_channel):
    if verified_level == "none":
        photo_count = rng.randint(2, 4)
    elif verified_level == "basic":
        photo_count = rng.randint(3, 5)
    elif verified_level == "photo":
        photo_count = rng.randint(4, 6)
    elif verified_level == "id":
        photo_count = rng.randint(4, 7)
    else:
        photo_count = rng.randint(5, 8)

    if source_channel in {"朋友介绍", "家人介绍", "线下活动"} and photo_count < 4 and rng.random() < 0.5:
        photo_count += 1

    base = f"https://cdn.her.local/profiles/{profile_id:05d}"
    avatar_url = f"{base}/avatar.jpg"
    photo_urls = [f"{base}/photo_{index}.jpg" for index in range(1, photo_count + 1)]
    return avatar_url, photo_urls


def build_photo_records(profile_id, avatar_url, photo_urls, created_at, updated_at):
    records = [
        {
            "profile_id": profile_id,
            "photo_url": avatar_url,
            "photo_type": "avatar",
            "sort_order": 0,
            "is_primary": 1,
            "created_at": created_at,
            "updated_at": updated_at,
        }
    ]
    for index, photo_url in enumerate(photo_urls, start=1):
        records.append(
            {
                "profile_id": profile_id,
                "photo_url": photo_url,
                "photo_type": "gallery",
                "sort_order": index,
                "is_primary": 0,
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )
    return records


def choose_age(rng):
    bands = [(23, 24, 8), (25, 27, 28), (28, 30, 34), (31, 33, 20), (34, 36, 10)]
    band = weighted_choice(rng, [((lo, hi), weight) for lo, hi, weight in bands])
    return rng.randint(band[0], band[1])


def choose_height(rng, gender):
    if gender == "男":
        return rng.randint(168, 188)
    return rng.randint(156, 173)


def choose_city(rng):
    return weighted_choice(rng, CITY_WEIGHTS)


def choose_district(rng, city):
    return rng.choice(CITY_DISTRICTS[city])


def choose_job_bundle(rng, city):
    job = rng.choice(JOBS)
    education = rng.choice(job["education"])
    income_min, income_max = rng.choice(job["income"])
    if city in {"上海", "杭州", "南京"}:
        income_min += 2
        income_max += 4
    elif city in {"无锡", "苏州"}:
        income_min += 1
        income_max += 2
    return job["title"], education, income_min, income_max


def maybe_bump_education(rng, education):
    if rng.random() >= 0.14:
        return education
    idx = EDUCATION_LEVELS.index(education)
    if idx + 1 < len(EDUCATION_LEVELS):
        return EDUCATION_LEVELS[idx + 1]
    return education


def choose_traits(rng, pool, count):
    return ", ".join(rng.sample(pool, count))


def ensure_tag(rng, text, tag, probability):
    items = split_items(text)
    if tag not in items and rng.random() < probability:
        items[0] = tag
    return ", ".join(unique_keep_order(items))


def choose_relationship_goal(rng, age):
    if age >= 31:
        return weighted_choice(rng, [("结婚导向", 50), ("认真恋爱", 36), ("先接触看看", 14)])
    if age <= 25:
        return weighted_choice(rng, [("认真恋爱", 52), ("结婚导向", 22), ("先接触看看", 26)])
    return weighted_choice(rng, [("认真恋爱", 48), ("结婚导向", 34), ("先接触看看", 18)])


def choose_marital_status(rng, age):
    if age <= 27:
        return weighted_choice(rng, [("未婚", 98), ("离异未育", 1), ("离异已育", 1)])
    if age <= 31:
        return weighted_choice(rng, [("未婚", 94), ("离异未育", 4), ("离异已育", 2)])
    return weighted_choice(rng, [("未婚", 88), ("离异未育", 7), ("离异已育", 5)])


def choose_children_info(rng, marital_status):
    if marital_status == "离异已育":
        count = weighted_choice(rng, [(1, 72), (2, 24), (3, 4)])
        living_with_self = weighted_choice(rng, [(1, 64), (0, 36)])
        return 1, count, living_with_self
    return 0, 0, 0


def choose_settlement_city(rng, city, relationship_goal):
    if relationship_goal == "结婚导向" and rng.random() < 0.86:
        return city
    if rng.random() < 0.72:
        return city
    return rng.choice(NEARBY_CITIES[city])


def choose_housing_status(rng, age, income_max, relationship_goal):
    items = list(HOUSING_WEIGHTS)
    if age >= 30 or income_max >= 30 or relationship_goal == "结婚导向":
        items = [("已购房", 40), ("租房", 24), ("与家人同住", 12), ("无房", 8), ("可协商", 10), ("未知", 6)]
    return weighted_choice(rng, items)


def choose_car_status(rng, age, income_max):
    items = list(CAR_WEIGHTS)
    if age >= 28 or income_max >= 24:
        items = [("有车", 46), ("无车", 24), ("计划购车", 16), ("可协商", 8), ("未知", 6)]
    return weighted_choice(rng, items)


def choose_source_channel(rng):
    return weighted_choice(rng, SOURCE_CHANNEL_WEIGHTS)


def choose_profile_status(rng, relationship_goal):
    if relationship_goal == "结婚导向":
        return weighted_choice(rng, [("active", 84), ("paused", 6), ("matched", 6), ("archived", 4)])
    return weighted_choice(rng, PROFILE_STATUS_WEIGHTS)


def choose_verified_level(rng, source_channel, profile_status):
    level = weighted_choice(rng, VERIFIED_WEIGHTS[source_channel])
    if profile_status == "matched" and level in {"none", "basic"} and rng.random() < 0.45:
        return "offline"
    return level


def choose_activity_window_days(profile_status):
    if profile_status == "active":
        return 14
    if profile_status == "paused":
        return 90
    if profile_status == "matched":
        return 45
    return 180


def choose_timestamps(rng, profile_status):
    now = datetime.now().replace(microsecond=0)
    created_days_ago = rng.randint(20, 720)
    created_at = now - timedelta(days=created_days_ago, hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
    active_window = choose_activity_window_days(profile_status)
    updated_at = now - timedelta(days=rng.randint(0, active_window), hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
    if updated_at < created_at:
        updated_at = created_at + timedelta(days=rng.randint(0, 3), hours=rng.randint(0, 23))
    last_active_at = updated_at
    return (
        created_at.strftime(DATETIME_FORMAT),
        updated_at.strftime(DATETIME_FORMAT),
        last_active_at.strftime(DATETIME_FORMAT),
    )


def choose_preferred_age_range(rng, gender, age):
    if gender == "男":
        min_age = max(22, age - rng.randint(2, 6))
        max_age = min(36, age + rng.randint(0, 2))
    else:
        min_age = max(23, age - rng.randint(1, 3))
        max_age = min(42, age + rng.randint(4, 8))
    if min_age > max_age:
        min_age, max_age = max_age, min_age
    return min_age, max_age


def choose_preferred_height_range(rng, gender, height):
    if gender == "男":
        min_height = rng.randint(155, min(168, height))
        max_height = min(176, height + rng.randint(-2, 4))
    else:
        min_height = max(168, height + rng.randint(4, 8))
        max_height = min(195, min_height + rng.randint(8, 16))
    if min_height > max_height:
        min_height, max_height = max_height, min_height
    return min_height, max_height


def choose_preferred_education_min(rng, own_education):
    own_rank = EDUCATION_RANK[own_education]
    offset = weighted_choice(rng, [(-1, 24), (0, 56), (1, 20)])
    desired_rank = max(1, min(len(EDUCATION_LEVELS), own_rank + offset))
    return EDUCATION_LEVELS[desired_rank - 1]


def choose_preferred_income_range(rng, gender, income_min, income_max, values):
    midpoint = (income_min + income_max) // 2
    if "不喜欢攀比" in values or "务实" in values:
        floor = max(8, midpoint - rng.randint(4, 10))
    elif gender == "女":
        floor = max(10, midpoint - rng.randint(0, 6))
    else:
        floor = max(8, midpoint - rng.randint(6, 12))
    ceiling = max(floor, midpoint + rng.randint(8, 22))
    return floor, ceiling


def choose_preferred_cities(rng, city, accept_long_distance):
    cities = [city]
    nearby = list(NEARBY_CITIES[city])
    rng.shuffle(nearby)
    if accept_long_distance == "接受":
        cities.extend(nearby[: rng.randint(2, 4)])
    elif accept_long_distance == "可协商":
        cities.extend(nearby[: rng.randint(1, 2)])
    return ", ".join(unique_keep_order(cities))


def choose_accept_marital_status(rng, age, marital_status):
    if marital_status == "离异已育":
        statuses = ["未婚", "离异未育", "离异已育"]
    elif marital_status == "离异未育":
        statuses = ["未婚", "离异未育"]
    elif age >= 31 and rng.random() < 0.42:
        statuses = ["未婚", "离异未育"]
    else:
        statuses = ["未婚"]
    return ", ".join(statuses)


def choose_accept_habit(rng, own_habit, values):
    if own_habit == "否" and ("边界清楚" in values or "三观正" in values):
        return weighted_choice(rng, [("不接受", 54), ("可协商", 34), ("接受", 12)])
    if own_habit == "偶尔":
        return weighted_choice(rng, [("可协商", 52), ("接受", 28), ("不接受", 20)])
    if own_habit == "是":
        return weighted_choice(rng, [("接受", 60), ("可协商", 28), ("不接受", 12)])
    return weighted_choice(rng, ACCEPT_BINARY_WEIGHTS)


def choose_want_children(rng, age, relationship_goal):
    if relationship_goal == "结婚导向":
        return weighted_choice(rng, [("想要", 66), ("可协商", 22), ("不要", 4), ("未知", 8)])
    if age <= 25:
        return weighted_choice(rng, [("想要", 46), ("可协商", 32), ("不要", 12), ("未知", 10)])
    return weighted_choice(rng, WANT_CHILDREN_WEIGHTS)


def choose_accept_partner_children(rng, age, marital_status):
    if marital_status.startswith("离异"):
        return weighted_choice(rng, [("接受", 52), ("可协商", 34), ("不接受", 10), ("未知", 4)])
    if age >= 31:
        return weighted_choice(rng, [("不接受", 34), ("可协商", 38), ("接受", 18), ("未知", 10)])
    return weighted_choice(rng, [("不接受", 58), ("可协商", 26), ("接受", 8), ("未知", 8)])


def choose_marriage_timeline(rng, age, relationship_goal):
    if relationship_goal == "结婚导向":
        return weighted_choice(rng, [("半年内", 12), ("1年内", 32), ("2年内", 22), ("合适就结婚", 24), ("暂不考虑", 2), ("未知", 8)])
    if relationship_goal == "先接触看看":
        return weighted_choice(rng, [("半年内", 2), ("1年内", 8), ("2年内", 18), ("合适就结婚", 28), ("暂不考虑", 32), ("未知", 12)])
    if age >= 30:
        return weighted_choice(rng, [("半年内", 8), ("1年内", 24), ("2年内", 24), ("合适就结婚", 30), ("暂不考虑", 4), ("未知", 10)])
    return weighted_choice(rng, MARRIAGE_TIMELINE_WEIGHTS)


def build_notes(rng, city, hobbies, relationship_goal, settlement_city):
    hobby1, hobby2 = hobbies[:2]
    templates = [
        f"工作稳定，周末喜欢{hobby1}和{hobby2}",
        "平时作息规律，比较看重相处舒服和沟通顺畅",
        f"在{city}生活多年，希望找长期稳定关系",
        "社交圈不复杂，喜欢简单真诚的相处方式",
        f"会做简单家常菜，休息时常去{hobby1}",
        "对未来有规划，希望两个人能一起成长",
        f"有长期在{settlement_city}定居的打算，倾向认真相处",
    ]
    if relationship_goal == "先接触看看":
        templates.append("希望先从自然接触开始，合适再进一步发展")
    return rng.choice(templates)


def make_record(rng, profile_id):
    gender = choose_gender(rng)
    sexual_orientation = choose_sexual_orientation(rng, gender)  # ✅ 新增：生成性取向
    age = choose_age(rng)
    city = choose_city(rng)
    district = choose_district(rng, city)
    height = choose_height(rng, gender)
    job, education, income_min, income_max = choose_job_bundle(rng, city)
    education = maybe_bump_education(rng, education)
    income_range = format_income_range(income_min, income_max)
    relationship_goal = choose_relationship_goal(rng, age)
    marital_status = choose_marital_status(rng, age)
    has_children, children_count, children_living_with_self = choose_children_info(rng, marital_status)
    source_channel = choose_source_channel(rng)
    profile_status = choose_profile_status(rng, relationship_goal)
    verified_level = choose_verified_level(rng, source_channel, profile_status)
    created_at, updated_at, last_active_at = choose_timestamps(rng, profile_status)
    avatar_url, photo_urls_list = choose_photo_assets(rng, profile_id, verified_level, source_channel)
    photo_count = len(photo_urls_list)

    personality = choose_traits(rng, PERSONALITY_POOL, 3)
    values = choose_traits(rng, VALUES_POOL, 3)
    lifestyle = choose_traits(rng, LIFESTYLE_POOL, 3)
    personality = ensure_tag(rng, personality, "情绪稳定", 0.42)
    values = ensure_tag(rng, values, "消费观正常", 0.48)

    hobbies = rng.sample(HOBBIES_POOL, 2)
    smoking = weighted_choice(rng, SMOKING_WEIGHTS)
    drinking = weighted_choice(rng, DRINKING_WEIGHTS)
    long_distance = weighted_choice(rng, LONG_DISTANCE_WEIGHTS)
    accept_long_distance = long_distance if rng.random() < 0.72 else weighted_choice(rng, ACCEPT_BINARY_WEIGHTS)

    preferred_age_min, preferred_age_max = choose_preferred_age_range(rng, gender, age)
    preferred_height_min, preferred_height_max = choose_preferred_height_range(rng, gender, height)
    preferred_education_min = choose_preferred_education_min(rng, education)
    preferred_income_min_wan, preferred_income_max_wan = choose_preferred_income_range(
        rng, gender, income_min, income_max, values
    )
    preferred_cities = choose_preferred_cities(rng, city, accept_long_distance)

    accept_smoking = choose_accept_habit(rng, smoking, values)
    accept_drinking = choose_accept_habit(rng, drinking, values)
    accept_marital_status = choose_accept_marital_status(rng, age, marital_status)
    want_children = choose_want_children(rng, age, relationship_goal)
    accept_partner_children = choose_accept_partner_children(rng, age, marital_status)
    marriage_timeline = choose_marriage_timeline(rng, age, relationship_goal)

    settlement_city = choose_settlement_city(rng, city, relationship_goal)
    housing_status = choose_housing_status(rng, age, income_max, relationship_goal)
    car_status = choose_car_status(rng, age, income_max)
    family_background = rng.choice(FAMILY_BACKGROUND_POOL)

    record = {
        "id": profile_id,
        "name": choose_name(rng, gender),
        "avatar_url": avatar_url,
        "photo_count": photo_count,
        "gender": gender,
        "sexual_orientation": sexual_orientation,  # ✅ 新增：性取向字段
        "age": age,
        "city": city,
        "district": district,
        "hometown": rng.choice(HOMETOWNS),
        "settlement_city": settlement_city,
        "housing_status": housing_status,
        "car_status": car_status,
        "height": height,
        "education": education,
        "job": job,
        "income_range": income_range,
        "relationship_goal": relationship_goal,
        "preferred_age_min": preferred_age_min,
        "preferred_age_max": preferred_age_max,
        "preferred_cities": preferred_cities,
        "preferred_height_min": preferred_height_min,
        "preferred_height_max": preferred_height_max,
        "preferred_education_min": preferred_education_min,
        "preferred_income_min_wan": preferred_income_min_wan,
        "preferred_income_max_wan": preferred_income_max_wan,
        "personality": personality,
        "values": values,
        "lifestyle": lifestyle,
        "hobbies": ", ".join(hobbies),
        "smoking": smoking,
        "drinking": drinking,
        "long_distance": long_distance,
        "accept_long_distance": accept_long_distance,
        "accept_smoking": accept_smoking,
        "accept_drinking": accept_drinking,
        "accept_marital_status": accept_marital_status,
        "marital_status": marital_status,
        "has_children": has_children,
        "children_count": children_count,
        "children_living_with_self": children_living_with_self,
        "want_children": want_children,
        "accept_partner_children": accept_partner_children,
        "marriage_timeline": marriage_timeline,
        "family_background": family_background,
        "notes": build_notes(rng, city, hobbies, relationship_goal, settlement_city),
        "profile_status": profile_status,
        "last_active_at": last_active_at,
        "verified_level": verified_level,
        "source_channel": source_channel,
        "created_at": created_at,
        "updated_at": updated_at,
    }
    return record, photo_urls_list


def generate_records(row_count, seed):
    rng = random.Random(seed)
    records = []
    photo_records = []
    for profile_id in range(1, row_count + 1):
        record, photo_urls_list = make_record(rng, profile_id)
        records.append(record)
        photo_records.extend(
            build_photo_records(
                profile_id=record["id"],
                avatar_url=record["avatar_url"],
                photo_urls=photo_urls_list,
                created_at=record["created_at"],
                updated_at=record["updated_at"],
            )
        )
    return records, photo_records


def write_csv(path, fieldnames, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def income_midpoint_wan(record: dict) -> int:
    text = str(record.get("income_range") or "")
    digits = [int(part) for part in text.replace("万/年", "").split("-") if part.isdigit()]
    if len(digits) >= 2:
        return (digits[0] + digits[1]) // 2
    if digits:
        return digits[0]
    return 0


def opposite_gender(gender: str) -> str:
    if gender == "男":
        return "女"
    if gender == "女":
        return "男"
    return "不限"


def to_profile_row(record: dict) -> dict:
    personality = str(record.get("personality") or "")
    values = str(record.get("values") or "")
    lifestyle = str(record.get("lifestyle") or "")
    return {
        "id": record["id"],
        "name": record["name"],
        "gender": record["gender"],
        "sexual_orientation": "异性恋",
        "age": record["age"],
        "city": record["city"],
        "education": record["education"],
        "job": record["job"],
        "income_range": record["income_range"],
        "marital_status": record["marital_status"],
        "has_children": record["has_children"],
        "relationship_goal": record["relationship_goal"],
        "profile_status": record["profile_status"],
        "verified_level": record["verified_level"],
        "photo_count": record["photo_count"],
        "life_routine": lifestyle,
        "communication_style": personality.split(",")[0].strip() if personality else None,
        "values": values,
        "notes": record.get("notes"),
        "last_active_at": record.get("last_active_at"),
        "public_display_name": record["name"],
        "public_education": record["education"],
        "public_job": record["job"],
        "public_personality": personality,
        "public_values": values,
        "public_notes": record.get("notes"),
    }


def to_persona_row(record: dict) -> dict:
    synthetic_traits = build_synthetic_personality_traits(record, identity=str(record["id"]))
    return {
        "user_key": str(record["id"]),
        "display_name": record["name"],
        "profile_id": record["id"],
        # 硬条件字段已删除，这些字段应该只在 profiles 表中
        # self_gender, self_age, self_city, self_district, self_height, self_education,
        # self_income_wan, self_job, self_marital_status, self_has_children,
        # self_children_count, self_children_living_with_self,
        # self_smoking, self_drinking, self_relationship_goal 已删除
        # target_gender 已移动到 profiles 表（硬条件）
        # 不可量化字段已删除：self_life_rhythm, self_work_pattern, self_expression_style
        "target_age_min": record.get("preferred_age_min"),
        "target_age_max": record.get("preferred_age_max"),
        "target_cities": record.get("preferred_cities"),
        "target_height_min": record.get("preferred_height_min"),
        "target_height_max": record.get("preferred_height_max"),
        "target_education_min": record.get("preferred_education_min"),
        "target_income_min_wan": record.get("preferred_income_min_wan"),
        "target_income_max_wan": record.get("preferred_income_max_wan"),
        "target_marital_statuses": record.get("accept_marital_status"),
        "target_accept_partner_children": record.get("accept_partner_children"),
        "target_accept_long_distance": record.get("accept_long_distance"),
        "target_want_children": record.get("want_children"),
        "target_marriage_timeline": record.get("marriage_timeline"),
        # preferred_traits, must_have_tags, must_not_have_tags 已删除
        "self_personality_traits_json": json.dumps(synthetic_traits, ensure_ascii=False, sort_keys=True),
        "created_at": record.get("created_at"),
        "updated_at": record.get("updated_at"),
    }


def to_photo_db_rows(record: dict, photo_records: list[dict]) -> list[dict]:
    profile_id = record["id"]
    rows: list[dict] = []
    avatar_url = str(record.get("avatar_url") or "").strip()
    if avatar_url:
        rows.append(
            {
                "profile_id": profile_id,
                "photo_url": avatar_url,
                "is_primary": 1,
                "sort_order": 0,
            }
        )
    sort_order = 1
    for photo in photo_records:
        if int(photo.get("profile_id") or 0) != profile_id:
            continue
        if str(photo.get("photo_type") or "") == "avatar":
            continue
        rows.append(
            {
                "profile_id": profile_id,
                "photo_url": photo["photo_url"],
                "is_primary": 0,
                "sort_order": sort_order,
            }
        )
        sort_order += 1
    return rows


def connect_mysql(mysql_config: dict):
    try:
        import pymysql
    except ImportError as exc:  # pragma: no cover - environment-specific path
        raise SystemExit("PyMySQL is required to load generated data into MySQL.") from exc

    return pymysql.connect(
        host=mysql_config["host"],
        port=mysql_config["port"],
        user=mysql_config["user"],
        password=mysql_config["password"],
        database=mysql_config["database"],
        charset=mysql_config["charset"],
        autocommit=False,
    )


def truncate_tables(conn, table_names: tuple[str, ...]) -> None:
    with conn.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        try:
            for table_name in table_names:
                cursor.execute(f"TRUNCATE TABLE `{table_name}`")
        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")


def truncate_database_except_migrations(conn) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_type = 'BASE TABLE'
              AND table_name <> 'schema_migrations'
            """
        )
        table_names = [
            (row["table_name"] if isinstance(row, dict) else row[0]) for row in cursor.fetchall()
        ]
    truncate_tables(conn, tuple(table_names))


def clean_all_user_databases(mysql_config: dict, *, clean_other_dbs: bool) -> None:
    conn = connect_mysql(mysql_config)
    try:
        truncate_tables(conn, HER_USER_TABLES)
        conn.commit()
    finally:
        conn.close()

    if not clean_other_dbs:
        return

    for database in OTHER_USER_DATABASES:
        other_config = dict(mysql_config)
        other_config["database"] = database
        conn = connect_mysql(other_config)
        try:
            truncate_database_except_migrations(conn)
            conn.commit()
            print(f"Cleared all user tables in {database}")
        finally:
            conn.close()


def executemany_batched(cursor, sql: str, rows: list[tuple], *, batch_size: int = 1000) -> None:
    batch: list[tuple] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= batch_size:
            cursor.executemany(sql, batch)
            batch.clear()
    if batch:
        cursor.executemany(sql, batch)


def load_mysql(records, photo_records, mysql_config, *, clean_other_dbs: bool):
    clean_all_user_databases(mysql_config, clean_other_dbs=clean_other_dbs)

    profile_table = mysql_config["table"]
    photo_table = mysql_config.get("photos_table", "profile_photos")
    profile_insert_sql = (
        f"INSERT INTO `{profile_table}` "
        f"({', '.join(f'`{column}`' for column in PROFILE_DB_COLUMNS)}) "
        f"VALUES ({', '.join(['%s'] * len(PROFILE_DB_COLUMNS))})"
    )
    persona_insert_sql = (
        "INSERT INTO `user_personas` "
        f"({', '.join(f'`{column}`' for column in PERSONA_DB_COLUMNS)}) "
        f"VALUES ({', '.join(['%s'] * len(PERSONA_DB_COLUMNS))})"
    )
    photo_insert_sql = (
        f"INSERT INTO `{photo_table}` "
        f"({', '.join(f'`{column}`' for column in PHOTO_DB_COLUMNS)}) "
        f"VALUES ({', '.join(['%s'] * len(PHOTO_DB_COLUMNS))})"
    )

    profile_rows = [tuple(to_profile_row(record)[column] for column in PROFILE_DB_COLUMNS) for record in records]
    persona_rows = [tuple(to_persona_row(record)[column] for column in PERSONA_DB_COLUMNS) for record in records]
    photo_db_rows: list[tuple] = []
    for record in records:
        for row in to_photo_db_rows(record, photo_records):
            photo_db_rows.append(tuple(row[column] for column in PHOTO_DB_COLUMNS))

    conn = connect_mysql(mysql_config)
    try:
        with conn.cursor() as cursor:
            executemany_batched(cursor, profile_insert_sql, profile_rows)
            executemany_batched(cursor, persona_insert_sql, persona_rows)
            executemany_batched(cursor, photo_insert_sql, photo_db_rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def parse_args():
    parser = argparse.ArgumentParser(description="Generate complete simulated dating profiles.")
    parser.add_argument("--rows", type=int, default=ROW_COUNT, help="Number of rows to generate.")
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed.")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="CSV output path.")
    parser.add_argument("--photos-output", default=str(PHOTOS_OUTPUT_PATH), help="Photo CSV output path.")
    parser.add_argument(
        "--load-mysql",
        action="store_true",
        help="Truncate persona/profile tables in `her`, optionally other DBs, then load generated rows.",
    )
    parser.add_argument(
        "--clean-all-dbs",
        action="store_true",
        help="With --load-mysql, also truncate all non-migration tables in chat/discovery/matchmaking/recommendation/ledger DBs.",
    )
    parser.add_argument("--mysql-host", default=DEFAULT_MYSQL["host"], help="MySQL host.")
    parser.add_argument("--mysql-port", type=int, default=DEFAULT_MYSQL["port"], help="MySQL port.")
    parser.add_argument("--mysql-user", default=DEFAULT_MYSQL["user"], help="MySQL user.")
    parser.add_argument("--mysql-password", default=DEFAULT_MYSQL["password"], help="MySQL password.")
    parser.add_argument("--mysql-db", default=DEFAULT_MYSQL["database"], help="MySQL database name.")
    parser.add_argument("--mysql-table", default=DEFAULT_MYSQL["table"], help="MySQL table name.")
    parser.add_argument("--mysql-photos-table", default="profile_photos", help="MySQL photo table name.")
    return parser.parse_args()


def main():
    args = parse_args()
    records, photo_records = generate_records(args.rows, args.seed)
    output_path = Path(args.output)
    photos_output_path = Path(args.photos_output)
    write_csv(output_path, FIELDNAMES, records)
    write_csv(photos_output_path, PHOTO_FIELDNAMES, photo_records)
    print(f"Wrote {len(records)} records to {output_path}")
    print(f"Wrote {len(photo_records)} photo rows to {photos_output_path}")

    if args.load_mysql:
        mysql_config = {
            "host": args.mysql_host,
            "port": args.mysql_port,
            "user": args.mysql_user,
            "password": args.mysql_password,
            "database": args.mysql_db,
            "table": args.mysql_table,
            "photos_table": args.mysql_photos_table,
            "charset": DEFAULT_MYSQL["charset"],
        }
        load_mysql(records, photo_records, mysql_config, clean_other_dbs=args.clean_all_dbs)
        print(
            f"Loaded {len(records)} profiles + personas into "
            f"{mysql_config['database']} on {mysql_config['host']}:{mysql_config['port']}"
        )
        photo_count = sum(len(to_photo_db_rows(record, photo_records)) for record in records)
        print(f"Loaded {photo_count} photo rows into {mysql_config['database']}.{mysql_config['photos_table']}")
        if args.clean_all_dbs:
            print("Also cleared chat/discovery/matchmaking/recommendation/ledger databases.")


if __name__ == "__main__":
    main()
