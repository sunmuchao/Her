"""Account, OTP, and session persistence for user auth."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from .storage import inflate_json_columns, json_dumps, row_to_dict

OTP_SCENE_LOGIN = "login"
OTP_STATUS_ISSUED = "issued"
OTP_STATUS_VERIFIED = "verified"
OTP_STATUS_EXPIRED = "expired"
OTP_STATUS_BLOCKED = "blocked"

ACCOUNT_STATUS_ACTIVE = "active"
ONBOARDING_STATUS_NOT_STARTED = "not_started"
ONBOARDING_STATUS_COMPLETED = "completed"

LOGIN_METHOD_SMS = "sms"
ROLE_END_USER = "end_user"

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
    if challenge_id:
        challenge = _row(
            conn,
            """
            SELECT *
            FROM auth_otp_challenges
            WHERE challenge_id = ? AND phone = ?
            LIMIT 1
            """,
            (challenge_id, phone),
        )
    else:
        challenge = _row(
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
    if not challenge:
        raise AuthDomainError(400, "code_not_requested", "请先获取验证码")
    if challenge.get("status") != OTP_STATUS_ISSUED:
        if challenge.get("status") == OTP_STATUS_EXPIRED:
            raise AuthDomainError(400, "code_expired", "验证码已过期，请重新获取")
        raise AuthDomainError(400, "code_not_available", "验证码当前不可用，请重新获取")
    expires_at = challenge.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at <= ts:
        conn.execute(
            "UPDATE auth_otp_challenges SET status = ?, updated_at = ? WHERE challenge_id = ?",
            (OTP_STATUS_EXPIRED, ts, challenge["challenge_id"]),
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
            (attempts, next_status, ts, challenge["challenge_id"]),
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
            now=ts,
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
        (OTP_STATUS_VERIFIED, ts, challenge["challenge_id"]),
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


def get_current_auth_payload(conn, user_id: str, access_token: str, *, now: datetime | None = None) -> dict[str, Any]:
    resolved = get_session_by_access_token(conn, access_token, now=now)
    if not resolved or str((resolved["user"] or {}).get("user_id") or "") != str(user_id):
        raise AuthDomainError(401, "unauthorized", "登录状态已失效，请重新登录")
    session = resolved["session"]
    user = resolved["user"]
    return {
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
    "ONBOARDING_STATUS_COMPLETED",
    "ONBOARDING_STATUS_NOT_STARTED",
    "OTP_RESEND_COOLDOWN",
    "OTP_SCENE_LOGIN",
    "OTP_TTL",
    "classify_phone_scenario",
    "get_current_auth_payload",
    "get_session_by_access_token",
    "issue_sms_code",
    "refresh_session",
    "revoke_session_by_access_token",
    "verify_sms_code",
]
