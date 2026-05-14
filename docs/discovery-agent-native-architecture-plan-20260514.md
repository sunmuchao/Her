# 发现页 Agent-Native 完整接入方案

日期：2026-05-14

---

## 1. 结论先行

发现页的正确形态不是：

- 前端自己解析用户条件
- 前端自己决定什么时候搜索
- 后端用一堆 `if/else` 把流程写死

发现页的正确形态应该是：

- 前端只负责展示和上报用户动作
- 后端只负责会话、工具、状态、审计和安全边界
- 真正的产品判断全部交给 GPT agent

一句话版：

`发现页前端 = 红娘对话窗口`

`后端 = agent 容器 + tool registry + session/state 持久化 + JSON 视图适配层`

`决策层 = GPT agent`

---

## 2. 目标与非目标

### 2.1 目标

本方案要实现的是：

1. 用户在发现页直接和 AI 红娘对话
2. 红娘自己判断是否需要继续追问
3. 红娘自己决定何时调用 `partner-search`
4. 红娘自己决定如何解释结果、强调哪些卡片、下一步建议什么
5. 前端收到稳定 JSON 后直接展示，不做产品判断

### 2.2 非目标

本方案明确不做：

1. 前端本地规则判断
2. 后端硬编码“用户说 X 就一定搜 Y”的规则树
3. 把 `partner-search` 扩成推荐系统、聊天系统或前端编排系统

---

## 3. 当前仓库里已经存在的基础能力

### 3.1 现有 GPT agent 接入已经存在，但在聊天红娘 C 上

仓库里已经有一套后端跑 GPT agent 的实现，不在前端：

- provider 配置：[`external-systems/partner-chat-system/chat_system/assistant_runtime.py`](../external-systems/partner-chat-system/chat_system/assistant_runtime.py)
  - `_configure_agents_sdk_provider()`：第 `900` 行附近
  - `_run_with_agents_sdk()`：第 `940` 行附近
  - `run_matchmaker_agent()`：第 `1172` 行附近
- 编排器：[`external-systems/partner-chat-system/chat_system/assistant_orchestrator.py`](../external-systems/partner-chat-system/chat_system/assistant_orchestrator.py)
  - `process_pending_agent_tasks()`：第 `342` 行附近
- 环境变量占位：[` .env.example`](../.env.example)
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL`
  - `HER_CHAT_AGENT_MODEL`
  - `HER_CHAT_AGENT_RUNTIME=agents_sdk`
  - `HER_CHAT_AGENT_OPENAI_API=chat_completions`
- 运行说明：[`external-systems/partner-chat-system/README.md`](../external-systems/partner-chat-system/README.md)

这证明了两件事：

1. 当前仓库已经接受“后端 agent 决策，前端只展示”的模式
2. 这套模式可以复用于发现页，只是不能直接复用聊天红娘的 prompt 和上下文

### 3.2 `partner-search` 已经是纯匹配引擎

`partner-search` 的边界在 [`local-skills/partner-search/SKILL.md`](../local-skills/partner-search/SKILL.md) 里写得很清楚：

- 输入画像和条件
- 输出候选结果
- 不负责持续留意
- 不负责通知
- 不负责会话管理
- 不负责前端交互编排

这意味着发现页不应该直接把 `partner-search` 暴露给前端，而应该在外面再包一层“红娘发现系统”。

### 3.3 网关里已有可复用的搜索和空结果能力

- 搜索入口：[`external-systems/partner-http-gateway/API_CONTRACT.md`](../external-systems/partner-http-gateway/API_CONTRACT.md)
  - `POST /v1/search/profiles`
- 空结果 opt-in 编排：[`external-systems/partner-recommendation-system/recommendation_system/no_match_opt_in.py`](../external-systems/partner-recommendation-system/recommendation_system/no_match_opt_in.py)
  - `run_search_session(...)`
  - `handle_opt_in_decision(...)`

这些都应该作为发现 agent 的工具，而不是前端直接理解的业务流程。

---

## 4. 核心设计原则

### 4.1 前端零业务判断

前端只允许做：

1. 展示消息
2. 展示条件 chips
3. 展示候选卡片
4. 展示建议按钮
5. 把用户输入或点击动作原样发给后端

前端不允许做：

1. 判断这句话是不是筛选条件
2. 判断是不是该搜索
3. 判断哪些卡片该展示
4. 判断空结果时是不是该给“继续留意”
5. 判断下一轮建议按钮该出现什么

### 4.2 后端零产品规则树

后端不应该写死下面这些产品判断：

1. 先问年龄还是先问城市
2. 什么时候停止追问
3. 什么时候调用 `partner-search`
4. 搜到 2 个结果后重点展示谁
5. 结果不够好时应该怎么解释
6. 空结果时要不要引导持续留意

这些判断全部应该由 agent 决定。

### 4.3 后端仍然必须保留硬边界

“后端不要硬编码逻辑”不等于后端什么都不做。

后端仍然必须硬编码这些非产品决策能力：

1. 鉴权
2. 幂等
3. rate limit
4. 持久化
5. tool 注册
6. schema 校验
7. 错误兜底
8. 审计日志
9. 风险隔离

允许硬编码的是“平台基础设施边界”，不允许硬编码的是“产品判断逻辑”。

### 4.4 工具和历史的正确归属

这里需要特别澄清两个容易说错的点。

#### 4.4.1 工具不是每轮临时讲给 agent 听的

正确做法是：

1. agent 创建时就绑定固定 tool 集合
2. 后端负责注册这些 tool
3. agent 天然知道自己有哪些工具可以调用

也就是说：

- `tool 定义` 是 agent 的固定配置
- 不是每轮用户发消息时再把“可用工具说明”重新拼进 prompt

#### 4.4.2 历史也不应该每轮全量硬塞进 prompt

正确做法是三层并存：

1. `固定指令`
   - 红娘角色、边界、输出 schema
2. `session memory`
   - 当前发现会话最近几轮上下文和已整理状态
3. `后端权威历史`
   - 完整 turn、搜索快照、action、详情读取记录

所以正确模式不是：

- 每轮都把全部历史塞给 agent

也不是：

- 只靠 agent 自己记住所有历史

而是：

- agent 平时依赖当前 session memory
- 必要时再通过 tool 主动查询后端保存的权威历史

---

## 5. 推荐架构

建议新增一个独立外层系统，而不是把发现页逻辑塞进前端，也不是直接塞进 `partner-search`：

```text
Frontend Discovery Page
        |
        v
