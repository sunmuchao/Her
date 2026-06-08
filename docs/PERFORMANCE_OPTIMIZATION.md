# Her 性能优化方案与落地说明

> 版本：2026-05-26（第二轮：开案 / 卡片投递 / 搜人流式 / Discovery 批量 action）  
> 原则：**不改变业务逻辑、API 签名与对外 JSON 输出**；仅优化 I/O 批次、并发与内存加载方式。

---

## 1. 背景（大白话）

系统在部分后台任务里像「100 对人要办手续，却每人跑 10 趟档案室」。优化方向是：**一次抱齐资料，在桌上对照处理**，送到用户手里的结果与现在一致。

| 办事员 | 负责什么 | 问题 | 改法 |
|--------|----------|------|------|
| A | 撮合自动开案 | 每对重复查成员、边、今日案量、未结案 | 开案前批量预取 |
| B | 按条件搜人 | 宽条件全量进内存再打分 | 分批拉取 + 分批 merge persona；缓存重复条件 |
| C | App 推荐卡片投递 | 每条待推送单独查 actions / 订阅 / 日 cap | 批量 IN 查询 + JOIN 订阅字段 |
| （已有） | 转化视图、池刷新、聊天时间线、订阅刷新 | — | 见 §2 |

---

## 2. 第一轮已落地（2026-05-26 前）

| 优先级 | 模块 | 状态 |
|--------|------|------|
| P0 | `recommendation_system.conversion_views` | ✅ 订阅级批量 actions/cases/events |
| P0 | `matchmaking_system.pool_members` | ✅ 批量边/成员 + `MATCHMAKING_POOL_REFRESH_MAX_WORKERS` |
| P0 | `partner_search` 分页拉 profile | ✅ `iter_profile_batches` |
| P1 | `chat_system.conversations` | ✅ `list_conversation_messages_for_conversations` |
| P1 | `recommendation_system.subscriptions` | ✅ `refresh_due_subscriptions` 并行 |
| 横切 | Gateway 连接池、搜人 LRU+MySQL 快照 | ✅ 见 `docs/TECH_OPTIMIZATION_10_3_IMPLEMENTATION.md` |

---

## 3. 第二轮：撮合自动开案（P0）

### 3.1 问题

`open_match_cases` 对每个 `eligible` 配对：

- `list_pairs(attach_profile_refs=True)` 每对 2× `get_pool_member`
- 循环内再 2× `get_pool_member`、2× `get_edge`、2× `_member_has_open_case`、2× `_count_member_cases_today`

约 **6N～10N** 次 DB round-trip。

### 3.2 方案

1. `list_pairs(..., attach_profile_refs=False)`
2. `get_pool_members_by_ids` / `get_edges_among_members` 一次预取
3. 新增 `members_with_open_cases`、`count_member_cases_today_for_members`（`pairs.py`）
4. 循环内仅 dict 查找，分支与写入逻辑不变

### 3.3 涉及文件

- `matchmaking_system/pairs.py`
- `matchmaking_system/matchmaking_cases.py`

### 3.4 预期收益

eligible 配对多时 DB 往返 **↓ 85–95%**，开案任务耗时 **↓ 50–80%**。

---

## 4. 第二轮：应用内卡片投递（P0）

### 4.1 问题

`deliver_in_app_recommendations` 对每条 `pending_delivery`：

- `inflate_recommendation` 无 `preloaded_action_rows` → 每条查 `recommendation_actions`
- 无 `subscription_overrides_json` → `_apply_review_projection` 每条 `get_subscription`
- `count_cards_delivered_today` 按 requester 多次 COUNT

### 4.2 方案

1. 拉取 pending 后批量 `list_recommendation_actions_for_recommendations`
2. JOIN 增加 `s.subscription_overrides_json`（及 review 所需订阅列），避免逐条 `get_subscription`
3. `count_cards_delivered_today_by_requesters` 一次 `GROUP BY requester_id`
4. `inflate_recommendation(..., preloaded_action_rows=...)`

### 4.3 涉及文件

- `recommendation_system/in_app_delivery.py`
- `recommendation_system/subscriptions.py`（可选 `list_subscriptions_by_ids`）

### 4.4 预期收益

pending 队列 100+ 时 DB 往返 **↓ 70–90%**，任务耗时 **↓ 40–60%**。

---

## 5. 第二轮：Partner Search 内存（P1）

### 5.1 问题

`load_mysql` 分批 fetch 后仍 `rows.extend(batch)` 再统一 normalize + 一次性 `load_personas_by_profile_ids`，峰值内存偏高。

### 5.2 方案

按 batch：**该批 persona 批量加载 → 立即 normalize → 追加结果**，不再保留原始 `rows` 大列表。  
打分语义不变（仍全量 `evaluate_records` → sort → diversity）。  
生产启用 `PARTNER_SEARCH_CACHE_TTL_SECONDS` / `PARTNER_SEARCH_SNAPSHOT_PERSIST`（`.env.example`）。

