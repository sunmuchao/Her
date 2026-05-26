#!/usr/bin/env bash
# Full-stack Playwright E2E for CI: MySQL bootstrap → gateway → Next.js → tests (mock flags OFF).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
APP_DIR="$ROOT_DIR/frontend/her-app"
GATEWAY_DIR="$ROOT_DIR/external-systems/partner-http-gateway"
LOG_DIR="${HER_E2E_LOG_DIR:-/tmp/her-e2e-ci}"
mkdir -p "$LOG_DIR"

_resolve_playwright_browsers_path() {
  local candidate="${1:-}"
  if [ -n "$candidate" ]; then
    for marker in "$candidate"/chromium-*/INSTALLATION_COMPLETE; do
      if [ -f "$marker" ]; then
        echo "$candidate"
        return 0
      fi
    done
  fi
  if [ "$(uname -s)" = "Linux" ]; then
    echo "${HOME}/.cache/ms-playwright"
  else
    echo "${HOME}/Library/Caches/ms-playwright"
  fi
}
export PLAYWRIGHT_BROWSERS_PATH="$(_resolve_playwright_browsers_path "${PLAYWRIGHT_BROWSERS_PATH:-}")"

export NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=false
export NEXT_PUBLIC_ENABLE_DEMO_NAV=true
export NEXT_PUBLIC_USE_AUTH_STUB=false
export NEXT_PUBLIC_E2E_GATEWAY_AUTH=true
export NODE_ENV=production

echo "[e2e-ci] bootstrapping MySQL schemas and seed data..."
python3 "$ROOT_DIR/scripts/ci_bootstrap_frontend_e2e.py"

if command -v lsof >/dev/null 2>&1; then
  lsof -iTCP:8765 -sTCP:LISTEN -n -P 2>/dev/null | awk 'NR>1 {print $2}' | xargs -I{} kill {} 2>/dev/null || true
  lsof -iTCP:3000 -sTCP:LISTEN -n -P 2>/dev/null | awk 'NR>1 {print $2}' | xargs -I{} kill {} 2>/dev/null || true
fi

stamp="$(date +%s)"
suffix="$(printf '%08d' "$((stamp % 100000000))")"
bind_phone="${HER_E2E_BIND_PHONE:-139${suffix:0:8}}"
openid="wx-openid-e2e-$stamp"
unionid="wx-union-e2e-$stamp"

# shellcheck source=/dev/null
source "$APP_DIR/.env.local" 2>/dev/null || true

echo "[e2e-ci] starting gateway (bind phone: $bind_phone)..."
cd "$GATEWAY_DIR"
HER_SMS_PROVIDER=shell \
HER_SMS_SHELL_COMMAND='sh -c "printf %s \"$HER_SMS_CODE\" > /tmp/her_sms_code.txt"' \
HER_AUTH_WECHAT_PROVIDER=stub \
HER_AUTH_WECHAT_STUB_CODES_JSON="{\"wx-code-1\":{\"openid\":\"$openid\",\"unionid\":\"$unionid\",\"nickname\":\"E2E用户\",\"avatar_url\":\"https://example.com/avatar-e2e.jpg\"}}" \
HER_AUTH_ONE_TAP_PROVIDER=stub \
HER_AUTH_ONE_TAP_STUB_PHONE=13800138000 \
HER_AUTH_ONE_TAP_STUB_TOKEN=carrier-token-1 \
PARTNER_CHAT_DB="${PARTNER_CHAT_DB:-mysql://root@127.0.0.1:3307/her_chat}" \
PARTNER_RECOMMENDATION_DB="${PARTNER_RECOMMENDATION_DB:-mysql://root@127.0.0.1:3307/her_recommendation}" \
PARTNER_MATCHMAKING_DB="${PARTNER_MATCHMAKING_DB:-mysql://root@127.0.0.1:3307/her_matchmaking}" \
PARTNER_DISCOVERY_DB="${PARTNER_DISCOVERY_DB:-mysql://root@127.0.0.1:3307/her_discovery}" \
HER_RELATION_LEDGER_DB="${HER_RELATION_LEDGER_DB:-mysql://root@127.0.0.1:3307/her_relationship_ledger}" \
HER_PROFILE_SOURCE_DSN="${HER_PROFILE_SOURCE_DSN:-mysql://root@127.0.0.1:3307/her?table=profiles&photos_table=profile_photos}" \
HER_PROXY_INTRO_STORAGE=matchmaking \
python3 -m gateway --host 127.0.0.1 --port 8765 >"$LOG_DIR/gateway.log" 2>&1 &
gateway_pid=$!

next_pid=""
cleanup() {
  if [[ -n "$next_pid" ]]; then kill "$next_pid" 2>/dev/null || true; fi
  kill "$gateway_pid" 2>/dev/null || true
}
trap cleanup EXIT

ready=0
for _ in $(seq 1 30); do
  if curl -fsS -X POST http://127.0.0.1:8765/v1/auth/one-tap/create \
    -H 'Content-Type: application/json' \
    --data '{"device_id":"ios-1","client_type":"ios"}' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "[e2e-ci] gateway failed readiness; see $LOG_DIR/gateway.log"
  tail -n 40 "$LOG_DIR/gateway.log" || true
  exit 1
fi

echo "[e2e-ci] building and starting Next.js..."
cd "$APP_DIR"
pnpm run build >"$LOG_DIR/next-build.log" 2>&1
pnpm exec next start --hostname 127.0.0.1 --port 3000 >"$LOG_DIR/next.log" 2>&1 &
next_pid=$!

for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:3000/splash >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! curl -fsS http://127.0.0.1:3000/splash >/dev/null 2>&1; then
  echo "[e2e-ci] frontend failed readiness; see $LOG_DIR/next.log"
  tail -n 40 "$LOG_DIR/next.log" || true
  exit 1
fi

echo "[e2e-ci] ensuring Playwright chromium..."
browsers_root="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/Library/Caches/ms-playwright}"
if [ "$(uname -s)" = "Linux" ]; then
  browsers_root="${PLAYWRIGHT_BROWSERS_PATH:-$HOME/.cache/ms-playwright}"
fi
chromium_ready=0
for marker in "${browsers_root}"/chromium-*/INSTALLATION_COMPLETE; do
  if [ -f "$marker" ]; then
    chromium_ready=1
    break
  fi
done
if [ "$chromium_ready" -eq 1 ]; then
  echo "[e2e-ci] chromium already present under ${browsers_root}, skipping download"
elif [ "${CI:-}" = "true" ]; then
  pnpm exec playwright install --with-deps chromium
else
  pnpm exec playwright install chromium
fi

echo "[e2e-ci] running Playwright (MOCK_FALLBACK=false)..."
HER_E2E_BIND_PHONE="$bind_phone" \
  pnpm exec playwright test tests/e2e/her-flow.spec.ts --reporter=line

echo "[e2e-ci] ok"
