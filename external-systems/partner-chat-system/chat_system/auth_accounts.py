"""Account, OTP, and session persistence for user auth."""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from profile_service import resolve_profile_source, upsert_profile_for_onboarding
from profile_service.persona_bridge import apply_persona_patch

from match_domain.onboarding_search import (
    age_from_birthday,
    build_onboarding_persona_patch,
    build_onboarding_profile_fields,
)

from .storage import inflate_json_columns, json_dumps, row_to_dict

logger = logging.getLogger(__name__)

OTP_SCENE_LOGIN = "login"
OTP_SCENE_BIND_PHONE = "bind_phone"
OTP_STATUS_ISSUED = "issued"
OTP_STATUS_VERIFIED = "verified"
OTP_STATUS_EXPIRED = "expired"
OTP_STATUS_BLOCKED = "blocked"

ACCOUNT_STATUS_ACTIVE = "active"
ONBOARDING_STATUS_NOT_STARTED = "not_started"
ONBOARDING_STATUS_COMPLETED = "completed"

LOGIN_METHOD_SMS = "sms"
LOGIN_METHOD_WECHAT = "wechat"
LOGIN_METHOD_ONE_TAP = "one_tap"
ROLE_END_USER = "end_user"

IDENTITY_TYPE_PHONE = "phone"
IDENTITY_TYPE_WECHAT_OPENID = "wechat_openid"
IDENTITY_TYPE_WECHAT_UNIONID = "wechat_unionid"

ONE_TAP_STATUS_CREATED = "created"
ONE_TAP_STATUS_VERIFIED = "verified"
ONE_TAP_STATUS_FAILED = "failed"
ONE_TAP_STATUS_EXPIRED = "expired"
ONE_TAP_TTL = timedelta(minutes=10)

OTP_TTL = timedelta(minutes=5)
OTP_RESEND_COOLDOWN = timedelta(seconds=60)
OTP_MAX_VERIFY_ATTEMPTS = 5
ACCESS_TOKEN_TTL = timedelta(hours=2)
REFRESH_TOKEN_TTL = timedelta(days=30)


