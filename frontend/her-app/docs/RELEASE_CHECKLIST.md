# Her App Release Checklist (§13.2.6)

Use this checklist before production releases to confirm frontend-backend reality landing.

## Stage 1 — Stop silent mocks

- [ ] Discover page shows no fake candidates when API returns empty (production build)
- [ ] Profile verification progress matches trust hub; no hardcoded verification items
- [ ] Trust center shows empty state when API returns no verification items
- [ ] Every page that still allows mock fallback displays `DemoDataBanner` when mock is active

## Stage 2 — Unified read sources

- [ ] Profile, trust center, and candidate detail use the same trust hub mapper for verification status
- [ ] Chat, inbox, and relationships do not render hardcoded sample conversations or relationships on first paint
- [ ] Relationships page resolves `case_id` from session / auth / ledger without requiring manual env config when logged in

## Stage 3 — Capture loop

- [ ] Live video verification submits user-recorded video (`video_base64`), not stub payload (except test env)
- [ ] Field verification accepts real file upload and reflects pending/verified changes in trust hub

## Manual spot checks (pre-release)

1. **Login → Discover**: run a discovery turn; confirm candidates and preferences trace to API or show explicit empty state.
2. **Candidate detail**: open a recommendation card; confirm fields come from discovery/trust APIs or mock banner is visible in dev only.
3. **Relationships**: open relationships tab; confirm timeline/conversations load from ledger + chat, pending actions from trust hub.

## Production env gates (CI)

Ensure these are `false` in production builds:

- `NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=false`
- `NEXT_PUBLIC_ENABLE_DEMO_NAV=false`
- `NEXT_PUBLIC_USE_AUTH_STUB=false`

CI jobs (`.github/workflows/frontend-her-app.yml`):

- `production-build` — asserts mock flags off at build time
- `e2e` — full-stack Playwright with real Gateway + MySQL (`pnpm e2e:her:ci`)
- `mock-fallback-regression` — dev-only banner when mock is intentionally enabled

See also `docs/MOCK_DEVELOPMENT.md`.

## Acceptance statement

> Every status, number, candidate, and verification progress shown in production must be traceable to a Gateway API or read model. If it cannot be traced, it is still an §13.2 gap.
