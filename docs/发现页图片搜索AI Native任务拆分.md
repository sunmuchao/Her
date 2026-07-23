# 发现页图片搜索 AI Native 任务拆分

日期：2026-07-19

> 本文档把《[发现页图片搜索 AI Native 完整落地方案](./发现页图片搜索AI%20Native完整落地方案.md)》拆成可执行任务清单。
>
> 目标不是“继续补一个图片搜索功能”，而是把发现页图片能力重构成统一 discovery 多模态对话链路。
>
> 适用范围：发现页前端、discovery session、Gateway、discovery runtime、match domain、埋点、验收。

---

## 1. 总体说明

### 1.1 任务拆分原则

本任务清单遵循四条原则：

1. 先止血，再收口，再 Agent 化
2. 顶层先统一协议，再统一链路，再统一记忆
3. face/style/reference/hybrid 继续保留，但逐步降级为内部能力
4. 每个阶段都必须有独立验收标准，避免“大重构做到一半无法上线”

### 1.2 任务状态定义

- `未开始`：当前仓库中未看到明确实现
- `进行中`：已有部分骨架，但未形成完整可用主链路
- `已完成`：已有完整实现且符合本方案要求

### 1.3 当前总体判断

基于 2026-07-20 当前仓库代码，这个 AI Native 改造的总体状态可判断为：

- 第一阶段：`已完成`
- 第二阶段：`已完成`
- 第三阶段：`已完成`
- 第四阶段：`已完成`
- 第五阶段：`未开始`
- 第六阶段：`未开始`

原因：

1. 前端“图片挂输入框 + 微信式发送”已有基础
2. Gateway 和底层 photo search 能力已有基础
3. 第一阶段止血项已经全部落地，可稳定支撑当前发图入口
4. 统一 discovery 多模态 turn 主链路已经建好
5. visual session memory 已建好，支持“上一张图”“继续找”“细化一下”
6. 服务端 visual planner 已接管当前视觉搜索主决策，后续还可继续向更完整 Agent 编排演进

---

## 2. 总体阶段划分

| 阶段 | 名称 | 当前状态 | 目标 |
|------|------|---------|------|
| 第一阶段 | 止血与兼容层收口 | 已完成 | 先消除现有发图失败和模式冲突问题 |
| 第二阶段 | 统一 discovery 多模态 turn | 已完成 | 让图文消息进入同一条 discovery 主链路 |
| 第三阶段 | 视觉会话记忆 | 已完成 | 支持“上一张图”“继续找”“细化一下” |
| 第四阶段 | Agent 接管视觉搜索决策 | 已完成 | 真正做到系统自己决定怎么搜 |
| 第五阶段 | 工具层重构与旧链路降级 | 未开始 | 把旧模式接口降为内部兼容层 |
| 第六阶段 | 上线前验收、监控与旧入口清理准备 | 未开始 | 做好上线前观测、验证与清理准备 |

---

## 3. 第一阶段：止血与兼容层收口

### 3.1 阶段目标

先解决当前最明显的问题：

1. 上传图片后不能因为顶层 `mode` 不兼容而失败
2. 用户不能再频繁看到“你重新发一次”这类伪错误
3. 当前前端自然对话入口，要先变成一个稳定可用入口

### 3.2 任务清单

#### 3.2.1 `A1-001` 盘点当前发图主链路

- 状态：`已完成`
- 目标：
  - 梳理当前发现页图片发送链路从前端到 Gateway 到 search service 的完整执行路径
  - 输出真实分支图和错误分支图
- 涉及文件：
  - [`frontend/her-app/components/her/discover-page.tsx`](../frontend/her-app/components/her/discover-page.tsx)
  - [`frontend/her-app/lib/api/endpoints/discovery.ts`](../frontend/her-app/lib/api/endpoints/discovery.ts)
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- 交付物：
  - 一份链路说明补充到实施进展或技术记录中
  - 已产出：[发现页图片发送链路梳理 A1-001](./发现页图片发送链路梳理_A1-001.md)
- 验收：
  - 能明确回答“发图失败时，当前失败在前端、Gateway 还是 match_domain”

#### 3.2.2 `A1-002` 兼容 `auto`，消除当前协议级失败

- 状态：`已完成`
- 目标：
  - 在兼容期内恢复 `mode=auto` 可用
  - 不再因 `auto` 被拒绝导致整条请求失败
- 涉及文件：
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
  - [`match_domain/photo_intent_agent.py`](../match_domain/photo_intent_agent.py)
- 依赖：
  - `A1-001`
- 实施要求：
  - `auto` 默认不再抛 `invalid_mode`
  - `auto` 优先落到 `hybrid`
  - 同时保留后续 Agent 接管的扩展点