class AuthDomainError(ValueError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = int(status_code)
        self.code = str(code)
        self.message = str(message)


def _utcnow(now: datetime | None = None) -> datetime:
    if now is not None:
        return now
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash_value(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _hash_code(*, phone: str, code: str, salt: str) -> str:
    return _hash_value(f"{phone}:{code}:{salt}")


def _mask_phone(phone: str) -> str:
    return f"{phone[:3]}****{phone[-4:]}"


def _generate_user_id() -> str:
    return f"usr-{uuid.uuid4().hex[:16]}"


def _generate_identity_id() -> str:
    return f"ident-{uuid.uuid4().hex[:16]}"


def _generate_challenge_id() -> str:
    return f"otp-{uuid.uuid4().hex[:16]}"


def _generate_session_id() -> str:
    return f"sess-{uuid.uuid4().hex[:16]}"


def _generate_event_id() -> str:
    return f"evt-{uuid.uuid4().hex[:16]}"


def _raw_token(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def _row(conn, sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    return row_to_dict(conn.execute(sql, params).fetchone())


def _active_user_by_phone(conn, phone: str) -> dict[str, Any] | None:
    row = _row(
        conn,
        """
        SELECT ua.*
        FROM user_accounts ua
        JOIN user_account_identities uai
          ON uai.user_id = ua.user_id
        WHERE uai.identity_type = 'phone'
          AND uai.identity_value = ?
          AND uai.status = 'active'
        LIMIT 1
        """,
        (phone,),
    )
    return row


def _active_user_by_wechat(
    conn,
    *,
    openid: str | None,
    unionid: str | None,
) -> dict[str, Any] | None:
    if unionid:
        row = _row(
            conn,
            """
            SELECT ua.*
            FROM user_accounts ua
            JOIN user_account_identities uai
              ON uai.user_id = ua.user_id
            WHERE uai.identity_type = ?
              AND uai.identity_value = ?
              AND uai.status = 'active'
            LIMIT 1
            """,
            (IDENTITY_TYPE_WECHAT_UNIONID, unionid),
        )
        if row:
            return row
    if openid:
        return _row(
            conn,
            """
            SELECT ua.*
            FROM user_accounts ua
            JOIN user_account_identities uai
              ON uai.user_id = ua.user_id
            WHERE uai.identity_type = ?
              AND uai.identity_value = ?
              AND uai.status = 'active'
            LIMIT 1
            """,
            (IDENTITY_TYPE_WECHAT_OPENID, openid),
        )
    return None


def _user_by_id(conn, user_id: str) -> dict[str, Any] | None:
    return row_to_dict(
        conn.execute(
            """
            SELECT *
            FROM user_accounts
            WHERE user_id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    )


def _onboarding_state(conn, user_id: str) -> dict[str, Any] | None:
    row = row_to_dict(
        conn.execute(
            """
            SELECT *
            FROM user_onboarding_profiles
            WHERE user_id = ?
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
    )
    return inflate_json_columns(
        row,
        basic_info=("basic_info_json", {}),
        preference=("preference_json", {}),
    )


def _log_event(
    conn,
    *,
    user_id: str | None,
    phone: str | None,
    event_type: str,
    result: str,
    reason_code: str | None = None,
    client_ip: str | None = None,
    device_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> None:
    ts = _utcnow(now)
    conn.execute(
        """
        INSERT INTO auth_login_events (
          event_id, user_id, phone, event_type, result, reason_code,
          client_ip, device_id, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
          _generate_event_id(),
          user_id,
          phone,
          event_type,
          result,
          reason_code,
          client_ip,
          device_id,
          json_dumps(metadata or {}),
          ts,
        ),
    )


def classify_phone_scenario(conn, phone: str) -> str:
    return "existing" if _active_user_by_phone(conn, phone) else "new"


def issue_sms_code(
    conn,
    *,
    phone: str,
    code: str,
    scene: str = OTP_SCENE_LOGIN,
    provider_name: str = "unknown",
    client_ip: str | None = None,
    device_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _utcnow(now)
    active = _row(
        conn,
        """
        SELECT *
        FROM auth_otp_challenges
        WHERE phone = ? AND scene = ? AND status = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (phone, scene, OTP_STATUS_ISSUED),
    )
    if active:
        resend_at = active.get("resend_available_at")
        if isinstance(resend_at, datetime) and ts < resend_at:
            seconds = max(1, int((resend_at - ts).total_seconds()))
            raise AuthDomainError(429, "sms_cooldown", f"发送过于频繁，请在 {seconds} 秒后重试")
        expires_at = active.get("expires_at")
        if isinstance(expires_at, datetime) and expires_at <= ts:
            conn.execute(
                "UPDATE auth_otp_challenges SET status = ?, updated_at = ? WHERE challenge_id = ?",
                (OTP_STATUS_EXPIRED, ts, active["challenge_id"]),
            )

    scenario = classify_phone_scenario(conn, phone)
    challenge_id = _generate_challenge_id()
    salt = secrets.token_hex(8)
    expires_at = ts + OTP_TTL
    resend_at = ts + OTP_RESEND_COOLDOWN
    conn.execute(
        """
        INSERT INTO auth_otp_challenges (
          challenge_id, phone, scene, scenario, code_hash, code_salt, status,
          expires_at, resend_available_at, verify_attempt_count, max_verify_attempts,
          client_ip, device_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
          challenge_id,
          phone,
          scene,
          scenario,
          _hash_code(phone=phone, code=code, salt=salt),
          salt,
          OTP_STATUS_ISSUED,
          expires_at,
          resend_at,
          0,
          OTP_MAX_VERIFY_ATTEMPTS,
          client_ip,
          device_id,
          ts,
          ts,
        ),
    )
    _log_event(
        conn,
        user_id=None,
        phone=phone,
        event_type="sms_send",
        result="success",
        client_ip=client_ip,
        device_id=device_id,
        metadata={"provider": provider_name, "scene": scene, "scenario": scenario},
        now=ts,
    )
    conn.commit()
    return {
        "challenge_id": challenge_id,
        "delivery": {
            "channel": "sms",
            "masked_phone": _mask_phone(phone),
            "expires_in_seconds": int(OTP_TTL.total_seconds()),
            "resend_in_seconds": int(OTP_RESEND_COOLDOWN.total_seconds()),
            "provider": provider_name,
        },
        "flow": {
            "scenario": scenario,
            "next_path": "" if scenario == "existing" else "/onboarding",
        },
    }


def _create_user_from_phone(conn, *, phone: str, now: datetime) -> dict[str, Any]:
    user_id = _generate_user_id()
    conn.execute(
        """
        INSERT INTO user_accounts (
          user_id, account_status, primary_phone, phone_verified_at, register_source,
          onboarding_status, first_login_at, last_login_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
          user_id,
          ACCOUNT_STATUS_ACTIVE,
          phone,
          now,
          LOGIN_METHOD_SMS,
          ONBOARDING_STATUS_NOT_STARTED,
          now,
          now,
          now,
          now,
        ),
    )
    conn.execute(
        """
        INSERT INTO user_account_identities (
          identity_id, user_id, identity_type, identity_value, is_primary, verified_at,
          bound_at, status, created_at, updated_at
        ) VALUES (?, ?, 'phone', ?, ?, ?, ?, 'active', ?, ?)
        """,
        (
          _generate_identity_id(),
          user_id,
          phone,
          1,
          now,
          now,
          now,
          now,
        ),
    )
    conn.execute(
        """
        INSERT INTO user_onboarding_profiles (
          user_id, onboarding_status, current_step, basic_info_json, preference_json,
          completed_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        (
          user_id,
          ONBOARDING_STATUS_NOT_STARTED,
          "basic_info",
          json_dumps({}),
          json_dumps({}),
          now,
          now,
        ),
    )
    return {
        "user_id": user_id,
        "account_status": ACCOUNT_STATUS_ACTIVE,
        "primary_phone": phone,
        "onboarding_status": ONBOARDING_STATUS_NOT_STARTED,
    }


def _create_user_without_phone(conn, *, register_source: str, now: datetime) -> dict[str, Any]:
    user_id = _generate_user_id()
    conn.execute(
        """
        INSERT INTO user_accounts (
          user_id, account_status, primary_phone, phone_verified_at, register_source,
          onboarding_status, first_login_at, last_login_at, created_at, updated_at
        ) VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            ACCOUNT_STATUS_ACTIVE,
            register_source,
            ONBOARDING_STATUS_NOT_STARTED,
            now,
            now,
            now,
            now,
        ),
    )
    conn.execute(
        """
        INSERT INTO user_onboarding_profiles (
          user_id, onboarding_status, current_step, basic_info_json, preference_json,
          completed_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)
        """,
        (
            user_id,
            ONBOARDING_STATUS_NOT_STARTED,
            "basic_info",
            json_dumps({}),
            json_dumps({}),
            now,
            now,
        ),
    )
    return {
        "user_id": user_id,
        "account_status": ACCOUNT_STATUS_ACTIVE,
        "primary_phone": None,
        "onboarding_status": ONBOARDING_STATUS_NOT_STARTED,
    }


def _ensure_identity(
    conn,
    *,
    user_id: str,
    identity_type: str,
    identity_value: str,
    is_primary: bool = False,
    verified_at: datetime | None = None,
    now: datetime,
) -> None:
    existing = _row(
        conn,
        """
        SELECT *
        FROM user_account_identities
        WHERE identity_type = ? AND identity_value = ?
        LIMIT 1
        """,
        (identity_type, identity_value),
    )
    if existing:
        if str(existing.get("user_id") or "") != str(user_id):
            raise AuthDomainError(409, "identity_conflict", f"{identity_type} is already bound to another account")
        conn.execute(
            """
            UPDATE user_account_identities
            SET is_primary = ?, verified_at = COALESCE(?, verified_at), status = 'active', updated_at = ?
            WHERE identity_id = ?
            """,
            (1 if is_primary else 0, verified_at, now, existing["identity_id"]),
        )
        return
    conn.execute(
        """
        INSERT INTO user_account_identities (
          identity_id, user_id, identity_type, identity_value, is_primary, verified_at,
          bound_at, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        (
            _generate_identity_id(),
            user_id,
            identity_type,
            identity_value,
            1 if is_primary else 0,
            verified_at,
            now,
            now,
            now,
        ),
    )


def _challenge_for_phone(
    conn,
    *,
    phone: str,
    challenge_id: str | None,
    scene: str,
) -> dict[str, Any] | None:
    if challenge_id:
        return _row(
            conn,
            """
            SELECT *
            FROM auth_otp_challenges
            WHERE challenge_id = ? AND phone = ?
            LIMIT 1
            """,
            (challenge_id, phone),
        )
    return _row(
        conn,
        """
        SELECT *
        FROM auth_otp_challenges
        WHERE phone = ? AND scene = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (phone, scene),
    )


def _consume_sms_challenge(
    conn,
    *,
    phone: str,
    code: str,
    challenge_id: str | None,
    scene: str,
    client_ip: str | None,
    device_id: str | None,
    now: datetime,
) -> dict[str, Any]:
    challenge = _challenge_for_phone(conn, phone=phone, challenge_id=challenge_id, scene=scene)
    if not challenge:
        raise AuthDomainError(400, "code_not_requested", "请先获取验证码")
    if challenge.get("status") != OTP_STATUS_ISSUED:
        if challenge.get("status") == OTP_STATUS_EXPIRED:
            raise AuthDomainError(400, "code_expired", "验证码已过期，请重新获取")
        raise AuthDomainError(400, "code_not_available", "验证码当前不可用，请重新获取")
    expires_at = challenge.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at <= now:
        conn.execute(
            "UPDATE auth_otp_challenges SET status = ?, updated_at = ? WHERE challenge_id = ?",
            (OTP_STATUS_EXPIRED, now, challenge["challenge_id"]),
        )
        conn.commit()
        raise AuthDomainError(400, "code_expired", "验证码已过期，请重新获取")
    attempts = int(challenge.get("verify_attempt_count") or 0)
    max_attempts = int(challenge.get("max_verify_attempts") or OTP_MAX_VERIFY_ATTEMPTS)
    expected_hash = _hash_code(phone=phone, code=code, salt=str(challenge.get("code_salt") or ""))
    if expected_hash != str(challenge.get("code_hash") or ""):
        attempts += 1
        next_status = OTP_STATUS_BLOCKED if attempts >= max_attempts else OTP_STATUS_ISSUED
        conn.execute(
            """
            UPDATE auth_otp_challenges
            SET verify_attempt_count = ?, status = ?, updated_at = ?
            WHERE challenge_id = ?
            """,
            (attempts, next_status, now, challenge["challenge_id"]),
        )
        _log_event(
            conn,
            user_id=None,
            phone=phone,
            event_type="sms_verify",
            result="fail",
            reason_code="code_mismatch",
            client_ip=client_ip,
            device_id=device_id,
            metadata={"attempt_count": attempts, "scene": scene},
            now=now,
        )
        conn.commit()
        message = "验证码错误，请重新输入" if attempts < max_attempts else "输入错误次数过多，请重新获取验证码"
        raise AuthDomainError(400 if attempts < max_attempts else 429, "code_mismatch", message)
    conn.execute(
        """
        UPDATE auth_otp_challenges
        SET status = ?, updated_at = ?
        WHERE challenge_id = ?
        """,
        (OTP_STATUS_VERIFIED, now, challenge["challenge_id"]),
    )
    return challenge


def _create_session(
    conn,
    *,
    user_id: str,
    login_method: str,
    client_type: str | None,
    client_ip: str | None,
    device_id: str | None,
    now: datetime,
) -> dict[str, Any]:
    session_id = _generate_session_id()
    access_token = _raw_token("atk")
    refresh_token = _raw_token("rtk")
    access_expires_at = now + ACCESS_TOKEN_TTL
    refresh_expires_at = now + REFRESH_TOKEN_TTL
    conn.execute(
        """
        INSERT INTO auth_sessions (
          session_id, user_id, access_token_hash, refresh_token_hash, login_method,
          client_type, client_ip, device_id, access_expires_at, refresh_expires_at,
          last_seen_at, revoked_at, revoke_reason, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
        """,
        (
          session_id,
          user_id,
          _hash_value(access_token),
          _hash_value(refresh_token),
          login_method,
          client_type,
          client_ip,
          device_id,
          access_expires_at,
          refresh_expires_at,
          now,
          now,
          now,
        ),
    )
    return {
        "session_id": session_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "Bearer",
        "expires_in_seconds": int(ACCESS_TOKEN_TTL.total_seconds()),
        "refresh_expires_in_seconds": int(REFRESH_TOKEN_TTL.total_seconds()),
        "access_expires_at": access_expires_at,
        "refresh_expires_at": refresh_expires_at,
    }


def verify_sms_code(
    conn,
    *,
    phone: str,
    code: str,
    challenge_id: str | None = None,
    scene: str = OTP_SCENE_LOGIN,
    client_ip: str | None = None,
    device_id: str | None = None,
    client_type: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _utcnow(now)
    _consume_sms_challenge(
        conn,
        phone=phone,
        code=code,
        challenge_id=challenge_id,
        scene=scene,
        client_ip=client_ip,
        device_id=device_id,
        now=ts,
    )
    user = _active_user_by_phone(conn, phone)
    is_new_user = user is None
    if user is None:
        user = _create_user_from_phone(conn, phone=phone, now=ts)
    else:
        conn.execute(
            """
            UPDATE user_accounts
            SET last_login_at = ?, primary_phone = COALESCE(primary_phone, ?), phone_verified_at = COALESCE(phone_verified_at, ?), updated_at = ?
            WHERE user_id = ?
            """,
            (ts, phone, ts, ts, user["user_id"]),
        )
        onboarding = _onboarding_state(conn, user["user_id"])
        user["onboarding_status"] = (
            onboarding.get("onboarding_status")
            if onboarding
            else user.get("onboarding_status") or ONBOARDING_STATUS_NOT_STARTED
        )
    session = _create_session(
        conn,
        user_id=str(user["user_id"]),
        login_method=LOGIN_METHOD_SMS,
        client_type=client_type,
        client_ip=client_ip,
        device_id=device_id,
        now=ts,
    )
    _log_event(
        conn,
        user_id=str(user["user_id"]),
        phone=phone,
        event_type="login_success",
        result="success",
        client_ip=client_ip,
        device_id=device_id,
        metadata={"login_method": LOGIN_METHOD_SMS, "session_id": session["session_id"]},
        now=ts,
    )
    conn.commit()
    return {
        "verified": True,
        "user": {
            "user_id": str(user["user_id"]),
            "is_new_user": is_new_user,
            "account_status": user.get("account_status") or ACCOUNT_STATUS_ACTIVE,
            "onboarding_status": user.get("onboarding_status") or ONBOARDING_STATUS_NOT_STARTED,
        },
        "session": session,
        "flow": {
            "scenario": "new" if is_new_user else "existing",
            "next_path": "/onboarding" if is_new_user else "",
        },
    }


def bind_phone_with_sms(
    conn,
    *,
    user_id: str,
    phone: str,
    code: str,
    challenge_id: str | None = None,
    client_ip: str | None = None,
    device_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _utcnow(now)
    user = _user_by_id(conn, user_id)
    if not user or user.get("account_status") != ACCOUNT_STATUS_ACTIVE:
        raise AuthDomainError(404, "user_not_found", "user account was not found")
    existing_user = _active_user_by_phone(conn, phone)
    if existing_user and str(existing_user.get("user_id") or "") != str(user_id):
        raise AuthDomainError(409, "phone_already_bound", "该手机号已绑定其他账号")
    _consume_sms_challenge(
        conn,
        phone=phone,
        code=code,
        challenge_id=challenge_id,
        scene=OTP_SCENE_BIND_PHONE,
        client_ip=client_ip,
        device_id=device_id,
        now=ts,
    )
    _ensure_identity(
        conn,
        user_id=user_id,
        identity_type=IDENTITY_TYPE_PHONE,
        identity_value=phone,
        is_primary=True,
        verified_at=ts,
        now=ts,
    )
    conn.execute(
        """
        UPDATE user_accounts
        SET primary_phone = ?, phone_verified_at = ?, updated_at = ?
        WHERE user_id = ?
        """,
        (phone, ts, ts, user_id),
    )
    _log_event(
        conn,
        user_id=user_id,
        phone=phone,
        event_type="bind_phone",
        result="success",
        client_ip=client_ip,
        device_id=device_id,
        now=ts,
    )
    conn.commit()
    updated = _user_by_id(conn, user_id) or user
    return {
        "ok": True,
        "user": {
            "user_id": user_id,
            "phone": updated.get("primary_phone"),
            "phone_bound": bool(updated.get("primary_phone")),
            "account_status": updated.get("account_status") or ACCOUNT_STATUS_ACTIVE,
            "onboarding_status": updated.get("onboarding_status") or ONBOARDING_STATUS_NOT_STARTED,
        },
    }


def _create_wechat_binding(
    conn,
    *,
    user_id: str,
    openid: str,
    unionid: str | None,
    nickname: str | None,
    avatar_url: str | None,
    raw_profile: dict[str, Any],
    now: datetime,
) -> None:
    _ensure_identity(
        conn,
        user_id=user_id,
        identity_type=IDENTITY_TYPE_WECHAT_OPENID,
        identity_value=openid,
        verified_at=now,
        now=now,
    )
    if unionid:
        _ensure_identity(
            conn,
            user_id=user_id,
            identity_type=IDENTITY_TYPE_WECHAT_UNIONID,
            identity_value=unionid,
            verified_at=now,
            now=now,
        )
    existing = _row(
        conn,
        """
        SELECT *
        FROM wechat_accounts
        WHERE openid = ?
        LIMIT 1
        """,
        (openid,),
    )
    if existing:
        conn.execute(
            """
            UPDATE wechat_accounts
            SET user_id = ?, unionid = ?, nickname = ?, avatar_url = ?, raw_profile_json = ?,
                bound_at = COALESCE(bound_at, ?), last_login_at = ?, status = 'active', updated_at = ?
            WHERE wechat_account_id = ?
            """,
            (
                user_id,
                unionid,
                nickname,
                avatar_url,
                json_dumps(raw_profile),
                now,
                now,
                now,
                existing["wechat_account_id"],
            ),
        )
        return
    conn.execute(
        """
        INSERT INTO wechat_accounts (
          wechat_account_id, user_id, openid, unionid, nickname, avatar_url, raw_profile_json,
          bound_at, last_login_at, status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
        """,
        (
            f"wx-{uuid.uuid4().hex[:16]}",
            user_id,
            openid,
            unionid,
            nickname,
            avatar_url,
            json_dumps(raw_profile),
            now,
            now,
            now,
            now,
        ),
    )


def login_with_wechat_profile(
    conn,
    *,
    openid: str,
    unionid: str | None = None,
    nickname: str | None = None,
    avatar_url: str | None = None,
    raw_profile: dict[str, Any] | None = None,
    client_ip: str | None = None,
    device_id: str | None = None,
    client_type: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _utcnow(now)
    if not openid:
        raise AuthDomainError(400, "wechat_openid_required", "wechat openid is required")
    user = _active_user_by_wechat(conn, openid=openid, unionid=unionid)
    is_new_user = user is None
    if user is None:
        user = _create_user_without_phone(conn, register_source=LOGIN_METHOD_WECHAT, now=ts)
    _create_wechat_binding(
        conn,
        user_id=str(user["user_id"]),
        openid=openid,
        unionid=unionid,
        nickname=nickname,
        avatar_url=avatar_url,
        raw_profile=raw_profile or {},
        now=ts,
    )
    session = _create_session(
        conn,
        user_id=str(user["user_id"]),
        login_method=LOGIN_METHOD_WECHAT,
        client_type=client_type,
        client_ip=client_ip,
        device_id=device_id,
        now=ts,
    )
    _log_event(
        conn,
        user_id=str(user["user_id"]),
        phone=user.get("primary_phone"),
        event_type="wechat_login",
        result="success",
        client_ip=client_ip,
        device_id=device_id,
        metadata={"openid": openid, "unionid": unionid, "session_id": session["session_id"]},
        now=ts,
    )
    conn.commit()
    updated = _user_by_id(conn, str(user["user_id"])) or user
    return {
        "user": {
            "user_id": str(updated["user_id"]),
            "is_new_user": is_new_user,
            "account_status": updated.get("account_status") or ACCOUNT_STATUS_ACTIVE,
            "onboarding_status": updated.get("onboarding_status") or ONBOARDING_STATUS_NOT_STARTED,
            "phone_bound": bool(updated.get("primary_phone")),
        },
        "session": session,
        "flow": {
            "scenario": "new" if is_new_user else "existing",
            "next_path": "/bind-phone" if not updated.get("primary_phone") else ("/onboarding" if is_new_user else ""),
        },
        "wechat_profile": {
            "openid": openid,
            "unionid": unionid,
            "nickname": nickname,
            "avatar_url": avatar_url,
        },
    }


def create_one_tap_attempt(
    conn,
    *,
    provider: str,
    masked_phone: str,
    provider_payload: dict[str, Any] | None = None,
    operator_request_id: str | None = None,
    device_id: str | None = None,
    client_ip: str | None = None,
    client_type: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _utcnow(now)
    attempt_id = f"otl-{uuid.uuid4().hex[:16]}"
    expires_at = ts + ONE_TAP_TTL
    conn.execute(
        """
        INSERT INTO auth_one_tap_attempts (
          attempt_id, provider, masked_phone, operator_request_id, status, provider_payload_json,
          client_ip, device_id, client_type, verified_phone, expires_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
        """,
        (
            attempt_id,
            provider,
            masked_phone,
            operator_request_id,
            ONE_TAP_STATUS_CREATED,
            json_dumps(provider_payload or {}),
            client_ip,
            device_id,
            client_type,
            expires_at,
            ts,
            ts,
        ),
    )
    conn.commit()
    return {
        "attempt_id": attempt_id,
        "provider": provider,
        "masked_phone": masked_phone,
        "expires_in_seconds": int(ONE_TAP_TTL.total_seconds()),
        "provider_payload": provider_payload or {},
    }


def verify_one_tap_login(
    conn,
    *,
    attempt_id: str,
    phone: str,
    provider: str,
    operator_token: str,
    client_ip: str | None = None,
    device_id: str | None = None,
    client_type: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _utcnow(now)
    attempt = _row(
        conn,
        """
        SELECT *
        FROM auth_one_tap_attempts
        WHERE attempt_id = ?
        LIMIT 1
        """,
        (attempt_id,),
    )
    if not attempt:
        raise AuthDomainError(404, "one_tap_attempt_not_found", "一键登录尝试不存在")
    if attempt.get("status") != ONE_TAP_STATUS_CREATED:
        raise AuthDomainError(400, "one_tap_attempt_invalid", "一键登录尝试当前不可用")
    expires_at = attempt.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at <= ts:
        conn.execute(
            "UPDATE auth_one_tap_attempts SET status = ?, updated_at = ? WHERE attempt_id = ?",
            (ONE_TAP_STATUS_EXPIRED, ts, attempt_id),
        )
        conn.commit()
        raise AuthDomainError(400, "one_tap_attempt_expired", "一键登录已过期，请重新发起")
    user = _active_user_by_phone(conn, phone)
    is_new_user = user is None
    if user is None:
        user = _create_user_from_phone(conn, phone=phone, now=ts)
    else:
        conn.execute(
            """
            UPDATE user_accounts
            SET last_login_at = ?, last_login_ip = ?, last_login_device_id = ?, updated_at = ?
            WHERE user_id = ?
            """,
            (ts, client_ip, device_id, ts, user["user_id"]),
        )
    session = _create_session(
        conn,
        user_id=str(user["user_id"]),
        login_method=LOGIN_METHOD_ONE_TAP,
        client_type=client_type or str(attempt.get("client_type") or "") or None,
        client_ip=client_ip,
        device_id=device_id or str(attempt.get("device_id") or "") or None,
        now=ts,
    )
    conn.execute(
        """
        UPDATE auth_one_tap_attempts
        SET status = ?, verified_phone = ?, updated_at = ?
        WHERE attempt_id = ?
        """,
        (ONE_TAP_STATUS_VERIFIED, phone, ts, attempt_id),
    )
    _log_event(
        conn,
        user_id=str(user["user_id"]),
        phone=phone,
        event_type="one_tap_login",
        result="success",
        client_ip=client_ip,
        device_id=device_id,
        metadata={"provider": provider, "session_id": session["session_id"], "operator_token_present": bool(operator_token)},
        now=ts,
    )
    conn.commit()
    return {
        "user": {
            "user_id": str(user["user_id"]),
            "is_new_user": is_new_user,
            "account_status": user.get("account_status") or ACCOUNT_STATUS_ACTIVE,
            "onboarding_status": user.get("onboarding_status") or ONBOARDING_STATUS_NOT_STARTED,
            "phone_bound": True,
        },
        "session": session,
        "flow": {
            "scenario": "new" if is_new_user else "existing",
            "next_path": "/onboarding" if is_new_user else "",
        },
    }


def _session_row_by_hash(conn, *, field_name: str, token_hash: str) -> dict[str, Any] | None:
    row = row_to_dict(
        conn.execute(
            f"""
            SELECT *
            FROM auth_sessions
            WHERE {field_name} = ?
            LIMIT 1
            """,
            (token_hash,),
        ).fetchone()
    )
    return row


def get_session_by_access_token(conn, access_token: str, *, now: datetime | None = None) -> dict[str, Any] | None:
    ts = _utcnow(now)
    session = _session_row_by_hash(conn, field_name="access_token_hash", token_hash=_hash_value(access_token))
    if not session:
        return None
    if session.get("revoked_at") is not None:
        return None
    expires_at = session.get("access_expires_at")
    if isinstance(expires_at, datetime) and expires_at <= ts:
        return None
    user = _user_by_id(conn, str(session["user_id"]))
    if not user or user.get("account_status") != ACCOUNT_STATUS_ACTIVE:
        return None
    onboarding = _onboarding_state(conn, str(user["user_id"]))
    user["onboarding_status"] = (
        onboarding.get("onboarding_status")
        if onboarding
        else user.get("onboarding_status") or ONBOARDING_STATUS_NOT_STARTED
    )
    return {"session": session, "user": user}


def _profile_source_from_env() -> tuple[str, str]:
    for key in (
        "HER_PROFILE_SOURCE_DSN",
        "HER_DISCOVERY_PROFILE_SOURCE",
        "PERSONA_MEMORY_MYSQL_SOURCE",
        "PARTNER_SEARCH_MYSQL_SOURCE",
    ):
        raw = (os.environ.get(key) or "").strip()
        if not raw:
            continue
        source_dsn, table_name = resolve_profile_source(raw)
        if source_dsn and table_name:
            return source_dsn, table_name
    raise AuthDomainError(
        503,
        "profile_source_unconfigured",
        "服务端未配置用户画像库（HER_DISCOVERY_PROFILE_SOURCE 或 HER_PROFILE_SOURCE_DSN）",
    )


def _age_from_birthday(birthday: str | None) -> int | None:
    return age_from_birthday(birthday)


def _persona_memory_source() -> str:
    for key in (
        "PERSONA_MEMORY_MYSQL_SOURCE",
        "HER_DISCOVERY_PROFILE_SOURCE",
        "HER_PROFILE_SOURCE_DSN",
        "PARTNER_SEARCH_MYSQL_SOURCE",
    ):
        raw = (os.environ.get(key) or "").strip()
        if raw:
            return raw
    return ""


def _sync_onboarding_persona_memory(*, profile_id: int, patch: dict[str, Any]) -> None:
    if profile_id <= 0 or not patch:
        return
    source = _persona_memory_source()
    if not source:
        return
    try:
        apply_persona_patch(
            {
                "source": source,
                "user_key": str(profile_id),
                "source_type": "profile_form",
                "patch": patch,
                "sync_profile": False,
                "basis": "onboarding_submit",
                "conversation_ref": f"onboarding/{profile_id}",
            }
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "onboarding persona sync failed profile_id=%s: %s",
            profile_id,
            exc,
            exc_info=True,
        )
        return


def _map_onboarding_to_profile_fields(
    basic_info: dict[str, Any] | None,
    preference: dict[str, Any] | None,
) -> dict[str, Any]:
    fields = build_onboarding_profile_fields(basic_info, preference)
    pref = dict(preference or {})
    tags = pref.get("tags")
    tag_text = ", ".join(str(item) for item in tags) if isinstance(tags, list) else str(tags or "")
    if tag_text:
        fields["values"] = tag_text
    return fields


def _linked_profile_id(onboarding: dict[str, Any] | None) -> int | None:
    if not onboarding:
        return None
    basic = onboarding.get("basic_info") or {}
    raw = basic.get("profile_id")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def get_onboarding_profile(conn, user_id: str) -> dict[str, Any]:
    onboarding = _onboarding_state(conn, user_id)
    if not onboarding:
        raise AuthDomainError(404, "onboarding_not_found", "未找到新用户资料记录")
    profile_id = _linked_profile_id(onboarding)
    return {
        "onboarding_status": onboarding.get("onboarding_status") or ONBOARDING_STATUS_NOT_STARTED,
        "current_step": onboarding.get("current_step"),
        "basic_info": onboarding.get("basic_info") or {},
        "preference": onboarding.get("preference") or {},
        "profile_id": profile_id,
        "requester_id": profile_id,
        "completed_at": onboarding.get("completed_at"),
    }


def find_user_id_by_profile_id(conn, profile_id: int) -> str | None:
    row = row_to_dict(
        conn.execute(
            """
            SELECT user_id
            FROM user_onboarding_profiles
            WHERE JSON_EXTRACT(basic_info_json, '$.profile_id') = ?
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            (int(profile_id),),
        ).fetchone()
    )
    user_id = str((row or {}).get("user_id") or "").strip()
    return user_id or None


def submit_onboarding_profile(
    conn,
    user_id: str,
    *,
    basic_info: dict[str, Any] | None = None,
    preference: dict[str, Any] | None = None,
    mark_completed: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _utcnow(now)
    user = _user_by_id(conn, user_id)
    if not user or user.get("account_status") != ACCOUNT_STATUS_ACTIVE:
        raise AuthDomainError(401, "unauthorized", "登录状态已失效，请重新登录")

    onboarding = _onboarding_state(conn, user_id)
    if not onboarding:
        raise AuthDomainError(404, "onboarding_not_found", "未找到新用户资料记录")

    merged_basic = dict(onboarding.get("basic_info") or {})
    merged_pref = dict(onboarding.get("preference") or {})
    if basic_info:
        merged_basic.update(dict(basic_info))
    if preference:
        merged_pref.update(dict(preference))

    source_dsn, source_table = _profile_source_from_env()
    profile_fields = _map_onboarding_to_profile_fields(merged_basic, merged_pref)
    if not profile_fields.get("name"):
        raise AuthDomainError(400, "name_required", "请填写姓名后再提交")

    existing_profile_id = _linked_profile_id({"basic_info": merged_basic, "preference": merged_pref})
    profile_id, write_mode = upsert_profile_for_onboarding(
        source_dsn=source_dsn,
        source_table_name=source_table,
        profile_id=existing_profile_id,
        fields=profile_fields,
    )
    merged_basic["profile_id"] = profile_id
    persona_patch = build_onboarding_persona_patch(merged_basic, merged_pref)
    _sync_onboarding_persona_memory(profile_id=profile_id, patch=persona_patch)

    next_status = (
        ONBOARDING_STATUS_COMPLETED
        if mark_completed
        else (onboarding.get("onboarding_status") or ONBOARDING_STATUS_NOT_STARTED)
    )
    completed_at = ts if mark_completed else onboarding.get("completed_at")

    conn.execute(
        """
        UPDATE user_onboarding_profiles
        SET onboarding_status = ?, current_step = ?, basic_info_json = ?, preference_json = ?,
            completed_at = ?, updated_at = ?
        WHERE user_id = ?
        """,
        (
            next_status,
            "completed" if mark_completed else (onboarding.get("current_step") or "basic_info"),
            json_dumps(merged_basic),
            json_dumps(merged_pref),
            completed_at,
            ts,
            user_id,
        ),
    )
    conn.execute(
        """
        UPDATE user_accounts
        SET onboarding_status = ?, updated_at = ?
        WHERE user_id = ?
        """,
        (next_status, ts, user_id),
    )
    _log_event(
        conn,
        user_id=user_id,
        phone=user.get("primary_phone"),
        event_type="onboarding_submit",
        result="success",
        metadata={"profile_id": profile_id, "write_mode": write_mode},
        now=ts,
    )
    conn.commit()

    return {
        "ok": True,
        "profile_id": profile_id,
        "requester_id": profile_id,
        "write_mode": write_mode,
        "user": {
            "user_id": str(user_id),
            "onboarding_status": next_status,
        },
        "onboarding": {
            "onboarding_status": next_status,
            "basic_info": merged_basic,
            "preference": merged_pref,
            "completed_at": completed_at,
        },
    }


def get_current_auth_payload(conn, user_id: str, access_token: str, *, now: datetime | None = None) -> dict[str, Any]:
    resolved = get_session_by_access_token(conn, access_token, now=now)
    if not resolved or str((resolved["user"] or {}).get("user_id") or "") != str(user_id):
        raise AuthDomainError(401, "unauthorized", "登录状态已失效，请重新登录")
    session = resolved["session"]
    user = resolved["user"]
    onboarding = _onboarding_state(conn, str(user["user_id"]))
    profile_id = _linked_profile_id(onboarding)
    payload: dict[str, Any] = {
        "user": {
            "user_id": str(user["user_id"]),
            "phone": user.get("primary_phone"),
            "account_status": user.get("account_status"),
            "onboarding_status": user.get("onboarding_status") or ONBOARDING_STATUS_NOT_STARTED,
        },
        "session": {
            "session_id": str(session["session_id"]),
            "login_method": session.get("login_method"),
            "client_type": session.get("client_type"),
            "device_id": session.get("device_id"),
            "access_expires_at": session.get("access_expires_at"),
            "refresh_expires_at": session.get("refresh_expires_at"),
        },
    }
    if profile_id is not None:
        payload["user"]["profile_id"] = profile_id
        payload["user"]["requester_id"] = profile_id
    if onboarding:
        payload["onboarding"] = {
            "onboarding_status": onboarding.get("onboarding_status"),
            "basic_info": onboarding.get("basic_info") or {},
            "preference": onboarding.get("preference") or {},
            "profile_id": profile_id,
        }
    return payload


def revoke_session_by_access_token(
    conn,
    access_token: str,
    *,
    reason: str = "logout",
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _utcnow(now)
    session = _session_row_by_hash(conn, field_name="access_token_hash", token_hash=_hash_value(access_token))
    if not session:
        return {"ok": True, "revoked": False}
    if session.get("revoked_at") is None:
        conn.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = ?, revoke_reason = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (ts, reason, ts, session["session_id"]),
        )
        _log_event(
            conn,
            user_id=str(session.get("user_id") or "") or None,
            phone=None,
            event_type="logout",
            result="success",
            reason_code=reason,
            metadata={"session_id": session["session_id"]},
            now=ts,
        )
        conn.commit()
    return {"ok": True, "revoked": True}


def refresh_session(
    conn,
    refresh_token: str,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    ts = _utcnow(now)
    session = _session_row_by_hash(conn, field_name="refresh_token_hash", token_hash=_hash_value(refresh_token))
    if not session or session.get("revoked_at") is not None:
        raise AuthDomainError(401, "invalid_refresh_token", "刷新登录状态失败，请重新登录")
    refresh_expires_at = session.get("refresh_expires_at")
    if isinstance(refresh_expires_at, datetime) and refresh_expires_at <= ts:
        raise AuthDomainError(401, "refresh_token_expired", "登录已过期，请重新登录")
    user = _user_by_id(conn, str(session["user_id"]))
    if not user or user.get("account_status") != ACCOUNT_STATUS_ACTIVE:
        raise AuthDomainError(401, "unauthorized", "登录状态已失效，请重新登录")
    access_token = _raw_token("atk")
    next_refresh_token = _raw_token("rtk")
    access_expires_at = ts + ACCESS_TOKEN_TTL
    next_refresh_expires_at = ts + REFRESH_TOKEN_TTL
    conn.execute(
        """
        UPDATE auth_sessions
        SET access_token_hash = ?, refresh_token_hash = ?, access_expires_at = ?,
            refresh_expires_at = ?, last_seen_at = ?, updated_at = ?
        WHERE session_id = ?
        """,
        (
          _hash_value(access_token),
          _hash_value(next_refresh_token),
          access_expires_at,
          next_refresh_expires_at,
          ts,
          ts,
          session["session_id"],
        ),
    )
    _log_event(
        conn,
        user_id=str(user["user_id"]),
        phone=user.get("primary_phone"),
        event_type="token_refresh",
        result="success",
        metadata={"session_id": session["session_id"]},
        now=ts,
    )
    conn.commit()
    return {
        "user": {
            "user_id": str(user["user_id"]),
            "is_new_user": False,
            "account_status": user.get("account_status"),
            "onboarding_status": user.get("onboarding_status") or ONBOARDING_STATUS_NOT_STARTED,
        },
        "session": {
            "session_id": str(session["session_id"]),
            "access_token": access_token,
            "refresh_token": next_refresh_token,
            "token_type": "Bearer",
            "expires_in_seconds": int(ACCESS_TOKEN_TTL.total_seconds()),
            "refresh_expires_in_seconds": int(REFRESH_TOKEN_TTL.total_seconds()),
            "access_expires_at": access_expires_at,
            "refresh_expires_at": next_refresh_expires_at,
        },
        "flow": {"scenario": "existing", "next_path": ""},
    }


__all__ = [
    "ACCESS_TOKEN_TTL",
    "AuthDomainError",
    "LOGIN_METHOD_SMS",
    "LOGIN_METHOD_WECHAT",
    "LOGIN_METHOD_ONE_TAP",
    "ONBOARDING_STATUS_COMPLETED",
    "ONBOARDING_STATUS_NOT_STARTED",
    "OTP_SCENE_BIND_PHONE",
    "OTP_RESEND_COOLDOWN",
    "OTP_SCENE_LOGIN",
    "OTP_TTL",
    "bind_phone_with_sms",
    "classify_phone_scenario",
    "create_one_tap_attempt",
    "get_current_auth_payload",
    "get_onboarding_profile",
    "get_session_by_access_token",
    "issue_sms_code",
    "login_with_wechat_profile",
    "refresh_session",
    "revoke_session_by_access_token",
    "submit_onboarding_profile",
    "verify_one_tap_login",
    "verify_sms_code",
]
