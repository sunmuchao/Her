#!/usr/bin/env python3
"""Fill NULL fields in profiles and user_personas tables with realistic virtual data."""

from __future__ import annotations

import random
import sys
from typing import Any

import pymysql

# 数据库连接配置
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3307,
    "user": "root",
    "database": "her",
    "charset": "utf8mb4",
}

# ==================== 数据生成策略 ====================

# 城市数据（包含 adcode）
CITIES = [
    ("北京", "110100", "海淀区", "110108"),
    ("北京", "110100", "朝阳区", "110105"),
    ("北京", "110100", "西城区", "110102"),
    ("上海", "310100", "浦东新区", "310115"),
    ("上海", "310100", "徐汇区", "310104"),
    ("上海", "310100", "静安区", "310106"),
    ("广州", "440100", "天河区", "440106"),
    ("广州", "440100", "越秀区", "440104"),
    ("深圳", "440300", "南山区", "440305"),
    ("深圳", "440300", "福田区", "440304"),
    ("杭州", "330100", "西湖区", "330106"),
    ("杭州", "330100", "余杭区", "330110"),
    ("成都", "510100", "锦江区", "510104"),
    ("成都", "510100", "武侯区", "510107"),
    ("南京", "320100", "鼓楼区", "320106"),
    ("南京", "320100", "玄武区", "320102"),
    ("武汉", "420100", "江汉区", "420103"),
    ("武汉", "420100", "武昌区", "420106"),
    ("西安", "610100", "雁塔区", "610113"),
    ("西安", "610100", "碑林区", "610103"),
    ("苏州", "320500", "姑苏区", "320508"),
    ("青岛", "370200", "市南区", "370202"),
    ("天津", "120100", "和平区", "120101"),
    ("重庆", "500100", "渝中区", "500103"),
    ("长沙", "430100", "岳麓区", "430104"),
    ("郑州", "410100", "金水区", "410105"),
    ("厦门", "350200", "思明区", "350203"),
    ("大连", "210200", "中山区", "210202"),
    ("沈阳", "210100", "和平区", "210102"),
    ("无锡", "320200", "梁溪区", "320213"),
]

# 家乡城市（二三线城市）
HOMETOWN_CITIES = [
    ("石家庄", "130100"),
    ("保定", "130600"),
    ("唐山", "130200"),
    ("太原", "140100"),
    ("大同", "140200"),
    ("呼和浩特", "150100"),
    ("包头", "150200"),
    ("长春", "220100"),
    ("吉林", "220200"),
    ("哈尔滨", "230100"),
    ("大庆", "230600"),
    ("南昌", "360100"),
    ("九江", "360400"),
    ("福州", "350100"),
    ("泉州", "350500"),
    ("南宁", "450100"),
    ("桂林", "450300"),
    ("贵阳", "520100"),
    ("昆明", "530100"),
    ("兰州", "620100"),
    ("银川", "640100"),
    ("乌鲁木齐", "650100"),
    ("海口", "460100"),
    ("三亚", "460200"),
    ("洛阳", "410300"),
    ("开封", "410200"),
    ("烟台", "370600"),
    ("潍坊", "370700"),
    ("临沂", "371300"),
    ("济宁", "370800"),
    ("徐州", "320300"),
    ("常州", "320400"),
    ("南通", "320600"),
    ("扬州", "321000"),
    ("芜湖", "340200"),
    ("合肥", "340100"),
    ("绍兴", "330600"),
    ("金华", "330700"),
    ("台州", "331000"),
    ("温州", "330300"),
    ("宁波", "330200"),
    ("湖州", "330500"),
    ("嘉兴", "330400"),
    ("保定", "130600"),
    ("邯郸", "130400"),
    ("秦皇岛", "130300"),
    ("张家口", "130700"),
    ("承德", "130800"),
    ("廊坊", "131000"),
]

# 学历
EDUCATIONS = [
    ("专科", 1),
    ("本科", 2),
    ("硕士", 3),
    ("博士", 4),
]

# 职业（根据学历分类）
JOBS_BY_EDUCATION = {
    1: ["护士", "美容师", "销售", "客服", "幼师", "会计", "行政助理", "导购", "服务员", "司机"],
    2: [
        "工程师",
        "设计师",
        "产品经理",
        "运营",
        "市场",
        "人力资源",
        "财务",
        "教师",
        "护士",
        "药剂师",
        "公务员",
        "银行职员",
        "记者",
        "编辑",
        "律师助理",
    ],
    3: [
        "高级工程师",
        "架构师",
        "主任医师",
        "副主任医师",
        "大学教授",
        "研究员",
        "律师",
        "投资经理",
        "咨询顾问",
        "总监",
        "经理",
    ],
    4: ["教授", "研究员", "主任医师", "首席科学家", "创始人", "合伙人", "首席架构师"],
}

