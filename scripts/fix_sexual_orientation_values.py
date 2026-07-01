#!/usr/bin/env python3
"""修正数据库中的性取向字段

问题：数据库中的性取向字段是中文"异性恋"，但系统期望英文值"like_male"/"like_female"
解决：批量更新为英文标准值，根据性别推导：
- 女性 + 异性恋 → like_male（喜欢男性）
- 男性 + 异性恋 → like_female（喜欢女性）

同时保留10%的同性恋用户：
- 女性 + 同性恋 → like_female（喜欢女性）
- 男性 + 同性恋 → like_male（喜欢男性）
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


def fix_sexual_orientation_values():
    """修正性取向字段的值"""

    print("=== 步骤1：查询所有虚拟用户 ===")

    with persona_engine.connect() as conn:
        query = text("""
            SELECT id, name, gender, sexual_orientation
            FROM profiles
            WHERE id >= 9000
            ORDER BY id ASC
        """)
        result = conn.execute(query)
        users = [(row[0], row[1], row[2], row[3]) for row in result]

    print(f"找到 {len(users)} 个虚拟用户")

    # 统计当前值分布
    print("\n当前性取向值分布：")
    from collections import Counter
    orientation_count = Counter(row[3] for row in users)
    for orientation, count in orientation_count.items():
        print(f"  {orientation}: {count} 个用户")

    print("\n=== 步骤2：生成修正方案 ===")

    updates = []
    male_hetero = 0
    male_homo = 0
    female_hetero = 0
    female_homo = 0

    for id, name, gender, current_orientation in users:
        # 根据性别重新分配性取向（10%同性恋，90%异性恋）
        if gender == "男":
            # 男性：90%异性恋（like_female），10%同性恋（like_male）
            orientation = rng.choice(["like_female"] * 9 + ["like_male"] * 1)
            if orientation == "like_female":
                male_hetero += 1
            else:
                male_homo += 1
        elif gender == "女":
            # 女性：90%异性恋（like_male），10%同性恋（like_female）
            orientation = rng.choice(["like_male"] * 9 + ["like_female"] * 1)
            if orientation == "like_male":
                female_hetero += 1
            else:
                female_homo += 1
        else:
            # 性别未知，默认异性恋
            orientation = "like_male"
            print(f"⚠️ 用户 {id} ({name}) 性别未知：{gender}")

        updates.append((id, orientation))

    print(f"\n修正方案统计：")
    print(f"  男性异性恋（like_female）：{male_hetero} 个")
    print(f"  男性同性恋（like_male）：{male_homo} 个")
    print(f"  女性异性恋（like_male）：{female_hetero} 个")
    print(f"  女性同性恋（like_female）：{female_homo} 个")

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

    print("\n✅ 批量修正完成")

    # 验证修正结果
    print("\n=== 步骤4：验证修正结果 ===")

    with persona_engine.connect() as conn:
        query = text("""
            SELECT gender, sexual_orientation, COUNT(*) as count
            FROM profiles
            WHERE id >= 9000
            GROUP BY gender, sexual_orientation
            ORDER BY gender, sexual_orientation
        """)
        result = conn.execute(query)

        print("\n修正后的性别-性取向分布：")
        print("-" * 50)
        for row in result:
            gender, orientation, count = row
            print(f"{gender:6} | {orientation:12} | {count:6} 个用户")

    print("\n=== 示例用户验证 ===")

    # 查询徐依嘉的修正结果
    with persona_engine.connect() as conn:
        query = text("""
            SELECT id, name, gender, sexual_orientation
            FROM profiles
            WHERE name = '徐依嘉'
            LIMIT 5
        """)
        result = conn.execute(query)

        print("\n徐依嘉的修正结果：")
        for row in result:
            id, name, gender, orientation = row
            print(f"  ID={id}")
            print(f"  姓名={name}")
            print(f"  性别={gender}")
            print(f"  性取向={orientation} ← 【修正后】")

            if gender == "女" and orientation == "like_male":
                print("  ✅ 验证通过：女性 + like_male → 应筛选男性候选人")
            elif gender == "女" and orientation == "like_female":
                print("  ⚠️ 同性恋女性：应筛选女性候选人")
            elif gender == "男":
                print(f"  ⚠️ 用户性别为男性（预期女性）")


if __name__ == "__main__":
    fix_sexual_orientation_values()