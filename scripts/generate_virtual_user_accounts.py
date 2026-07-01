#!/usr/bin/env python3
"""为虚拟用户生成完整的账号数据（包括手机号、user_id、onboarding信息）。

使用方法：
    python scripts/generate_virtual_user_accounts.py [--limit 100] [--dry-run]

说明：
    --limit: 只生成前N个虚拟用户的账号数据（默认全部）
    --dry-run: 只打印生成的数据，不写入数据库
"""

import argparse
import csv
import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _repo_bootstrap import bootstrap_repo

REPO_ROOT = bootstrap_repo()


def _load_dotenv():
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = REPO_ROOT / ".env"
    if env_path.is_file():
        load_dotenv(env_path, override=True)


def _load_mysql_root_password():
    import os
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


_load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from urllib.parse import quote, unquote, urlparse, urlunparse


def _resolve_sqlalchemy_dsn(raw_dsn, *, strip_query=False):
    import os
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


def _build_engine(env_name, default, *, strip_query=False):
    import os
    return create_engine(
        _resolve_sqlalchemy_dsn(os.environ.get(env_name, default), strip_query=strip_query)
    )


chat_engine = _build_engine("PARTNER_CHAT_DB", "mysql://root@127.0.0.1:3307/her_chat")
persona_engine = _build_engine(
    "PERSONA_MEMORY_MYSQL_SOURCE",
    "mysql://root@127.0.0.1:3307/her?table=profiles",
    strip_query=True,
)


def generate_phone_number(profile_id):
    """为虚拟用户生成手机号（使用固定的虚拟号码段）。

    虚拟用户手机号格式：1860000xxxx（避免与真实号码冲突）
    """
    # 使用虚拟号码段：1860000开头
    # 后4位使用profile_id的后4位（确保唯一性）
    suffix = profile_id % 10000
    return f"1860000{suffix:04d}"


def generate_user_id(profile_id):
    """生成虚拟用户的user_id。

    格式：usr-virt-{profile_id}
    """
    return f"usr-virt-{profile_id}"


def generate_identity_id(profile_id, identity_type):
    """生成身份ID。

    格式：id-virt-{profile_id}-{identity_type}
    """
    return f"id-virt-{profile_id}-{identity_type}"


def load_virtual_profiles(limit=None):
    """从CSV文件加载虚拟用户profile数据。"""
    csv_path = REPO_ROOT / "virtual_profiles_10000.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"虚拟用户CSV文件不存在: {csv_path}")

    profiles = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if limit and i >= limit:
                break
            profiles.append(row)

    return profiles


def build_basic_info_json(profile_data):
    """构建basic_info_json数据。"""
    basic_info = {
        "profile_id": int(profile_data["id"]),
        "name": profile_data["name"],
        "gender": profile_data["gender"],
        "age": int(profile_data["age"]),
        "city": profile_data["city"],
        "district": profile_data.get("district", ""),
        "hometown": profile_data.get("hometown", ""),
        "height": int(profile_data.get("height", 165)),
        "education": profile_data["education"],
        "job": profile_data["job"],
        "income_range": profile_data.get("income_range", ""),
        "marital_status": profile_data.get("marital_status", "未婚"),
        "has_children": profile_data.get("has_children", "否") == "是",
        "relationship_goal": profile_data.get("relationship_goal", "结婚导向"),
        "avatar_url": profile_data.get("avatar_url", ""),
        "photo_count": int(profile_data.get("photo_count", 0)),
        "housing_status": profile_data.get("housing_status", ""),
        "car_status": profile_data.get("car_status", ""),
    }
    return json.dumps(basic_info, ensure_ascii=False)


def build_preference_json(profile_data):
    """构建preference_json数据。"""
    preference = {
        "preferred_age_min": int(profile_data.get("preferred_age_min", 25)),
        "preferred_age_max": int(profile_data.get("preferred_age_max", 30)),
        "preferred_cities": profile_data.get("preferred_cities", "无锡"),
        "preferred_height_min": int(profile_data.get("preferred_height_min", 170)),
        "preferred_height_max": int(profile_data.get("preferred_height_max", 180)),
        "preferred_education_min": profile_data.get("preferred_education_min", "大专"),
        "preferred_income_min_wan": int(profile_data.get("preferred_income_min_wan", 10)),
        "preferred_income_max_wan": int(profile_data.get("preferred_income_max_wan", 20)),
        "accept_long_distance": profile_data.get("accept_long_distance", "可协商"),
        "accept_smoking": profile_data.get("accept_smoking", "不接受"),
        "accept_drinking": profile_data.get("accept_drinking", "可协商"),
        "accept_marital_status": profile_data.get("accept_marital_status", "未婚"),
        "accept_partner_children": profile_data.get("accept_partner_children", "不接受"),
    }
    return json.dumps(preference, ensure_ascii=False)