# 收入范围（单位：万元，根据学历和年龄）
def generate_income_range(education_code: int, age: int) -> tuple[int, int]:
    """Generate realistic income range based on education and age."""
    base_ranges = {
        1: (5, 10),  # 专科
        2: (10, 20),  # 本科
        3: (20, 40),  # 硕士
        4: (40, 100),  # 博士
    }

    min_income, max_income = base_ranges[education_code]

    # 年龄修正：年龄越大收入越高（但有上限）
    age_factor = min((age - 25) * 0.5, 1.5)  # 最大增加 50%

    min_income = int(min_income * (1 + age_factor))
    max_income = int(max_income * (1 + age_factor))

    return min_income, max_income


# 婚姻状态（根据年龄）
def generate_marital_status(age: int) -> str:
    """Generate marital status based on age."""
    if age < 25:
        return random.choices(["未婚", "离异"], weights=[95, 5])[0]
    elif age < 30:
        return random.choices(["未婚", "离异", "丧偶"], weights=[70, 25, 5])[0]
    elif age < 40:
        return random.choices(["未婚", "离异", "丧偶"], weights=[30, 60, 10])[0]
    else:
        return random.choices(["未婚", "离异", "丧偶"], weights=[10, 80, 10])[0]


# 是否有孩子（根据婚姻状态和年龄）
def generate_has_children(marital_status: str, age: int) -> bool:
    """Generate has_children based on marital status and age."""
    if marital_status == "未婚":
        return False
    elif marital_status == "离异":
        # 离异用户，年龄越大越可能有孩子
        return random.random() < min(age / 40, 0.8)
    else:  # 丧偶
        return random.random() < 0.9


# 体重（根据性别和年龄）
def generate_weight(gender: str, age: int) -> int:
    """Generate realistic weight based on gender and age."""
    if gender == "男":
        # 男性：60-80kg 为主
        base = random.normalvariate(70, 8)
        # 年龄修正：中年略重
        age_factor = max(0, (age - 30) * 0.3)
        weight = int(base + age_factor)
        return max(55, min(weight, 90))
    else:
        # 女性：45-65kg 为主
        base = random.normalvariate(55, 7)
        weight = int(base)
        return max(45, min(weight, 75))


# 房产（根据年龄和收入）
def generate_has_house(age: int, income_min: int) -> str:
    """Generate has_house based on age and income."""
    if age < 25:
        return random.choices(["无房", "有房（有贷）", "有房（无贷）"], weights=[80, 15, 5])[0]
    elif age < 30:
        prob = min(income_min / 20, 0.5)
        return random.choices(
            ["无房", "有房（有贷）", "有房（无贷）"], weights=[1 - prob, prob * 0.8, prob * 0.2]
        )[0]
    else:
        prob = min(income_min / 15, 0.7)
        return random.choices(
            ["无房", "有房（有贷）", "有房（无贷）"], weights=[1 - prob, prob * 0.5, prob * 0.5]
        )[0]


# 车产（根据年龄和收入）
def generate_has_car(age: int, income_min: int) -> str:
    """Generate has_car based on age and income."""
    if age < 25:
        return random.choices(["无车", "有车"], weights=[70, 30])[0]
    else:
        prob = min(income_min / 10, 0.6)
        return random.choices(["无车", "有车"], weights=[1 - prob, prob])[0]


# 宗教信仰
RELIGIONS = ["无", "佛教", "基督教", "天主教", "伊斯兰教", "其他"]


