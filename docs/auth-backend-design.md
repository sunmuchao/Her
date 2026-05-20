# Auth Backend Design

## Goal

Build a production-shaped account system for the Her app while landing the smallest end-to-end usable slice first.

Phase 1 is the implementation target in this repo:

- phone SMS login/register merge
- persistent OTP challenges
- persistent access/refresh sessions
- `GET /v1/auth/me`
- `POST /v1/auth/logout`
- dynamic bearer-token auth backed by session storage

Later phases extend this foundation with:

- carrier one-tap login
- WeChat login and phone binding
- password reset and phone change
- richer audit/risk controls

## Current State

Before this change the gateway only had:

- `POST /v1/auth/sms/send-code`
- `POST /v1/auth/sms/verify-code`

But those routes were demo-only:

- OTP records lived in memory
- “existing/new user” was guessed from the phone number
- no user table
- no session token
- no `/me`
- no `/logout`

## Product Rules

The account system follows these product rules:

1. Login and registration are merged.
2. A verified phone number logs an existing user in, or creates a new user automatically.
3. The backend is the source of truth for “new user” vs “existing user”.
4. Every successful login issues an access token and refresh token.
5. API requests authenticate with bearer access tokens.

## Data Model

Phase 1 lands these MySQL tables in the chat database:

### `user_accounts`

One row per application account.

Important fields:

- `user_id`
- `account_status`
- `primary_phone`
- `phone_verified_at`
- `register_source`
- `onboarding_status`
- `created_at`
- `updated_at`

### `user_account_identities`

Identity bindings for an account.

Phase 1 uses:

- `identity_type = phone`
- `identity_value = 13800138000`

Later phases will add:

- `wechat_openid`
- `wechat_unionid`
- `password`

### `auth_otp_challenges`

Persistent SMS verification challenges.

Important fields:

- `challenge_id`
- `phone`
- `scene`
- `code_hash`
- `code_salt`
- `status`
- `expires_at`
- `resend_available_at`
- `verify_attempt_count`
- `max_verify_attempts`

### `auth_sessions`

Login sessions and tokens.

Important fields:

- `session_id`
- `user_id`
- `access_token_hash`
- `refresh_token_hash`
- `login_method`
- `access_expires_at`
- `refresh_expires_at`
- `revoked_at`

### `auth_login_events`

Operational and risk audit trail.

Important fields:

- `event_id`
- `user_id`
- `phone`
- `event_type`
- `result`
- `reason_code`
- `client_ip`
- `device_id`
- `metadata_json`

### `user_onboarding_profiles`

Tracks whether a user still needs first-time onboarding.

## API Design

### Public auth routes

#### `POST /v1/auth/sms/send-code`

Request:

```json
{
  "phone": "13800138000",
  "scene": "login",
  "device_id": "ios-device-1",
  "client_type": "ios"
}
```

Response:

```json
{
  "challenge_id": "otp-xxx",
  "delivery": {
    "channel": "sms",
    "masked_phone": "138****8000",
    "expires_in_seconds": 300,
    "resend_in_seconds": 60,
    "provider": "aliyun"
  },
  "flow": {
    "scenario": "existing",
    "next_path": ""
  }
}
```

#### `POST /v1/auth/sms/verify-code`

Request:

```json
{
  "phone": "13800138000",
  "code": "123456",
  "challenge_id": "otp-xxx",
  "device_id": "ios-device-1",
  "client_type": "ios"
}
```

Response:

```json
{
  "verified": true,
  "user": {
    "user_id": "usr_xxx",
    "is_new_user": true,
    "account_status": "active",
    "onboarding_status": "not_started"
  },
  "session": {
    "session_id": "sess_xxx",
    "access_token": "raw-access-token",
    "refresh_token": "raw-refresh-token",
    "token_type": "Bearer",
    "expires_in_seconds": 7200,
    "refresh_expires_in_seconds": 2592000
  },
  "flow": {
    "scenario": "new",
    "next_path": "/onboarding"
  }
}
```

#### `POST /v1/auth/token/refresh`

