# 发现页 Agent-Native 方案任务拆解

> 文档校准说明：本文少量示例仍引用 `types.py` 等未单独落地的文件。当前 discovery 结构化 schema 主要集中在 `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`、`service.py`、`view_models.py`。

本文档把 [`discovery-agent-native-architecture-plan-20260514.md`](./discovery-agent-native-architecture-plan-20260514.md) 拆成可排期、可开发、可验收的任务。

目标不是继续讨论理念，而是把“前端纯展示、后端不写死产品判断、发现页由 GPT agent 决策”的方案变成可执行工作项。

---

## 1. 拆分原则

### 1.1 先搭 agent 容器，再接产品能力

建议顺序：

1. 先把 discovery session、turn、action、tool-run 这些基础设施建起来
2. 再把 GPT agent 接进去
3. 再把 `partner-search`、`persona-memory-sync`、空结果持续留意、资料详情承接接进去
4. 最后再补观测、质量和前端联调

### 1.2 不要先写业务规则兜底版

这一套方案的前提就是：

- 前端不做业务判断
- 后端也不做规则树判断
- agent 拥有真实决策权

因此不建议先写一个“规则版发现页”再回头改成 agent-native。

### 1.3 工具层和判断层必须分开验收

每个任务都要能回答两个问题：

1. 这个任务是在加“能力”还是在加“判断”
2. 判断是否仍然由 agent 负责

如果一个任务把“什么时候搜、怎么追问、展示谁”写死在代码里，就不符合本方案。

---

## 2. 阶段总览

### Phase A：基础骨架

- `D01` 统一 discovery 术语、边界和输出 schema
- `D02` 建 discovery system 外层目录与基础模块
- `D03` 设计并落 discovery 持久化表

### Phase B：agent 运行时

- `D04` 建 discovery agent runtime
- `D05` 建 discovery tool registry
- `D06` 建 action_id 机制和服务端动作语义存储

### Phase C：搜索与结果渲染

- `D07` 接入 `partner-search` tool
- `D08` 实现 discovery turn 主链路
- `D09` 实现 result card / criteria / action 的 view adapter

### Phase D：详情与持续留意

- `D10` 实现资料详情页读模型
- `D11` 实现空结果持续留意 tool
- `D12` 实现发现页会话恢复与快照

### Phase E：网关、测试与联调

- `D13` 暴露 `/v1/discovery/...` 网关接口
- `D14` 建 discovery 系统测试与假 agent 回归
- `D15` 补日志、审计和运行指标

### 2.1 当前完成情况（截至 2026-05-14）

状态说明：

- `已完成`：主能力已经落地并有自动化验证
- `部分完成`：主干已落地，但还有文档里列出的子能力未补齐
- `未完成`：当前仓库里还没有对应闭环

| 任务 | 当前状态 | 说明 |
| --- | --- | --- |
| `D01` | `已完成` | discovery 术语、边界、render model / detail_view 契约已写入架构文档和本任务文档。 |
| `D02` | `已完成` | `partner-discovery-system` 目录、`storage.py`、`service.py`、`agent_runtime.py`、`view_models.py` 已建立。 |
| `D03` | `已完成` | `discovery_agent_sessions`、`turns`、`actions`、`search_runs` 表和 migration 已落地，支持内存版与 MySQL 版。 |
| `D04` | `已完成` | discovery agent runtime 已落地，支持真实 Agents SDK 路径和 stub fallback。 |
| `D05` | `部分完成` | 当前 runtime 仍以 `get_discovery_session_state`、`get_requester_profile`、`search_partner_candidates`、`create_saved_search_subscription_from_last_search` 为主；目标方案已收敛为 `partner-search`、`persona-memory-sync`、`create_saved_search_subscription_from_last_search` 三项核心业务能力，其余改为上下文注入或后续增强。 |
| `D06` | `已完成` | `action_id` 生成、过期、消费、防重放都已落地。 |
| `D07` | `已完成` | discovery 已接入 `partner-search` 作为纯搜索工具，并持久化 search run。 |
| `D08` | `已完成` | `create_session(...)`、`process_turn(...)`、`get_session_view(...)` 主链路已跑通。 |
| `D09` | `已完成` | timeline、criteria chips、candidate cards、suggested actions 的 view adapter 已落地。 |
| `D10` | `已完成` | 资料详情页已接正式读模型；当前走独立 `profile_detail_reader`，不是把详情页职责挂在 `partner_search` 对外 API 上。 |
| `D11` | `已完成` | 0 结果搜索后，agent 可给出持续留意 action；用户点击后可根据上一轮搜索底稿创建 saved search subscription，并继续走“最新画像重新编译有效搜索请求”的后续刷新机制。 |
| `D12` | `部分完成` | `GET /v1/discovery/sessions/{session_id}` 和最新 view 恢复已可用；独立 `discovery_view_snapshots` 还没单独落表。 |
| `D13` | `已完成` | `POST /v1/discovery/sessions`、`POST /turns`、`GET /sessions/{id}`、`GET /profiles/{id}` 已开放，契约文档已更新。 |
| `D14` | `部分完成` | discovery service / gateway / fake runtime 回归已建立，已覆盖 D11 持续留意闭环；更细的 tool 记录测试还没补齐。 |
| `D15` | `部分完成` | 已有 trace_id、错误码、search_run 持久化等基础观测；专门的 tool-run 审计和指标计数器还没补全。 |

前端联调任务当前状态：

- 发现页和聊天页静态 HTML 原型已做
- discovery 后端接口已具备联调条件
- 真正的前端接口接入仍未开始，前端联调任务 1-5 目前都还不算完成

---

## 3. 具体任务