def insert_user_accounts(profiles, dry_run=False):
    """插入user_accounts表数据。"""
    if dry_run:
        print("\n=== user_accounts 表数据（预览） ===")
        for i, profile in enumerate(profiles[:5]):  # 只显示前5个
            profile_id = int(profile["id"])
            user_id = generate_user_id(profile_id)
            phone = generate_phone_number(profile_id)
            print(f"\n用户 {i+1}:")
            print(f"  user_id: {user_id}")
            print(f"  primary_phone: {phone}")
            print(f"  account_status: active")
            print(f"  register_source: virtual_import")
            print(f"  onboarding_status: completed")
        return

    with chat_engine.begin() as conn:
        # 先清理旧的虚拟用户数据（避免重复）
        # ✅ 修正：先删除 identities（有外键约束），再删除其他表
        conn.execute(text("DELETE FROM user_account_identities WHERE identity_id LIKE 'id-virt-%'"))
        conn.execute(text("DELETE FROM user_onboarding_profiles WHERE user_id LIKE 'usr-virt-%'"))
        conn.execute(text("DELETE FROM user_accounts WHERE user_id LIKE 'usr-virt-%'"))

        print(f"已清理旧的虚拟用户数据")

        # 批量插入user_accounts
        insert_query = text("""
            INSERT INTO user_accounts (
                user_id,
                account_status,
                primary_phone,
                phone_verified_at,
                register_source,
                onboarding_status,
                first_login_at,
                last_login_at,
                created_at,
                updated_at
            ) VALUES (
                :user_id,
                :account_status,
                :primary_phone,
                :phone_verified_at,
                :register_source,
                :onboarding_status,
                :first_login_at,
                :last_login_at,
                :created_at,
                :updated_at
            )
        """)

        now = datetime.now()
        verified_at = now - timedelta(days=random.randint(1, 30))

        batch_size = 100
        for i in range(0, len(profiles), batch_size):
            batch = profiles[i:i + batch_size]
            values = []
            for profile in batch:
                profile_id = int(profile["id"])
                values.append({
                    "user_id": generate_user_id(profile_id),
                    "account_status": "active",
                    "primary_phone": generate_phone_number(profile_id),
                    "phone_verified_at": verified_at,
                    "register_source": "virtual_import",
                    "onboarding_status": "completed",
                    "first_login_at": verified_at,
                    "last_login_at": now - timedelta(hours=random.randint(1, 72)),
                    "created_at": verified_at,
                    "updated_at": now,
                })

            conn.execute(insert_query, values)
            print(f"已插入 {i + len(batch)}/{len(profiles)} 个user_accounts记录")


def insert_user_onboarding_profiles(profiles, dry_run=False):
    """插入user_onboarding_profiles表数据。"""
    if dry_run:
        print("\n=== user_onboarding_profiles 表数据（预览） ===")
        for i, profile in enumerate(profiles[:5]):
            profile_id = int(profile["id"])
            user_id = generate_user_id(profile_id)
            basic_info = build_basic_info_json(profile)
            preference = build_preference_json(profile)
            print(f"\n用户 {i+1}:")
            print(f"  user_id: {user_id}")
            print(f"  onboarding_status: completed")
            print(f"  basic_info_json长度: {len(basic_info)}")
            print(f"  preference_json长度: {len(preference)}")
        return

    with chat_engine.begin() as conn:
        insert_query = text("""
            INSERT INTO user_onboarding_profiles (
                user_id,
                onboarding_status,
                current_step,
                basic_info_json,
                preference_json,
                completed_at,
                created_at,
                updated_at
            ) VALUES (
                :user_id,
                :onboarding_status,
                :current_step,
                :basic_info_json,
                :preference_json,
                :completed_at,
                :created_at,
                :updated_at
            )
        """)

        now = datetime.now()
        completed_at = now - timedelta(days=random.randint(1, 30))

        batch_size = 100
        for i in range(0, len(profiles), batch_size):
            batch = profiles[i:i + batch_size]
            values = []
            for profile in batch:
                profile_id = int(profile["id"])
                values.append({
                    "user_id": generate_user_id(profile_id),
                    "onboarding_status": "completed",
                    "current_step": None,
                    "basic_info_json": build_basic_info_json(profile),
                    "preference_json": build_preference_json(profile),
                    "completed_at": completed_at,
                    "created_at": completed_at,
                    "updated_at": now,
                })

            conn.execute(insert_query, values)
            print(f"已插入 {i + len(batch)}/{len(profiles)} 个user_onboarding_profiles记录")


