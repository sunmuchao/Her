#!/usr/bin/env python3
"""批量更新虚拟用户的性取向字段（sexual_orientation）

根据性别推导性取向：
- 男性：90% like_female（喜欢女性），10% like_male（喜欢男性）
- 女性：90% like_male（喜欢男性），10% like_female（喜欢女性）

执行步骤：
1. 查询所有虚拟用户的 profile_id 和 gender
2. 根据性别随机分配性取向（90%异性恋，10%同性恋）
3. 执行批量 UPDATE
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from _repo_bootstrap import bootstrap_repo  # noqa: E402

REPO_ROOT = bootstrap_repo()

import os
from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env", override=True)

# 使用 pymysql 作为 MySQL 驱动
import pymysql
pymysql.install_as_MySQLdb()

from sqlalchemy import create_engine, text
from urllib.parse import quote, unquote, urlparse, urlunparse

# 加载 MySQL root 密码
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


# 解析 DSN（自动添加密码）
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


# 连接 persona 数据库
persona_dsn_raw = os.environ.get("PARTNER_PERSONA_DB", "mysql://root@127.0.0.1:3307/her?table=profiles")
persona_dsn = _resolve_sqlalchemy_dsn(persona_dsn_raw, strip_query=True)
persona_engine = create_engine(persona_dsn, echo=False)

# 设置随机种子（确保可复现）
SEED = 20260701
rng = random.Random(SEED)


def batch_update_sexual_orientation():
    """批量更新虚拟用户的性取向"""

    print("=== 步骤1：查询所有虚拟用户 ===")

    with persona_engine.connect() as conn:
        # 查询所有虚拟用户（id >= 9000）
        query = text("""
            SELECT id, gender, sexual_orientation
            FROM profiles
            WHERE id >= 9000
            ORDER BY id ASC
        """)
        result = conn.execute(query)
        users = [(row[0], row[1], row[2]) for row in result]

    print(f"找到 {len(users)} 个虚拟用户")

    # 统计当前性取向缺失情况
    missing_count = sum(1 for _, _, orientation in users if not orientation or orientation.strip() == "")
    print(f"性取向缺失：{missing_count} 个用户")

    if missing_count == 0:
        print("✅ 所有用户已有性取向字段，无需更新")
        return

    print("\n=== 步骤2：生成性取向分配方案 ===")

    updates = []
    male_count = 0
    female_count = 0

    for id, gender, current_orientation in users:
        # 如果已有性取向，跳过
        if current_orientation and current_orientation.strip():
            continue

        # 根据性别生成性取向
        if gender == "男":
            # 男性：90%异性恋（喜欢女性），10%同性恋（喜欢男性）
            orientation = rng.choice(["like_female"] * 9 + ["like_male"] * 1)
            male_count += 1
        elif gender == "女":
            # 女性：90%异性恋（喜欢男性），10%同性恋（喜欢女性）
            orientation = rng.choice(["like_male"] * 9 + ["like_female"] * 1)
            female_count += 1
        else:
            # 性别未知，默认异性恋
            orientation = "like_male"
            print(f"⚠️ 用户 {id} 性别未知：{gender}")

        updates.append((id, orientation))

    print(f"需要更新：{len(updates)} 个用户")
    print(f"  男性用户：{male_count} 个")
    print(f"  女性用户：{female_count} 个")

    if not updates:
        print("✅ 无需更新")
        return

    print("\n=== 步骤3：执行批量 UPDATE ===")

    with persona_engine.begin() as conn:
        # 批量更新（每批100个）
        batch_size = 100
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i + batch_size]

            for id, orientation in batch:
                update_query = text("""
                    UPDATE profiles
                    SET sexual_orientation = :orientation
                    WHERE id = :id
                """)
                conn.execute(update_query, {"orientation": orientation, "id": id})

            print(f"已更新：{i + len(batch)}/{len(updates)} 个用户")

    print("\n✅ 批量更新完成")

    # 验证更新结果
    print("\n=== 步骤4：验证更新结果 ===")

    with persona_engine.connect() as conn:
        # 查询更新后的统计
        query = text("""
            SELECT
                gender,
                sexual_orientation,
                COUNT(*) as count
            FROM profiles
            WHERE id >= 9000
            GROUP BY gender, sexual_orientation
            ORDER BY gender, sexual_orientation
        """)
        result = conn.execute(query)

        print("\n性别-性取向分布统计：")
        print("-" * 50)
        for row in result:
            gender, orientation, count = row
            print(f"{gender:6} | {orientation:12} | {count:6} 个用户")

    print("\n=== 示例用户验证 ===")

    # 查询徐依嘉的更新结果
    with persona_engine.connect() as conn:
        query = text("""
            SELECT id, name, gender, sexual_orientation
            FROM profiles
            WHERE name = '徐依嘉'
            LIMIT 5
        """)
        result = conn.execute(query)

        for row in result:
            print(f"\n徐依嘉：")
            print(f"  Profile ID: {row[0]}")
            print(f"  性别: {row[1]}")
            print(f"  性取向: {row[2]} ← 【关键验证点】")

            # 验证是否应该筛选男性
            if row[1] == "女" and row[2] == "like_male":
                print("  ✅ 验证通过：女性 + like_male → 应筛选男性候选人")
            elif row[1] == "女" and row[2] == "like_female":
                print("  ⚠️ 同性恋女性：应筛选女性候选人")


if __name__ == "__main__":
    batch_update_sexual_orientation()