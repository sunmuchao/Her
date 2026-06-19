# Agent 执行逻辑完整梳理

> 基于 2026-06-19 12:37-12:42 的对话日志分析

## 用户对话内容回顾

**用户输入 1**：
```
我想找性格外向的女生
```

**用户输入 2**：
```
我希望找一个愿意一起吃路边摊、旅行住干净民宿、不追求奢侈品包包的女生。
也同时希望女生有独立收入，不是为了钱和我在一起，而是看中我的人格魅力。
```

**Agent 回复**：
```
明白了，你说的这些其实是很核心的生活价值观——

总结一下你的期望：
🌟 消费观朴素务实：吃路边摊、住民宿，享受的是生活本身而不是排场
🌟 不追奢侈品：不追求名牌包包那些
🌟 对方有独立收入：经济独立，在一起是因为人，不是因为钱
🌟 看重你的人格魅力：希望对方是真正被你这个人吸引

结合你刚才说想找外向的女生，我看了一下现在的候选人：

张安萌（27岁，采购） 比较符合——ESFJ外向型，价值观是"真诚沟通"，属于"真诚靠近型"，有稳定工作。感觉她更看重人和人之间的真实连接。

刘舒彤（25岁，审计） 也是ESFJ外向型，有独立收入，不过她的价值观里提到"生活质感"，这个可能要看具体是什么理解——是追求品质还是追求奢侈，聊了才知道。

其他几位偏内向，可能不太符合你"外向"的要求。

你想先跟张安萌或刘舒彤聊聊看，还是我帮你再搜一轮？
```

---

## 一、执行流程架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                     用户输入                                     │
│  "我想找性格外向的女生"                                           │
│  "我希望找一个愿意吃路边摊...的女生"                               │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Service 层                                   │
│  - 接收用户消息                                                   │
│  - 构建 DiscoveryRunInput                                        │
│  - 调用 Agent Runtime                                            │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Agent Runtime (agent_runtime.py)            │
│                                                                 │
│  1. 构建 System Prompt (SOUL.md)                                │
│  2. 构建 Runtime Input (用户状态、候选人数据、用户画像)           │
│  3. 定义工具（Tools）                                            │
│     - sync_requester_persona_memory                             │
│     - search_partner_candidates                                 │
│     - reply_to_user                                             │
│     - show_candidates                                           │
│     - suggest_assessment                                        │
│  4. 调用 Agents SDK Runner                                      │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                     LLM Agent 决策                               │
│                                                                 │
│  - 理解用户意图                                                   │
│  - 选择合适的工具                                                 │
│  - 生成回复内容                                                   │
│  - 提供建议按钮                                                   │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                     工具执行层                                    │
│                                                                 │
│  1. search_partner_candidates (失败)                            │
│     - 参数：{"match_traits": ["外向"], "similarity_threshold": 0.7} │
│     - 错误：name 'profile_facts' is not defined                 │
│                                                                 │
│  2. sync_requester_persona_memory (禁用)                        │
│     - 参数：生活价值观偏好                                        │
│     - 返回：disabled_for_testing                                 │
│                                                                 │
│  3. reply_to_user (成功)                                        │
│     - 参数：回复消息、phase、button_texts                         │
│     - 返回：{"success": True, "kind": "reply"}                  │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                     决策提取层                                    │
│                                                                 │
│  - 从 tool_state 提取 reply_payload                             │
│  - 构建 DiscoveryDecision                                       │
│  - 记录关键日志                                                   │
│  - 返回 DiscoveryRuntimeResult                                  │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Service 层                                   │
│  - 处理决策结果                                                   │
│  - 构建前端响应                                                   │
│  - 返回给用户                                                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、关键执行步骤详解

### 2.1 Agent Runtime 初始化

**位置**：`agent_runtime.py` 第 846-856 行

```python
def _run_with_agents_sdk(
    self,
    run_input: DiscoveryRunInput,
    *,
    event: str,
    user_message: str | None,
    action_context: dict[str, Any] | None,
) -> DiscoveryRuntimeResult:
    try:
        from agents import Agent, AgentOutputSchema, Runner, function_tool
    except ImportError as exc:
        raise RuntimeError("Missing Agents SDK dependency. Install `openai-agents`.") from exc

    _configure_agents_sdk_provider()
    tool_state: dict[str, Any] = {"last_search_response": None}
```