### D01：统一 discovery 术语、边界和输出 schema

- 优先级：`P0`
- 目标：把“发现页 agent-native”用统一术语写清楚，避免研发阶段各自理解。
- 产出：
  - 明确 discovery session / turn / action / tool-run / view snapshot 定义
  - 明确前端只收 render model，不收底层 search result 原样结构
  - 明确 agent 输出 schema 和前端 render model schema 不是一回事
- 建议文件：
  - [`docs/discovery-agent-native-architecture-plan-20260514.md`](./discovery-agent-native-architecture-plan-20260514.md)
  - 本文档
  - 可选新增：`external-systems/partner-discovery-system/discovery_system/types.py`
- 依赖：无
- 完成标准：
  - 团队对 `session memory`、`tool registry`、`backend source of truth` 使用同一套表述
  - 不再出现“前端解析条件”或“后端规则树兜底发现页”的模糊描述

### D02：创建 `partner-discovery-system` 外层系统骨架

- 优先级：`P0`
- 目标：把发现页从现有聊天系统和推荐系统里独立出来，避免后续逻辑缠绕。
- 产出：
  - 新目录：
    - `external-systems/partner-discovery-system/discovery_system/__init__.py`
    - `storage.py`
    - `service.py`
    - `agent_runtime.py`
    - `view_models.py`
  - 最小 import 路径打通
- 建议文件：
  - `external-systems/partner-discovery-system/**`
  - `pyproject.toml`
- 依赖：`D01`
- 完成标准：
  - 仓库能 import `discovery_system`
  - 不依赖前端代码即可单测 discovery system

### D03：落 discovery 持久化表

- 优先级：`P0`
- 目标：把会话、记忆、历史和工具真相放到后端数据库里，避免只靠模型记忆。
- 产出：
  - `discovery_agent_sessions`
  - `discovery_agent_turns`
  - `discovery_agent_actions`
  - `discovery_search_runs`
  - 可选 `discovery_view_snapshots`
- 建议文件：
  - `outer_system_mysql_schema.py`
  - `external-systems/partner-discovery-system/discovery_system/storage.py`
  - 对应测试
- 依赖：`D02`
- 完成标准：
  - 能创建和读取 discovery session
  - 能存 turn、action、search run
  - `state_json` 能保存 `session memory`

### D04：建立 discovery agent runtime

