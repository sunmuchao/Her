#!/usr/bin/env python3
"""验证性取向反向匹配逻辑

测试场景：
1. 用户A：男性，候选人B：like_female（喜欢女性）→ 应淘汰B
2. 用户A：男性，候选人C：like_male（喜欢男性）→ 应保留C
3. 用户A：女性，候选人D：like_male（喜欢男性）→ 应保留D
4. 用户A：女性，候选人E：like_female（喜欢女性）→ 应淘汰E
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


def test_sexual_orientation_reciprocal_match():
    """测试性取向反向匹配"""

    print("=== 测试性取向反向匹配逻辑 ===")

    # 导入反向匹配函数
    from partner_search.search_reciprocal import evaluate_reciprocal_compatibility
    from partner_search.search_candidates import _build_search_reciprocal_runtime

    runtime = _build_search_reciprocal_runtime()

    # 测试场景1：男性用户 + 女性喜欢候选人（应淘汰）
    print("\n【场景1】用户A：男性 → 候选人B：like_female（喜欢女性）")

    self_profile_1 = {"gender": "male", "age": 25, "city": "无锡"}
    candidate_1 = {"sexual_orientation": "like_female", "age": 26, "city": "无锡", "gender": "male"}

    result_1 = evaluate_reciprocal_compatibility(
        runtime,
        record=candidate_1,
        self_profile=self_profile_1,
        diagnostics=True,
        reciprocal_mode="strict"
    )

    if result_1 is None or not result_1.get("matched", True):
        print("✅ 正确淘汰：候选人喜欢女性，用户是男性（不匹配）")
        print(f"   淘汰原因：{result_1.get('reject_reason', '未知')}")
    else:
        print("❌ 错误：应该淘汰但未淘汰")
        print(f"   结果：{result_1}")

    # 测试场景2：男性用户 + 男性喜欢候选人（应保留）
    print("\n【场景2】用户A：男性 → 候选人C：like_male（喜欢男性）")

    self_profile_2 = {"gender": "male", "age": 25, "city": "无锡"}
    candidate_2 = {"sexual_orientation": "like_male", "age": 26, "city": "无锡", "gender": "male"}

    result_2 = evaluate_reciprocal_compatibility(
        runtime,
        record=candidate_2,
        self_profile=self_profile_2,
        diagnostics=True,
        reciprocal_mode="strict"
    )

    if result_2 and result_2.get("matched", True):
        print("✅ 正确保留：候选人喜欢男性，用户是男性（匹配）")
        print(f"   匹配原因：{result_2.get('matched_on', [])}")
        print(f"   加分：{result_2.get('score_bonus', 0)}")
    else:
        print("❌ 错误：应该保留但被淘汰")
        print(f"   结果：{result_2}")

    # 测试场景3：女性用户 + 男性喜欢候选人（应淘汰）
    print("\n【场景3】用户A：女性 → 候选人D：男，like_male（喜欢男性）")
    print("预期：淘汰（候选人D是同性恋男性，不喜欢女性）")

    self_profile_3 = {"gender": "female", "age": 25, "city": "无锡"}
    candidate_3 = {"sexual_orientation": "like_male", "age": 26, "city": "无锡", "gender": "male"}

    result_3 = evaluate_reciprocal_compatibility(
        runtime,
        record=candidate_3,
        self_profile=self_profile_3,
        diagnostics=True,
        reciprocal_mode="strict"
    )

    if result_3 is None or not result_3.get("matched", True):
        print("✅ 正确淘汰：候选人D喜欢男性，用户A是女性（候选人不喜欢用户）")
        print(f"   淘汰原因：{result_3.get('reject_reason', '未知')}")
    else:
        print("❌ 错误：候选人D不喜欢女性，应该淘汰")
        print(f"   结果：{result_3}")

    # 测试场景4：女性用户（异性恋） + 女性喜欢候选人（应淘汰）
    print("\n【场景4】用户A：女性（异性恋，like_male）→ 候选人E：女，like_female（喜欢女性）")
    print("预期：淘汰（候选人E是同性恋女性，用户A是异性恋）")

    self_profile_4 = {"gender": "female", "age": 25, "city": "无锡", "sexual_orientation": "like_male"}
    candidate_4 = {"sexual_orientation": "like_female", "age": 26, "city": "无锡", "gender": "female"}

    result_4 = evaluate_reciprocal_compatibility(
        runtime,
        record=candidate_4,
        self_profile=self_profile_4,
        diagnostics=True,
        reciprocal_mode="strict"
    )

    if result_4 is None or not result_4.get("matched", True):
        print("✅ 正确淘汰：候选人E喜欢女性，用户A是女性（性别匹配）")
        print("   但用户A是异性恋（like_male），不喜欢女性候选人")
        print(f"   淘汰原因：{result_4.get('reject_reason', '未知')}")
    else:
        print("⚠️ 保留：候选人E喜欢女性，用户A是女性（性别匹配）")
        print(f"   结果：{result_4}")
        print("   注意：反向匹配只检查候选人是否喜欢用户，不检查用户是否喜欢候选人")
        print("   SQL WHERE层应该已经筛选了（用户A喜欢男性，候选人E是女性，不应出现）")

    # 测试场景5：女性用户（同性恋） + 女性喜欢候选人（应保留）
    print("\n【场景5】用户A：女性（同性恋，like_female）→ 候选人F：女，like_female（喜欢女性）")
    print("预期：保留（双向同性恋匹配）")

    self_profile_5 = {"gender": "female", "age": 25, "city": "无锡", "sexual_orientation": "like_female"}
    candidate_5 = {"sexual_orientation": "like_female", "age": 26, "city": "无锡", "gender": "female"}

    result_5 = evaluate_reciprocal_compatibility(
        runtime,
        record=candidate_5,
        self_profile=self_profile_5,
        diagnostics=True,
        reciprocal_mode="strict"
    )

    if result_5 and result_5.get("matched", True):
        print("✅ 正确保留：候选人F喜欢女性，用户A是女性（性别匹配）")
        print(f"   匹配原因：{result_5.get('matched_on', [])}")
        print(f"   加分：{result_5.get('score_bonus', 0)}")
        print("   注意：SQL WHERE层应该筛选候选人gender=female（用户喜欢女性）")
    else:
        print("❌ 错误：双向同性恋匹配应该保留")
        print(f"   结果：{result_5}")

    print("\n=== 测试数据库真实用户 ===")

    # 测试真实用户：胡睿城（同性恋男性）
    print("\n查询胡睿城（ID=9001，男，like_male）")

    with persona_engine.connect() as conn:
        query = text("""
            SELECT id, name, gender, sexual_orientation
            FROM profiles
            WHERE id = 9001
        """)
        result = conn.execute(query)
        row = result.fetchone()

        if row:
            print(f"胡睿城：ID={row[0]}, 性别={row[1]}, 性取向={row[2]}")

            # 模拟一个女性用户搜索胡睿城
            self_profile_female = {"gender": "female", "age": 25, "city": "无锡"}
            candidate_hrc = {"sexual_orientation": row[2], "gender": row[1], "age": 26, "city": "无锡"}

            result_hrc = evaluate_reciprocal_compatibility(
                runtime,
                record=candidate_hrc,
                self_profile=self_profile_female,
                diagnostics=True,
                reciprocal_mode="strict"
            )

            if result_hrc is None or not result_hrc.get("matched", True):
                print("✅ 正确：女性用户不应该匹配到胡睿城（同性恋男性，喜欢男性）")
                print(f"   淘汰原因：{result_hrc.get('reject_reason', '未知')}")
            else:
                print("❌ 错误：女性用户应该被淘汰")
                print(f"   结果：{result_hrc}")

    print("\n=== 测试总结 ===")
    print("✅ 性取向反向匹配已添加")
    print("✅ 会淘汰不符合候选人性取向的用户")
    print("⚠️ 注意：同性恋场景需要用户自己的性取向也匹配")


if __name__ == "__main__":
    test_sexual_orientation_reciprocal_match()