**关键点**：
- 初始化 `tool_state` 用于存储工具调用结果
- 加载 Agents SDK 依赖
- 配置 Provider（API Key、Base URL 等）

---

### 2.2 工具定义

**位置**：`agent_runtime.py` 第 862-1056 行

#### 工具 1：sync_requester_persona_memory

```python
@function_tool
def sync_requester_persona_memory(patch_json: str) -> dict[str, Any]:
    """同步用户的择偶偏好到长期记忆。当用户说出明确、稳定、适合落库的择偶偏好时调用。沉淀长期偏好，后续推荐更精准。"""
    patch = json.loads(str(patch_json or "{}"))
    if not isinstance(patch, dict):
        raise ValueError("patch_json must decode into a JSON object")
    return run_input.sync_requester_persona_memory(patch)
```

**调用时机**：用户说出明确、稳定、适合落库的择偶偏好时

**本次对话调用**：
```json
{
  "patch_json": {
    "values_lifestyle": {
      "consumption_style": "朴素务实，不追求奢侈品",
      "dining_preference": "接地气，愿意吃路边摊",
      "travel_style": "干净民宿即可，不追求奢华",
      "partner_financial_expectation": "希望对方有独立收入，不是为钱在一起",
      "attracted_to": "人格魅力，而非物质条件"
    }
  }
}
```

**返回结果**：
```json
{
  "synced": False,
  "error_code": "disabled_for_testing",
  "message": "硬禁用：验证方案文档的'不插手'理想设计",
  "test_mode": True
}
```

---

#### 工具 2：search_partner_candidates

```python
@function_tool
def search_partner_candidates(
    criteria_json: str,
    personality_match_json: str = "",
    limit: int = 5
) -> dict[str, Any]:
    """搜索候选人。当用户想看推荐、调整搜索条件、表达不满后重新搜索时调用。

    支持的筛选条件（硬约束）：
    - gender: 性别（male/female）
    - age_min/age_max: 年龄范围
    - cities: 城市列表
    - relationship_goals: 关系目标

    性格匹配（向量筛选，可选）：
    - personality_match_json: 性格特质匹配条件
      示例：{"match_traits": ["外向", "温柔"], "similarity_threshold": 0.75}
      - match_traits: 想要匹配的性格特质列表
      - similarity_threshold: 相似度阈值（0.0-1.0，默认0.75）
      - Agent可根据对话上下文自主调整阈值（高要求用0.8，宽松用0.6）
    """
    # ...（工具实现逻辑）
```

**本次对话调用（失败）**：

**第一次调用**：
```json
{
  "criteria_json": {
    "gender": "female",
    "cities": ["无锡"],
    "relationship_goals": "dating",
    "age_min": 23,
    "age_max": 33
  },
  "personality_match_json": {
    "match_traits": ["外向"],
    "similarity_threshold": 0.7
  },
  "limit": 5
}
```

**错误信息**：
```
An error occurred while running the tool. Please try again.
Error: name 'profile_facts' is not defined
```

**第二次调用**（Agent 重试）：
- 参数相同
- 错误相同

**日志记录**：
```
2026-06-19 12:37:20,777 INFO discovery_system.service_integrations
【性格匹配转换】personality_match={'match_traits': ['外向'], 'similarity_threshold': 0.7}
→ vector_filter_json={'include': {'personality_traits': {'text': '外向', 'similarity_threshold': 0.7}}}
```

---

#### 工具 3：reply_to_user

```python
@function_tool
def reply_to_user(
    message: str,
    phase: str = "collecting_preferences",
    button_texts: list[str] = [],
) -> dict[str, Any]:
    """回复用户对话消息，不展示候选人卡片。

    适用场景：
    - 回答用户问题
    - 解释推荐理由
    - 收集用户反馈
    """
    # 【证据优先】记录工具调用参数
    _logger.info("【工具调用】reply_to_user")
    _logger.info("  - message：%s", message)
    _logger.info("  - phase：%s", phase)
    _logger.info("  - button_texts：%s", button_texts)

    payload = {
        "kind": "reply",
        "phase": phase,
        "assistant_message": message,
        "suggested_actions": [
            {"label": btn, "style": "secondary", "semantic_payload": {"kind": "suggested"}}
            for btn in button_texts[:3]
        ],
    }
    tool_state["reply_payload"] = payload
    return {"success": True, "kind": "reply", "phase": phase}
```

**本次对话调用（成功）**：