- 验收：
  - 上传图片直接发送时，不再因为 `mode` 失败
- 当前落地结果：
  - Gateway 顶层已接受 `auto`
  - `auto` 当前会映射为 `PhotoPreferenceIntent(mode="hybrid")`
  - 已补最小测试覆盖 `auto -> hybrid`
  - 验证命令：
    - `PYTHONPATH=/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway:/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system python3 -m pytest tests/test_discovery_routes_list_sessions.py -k "photo_search_auto_mode_defaults_to_hybrid or photo_search_requires_image_for_face_mode or photo_search_returns_enriched_candidates"`

#### 3.2.3 `A1-003` 统一第一轮处理中话术

- 状态：`已完成`
- 目标：
  - 删除当前“按脸找 / 按感觉找”的前台预判话术
  - 统一成自然处理中提示
- 涉及文件：
  - [`frontend/her-app/components/her/discover-page.tsx`](../frontend/her-app/components/her/discover-page.tsx)
- 实施要求：
  - 处理中提示不暴露模式
  - 不再让前台替后台做策略解释
- 验收：
  - 用户发图后只看到自然消息，不看到模式预判
- 当前落地结果：
  - 发图后的处理中提示已统一为：
    - `收到，我先看看这张图。`
  - 前端不再在这一轮处理中消息里暴露 `按脸 / 按感觉 / 参考人物` 的模式解释

#### 3.2.4 `A1-004` 错误提示分层

- 状态：`已完成`
- 目标：
  - 把当前统一错误文案，拆成真实错误分层
- 涉及文件：
  - [`frontend/her-app/components/her/discover-page.tsx`](../frontend/her-app/components/her/discover-page.tsx)
  - [`frontend/her-app/lib/api/client.ts`](../frontend/her-app/lib/api/client.ts)
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- 错误分类至少包括：
  - 图片读取失败
  - 参数不合法
  - 搜索为空
  - 服务繁忙
- 验收：
  - 不再所有失败都统一显示“你重新发一次”
- 当前落地结果：
  - 前端提交图片搜索失败后，已不再统一显示“你重新发一次”
  - 当前已分层为至少四类用户提示：
    - 图片格式不支持
    - 图片体积过大
    - 请求参数不完整或不合法
    - 服务繁忙或后端暂时不可用
  - Gateway 图片搜索错误响应已补充稳定字段：
    - `error.code`
    - `error_message`
    - `retryable`
  - `profile_source_missing` 和运行时异常已改为 `503`，避免误判成用户重发即可解决的问题
  - “搜索为空”继续按正常成功分支处理，不再算失败；前端会提示：
    - `这次我还没找到特别贴的，你可以换张图，或者补一句更明确的描述。`
  - 验证命令：
    - `PYTHONPATH=/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway:/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system python3 -m pytest tests/test_discovery_routes_list_sessions.py -k "photo_search_requires_image_for_face_mode or photo_search_returns_retryable_error_when_profile_source_missing or photo_search_returns_retryable_error_when_search_runtime_fails or photo_search_auto_mode_defaults_to_hybrid"`
    - `pnpm vitest run tests/unit/api-errors.test.ts`

#### 3.2.5 `A1-005` 补第一阶段监控

- 状态：`已完成`
- 目标：
  - 监控“有图消息发送成功率”和“photo search 成功率”
- 涉及文件：
  - [`observability/photo_search_metrics.py`](../observability/photo_search_metrics.py)
  - [`external-systems/partner-http-gateway/gateway/ops_routes.py`](../external-systems/partner-http-gateway/gateway/ops_routes.py)
- 验收：
  - 能区分：
    - 请求没进 Gateway
    - Gateway 拒绝
    - 搜索失败
    - 搜索为空
- 当前落地结果：
  - `observability/photo_search_metrics.py` 已新增图片搜索漏斗分层能力
  - 当前 dashboard 会直接输出：
    - `request_not_entered_gateway`
    - `gateway_rejected`
    - `search_failed`
    - `search_empty`
    - `search_succeeded`
  - Gateway 图片搜索入口已补事件埋点：
    - `gateway_received`
    - `gateway_rejected`
    - `search_runtime_failed`
    - `results_ready`
    - `empty_result`
  - `/v1/ops/photo-search/dashboard` 现在会返回 `funnel` 结构，方便 ops 直接看分段问题，不用再自己读散点事件
  - 验证命令：
    - `python3 -m pytest tests/test_photo_search_metrics.py`
    - `PYTHONPATH=/Users/sunmuchao/Downloads/Her:/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway:/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system:/Users/sunmuchao/Downloads/Her/external-systems/partner-matchmaking-system python3 -m pytest tests/test_ops_routes.py tests/test_discovery_routes_list_sessions.py -k "photo_search"`
  - 验证说明：
    - 与 `A1-005` 直接相关的 photo search 监控与 gateway 测试已通过
    - 同批选择运行时有 1 条旧链路测试失败，原因是 discovery 建会话时继续依赖缺失的 `chat_system` 模块，与本次图片搜索监控改动无关