Uses refresh token rotation and returns a new access/refresh pair.

#### `POST /v1/auth/wechat/login`

Request:

```json
{
  "code": "wechat-oauth-code",
  "device_id": "ios-device-1",
  "client_type": "ios"
}
```

Response:

```json
{
  "user": {
    "user_id": "usr_xxx",
    "is_new_user": true,
    "account_status": "active",
    "onboarding_status": "not_started",
    "phone_bound": false
  },
  "session": {
    "session_id": "sess_xxx",
    "access_token": "raw-access-token",
    "refresh_token": "raw-refresh-token",
    "token_type": "Bearer",
    "expires_in_seconds": 7200,
    "refresh_expires_in_seconds": 2592000
  },
  "flow": {
    "scenario": "new",
    "next_path": "/bind-phone"
  },
  "wechat_profile": {
    "openid": "wx-openid-1",
    "unionid": "wx-union-1",
    "nickname": "微信昵称",
    "avatar_url": "https://..."
  }
}
```

#### `POST /v1/auth/one-tap/create`

Request:

```json
{
  "device_id": "ios-device-1",
  "client_type": "ios"
}
```

Response:

```json
{
  "attempt_id": "otl-xxx",
  "provider": "carrier",
  "masked_phone": "138****8000",
  "expires_in_seconds": 600,
  "provider_payload": {}
}
```

#### `POST /v1/auth/one-tap/verify`

Request:

```json
{
  "attempt_id": "otl-xxx",
  "operator_token": "carrier-token",
  "device_id": "ios-device-1",
  "client_type": "ios"
}
```

Response shape is the same as successful phone login.

### Authenticated routes

#### `GET /v1/auth/me`

Returns the current user and active session summary.

#### `POST /v1/auth/logout`

Revokes the current access session.

#### `POST /v1/auth/wechat/bind-phone`

Requires bearer access token.

Request:

```json
{
  "phone": "13800138000",
  "code": "123456",
  "challenge_id": "otp-xxx",
  "device_id": "ios-device-1"
}
```

Response:

```json
{
  "ok": true,
  "user": {
    "user_id": "usr_xxx",
    "phone": "13800138000",
    "phone_bound": true,
    "account_status": "active",
    "onboarding_status": "not_started"
  }
}
```

## Authentication Model

The gateway now accepts bearer tokens from two sources:

1. static/operator tokens from existing config
2. dynamic end-user access tokens stored in `auth_sessions`

When a bearer token matches a live auth session:

- actor id = `user_id`
- roles = `end_user`
- auth source = `auth_session`

This keeps the new account system compatible with existing gateway access control.

## Phase Plan

### Phase 1

Implemented in this repo:

- real user/account rows
- OTP persistence
- login/register merge
- access/refresh sessions
- `/me`
- `/logout`
- `/token/refresh`

### Phase 2

- WeChat login
- carrier one-tap login
- WeChat phone binding
- device/session management

Current landing status:

- gateway routes are implemented for WeChat login, one-tap create/verify, and WeChat bind-phone
- domain persistence is implemented in `chat_system.auth_accounts`
- local development can run with stub providers before real vendor integration

### Phase 3

Planned next:

- password set/reset
- phone change
- richer login risk scoring
- customer support recovery flows

## Operational Notes

- OTP codes are hashed before storage.
- access/refresh tokens are stored as hashes only.
- the chat MySQL schema now owns auth tables because the gateway already uses that database and migration path.
- a small in-memory fallback still exists in the OTP service only for tests and non-persistent development scenarios.
- `auth_one_tap_attempts` persists carrier one-tap attempts and expiry state.
- local WeChat stub mode uses `HER_AUTH_WECHAT_STUB_CODES_JSON`.
- local one-tap stub mode uses `HER_AUTH_ONE_TAP_STUB_PHONE` and `HER_AUTH_ONE_TAP_STUB_TOKEN`.
- real WeChat open-platform mode uses `HER_WECHAT_APP_ID` and `HER_WECHAT_APP_SECRET`.
