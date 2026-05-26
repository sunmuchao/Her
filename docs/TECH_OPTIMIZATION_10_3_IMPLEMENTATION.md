# §10.3 技术优化建议 — 完整落地方案

> 状态：**已全部落地**（2026-05-26，含 cutover 自动化与搜人快照表）  
> 对应 `SYSTEM_DOC.md` §10.3 八项建议；本文档为执行清单与运维说明。

## 总览

| 领域 | 目标 | 落地物 |
|------|------|--------|
| 架构 | 生产三分面 Gateway；proxy intro 仅 matchmaking | `docker-compose.yml`、`docs/GATEWAY_DEPLOYMENT.md`、`match_domain/proxy_intro_storage.py` |
| 数据 | 全环境 ledger_primary；关闭 timeline 兜底 | `.env.example`、`relationship_ledger/runtime.py` 生产校验 |
| 可靠性 | Outbox 积压告警；重试策略文档 | `observability/outbox_health.py`、`docs/RETRY_POLICY.md` |
| 性能 | Gateway 连接池；搜人 criteria 内存缓存 + MySQL 快照表 | `PARTNER_GATEWAY_DB_POOL_MAX`、`search_cache.py`、`search_snapshot_store.py`、`m0004_partner_search_snapshots` |
| 安全 | 生产禁 stub 登录；JSON-RPC 仅 internal；密钥与风控外置 | `her_production.py`、`auth_providers.py`、`config/fraud_graph_rules.yaml` |
| AI | Discovery/Chat 分端点；persona-eval 门禁 | `.env.example`、`discovery_system/agent_runtime.py`、`.github/workflows/persona-eval-gate.yml` |
| 前端 | 无生产 mock；统一离线/错误；a11y | `app-connectivity.tsx`、`request-error-state.tsx`、`error-state.tsx`、`layout.tsx` |
| DevEx | `docker compose` 一键栈；REST 契约测；cutover 脚本 | `docker-compose.yml`、`tech_optimization_cutover.py`、`validate_tech_optimization_env.py` |

---

## 1. 架构

### 1.1 Gateway 三分面部署

**现状**：`PARTNER_GATEWAY_SURFACE` + `PARTNER_GATEWAY_ENABLE_JSONRPC` 已在代码中实现（`gateway/surface_config.py`）。

**落地**：

```bash
# 本地一键（三分面 + MySQL + 调度器 + 前端）
docker compose up -d

# 或沿用 shell（兼容）
scripts/start_local_stack.sh --with-scheduler
```

Compose 服务：

| 服务 | `PARTNER_GATEWAY_SURFACE` | `PARTNER_GATEWAY_ENABLE_JSONRPC` |
|------|---------------------------|----------------------------------|
| `gateway-public` | `public` | `0` |
| `gateway-ops` | `ops` | `0` |
| `gateway-internal` | `internal` | `1` |

详见 [GATEWAY_DEPLOYMENT.md](./GATEWAY_DEPLOYMENT.md)。

### 1.2 Proxy intro 迁移至 matchmaking

**落地**：

- 默认 `HER_PROXY_INTRO_STORAGE=matchmaking`（`.env.example`）；非 matchmaking 值会被忽略
- 实现：`matchmaking_system/proxy_intro_core.py`（`recommendation_system` 为懒加载 re-export）
- 数据迁移：`python scripts/setup_ledger_and_proxy_intro_storage.py`
- **已移除** `HER_ALLOW_LEGACY_PROXY_INTRO_*` 与 `match_domain/proxy_intro_legacy.py`

**生产 cutover 检查表**（由 `scripts/tech_optimization_cutover.py` 自动化；本地/`start_local_stack.sh` 与 e2e bootstrap 默认执行）：

1. [x] 代码默认 matchmaking 存储
2. [x] 全环境 `HER_PROXY_INTRO_STORAGE=matchmaking`（`.env.example` / compose / CI / e2e 脚本已统一）
3. [x] 运行 `migrate_proxy_intro_to_matchmaking.py`（非 dry-run，含于 cutover）
4. [x] ledger backfill 完成（含于 cutover）

---

## 2. 数据

| 变量 | 生产值 | 说明 |
|------|--------|------|
| `HER_RELATION_LEDGER_READ_MODE` | `ledger_primary` | 关系时间线以 ledger 为准 |
| `HER_ALLOW_LEGACY_TIMELINE_FALLBACK` | **未设置** | 禁止合并旧 domain events |

`HER_PRODUCTION_MODE=1` 时，`scripts/validate_production_env.py` 与 `relationship_ledger.runtime` 会拒绝开启 legacy timeline fallback。

---

## 3. 可靠性

### 3.1 Outbox 告警