### 3.3 第一阶段验收

满足以下条件即通过：

1. 上传图片直接发送，不再因为 `mode` 失败
2. 用户错误提示不再统一“重发一次”
3. 能从埋点上看出请求是失败在入口、路由还是搜索

当前结论：`第一阶段已完成`

---

## 4. 第二阶段：统一 discovery 多模态 turn

### 4.1 阶段目标

把当前“图片搜索请求”和“普通对话请求”收成一条 discovery 主链路。

### 4.2 任务清单

#### 4.2.1 `A2-001` 设计统一多模态 turn schema

- 状态：`已完成`
- 目标：
  - 明确 discovery turn 的统一请求结构
- 目标结构：
  - `session_id`
  - `message.text`
  - `message.attachments[]`
  - `client_context`
- 涉及文件：
  - [`frontend/her-app/lib/api/endpoints/discovery.ts`](../frontend/her-app/lib/api/endpoints/discovery.ts)
  - [`frontend/her-app/lib/types/discovery.ts`](../frontend/her-app/lib/types/discovery.ts)
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- 验收：
  - 形成稳定 schema，且不再以 `mode` 为顶层字段
- 当前落地结果：
  - 统一 turn 请求结构已落地为：
    - `session_id`
    - `message.text`
    - `message.attachments[]`
    - `client_context`
  - 图片搜索模式不再作为顶层字段发送
  - `mode / celebrity_name / top_k / filters` 已下沉到 `client_context.intent_hint` 与 `client_context` 中
  - 相关文件：
    - `frontend/her-app/lib/types/discovery.ts`
    - `frontend/her-app/lib/api/endpoints/discovery.ts`
    - `external-systems/partner-http-gateway/gateway/discovery_routes.py`

#### 4.2.2 `A2-002` 新增统一 discovery turn Gateway 入口

- 状态：`已完成`
- 目标：
  - 新增或改造 `POST /v1/discovery/turns`
  - 支持 `text + attachments`
- 涉及文件：
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- 依赖：
  - `A2-001`
- 验收：
  - Gateway 能接受一条带图 discovery 消息
- 当前落地结果：
  - Gateway 已新增 `POST /v1/discovery/turns`
  - `POST /v1/discovery/sessions/{id}/turns` 也已兼容接收统一 schema
  - Gateway 现在会把统一 body 转给 discovery service 的多模态 turn 入口
  - 已补 gateway 路由测试覆盖带图 turn 分发

#### 4.2.3 `A2-003` 前端统一提交入口

- 状态：`已完成`
- 目标：
  - 让发现页图文消息和纯文本消息最终汇流到同一个 `submitTurn`
- 涉及文件：
  - [`frontend/her-app/hooks/use-discovery-session.ts`](../frontend/her-app/hooks/use-discovery-session.ts)
  - [`frontend/her-app/components/her/discover-page.tsx`](../frontend/her-app/components/her/discover-page.tsx)
- 依赖：
  - `A2-001`
  - `A2-002`
- 实施要求：
  - 允许 `submitTurn({ text, attachments })`
  - 兼容旧调用方式
- 验收：
  - 发纯文本和发图，前端最终走同一类 turn API
- 当前落地结果：
  - `useDiscoverySession.submitTurn(...)` 已支持：
    - `text`
    - `attachments`
    - `clientContext`
  - 同时保留旧参数兼容：
    - `user_message`
    - `action_id`
  - 发现页发纯文本和发图现在都走 `submitDiscoveryTurn -> /v1/discovery/turns`
  - `discover-page.tsx` 已不再直接依赖独立 `/photo-search` 作为主发送入口
  - 已补前端接口层单测，验证统一 payload 确实发到新 endpoint

#### 4.2.4 `A2-004` 后端统一多模态 turn 编排函数

- 状态：`已完成`
- 目标：
  - 在 discovery service 层增加统一入口