**第一次调用**：
```json
{
  "message": "好的，你想找性格外向的女生～\n\n我看了一下刚才推荐给你的几位，其中有两个是典型外向型的：\n\n**张安萌（ESFJ）**——热情、善于社交、喜欢照顾人，和她在一起会比较热闹有活力。\n\n**刘舒彤（ESFJ）**——同样是外向型，重视家庭和生活品质，性格温暖开朗。\n\n其他几位（ISTJ、ISFJ）偏内向沉稳一些。\n\n你是想先看看这两位外向型的，还是我帮你重新搜一轮，专门筛选外向的女生？另外，你对"外向"的理解是那种特别能聊能社交的，还是开朗活泼就行？",
  "phase": "results_shown",
  "button_texts": ["看看这两位", "重新搜外向的", "我再说说外向的标准"]
}
```

**第二次调用**：
```json
{
  "message": "明白了，你说的这些其实是很核心的生活价值观——\n\n总结一下你的期望：\n🌟 **消费观朴素务实**：吃路边摊、住民宿，享受的是生活本身而不是排场\n🌟 **不追奢侈品**：不追求名牌包包那些\n🌟 **对方有独立收入**：经济独立，在一起是因为人，不是因为钱\n🌟 **看重你的人格魅力**：希望对方是真正被你这个人吸引\n\n结合你刚才说想找**外向**的女生，我看了一下现在的候选人：\n\n**张安萌（27岁，采购）** 比较符合——ESFJ外向型，价值观是"真诚沟通"，属于"真诚靠近型"，有稳定工作。感觉她更看重人和人之间的真实连接。\n\n**刘舒彤（25岁，审计）** 也是ESFJ外向型，有独立收入，不过她的价值观里提到"生活质感"，这个可能要看具体是什么理解——是追求品质还是追求奢侈，聊了才知道。\n\n其他几位偏内向，可能不太符合你"外向"的要求。\n\n你想先跟张安萌或刘舒彤聊聊看，还是我帮你再搜一轮？",
  "phase": "results_shown",
  "button_texts": ["先看看这两位", "帮我重新搜", "我想多了解张安萌"]
}
```

**日志记录**：
```
2026-06-19 12:37:32,500 INFO discovery_system.agent_runtime
  - message：好的，你想找性格外向的女生～
  ...

2026-06-19 12:42:49,935 INFO discovery_system.agent_runtime
  - button_texts：['先看看这两位', '帮我重新搜', '我想多了解张安萌']
```

---

### 2.3 Agent 构建与执行

**位置**：`agent_runtime.py` 第 1041-1083 行

```python
instructions = _build_discovery_agent_instructions(
    event=event,
    user_message=user_message,
    action_context=action_context,
)

# 方案A：拆分为两个专用工具（reply_to_user + show_candidates）
tools = [
    sync_requester_persona_memory,
    search_partner_candidates,
    create_saved_search_subscription_from_last_search,
    reply_to_user,
    show_candidates,
    suggest_assessment,
]

runtime_input = _build_runtime_prompt(
    run_input=run_input,
    event=event,
    user_message=user_message,
    action_context=action_context,
)

agent = Agent(
    name="discovery_matchmaker",
    instructions=instructions.strip(),
    model=_resolve_discovery_model(wire_api=_resolve_discovery_wire_api()),
    output_type=None,
    tools=tools,
)

started = time.perf_counter()
result, first_token_latency_ms = asyncio.run(
    self._run_streamed_agent(
        Runner=Runner,
        agent=agent,
        runtime_input=runtime_input,
        started=started,
        agent_session=run_input.agent_session,
    )
)
```

**关键点**：
- **Instructions**：System Prompt（SOUL.md）
- **Tools**：可用工具列表
- **Runtime Input**：用户状态、候选人数据、用户画像
- **Model**：qwen3.7-plus（从日志可见）
- **Session Memory**：启用会话记忆

---

### 2.4 Runtime Input 构建

**位置**：`agent_runtime.py` 第 755-804 行

```python
def _build_runtime_prompt(
    *,
    run_input: DiscoveryRunInput,
    event: str,
    user_message: str | None,
    action_context: dict[str, Any] | None,
) -> str:
    # ... 构建用户状态、候选人数据、用户画像
    payload = {
        "event": {
            "clicked_action": action_context,
            "type": event,
            "user_message": user_message,
        },
        "memory_summary": memory_summary,
        "state": {
            "current_results": current_results,
            "last_search": last_search_summary,
            "session": session_summary,
            "user_profile": user_profile_summary,
            "visible_actions": visible_actions,
        },
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
```