### 5.3 涉及文件

- `partner_search/search_sources.py`

### 5.4 预期收益

宽条件内存峰值 **↓ 40–70%**；重复 criteria **接近 O(1)**（缓存命中）。

---

## 6. 第二轮：Discovery 可见 action（P1）

### 6.1 问题

`build_visible_action_summaries` 最多 3 次 `get_action`，MySQL 实现每次 `_open()` 新连接。

### 6.2 方案

- `storage.get_actions(session_id, action_ids) -> dict[str, StoredAction]`
- 单次 `WHERE action_id IN (...)` 查询

### 6.3 涉及文件

- `discovery_system/storage.py`（内存 + MySQL）
- `discovery_system/service_context.py`

---

## 7. 环境变量一览

| 变量 | 默认 | 说明 |
|------|------|------|
| `PARTNER_SEARCH_CACHE_TTL_SECONDS` | `120`（`.env.example`） | >0 启用 criteria LRU |
| `PARTNER_SEARCH_CACHE_MAX_ENTRIES` | `256` | LRU 上限 |
| `PARTNER_SEARCH_SNAPSHOT_PERSIST` | `1` | MySQL 快照表 |
| `PARTNER_SEARCH_PROFILE_BATCH_SIZE` | `500` | profile 分页；0=单次 fetch |
| `MATCHMAKING_POOL_REFRESH_MAX_WORKERS` | `4` | 池刷新并行度 |
| `RECOMMENDATION_REFRESH_MAX_WORKERS` | `4` | 订阅刷新并行度 |
| `PARTNER_GATEWAY_DB_POOL_MAX` | `16` | 网关每库连接池 |

---

## 8. 回归验证

```bash
pytest external-systems/partner-matchmaking-system/tests/test_matchmaking_system.py -q
pytest external-systems/partner-recommendation-system/tests/test_recommendation_system.py -q
pytest external-systems/partner-discovery-system/tests/test_discovery_system.py -q
pytest partner_search/tests/ -q 2>/dev/null || true
```

---

## 9. 实施清单

| # | 项 | 状态 |
|---|-----|------|
| 1 | 本文档（含大白话与第二轮范围） | ✅ |
| 2 | 撮合 `open_match_cases` 批量预取 | ✅ |
| 3 | `deliver_in_app_recommendations` 批量 | ✅ |
| 4 | `load_mysql` 流式 normalize | ✅ |
| 5 | Discovery `get_actions` 批量 | ✅ |
| 6 | 全量 pytest 回归（matchmaking + recommendation + discovery，54 passed） | ✅ |

---

## 10. 约束（实施时必须遵守）

- 不修改对外 REST/JSON-RPC 响应字段与枚举语义。
- 不改变开案条件、推送 cap、安静时段、多样性选人等业务判定。
- 保留既有异常类型与错误处理路径。
- 仅通过批量查询、预取、并行与内存布局优化降低延迟与 DB 负载。

---

## 11. 基准脚本

可复现基准脚本：

```bash
python scripts/run_perf_benchmarks.py \
  --output-json artifacts/perf-benchmark-report.json
```

更贴近生产数据量的压测参数集：

```bash
python scripts/run_perf_benchmarks.py \
  --preset prod_like \
  --output-json artifacts/perf-benchmark-report-prod-like.json
```

当前预设含义：

| preset | repeat | search_profiles | messages_per_conversation | opening_cases | matchmaking_pairs | layout_updates | recommendation_count | trust_hub_items |
|--------|--------|-----------------|---------------------------|---------------|-------------------|----------------|----------------------|-----------------|
| `default` | `3` | `4000` | `400` | `60` | `40` | `60` | `200` | `50` |
| `prod_like` | `5` | `12000` | `1000` | `180` | `160` | `240` | `800` | `150` |

说明：

- `prod_like` 是本地单机 MySQL 上的**生产近似压测集**，目标是放大对象数量、会话消息量和推荐基数，观察优化后的扩展趋势，而不是精确复刻线上绝对时延。
- 若本机资源有限，可用 `--preset prod_like --repeat 3` 先降重复次数。
- 任意显式 CLI 参数都会覆盖 preset，例如只想放大搜索规模：`--preset prod_like --search-profiles 20000`。

输出内容：

- `partner_search_full_scan`
  - 当前实现 vs `legacy_emulation`
  - 指标：平均耗时、SQL 次数、数据库返回字段单元格数
- `chat_case_timeline`
  - 当前批量 members / 限量消息读取 vs 旧版 N+1 / 全量消息回拉
- `assistant_opening_probe_scan`
  - 当前批量预取扫描 vs 旧版循环内多次查询

说明：

- 脚本默认使用本地 `127.0.0.1:3307` MySQL。
- 搜索基准会自动构造宽表 filler 列，用来放大 `SELECT *` 与列投影差异。
- `Avg Cells` 是数据库返回的字段单元格数代理指标，比单纯行数更能体现宽表 I/O 体积。