partner-http-gateway  /v1/discovery/...
        |
        v
partner-discovery-system
  - session storage
  - turn storage
  - action storage
  - tool run storage
  - agent runtime
  - session memory / state
  - tool registry
  - view adapter
        |
        +--> partner-search
        +--> recommendation_system.no_match_opt_in
        +--> recommendation_system.create_subscription
        +--> profile detail reader
        +--> trust / verification read models
```

建议新目录：

```text
external-systems/partner-discovery-system/
  discovery_system/
    __init__.py
    storage.py
    service.py
    agent_runtime.py
    view_models.py
  tests/
    test_discovery_system.py
```

这样做的原因：

1. 保持 `partner-search` 的纯匹配边界不变
2. 保持发现页的 agent 编排逻辑独立
3. 方便未来继续加“详情页承接”和“持续留意”

---

## 6. 发现页的真实职责分层

### 6.1 前端职责

前端发现页只负责渲染后端返回的 `render model`：

- timeline items
- normalized criteria chips
- result cards
- suggested actions
- composer placeholder

### 6.2 后端基础设施职责

后端负责：

- 发现会话的创建与恢复
- agent 的固定配置与启动
- tool registry 注册
- session state 持久化
- 权威历史持久化
- agent 输出校验
- 将 agent 输出稳定化成前端 JSON

### 6.3 GPT agent 职责

agent 负责：

- 解释用户自然语言
- 判断信息够不够
- 决定是否继续追问
- 决定是否调用搜索工具
- 决定先展示哪几个候选人
- 决定结果用什么口吻解释
- 决定下一轮快速按钮是什么
- 决定空结果时是否建议“持续留意”

---

## 7. 发现页完整时序

```text
1. 用户打开发现页
2. 前端调用 POST /v1/discovery/sessions
3. 后端创建 discovery session
4. agent 生成欢迎语和第一轮建议问题
5. 前端展示欢迎消息

6. 用户输入自然语言
7. 前端调用 POST /v1/discovery/sessions/{session_id}/turns
8. 后端找到这条 discovery session，并唤起一个已经绑定好 tools 的 discovery agent
9. agent 基于当前 user message、session memory 和必要时可查询的后端历史来判断：
   - 先追问
   - 还是直接搜索