def insert_user_account_identities(profiles, dry_run=False):
    """插入user_account_identities表数据（profile_id映射 + 手机号映射）。"""
    if dry_run:
        print("\n=== user_account_identities 表数据（预览） ===")
        for i, profile in enumerate(profiles[:5]):
            profile_id = int(profile["id"])
            user_id = generate_user_id(profile_id)
            phone = generate_phone_number(profile_id)

            # profile身份映射
            identity_id_profile = generate_identity_id(profile_id, "profile")
            print(f"\n用户 {i+1} - Profile身份:")
            print(f"  identity_id: {identity_id_profile}")
            print(f"  user_id: {user_id}")
            print(f"  identity_type: profile")
            print(f"  identity_value: {profile_id}")
            print(f"  is_primary: 1")

            # 手机号身份映射（关键！）
            identity_id_phone = generate_identity_id(profile_id, "phone")
            print(f"\n用户 {i+1} - Phone身份:")
            print(f"  identity_id: {identity_id_phone}")
            print(f"  user_id: {user_id}")
            print(f"  identity_type: phone")
            print(f"  identity_value: {phone}")
            print(f"  is_primary: 1")
            print(f"  status: active")
        return

    # ✅ 新增：导入加密工具
    try:
        from chat_system.sensitive_data_crypto import SensitiveDataCrypto
    except ImportError:
        # 如果导入失败，定义一个简单的加密类（仅用于虚拟用户）
        class SensitiveDataCrypto:
            @staticmethod
            def encrypt_phone(phone):
                # 虚拟用户手机号不需要真实加密，直接存储即可
                # 但格式要与真实加密一致（避免字段长度问题）
                return phone

    with chat_engine.begin() as conn:
        insert_query = text("""
            INSERT INTO user_account_identities (
                identity_id,
                user_id,
                identity_type,
                identity_value,
                is_primary,
                verified_at,
                bound_at,
                status,
                created_at,
                updated_at
            ) VALUES (
                :identity_id,
                :user_id,
                :identity_type,
                :identity_value,
                :is_primary,
                :verified_at,
                :bound_at,
                :status,
                :created_at,
                :updated_at
            )
        """)

        now = datetime.now()
        verified_at = now - timedelta(days=random.randint(1, 30))

        batch_size = 100
        for i in range(0, len(profiles), batch_size):
            batch = profiles[i:i + batch_size]
            values = []
            for profile in batch:
                profile_id = int(profile["id"])
                user_id = generate_user_id(profile_id)
                phone = generate_phone_number(profile_id)

                # 1. Profile身份映射
                values.append({
                    "identity_id": generate_identity_id(profile_id, "profile"),
                    "user_id": user_id,
                    "identity_type": "profile",
                    "identity_value": str(profile_id),
                    "is_primary": 1,
                    "verified_at": verified_at,
                    "bound_at": verified_at,
                    "status": "verified",
                    "created_at": verified_at,
                    "updated_at": now,
                })

                # 2. ✅ 新增：手机号身份映射（关键！登录时需要）
                values.append({
                    "identity_id": generate_identity_id(profile_id, "phone"),
                    "user_id": user_id,
                    "identity_type": "phone",
                    "identity_value": phone,  # 手机号（明文，虚拟号码段）
                    "is_primary": 1,
                    "verified_at": verified_at,
                    "bound_at": verified_at,
                    "status": "active",  # ✅ 关键：status必须为active才能被查找
                    "created_at": verified_at,
                    "updated_at": now,
                })

            conn.execute(insert_query, values)
            print(f"已插入 {i + len(batch)}/{len(profiles)} 个用户身份记录（每人2条：profile + phone）")


