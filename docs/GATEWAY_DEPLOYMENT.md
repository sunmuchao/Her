# Gateway deployment surfaces (§13.4)

The partner HTTP gateway supports logical **route surfaces** for physical or logical split deployments without forking code.

## Environment variables

| Variable | Values | Default | Purpose |
| --- | --- | --- | --- |
| `PARTNER_GATEWAY_SURFACE` | `all`, `public`, `ops`, `internal` | `all` | Which REST routes are mounted |
| `PARTNER_GATEWAY_ENABLE_JSONRPC` | `0`, `1` | `1` | Enable `POST /jsonrpc` (internal/scripts) |

## Recommended production layout

```text
her-gateway-public   SURFACE=public   ENABLE_JSONRPC=0   → her-app users
her-gateway-ops      SURFACE=ops      ENABLE_JSONRPC=0   → /v1/ops/* workbench
her-gateway-internal SURFACE=internal ENABLE_JSONRPC=1   → schedulers / scripts
```

Local development keeps `SURFACE=all`.

## Route faces

| Face | REST | JSON-RPC |
| --- | --- | --- |
| `public` | `/v1/*` except `/v1/ops/*` | disabled |
| `ops` | `/v1/ops/*`, `/health` | disabled |
| `internal` | `/health` only | enabled |
| `all` | everything | enabled (if `ENABLE_JSONRPC=1`) |

Public login routes (`/v1/auth/*` without session) are always available before surface checks.

## BFF aggregate reads

| Endpoint | Purpose |
| --- | --- |
| `GET /v1/candidates/{id}` | profile + trust + optional discovery detail + explain |
| `GET /v1/profiles/{id}/trust` | TrustSummary |
| `GET /v1/profile/me` | profile_facts |
| `GET /v1/persona/collected` | collected_statements |
| `GET /v1/ops/workbench/summary` | ops dashboard |

## Audit

```bash
python scripts/audit_gateway_routes.py
```

Must pass before merging gateway write-path changes.
