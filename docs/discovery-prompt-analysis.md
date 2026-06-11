# 发现页提示词完整梳理报告

> **生成时间**: 2026-06-11
> **目的**: 梳理发现页内部逻辑中所有提示词部分的内容，并根据 Agent Native 原则提出改进建议

---

## 一、提示词架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                  SOUL.md（单一真相来源）                      │
│                                                             │
│  ✅ 职责：角色定义 + 核心原则                                 │
│  ✅ 内容：29行简洁角色定义                                    │
│  ✅ 位置：discovery_system/DISCOVERY_AGENT_SOUL.md          │
└─────────────────────────────────────────────────────────────┘
                          ↓ 注入
┌─────────────────────────────────────────────────────────────┐
│              agent_runtime.py（运行时构建）                   │
│                                                             │
│  ✅ _build_discovery_agent_instructions():                  │
│     - 加载 SOUL.md 内容                                     │
│     - 添加简短事件说明（当前事件、用户消息）                   │
│     - 不重复上下文信息（通过工具参数传递）                     │
│                                                             │
│  ✅ _build_runtime_prompt():                               │
│     - 构建运行时上下文（state + memory_summary）             │
│     - 通过 JSON 传递给 Agent，不拼接到 Prompt                │
└─────────────────────────────────────────────────────────────┘
                          ↓ 工具定义
┌─────────────────────────────────────────────────────────────┐
│              工具层（8个核心工具）                            │
│                                                             │
│  1. sync_requester_persona_memory - 沉淀长期偏好             │
│  2. propose_requester_profile_update - 更新用户资料          │
│  3. search_partner_candidates - 搜索候选人                  │
│  4. create_saved_search_subscription - 创建订阅             │
│  5. submit_rejection_feedback - 提交拒绝反馈                │
│  6. get_feedback_options - 获取反馈选项                     │
│  7. reply_to_user - 回复对话                                │
│  8. show_candidates - 展示候选人卡片                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、核心提示词内容分析

### 2.1 SOUL.md 完整内容（29行）

**文件**: `external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md`

```markdown
# Her AI 红娘角色定义

## 核心角色
你是 Her 婚恋平台的智能红娘助手"小雅"，帮助用户找到合适的对象。

## 核心原则

### 1. 学习式对话
- 每次拒绝都是学习机会，不要只刷新，要理解原因
- 先答应用户请求，再顺带收集信号

### 2. 主动建议
- 理解用户意图，不只是执行命令
- 当用户多次表达相似不满时，主动提出调整建议

### 3. 诚实透明
- 推荐理由要可解释，调整策略要告知用户
- **当用户对某个维度表达不满时，应该解释该维度的匹配逻辑**

### 4. 安全边界
- 拒绝违规请求，保护用户隐私

---

## 输出风格

- 口语化、自然、像真人红娘
- 根据用户性格调整语气（急性子简洁，慢性子详细）
- 根据会话长度调整详略
```

**设计优点**：
- ✅ **简洁**：29行，符合 Agent Native 原则
- ✅ **单一真相来源**：角色定义集中在一个文件
- ✅ **用自然语言表达原则**：无触发词映射表
- ✅ **软约束在 Prompt 中表达**：如"主动建议"、"诚实透明"

**设计不足**：
- ⚠️ **缺少安全边界详细说明**：仅有一行"拒绝违规请求"
- ⚠️ **缺少决策护栏**：没有置信度阈值、风险分级说明
- ⚠️ **缺少上下文处理指导**：如何利用 state 和 memory_summary

---

### 2.2 工具定义中的提示词（description）

**文件**: `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`

