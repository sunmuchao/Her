# 心理测评引导 Tool 设计方案

## 背景

### 问题场景

用户在发现页对话：
```
用户："性格上也不合适"
Agent追问："你理想中的性格是什么样的？"
用户："想要更活泼开朗的"
Agent调整："优先匹配外向型（E型人格）的女生"
```

**问题**：系统只知道用户想要什么样的性格，不知道用户自己的性格类型。匹配是单向的，不准确。

---

## 架构设计

### Agent Native 分层原则

```
┌─────────────────────────────────────────────────────────────────┐
│  Prompt层 (SOUL.md) - 软约束                                    │
│                                                                 │
│  "当用户关心性格匹配时，可以引导做测评"                          │
│  Agent自主判断：什么时候建议用户做测评                           │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Tool层 - 硬约束 + 执行                                         │
│                                                                 │
│  suggest_assessment(assessment_type)                            │
│  - 检查用户是否已完成指定类型的测评                              │
│  - 未完成：返回测评引导卡片（前端渲染）                          │
│  - 已完成：返回用户性格类型信息                                  │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  前端层                                                         │
│                                                                 │
│  渲染测评引导卡片：                                              │
│  - 测评类型：MBTI性格测试                                        │
│  - 预计时长：约5分钟                                             │
│  - 好处：让匹配更精准                                            │
│  - "开始测评"按钮                                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tool 定义

### 函数签名

```python
@function_tool
def suggest_assessment(
    assessment_type: str = "mbti_16"
) -> dict[str, Any]:
    """
    检查用户测评状态，如未完成则返回引导卡片。
    
    适用场景：
    - 用户关心性格匹配时
    - 用户多次提到性格相关话题时
    - Agent判断需要了解用户性格类型时
    
    参数：
    - assessment_type: 测评类型
      - "mbti_16": MBTI性格测试
      - "attachment_style": 依恋风格测试
      - "big_five": 大五人格测试
    
    返回：
    - 已完成：{"completed": true, "type_code": "INTJ", "summary": "你是INTJ型"}
    - 未完成：{"completed": false, "suggest": true, "card": {...}}
    """
```

### 返回结构

#### 用户已完成测评

```python
{
    "completed": true,
    "assessment_type": "mbti_16",
    "type_code": "INTJ",
    "summary": "你是INTJ型（内向、直觉、思考、判断）",
    "dimension_scores": {
        "E-I": -65,  # 偏内向
        "S-N": 72,   # 偏直觉
        "T-F": 58,   # 偏思考
        "J-P": 45,   # 偏判断
    }
}
```

#### 用户未完成测评

```python
{
    "completed": false,
    "suggest": true,
    "assessment_type": "mbti_16",
    "card": {
        "card_type": "assessment_suggest",
        "assessment_type": "mbti_16",
        "title": "MBTI性格测试",
        "description": "了解你的性格类型，让匹配更精准",
        "duration": "约5分钟",
        "reward": "匹配准确度提升30%",
        "action_label": "开始测评",
        "action_id": "start_mbti_assessment"
    }
}
```

---

## 代码改动清单

### 1. agent_runtime.py

#### DiscoveryRunInput 添加字段

```python
@dataclass(frozen=True)
class DiscoveryRunInput:
    session_id: str
    requester_id: int
    profile_id: int
    phase: str
    criteria_labels: list[str]
    recent_timeline: list[dict[str, Any]]
    runtime_context: dict[str, Any]
    search_partner_candidates: Callable[[dict[str, Any], int], dict[str, Any]]
    sync_requester_persona_memory: Callable[[dict[str, Any]], dict[str, Any]]
    propose_requester_profile_update: Callable[[str, str], dict[str, Any]]
    create_saved_search_subscription_from_last_search: Callable[[], dict[str, Any]]
    suggest_assessment: Callable[[str], dict[str, Any]]  # 新增
    tool_call_buffer: list["DiscoveryToolCall"] = field(default_factory=list)
    agent_session: Any | None = None
```

#### 添加 Tool 定义

```python
@function_tool
def suggest_assessment(assessment_type: str = "mbti_16") -> dict[str, Any]:
    """检查用户测评状态，如未完成则返回引导卡片。当用户关心性格匹配时调用。"""
    return run_input.suggest_assessment(assessment_type)