- 建议函数：
  - `process_discovery_multimodal_turn(...)`
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/service.py`](../external-systems/partner-discovery-system/discovery_system/service.py)
  - [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
- 依赖：
  - `A2-002`
- 验收：
  - 后端对“带图消息”不再走独立 ad-hoc 分支
- 当前落地结果：
  - discovery service 已新增统一入口：
    - `process_multimodal_turn(...)`
  - service 内部现在会：
    - 识别文本 turn
    - 识别图片附件 turn
    - 对纯文本自动回落到原有 `process_turn(...)`
    - 对带图消息统一走 service 内部多模态搜索编排
  - service 处理成功后会直接写入 session timeline、turn 记录和 view snapshot
  - 已补 discovery service 多模态单测

#### 4.2.5 `A2-005` 兼容旧 `/photo-search` 调用

- 状态：`已完成`
- 目标：
  - 保留兼容期，不打断现有接口
  - 但明确旧接口只作为兼容层
- 涉及文件：
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- 验收：
  - 旧前端可用
  - 新链路默认走统一 turn
- 当前落地结果：
  - 新前端默认已走统一 turn 主链路
  - 旧 `/v1/discovery/photo-search` 仍保留
  - 当旧接口带 `session_id` 调用时，已退化为兼容转发层：
    - 内部转到统一多模态 turn
    - 对外继续返回兼容结构
  - 当旧接口不带 `session_id` 时，仍保留原有独立返回能力，避免兼容期外部调用被打断

### 4.3 第二阶段验收

满足以下条件即通过：

1. 带图消息和纯文本消息进入统一 discovery turn 主链路
2. 前端不再依赖独立图片搜索请求才能发图
3. `/photo-search` 退为兼容层而不是产品主入口

当前结论：`第二阶段已完成`

验证命令：

- `PYTHONPATH=/Users/sunmuchao/Downloads/Her:/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system python3 -m pytest tests/test_multimodal_turns.py`
- `PYTHONPATH=/Users/sunmuchao/Downloads/Her:/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway:/Users/sunmuchao/Downloads/Her/external-systems/partner-discovery-system python3 -m pytest tests/test_discovery_routes_list_sessions.py -k "dispatch_photo_search or multimodal_turn or photo_search"`
- `pnpm vitest run tests/unit/api-errors.test.ts tests/unit/discovery-endpoints.test.ts`

验证说明：

- A2 相关 Python 和前端单测已通过
- `pnpm exec tsc --noEmit` 暴露出仓库中其他页面与旧测试文件的既有类型问题，未指向本次 A2 改动链路

---

## 5. 第三阶段：视觉会话记忆

### 5.1 阶段目标

让系统真正记住“当前正在参考哪张图、刚刚按什么方向找过、上一轮结果是什么”。

### 5.2 任务清单

#### 5.2.1 `A3-001` 设计 `visual_context` session memory schema

- 状态：`已完成`
- 目标：
  - 为 discovery session 增加 `visual_context`
- 建议字段：
  - `active_reference_image`
  - `active_visual_intent`
  - `active_constraints`
  - `last_result_group_id`
  - `last_result_profile_ids`
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/agent_session_store.py`](../external-systems/partner-discovery-system/discovery_system/agent_session_store.py)
  - [`external-systems/partner-discovery-system/discovery_system/view_models.py`](../external-systems/partner-discovery-system/discovery_system/view_models.py)
- 验收：
  - schema 定义清晰，支持后续读写
 - 完成说明：
  - 已在 discovery session `state["visual_context"]` 中落地标准结构
  - 已补充标准化 helper，统一约束 `active_reference_image / active_visual_intent / active_constraints / last_result_*`

#### 5.2.2 `A3-002` 写入最近参考图

- 状态：`已完成`
- 目标：
  - 每次带图 turn 成功处理后，把当前图片写入 `visual_context`
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/service.py`](../external-systems/partner-discovery-system/discovery_system/service.py)
  - [`external-systems/partner-discovery-system/discovery_system/agent_session_store.py`](../external-systems/partner-discovery-system/discovery_system/agent_session_store.py)
- 依赖：
  - `A3-001`
- 验收：
  - session 中可读出当前 active reference image
 - 完成说明：
  - 每次图片搜索成功后，都会把当前 reference image 写回 `visual_context.active_reference_image`
  - `session payload` 和 `runtime_context` 都能读到 compact visual context

#### 5.2.3 `A3-003` 写入最近视觉意图与约束

- 状态：`已完成`
- 目标：
  - 把本轮 visual intent 摘要、hard filters、结果组引用写入 session memory
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/service.py`](../external-systems/partner-discovery-system/discovery_system/service.py)
- 依赖：
  - `A3-001`
- 验收：
  - 能读出“上一轮按什么逻辑搜、加了什么约束”
 - 完成说明：
  - 已写入最近 visual intent、hard filters、style keywords、refinement texts、结果组 ID 和 profile IDs
  - 运行时上下文已暴露 `visual_context`，后续 Agent 可直接消费

#### 5.2.4 `A3-004` 识别“上一张图引用”

- 状态：`已完成`
- 目标：
  - 识别以下自然表达：
    - `刚才那张`
    - `上面那张图`
    - `还是这种感觉`
    - `按那张继续找`
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
  - [`match_domain/photo_intent_agent.py`](../match_domain/photo_intent_agent.py)