| 工具名称 | description 内容（关键部分） |
|---------|---------------------------|
| `sync_requester_persona_memory` | "同步用户的择偶偏好到长期记忆。当用户说出明确、稳定、适合落库的择偶偏好时调用。沉淀长期偏好，后续推荐更精准。" |
| `propose_requester_profile_update` | "提议更新用户本人的正式资料（年龄、城市、婚姻状态等）。当用户说出个人资料变更时调用。需要用户确认后生效。" |
| `search_partner_candidates` | "搜索候选人。当用户想看推荐、调整搜索条件、表达不满后重新搜索时调用。传入调整后的参数（如 cities、age_min/age_max）。返回匹配的候选人列表。" |
| `create_saved_search_subscription_from_last_search` | "创建订阅，按当前搜索条件持续留意新候选人。当用户想长期关注符合条件的候选人、或者当前搜索无结果时推荐使用。" |
| `submit_rejection_feedback` | "提交拒绝反馈，记录用户对候选人的不满原因。调用场景：用户表达不满、用户点击反馈选项按钮、state.awaiting_rejection_feedback 为 true 时用户回复反馈内容" |
| `get_feedback_options` | "获取反馈选项列表，用于追问用户哪里不合适。调用场景：用户点击'换一批'按钮、需要追问用户不合适原因时、Agent 判断需要收集反馈信号时" |
| `reply_to_user` | "回复用户对话消息，不展示候选人卡片。适用场景：回答用户问题、解释推荐理由、收集用户反馈" |
| `show_candidates` | "展示候选人卡片列表，配合对话回复使用。" |

**设计优点**：
- ✅ **描述能力而非触发词**：如"当用户想看推荐"而非"匹配关键词 '推荐'"
- ✅ **包含使用场景**：明确何时调用
- ✅ **职责分离**：reply_to_user 和 show_candidates 分离

**设计不足**：
- ⚠️ **submit_rejection_feedback 包含调用场景判断**："state.awaiting_rejection_feedback 为 true"这应该在 Agent 层判断，而非工具描述中规定
- ⚠️ **get_feedback_options 包含触发逻辑**："用户点击'换一批'按钮"这是前端事件，不应在工具描述中硬编码

---

### 2.3 硬编码提示词（违反 Agent Native）

#### 2.3.1 feedback_service.py 第108行

**文件**: `external-systems/partner-discovery-system/discovery_system/feedback_service.py`

```python
return {
    "options": options[:6],
    "追问文案": "好的，帮你换一批新的。换之前能简单告诉我上一批哪里不太合适吗？这样我下轮会更准。"
}
```

**问题分析**：
- ❌ **反模式：工具返回预加工**（instruction/output_hint）
- ❌ **决策权被剥夺**：Agent 无法自主决定追问方式
- ❌ **千篇一律**：所有用户看到相同的追问文案

**根因分析**（五问法）：
```
问题现象：追问文案千篇一律
├─ 为什么 1: 追问文案在代码中硬编码
├─ 为什么 2: feedback_service.py 包含输出内容
├─ 为什么 3: 设计理念把工具当成"业务逻辑执行器"
├─ 为什么 4: 未遵循 Agent Native 三层分离原则
└─ 为什么 5: 【根本原因】职责边界模糊，工具越界到 Agent 层
```

#### 2.3.2 StubDiscoveryAgentRuntime 第848-860行

**文件**: `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`

```python
def initial_decision(self, _run_input: DiscoveryRunInput) -> DiscoveryRuntimeResult:
    return DiscoveryRuntimeResult(
        decision=DiscoveryDecision(
            phase="collecting_preferences",
            assistant_message="先跟我说说你想找什么样的人，不用一次讲完整。",
            suggested_actions=[
                DiscoveryActionSuggestion(
                    label="先从城市和年龄说起",
                    style="primary",
                    semantic_payload={"kind": "starter_prompt", "slot": "city_and_age"},
                ),
                DiscoveryActionSuggestion(
                    label="先说你最在意的 3 个条件",
                    semantic_payload={"kind": "starter_prompt", "slot": "top_preferences"},
                ),
            ],
        )
    )
```

**问题分析**：
- ⚠️ **硬编码初始对话**：这是 fallback 逻辑，可接受
- ⚠️ **硬编码按钮文案**：应该由 Agent 自主生成

#### 2.3.3 前端硬编码提示词

**文件**: `frontend/her-app/components/her/discover-page.tsx`

```typescript
<h1 className="font-medium text-foreground">小雅</h1>
<p className="text-xs text-muted-foreground">你的专属红娘</p>
```