def verify_insertion(profiles, dry_run=False):
    """验证插入的数据。"""
    if dry_run:
        print("\n=== 数据验证（dry-run模式，跳过） ===")
        return

    with chat_engine.connect() as conn:
        # 查询统计
        accounts_count = conn.execute(
            text("SELECT COUNT(*) FROM user_accounts WHERE user_id LIKE 'usr-virt-%'")
        ).scalar()
        onboarding_count = conn.execute(
            text("SELECT COUNT(*) FROM user_onboarding_profiles WHERE user_id LIKE 'usr-virt-%'")
        ).scalar()
        identities_count = conn.execute(
            text("SELECT COUNT(*) FROM user_account_identities WHERE identity_id LIKE 'id-virt-%'")
        ).scalar()

        # ✅ 新增：分别统计profile和phone身份映射
        profile_identities_count = conn.execute(
            text("SELECT COUNT(*) FROM user_account_identities WHERE identity_id LIKE 'id-virt-%' AND identity_type = 'profile'")
        ).scalar()
        phone_identities_count = conn.execute(
            text("SELECT COUNT(*) FROM user_account_identities WHERE identity_id LIKE 'id-virt-%' AND identity_type = 'phone'")
        ).scalar()

        print("\n=== 数据验证 ===")
        print(f"user_accounts 表: {accounts_count} 条记录")
        print(f"user_onboarding_profiles 表: {onboarding_count} 条记录")
        print(f"user_account_identities 表: {identities_count} 条记录")
        print(f"  - profile身份映射: {profile_identities_count} 条")
        print(f"  - phone身份映射: {phone_identities_count} 条（✅ 关键！）")

        # 查询周子琳的数据验证
        print("\n=== 周子琳数据验证 ===")
        profile_id = 6549
        user_id = generate_user_id(profile_id)
        phone = generate_phone_number(profile_id)

        result = conn.execute(
            text("""
                SELECT ua.user_id, ua.primary_phone, uop.basic_info_json
                FROM user_accounts ua
                LEFT JOIN user_onboarding_profiles uop ON ua.user_id = uop.user_id
                WHERE ua.user_id = :user_id
            """),
            {"user_id": user_id}
        ).fetchone()

        if result:
            print(f"user_id: {result[0]}")
            print(f"手机号: {result[1]}")
            basic_info = json.loads(result[2])
            print(f"姓名: {basic_info.get('name')}")
            print(f"城市: {basic_info.get('city')}")
            print(f"职业: {basic_info.get('job')}")

            # ✅ 新增：验证手机号身份映射是否存在
            phone_identity = conn.execute(
                text("""
                    SELECT identity_id, identity_type, identity_value, status
                    FROM user_account_identities
                    WHERE user_id = :user_id AND identity_type = 'phone'
                """),
                {"user_id": user_id}
            ).fetchone()

            if phone_identity:
                print(f"\n手机号身份映射验证:")
                print(f"  identity_id: {phone_identity[0]}")
                print(f"  identity_type: {phone_identity[1]}")
                print(f"  identity_value: {phone_identity[2]}")
                print(f"  status: {phone_identity[3]}（✅ 必须为active才能登录）")
            else:
                print(f"\n❌ 缺少手机号身份映射（登录会失败）")
        else:
            print(f"未找到周子琳的账号数据")


def main():
    parser = argparse.ArgumentParser(description="为虚拟用户生成完整的账号数据")
    parser.add_argument("--limit", type=int, help="只生成前N个虚拟用户的账号数据")
    parser.add_argument("--dry-run", action="store_true", help="只打印生成的数据，不写入数据库")
    args = parser.parse_args()

    print("=== 开始为虚拟用户生成账号数据 ===")

    # 加载虚拟用户profile数据
    profiles = load_virtual_profiles(limit=args.limit)
    print(f"加载了 {len(profiles)} 个虚拟用户profile")

    # 生成账号数据
    insert_user_accounts(profiles, dry_run=args.dry_run)
    insert_user_onboarding_profiles(profiles, dry_run=args.dry_run)
    insert_user_account_identities(profiles, dry_run=args.dry_run)

    # 验证数据
    verify_insertion(profiles, dry_run=args.dry_run)

    print("\n=== 完成 ===")


if __name__ == "__main__":
    main()