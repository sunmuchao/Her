"""查询虚拟用户王语文的手机号"""

import os
import json
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 数据库连接
chat_db_url = os.environ.get("PARTNER_CHAT_DB", "mysql://root@127.0.0.1:3307/her_chat")
persona_db_url = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "mysql://root@127.0.0.1:3307/her?table=profiles")

# 如果没有指定驱动，使用 pymysql
if chat_db_url.startswith("mysql://") and "+pymysql" not in chat_db_url:
    chat_db_url = chat_db_url.replace("mysql://", "mysql+pymysql://")
if persona_db_url.startswith("mysql://") and "+pymysql" not in persona_db_url:
    persona_db_url = persona_db_url.split("?")[0].replace("mysql://", "mysql+pymysql://")

# 创建引擎
chat_engine = create_engine(chat_db_url)
persona_engine = create_engine(persona_db_url)

def query_user_by_name(name):
    """根据名字查询用户手机号"""

    with chat_engine.connect() as conn:
        # 查询 user_onboarding_profiles 表，找到名字匹配的用户
        query = text("""
            SELECT
                uop.user_id,
                uop.basic_info_json,
                ua.primary_phone
            FROM user_onboarding_profiles uop
            LEFT JOIN user_accounts ua ON uop.user_id = ua.user_id
            WHERE uop.basic_info_json LIKE :name_pattern
        """)

        result = conn.execute(query, {"name_pattern": f'%{name}%'})

        users = []
        for row in result:
            user_id = row[0]
            basic_info_json = row[1]
            primary_phone = row[2]

            # 解析 basic_info_json
            if basic_info_json:
                try:
                    basic_info = json.loads(basic_info_json)
                    user_name = basic_info.get('name', '')

                    # 精确匹配名字
                    if user_name == name:
                        users.append({
                            'user_id': user_id,
                            'name': user_name,
                            'phone': primary_phone,
                            'basic_info': basic_info
                        })
                except json.JSONDecodeError:
                    print(f"JSON解析失败: {basic_info_json}")

        return users

def list_all_users(limit=20):
    """列出所有用户（用于调试）"""

    with chat_engine.connect() as conn:
        query = text("""
            SELECT
                uop.user_id,
                uop.basic_info_json,
                ua.primary_phone
            FROM user_onboarding_profiles uop
            LEFT JOIN user_accounts ua ON uop.user_id = ua.user_id
            LIMIT :limit
        """)

        result = conn.execute(query, {"limit": limit})

        users = []
        for row in result:
            user_id = row[0]
            basic_info_json = row[1]
            primary_phone = row[2]

            # 解析 basic_info_json
            if basic_info_json:
                try:
                    basic_info = json.loads(basic_info_json)
                    user_name = basic_info.get('name', '未知')
                    users.append({
                        'user_id': user_id,
                        'name': user_name,
                        'phone': primary_phone,
                        'basic_info': basic_info
                    })
                except json.JSONDecodeError:
                    users.append({
                        'user_id': user_id,
                        'name': 'JSON解析失败',
                        'phone': primary_phone,
                        'basic_info': {}
                    })

        return users

def query_virtual_users():
    """查询虚拟用户的详细信息"""

    with chat_engine.connect() as conn:
        # 查询虚拟用户的基本信息
        query = text("""
            SELECT
                ua.user_id,
                ua.primary_phone,
                uop.basic_info_json,
                uop.preference_json
            FROM user_accounts ua
            LEFT JOIN user_onboarding_profiles uop ON ua.user_id = uop.user_id
            WHERE ua.user_id LIKE 'usr-virt-%'
            ORDER BY ua.user_id
            LIMIT 50
        """)

        result = conn.execute(query)

        users = []
        for row in result:
            user_id = row[0]
            primary_phone = row[1]
            basic_info_json = row[2]
            preference_json = row[3]

            user_data = {
                'user_id': user_id,
                'phone': primary_phone,
                'basic_info': {},
                'preference': {}
            }

            # 解析 basic_info_json
            if basic_info_json:
                try:
                    basic_info = json.loads(basic_info_json)
                    user_data['basic_info'] = basic_info
                    user_data['name'] = basic_info.get('name', '未知')
                except json.JSONDecodeError:
                    user_data['name'] = 'JSON解析失败'

            # 解析 preference_json
            if preference_json:
                try:
                    preference = json.loads(preference_json)
                    user_data['preference'] = preference
                except json.JSONDecodeError:
                    pass

            users.append(user_data)

        return users