**文件**: `frontend/her-app/hooks/use-discovery-session.ts`

```typescript
const [composerPlaceholder, setComposerPlaceholder] = useState('输入你的想法...')
```

**问题分析**：
- ⚠️ **前端硬固定 UI 标签**：应该由后端返回或动态生成
- ⚠️ **composerPlaceholder 未动态更新**：应该根据 Agent 状态变化

---

## 三、改进建议

### 3.1 优先级 1：移除 feedback_service.py 中的硬编码追问文案

**当前问题**：
```python
# ❌ 错误设计
return {
    "options": options[:6],
    "追问文案": "好的，帮你换一批新的。换之前能简单告诉我上一批哪里不太合适吗？这样我下轮会更准。"
}
```

**改进方案**：
```python
# ✅ 正确设计 - 只返回数据
return {
    "options": options[:6],
    "component_type": "FeedbackOptions",  # 前端渲染需要
    # ❌ 移除："追问文案"
}
```

**Agent 如何追问**：
- Agent 根据 `get_feedback_options` 返回的 `options` 自主决定如何追问
- SOUL.md 中已有原则："每次拒绝都是学习机会，不要只刷新，要理解原因"
- Agent 会自然说出类似："好的，帮你换一批新的。换之前能简单告诉我上一批哪里不太合适吗？"

---

### 3.2 优先级 2：优化 SOUL.md 内容

**当前问题**：
- 缺少安全边界详细说明
- 缺少决策护栏
- 缺少上下文处理指导

**改进方案**：

```markdown
# Her AI 红娘角色定义

## 核心角色
你是 Her 婚恋平台的智能红娘助手"小雅"，帮助用户找到合适的对象。

## 核心原则

### 1. 学习式对话
- 每次拒绝都是学习机会，不要只刷新，要理解原因
- 先答应用户请求，再顺带收集信号

### 2. 主动建议
- 理解用户意图，不只是执行命令
- 当用户多次表达相似不满时，主动提出调整建议

### 3. 诚实透明
- 推荐理由要可解释，调整策略要告知用户
- 当用户对某个维度表达不满时，应该解释该维度的匹配逻辑

### 4. 安全边界（硬约束）
- 拒绝违规请求（暴力、歧视、欺诈）
- 不泄露用户隐私信息
- 不代用户做重大决策（只建议，不强制）

### 5. 决策护栏
- 高置信度时自主执行（如"换一批"、"调整年龄范围"）
- 低置信度时请求用户确认（如"修改城市"、"删除偏好"）
- 每次推荐后等待用户反馈再继续

---

## 输出风格

- 口语化、自然、像真人红娘
- 根据用户性格调整语气（急性子简洁，慢性子详细）
- 根据会话长度调整详略

---

## 上下文处理

- **state.session**: 当前会话阶段，决定对话策略
- **state.current_results**: 当前展示的候选人，避免重复推荐
- **memory_summary**: 用户长期偏好和近期反馈，优先参考
- **visible_actions**: 用户可点击的按钮，引导用户表达
```

---

### 3.3 优先级 3：优化工具定义

**当前问题**：
- `submit_rejection_feedback` 包含调用场景判断："state.awaiting_rejection_feedback 为 true"
- `get_feedback_options` 包含触发逻辑："用户点击'换一批'按钮"

**改进方案**：

```python
# ❌ 错误设计
"""提交拒绝反馈，记录用户对候选人的不满原因。

调用场景：
- 用户表达不满或说明不合适原因
- 用户点击反馈选项按钮（action_context.kind == 'rejection_feedback'）
- state.awaiting_rejection_feedback 为 true 时用户回复反馈内容
"""

# ✅ 正确设计 - 只描述能力
"""提交拒绝反馈，记录用户对候选人的不满原因。

用途：
- 记录用户对候选人不满的具体原因
- 反馈会沉淀到长期记忆，影响后续推荐
"""
```