10. 如需搜索，agent 调用 search tool
11. 后端拿到 canonical search result
12. agent 产出最终 view intent
13. 后端把结果适配成前端 render model
14. 前端直接展示

15. 用户点击“只看无锡本地”
16. 前端只上传 action_id
17. 后端查 action payload，并恢复对应 discovery session
18. 再次唤起同一个 discovery agent
19. agent 决定是否重新搜索或继续追问
20. 前端继续展示
```

---

## 8. 工具层设计

### 8.1 原则

tool 层只提供“能力”，不提供产品判断。

也就是说：

- tool 可以返回候选结果
- tool 可以返回详情
- tool 可以创建持续留意订阅

但：

- tool 不负责决定“现在该不该调用我”
- tool 不负责决定“要不要先追问一下”

这些都由 agent 决定。

补充一点：

- tool 是 agent 创建时就已注册好的固定能力
- 不是每轮 turn 再临时下发一遍“你有哪些工具”

### 8.2 建议的 tool 列表

#### Tool 1. `search_partner_candidates`

用途：

- 调 `partner-search`
- 返回 canonical search response

底层可复用：

- `POST /v1/search/profiles`
- 或 `partner_search.search_profiles(...)`

输入：

- structured criteria
- self profile
- limit

输出：

- result_count
- has_match
- results[]
- trust fields
- caution fields

#### Tool 2. `get_candidate_profile_detail`

用途：

- 读取某个候选人的详情模型

输入：

- `profile_id`
- `source`

输出：

- 基础资料
- 照片
- verification_items
- trust_summary
- caution_items
- 建议确认的问题

#### Tool 3. `create_saved_search_subscription_from_last_search`

用途：

- 当这一轮搜不到合适人时，为用户创建“持续留意”

底层可复用：

- `recommendation_system.no_match_opt_in`
- `recommendation_system.create_subscription`

重要边界：

- agent 决定要不要向用户提出“持续留意”
- 用户确认后，tool 只负责创建，不负责替 agent 决策

#### Tool 4. `get_discovery_session_state`

用途：

- 让 agent 读取当前 discovery session 的结构化状态，而不是依赖前端解释

输出：

- normalized criteria
- last search snapshot ref
- unresolved questions
- previous action context

#### Tool 5. `list_recent_discovery_turns`

用途：

- 让 agent 在需要时读取最近几轮发现对话

注意：

- 这不是说每轮都把最近几轮硬塞进 prompt
- 而是说这份历史始终在后端，agent 需要时可以主动查

#### Tool 6. `load_candidate_result_set`

用途：

- 给 agent 看上一轮搜索结果，便于下一轮缩小

---

## 9. Agent 运行时设计

### 9.1 复用现有 chat agent 的模式

发现页建议复用聊天红娘 C 的运行方式：

- 依然使用 `openai-agents`
- 依然由后端注册 function tools
- 依然要求结构化 JSON 输出
- 依然由后端做 schema validate

不要复用的部分：

- 聊天红娘的 prompt
- 聊天 case/session/task 表
- 聊天里的多会话上下文

### 9.2 建议的 discovery agent 输入

不要把这里理解成“每轮都把所有内容全量塞进 prompt”。

更准确地说，discovery agent 每次被唤起时，运行上下文应分成三层：

1. agent 固定配置
2. 当前 session memory / state
3. agent 可主动调用的历史和搜索 tools

其中，直接注入本轮运行上下文的最小必要信息建议包含：

- 当前用户消息
- discovery session 当前 state
- 当前用户的画像快照
- 最近一轮或当前有效的搜索结果引用

其余历史不要默认全量注入，而应通过下列 tools 按需读取：

- `get_discovery_session_state`
- `list_recent_discovery_turns`
- `load_candidate_result_set`

### 9.3 建议的 discovery agent 输出 schema

发现页不应该直接吃 LLM 原文，而应该吃严格 schema。

建议输出：

```json
{
  "assistant_messages": [
    {
      "tone": "warm",
      "body": "我先按无锡、认真恋爱、真人认证优先帮你缩一轮。"
    }
  ],
  "criteria_patch": {
    "cities": ["无锡"],
    "relationship_goals": ["认真恋爱", "结婚导向"],
    "verified_level_min": "photo"
  },
  "should_run_search": true,
  "search_request_ref": "search-run-001",
  "result_card_refs": ["candidate-1001", "candidate-1007"],
  "detail_prefetch_refs": ["candidate-1001"],
  "suggested_actions": [
    {
      "action_id": "act-001",
      "label": "只看无锡本地",
      "kind": "agent_defined"
    },
    {
      "action_id": "act-002",
      "label": "再年轻一点",
      "kind": "agent_defined"
    }
  ],
  "session_state_patch": {
    "phase": "results_shown"
  }
}
```

注意：

- agent 可以决定 `should_run_search`
- agent 可以决定 `suggested_actions`
- agent 不能随便编造卡片字段
- 卡片详情最好引用 canonical tool result，再由后端 adapter 输出给前端

---

## 10. 为什么需要“view adapter”，但它不算业务硬编码

这里需要明确一个容易混淆的点。

如果 agent 最终直接输出完整卡片文案、完整字段和值，风险很高：

1. 容易幻觉
2. 容易和 tool 实际返回不一致
3. 不利于前端稳定渲染

所以建议后端保留一层 deterministic adapter：

- agent 负责“决定展示谁、强调什么”
- adapter 负责“把 canonical candidate 数据组装成稳定卡片 JSON”

这层 adapter 不属于你反对的“硬编码业务判断”，因为它不决定产品逻辑，只负责：

1. 引用真实字段
2. 保证 JSON shape 稳定
3. 避免 agent 编造值

---

## 11. 前端 API contract

### 11.1 创建发现会话

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
  "session": {
    "session_id": "discovery-session-001",
    "status": "active"
  },
  "view": {
    "timeline": [
      {
        "item_type": "assistant_message",
        "body": "先跟我说说你想找什么样的人，不用一次讲完整。"
      }
    ],
    "criteria_chips": [],
    "suggested_actions": [
      {
        "action_id": "act-open-001",
        "label": "先从城市和年龄说起"
      }
    ],
    "composer": {
      "placeholder": "告诉红娘你的偏好，她会替你整理并搜索。"
    }
  }
}
```