def query_profile_by_name(name):
    """从 profiles 表中根据名字查询用户信息"""

    with persona_engine.connect() as conn:
        # 查询 profiles 表
        query = text("""
            SELECT
                id,
                name,
                gender,
                age,
                city,
                education,
                job
            FROM profiles
            WHERE name = :name
            LIMIT 50
        """)

        result = conn.execute(query, {"name": name})

        profiles = []
        for row in result:
            profiles.append({
                'profile_id': row[0],
                'name': row[1],
                'gender': row[2],
                'age': row[3],
                'city': row[4],
                'education': row[5],
                'job': row[6]
            })

        return profiles

def main():
    name = "林舒雯"
    print(f"查询用户: {name}")

    # 先从 profiles 表查询
    print("\n=== 从 profiles 表查询 ===")
    profiles = query_profile_by_name(name)

    if profiles:
        print(f"\n在 profiles 表中找到 {len(profiles)} 个用户:")
        for profile in profiles:
            print(f"\nProfile ID: {profile['profile_id']}")
            print(f"姓名: {profile['name']}")
            print(f"性别: {profile['gender']}")
            print(f"年龄: {profile['age']}")
            print(f"城市: {profile['city']}")
            print(f"学历: {profile['education']}")
            print(f"职业: {profile['job']}")

            # 根据 profile_id 查找对应的 user_id 和手机号
            profile_id = profile['profile_id']
            with chat_engine.connect() as conn:
                query = text("""
                    SELECT
                        uop.user_id,
                        ua.primary_phone
                    FROM user_onboarding_profiles uop
                    LEFT JOIN user_accounts ua ON uop.user_id = ua.user_id
                    WHERE JSON_EXTRACT(uop.basic_info_json, '$.profile_id') = :profile_id
                """)
                result = conn.execute(query, {"profile_id": profile_id})
                user_row = result.fetchone()

                if user_row:
                    print(f"\n对应的用户信息:")
                    print(f"  用户ID: {user_row[0]}")
                    print(f"  手机号: {user_row[1]}")
                else:
                    print(f"\n未找到对应的用户ID (profile_id={profile_id})")
        return

    # 如果 profiles 表没找到，再从 chat 数据库查询
    print("\n=== 从 chat 数据库查询虚拟用户 ===")
    virtual_users = query_virtual_users()

    found_user = None
    for user in virtual_users:
        # 检查 basic_info 中是否有名字
        if 'name' in user and user['name'] == name:
            found_user = user
            break

        # 检查整个 basic_info_json 是否包含名字
        if user['basic_info']:
            for key, value in user['basic_info'].items():
                if isinstance(value, str) and value == name:
                    found_user = user
                    break

        if found_user:
            break

    if found_user:
        print(f"\n找到用户: {name}")
        print(f"用户ID: {found_user['user_id']}")
        print(f"手机号: {found_user['phone']}")
        print(f"\n基本信息:")
        for key, value in found_user['basic_info'].items():
            print(f"  {key}: {value}")
        if found_user['preference']:
            print(f"\n偏好信息:")
            for key, value in found_user['preference'].items():
                print(f"  {key}: {value}")
    else:
        print(f"\n未找到用户: {name}")

        # 显示部分虚拟用户供参考
        print(f"\n显示前10个虚拟用户:")
        for i, user in enumerate(virtual_users[:10]):
            print(f"\n用户 {i+1}:")
            print(f"  用户ID: {user['user_id']}")
            print(f"  手机号: {user['phone']}")
            if user['basic_info']:
                print(f"  基本信息: {user['basic_info']}")

        # 最后尝试在整个数据库中搜索
        print("\n=== 在整个 chat 数据库中搜索 ===")
        users = query_user_by_name(name)
        if users:
            print(f"\n找到 {len(users)} 个用户:")
            for user in users:
                print(f"\n用户ID: {user['user_id']}")
                print(f"姓名: {user['name']}")
                print(f"手机号: {user['phone']}")
        else:
            print(f"未找到用户: {name}")

if __name__ == "__main__":
    main()