```python
# ❌ 错误设计
"""获取反馈选项列表，用于追问用户哪里不合适。

调用场景：
- 用户点击"换一批"按钮（action_context.kind == 'show_more_candidates'）
- 需要追问用户不合适原因时
- Agent 判断需要收集反馈信号时
"""

# ✅ 正确设计 - 只描述能力
"""获取反馈选项列表，用于追问用户哪里不合适。

用途：
- 获取预设的反馈选项（如"年龄不合适"、"距离太远"）
- 选项会根据用户历史反馈动态调整
"""
```

---

### 3.4 优先级 4：前端动态化改进

**当前问题**：
- `composerPlaceholder` 固定为"输入你的想法..."
- UI 标签硬编码"小雅 - 你的专属红娘"

**改进方案**：

#### 3.4.1 composerPlaceholder 应根据会话状态动态变化

```typescript
// ❌ 错误设计 - 固定 placeholder
const [composerPlaceholder, setComposerPlaceholder] = useState('输入你的想法...')

// ✅ 正确设计 - 根据会话状态动态变化
const composerPlaceholder = useMemo(() => {
  if (state.phase === 'collecting_preferences') {
    return '说说你想找什么样的人...'
  } else if (state.phase === 'showing_candidates') {
    return '对这批候选人有什么想法？'
  } else if (state.awaiting_rejection_feedback) {
    return '告诉我哪里不太合适...'
  }
  return '输入你的想法...'
}, [state.phase, state.awaiting_rejection_feedback])
```

#### 3.4.2 UI 标签应由后端返回

```typescript
// ❌ 错误设计 - 硬固定 UI 标签
<h1 className="font-medium text-foreground">小雅</h1>
<p className="text-xs text-muted-foreground">你的专属红娘</p>

// ✅ 正确设计 - 从 session config 获取
<h1 className="font-medium text-foreground">{agentName}</h1>
<p className="text-xs text-muted-foreground">{agentDescription}</p>
```

---

## 四、改进优先级排序

| 优先级 | 问题 | 影响 | 改动范围 |
|-------|------|------|---------|
| **P0** | feedback_service.py 硬编码追问文案 | Agent 千篇一律，失去个性化 | 1 文件（feedback_service.py） |
| **P1** | SOUL.md 缺少安全边界和决策护栏 | Agent 可能越界或决策不当 | 1 文件（DISCOVERY_AGENT_SOUL.md） |
| **P2** | 工具定义包含调用场景判断 | Agent 决策被工具剥夺 | 1 文件（agent_runtime.py） |
| **P3** | 前端 composerPlaceholder 未动态化 | 用户体验不够智能 | 2 文件（前端组件） |
| **P4** | 前端 UI 标签硬编码 | 不够 Generative UI | 2 文件（前端组件） |

---

## 五、架构改进后的效果对比

| 维度 | 当前设计 | 改进后设计 |
|------|---------|-----------|
| **追问文案** | 固定模板，千篇一律 | Agent 根据用户性格、历史反馈自主生成 |
| **工具返回** | 包含 instruction/output_hint | 只返回原始数据（options） |
| **决策权** | 工具判断何时调用 | Agent 根据上下文自主决定 |
| **安全边界** | SOUL.md 仅一行说明 | 详细的安全边界和决策护栏 |
| **前端 placeholder** | 固定文案 | 根据会话状态动态变化 |
| **UI 标签** | 硬固定"小雅" | 从后端配置获取 |

---

## 六、实施步骤建议

### Phase 1：移除硬编码追问文案（最小改动，最大效果）

1. 修改 `feedback_service.py:108`，移除 "追问文案" 字段
2. 修改 `service.py:1959`，不再返回 `prompt_message`
3. 测试 Agent 是否能自主追问（根据 SOUL.md 中的原则）

### Phase 2：优化 SOUL.md

1. 添加安全边界详细说明
2. 添加决策护栏
3. 添加上下文处理指导

### Phase 3：优化工具定义

1. 移除 `submit_rejection_feedback` 中的调用场景判断
2. 移除 `get_feedback_options` 中的触发逻辑

### Phase 4：前端动态化

1. composerPlaceholder 根据会话状态动态变化
2. UI 标签从后端配置获取

---

## 七、诊断检查清单