**本次对话 Runtime Input（从日志提取）**：

```json
{
  "event": {
    "clicked_action": null,
    "type": "user_message",
    "user_message": "我想找性格外向的女生"
  },
  "memory_summary": {
    "recent_feedback_summary": null,
    "stable_preferences_summary": "关系目标是dating"
  },
  "state": {
    "current_results": [
      {
        "compatibility_summary": "MBTI ESFJ；依恋偏secure",
        "personality_signals": {
          "attachment": {"type_code": "secure"},
          "mbti": {"type_code": "ESFJ"},
          "values": {
            "top_values": ["真诚沟通", "稳定经营"],
            "value_type": "真诚靠近型"
          }
        },
        "profile_id": 2701,
        "reason_summary": "状态 active、年龄 27、性别 女",
        "subtitle": "无锡 · 采购 · 本科",
        "title": "张安萌 27"
      },
      {
        "compatibility_summary": "MBTI ISTJ；依恋偏anxious",
        "personality_signals": {
          "attachment": {"type_code": "anxious"},
          "mbti": {"type_code": "ISTJ"},
          "values": {
            "top_values": ["稳定经营", "家庭责任"],
            "value_type": "稳定经营型"
          }
        },
        "profile_id": 5176,
        "reason_summary": "状态 active、年龄 25、性别 女",
        "subtitle": "无锡 · 银行职员 · 硕士",
        "title": "吴若宁 25"
      },
      {
        "compatibility_summary": "MBTI ISFJ；依恋偏secure",
        "personality_signals": {
          "attachment": {"type_code": "secure"},
          "mbti": {"type_code": "ISFJ"},
          "values": {
            "top_values": ["家庭责任", "独立空间"],
            "value_type": "家庭投入型"
          }
        },
        "profile_id": 9531,
        "reason_summary": "状态 active、年龄 25、性别 女",
        "subtitle": "无锡 · 护士 · 本科",
        "title": "陈沐妍 25"
      },
      {
        "compatibility_summary": "MBTI ESFJ；依恋偏secure",
        "personality_signals": {
          "attachment": {"type_code": "secure"},
          "mbti": {"type_code": "ESFJ"},
          "values": {
            "top_values": ["家庭责任", "生活质感"],
            "value_type": "家庭投入型"
          }
        },
        "profile_id": 5054,
        "reason_summary": "状态 active、年龄 25、性别 女",
        "subtitle": "无锡 · 审计 · 硕士",
        "title": "刘舒彤 25"
      },
      {
        "compatibility_summary": "MBTI ISTJ；依恋偏avoidant",
        "personality_signals": {
          "attachment": {"type_code": "avoidant"},
          "mbti": {"type_code": "ISTJ"},
          "values": {
            "top_values": ["稳定经营", "家庭责任"],
            "value_type": "稳定经营型"
          }
        },
        "profile_id": 8832,
        "reason_summary": "状态 active、年龄 25、性别 女",
        "subtitle": "无锡 · 审计 · 本科",
        "title": "赵思岚 25"
      }
    ],
    "last_search": {
      "criteria_summary": "无锡，female，23-33岁，dating",
      "result_count": 5,
      "status": "success"
    },
    "session": {
      "criteria_labels": ["无锡", "女", "23-33岁", "先谈恋爱"],
      "phase": "results_shown",
      "session_id": "discovery-session-61728e5094da",
      "status": "active"
    },
    "user_profile": {
      "age": 28,
      "city": "无锡",
      "gender": "male",
      "has_children": false,
      "job": "创始人",
      "marital_status": "未婚",
      "relationship_goal": "dating",
      "target_gender": "男"
    },
    "visible_actions": []
  }
}
```

---

### 2.5 Agent 决策提取

**位置**：`agent_runtime.py` 第 1108-1218 行