```

#### 添加到 tools 列表

```python
tools = [
    sync_requester_persona_memory,
    propose_requester_profile_update,
    search_partner_candidates,
    create_saved_search_subscription_from_last_search,
    reply_to_user,
    show_candidates,
    suggest_assessment,  # 新增
]
```

---

### 2. service_integrations.py

#### 添加实现函数

```python
def suggest_assessment_with(
    profile_id: int,
    assessment_type: str,
) -> dict[str, Any]:
    """检查用户测评状态，返回引导卡片或性格信息。"""
    
    # 1. 查询用户的性格特质
    traits = load_traits_for_discovery(profile_id)
    
    # 2. 检查是否已完成指定类型的测评
    mbti_type = traits.get("mbti", {}).get("type_code")
    
    if assessment_type == "mbti_16":
        if mbti_type:
            # 已完成：返回性格信息
            return {
                "completed": True,
                "assessment_type": "mbti_16",
                "type_code": mbti_type,
                "summary": f"你是{mbti_type}型",
                "dimension_scores": traits.get("mbti", {}).get("scores", {}),
            }
        else:
            # 未完成：返回引导卡片
            return {
                "completed": False,
                "suggest": True,
                "assessment_type": "mbti_16",
                "card": {
                    "card_type": "assessment_suggest",
                    "assessment_type": "mbti_16",
                    "title": "MBTI性格测试",
                    "description": "了解你的性格类型，让匹配更精准",
                    "duration": "约5分钟",
                    "reward": "匹配准确度提升30%",
                    "action_label": "开始测评",
                    "action_id": "start_mbti_assessment",
                },
            }
    
    # 其他测评类型类似处理...
    
    return {"completed": False, "suggest": False}
```

---

### 3. service.py

#### 在 run_input 构建中添加

```python
run_input = DiscoveryRunInput(
    session_id=session.session_id,
    requester_id=session.requester_id,
    profile_id=session.profile_id,
    phase=state.get("phase") or "collecting_preferences",
    criteria_labels=criteria_labels_from_state(state),
    recent_timeline=recent_timeline_from_view(session.view),
    runtime_context=runtime_context,
    search_partner_candidates=lambda criteria, limit: _search_partner_candidates_impl(...),
    sync_requester_persona_memory=lambda patch: _sync_requester_persona_memory_impl(...),
    propose_requester_profile_update=lambda patch_json, evidence: _propose_requester_profile_update_impl(...),
    create_saved_search_subscription_from_last_search=lambda: _create_saved_search_subscription_impl(...),
    suggest_assessment=lambda assessment_type: suggest_assessment_with(session.profile_id, assessment_type),  # 新增
)
```

---

### 4. DISCOVERY_AGENT_SOUL.md

#### 添加软约束

```markdown
### 2. 主动建议

- 理解用户意图，不只是执行命令
- 当用户多次表达相似不满时，主动提出调整建议

#### 性格匹配建议

当用户关心性格匹配时（如提到"性格不合适"、"想要活泼开朗的"）：
- **可以引导用户完成自己的性格测试**
- 使用 `suggest_assessment` 工具检查用户测评状态
- 未完成：引导用户做测评，让匹配更精准
- 已完成：告诉用户他的性格类型，解释匹配逻辑

示例：
> "你提到性格匹配很重要。要不要测一下你的MBTI？这样我能更精准地帮你找合适的人。"
```

---

### 5. 前端改动

#### view_models.py - 添加卡片类型

```python
def build_assessment_suggest_card(card_data: dict[str, Any]) -> dict[str, Any]:
    """构建测评引导卡片。"""
    return {
        "kind": "assessment_suggest",
        "id": f"assessment-suggest-{card_data.get('assessment_type')}",
        "assessment_type": card_data.get("assessment_type"),
        "title": card_data.get("title"),
        "description": card_data.get("description"),
        "duration": card_data.get("duration"),
        "reward": card_data.get("reward"),
        "action": {
            "label": card_data.get("action_label"),
            "action_id": card_data.get("action_id"),
        },
    }