### 11.2 发送一轮用户输入

`POST /v1/discovery/sessions/{session_id}/turns`

请求：

```json
{
  "user_message": "我在无锡，想找认真恋爱、最好工作稳定一点的女生。"
}
```

或者点击 action 时：

```json
{
  "action_id": "act-001"
}
```

前端不能上传“我判断这是 refine_search”。  
前端只上传 `action_id`。

响应：

```json
{
  "session": {
    "session_id": "discovery-session-001",
    "status": "active",
    "phase": "results_shown"
  },
  "view": {
    "timeline": [
      {
        "item_type": "user_message",
        "body": "我在无锡，想找认真恋爱、最好工作稳定一点的女生。"
      },
      {
        "item_type": "assistant_message",
        "body": "我先按无锡、认真恋爱、稳定度优先帮你缩一轮。"
      },
      {
        "item_type": "result_group",
        "group_id": "group-001",
        "cards": [
          {
            "card_id": "candidate-1001",
            "profile_id": 1001,
            "title": "林知夏 29",
            "subtitle": "无锡 · 中学老师 · 硕士",
            "match_score": 92,
            "trust_badges": ["真人照认证", "学历已核验"],
            "reason_summary": "目标一致、生活稳定、表达自然"
          }
        ]
      }
    ],
    "criteria_chips": [
      {"label": "无锡"},
      {"label": "认真恋爱"},
      {"label": "工作稳定优先"}
    ],
    "suggested_actions": [
      {
        "action_id": "act-002",
        "label": "只看无锡本地"
      },
      {
        "action_id": "act-003",
        "label": "真人认证以上"
      }
    ]
  }
}
```

### 11.3 恢复发现页

`GET /v1/discovery/sessions/{session_id}`

返回当前完整 render model。

前端恢复页面时，不允许自己重算。

### 11.4 资料详情页

`GET /v1/discovery/profiles/{profile_id}?session_id=...`

返回详情页专用 render model：

- hero
- photo gallery
- verified sections
- self-reported sections
- caution sections
- matchmaker notes
- CTA actions

前端不应该把列表页字段拼成详情页。

---

## 12. 建议的数据表

建议新增：

### 12.1 `discovery_agent_sessions`

字段建议：

- `session_id`
- `requester_id`
- `requester_profile_id`
- `status`
- `state_json`
- `memory_version`
- `created_at`
- `updated_at`

### 12.2 `discovery_agent_turns`

字段建议：

- `turn_id`
- `session_id`
- `role`
- `body`
- `source`
- `action_id`
- `tool_run_refs_json`
- `agent_output_json`
- `created_at`

