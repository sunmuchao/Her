# 红娘发现页性能与交互架构优化方案

> 版本：2026-05-27  
> 状态：**方案文档**（待按阶段落地）  
> 范围：C 端「红娘」Tab（`DiscoverPage` / `/discover`）、`discovery_system`、关联前端 hooks 与 persona 写入策略  
> 相关：`SYSTEM_DOC.md` §5.5 / §6、`docs/PERFORMANCE_OPTIMIZATION.md`（后台批处理已落地项）、`docs/TECH_OPTIMIZATION_10_3_IMPLEMENTATION.md`（连接池与搜人缓存）

---

## 目录

1. [背景（大白话）](#1-背景大白话)
2. [现状与瓶颈](#2-现状与瓶颈)
3. [目标体验](#3-目标体验)
4. [方案总览](#4-方案总览)
5. [方案 A：资料填完后首搜不调 AI](#5-方案-a资料填完后首搜不调-ai)
6. [方案 B：聊天中不写档案、聊后自动更新画像](#6-方案-b聊天中不写档案聊后自动更新画像)
7. [合并后的端到端流程](#7-合并后的端到端流程)
8. [前端优化（体感与瀑布流）](#8-前端优化体感与瀑布流)
9. [后端 / AI / 配置优化](#9-后端--ai--配置优化)
10. [实施阶段建议](#10-实施阶段建议)
11. [风险与缓解](#11-风险与缓解)
12. [验收与观测](#12-验收与观测)
13. [附录：代码锚点与相关文档](#13-附录代码锚点与相关文档)

---

## 1. 背景（大白话）

红娘页（发现页）用户体感慢，**主要不是在等 React 画页面**，而是在等后端「小雅」办完一整套事：

- 进门有时要等 AI 想开场白；
- 发一条消息，后端可能：理解意图 → 写画像 → 搜人 → 落库 → 再生成回复；
- 前端还把多个接口**串行**排队，骨架屏消失得更晚。

本方案把讨论收敛为两条产品/架构主线，并配上工程落地路径：

| 编号 | 核心想法 | 目的 |
|------|----------|------|
| **A** | 资料（onboarding）填完后，**先按已填条件直接搜人展示**，首屏不绑 AI 开场 | 首屏有「货」、降低等待 |
| **B** | 聊天过程中**不写 persona 档案**；搜人靠 **DB 已有画像 + 本场对话记忆/临时条件**；**聊结束后**用完整记录 **自动** 更新画像（无需用户确认） | 每轮更快、少 tool 往返、常能省 token |

二者可组合：**先给结果，再聊天；聊天快写库慢；重要动作仍可即时落库。**

---

## 2. 现状与瓶颈

### 2.1 前端（`her-app`）

| 现象 | 原因（代码） |
|------|----------------|
| 首屏骨架屏久 | `useDiscoverySession` 串行：`hydrateSessionFromAuthMe` → `get/createDiscoverySession` → `hydrateFromResponse`（内含 `fetchCollectedStatements`）后才 `isLoadingSession = false` |
| 发消息后「卡住」 | `isTyping` 恒为 `false`，无「正在输入」；用户消息非乐观更新，需等 `submitDiscoveryTurn` 返回 |
| 来信子页慢 | `useRecommendationInbox` 在 cards 之后可能 N 次 `fetchConversionViewsForSubscription` |

关键文件：

- `frontend/her-app/hooks/use-discovery-session.ts`
- `frontend/her-app/components/her/discover-page.tsx`
- `frontend/her-app/hooks/use-badge-counts.ts`

### 2.2 后端（`discovery_system`）

| 场景 | API | 典型耗时来源 |
|------|-----|----------------|
| 首次进入 / 无本地 session | `POST /v1/discovery/sessions` | `create_session` 内同步 `initial_decision()` → Agents SDK `Runner.run_sync` |
| 再次进入 | `GET /v1/discovery/sessions/{id}` | 一般较快（读 session / view） |
| 发消息 / 点 action | `POST .../turns` | `run_turn()` + 可选 tool：`sync_requester_persona_memory` → `search_partner_candidates` |

`create_session` 与 `process_turn` 均在**同一 HTTP 请求内**完成：Agent 决策 → 写 session/turn/view_snapshot/search_run → audit。

关键文件：

- `external-systems/partner-discovery-system/discovery_system/service.py`
- `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`
- `external-systems/partner-discovery-system/discovery_system/service_integrations.py`

### 2.3 Agent 与搜人

- Discovery Agent 默认模型与超时见 `HER_DISCOVERY_AGENT_*`（默认 timeout 最高 120s）。
- Prompt 鼓励：**有稳定新信息时先 `sync_requester_persona_memory`，再搜索** → 单轮可能多轮 tool。
- **搜人本身不依赖 LLM**：`search_partner_candidates_with` 使用 `profiles` + `persona` + `criteria_overrides`，经 `build_discovery_search_request` 编译后调用 `partner_search`（见 `match_domain/criteria_compiler.py`）。
- 仓库已有 `run_discovery_collect_then_search(..., persona_patch=None)`，即 **search_only** 编排能力。

### 2.4 已具备、需确认开启的基础设施

| 能力 | 配置 / 代码 |
|------|-------------|
| Gateway DB 连接池 | `PARTNER_GATEWAY_DB_POOL_MAX` |
| 搜人 criteria 缓存 + MySQL 快照 | `PARTNER_SEARCH_CACHE_TTL_SECONDS`、`partner_search/search_cache.py` |
| Discovery / Chat Agent 分端点 | `HER_DISCOVERY_AGENT_*` vs `HER_CHAT_AGENT_*` |

详见 `docs/TECH_OPTIMIZATION_10_3_IMPLEMENTATION.md`。

---

## 3. 目标体验

### 3.1 用户侧

1. **填完资料进入红娘页**：几秒内看到「按你资料先找的」候选人卡片 + 简短固定开场（不等待 LLM 寒暄）。
2. **聊天调条件**：发送后立刻看到自己的话 +「小雅正在输入」；几秒内收到回复；若触发搜人，列表随条件更新。
3. **离开或一段时间后**：偏好自动沉淀到长期画像；下次进入首搜更准。
4. **明确动作**（如「保存为长期留意」）：仍即时落库，不拖到聊后。

### 3.2 工程侧

| 指标 | 方向 |
|------|------|
| 首屏 TTI | `POST /sessions` 或首屏关键路径 p95 明显下降（方案 A + 前端并行） |
| 单轮 turn 延迟 | 去掉聊天中 persona sync tool 后 p95 下降 |
| Token / 成本 | 每轮少 0～1 次 tool；聊后 1 次结构化抽取（相对多轮 sync 常更省，需控制摘要长度） |
| 正确性 | 聊天中搜人依赖 session 临时条件 + tool `criteria_json`，不依赖 DB persona 实时更新 |

---

## 4. 方案总览

```mermaid
flowchart TB
  subgraph onboarding [资料填写完成]
    P[profiles 已写入]
  end

  subgraph entry [进入红娘页 - 方案 A]
    S1[create_session 或 restore]
    S2[profile 驱动 search_only]
    S3[展示卡片 + 模板开场]
    S1 --> S2 --> S3
  end

  subgraph chat [聊天中 - 方案 B]
    C1[读 DB profiles + persona]
    C2[读 session working_criteria + Agent 记忆]
    C3[run_turn: 仅 search tool + 回复]
    C4[不写 persona]
    C1 --> C2 --> C3 --> C4
  end

  subgraph end [会话结束]
    E1[触发器: 离开/超时/新 session]
    E2[从 discovery_turns 拉全量对话]
    E3[摘要 + 一次 LLM 抽取 patch]
    E4[upsert_persona_memory 自动落库]
    E1 --> E2 --> E3 --> E4
  end

  P --> entry
  entry --> chat
  chat --> end
```

| 阶段 | 改动类型 | 优先级 |
|------|----------|--------|
| 前端并行 + Typing + 乐观消息 | 前端 | P0（体感） |
| 首屏 profile 首搜（无 initial LLM） | discovery `create_session` 编排 | P0 |
| 聊天去掉 sync tool + session working_criteria | Agent + service | P1 |
| 聊后批量 persona 更新任务 | 新 worker / gateway 维护接口 | P1 |
| 异步 turn / SSE（可选） | 前后端 | P2 |

---

## 5. 方案 A：资料填完后首搜不调 AI

### 5.1 结论

**赞成。** Onboarding 写入的 `profiles` 已是结构化条件；`search_partner_candidates` 可在无 LLM 情况下执行。

### 5.2 与现状差异

| 现状 | 目标 |
|------|------|
| `create_session` 末尾必调 `runtime.initial_decision()` | 建 session 后立即 `search_partner_candidates(criteria={})` 或仅用 profile/persona 编译条件 |
| 用户首屏等 AI 开场 | `view` 直接带 `result_group` + 模板 `assistant_message` |

### 5.3 推荐编排（`DiscoveryService.create_session`）

1. `storage.save_session`（phase 可先 `results_shown` 或 `collecting_preferences`）。
2. 调用 `search_partner_candidates_with`（**不**传 `persona_patch`；`criteria_overrides` 可为空，由 `compile_effective_criteria` 吃 profile + 已有 persona）。
3. `_apply_runtime_result` 填入卡片；`assistant_message` 使用**固定模板**，例如：  
   「我根据你刚填的资料筛了几位，你先看看有没有眼缘。觉得不合适，随时跟我说。」
4. **不**调用 `initial_decision()`；或改为后台异步/用户首条消息再调。
5. 照常 `create_turn`（`request_kind=session_opened`）、`view_snapshot` 持久化（审计与恢复）。

可参考已有编排：`service_integrations.run_discovery_collect_then_search(..., orchestration="search_only")`。

### 5.4 产品注意点

- 资料过粗 → 结果泛或为空：需空状态 + 引导进对话微调。
- 用户已在 persona 有历史偏好：首搜仍合并 `persona_row`（与 onboarding 资料叠加）。
- 与方案 B 一致：聊天中条件变更靠 session，不靠本次写库。

### 5.5 可选增强

- Onboarding `onComplete` 时 **pre-warm**：后台 `POST /v1/discovery/sessions`，进页只做 `GET`。
- 新用户与老用户分支：仅 `onboarding_status=completed` 且本场为新 session 时走 profile 首搜。

---

## 6. 方案 B：聊天中不写档案、聊后自动更新画像

### 6.1 结论

**方向成立**：聊天中不写 `persona_memory` 可显著降低每轮延迟与 token；聊后根据**完整聊天记录**一次性 `upsert` **可行**，且**不需要用户确认**，但须定义触发器、保守写入策略与即时落库例外。

### 6.2 「档案」两层含义

| 层级 | 存储 | 何时写入 |
|------|------|----------|
| **资料 `profiles`** | 对外展示字段 | Onboarding / 资料页（已完成） |
| **画像 `persona` / collected** | 偏好、must_have、对话沉淀 | **现状**：聊天中 AI 调 `sync_requester_persona_memory`；**目标**：聊后批处理 + 少量即时例外 |

### 6.3 聊天中如何仍能搜准（不写 DB persona）

搜人链路已支持 **`criteria_overrides`**（Agent tool `search_partner_candidates(criteria_json)`）：

```
compile_effective_criteria(
  profile_row=self_profile,
  persona_row=persona_row,      // 上一场或历史沉淀，聊天中可不变
  overrides=criteria_overrides // 来自本场 AI 或 session.working_criteria
)
```

**必须保证**（不能单靠模型记忆）：

1. **`session.state.working_criteria`**（或等价字段）：后端在每次成功 search / 明确 criteria_labels 后合并更新；`search_partner_candidates_with` 在 overrides 为空时回退到 working_criteria。
2. **Agent 工具集**：聊天 turn **移除** `sync_requester_persona_memory`；保留 `search_partner_candidates`、`create_saved_search_subscription_from_last_search`（订阅仍可能需即时条件）。
3. **Prompt 调整**：删除「先 sync 再搜」；改为「用 official_context + 本场 working_criteria + 用户最新消息决定 search 参数」。

Agent **会话记忆**（`HER_DISCOVERY_AGENT_SESSION_MEMORY`，默认 limit 80）用于多轮对话连贯；**不能**作为聊后更新的唯一来源（超长会话会截断）。

### 6.4 聊后自动更新画像（无需用户确认）

#### 触发器（产品需定稿，代码侧暂无统一 `close_session`）

建议采用**组合触发**（满足其一即入队）：

| 触发 | 说明 |
|------|------|
| 离开红娘 Tab / 页面 `visibility hidden` 超时 | 前端 beacon 或 `POST .../sessions/{id}/finalize` |
| Session 空闲 ≥ N 分钟 | 调度器扫描 `updated_at` |
| 同用户新建 discovery session | 旧 session finalize |
| 每日兜底批处理 | 扫未 finalize 的 active session |

#### 处理流水线

1. 从 `discovery_turns` + `view.timeline` 拉取本场 **user/assistant** 全量文本（不依赖 Agent session 内存）。
2. **摘要**（规则或小模型，控制在数百～千余 token）：降低聊后单次 LLM 成本。
3. **一次**结构化抽取 → `persona` patch JSON（字段与现有 `sync_requester_persona_memory` patch 对齐）。
4. `upsert_persona_memory`：`source_type=inferred` / `basis=discovery_session_finalize`，`conversation_ref=discovery/{session_id}`。
5. 标记 session `persona_finalized_at`；避免重复跑。

#### 写入策略（无确认时的风控）

| 原则 | 做法 |
|------|------|
| 不覆盖用户明确填过的字段 | `explicit` / profile_form 来源优先于 inferred |
| 试探性口语降权 | 「先看看」「说不定」不进 must_have |
| 只写稳定、重复出现的偏好 | 抽取 prompt 中约束 confidence |
| 可审计可改 | 用户可在「采集偏好」页查看/修正（已有 collected 路由） |

### 6.5 Token 与延迟

| 维度 | 聊天中不写档案 | 聊后批处理 |
|------|----------------|------------|
| **延迟** | 每轮少 0～1 次 tool + DB 写入，体感明显提升 | 不阻塞用户 |
| **Token** | 每轮 prompt 可缩短（无 sync 说明） | 1 次摘要 + 1 次抽取；通常 **短会话** 优于 N 次 sync；**极长会话** 需摘要否则单次输入过大 |

### 6.6 必须即时写库的例外

以下**不应**等到聊后：

- 用户点击 **「保存为长期留意 / 创建订阅」**（`create_saved_search_subscription_from_last_search`）→ 条件进推荐系统。
- 合规/安全相关明示确认（若未来有）。
- 可选：用户明确说「以后都按这个来」且模型置信度高 → 可触发即时 partial sync（P2）。

---

## 7. 合并后的端到端流程

```text
[Onboarding 完成]
    profiles 写入 DB
         ↓
[进入红娘页]
    POST sessions（或 GET 恢复）
    → search_only（profile + 已有 persona）
    → 展示候选人 + 模板开场（无 initial_decision）
         ↓
[用户聊天]
    每轮：读 profiles + persona + session.working_criteria + Agent 记忆
    → 可选 search（criteria 写入 working_criteria）
    → 回复展示（不写 persona）
    前端：乐观用户消息 + isTyping
         ↓
[会话结束触发]
    摘要 discovery_turns
    → 一次抽取 patch → upsert_persona_memory（自动）
         ↓
[下次进入]
    persona 已更新 → 首搜更准
```

---

## 8. 前端优化（体感与瀑布流）

与方案 A/B 正交，建议 **P0 同步做**：

| 项 | 做法 |
|----|------|
| 对话内嵌卡片 | `timeline` 按序渲染 `assistant_message` / `user_message` / `result_group`（**已落地**，不再把全部候选人堆在底部） |
| 并行请求 | `auth/me`、`discovery session`、`collected` 并行；**不以** `collected` 阻塞 `isLoadingSession` |
| Typing | `isTyping` 绑定 `isSubmittingTurn` |
| 乐观 UI | `submitTurn` 先 append 用户消息，失败再回滚 |
| Session 恢复 | 优先 localStorage + `GET`；仅 404 再 `POST` 创建 |
| 来信页 | conversion 标签懒加载或批量 API，避免 per-subscription 串行 |

文件：`use-discovery-session.ts`、`discover-page.tsx`。

---

## 9. 后端 / AI / 配置优化

| 类别 | 建议 |
|------|------|
| **配置** | 确认 `PARTNER_SEARCH_CACHE_TTL_SECONDS=120`、`PARTNER_GATEWAY_DB_POOL_MAX=16`；Discovery 使用更快模型 `HER_DISCOVERY_AGENT_MODEL` |
| **create_session** | 实施方案 A；`HER_DISCOVERY_AGENT_RUNTIME=stub` 仅本地调试 |
| **process_turn** | 实施方案 B；精简 `official_context` payload |
| **持久化** | 评估 `save_compiled_snapshot`、部分 audit 异步化（不改对外 JSON） |
| **架构 P2** | `POST /turns` → 202 + 轮询/SSE；流式 assistant 文案 |

---

## 10. 实施阶段建议

### 阶段 1（1～2 天）— 体感与可观测

- [ ] 前端：并行加载、Typing、乐观消息
- [ ] 确认搜人缓存与 DB 池配置
- [ ] Network/日志基线：sessions、turns p50/p95

### 阶段 2（3～5 天）— 方案 A

- [x] `create_session`：profile 首搜 + 模板开场；跳过 `initial_decision`（`HER_DISCOVERY_CREATE_SESSION_MODE=profile_first`，默认）
- [ ] 测试：新用户 onboarding 后进页、0 结果、有结果、恢复 session
- [ ] 更新 Gateway 契约测 / e2e（`her-flow.spec.ts` discovery 段）

### 阶段 3（5～8 天）— 方案 B

- [ ] `session.state.working_criteria` 读写与 search 合并
- [ ] Agent：移除聊天中 `sync_requester_persona_memory`；改 prompt
- [ ] `finalize_discovery_session` API + 触发器（前端离开 / 空闲扫描）
- [ ] 聊后：摘要 + 抽取 + `upsert_persona_memory`
- [ ] 单测：`test_discovery_system.py` 覆盖 search_only 首屏、finalize 不写重复

### 阶段 4（可选）— 异步 turn / 流式

---

## 11. 风险与缓解

| 风险 | 缓解 |
|------|------|
| 首搜 0 结果 | 空状态 + 引导对话；勿误判为「没人」 |
| 聊天中搜人仍用旧条件 | **强制** working_criteria 合并进 search |
| 聊后画像写错 | inferred 不覆盖 explicit；偏好页可改 |
| 用户中途离开未 finalize | 多触发器 + 下次进页补跑 |
| 订阅/推荐与聊后画像不一致 | 订阅动作即时落库；推荐读 last_search_run |
| 长会话 Agent 记忆截断 | finalize 读 DB turns，不读 Agent memory |
| 聊后单次 LLM 过大 | 先摘要再抽取 |

---

## 12. 验收与观测

### 12.1 浏览器 / API

| 检查 | 期望 |
|------|------|
| 新用户首进 `POST /sessions` | 明显短于改前（无 LLM 时 <2s 量级，视搜人库而定） |
| `POST /turns` | 无 `sync_requester_persona_memory` tool_calls |
| `GET /sessions/{id}` 回访 | 仍快 |
| finalize 后 `GET /v1/persona/collected` | 反映本场偏好（允许延迟数秒） |

### 12.2 指标与日志

- Discovery funnel：`session_open`、`user_message`、`tool_calls.search_partner_candidates`、`persona_finalize`
- `trace_id` 贯穿 Gateway 与 discovery audit
- 对比改前改后：sessions/turns 延迟、tool 次数、Agent token（若已接用量日志）

### 12.3 回归范围

```bash
pytest external-systems/partner-discovery-system/tests/test_discovery_system.py -q
# 前端
cd frontend/her-app && pnpm test -- --testPathPattern=discovery
```

---

## 13. 附录：代码锚点与相关文档

### 13.1 关键代码

| 模块 | 路径 |
|------|------|
| 发现页 UI | `frontend/her-app/components/her/discover-page.tsx` |
| Session hook | `frontend/her-app/hooks/use-discovery-session.ts` |
| Discovery API | `frontend/her-app/lib/api/endpoints/discovery.ts` |
| create_session / process_turn | `external-systems/partner-discovery-system/discovery_system/service.py` |
| Agent runtime | `external-systems/partner-discovery-system/discovery_system/agent_runtime.py` |
| 搜人 + persona sync | `external-systems/partner-discovery-system/discovery_system/service_integrations.py` |
| Criteria 编译 | `match_domain/criteria_compiler.py` → `build_discovery_search_request` |
| Gateway 路由 | `external-systems/partner-http-gateway/gateway/discovery_routes.py` |
| Agent 会话记忆 | `external-systems/partner-discovery-system/discovery_system/agent_session_store.py` |

### 13.2 相关文档

| 文档 | 说明 |
|------|------|
| [`SYSTEM_DOC.md`](../SYSTEM_DOC.md) | 系统总览 §5.5 发现页、§10.3 技术优化 |
| [`PERFORMANCE_OPTIMIZATION.md`](./PERFORMANCE_OPTIMIZATION.md) | 后台批处理性能（撮合/推荐/搜人分批） |
| [`TECH_OPTIMIZATION_10_3_IMPLEMENTATION.md`](./TECH_OPTIMIZATION_10_3_IMPLEMENTATION.md) | 连接池、搜人缓存、Agent 分端点 |
| [`design-pages/02-discovery-session.md`](./design-pages/02-discovery-session.md) | 发现会话页产品设计（实现以代码为准） |
| [`archive/discovery-agent-native-architecture-plan-20260514.md`](./archive/discovery-agent-native-architecture-plan-20260514.md) | 历史 Discovery Agent 架构（仅供参考） |

### 13.3 环境变量速查

| 变量 | 用途 |
|------|------|
| `HER_DISCOVERY_AGENT_RUNTIME` | `agents_sdk` / `stub` |
| `HER_DISCOVERY_AGENT_MODEL` | Discovery 专用模型 |
| `HER_DISCOVERY_AGENT_TIMEOUT_SECONDS` | Agent 超时 |
| `HER_DISCOVERY_PROFILE_SOURCE` | 搜人 profile 源 |
| `HER_DISCOVERY_CREATE_SESSION_MODE` | `profile_first`（默认，资料首搜）/ `agent`（LLM 开场） |
| `PARTNER_SEARCH_CACHE_TTL_SECONDS` | 搜人缓存 TTL（0=关） |
| `PARTNER_GATEWAY_DB_POOL_MAX` | Gateway 连接池 |
| `HER_DISCOVERY_AGENT_SESSION_MEMORY` | Agent 多轮记忆开关 |
| `HER_DISCOVERY_AGENT_SESSION_LIMIT` | 记忆条数上限（默认 80） |

---

## 变更记录

| 日期 | 说明 |
|------|------|
| 2026-05-27 | 初版：汇总红娘页性能分析、方案 A（资料首搜）、方案 B（聊后写画像）、前端与实施阶段 |