- 依赖：
  - `A3-001`
  - `A3-002`
  - `A3-003`
- 验收：
  - 用户不重发图，只说“还是刚才那张那种”，系统也能继续搜索
 - 完成说明：
  - 已在 discovery service 识别 `刚才那张 / 上面那张图 / 这种感觉 / 按那张继续找` 等续搜表达
  - 若当前 turn 无附件，会自动复用 session 中最近参考图继续走图片搜索链路

#### 5.2.5 `A3-005` 支持 refinement

- 状态：`已完成`
- 目标：
  - 把这类请求识别成上一轮视觉搜索 refinement：
    - `不要太成熟`
    - `温柔一点`
    - `换成上海`
    - `长发一点`
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
  - [`match_domain/photo_intent_agent.py`](../match_domain/photo_intent_agent.py)
- 依赖：
  - `A3-004`
- 验收：
  - refinement 不再被当成全新、无上下文的一轮普通对话
 - 完成说明：
  - 已支持 `不要太成熟 / 温柔一点 / 换成上海 / 长发一点` 这类 refinement
  - 服务端会在上一轮 visual context 基础上合并约束，再次执行图片搜索

### 5.3 第三阶段验收

满足以下条件即通过：

1. session memory 中正式存在 visual context
2. 用户说“上一张图”“刚才那张”时，系统能正确复用 reference
3. 用户补充“成熟一点/城市换成上海”时，系统会在上一轮基础上 refinement

验证说明：

- 已新增 discovery service 单测，覆盖：
  - 首次带图搜索后写入 `visual_context`
  - 无需重传图片的 follow-up 视觉搜索
  - refinement 约束合并与 reference image 复用

---

## 6. 第四阶段：Agent 接管视觉搜索决策

### 6.1 阶段目标

让“怎么搜、要不要追问、调用哪些能力”真正由 Agent 决策，而不是 Gateway 或前端模式分流。

### 6.2 任务清单

#### 6.2.1 `A4-001` 定义 Agent 视觉搜索决策输出 schema

- 状态：`已完成`
- 目标：
  - 定义 Agent 每轮必须输出的结构化计划