- 优先级：`P0`
- 目标：复用现有聊天红娘的 Agents SDK 运行思路，但换成发现页专用 runtime。
- 产出：
  - `DiscoveryRunInput`
  - `DiscoveryDecision` 或等价结构化输出 schema
  - `run_discovery_agent(...)`
  - provider 配置复用 `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `HER_CHAT_AGENT_*` 或独立 discovery env
- 建议文件：
  - `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`
  - 可参考：`external-systems/partner-chat-system/chat_system/assistant_runtime.py`
- 依赖：`D02`
- 完成标准：
  - discovery agent 能在后端独立运行
  - 输出是结构化 JSON，不是散文字符串
  - 失败时有 fallback 和错误记录

### D05：建立 discovery tool registry

- 优先级：`P0`
- 目标：把 discovery agent 的核心业务能力收敛成少量固定能力；状态类信息由后端注入，而不是把所有读取动作都做成 tool。
- 产出：
  - tool registry 代码
  - 固定核心能力注册入口
  - 上下文注入 contract
  - tool 调用结果记录机制
- 首批核心能力：
  - `partner-search`
  - `persona-memory-sync`
  - `create_saved_search_subscription_from_last_search`
- 不作为首版核心 tool 的能力：
  - `get_discovery_session_state`
    - 改成后端每轮直接注入 session 摘要、phase、visible actions、last search summary
  - `get_requester_profile`
    - 改成后端每轮直接注入 requester persona snapshot
  - `list_recent_discovery_turns`
    - 作为后续增强能力，不进入首版主链路
  - `load_candidate_result_set`
    - 作为后续增强能力，不进入首版主链路
  - `get_candidate_profile_detail`
    - 不放回 agent tool，继续走独立详情页读模型和接口
- 建议文件：
  - `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`
  - `service.py`
  - `storage.py`
- 依赖：`D03`、`D04`
- 完成标准：
  - agent 创建时能绑定固定核心能力
  - 后端每轮会注入正式上下文，而不是依赖 agent 自己记忆
  - 后端能记录每次核心能力调用及其结果引用
  - 不把会话状态读取、详情读取硬塞进 `partner-search` 或 `persona-memory-sync`

### D06：实现 action_id 机制

- 优先级：`P0`
- 目标：保证前端点击建议按钮时只上传 `action_id`，不上传业务语义。
- 产出：
  - 服务端生成 `action_id`
  - 后端保存 `semantic_payload_json`
  - action 过期机制
  - action 重放保护
- 建议文件：
  - `external-systems/partner-discovery-system/discovery_system/storage.py`
  - `service.py`
  - 对应测试
- 依赖：`D03`
- 完成标准：
  - 前端只需提交 `action_id`
  - 后端可恢复动作真实语义
  - 过期 action 有明确错误返回

### D07：接入 `partner-search` tool

- 优先级：`P0`
- 目标：把 `partner-search` 作为 discovery agent 的纯匹配工具接进来，不改它的职责边界。
- 产出：
  - tool wrapper
  - canonical search response 存储
  - search request / response 引用机制
- 建议文件：
  - `external-systems/partner-discovery-system/discovery_system/service.py`
  - `local-skills/partner-search/partner_search/api.py` 只在必要时补适配，不改产品边界
- 依赖：`D05`
- 完成标准：
  - discovery agent 可调用搜索工具
  - 搜索结果可持久化到 `discovery_search_runs`
  - 没有把发现页编排逻辑塞进 `partner-search`

### D08：实现 discovery turn 主链路

- 优先级：`P0`
- 目标：让“用户一句话 -> agent 决策 -> 可展示 JSON”跑通。
- 产出：
  - `create_session(...)`
  - `process_turn(...)`
  - `get_session_view(...)`
  - turn 落库
  - agent 输出落库
- 建议文件：
  - `external-systems/partner-discovery-system/discovery_system/service.py`
  - `storage.py`
- 依赖：`D04`、`D05`、`D06`、`D07`
- 完成标准：
  - 用户发自然语言后，系统能返回：
    - assistant message
    - criteria chips
    - result cards 或追问
    - suggested actions
  - 前端无需自己判断任何业务语义

### D09：实现 discovery view adapter

- 优先级：`P0`
- 目标：让 agent 决定“展示谁、强调什么”，但由后端 deterministic adapter 组装稳定 JSON。
- 产出：
  - `timeline` render model
  - `result_group` render model
  - `criteria_chips` render model
  - `suggested_actions` render model
- 建议文件：
  - `external-systems/partner-discovery-system/discovery_system/view_models.py`
  - `service.py`
- 依赖：`D08`
- 完成标准：
  - 前端收到的 JSON shape 稳定
  - 真实候选字段引用自 canonical search result
  - agent 不能直接编造卡片原始字段值

### D10：实现资料详情页读模型

- 优先级：`P1`
- 目标：让发现页候选卡片点进去后，有一个正式的详情页读接口，而不是靠列表字段拼详情页。
- 产出：
  - `GET profile detail` 对应 service
  - hero、photo gallery、verified、自填、risk/caution、matchmaker notes 分区
- 建议文件：
  - `external-systems/partner-discovery-system/discovery_system/service.py`
  - `view_models.py`
  - 可能需要在 gateway 暴露 `GET /v1/discovery/profiles/{profile_id}`
- 依赖：`D07`、`D09`
- 完成标准：
  - 详情页可以只靠后端返回 render model 渲染
  - 前端不需要再自己拼 `verification_items` 和 `trust_summary`

### D11：实现空结果持续留意 tool

- 优先级：`P1`
- 目标：当这一轮搜索没有合适结果时，由 agent 决定要不要引导持续留意；用户确认后由后端创建订阅。
- 产出：
  - wrapper tool：`create_saved_search_subscription_from_last_search`
  - 对接 `no_match_opt_in`
  - 会话里记录本次 opt-in 动作
- 建议文件：
  - `external-systems/partner-discovery-system/discovery_system/service.py`
  - `external-systems/partner-recommendation-system/recommendation_system/no_match_opt_in.py`
- 依赖：`D07`、`D08`
- 完成标准：
  - 空结果时不是后端写死提示文案
  - 是 agent 决定是否建议持续留意
  - 用户点击后可以实际创建订阅

### D12：实现 discovery session 恢复和 view snapshot

- 优先级：`P1`
- 目标：让发现页刷新、重开、恢复时仍然是“纯展示”，不用前端重算。
- 产出：
  - `GET /v1/discovery/sessions/{session_id}`
  - 可选 `discovery_view_snapshots`
  - render model 恢复逻辑
- 建议文件：
  - `service.py`
  - `storage.py`
  - `view_models.py`
- 依赖：`D08`、`D09`
- 完成标准：
  - 刷新页面后能恢复完整 discover view
  - 前端不做重组装和重判断

### D13：暴露 discovery 网关接口

- 优先级：`P0`
- 目标：让前端有正式接入入口。
- 产出：
  - `POST /v1/discovery/sessions`
  - `POST /v1/discovery/sessions/{session_id}/turns`
  - `GET /v1/discovery/sessions/{session_id}`
  - `GET /v1/discovery/profiles/{profile_id}`
- 建议文件：
  - `external-systems/partner-http-gateway/gateway/app.py`
  - `external-systems/partner-http-gateway/API_CONTRACT.md`
- 依赖：`D08`、`D09`、`D10`
- 完成标准：
  - gateway 返回 discovery render model
  - discovery 相关错误码和参数校验明确

### D14：建立 discovery 测试矩阵

- 优先级：`P0`
- 目标：保证这套系统不是只靠人工点页面感受。
- 测试分层：
  - storage 测试
  - service 测试
  - gateway 测试
  - 假 agent 回归测试
  - tool 调用记录测试
- 关键场景：
  - 首次欢迎
  - agent 先追问
  - agent 直接搜索
  - 结果卡片展示
  - action_id refine
  - 空结果持续留意
  - 详情页读取
- 建议文件：
  - `external-systems/partner-discovery-system/tests/test_discovery_system.py`
  - `external-systems/partner-http-gateway/gateway_tests/*`
- 依赖：`D08`、`D09`、`D10`、`D11`、`D13`
- 完成标准：
  - 核心 discovery 流程有自动化回归
  - 不依赖真实模型也能跑主链路

### D15：补 discovery 观测、审计和指标

- 优先级：`P1`
- 目标：发现页既然把判断交给 agent，就必须能审计“agent 为什么这么做”。
- 产出：
  - 每轮 turn 日志
  - tool run 审计
  - search_run 引用
  - action 点击回流
  - 指标建议：
    - `session_created_count`
    - `turn_processed_count`
    - `search_tool_call_count`
    - `search_zero_result_count`
    - `detail_open_count`
    - `subscription_opt_in_count`
- 建议文件：
  - `service.py`
  - `observability/*`
  - gateway access / pipeline logs
- 依赖：`D08`
- 完成标准：
  - 能追溯某一轮为什么出现某组卡片和某组 actions
  - 能统计零结果率和持续留意转化率

---

## 4. 推荐实施顺序

如果按最稳妥顺序推进，建议这样排：

1. `D01`
2. `D02`
3. `D03`
4. `D04`
5. `D05`
6. `D06`
7. `D07`
8. `D08`
9. `D09`
10. `D13`
11. `D14`
12. `D10`
13. `D11`
14. `D12`
15. `D15`

原因：

- 先打通 session + agent + search 主链路
- 再给前端正式入口
- 然后补详情、持续留意和恢复能力
- 最后加强观测

---

## 5. 最小可上线子集

如果要做一个最小可联调版本，只需要先完成：

- `D01`
- `D02`
- `D03`
- `D04`
- `D05`
- `D06`
- `D07`
- `D08`
- `D09`
- `D13`
- `D14`

这一版就已经能做到：

1. 前端发一句自然语言
2. 后端 agent 自己决定追问还是搜索
3. 返回红娘消息 + 条件 chips + 候选卡片 + action buttons
4. 前端只渲染

---

## 6. 每个任务的最终验收共识

无论是哪个任务，最后都必须满足这三个总要求：

1. 前端不新增业务判断
2. 后端不新增规则树式产品逻辑
3. agent 仍然拥有真实产品决策权

只要某个任务的实现让这三条被破坏，就算功能做出来，也不算符合本方案。

---

## 7. 研发任务单版

如果不想看 `D01-D15`，可以直接按下面这版排期。

### 7.1 后端任务

#### 后端任务 1：创建发现系统骨架

- 目标：新建独立的 `partner-discovery-system`
- 要做的事：
  - 新建 `external-systems/partner-discovery-system/discovery_system/`
  - 先放 `storage.py`、`service.py`、`agent_runtime.py`、`view_models.py`
- 完成后产物：
  - discovery system 可以被 import
- 对应原任务：
  - `D02`

#### 后端任务 2：落发现页会话存储

- 目标：把发现页会话、对话轮次、动作、搜索记录都存下来
- 要做的事：
  - 建 session 表
  - 建 turn 表
  - 建 action 表
  - 建 search_run 表
- 完成后产物：
  - 后端可以恢复任意一个 discovery session
- 对应原任务：
  - `D03`

#### 后端任务 3：接 discovery 专用 GPT agent

- 目标：让发现页请求可以交给 GPT 红娘处理
- 要做的事：
  - 建 `run_discovery_agent(...)`
  - 定 discovery agent 输出 schema
  - 复用现有 OpenAI provider 配置
- 完成后产物：
  - 用户一句话可以得到结构化 agent 输出
- 对应原任务：
  - `D04`

#### 后端任务 4：注册 discovery tools

- 目标：把工具固定挂到 agent 上
- 要做的事：
  - 注册 `partner-search`
  - 注册 `persona-memory-sync`
  - 注册 `create_saved_search_subscription_from_last_search`
  - 把 session / requester profile / recent timeline / last search summary 改成后端上下文注入
- 完成后产物：
  - agent 创建后天然就知道能用哪些核心能力
- 对应原任务：
  - `D05`

#### 后端任务 5：实现 action_id 机制

- 目标：前端点击按钮时只传 `action_id`
- 要做的事：
  - 服务端生成 `action_id`
  - 服务端保存动作语义
  - 做过期和重放保护
- 完成后产物：
  - 前端不用理解按钮背后的业务语义
- 对应原任务：
  - `D06`

#### 后端任务 6：接入 `partner-search`

- 目标：把 `partner-search` 接成 discovery agent 的一个工具
- 要做的事：
  - 写 tool wrapper
  - 存搜索请求和结果
  - 保持 `partner-search` 还是纯搜索工具
  - 让搜索优先消费 `persona-memory-sync` 已同步到 `profiles` 的最新画像
- 完成后产物：
  - agent 可自行决定何时搜索
- 对应原任务：
  - `D07`

#### 后端任务 6A：接入 `persona-memory-sync`

- 目标：让 discovery agent 能把用户新说出的稳定画像写回长期记忆，再驱动后续搜索与持续留意。
- 要做的事：
  - 定义 discovery 到 `persona-memory-sync` 的 patch 生成规则
  - 明确只有“明确、稳定、可落库”的信息才触发写画像
  - 约定常见顺序为：先写画像，再搜索
- 完成后产物：
  - discovery 对话产生的新画像可以沉淀到 `user_personas` / `profiles`
- 对应原任务：
  - `D05`

#### 后端任务 7：打通发现页主链路

- 目标：跑通“用户一句话 -> agent -> 搜索或追问 -> 返回页面 JSON”
- 要做的事：
  - 实现 `create_session(...)`
  - 实现 `process_turn(...)`
  - 实现 `get_session_view(...)`
- 完成后产物：
  - 后端能直接返回前端可展示的数据
- 对应原任务：
  - `D08`

#### 后端任务 8：实现 render model 适配层

- 目标：把 agent 输出整理成前端稳定 JSON
- 要做的事：
  - 输出 `message`
  - 输出 `criteria_chips`
  - 输出 `result_cards`
  - 输出 `suggested_actions`
- 完成后产物：
  - 前端拿到 JSON 后只渲染，不判断
- 对应原任务：
  - `D09`

#### 后端任务 9：实现资料详情页读模型

- 目标：候选卡片点进去后有正式详情承接页
- 要做的事：
  - 实现 profile detail read model
  - 返回详情页完整 render model
- 完成后产物：
  - 前端不用拿列表字段硬拼详情页
- 对应原任务：
  - `D10`

#### 后端任务 10：实现空结果持续留意

- 目标：空结果时，agent 可决定是否引导“持续留意”
- 要做的事：
  - 封装 saved search subscription tool
  - 记录用户 opt-in 动作
- 完成后产物：
  - 空结果时可真正创建订阅
- 对应原任务：
  - `D11`

#### 后端任务 11：支持 session 恢复

- 目标：刷新页面后还能恢复原来的发现页状态
- 要做的事：
  - 支持 session view 读取
  - 可选存 view snapshot
- 完成后产物：
  - 前端刷新后仍然只展示后端返回内容
- 对应原任务：
  - `D12`

#### 后端任务 12：补测试和观测

- 目标：保证 discovery system 可回归、可审计
- 要做的事：
  - 补 storage / service / fake agent 测试
  - 补 turn log / tool log / 指标
- 完成后产物：
  - 能追溯 agent 为什么给出某次结果
- 对应原任务：
  - `D14`
  - `D15`

### 7.2 网关任务

#### 网关任务 1：开放 discovery 接口

- 目标：给前端正式入口
- 要做的事：
  - `POST /v1/discovery/sessions`
  - `POST /v1/discovery/sessions/{session_id}/turns`
  - `GET /v1/discovery/sessions/{session_id}`
  - `GET /v1/discovery/profiles/{profile_id}`
- 完成后产物：
  - 前端可以不直接碰 discovery system 内部实现
- 对应原任务：
  - `D13`

#### 网关任务 2：补 discovery 接口契约

- 目标：把请求和返回 schema 定义清楚
- 要做的事：
  - 更新 API contract
  - 明确错误码
  - 明确 `action_id` 的使用方式
- 完成后产物：
  - 联调时前后端对同一套 JSON 说话
- 对应原任务：
  - `D01`
  - `D13`

### 7.3 前端联调任务

#### 前端联调任务 1：接发现页会话接口

- 目标：页面能创建 discovery session
- 要做的事：
  - 首次进入发现页时创建 session
  - 保存 `session_id`
- 注意：
  - 前端不判断欢迎语内容
  - 直接展示后端返回内容

#### 前端联调任务 2：接 turn 提交接口

- 目标：用户输入一句话后，可以拿到新一轮 render model
- 要做的事：
  - 提交 `user_message`
  - 渲染返回的 `message / chips / cards / actions`
- 注意：
  - 前端不判断这句话是不是搜索条件

#### 前端联调任务 3：接 action_id 点击接口

- 目标：用户点击建议按钮时，不传业务语义，只传 `action_id`
- 要做的事：
  - 点击按钮时回传 `action_id`
  - 渲染新返回的页面状态
- 注意：
  - 前端不要自己组装 refine 参数

#### 前端联调任务 4：接资料详情页

- 目标：候选卡片点击后进入资料详情页
- 要做的事：
  - 调 `GET /v1/discovery/profiles/{profile_id}`
  - 按 render model 展示详情
- 注意：
  - 前端不要自己拼 trust / verification 逻辑

#### 前端联调任务 5：接 session 恢复

- 目标：刷新后恢复 discovery 页面
- 要做的事：
  - 页面重开时调 `GET /v1/discovery/sessions/{session_id}`
  - 直接回显 session view
- 注意：
  - 前端不自己恢复聊天和卡片状态

---

## 8. 最简单排期版

如果只看“第一期先做什么”，就按下面 3 组来做。

### 第一组：先把主链路做通

- 后端任务 1
- 后端任务 2
- 后端任务 3
- 后端任务 4
- 后端任务 5
- 后端任务 6
- 后端任务 7
- 后端任务 8
- 网关任务 1
- 网关任务 2

做完后就能实现：

- 用户输入一句话
- GPT 红娘决定追问还是搜索
- 前端收到可展示 JSON

### 第二组：再补承接页和空结果

- 后端任务 9
- 后端任务 10
- 前端联调任务 4

做完后就能实现：

- 候选卡片点进详情页
- 空结果时支持持续留意

### 第三组：最后补恢复、测试、观测

- 后端任务 11
- 后端任务 12
- 前端联调任务 5

做完后就能实现：

- 刷新恢复
- 自动化回归
- agent 决策可审计

---

## 9. 按人分工版

如果现在要直接开工，建议按 4 个角色拆。

### 9.1 后端 A：发现系统主链路负责人

- 负责范围：
  - `partner-discovery-system` 骨架
  - discovery session / turn / action / search_run 存储
  - discovery agent runtime
  - `create_session(...)`
  - `process_turn(...)`
  - `get_session_view(...)`
  - session 恢复
  - 测试和观测主框架
- 主要对应任务：
  - 后端任务 1
  - 后端任务 2
  - 后端任务 3
  - 后端任务 7
  - 后端任务 11
  - 后端任务 12
- 交付物：
  - `external-systems/partner-discovery-system/discovery_system/storage.py`
  - `external-systems/partner-discovery-system/discovery_system/service.py`
  - `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`

### 9.2 后端 B：工具接入和视图模型负责人

- 负责范围：
  - discovery tool registry
  - `action_id` 机制
  - `partner-search` tool wrapper
  - render model / view adapter
  - 资料详情页 read model
  - 空结果持续留意 tool
- 主要对应任务：
  - 后端任务 4
  - 后端任务 5
  - 后端任务 6
  - 后端任务 8
  - 后端任务 9
  - 后端任务 10
- 交付物：
  - `external-systems/partner-discovery-system/discovery_system/view_models.py`
  - `external-systems/partner-discovery-system/discovery_system/service.py` 里的 tool 接入部分

### 9.3 网关负责人

- 负责范围：
  - discovery API 暴露
  - 请求参数校验
  - 返回 schema 固化
  - API contract 更新
- 主要对应任务：
  - 网关任务 1
  - 网关任务 2
- 交付物：
  - `external-systems/partner-http-gateway/gateway/app.py`
  - `external-systems/partner-http-gateway/API_CONTRACT.md`

### 9.4 前端负责人

- 负责范围：
  - 发现页接 session / turn / action_id
  - 资料详情页接 profile detail
  - session 恢复
  - 全程只做展示，不做业务判断
- 主要对应任务：
  - 前端联调任务 1
  - 前端联调任务 2
  - 前端联调任务 3
  - 前端联调任务 4
  - 前端联调任务 5
- 交付物：
  - 发现页联调版
  - 资料详情页联调版

---

## 10. 并行开工顺序

下面这版最适合直接排期。

### 第 1 批：可以立刻并行

- 后端 A：
  - 建 `partner-discovery-system`
  - 建 discovery 存储表和 storage layer
- 后端 B：
  - 定 render model
  - 定 `action_id` 数据结构
  - 定 tool registry 接口
- 网关：
  - 先写 discovery API contract 草案
- 前端：
  - 用 mock JSON 接发现页静态页面

这一批结束的标志：

- 大家对 discovery 的请求和返回 JSON 说的是同一套结构

### 第 2 批：后端主链路并行开发

- 后端 A：
  - 接 GPT agent runtime
  - 打通 `create_session(...)`
  - 打通 `process_turn(...)`
- 后端 B：
  - 接 `partner-search`
  - 接 `persona-memory-sync`
  - 把 history / state 信息改成上下文注入
  - 实现 view adapter
- 网关：
  - 开 `POST /v1/discovery/sessions`
  - 开 `POST /v1/discovery/sessions/{session_id}/turns`
- 前端：
  - 接创建 session
  - 接发送用户消息
  - 接渲染 `message / chips / cards / actions`

这一批结束的标志：

- 用户在发现页发一句话，系统能返回一轮真实可展示内容

### 第 3 批：补承接页和动作闭环

- 后端 B：
  - 完成 `action_id` 恢复语义
  - 完成资料详情页 read model
  - 完成持续留意 tool
- 网关：
  - 开 `GET /v1/discovery/profiles/{profile_id}`
  - 补 discovery 错误码
- 前端：
  - 接按钮点击只传 `action_id`
  - 接候选卡片跳详情页

这一批结束的标志：

- 卡片点击、按钮点击、空结果继续留意都能闭环

### 第 4 批：补恢复、测试、观测

- 后端 A：
  - session 恢复
  - fake agent 回归测试
  - turn / tool 审计日志
- 网关：
  - 开 `GET /v1/discovery/sessions/{session_id}`
- 前端：
  - 刷新恢复页面状态

这一批结束的标志：

- 发现页不是只能人工点通，而是可回归、可恢复、可审计

---

## 11. 最小团队排期建议

如果只有 3 个人，建议这样合并：

- 人员 1：后端主链路
  - 做后端 A 全部内容
- 人员 2：后端工具 + 网关
  - 做后端 B + 网关全部内容
- 人员 3：前端联调
  - 做全部前端联调任务

如果只有 2 个人，建议这样合并：

- 人员 1：后端
  - 后端 A + 后端 B + 网关
- 人员 2：前端
  - 前端联调全部内容

---

## 12. 直接可执行的第一周任务

如果明天就开工，第一周只做下面这些。

### 后端

- 建 `partner-discovery-system`
- 建 discovery 存储
- 接 discovery agent runtime
- 接 `partner-search`
- 打通 `create_session(...)`
- 打通 `process_turn(...)`
- 输出基础 render model

### 网关

- 开：
  - `POST /v1/discovery/sessions`
  - `POST /v1/discovery/sessions/{session_id}/turns`
- 写清楚请求和返回 schema

### 前端

- 接创建 session
- 接发送一句话
- 接渲染：
  - message
  - criteria chips
  - result cards
  - suggested actions

第一周做完的验收标准：

- 用户在发现页输入一句话
- 后端交给 GPT 红娘
- 红娘决定追问还是搜索
- 页面能展示返回结果

---

## 13. 接口请求与响应 JSON

这一节只回答 4 个问题：

1. 前端创建发现页 session 时传什么
2. 前端发一句话时传什么
3. 前端点建议按钮时传什么
4. 后端到底返回什么 JSON 给前端渲染

### 13.1 契约原则

- 前端只允许上传两种输入：
  - `user_message`
  - `action_id`
- 前端不允许上传：
  - `intent`
  - `refine_type`
  - `search_filters`
  - `should_search`
- 后端统一返回：
  - `trace_id`
  - `session`
  - `view`
- 前端只认 `view`，不认底层 tool 返回

### 13.2 通用返回结构

发现页主接口统一返回这个结构：

```json
{
  "trace_id": "trace-3f1d9d7c",
  "session": {
    "session_id": "discovery-session-001",
    "status": "active",
    "phase": "collecting_preferences",
    "updated_at": "2026-05-14T14:30:00+08:00"
  },
  "view": {
    "timeline": [],
    "criteria_chips": [],
    "suggested_actions": [],
    "composer": {
      "placeholder": "告诉红娘你的偏好，她会替你整理并搜索。",
      "disabled": false
    }
  }
}
```

字段解释：

- `session.status`
  - `active`
  - `closed`
- `session.phase`
  - `collecting_preferences`
  - `searching`
  - `results_shown`
  - `no_result`
- `view.timeline`
  - 按时间顺序渲染的页面内容
- `view.criteria_chips`
  - 当前已整理出的条件标签
- `view.suggested_actions`
  - 后端生成的可点按钮
- `view.composer`
  - 输入框展示配置

### 13.3 `timeline` JSON 结构

#### `assistant_message`

```json
{
  "item_type": "assistant_message",
  "item_id": "msg-a-001",
  "body": "先跟我说说你想找什么样的人，不用一次讲完整。"
}
```

#### `user_message`

```json
{
  "item_type": "user_message",
  "item_id": "msg-u-001",
  "body": "我在无锡，想找认真恋爱的女生。"
}
```

#### `result_group`

```json
{
  "item_type": "result_group",
  "item_id": "group-001",
  "title": "这一轮先给你看 3 位",
  "cards": [
    {
      "card_id": "candidate-1001",
      "profile_id": 1001,
      "title": "林知夏 29",
      "subtitle": "无锡 · 中学老师 · 硕士",
      "cover_image_url": "https://static.example.com/p/1001/cover.jpg",
      "match_score": 92,
      "trust_badges": ["真人照认证", "学历已核验"],
      "reason_summary": "目标一致、工作稳定、表达自然",
      "open_profile_action": {
        "type": "open_profile",
        "profile_id": 1001
      }
    }
  ]
}
```

### 13.4 `criteria_chips` JSON 结构

```json
[
  {"chip_id": "chip-city", "label": "无锡"},
  {"chip_id": "chip-goal", "label": "认真恋爱"},
  {"chip_id": "chip-prefer-1", "label": "工作稳定优先"}
]
```

### 13.5 `suggested_actions` JSON 结构

```json
[
  {
    "action_id": "act-002",
    "label": "只看无锡本地",
    "style": "secondary"
  },
  {
    "action_id": "act-003",
    "label": "真人认证以上",
    "style": "secondary"
  }
]
```

这里最关键的是：

- 前端只展示 `label`
- 前端点击后只回传 `action_id`
- 前端不知道这个按钮背后代表什么语义

### 13.6 创建 session

`POST /v1/discovery/sessions`

请求：

```json
{
  "requester_id": 70001,
  "profile_id": 10001
}
```

响应：

```json
{
  "trace_id": "trace-7c22b8ea",
  "session": {
    "session_id": "discovery-session-001",
    "status": "active",
    "phase": "collecting_preferences",
    "updated_at": "2026-05-14T14:30:00+08:00"
  },
  "view": {
    "timeline": [
      {
        "item_type": "assistant_message",
        "item_id": "msg-a-001",
        "body": "先跟我说说你想找什么样的人，不用一次讲完整。"
      }
    ],
    "criteria_chips": [],
    "suggested_actions": [
      {
        "action_id": "act-open-001",
        "label": "先从城市和年龄说起",
        "style": "primary"
      }
    ],
    "composer": {
      "placeholder": "告诉红娘你的偏好，她会替你整理并搜索。",
      "disabled": false
    }
  }
}
```

前端动作：

- 保存 `session_id`
- 直接渲染 `view`
- 不要自己生成欢迎语

### 13.7 发送一轮输入

`POST /v1/discovery/sessions/{session_id}/turns`

这个接口支持两种请求体，但一次只能传一种。

#### 情况 A：用户输入一句话

请求：

```json
{
  "user_message": "我在无锡，想找认真恋爱、最好工作稳定一点的女生。"
}
```

#### 情况 B：用户点击了建议按钮

请求：

```json
{
  "action_id": "act-002"
}
```

禁止这样传：

```json
{
  "intent": "refine_search",
  "filter_city": "无锡"
}
```

响应示例 1：agent 决定继续追问

```json
{
  "trace_id": "trace-cfd91a11",
  "session": {
    "session_id": "discovery-session-001",
    "status": "active",
    "phase": "collecting_preferences",
    "updated_at": "2026-05-14T14:31:00+08:00"
  },
  "view": {
    "timeline": [
      {
        "item_type": "user_message",
        "item_id": "msg-u-002",
        "body": "我在无锡，想找认真恋爱、最好工作稳定一点的女生。"
      },
      {
        "item_type": "assistant_message",
        "item_id": "msg-a-002",
        "body": "收到。你更在意年龄范围，还是更在意是否本地长期发展？"
      }
    ],
    "criteria_chips": [
      {"chip_id": "chip-city", "label": "无锡"},
      {"chip_id": "chip-goal", "label": "认真恋爱"},
      {"chip_id": "chip-prefer-1", "label": "工作稳定优先"}
    ],
    "suggested_actions": [
      {
        "action_id": "act-004",
        "label": "我更在意年龄范围",
        "style": "secondary"
      },
      {
        "action_id": "act-005",
        "label": "我更在意长期在无锡发展",
        "style": "secondary"
      }
    ],
    "composer": {
      "placeholder": "继续告诉红娘你的要求",
      "disabled": false
    }
  }
}
```

响应示例 2：agent 决定直接搜索并展示结果

```json
{
  "trace_id": "trace-d2a8290f",
  "session": {
    "session_id": "discovery-session-001",
    "status": "active",
    "phase": "results_shown",
    "updated_at": "2026-05-14T14:32:00+08:00"
  },
  "view": {
    "timeline": [
      {
        "item_type": "user_message",
        "item_id": "msg-u-003",
        "body": "我在无锡，想找认真恋爱、最好工作稳定一点的女生。"
      },
      {
        "item_type": "assistant_message",
        "item_id": "msg-a-003",
        "body": "我先按无锡、认真恋爱、工作稳定优先帮你缩一轮。"
      },
      {
        "item_type": "result_group",
        "item_id": "group-001",
        "title": "这一轮先给你看 3 位",
        "cards": [
          {
            "card_id": "candidate-1001",
            "profile_id": 1001,
            "title": "林知夏 29",
            "subtitle": "无锡 · 中学老师 · 硕士",
            "cover_image_url": "https://static.example.com/p/1001/cover.jpg",
            "match_score": 92,
            "trust_badges": ["真人照认证", "学历已核验"],
            "reason_summary": "目标一致、工作稳定、表达自然",
            "open_profile_action": {
              "type": "open_profile",
              "profile_id": 1001
            }
          }
        ]
      }
    ],
    "criteria_chips": [
      {"chip_id": "chip-city", "label": "无锡"},
      {"chip_id": "chip-goal", "label": "认真恋爱"},
      {"chip_id": "chip-prefer-1", "label": "工作稳定优先"}
    ],
    "suggested_actions": [
      {
        "action_id": "act-006",
        "label": "只看无锡本地",
        "style": "secondary"
      },
      {
        "action_id": "act-007",
        "label": "真人认证以上",
        "style": "secondary"
      }
    ],
    "composer": {
      "placeholder": "继续说你的要求，或点按钮让红娘继续筛",
      "disabled": false
    }
  }
}
```

前端动作：

- 不管是 `user_message` 还是 `action_id`
- 都只拿后端新的 `view` 覆盖渲染
- 不做追问/搜索判断

### 13.8 恢复当前 session

`GET /v1/discovery/sessions/{session_id}`

响应：

```json
{
  "trace_id": "trace-e0e2b6c9",
  "session": {
    "session_id": "discovery-session-001",
    "status": "active",
    "phase": "results_shown",
    "updated_at": "2026-05-14T14:35:00+08:00"
  },
  "view": {
    "timeline": [
      {
        "item_type": "assistant_message",
        "item_id": "msg-a-003",
        "body": "我先按无锡、认真恋爱、工作稳定优先帮你缩一轮。"
      },
      {
        "item_type": "result_group",
        "item_id": "group-001",
        "title": "这一轮先给你看 3 位",
        "cards": [
          {
            "card_id": "candidate-1001",
            "profile_id": 1001,
            "title": "林知夏 29",
            "subtitle": "无锡 · 中学老师 · 硕士",
            "cover_image_url": "https://static.example.com/p/1001/cover.jpg",
            "match_score": 92,
            "trust_badges": ["真人照认证", "学历已核验"],
            "reason_summary": "目标一致、工作稳定、表达自然",
            "open_profile_action": {
              "type": "open_profile",
              "profile_id": 1001
            }
          }
        ]
      }
    ],
    "criteria_chips": [
      {"chip_id": "chip-city", "label": "无锡"},
      {"chip_id": "chip-goal", "label": "认真恋爱"},
      {"chip_id": "chip-prefer-1", "label": "工作稳定优先"}
    ],
    "suggested_actions": [
      {
        "action_id": "act-006",
        "label": "只看无锡本地",
        "style": "secondary"
      }
    ],
    "composer": {
      "placeholder": "继续说你的要求，或点按钮让红娘继续筛",
      "disabled": false
    }
  }
}
```

前端动作：

- 页面重开后直接调用这个接口
- 不要自己恢复历史消息和卡片

### 13.9 资料详情页

`GET /v1/discovery/profiles/{profile_id}?session_id=discovery-session-001`

响应：

```json
{
  "trace_id": "trace-f4380f20",
  "profile_id": 1001,
  "detail_view": {
    "hero": {
      "name": "林知夏",
      "age": 29,
      "city": "无锡",
      "headline": "中学老师 · 硕士 · 认真恋爱"
    },
    "photo_gallery": [
      {
        "image_url": "https://static.example.com/p/1001/1.jpg"
      },
      {
        "image_url": "https://static.example.com/p/1001/2.jpg"
      }
    ],
    "verified_sections": [
      {
        "title": "已核验信息",
        "items": ["真人照认证", "学历已核验"]
      }
    ],
    "self_reported_sections": [
      {
        "title": "她的自我介绍",
        "items": ["平时作息规律，周末喜欢徒步和看展。"]
      }
    ],
    "caution_sections": [
      {
        "title": "你需要知道",
        "items": ["工作日回复可能偏晚。"]
      }
    ],
    "matchmaker_notes": [
      "和你这一轮条件的匹配点主要在生活稳定、城市一致、关系目标明确。"
    ]
  }
}
```

前端动作：

- 详情页只渲染 `detail_view`
- 不从列表卡片字段自己拼详情页

### 13.10 错误返回

统一错误结构建议如下：

```json
{
  "trace_id": "trace-err-001",
  "error_code": "DISCOVERY_ACTION_EXPIRED",
  "error_message": "action_id 已过期，请刷新当前发现页。",
  "retryable": true
}
```

建议先定义这几个 discovery 错误码：

- `DISCOVERY_SESSION_NOT_FOUND`
- `DISCOVERY_SESSION_CLOSED`
- `DISCOVERY_INVALID_TURN_INPUT`
- `DISCOVERY_ACTION_NOT_FOUND`
- `DISCOVERY_ACTION_EXPIRED`
- `DISCOVERY_PROFILE_NOT_FOUND`
- `DISCOVERY_RENDER_FAILED`

### 13.11 前后端联调时只看这条规则

前端联调时，永远只遵守这一条：

- 发送时：
  - 只发 `user_message` 或 `action_id`
- 展示时：
  - 只认后端返回的 `view` 或 `detail_view`

只要前端开始自己拼条件、自己判断按钮含义、自己决定要不要搜索，就说明这套契约被破坏了。
