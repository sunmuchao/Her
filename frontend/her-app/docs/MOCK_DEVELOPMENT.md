# Development mock policy (§13.2)

Local development may use mock fallbacks and auth stubs so UI work does not require a full Gateway + MySQL stack. **Production and CI E2E never allow silent mocks.**

## Three public flags

| Variable | Dev purpose | Production |
|----------|-------------|------------|
| `NEXT_PUBLIC_ALLOW_MOCK_FALLBACK` | When API fails or user is logged out, show fixtures + yellow `DemoDataBanner` | Must be `false` (hard-disabled in `lib/env.ts` when `NODE_ENV=production`) |
| `NEXT_PUBLIC_USE_AUTH_STUB` | Skip real SMS/WeChat; use local stub tokens | Must be `false` |
| `NEXT_PUBLIC_ENABLE_DEMO_NAV` | Show demo nav shortcuts (e.g. jump to relationships) | Must be `false` (demo nav is always on in `NODE_ENV=development`) |

See `.env.example` for copy-paste defaults.

## Yellow banner rule

Any page that renders fixture data while mock is allowed **must** show `DemoDataBanner`:

> 当前展示的是演示数据（接口不可用或开发 Mock 已开启）

Pages wired today: discover, profile, relationships, chat, candidate detail, collected preferences.

## When to use mocks

- **UI-only work** — set `NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=true` in `.env.local`, run `pnpm dev`.
- **Gateway integration** — use `pnpm e2e:her:stub` (frontend on `:3000` + gateway stub on `:8765`).
- **Full stack / CI parity** — `pnpm e2e:her:ci` (MySQL bootstrap → gateway → production build → Playwright).

## Production gates

1. `lib/env.ts` — `isMockFallbackAllowed()`, `isAuthStubEnabled()` return `false` in production regardless of env vars.
2. CI job `production-build` — builds with all three flags `false`.
3. CI job `e2e` — runs Playwright with `NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=false` against real Gateway + MySQL.
4. CI job `mock-fallback-regression` — proves banner appears when mock is intentionally enabled (dev path only).

## Fixtures location

- `lib/fixtures/demo-profiles.ts`
- `lib/fixtures/demo-candidates.ts`

Do not import these from production-only code paths without `isMockFallbackAllowed()` guard.
