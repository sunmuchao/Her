#!/usr/bin/env python3
"""验证双向匹配逻辑

关键验证场景：
- A用户：男，like_male（同性恋）→ 目标筛选：gender = male
- B用户：男，like_female（异性恋）→ B喜欢女性，不喜欢男性
- **预期结果**：A不应该匹配到B（双向匹配：B也要喜欢A的性别）

验证步骤：
1. 找一个同性恋男性用户（like_male）
2. 找一个异性恋男性用户（like_female）
3. 验证：同性恋男性不应该匹配到异性恋男性
"""

from __future__ import annotations

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


def verify_bidirectional_matching():
    """验证双向匹配逻辑"""

    print("=== 步骤1：查找同性恋男性用户（like_male）===")

    with persona_engine.connect() as conn:
        query = text("""
            SELECT id, name, gender, sexual_orientation
            FROM profiles
            WHERE gender = '男' AND sexual_orientation = 'like_male'
            LIMIT 5
        """)
        result = conn.execute(query)
        gay_males = [(row[0], row[1], row[2], row[3]) for row in result]

    print(f"找到 {len(gay_males)} 个同性恋男性用户：")
    for id, name, gender, orientation in gay_males:
        print(f"  ID={id} 姓名={name} 性别={gender} 性取向={orientation}")

    if not gay_males:
        print("⚠️ 没有找到同性恋男性用户，无法验证")
        return

    print("\n=== 步骤2：查找异性恋男性用户（like_female）===")

    with persona_engine.connect() as conn:
        query = text("""
            SELECT id, name, gender, sexual_orientation
            FROM profiles
            WHERE gender = '男' AND sexual_orientation = 'like_female'
            LIMIT 10
        """)
        result = conn.execute(query)
        straight_males = [(row[0], row[1], row[2], row[3]) for row in result]

    print(f"找到 {len(straight_males)} 个异性恋男性用户：")
    for id, name, gender, orientation in straight_males[:5]:
        print(f"  ID={id} 姓名={name} 性别={gender} 性取向={orientation}")

    if not straight_males:
        print("⚠️ 没有找到异性恋男性用户，无法验证")
        return

    print("\n=== 步骤3：验证双向匹配逻辑 ===")

    # 选择一个同性恋男性用户作为A
    user_a = gay_males[0]
    print(f"\n用户A（同性恋男性）：")
    print(f"  ID={user_a[0]} 姓名={user_a[1]} 性取向={user_a[3]}（喜欢男性）")

    # 选择一个异性恋男性用户作为B
    user_b = straight_males[0]
    print(f"\n用户B（异性恋男性）：")
    print(f"  ID={user_b[0]} 姓名={user_b[1]} 性取向={user_b[3]}（喜欢女性）")

    print("\n【关键验证】：")
    print("  A是男性，喜欢男性 → 目标筛选：gender = male")
    print("  B是男性，符合A的筛选条件 ✓")
    print("  BUT：B是异性恋（like_female），只喜欢女性 ✗")
    print("  因此：A不应该匹配到B（双向匹配失败）")

    print("\n=== 步骤4：检查系统是否有双向匹配逻辑 ===")

    # 检查 match_domain 中是否有双向匹配的代码
    import subprocess

    print("搜索代码中的双向匹配逻辑...")
    result = subprocess.run(
        ["grep", "-r", "sexual_orientation", "match_domain/", "--include=*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True
    )

    if result.stdout:
        print("找到相关代码：")
        lines = result.stdout.strip().split("\n")[:10]
        for line in lines:
            print(f"  {line}")
    else:
        print("⚠️ 未找到双向匹配逻辑代码")

    print("\n=== 步骤5：验证徐依嘉的情况 ===")

    # 查询徐依嘉的数据
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
            print(f"  ID={row[0]}")
            print(f"  性别={row[1]}")
            print(f"  性取向={row[2]}")

            if row[1] == "女":
                if row[2] == "like_male":
                    print("  ✅ 异性恋女性：应该筛选男性候选人")
                elif row[2] == "like_female":
                    print("  ⚠️ 同性恋女性：应该筛选女性候选人")
                else:
                    print(f"  ❌ 性取向异常：{row[2]}")

    print("\n=== 总结 ===")

    if gay_males and straight_males:
        print("✅ 数据库中有同性恋和异性恋用户，可以验证双向匹配")
        print("⚠️ 需要确认系统代码是否实现了双向匹配逻辑")
        print("   即：A匹配B时，不仅要B符合A的条件，还要A符合B的条件")
    else:
        print("❌ 数据库数据不足，无法验证双向匹配")


if __name__ == "__main__":
    verify_bidirectional_matching()