### System Prompt（SOUL.md）检查

- [x] 是否用自然语言而非触发词映射表？✅ 是
- [x] 是否只保留 5 条以内核心原则？✅ 是（4 条）
- [x] 是否没有输出格式硬性规定？✅ 是
- [x] 是否没有流程步骤硬编码？✅ 是
- [ ] 是否有明确的安全边界？⚠️ 仅一行说明
- [ ] 是否有决策护栏？❌ 缺失

### 工具定义检查

- [x] description 是否描述能力而非触发词？✅ 是
- [ ] 是否只返回原始数据（无 instruction/output_hint）？❌ feedback_service.py 有硬编码追问文案
- [x] 是否不含软约束业务逻辑？✅ 是（筛选、排序在 Agent 层）
- [x] 是否保留硬约束（安全边界）？✅ 是
- [x] 是否保留 component_type？✅ 是

### 职责边界检查

- [x] 规则是否只在一处定义？✅ 是（SOUL.md）
- [x] SOUL.md 和工具 description 是否没有重复规则？✅ 是
- [x] 硬约束和软约束是否分层清晰？✅ 是
- [x] 新开发者是否清楚规则应该写在哪里？✅ 是

### 模型适配检查

- [ ] Prompt 复杂度是否在模型能力范围内？⚠️ 需根据实际使用模型评估
- [ ] 是否测试验证 Agent 能正确理解意图？⚠️ 需实际测试
- [ ] 如果用弱模型，是否做了适配简化？⚠️ 需根据实际情况调整

---

## 八、反模式诊断总结

### 发现的反模式

| 反模式类型 | 发现位置 | 严重程度 |
|-----------|---------|---------|
| **工具返回预加工** | feedback_service.py 第108行 | 🔴 高 |
| **工具包含调用场景判断** | agent_runtime.py 工具定义 | 🟡 中 |
| **前端硬编码 UI** | discover-page.tsx, use-discovery-session.ts | 🟢 低 |

### 未发现的反模式

- ✅ **无触发词映射表**：SOUL.md 用自然语言表达原则
- ✅ **无工具包含业务逻辑**：筛选、排序在 Agent 层
- ✅ **无职责边界模糊**：规则集中在 SOUL.md

---

## 九、相关文件清单

| 文件路径 | 提示词类型 | 重要程度 |
|---------|-----------|---------|
| `external-systems/partner-discovery-system/discovery_system/DISCOVERY_AGENT_SOUL.md` | Agent 角色定义核心提示词 | **最重要** |
| `external-systems/partner-discovery-system/discovery_system/agent_runtime.py` | 运行时提示词构建逻辑、工具描述 | **最重要** |
| `external-systems/partner-discovery-system/discovery_system/feedback_service.py` | 反馈追问文案（硬编码） | 中等 |
| `external-systems/partner-discovery-system/discovery_system/decision_models.py` | 工具参数描述（作为 schema 提示） | 中等 |
| `frontend/her-app/components/her/discover-page.tsx` | 前端 UI 标签、mock fallback 文案 | 低 |
| `frontend/her-app/hooks/use-discovery-session.ts` | composerPlaceholder 默认值、mock fallback 文案 | 低 |
| `frontend/her-app/app/layout.tsx` | 页面标题 | 低 |
| `docs/discovery-agent-context-optimization-plan.md` | 文档：prompt 结构设计说明 | 参考 |
| `docs/archive/discovery-agent-native-architecture-plan-20260514.md` | 文档：架构规划说明 | 参考 |

---

## 十、下一步行动建议

**建议从 P0（移除 feedback_service.py 硬编码追问文案）开始**，这是最小改动、最大效果的改进点。

### 具体行动：

1. **立即执行**：移除 `feedback_service.py` 中的 "追问文案" 字段
2. **短期规划**：优化 SOUL.md，添加安全边界和决策护栏
3. **中期规划**：优化工具定义，移除调用场景判断
4. **长期规划**：前端动态化改造

---

**文档维护说明**：此文档应随着改进实施进度同步更新，记录每个改进点的实施状态和效果验证结果。