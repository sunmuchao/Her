# Gateway cross-domain write checklist (§13.1.3)

New or modified Gateway handlers that perform **writes** must pass this checklist in PR review:

1. **Single owner** — The handler calls at most one domain write API (recommendation OR matchmaking OR chat OR persona sync). Aggregated **read** endpoints are exempt.
2. **No long orchestration** — Multi-step flows (collect → search → deliver) belong in the owning system service, not in `gateway/app.py` handlers.
3. **Support conclusions only** — Handlers must not parse moderation table shapes; use `GateDecision` / `TrustSummary` from `match_domain`.
4. **Principal once** — End-user identity is resolved via `IdentityResolver`; do not re-parse tokens in route handlers.
5. **Ops overrides** — Manual actions go through `POST /v1/ops/overrides` and target owner APIs.

Run `python scripts/audit_gateway_routes.py` in CI or before merge; it must exit 0.

Examples of allowed patterns:

- `GET /v1/profiles/{id}/trust` — BFF read aggregation
- `POST /v1/search/profiles` — search with external moderation gate via `search_profiles_with_visibility_gate`

Examples to reject:

- Handler that updates persona, runs search, and creates recommendation in one request
- Handler that writes `risk_flags_json` semantics directly onto recommendation rows