```

#### discover-page.tsx - 渲染卡片

```tsx
if (item.kind === 'assessment_suggest') {
  return (
    <div className="rounded-lg border border-primary/20 bg-primary/5 p-4">
      <div className="flex items-start gap-3">
        <Brain className="h-5 w-5 text-primary" />
        <div className="flex-1">
          <h3 className="font-medium">{item.title}</h3>
          <p className="text-sm text-muted-foreground mt-1">{item.description}</p>
          <div className="flex items-center gap-2 mt-2 text-xs text-muted-foreground">
            <span>⏱ {item.duration}</span>
            <span>🎁 {item.reward}</span>
          </div>
          <button
            onClick={() => onOpenAssessment(item.assessment_type)}
            className="mt-3 rounded-full bg-primary px-4 py-2 text-sm text-primary-foreground"
          >
            {item.action.label}
          </button>
        </div>
      </div>
    </div>
  )
}
```

---

## 测试方案

### 1. Tool 单元测试

```python
def test_suggest_assessment_returns_card_when_not_completed():
    """未完成测评时返回引导卡片。"""
    run_input = DiscoveryRunInput(
        suggest_assessment=lambda _type: {
            "completed": False,
            "suggest": True,
            "card": {"title": "MBTI性格测试"},
        }
    )
    
    result = run_input.suggest_assessment("mbti_16")
    
    assert result["completed"] == False
    assert result["suggest"] == True
    assert "card" in result
```

### 2. Agent 行为测试

```python
def test_agent_suggests_assessment_when_user_mentions_personality():
    """用户提到性格匹配时，Agent引导做测评。"""
    # 模拟用户说"性格上不合适"
    result = runtime.run_turn(
        run_input,
        user_message="性格上不太合适",
    )
    
    # 验证：Agent应该调用suggest_assessment工具
    # 或者回复中包含引导做测评的内容
```

### 3. 端到端测试

```python
def test_full_flow_assessment_suggestion():
    """完整流程测试：
    1. 用户说"性格不合适"
    2. Agent追问"理想的性格"
    3. 用户回答后，Agent引导做测评
    4. 前端渲染测评卡片
    5. 用户点击开始测评
    """
```

---

## 交互流程示例

### 场景1：用户未完成测评

```
用户："性格上也不合适"
Agent："能说说你理想的性格是什么样的吗？"
用户："想要更活泼开朗的"
Agent调用suggest_assessment("mbti_16") → 返回引导卡片
Agent："你提到性格匹配很重要。建议你先做个MBTI测试，这样我能更精准地帮你找合适的人。"
前端渲染：[MBTI性格测试卡片] + [开始测评]按钮
```

### 场景2：用户已完成测评

```
用户："性格上也不合适"
Agent："能说说你理想的性格是什么样的吗？"
用户："想要更活泼开朗的"
Agent调用suggest_assessment("mbti_16") → 返回"你是INTJ型"
Agent："你是INTJ型（内向型），想要活泼开朗的E型女生。这个组合不错——内向的你需要外向的她来带动节奏。我帮你调整匹配方向。"
```

---

## 评估指标

| 指标 | 目标 |
|------|------|
| 测评完成率 | 提升30%（从10% → 13%） |
| 匹配准确度 | 提升20%（基于性格双向匹配） |
| 用户满意度 | 提升15%（更精准的推荐） |
| Agent引导成功率 | 60%用户点击"开始测评" |

---

## 风险与对策

| 飴险 | 对策 |
|------|------|
| 用户反感引导 | 软约束：Agent自主判断时机，不强推 |
| 测评太长 | 默认推荐MBTI（5分钟），其他测评可选 |
| 用户已完成测评 | Tool返回已完成状态，Agent直接解释匹配逻辑 |

---

## 实施步骤

1. **Phase 1：Tool定义**（1天）
   - agent_runtime.py 添加 suggest_assessment Tool
   - service_integrations.py 实现测评状态检查

2. **Phase 2：前端渲染**（1天）
   - view_models.py 添加测评引导卡片类型
   - discover-page.tsx 渲染卡片

3. **Phase 3：SOUL.md更新**（半天）
   - 添加性格匹配建议的软约束

4. **Phase 4：测试验证**（1天）
   - 单元测试
   - Agent行为测试
   - 端到端测试

5. **Phase 5：上线验证**（1周）
   - 监控测评完成率
   - 监控匹配准确度

---

## 总结

### 核心设计原则

1. **Agent Native架构**：
   - Tool执行硬约束（检查测评状态）
   - Prompt表达软约束（引导时机）

2. **双向匹配**：
   - 知道用户性格 + 候选人性格
   - 匹配逻辑更精准

3. **渐进式引导**：
   - 不强制用户做测评
   - Agent自主判断时机
   - 用户可以选择跳过

### 一句话总结

**通过Tool让Agent能够检查测评状态并返回引导卡片，实现双向性格匹配。**