### 12.3 `discovery_agent_actions`

字段建议：

- `action_id`
- `session_id`
- `turn_id`
- `label`
- `semantic_payload_json`
- `expires_at`

作用：

- 前端只上传 `action_id`
- 真正语义只存在后端

### 12.4 `discovery_search_runs`

字段建议：

- `search_run_id`
- `session_id`
- `request_json`
- `response_json`
- `result_count`
- `created_at`

### 12.5 `discovery_view_snapshots`

可选。

如果希望前端恢复更快，可以存每轮稳定 render model。

### 12.6 关于“记忆”的数据归属

建议不要把“记忆”理解成只在模型上下文里存在。

更准确的数据归属是：

- `session memory`
  - 保存在 `discovery_agent_sessions.state_json`
  - 表示当前已整理出的条件、未解决问题、当前阶段
- `turn history`
  - 保存在 `discovery_agent_turns`
  - 表示真实对话和 agent 输出
- `tool truth`
  - 保存在 `discovery_search_runs` 等表
  - 表示真实工具执行结果

这样 agent 可以“像有记忆”，但系统的权威事实来源仍然在后端数据库里。

---

## 13. 空结果与“持续留意”

这里必须强调：  
“空结果时要不要引导持续留意”也不应该写死成前端或后端规则。

推荐做法：

1. tool 返回 `result_count=0`
2. agent 自己决定怎么跟用户解释
3. agent 如果认为合适，可以给一个建议 action：
   - `如果你愿意，我后面继续替你留意`
4. 用户点击后，前端只上传 `action_id`
5. 后端把对应 action 交给 agent 或直接调用订阅创建 tool

底层可以复用：

- `recommendation_system.no_match_opt_in.run_search_session(...)`
- `recommendation_system.no_match_opt_in.handle_opt_in_decision(...)`

但不要把用户文案和展示时机写死在前端。

---

## 14. 资料详情页承接

发现页里的卡片点进去后，详情页仍然必须遵守同一原则：

- 前端只展示
- 后端返回完整 render model

详情页建议至少返回以下分区：

1. 基础信息
2. 照片和活跃状态
3. 已核验信息
4. 自填信息
5. 待确认或风险提示
6. 红娘为什么把她放在这一轮结果里
7. 下一步建议确认什么

这样详情页不需要前端自己拼：

- `verification_items`
- `trust_summary`
- `caution_items`
- `match reasons`

---

## 15. 与聊天系统的关系

发现页和聊天系统应该统一成一种产品哲学：

- 都是 agent-native
- 都是前端纯展示
- 都是后端注册 tools
- 都是后端 validate structured output

发现页不应该直接复用聊天红娘的 prompt，但应复用这套运行方式：

- Agents SDK runtime
- function tools
- structured JSON schema
- task/session/turn 持久化
- 审计日志

---

## 16. 建议的分阶段落地

### Phase 1

先落 discovery agent 最小闭环：

1. session 创建
2. user_message -> agent -> assistant_message
3. agent 调 `partner-search`
4. 返回结果卡片
5. suggested actions 走 `action_id`

### Phase 2

补详情页正式承接：

1. `GET /v1/discovery/profiles/{profile_id}`
2. 详情 render model

### Phase 3

补空结果持续留意：

1. no result explanation
2. opt-in action
3. subscription create

### Phase 4

补行为回流与长期状态：

1. skip / keep / viewed
2. 更强的 discovery memory

---

## 17. 最终判断标准

如果实现正确，最后应该满足：

1. 前端不理解业务语义，只理解 render model
2. 前端按钮点击只发 `action_id`，不带产品判断
3. 后端不写死“先问什么、何时搜、怎么缩小”的规则树
4. tool 是预注册给 agent 的，不是每轮临时讲一遍
5. 历史既不只靠 agent 自己记，也不每轮全量塞 prompt，而是 `session memory + backend source of truth`
6. agent 拥有真实决策权
7. `partner-search` 仍然保持纯匹配引擎边界

---

## 18. 一句话结论

发现页应该做成：

**前端纯展示 + 后端 agent 容器 + tool 层 + GPT 决策**

而不是：

**前端规则页**  
或  
**后端 if/else 编排页**

这套方案本质上是把当前已经落地在聊天红娘 C 上的 `Agents SDK + 后端编排 + 结构化输出` 模式，扩展到发现页，但把产品判断进一步从“后端规则树”收缩为“agent 决策”。