# 目标偏好生成
def generate_target_preferences(profile_data: dict[str, Any]) -> dict[str, Any]:
    """Generate target preferences based on user's own profile."""
    age = profile_data["age"]
    gender = profile_data["gender"]
    city = profile_data["city"]
    education_code = profile_data.get("education_code", 2)

    # 目标年龄范围：比自己小 3-10 岁或大 0-5 岁
    if gender == "男":
        target_age_min = max(18, age - 10)
        target_age_max = age - 3
    else:
        target_age_min = age
        target_age_max = age + 10

    # 目标身高：男性找女性 155-175cm，女性找男性 170-185cm
    if gender == "男":
        target_height_min = 155
        target_height_max = 175
    else:
        target_height_min = 170
        target_height_max = 185

    # 目标体重
    if gender == "男":
        target_weight_min = 45
        target_weight_max = 65
    else:
        target_weight_min = 60
        target_weight_max = 80

    # 目标学历：不低于自己，或略低
    target_education_min_code = max(1, education_code - 1)

    # 目标收入：根据自己收入调整
    income_min = profile_data.get("income_min", 10)
    if gender == "男":
        # 男性找女性，收入要求相对宽松
        target_income_min_wan = max(5, int(income_min * 0.5))
        target_income_max_wan = int(income_min * 1.5)
    else:
        # 女性找男性，收入要求相对高
        target_income_min_wan = max(10, int(income_min * 0.8))
        target_income_max_wan = int(income_min * 3)

    # 目标城市：优先同城，接受异地
    target_cities = [city]
    # 额外接受 2-3 个城市
    extra_cities = random.sample([c[0] for c in CITIES[:10]], k=random.randint(0, 3))
    target_cities.extend(extra_cities)

    # 目标婚姻状态
    marital_status = profile_data.get("marital_status", "未婚")
    if marital_status == "未婚":
        target_marital_statuses = ["未婚"]
    else:
        target_marital_statuses = random.choices(
            [["未婚", "离异"], ["离异"], ["未婚", "离异", "丧偶"]],
            weights=[0.4, 0.4, 0.2],
        )[0]

    # 房产、车产要求
    if age > 30:
        target_house_requirement = random.choice(["无要求", "有房即可", "有房（无贷）优先"])
        target_car_requirement = random.choice(["无要求", "有车即可"])
    else:
        target_house_requirement = random.choice(["无要求", "有房即可"])
        target_car_requirement = "无要求"

    # 抽烟、喝酒接受度
    target_smoke_acceptance = random.choice(["不接受", "偶尔可以", "可以接受"])
    target_drink_acceptance = random.choice(["不接受", "偶尔可以", "可以接受"])

    return {
        "target_age_min": target_age_min,
        "target_age_max": target_age_max,
        "target_height_min": target_height_min,
        "target_height_max": target_height_max,
        "target_weight_min": target_weight_min,
        "target_weight_max": target_weight_max,
        "target_education_min_code": target_education_min_code,
        "target_income_min_wan": target_income_min_wan,
        "target_income_max_wan": target_income_max_wan,
        "target_cities": target_cities,
        "target_marital_statuses": target_marital_statuses,
        "target_house_requirement": target_house_requirement,
        "target_car_requirement": target_car_requirement,
        "target_smoke_acceptance": target_smoke_acceptance,
        "target_drink_acceptance": target_drink_acceptance,
    }


