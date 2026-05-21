#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
APP_DIR="$ROOT_DIR/frontend/her-app"
GATEWAY_DIR="$ROOT_DIR/external-systems/partner-http-gateway"

if ! curl -fsS http://127.0.0.1:3000 >/dev/null 2>&1; then
  echo "frontend dev server is not running on http://127.0.0.1:3000"
  echo "start it first: cd $APP_DIR && pnpm dev --hostname 127.0.0.1 --port 3000"
  exit 1
fi

if command -v lsof >/dev/null 2>&1; then
  lsof -iTCP:8765 -sTCP:LISTEN -n -P | awk 'NR>1 {print $2}' | xargs -I{} kill {} 2>/dev/null || true
fi

stamp="$(date +%s)"
suffix="$(printf '%08d' "$((stamp % 100000000))")"
bind_phone="${HER_E2E_BIND_PHONE:-139${suffix:0:8}}"
openid="wx-openid-e2e-$stamp"
unionid="wx-union-e2e-$stamp"
nickname="测试微信用户E2E"
avatar_url="https://example.com/avatar-e2e.jpg"

echo "using bind phone: $bind_phone"
echo "using wechat openid: $openid"

cd "$GATEWAY_DIR"
HER_SMS_PROVIDER=shell \
HER_SMS_SHELL_COMMAND='sh -c "printf %s \"$HER_SMS_CODE\" > /tmp/her_sms_code.txt"' \
HER_AUTH_WECHAT_PROVIDER=stub \
HER_AUTH_WECHAT_STUB_CODES_JSON="{\"wx-code-1\":{\"openid\":\"$openid\",\"unionid\":\"$unionid\",\"nickname\":\"$nickname\",\"avatar_url\":\"$avatar_url\"}}" \
HER_AUTH_ONE_TAP_PROVIDER=stub \
HER_AUTH_ONE_TAP_STUB_PHONE=13800138000 \
HER_AUTH_ONE_TAP_STUB_TOKEN=carrier-token-1 \
python3 -m gateway --host 127.0.0.1 --port 8765 >/tmp/her-gateway-e2e.log 2>&1 &
gateway_pid=$!

cleanup() {
  kill "$gateway_pid" 2>/dev/null || true
}
trap cleanup EXIT

sleep 2

cd "$APP_DIR"
HER_E2E_BIND_PHONE="$bind_phone" pnpm exec playwright test tests/e2e/her-flow.spec.ts --reporter=line