```python
# 提取工具调用结果
reply_payload = tool_state.get("reply_payload")
show_payload = tool_state.get("show_payload")

# 方案C：提取所有 payload，供 Service 层处理
payloads = []
if reply_payload:
    payloads.append(reply_payload)
if show_payload:
    payloads.append(show_payload)

# 提取主要 decision
decision_payload = show_payload or reply_payload

if decision_payload is not None:
    decision = DiscoveryDecision(
        phase=decision_payload.get("phase") or "collecting_preferences",
        assistant_message=decision_payload.get("assistant_message") or "",
        criteria_labels=decision_payload.get("criteria_labels") or [],
        suggested_actions=[
            DiscoveryActionSuggestion(
                label=action.get("label"),
                style=action.get("style"),
                semantic_payload=action.get("semantic_payload"),
            )
            for action in (decision_payload.get("suggested_actions") or [])
        ],
        result_group_title=decision_payload.get("result_group_title"),
        selected_candidates=[
            DiscoveryCandidateSelection(
                profile_id=c.get("profile_id"),
                reason_summary=c.get("reason_summary") or "",
            )
            for c in (decision_payload.get("selected_candidates") or [])
        ],
        _all_payloads=payloads,
    )
```

---

### 2.6 关键日志埋点

**位置**：`agent_runtime.py` 第 1198-1209 行

```python
# 【证据优先】关键日志埋点：记录 Agent 实际行为
_logger.info("=" * 80)
_logger.info("【Agent 实际行为记录】")
_logger.info("用户输入：%s", user_message or action_context or "initial")
_logger.info("Agent 输出：%s", decision.assistant_message)
_logger.info("决策阶段：%s", decision.phase)
_logger.info("建议按钮：%s", [action.label for action in (decision.suggested_actions or [])])
_logger.info("工具调用：%s", list(tool_state.keys()))
_logger.info("=" * 80)
```

**本次对话日志记录**：

```
2026-06-19 12:37:36,888 INFO discovery_system.agent_runtime 用户输入：我想找性格外向的女生
2026-06-19 12:37:36,888 INFO discovery_system.agent_runtime Agent 输出：好的，你想找性格外向的女生～...
2026-06-19 12:37:36,888 INFO discovery_system.agent_runtime 决策阶段：results_shown
2026-06-19 12:37:36,888 INFO discovery_system.agent_runtime 建议按钮：['看看这两位', '重新搜外向的', '我再说说外向的标准']

2026-06-19 12:42:59,117 INFO discovery_system.agent_runtime 用户输入：我希望找一个愿意一起吃路边摊...
2026-06-19 12:42:59,117 INFO discovery_system.agent_runtime Agent 输出：明白了，你说的这些其实是很核心的生活价值观——...
2026-06-19 12:42:59,117 INFO discovery_system.agent_runtime 决策阶段：results_shown
2026-06-19 12:42:59,117 INFO discovery_system.agent_runtime 建议按钮：['先看看这两位', '帮我重新搜', '我想多了解张安萌']
```

---

## 三、关键问题分析

### 3.1 search_partner_candidates 工具失败

**问题现象**：
```
Error: name 'profile_facts' is not defined
```

**根因分析**：
```
问题现象：search_partner_candidates 工具调用失败
├─ 为什么 1: 工具内部引用了未定义的变量 profile_facts
├─ 为什么 2: 性格匹配转换成功，但后续查询失败
│   → 日志显示：personality_match={'match_traits': ['外向'], 'similarity_threshold': 0.7} 转换成功
├─ 为什么 3: 可能是 Service Integrations 层的代码缺陷
│   → 需要检查 service_integrations.py 中的性格匹配查询逻辑
└─ 为什么 4: 【根本原因】向量查询时缺少必要的上下文变量定义
```

**修复建议**：
1. 检查 `service_integrations.py` 中性格匹配查询逻辑
2. 确保向量查询时 `profile_facts` 变量已定义
3. 补充错误日志，定位具体失败位置

---

### 3.2 Agent 应对策略分析

**Agent 行为**：
- ✅ 正确识别用户意图（找外向女生）
- ✅ 尝试调用 search_partner_candidates 工具
- ❌ 工具调用失败两次
- ✅ 改用 reply_to_user 工具回复用户
- ✅ 从现有候选人中筛选外向型（ESFJ）
- ✅ 生成合理的推荐理由和对话回复
- ✅ 提供合理的建议按钮

**优点**：
1. **自主决策能力强**：工具失败后，Agent 能够自主调整策略，改用 reply_to_user 回复用户
2. **理解用户意图准确**：正确识别"外向"需求，从现有候选人中筛选 ESFJ 类型
3. **推荐理由合理**：根据 personality_signals 数据自主生成推荐理由
4. **对话风格自然**：口语化、像真人红娘