def fill_profiles_table(conn: pymysql.Connection) -> None:
    """Fill NULL fields in profiles table."""
    print("开始填充 profiles 表...")

    # 查询需要填充的记录
    with conn.cursor() as cursor:
        # 1. 填充 education, job, income_range NULL 的记录
        cursor.execute(
            """
            SELECT id, gender, age, city
            FROM profiles
            WHERE education IS NULL OR job IS NULL OR income_range IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 education/job/income")

        for record in null_records:
            id, gender, age, city = record

            # 随机选择学历
            education, education_code = random.choice(EDUCATIONS)

            # 根据学历选择职业
            job = random.choice(JOBS_BY_EDUCATION[education_code])

            # 生成收入范围
            income_min, income_max = generate_income_range(education_code, age)

            # 更新
            cursor.execute(
                """
                UPDATE profiles
                SET education = %s,
                    job = %s,
                    income_range = CONCAT(%s, '-', %s, '万')
                WHERE id = %s
                """,
                (education, job, income_min, income_max, id),
            )

        # 2. 填充 marital_status, has_children NULL 的记录
        cursor.execute(
            """
            SELECT id, age
            FROM profiles
            WHERE marital_status IS NULL OR has_children IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 marital_status/has_children")

        for record in null_records:
            id, age = record

            marital_status = generate_marital_status(age)
            has_children = generate_has_children(marital_status, age)

            cursor.execute(
                """
                UPDATE profiles
                SET marital_status = %s,
                    has_children = %s
                WHERE id = %s
                """,
                (marital_status, has_children, id),
            )

        # 3. 填充地理位置编码字段（city_adcode, district_adcode）
        cursor.execute(
            """
            SELECT id, city
            FROM profiles
            WHERE city_adcode IS NULL OR district_adcode IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 city_adcode/district_adcode")

        # 建立城市查询字典
        city_dict = {}
        for city_name, city_adcode, district_name, district_adcode in CITIES:
            if city_name not in city_dict:
                city_dict[city_name] = []
            city_dict[city_name].append((city_adcode, district_name, district_adcode))

        for record in null_records:
            id, city = record

            # 查找城市对应的 adcode
            if city in city_dict:
                city_adcode, district_name, district_adcode = random.choice(city_dict[city])
            else:
                # 如果城市不在列表中，随机选择一个
                city_data = random.choice(CITIES)
                city_adcode = city_data[1]
                district_adcode = city_data[3]

            cursor.execute(
                """
                UPDATE profiles
                SET city_adcode = %s,
                    district_adcode = %s
                WHERE id = %s
                """,
                (city_adcode, district_adcode, id),
            )

        # 4. 填充家乡城市字段（hometown_city, hometown_city_adcode）
        cursor.execute(
            """
            SELECT id
            FROM profiles
            WHERE hometown_city IS NULL OR hometown_city_adcode IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 hometown_city")

        for record in null_records:
            id = record[0]

            hometown_city, hometown_adcode = random.choice(HOMETOWN_CITIES)

            cursor.execute(
                """
                UPDATE profiles
                SET hometown_city = %s,
                    hometown_city_adcode = %s
                WHERE id = %s
                """,
                (hometown_city, hometown_adcode, id),
            )

        # 5. 填充体重字段（weight）
        cursor.execute(
            """
            SELECT id, gender, age
            FROM profiles
            WHERE weight IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 weight")

        for record in null_records:
            id, gender, age = record

            weight = generate_weight(gender, age)

            cursor.execute(
                """
                UPDATE profiles
                SET weight = %s
                WHERE id = %s
                """,
                (weight, id),
            )

        # 6. 填充房产、车产字段（has_house, has_car）
        # 需要先获取收入数据
        cursor.execute(
            """
            SELECT p.id, p.age,
                   CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(p.income_range, '-', 1), '万', 1) AS UNSIGNED) AS income_min
            FROM profiles p
            WHERE p.has_house IS NULL OR p.has_car IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 has_house/has_car")

        for record in null_records:
            id, age, income_min = record

            income_min = income_min or 10  # 默认值

            has_house = generate_has_house(age, income_min)
            has_car = generate_has_car(age, income_min)

            cursor.execute(
                """
                UPDATE profiles
                SET has_house = %s,
                    has_car = %s
                WHERE id = %s
                """,
                (has_house, has_car, id),
            )

        # 7. 填充宗教信仰字段（religion）
        cursor.execute(
            """
            SELECT id
            FROM profiles
            WHERE religion IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 religion")

        for record in null_records:
            id = record[0]

            religion = random.choices(RELIGIONS, weights=[85, 8, 3, 2, 1, 1])[0]

            cursor.execute(
                """
                UPDATE profiles
                SET religion = %s
                WHERE id = %s
                """,
                (religion, id),
            )

        # 8. 填充是否独生子女字段（is_only_child）
        cursor.execute(
            """
            SELECT id
            FROM profiles
            WHERE is_only_child IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 is_only_child")

        for record in null_records:
            id = record[0]

            is_only_child = random.choices([True, False], weights=[40, 60])[0]

            cursor.execute(
                """
                UPDATE profiles
                SET is_only_child = %s
                WHERE id = %s
                """,
                (is_only_child, id),
            )

        # 9. 填充期望对象性别字段（target_gender）
        cursor.execute(
            """
            SELECT id, gender
            FROM profiles
            WHERE target_gender IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 target_gender")

        for record in null_records:
            id, gender = record

            # 根据自己的性别反向设置
            target_gender = "女" if gender == "男" else "男"

            cursor.execute(
                """
                UPDATE profiles
                SET target_gender = %s
                WHERE id = %s
                """,
                (target_gender, id),
            )

    conn.commit()
    print("profiles 表填充完成！")


def fill_personas_table(conn: pymysql.Connection) -> None:
    """Fill NULL fields in user_personas table."""
    print("开始填充 user_personas 表...")

    with conn.cursor() as cursor:
        # 获取 profiles 表数据，用于生成合理的偏好
        cursor.execute(
            """
            SELECT
                p.id AS profile_id,
                p.gender,
                p.age,
                p.city,
                p.marital_status,
                p.education,
                CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(p.income_range, '-', 1), '万', 1) AS UNSIGNED) AS income_min,
                up.id AS persona_id,
                up.user_key
            FROM profiles p
            JOIN user_personas up ON up.profile_id = p.id
            """
        )
        profile_persona_map = {row[7]: row for row in cursor.fetchall()}

        # 1. 填充 display_name NULL 的记录
        cursor.execute(
            """
            SELECT id, user_key
            FROM user_personas
            WHERE display_name IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 display_name")

        for record in null_records:
            persona_id, user_key = record

            # 使用 user_key 或随机生成昵称
            display_name = f"用户{persona_id % 10000}"

            cursor.execute(
                """
                UPDATE user_personas
                SET display_name = %s
                WHERE id = %s
                """,
                (display_name, persona_id),
            )

        # 2. 填充目标偏好字段
        # 需要先获取 profiles 数据
        cursor.execute(
            """
            SELECT up.id, p.gender, p.age, p.city, p.marital_status,
                   CASE p.education
                       WHEN '专科' THEN 1
                       WHEN '本科' THEN 2
                       WHEN '硕士' THEN 3
                       WHEN '博士' THEN 4
                       ELSE 2
                   END AS education_code,
                   CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(p.income_range, '-', 1), '万', 1) AS UNSIGNED) AS income_min
            FROM user_personas up
            JOIN profiles p ON up.profile_id = p.id
            WHERE up.target_age_min IS NULL
               OR up.target_age_max IS NULL
               OR up.target_height_min IS NULL
               OR up.target_height_max IS NULL
               OR up.target_education_min IS NULL
               OR up.target_income_min_wan IS NULL
               OR up.target_income_max_wan IS NULL
               OR up.target_cities IS NULL
               OR up.target_marital_statuses IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少目标偏好字段")

        for record in null_records:
            persona_id, gender, age, city, marital_status, education_code, income_min = record

            profile_data = {
                "age": age,
                "gender": gender,
                "city": city,
                "marital_status": marital_status,
                "education_code": education_code,
                "income_min": income_min or 10,
            }

            target_prefs = generate_target_preferences(profile_data)

            # 更新
            cursor.execute(
                """
                UPDATE user_personas
                SET target_age_min = %s,
                    target_age_max = %s,
                    target_height_min = %s,
                    target_height_max = %s,
                    target_education_min = %s,
                    target_income_min_wan = %s,
                    target_income_max_wan = %s,
                    target_cities = %s,
                    target_marital_statuses = %s
                WHERE id = %s
                """,
                (
                    target_prefs["target_age_min"],
                    target_prefs["target_age_max"],
                    target_prefs["target_height_min"],
                    target_prefs["target_height_max"],
                    EDUCATIONS[target_prefs["target_education_min_code"] - 1][0],
                    target_prefs["target_income_min_wan"],
                    target_prefs["target_income_max_wan"],
                    ",".join(target_prefs["target_cities"]),
                    ",".join(target_prefs["target_marital_statuses"]),
                    persona_id,
                ),
            )

        # 3. 填充目标体重字段（target_weight_min, target_weight_max）
        cursor.execute(
            """
            SELECT up.id, p.gender
            FROM user_personas up
            JOIN profiles p ON up.profile_id = p.id
            WHERE up.target_weight_min IS NULL OR up.target_weight_max IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 target_weight")

        for record in null_records:
            persona_id, gender = record

            if gender == "男":
                target_weight_min = 45
                target_weight_max = 65
            else:
                target_weight_min = 60
                target_weight_max = 80

            cursor.execute(
                """
                UPDATE user_personas
                SET target_weight_min = %s,
                    target_weight_max = %s
                WHERE id = %s
                """,
                (target_weight_min, target_weight_max, persona_id),
            )

        # 4. 填充学历编码字段（target_education_min_code）
        cursor.execute(
            """
            SELECT up.id, up.target_education_min
            FROM user_personas up
            WHERE up.target_education_min_code IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 target_education_min_code")

        edu_dict = {"专科": 1, "本科": 2, "硕士": 3, "博士": 4}

        for record in null_records:
            persona_id, target_education_min = record

            education_code = edu_dict.get(target_education_min, 2)

            cursor.execute(
                """
                UPDATE user_personas
                SET target_education_min_code = %s
                WHERE id = %s
                """,
                (education_code, persona_id),
            )

        # 5. 填充目标家乡城市字段（target_hometown_cities）
        cursor.execute(
            """
            SELECT id
            FROM user_personas
            WHERE target_hometown_cities IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 target_hometown_cities")

        for record in null_records:
            persona_id = record[0]

            # 随机选择 1-3 个家乡城市
            hometowns = random.sample([c[0] for c in HOMETOWN_CITIES[:30]], k=random.randint(1, 3))

            cursor.execute(
                """
                UPDATE user_personas
                SET target_hometown_cities = %s
                WHERE id = %s
                """,
                (",".join(hometowns), persona_id),
            )

        # 6. 填充房产、车产要求字段
        cursor.execute(
            """
            SELECT up.id, p.age, p.gender,
                   CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(p.income_range, '-', 1), '万', 1) AS UNSIGNED) AS income_min
            FROM user_personas up
            JOIN profiles p ON up.profile_id = p.id
            WHERE up.target_house_requirement IS NULL OR up.target_car_requirement IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 target_house_requirement/target_car_requirement")

        for record in null_records:
            persona_id, age, gender, income_min = record

            income_min = income_min or 10

            if age > 30:
                target_house_requirement = random.choice(["无要求", "有房即可", "有房（无贷）优先"])
                target_car_requirement = random.choice(["无要求", "有车即可"])
            else:
                target_house_requirement = random.choice(["无要求", "有房即可"])
                target_car_requirement = "无要求"

            cursor.execute(
                """
                UPDATE user_personas
                SET target_house_requirement = %s,
                    target_car_requirement = %s
                WHERE id = %s
                """,
                (target_house_requirement, target_car_requirement, persona_id),
            )

        # 7. 填充抽烟、喝酒接受度字段
        cursor.execute(
            """
            SELECT id
            FROM user_personas
            WHERE target_smoke_acceptance IS NULL OR target_drink_acceptance IS NULL
            """
        )
        null_records = cursor.fetchall()

        print(f"发现 {len(null_records)} 条记录缺少 target_smoke_acceptance/target_drink_acceptance")

        for record in null_records:
            persona_id = record[0]

            target_smoke_acceptance = random.choice(["不接受", "偶尔可以", "可以接受"])
            target_drink_acceptance = random.choice(["不接受", "偶尔可以", "可以接受"])

            cursor.execute(
                """
                UPDATE user_personas
                SET target_smoke_acceptance = %s,
                    target_drink_acceptance = %s
                WHERE id = %s
                """,
                (target_smoke_acceptance, target_drink_acceptance, persona_id),
            )

    conn.commit()
    print("user_personas 表填充完成！")


def main() -> None:
    """Main function."""
    print("开始填充虚拟数据...")
    print("=" * 60)

    try:
        conn = pymysql.connect(**DB_CONFIG)
        print("数据库连接成功")

        fill_profiles_table(conn)
        print()
        fill_personas_table(conn)

        print("=" * 60)
        print("所有数据填充完成！")

        # 统计最终结果
        print("\n最终统计：")
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN hometown_city IS NULL THEN 1 ELSE 0 END) AS hometown_null,
                    SUM(CASE WHEN weight IS NULL THEN 1 ELSE 0 END) AS weight_null,
                    SUM(CASE WHEN has_house IS NULL THEN 1 ELSE 0 END) AS house_null,
                    SUM(CASE WHEN religion IS NULL THEN 1 ELSE 0 END) AS religion_null
                FROM profiles
                """
            )
            result = cursor.fetchone()
            print(f"Profiles 表剩余 NULL 字段: hometown={result[0]}, weight={result[1]}, house={result[2]}, religion={result[3]}")

            cursor.execute(
                """
                SELECT
                    SUM(CASE WHEN target_weight_min IS NULL THEN 1 ELSE 0 END) AS weight_null,
                    SUM(CASE WHEN target_house_requirement IS NULL THEN 1 ELSE 0 END) AS house_null,
                    SUM(CASE WHEN target_smoke_acceptance IS NULL THEN 1 ELSE 0 END) AS smoke_null
                FROM user_personas
                """
            )
            result = cursor.fetchone()
            print(f"Personas 表剩余 NULL 字段: weight={result[0]}, house={result[1]}, smoke={result[2]}")

        conn.close()

    except Exception as e:
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()