- 建议字段：
  - `turn_type`
  - `should_search_now`
  - `should_ask_clarifying_question`
  - `resolved_visual_plan`
  - `assistant_summary`
  - `follow_up_suggestions`
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/decision_models.py`](../external-systems/partner-discovery-system/discovery_system/decision_models.py)
  - [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
- 验收：
  - 有稳定结构化 plan，而不是散落在自然语言里的临时判断
 - 完成说明：
  - 已新增 `VisualSearchDecisionPayloadModel` 与 `VisualResolvedPlanModel`
  - 结构化字段覆盖 `turn_type / should_search_now / should_ask_clarifying_question / resolved_visual_plan / assistant_summary / follow_up_suggestions`

#### 6.2.2 `A4-002` 接入 visual plan builder

- 状态：`已完成`
- 目标：
  - 将当前 `PhotoPreferenceIntent` 相关能力升级为 Agent 可调用视觉计划构建器
- 涉及文件：
  - [`match_domain/photo_intent_agent.py`](../match_domain/photo_intent_agent.py)
- 依赖：
  - `A4-001`
- 验收：
  - Agent 能获得稳定 visual plan，而非直接依赖旧模式字段
 - 完成说明：
  - 已在 `match_domain/photo_intent_agent.py` 落地 `build_visual_search_plan`
  - discovery runtime 已挂载同名工具，后续 Agent 可直接取计划，不必再依赖旧 `mode` 字段

#### 6.2.3 `A4-003` 默认策略切到 Agent 决策

- 状态：`已完成`
- 目标：
  - 用户只发图时，由 Agent 决定 `hybrid` / `face-first` / `style-first`
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
  - [`match_domain/photo_discovery_search.py`](../match_domain/photo_discovery_search.py)
- 依赖：
  - `A4-002`
- 验收：
  - 顶层不再靠前端或 Gateway 指定模式
 - 完成说明：
  - `process_multimodal_turn` / `_run_photo_search_turn` 已改为先构建 visual plan，再决定 `hybrid / face / style / celebrity`
  - 用户只发图时，默认由服务端 visual planner 决定搜索策略，前端 `mode` 只作为 hint

#### 6.2.4 `A4-004` 增加追问判断能力

- 状态：`已完成`
- 目标：
  - 对以下情况允许 Agent 先追问：
    - 图片质量差
    - 当前表达过于模糊
    - 没有可用 reference
    - 条件冲突
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
- 依赖：
  - `A4-001`
- 验收：
  - 必要时系统会先问一句，而不是盲搜或乱搜
 - 完成说明：
  - 当用户说的是视觉续搜/视觉意图，但当前没有可用 reference 时，系统会先追问
  - 已覆盖 `还是这种感觉` 这类无图无上下文场景

#### 6.2.5 `A4-005` 输出自然解释与下一步建议

- 状态：`已完成`
- 目标：
  - 搜索完成后，由 Agent 输出自然总结和 refinement 建议
- 涉及文件：
  - [`match_domain/photo_intent_agent.py`](../match_domain/photo_intent_agent.py)
  - [`external-systems/partner-discovery-system/discovery_system/view_models.py`](../external-systems/partner-discovery-system/discovery_system/view_models.py)
- 依赖：
  - `A4-001`
- 验收：
  - 助手消息不再像工具执行日志，而更像红娘自然回复
 - 完成说明：
  - 已新增 `build_visual_search_result_summary`
  - 搜索结果回复会自动带自然化总结和下一步 refinement 提示

### 6.3 第四阶段验收

满足以下条件即通过：

1. 视觉搜索策略由 Agent 决定
2. 必要时会追问，而不是一律直接搜
3. 搜索结果和后续建议由 Agent 自然生成

验证说明：

- 已新增/更新 discovery multimodal 单测，覆盖：
  - 仅上传图片时由服务端 planner 默认选择策略
  - 续搜 refinement 继续沿用上一轮 visual context
  - 无 reference 的视觉请求先追问而非误搜

---

## 7. 第五阶段：工具层重构与旧链路降级

### 7.1 阶段目标

把现有 face/style/reference/hybrid 从“顶层业务模式”降级成“内部能力工具”。

### 7.2 任务清单

#### 7.2.1 `A5-001` 定义视觉能力型工具集

- 状态：`已完成`
- 目标：
  - 按能力重组工具，而不是按模式重组工具
- 工具集合建议：
  - `load_recent_visual_context`
  - `build_visual_search_plan`
  - `parse_visual_user_intent`
  - `search_face_similarity_candidates`
  - `search_style_similarity_candidates`
  - `search_reference_person_candidates`
  - `apply_candidate_hard_filters`
  - `rerank_visual_candidates`
  - `persist_visual_search_memory`
  - `resolve_direct_image_urls`
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
  - [`external-systems/partner-discovery-system/discovery_system/service_integrations.py`](../external-systems/partner-discovery-system/discovery_system/service_integrations.py)
- 完成说明：
  - 已在 Agent Runtime 挂出能力型工具，而不是直接把 face/style/hybrid 当成顶层协议。
  - 工具职责已经拆成“读上下文”“解析意图”“搜候选人”“过滤/重排”“沉淀记忆”几类。
- 验收：
  - Agent 可见的是能力集合，而不是业务模式集合

#### 7.2.2 `A5-002` 保留底层 face/style/hybrid/reference 搜索函数

- 状态：`已完成`
- 目标：
  - 明确底层能力继续保留，不推倒重写
  - 但不再让它们成为顶层协议边界
- 涉及文件：
  - [`match_domain/photo_discovery_search.py`](../match_domain/photo_discovery_search.py)
- 完成说明：
  - 底层搜索函数继续保留，避免重写已有 face/style/reference/hybrid 搜索能力。
  - 已补充模块说明，明确这些函数现在是内部能力层，由 discovery service / agent tools 组合调用。
- 验收：
  - 底层函数仍能独立测试
  - 顶层不再直接以模式调用它们

#### 7.2.3 `A5-003` 把 `/photo-search` 降级为内部兼容层

- 状态：`已完成`
- 目标：
  - 明确旧接口角色变化
- 涉及文件：
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- 依赖：
  - `A2-005`
  - `A5-001`
- 完成说明：
  - `/photo-search` 带 `session_id` 时，已改为转发到统一的 multimodal turn 链路。
  - `/photo-search` 返回体已显式打上 `compatibility_mode=legacy_photo_search_route` 和 `route_role=compatibility_layer`。
  - 新增 `/v1/discovery/turns` 作为统一 discovery turn 入口，新功能不再围绕旧 `/photo-search` 扩展。
- 验收：
  - 新功能不再围绕 `/photo-search` 扩展
  - `/photo-search` 只承担旧版本兼容与内部 fallback

#### 7.2.4 `A5-004` 统一 timeline 构建

- 状态：`已完成`
- 目标：
  - 把视觉搜索结果和普通聊天结果统一映射到 discovery timeline
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/view_models.py`](../external-systems/partner-discovery-system/discovery_system/view_models.py)
  - [`frontend/her-app/lib/discovery/map-discovery-view.ts`](../frontend/her-app/lib/discovery/map-discovery-view.ts)
- 完成说明：
  - 后端已抽出 `build_visual_search_timeline_entries(...)`，统一生产用户图文消息、助手解释和结果组。
  - 前端 timeline 映射已抽成统一的 `mapDiscoveryTimelineItem(...)`，视觉搜索结果和普通对话共用一套转换逻辑。