**改进点**：
1. **工具失败处理**：应记录工具失败原因，避免用户看到"搜索失败"提示
2. **性格匹配数据不足**：现有候选人数据中没有详细的性格特质描述，Agent 只能依赖 MBTI 类型判断
3. **价值观匹配不够精准**：张安萌的价值观是"真诚沟通"，刘舒彤的价值观是"生活质感"，与用户的"朴素务实"匹配度需要更细致分析

---

## 四、数据流转分析

### 4.1 用户状态数据

```json
{
  "session": {
    "criteria_labels": ["无锡", "女", "23-33岁", "先谈恋爱"],
    "phase": "results_shown",
    "session_id": "discovery-session-61728e5094da",
    "status": "active"
  },
  "user_profile": {
    "age": 28,
    "city": "无锡",
    "gender": "male",
    "has_children": false,
    "job": "创始人",
    "marital_status": "未婚",
    "relationship_goal": "dating",
    "target_gender": "男"
  }
}
```

### 4.2 候选人性格数据

**张安萌（2701）**：
```json
{
  "compatibility_summary": "MBTI ESFJ；依恋偏secure",
  "personality_signals": {
    "attachment": {"type_code": "secure"},
    "mbti": {"type_code": "ESFJ"},
    "values": {
      "top_values": ["真诚沟通", "稳定经营"],
      "value_type": "真诚靠近型"
    }
  }
}
```

**刘舒彤（5054）**：
```json
{
  "compatibility_summary": "MBTI ESFJ；依恋偏secure",
  "personality_signals": {
    "attachment": {"type_code": "secure"},
    "mbti": {"type_code": "ESFJ"},
    "values": {
      "top_values": ["家庭责任", "生活质感"],
      "value_type": "家庭投入型"
    }
  }
}
```

### 4.3 性格匹配转换

**输入**：
```json
{
  "match_traits": ["外向"],
  "similarity_threshold": 0.7
}
```

**转换结果**：
```json
{
  "include": {
    "personality_traits": {
      "text": "外向",
      "similarity_threshold": 0.7
    }
  }
}
```

---

## 五、Agent Native 架构验证

### 5.1 三层分离架构

| 层级 | 本次执行表现 | 符合度 |
|------|------------|--------|
| System Prompt Layer (SOUL.md) | ✅ 定义角色、原则、安全边界 | 高 |
| Tools Layer | ⚠️ 工具失败，但职责清晰 | 中 |
| Data Layer | ✅ 原始数据清晰，包含 personality_signals | 高 |

### 5.2 职责边界检查

| 检查项 | 本次执行表现 | 符合度 |
|--------|------------|--------|
| Agent 自主决策 | ✅ 工具失败后自主调整策略 | 高 |
| 工具只提供原始数据 | ✅ personality_signals 数据完整 | 高 |
| Agent 自主生成推荐理由 | ✅ 根据 MBTI 和价值观自主分析 | 高 |
| 输出内容自然语言化 | ✅ 口语化、像真人红娘 | 高 |

### 5.3 硬约束 vs 软约束分层

| 约束类型 | 本次执行表现 | 符合度 |
|----------|------------|--------|
| 硬约束（性别、年龄、城市） | ✅ 在 criteria_json 中传递 | 高 |
| 软约束（性格外向、价值观匹配） | ✅ Agent 自主判断 | 高 |
| 性格匹配向量筛选 | ⚠️ 工具失败，但转换逻辑正确 | 中 |

---

## 六、总结

### 6.1 执行流程完整度

✅ **完整流程**：从用户输入 → Agent Runtime → LLM Agent → 工具执行 → 决策提取 → Service 层，完整链路清晰

✅ **数据流转清晰**：用户状态、候选人数据、性格匹配数据流转完整

✅ **Agent Native 架构符合度高**：Agent 自主决策、工具职责清晰、原始数据完整

### 6.2 关键问题

❌ **search_partner_candidates 工具失败**：`profile_facts` 未定义

⚠️ **性格匹配数据不足**：候选人性格数据只有 MBTI、依恋风格、价值观，缺少详细的性格特质描述

### 6.3 改进建议

1. **修复工具缺陷**：确保 `profile_facts` 变量定义
2. **增强性格数据**：增加性格特质向量数据，提升匹配精准度
3. **优化价值观匹配**：细化价值观标签，提升"朴素务实"等价值观匹配度
4. **工具失败处理**：Agent 应提示用户"正在调整推荐策略"，避免用户感知失败