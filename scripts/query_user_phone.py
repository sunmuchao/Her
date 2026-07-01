"""查询虚拟用户手机号与 profile 映射。"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import quote, unquote, urlparse, urlunparse

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from _repo_bootstrap import bootstrap_repo  # noqa: E402

REPO_ROOT = bootstrap_repo()


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


def _load_mysql_root_password() -> str:
    direct = str(os.environ.get("MYSQL_ROOT_PASSWORD") or "").strip()
    if direct:
        return direct

    secret_file = str(os.environ.get("MYSQL_ROOT_PASSWORD_FILE") or "").strip()
    candidate_files = []
    if secret_file:
        candidate_files.append(Path(secret_file))
    candidate_files.append(REPO_ROOT / "secrets" / "mysql_root_password.txt")

    for path in candidate_files:
        try:
            if path.is_file():
                password = path.read_text(encoding="utf-8").strip()
                if password:
                    os.environ["MYSQL_ROOT_PASSWORD"] = password
                    return password
        except OSError:
            continue
    return ""


def _resolve_sqlalchemy_dsn(raw_dsn: str, *, strip_query: bool = False) -> str:
    dsn = str(raw_dsn or "").strip()
    if not dsn:
        raise ValueError("MySQL DSN is empty")

    parsed = urlparse(dsn)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        return dsn

    if (parsed.username or "") == "root" and not parsed.password:
        password = _load_mysql_root_password()
        if password:
            host = parsed.hostname or "127.0.0.1"
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"
            userinfo = f"{quote(unquote(parsed.username or 'root'), safe='')}:{quote(password, safe='')}"
            netloc = f"{userinfo}@{host}"
            if parsed.port:
                netloc += f":{parsed.port}"
            parsed = parsed._replace(netloc=netloc)

    if parsed.scheme == "mysql":
        parsed = parsed._replace(scheme="mysql+pymysql")
    if strip_query:
        parsed = parsed._replace(query="")
    return urlunparse(parsed)


def _build_engine(env_name: str, default: str, *, strip_query: bool = False):
    return create_engine(
        _resolve_sqlalchemy_dsn(os.environ.get(env_name, default), strip_query=strip_query)
    )


def _print_connection_hint(exc: OperationalError, env_name: str) -> None:
    print(f"\n数据库连接失败: {env_name}")
    print(f"错误: {exc}")
    print("排查建议:")
    print("  1. 确认目标 MySQL 已启动，并监听正确的 host/port。")
    print("  2. 检查 .env 中的 DSN 是否符合当前环境。")
    print("  3. 如使用 root 账号，确认 MYSQL_ROOT_PASSWORD 或 secrets/mysql_root_password.txt 可用。")


_load_dotenv()
chat_engine = _build_engine("PARTNER_CHAT_DB", "mysql://root@127.0.0.1:3307/her_chat")
persona_engine = _build_engine(
    "PERSONA_MEMORY_MYSQL_SOURCE",
    "mysql://root@127.0.0.1:3307/her?table=profiles",
    strip_query=True,
)

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
    name = "罗舒悦"
    print(f"查询用户: {name}")

    # 先从 profiles 表查询
    print("\n=== 从 profiles 表查询 ===")
    try:
        profiles = query_profile_by_name(name)
    except OperationalError as exc:
        _print_connection_hint(exc, "PERSONA_MEMORY_MYSQL_SOURCE")
        return

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
    try:
        virtual_users = query_virtual_users()
    except OperationalError as exc:
        _print_connection_hint(exc, "PARTNER_CHAT_DB")
        return

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
        try:
            users = query_user_by_name(name)
        except OperationalError as exc:
            _print_connection_hint(exc, "PARTNER_CHAT_DB")
            return
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