- 验收：
  - 结果组、用户图文消息、助手解释、建议按钮都走统一 view model

### 7.3 第五阶段验收

满足以下条件即通过：

1. face/style/reference/hybrid 不再是顶层接口设计
2. Agent 看到的是工具能力，而不是模式路由表
3. timeline 统一收口
4. `/photo-search` 只保留兼容层角色，统一 turn 入口已经切到 `/v1/discovery/turns`

---

## 8. 第六阶段：上线前验收、监控与旧入口清理准备

### 8.1 阶段目标

在正式上线前，把 AI Native 链路的监控、验收、测试和旧入口清理准备做好。

### 8.2 任务清单

#### 8.2.1 `A6-001` 新旧链路埋点对比

- 状态：`已完成`
- 目标：
  - 区分旧 `/photo-search` 链路和新 unified turn 链路
- 涉及文件：
  - [`observability/photo_search_metrics.py`](../observability/photo_search_metrics.py)
  - [`external-systems/partner-http-gateway/gateway/ops_routes.py`](../external-systems/partner-http-gateway/gateway/ops_routes.py)
- 完成说明：
  - 旧 `/photo-search` 和新 `/v1/discovery/turns` 都补上了 `entrypoint` / `route_kind` 埋点字段。
  - photo-search dashboard 已新增 `route_comparison`，可以直接对比 legacy compatibility route 和 unified discovery turn。
- 验收：
  - 验收环境或联调面板里能看出新旧链路对比

#### 8.2.2 `A6-002` 补关键业务指标

- 状态：`已完成`
- 目标：
  - 增加这些指标：
    - 带图 turn 成功率
    - 引用上一张图识别成功率
    - refinement 成功率
    - 首轮出结果率
    - 无结果后二次交互率
- 完成说明：
  - dashboard 已新增 `key_metrics`：
    - `image_turn_success_rate`
    - `reuse_reference_success_rate`
    - `refinement_success_rate`
    - `first_turn_result_rate`
    - `empty_result_followup_rate`
  - unified turn 链路已补发 `has_image`、`reused_reference_image`、`is_refinement`、`is_first_visual_turn`、`follows_empty_result` 等事件维度。
- 验收：
  - 指标可在上线前联调环境中稳定观测

#### 8.2.3 `A6-003` 预留上线切换点，但暂不做灰度

- 状态：`已完成`
- 目标：
  - 明确未来正式上线时的切换位置，但当前阶段不实现灰度分桶
  - 确保：
    - 旧链路入口位置清晰
    - 新 unified turn 入口位置清晰
    - Agent 决策入口位置清晰
- 涉及文件：
  - Gateway 路由层
  - discovery runtime 配置
- 完成说明：
  - gateway 路由层已明确：
    - 主入口：`/v1/discovery/turns`
    - 兼容入口：`/v1/discovery/photo-search`
  - dashboard 已新增 `switchpoints`，明确网关切换点和 Agent 决策入口。
  - 当前实现只保留切换位，不引入灰度分桶复杂度。
- 验收：
  - 文档和代码里能明确看出未来切换点
  - 当前实现不引入多余灰度复杂度

#### 8.2.4 `A6-004` 补完整测试矩阵

- 状态：`已完成`
- 目标：
  - 补至少以下测试：
    - 只发图
    - 发图加一句话
    - 先发图再说“按刚才那张找”
    - refinement
    - 图片损坏
    - 搜索为空
    - Gateway fallback
    - 无 reference 时先追问
- 涉及文件：
  - 前端单测 / e2e
  - Gateway 测试
  - discovery runtime 测试
- 完成说明：
  - discovery runtime 已补：
    - 只发图
    - 发图加一句话
    - 先发图再说“按刚才那张找”
    - refinement
    - 图片损坏
    - 搜索为空
    - 无 reference 时先追问
  - gateway 已补：
    - `/v1/discovery/turns` 只发图
    - `/v1/discovery/sessions/{id}/turns` fallback 到 multimodal turn
    - `/photo-search` 空结果兼容返回
- 验收：
  - 关键视觉会话场景都有自动化覆盖

#### 8.2.5 `A6-005` 下线旧前台模式残留

- 状态：`已完成`
- 目标：
  - 清理所有前台模式遗留文案、状态名、注释与入口
- 涉及文件：
  - 发现页前端
  - 相关设计文档
- 依赖：
  - 前五阶段稳定通过
- 完成说明：
  - 发现页前端已去掉 `photoSearchMode` 状态，不再向用户暴露“按脸找 / 按感觉找 / 按明星找”的前台模式心智。
  - 图片发送入口统一改成“上传图片 + 可补一句话 + 后端自动理解”的交互。
  - 前端已不再直接调用旧 `/photo-search` 作为主链路。
