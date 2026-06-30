#!/usr/bin/env python3
"""Initialize MySQL schemas and seed data for frontend Playwright E2E (CI / local)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_ROOT = REPO_ROOT / "external-systems" / "partner-http-gateway"
CHAT_ROOT = REPO_ROOT / "external-systems" / "partner-chat-system"
REC_ROOT = REPO_ROOT / "external-systems" / "partner-recommendation-system"
MM_ROOT = REPO_ROOT / "external-systems" / "partner-matchmaking-system"

for root in (REPO_ROOT, GATEWAY_ROOT, CHAT_ROOT, REC_ROOT, MM_ROOT):
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)

import outer_system_mysql_schema as mysql_schema  # noqa: E402
from db_migrations.runner import initialize_target_database, target_env_var  # noqa: E402
from gateway_tests.helpers import (  # noqa: E402
    auth_headers,
    call_gateway_json,
    ensure_search_schema,
    insert_search_profile,
    search_test_config,
)

MYSQL_HOST = os.environ.get("HER_E2E_MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.environ.get("HER_E2E_MYSQL_PORT", "3307"))
MYSQL_USER = os.environ.get("HER_E2E_MYSQL_USER", "root")
MYSQL_PASSWORD = mysql_schema.parse_mysql_dsn(f"mysql://{MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/bootstrap")["password"]

SEARCH_DSN = (
    f"mysql://{MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/her"
    "?table=profiles&photos_table=profile_photos"
)

TARGET_DSNS = {
    "chat": f"mysql://{MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/her_chat",
    "recommendation": f"mysql://{MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/her_recommendation",
    "matchmaking": f"mysql://{MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/her_matchmaking",
    "discovery": f"mysql://{MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/her_discovery",
    "relationship_ledger": f"mysql://{MYSQL_USER}@{MYSQL_HOST}:{MYSQL_PORT}/her_relationship_ledger",
}

STATIC_TOKENS = {
    "token-ops": {
        "actor_id": "ops-1",
        "roles": ["ops_operator", "service_worker"],
    },
    "token-user-a": {"actor_id": "user-a", "roles": ["end_user"]},
    "token-user-b": {"actor_id": "user-b", "roles": ["end_user"]},
    "token-requester-70001": {"actor_id": "70001", "roles": ["end_user"]},
}


def wait_for_mysql(max_attempts: int = 30) -> None:
    import pymysql

    for attempt in range(max_attempts):
        try:
            conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD)
            conn.close()
            print(f"[e2e-bootstrap] mysql ready on {MYSQL_HOST}:{MYSQL_PORT}")
            return
        except Exception as exc:  # noqa: BLE001
            if attempt + 1 == max_attempts:
                raise RuntimeError(f"MySQL not ready after {max_attempts} attempts: {exc}") from exc
            time.sleep(2)


def _env_flag(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def ensure_databases(*, reset: bool = True) -> None:
    import pymysql

    names = {"her", "her_chat", "her_recommendation", "her_matchmaking", "her_discovery", "her_relationship_ledger"}
    conn = pymysql.connect(host=MYSQL_HOST, port=MYSQL_PORT, user=MYSQL_USER, password=MYSQL_PASSWORD)
    try:
        with conn.cursor() as cursor:
            for name in sorted(names):
                if reset:
                    cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
                cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4")
        conn.commit()
    finally:
        conn.close()
    print(f"[e2e-bootstrap] databases {'reset and ' if reset else ''}ensured")


def migrate_targets() -> None:
    for target, dsn in TARGET_DSNS.items():
        os.environ[target_env_var(target)] = dsn
        cfg = mysql_schema.parse_mysql_dsn(dsn)
        mysql_schema.ensure_database(cfg)
        conn = mysql_schema.mysql_database_connect(cfg)
        try:
            result = initialize_target_database(
                conn,
                target=target,
                config=cfg,
                mode="migrate",
                source=dsn,
            )
            applied = [m.get("migration_id") for m in result.get("applied", [])]
            print(f"[e2e-bootstrap] migrated {target}: applied={applied or '(none)'}")
        finally:
            conn.close()

    os.environ["HER_PROFILE_SOURCE_DSN"] = SEARCH_DSN
    from partner_search.search_snapshot_store import ensure_search_snapshot_table

    ensure_search_snapshot_table()
    print("[e2e-bootstrap] ensured partner_search_snapshots")


def seed_search_profiles() -> None:
    config = search_test_config(SEARCH_DSN)
    ensure_search_schema(config)
    active_at = datetime(2026, 5, 7, 10, 0, 0)
    insert_search_profile(
        config,
        (
            9001,
            "E2E候选人",
            "女",
            27,
            "上海",
            "本科",
            "产品经理",
            "20-30万/年",
            "未婚",
            0,
            "认真恋爱",
            "active",
            "offline",
            "offline_verified",
            "verified",
            "verified",
            "verified",
            "approved",
            0,
            3,
            "生活规律",
            "主动沟通",
            "愿意长期关系",
            "E2E seed",
            active_at,
        ),
    )
    insert_search_profile(
        config,
        (
            9002,
            "E2E无锡候选人",
            "女",
            29,
            "无锡",
            "硕士",
            "中学老师",
            "20-30万/年",
            "未婚",
            0,
            "认真恋爱",
            "active",
            "offline",
            "offline_verified",
            "verified",
            "verified",
            "verified",
            "approved",
            0,
            3,
            "生活规律",
            "主动沟通",
            "愿意长期关系",
            "E2E seed wuxi",
            active_at,
        ),
    )
    print("[e2e-bootstrap] search profiles seeded")


def seed_matchmaking_demo_case() -> None:
    """Allow /v1/timeline for case-frontend-demo without auth (actor=None path)."""
    cfg = mysql_schema.parse_mysql_dsn(TARGET_DSNS["matchmaking"])
    conn = mysql_schema.mysql_database_connect(cfg)
    now = datetime(2026, 5, 8, 22, 0, 0)
    empty_json = "{}"
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM match_cases WHERE case_id = %s", ("case-frontend-demo",))
            cursor.execute("DELETE FROM matchmaking_pairs WHERE pair_key = %s", ("pair-e2e-demo",))
            cursor.execute(
                "DELETE FROM matchmaking_pool_members WHERE member_id IN (%s, %s)",
                ("mem-e2e-a", "mem-e2e-b"),
            )
            cursor.execute(
                """
                INSERT INTO matchmaking_pool_members (
                  member_id, user_key, source, self_profile_json, search_criteria_json,
                  status, is_still_searching, allowed_channels_json, min_pair_score,
                  daily_case_cap, refresh_interval_hours, limit_count, needs_refresh,
                  created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    "mem-e2e-a",
                    "user-a",
                    SEARCH_DSN,
                    empty_json,
                    empty_json,
                    "active",
                    1,
                    "[]",
                    1,
                    5,
                    24,
                    5,
                    0,
                    now,
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO matchmaking_pool_members (
                  member_id, user_key, source, self_profile_json, search_criteria_json,
                  status, is_still_searching, allowed_channels_json, min_pair_score,
                  daily_case_cap, refresh_interval_hours, limit_count, needs_refresh,
                  created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    "mem-e2e-b",
                    "user-b",
                    SEARCH_DSN,
                    empty_json,
                    empty_json,
                    "active",
                    1,
                    "[]",
                    1,
                    5,
                    24,
                    5,
                    0,
                    now,
                    now,
                ),
            )
            cursor.execute(
                """
                INSERT INTO matchmaking_pairs (
                  pair_key, member_low_id, member_high_id,
                  score_low_to_high, score_high_to_low, pair_score, pair_status,
                  latest_payload_json, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                ("pair-e2e-demo", "mem-e2e-a", "mem-e2e-b", 80, 80, 80, "case_opened", empty_json, now, now),
            )
            cursor.execute(
                """
                INSERT INTO match_cases (
                  case_id, pair_key, initiator_type, case_type, status,
                  first_contact_member_id, second_contact_member_id,
                  created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    "case-frontend-demo",
                    "pair-e2e-demo",
                    "system",
                    "matchmaking",
                    "pending_first_contact",
                    "mem-e2e-a",
                    "mem-e2e-b",
                    now,
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    print("[e2e-bootstrap] matchmaking case-frontend-demo seeded")


def seed_chat_demo_case() -> None:
    from gateway.app import PartnerGateway

    os.environ["PARTNER_GATEWAY_STATIC_TOKENS_JSON"] = json.dumps(STATIC_TOKENS)
    os.environ["HER_RELATION_LEDGER_DB"] = TARGET_DSNS["relationship_ledger"]
    os.environ["HER_PROXY_INTRO_STORAGE"] = "matchmaking"
    os.environ["HER_PROFILE_SOURCE_DSN"] = SEARCH_DSN

    gw = PartnerGateway(
        recommendation_dsn=TARGET_DSNS["recommendation"],
        matchmaking_dsn=TARGET_DSNS["matchmaking"],
        chat_dsn=TARGET_DSNS["chat"],
        relation_ledger_dsn=TARGET_DSNS["relationship_ledger"],
        db_pool_max=0,
    )

    status, payload = call_gateway_json(
        gw,
        "POST",
        "/v2/chat/cases/case-frontend-demo/assistant-layout",
        body={
            "relation_key": "rel-frontend-demo",
            "participant_a_id": "user-a",
            "participant_b_id": "user-b",
            "agent_id": "agent-c",
            "now": "2026-05-08 22:00:00",
        },
        extra=auth_headers("token-ops"),
    )
    if not str(status).startswith("201"):
        raise RuntimeError(f"assistant-layout failed: {status} {payload}")

    conversations = payload.get("layout", {}).get("conversations", [])
    main_id = next(
        (
            item["conversation_id"]
            for item in conversations
            if item.get("metadata", {}).get("layout_role") == "main_group"
        ),
        None,
    )
    if not main_id:
        raise RuntimeError("main_group conversation missing from assistant-layout")

    status, msg_payload = call_gateway_json(
        gw,
        "POST",
        f"/v2/chat/conversations/{main_id}/messages",
        body={
            "author_id": "user-b",
            "source": "user",
            "body": "E2E seed hello",
            "now": "2026-05-08 22:05:00",
        },
        extra=auth_headers("token-user-b"),
    )
    if not str(status).startswith("201"):
        raise RuntimeError(f"seed message failed: {status} {msg_payload}")

    print(f"[e2e-bootstrap] chat case-frontend-demo seeded (main={main_id})")


def export_env_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "PARTNER_GATEWAY_BASE_URL=http://127.0.0.1:8080",
        "PARTNER_GATEWAY_API_KEY=",
        f"PARTNER_CHAT_DB={TARGET_DSNS['chat']}",
        f"PARTNER_RECOMMENDATION_DB={TARGET_DSNS['recommendation']}",
        f"PARTNER_MATCHMAKING_DB={TARGET_DSNS['matchmaking']}",
        f"PARTNER_DISCOVERY_DB={TARGET_DSNS['discovery']}",
        f"HER_RELATION_LEDGER_DB={TARGET_DSNS['relationship_ledger']}",
        "HER_RELATION_LEDGER_READ_MODE=ledger_primary",
        "HER_PROXY_INTRO_STORAGE=matchmaking",
        f"HER_PROFILE_SOURCE_DSN={SEARCH_DSN}",
        "PARTNER_GATEWAY_DB_POOL_MAX=16",
        "PARTNER_SEARCH_CACHE_TTL_SECONDS=120",
        "PARTNER_SEARCH_CACHE_MAX_ENTRIES=256",
        "PARTNER_SEARCH_SNAPSHOT_PERSIST=1",
        "NEXT_PUBLIC_HER_REQUESTER_ID=70001",
        "NEXT_PUBLIC_HER_PROFILE_ID=10001",
        "NEXT_PUBLIC_HER_USER_ID=user-a",
        "NEXT_PUBLIC_HER_CASE_ID=case-frontend-demo",
        "NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=false",
        "NEXT_PUBLIC_ENABLE_DEMO_NAV=true",
        "NEXT_PUBLIC_USE_AUTH_STUB=false",
        "NEXT_PUBLIC_E2E_GATEWAY_AUTH=true",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[e2e-bootstrap] wrote {path}")


def main() -> None:
    reset = _env_flag("HER_E2E_BOOTSTRAP_RESET", False)
    seed_demo = _env_flag("HER_E2E_BOOTSTRAP_SEED_DEMO", False)
    wait_for_mysql()
    ensure_databases(reset=reset)
    migrate_targets()
    if seed_demo:
        seed_search_profiles()
        seed_matchmaking_demo_case()
        seed_chat_demo_case()

    env_local = REPO_ROOT / "frontend" / "her-app" / ".env.local"
    export_env_file(env_local)
    try:
        subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "tech_optimization_cutover.py"), "--skip-validate-env"],
            cwd=str(REPO_ROOT),
            check=True,
        )
    except Exception as exc:
        print(f"[e2e-bootstrap] warning: tech optimization cutover skipped: {exc}")

    for key, value in TARGET_DSNS.items():
        os.environ[target_env_var(key)] = value
    print("[e2e-bootstrap] ok")


if __name__ == "__main__":
    main()