`observability/outbox_health.py` 在 worker / scheduler 消费后调用 `emit_outbox_health_alerts()`，基于 `summarize_outbox()` 发出：

- `{system}.outbox_backlog` — pending + retry_due
- `{system}.outbox_failed_depth` — failed 行数
- `{system}.outbox_processing_stale` — 超时 processing

阈值环境变量：`HER_ALERT_{CHAT|RECOMMENDATION|MATCHMAKING}_OUTBOX_*`（见 `docs/RETRY_POLICY.md`）。

### 3.2 重试策略

见 [RETRY_POLICY.md](./RETRY_POLICY.md)。

---

## 4. 性能

| 变量 | 建议值 | 说明 |
|------|--------|------|
| `PARTNER_GATEWAY_DB_POOL_MAX` | `8`–`32` | 每库连接池上限；`0` 为每请求新建 |
| `PARTNER_SEARCH_CACHE_TTL_SECONDS` | `120` | criteria 热点缓存 TTL；`0` 关闭 |
| `PARTNER_SEARCH_CACHE_MAX_ENTRIES` | `256` | 进程内 LRU 上限 |
| `PARTNER_SEARCH_SNAPSHOT_PERSIST` | `1` | 启用 MySQL 快照表（跨进程/重启） |

---

## 5. 安全

| 项 | 落地 |
|----|------|
| 真实 SMS/微信 | `HER_PRODUCTION_MODE=1` 时禁止 stub / mac_messages / 未配置 SMS |
| JSON-RPC | 仅 `SURFACE=internal` 且 `ENABLE_JSONRPC=1` |
| 密钥 | `her_production.require_secret()`；生产用 K8s Secret / Vault 注入，勿提交 `.env` |
| fraud_graph | `config/fraud_graph_rules.yaml` + `fraud_graph_config.py` |

部署前：

```bash
HER_PRODUCTION_MODE=1 python scripts/validate_production_env.py
```

---

## 6. AI

### 6.1 Discovery / Chat 分离

生产必须设置（勿依赖 chat 变量回退）：

```bash
HER_DISCOVERY_AGENT_API_KEY=...
HER_DISCOVERY_AGENT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
HER_DISCOVERY_AGENT_MODEL=qwen3.6-plus
HER_DISCOVERY_AGENT_WIRE_API=responses
```

`HER_PRODUCTION_MODE=1` 且未配置 discovery 专用 key/base_url 时，discovery runtime 启动失败。

### 6.2 persona-eval 回归门禁

```bash
python scripts/persona_eval_regression_gate.py \
  --baseline artifacts/persona-eval/persona_agent_metrics_v11_2026-04-29.json \
  --candidate path/to/new_metrics.json
```

CI：`.github/workflows/persona-eval-gate.yml`（PR 跑 skill 单测 + baseline 对比）。

---

## 7. 前端

| 项 | 落地 |
|----|------|
| 生产 mock | `env.ts` 已在 `NODE_ENV=production` 强制关闭 |
| 离线/错误 | `AppConnectivityProvider` + `RequestErrorState` |
| a11y | `layout.tsx` skip-link；`RequestErrorState` 带 `role="alert"` |

---

## 8. DevEx

```bash
docker compose up -d          # MySQL + 三分面 Gateway + scheduler
docker compose --profile frontend up -d   # 含 Next.js
scripts/compose_bootstrap.sh  # 仅初始化 schema/seed
```

契约测试：

```bash
python -m unittest external-systems/partner-http-gateway/gateway_tests/test_openapi_contract.py
```

---

## 9. Cutover 与验收

```bash
# 一键 cutover（迁移 + backfill + 验证报告）
python scripts/tech_optimization_cutover.py

# 仅验证当前库状态
python scripts/tech_optimization_cutover.py --verify-only

# 环境一致性（repo 模板 + 当前 env）
python scripts/validate_tech_optimization_env.py
```

## 验收命令

```bash
# 环境校验
HER_PRODUCTION_MODE=1 python scripts/validate_production_env.py

# Gateway 面 + 契约
python -m unittest discover -s external-systems/partner-http-gateway/gateway_tests -p 'test_*.py'

# Outbox / proxy intro / ledger
python -m pytest tests/test_proxy_intro_matchmaking_storage.py tests/test_status_layering_and_ledger.py -q

# persona-eval 门禁（需 baseline）
python scripts/persona_eval_regression_gate.py --self-check

# 前端生产构建
cd frontend/her-app && NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=false pnpm build
```

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-26 | 收尾：cutover 自动化、搜人 MySQL 快照表、环境校验 CI、request-error-state |
| 2026-05-26 | 初版落地：代码、compose、文档、CI 门禁 |