- 验收：
  - 用户侧已完全感知不到“按脸找 / 按感觉找 / 按明星找”的模式心智

### 8.3 第六阶段验收

满足以下条件即通过：

1. 指标可观测
2. 新旧链路可比较
3. 上线前测试矩阵基本补齐
4. 用户侧旧模式心智基本清理完成
5. 未来正式上线时的切换点已经明确，但当前不额外引入灰度复杂度
6. 空结果、追问、复用上一张图、refinement 等关键视觉会话都能单独观测

---

## 9. 涉及文件总表

### 9.1 前端

- [`frontend/her-app/components/her/discover-page.tsx`](../frontend/her-app/components/her/discover-page.tsx)
- [`frontend/her-app/hooks/use-discovery-session.ts`](../frontend/her-app/hooks/use-discovery-session.ts)
- [`frontend/her-app/lib/api/endpoints/discovery.ts`](../frontend/her-app/lib/api/endpoints/discovery.ts)
- [`frontend/her-app/lib/types/discovery.ts`](../frontend/her-app/lib/types/discovery.ts)
- [`frontend/her-app/lib/discovery/map-discovery-view.ts`](../frontend/her-app/lib/discovery/map-discovery-view.ts)
- [`frontend/her-app/lib/api/client.ts`](../frontend/her-app/lib/api/client.ts)

### 9.2 Gateway

- [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- [`external-systems/partner-http-gateway/gateway/ops_routes.py`](../external-systems/partner-http-gateway/gateway/ops_routes.py)

### 9.3 Discovery Runtime

- [`external-systems/partner-discovery-system/discovery_system/service.py`](../external-systems/partner-discovery-system/discovery_system/service.py)
- [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
- [`external-systems/partner-discovery-system/discovery_system/agent_session_store.py`](../external-systems/partner-discovery-system/discovery_system/agent_session_store.py)
- [`external-systems/partner-discovery-system/discovery_system/decision_models.py`](../external-systems/partner-discovery-system/discovery_system/decision_models.py)
- [`external-systems/partner-discovery-system/discovery_system/view_models.py`](../external-systems/partner-discovery-system/discovery_system/view_models.py)
- [`external-systems/partner-discovery-system/discovery_system/service_integrations.py`](../external-systems/partner-discovery-system/discovery_system/service_integrations.py)

### 9.4 Match Domain / Search

- [`match_domain/photo_discovery_search.py`](../match_domain/photo_discovery_search.py)
- [`match_domain/photo_intent_agent.py`](../match_domain/photo_intent_agent.py)
- [`observability/photo_search_metrics.py`](../observability/photo_search_metrics.py)

---

## 10. 关键路径

最短可上线关键路径如下：

```text
第一阶段（止血与兼容）
    ->
第二阶段（统一 discovery turn）
    ->
第三阶段（visual session memory）
    ->
第四阶段（Agent 接管视觉搜索决策）
    ->
第六阶段（灰度与验收）
```

第五阶段不是最早上线阻塞项，但它决定架构是否真正 AI Native 化，不能长期拖着不做。

---

## 11. 任务统计

### 11.1 数量统计

| 阶段 | 任务数 |
|------|-------|
| 第一阶段 | 5 |
| 第二阶段 | 5 |
| 第三阶段 | 5 |
| 第四阶段 | 5 |
| 第五阶段 | 4 |
| 第六阶段 | 5 |
| **总计** | **29** |

### 11.2 建议排期

按 2 到 3 人并行估算：

| 阶段 | 建议周期 |
|------|---------|
| 第一阶段 | 3 到 5 天 |
| 第二阶段 | 4 到 6 天 |
| 第三阶段 | 4 到 6 天 |
| 第四阶段 | 5 到 8 天 |
| 第五阶段 | 4 到 6 天 |
| 第六阶段 | 4 到 6 天 |
| **总计** | **24 到 37 天** |

这是假设现有 discovery runtime 和 photo search 基础能力可复用的前提下的估算。

---

## 12. 最终验收口径

只有同时满足下面六条，才算本次 AI Native 改造真正完成：

1. 用户上传图片后，前台只有自然对话入口，没有模式入口
2. 图文消息与纯文本消息进入统一 discovery turn 主链路
3. system session memory 中正式存在 visual context
4. 用户可自然引用“上一张图”并继续 refinement
5. 视觉搜索策略由 Agent 决定，而不是顶层模式字段决定
6. 旧 `/photo-search` 链路已降为兼容层，不再主导产品形态

一句话总结：

**这 29 个任务做完，系统才算从“自然对话外观”真正进化成“AI Native 内核”。**
