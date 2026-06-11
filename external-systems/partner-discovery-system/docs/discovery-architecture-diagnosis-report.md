# 发现页架构诊断报告

> **诊断时间**：2026-06-10  
> **诊断目标**：发现页对话系统（partner-discovery-system）  
> **诊断方法**：五问法根因分析 + Agent Native 反模式识别  

---

## 一、问题现象

**用户反馈**：发现页内部逻辑中太多 if-else，以及提示词含有大量错误以及不必要的东西导致整体发现页的对话显得及其笨重。

**代码现状**：
- `service.py`：2411行，189个if语句
- `agent_runtime.py`：1523行，144个if语句
- `feedback_service.py`：大量硬编码映射表
- 提示词文件中包含大量工具使用规则和输出格式规定

---

## 二、五问法根因分析

```
问题现象：发现页对话笨重、响应不够智能，包含大量 if-else 硬编码逻辑
├─ 为什么 1: 业务逻辑被硬编码在代码中
│   ├─ service.py 第1010-1060行：feedback_type 硬编码调整策略
│   ├─ service.py 第390-403行：action_kind 硬编码分支判断
│   ├─ service.py 第1042-1065行：硬编码回复模板
│   └─ agent_runtime.py 第929-939行：semantic_payload.kind 硬编码值限制
│
├─ 为什么 2: 设计理念停留在"传统软件 + AI"，把 Agent 当规则执行器
│   ├─ FEEDBACK_TO_CRITERIA_ADJUSTMENT 映射表（软约束硬编码）
│   ├─ _feedback_followup_message 函数（回复模板硬编码）
│   └─ action_kind 分支判断（执行路径硬编码）
│
├─ 为什么 3: 没有遵循 Agent Native 架构原则，职责边界不清晰
│   ├─ SOUL.md 定义了软约束规则（反馈类型调整策略）
│   ├─ feedback_service.py 硬编码同样的软约束规则
│   └─ 规则分散在多处，缺少单一真相来源
│
├─ 为什么 4: 缺少单一真相来源，规则在多处重复定义
│   ├─ SOUL.md（软约束规则）+ feedback_service.py（同样规则硬编码）= 重复定义
│   ├─ agent_runtime.py（工具使用规则）+ service.py（执行路径判断）= 职责错位
│   └─ 修改一处可能导致其他地方不一致
│
└─ 为什么 5: 【根本原因】设计理念把 Agent 当成"规则执行器"，而非"决策引擎"

根本对策：遵循 Agent Native 架构原则重构：
1. 职责边界清晰化：SOUL.md（角色原则）+ 工具 description（能力场景）+ Prompt（软约束）
2. 移除硬编码规则：删除 FEEDBACK_TO_CRITERIA_ADJUSTMENT、_feedback_followup_message 模板
3. 简化工具返回：保留原始数据（results + criteria），Agent 自主决定调整策略
4. 单一真相来源：软约束只在 Prompt 中表达，代码只执行硬约束（安全边界）
```

---

## 三、反模式识别诊断

根据 Agent Native 诊断方法论，发现以下 **严重反模式**：

### 🔴 反模式 1：工具包含业务逻辑（最严重）

**识别特征**：
```python
# service.py 第1010-1060行 - 硬编码反馈调整策略（软约束）
if feedback_type == "location_distance" and self_city:
    override["cities"] = [self_city]
elif feedback_type in {"age_gap", "criteria_age"} and self_age is not None:
    override["age_min"] = max(18, self_age - 3)
    override["age_max"] = self_age + 3
elif feedback_type == "work_life_balance":
    ...
```

**问题分析**：
- ❌ 反馈类型调整策略是**软约束**，应该由 Agent 根据上下文自主决策
- ❌ 硬编码了调整逻辑，Agent 无法根据用户性格、历史偏好、具体场景灵活调整
- ❌ 决策权被代码剥夺，Agent 变成"参数传递器"

**修复方向**：
- ✅ 移除 FEEDBACK_TO_CRITERIA_ADJUSTMENT 映射表
- ✅ 工具只返回原始数据（feedback_type + feedback_text + user_profile + current_criteria）
- ✅ Agent 根据 Prompt 中的软约束规则自主决定调整策略

---

### 🔴 反模式 2：职责边界模糊（重复定义）

**识别特征**：
```
规则分散在多处（重复定义）：
├─ SOUL.md 第77-106行：反馈类型到调整策略映射（软约束）
├─ feedback_service.py 第13-130行：FEEDBACK_TO_CRITERIA_ADJUSTMENT（同样规则硬编码）
└─ service.py 第1010-1060行：硬编码调整逻辑（再次重复）
```

**问题分析**：
- ❌ 同一规则在多处定义，修改一处可能导致其他地方不一致
- ❌ Agent 需要遵循多处规则反而困惑（SOUL.md 说一套，代码执行另一套）
- ❌ 缺少单一真相来源，代码和 Prompt 职责错位

**修复方向**：
- ✅ 软约束只在 Prompt 中表达（单一真相来源）
- ✅ 移除 feedback_service.py 中的 FEEDBACK_TO_CRITERIA_ADJUSTMENT
- ✅ service.py 只保留硬约束（安全边界、数据校验）

---

### 🟡 反模式 3：输出模板硬编码

**识别特征**：
```python
# service.py 第1042-1065行 - 硬编码回复模板
if feedback_type == "occupation_mismatch":
    return "明白了,你更在意职业方向。我按这个意思重新筛了一批..."
if feedback_type == "location_distance":
    return "明白了,你更希望距离近一点。我按同城优先重新筛了一批..."
```

**问题分析**：
- ❌ 回复模板化、千篇一律，失去个性化
- ❌ 无法根据用户性格（急性子简洁，慢性子详细）调整语气
- ❌ 无法根据会话长度调整详略

**修复方向**：
- ✅ 移除 _feedback_followup_message 模板函数
- ✅ Agent 根据 Prompt 中的输出风格原则自主生成回复
- ✅ SOUL.md 已经定义了输出风格原则（口语化、自然、个性化），让 Agent 执行

---

### 🟡 反模式 4：硬编码执行路径

**识别特征**：
```python
# service.py 第390-403行 - 硬编码 action_kind 分支
if action_kind == "show_more_candidates":
    runtime_result = self._build_batch_refresh_prompt_result(...)
elif action_kind == "rejection_feedback":
    runtime_result = self._force_rejection_feedback_turn(...)
else:
    runtime_result = self.runtime.run_turn(...)
```

**问题分析**：
- ❌ 执行路径硬编码，Agent 无法根据上下文灵活编排
- ❌ 业务规则（"每次换一批都追问"）应该由 Agent 自主判断，而非代码强制

**修复方向**：
- ✅ 移除 action_kind 硬编码分支
- ✅ 统一走 Agent Runtime，让 Agent 根据 Prompt 自主决策
- ✅ 保留硬约束：安全边界、权限校验

---

### 🟢 未发现反模式：触发词映射表

SOUL.md 中没有发现硬编码触发词映射表，使用自然语言描述场景，这部分设计合理。

---

### 🟢 未发现反模式：工具返回预加工

从 decision_models.py 看，工具返回结构合理，没有 instruction/output_hint 字段，这部分设计合理。

---

## 四、架构对比

| 维度 | 当前设计（反模式） | Agent Native 设计（正确） |
|------|------------------|-------------------------|
| **规则表达** | 代码硬编码（if-else） | Prompt 自然语言表达 |
| **决策主体** | 规则引擎（代码） | LLM Agent |
| **工具职责** | 包含业务逻辑（软约束） | 纯数据查询/执行 |
| **输出方式** | 预设模板 | AI 动态生成 |
| **规则位置** | 分散在多处（重复定义） | 单一真相来源 |

---

## 五、影响分析

| 反模式 | 导致的问题 | 用户感知 |
|--------|-----------|---------|
| **工具包含业务逻辑** | Agent 无法灵活调整策略 | 推荐千篇一律、不够智能 |
| **职责边界模糊** | 代码和 Prompt 冲突 | 对话笨重、响应不符合预期 |
| **输出模板硬编码** | 回复模板化 | 千篇一律、失去个性化 |
| **硬编码执行路径** | Agent 无法自主编排 | 对话流程僵化 |

---

## 六、重构方案设计

基于 Agent Native 架构原则，设计了 **四阶段渐进式重构方案**：

### 📋 Phase 1：职责边界重构（最小改动）

**目标**：明确职责边界，单一真相来源

| 文件 | 改动内容 | 原因 |
|------|---------|------|
| **DISCOVERY_AGENT_SOUL.md** | 移除第77-106行"反馈类型到调整策略映射表" | 软约束应在 Prompt 中表达，而非硬编码在 SOUL.md |
| **DISCOVERY_AGENT_SOUL.md** | 保留核心原则（诚实、学习式对话、主动建议、安全边界） | 正确定位：角色定义 + 核心原则 |
| **agent_runtime.py** | 简化第864-976行 `_build_discovery_agent_instructions()` | 移除过多的工具使用规则和输出格式规定 |
| **agent_runtime.py** | 移除第913-945行硬编码的工具调用规则 | Agent 应自主理解意图，而非遵循硬编码规则 |
| **agent_runtime.py** | 补充工具 description（使用场景描述） | 补充触发信息，让 Agent 自主判断 |

---

### 📋 Phase 2：移除业务逻辑硬编码（核心重构）

**目标**：移除软约束硬编码，让 Agent 自主决策

| 文件 | 移除内容 | 原因 |
|------|---------|------|
| **feedback_service.py** | 移除第13-130行 `FEEDBACK_TO_CRITERIA_ADJUSTMENT` 映射表 | 软约束重复定义，应在 Prompt 中表达 |
| **feedback_service.py** | 移除第133-163行 `SECONDARY_OPTIONS_MAP` 硬编码 | 二级追问触发规则应由 Agent 自主判断 |
| **service.py** | 移除第1010-1060行 feedback_type 硬编码调整逻辑 | 决策权被代码剥夺，Agent 无法灵活调整 |
| **service.py** | 移除第1042-1065行 `_feedback_followup_message` 模板函数 | 回复模板化，失去个性化 |
| **service.py** | 移除第390-403行 action_kind 硬编码分支判断 | 执行路径硬编码，Agent 无法自主编排 |

---

### 📋 Phase 3：工具返回结构简化

**目标**：工具只返回原始数据，Agent 自主加工

| 文件 | 改动内容 |
|------|---------|
| **service.py** | 工具返回改为原始数据：`feedback_type` + `feedback_text` + `user_profile` + `current_criteria` |
| **service.py** | 移除 override 参数硬编码逻辑 |
| **service.py** | Agent 根据 Prompt 中的软约束规则自主决定调整策略 |

---

### 📋 Phase 4：Prompt 重设计（单一真相来源）

**目标**：软约束在 Prompt 中表达，清晰明确

**新增 Prompt 内容**（替代所有硬编码规则）：

```markdown
## 反馈处理策略（软约束）

当用户表达不满或选择反馈选项时，自主决定调整策略：

### 地理位置相关
- 用户说"太远了"、"同城优先" → 调用 search_partner_candidates，传入 cities=[用户所在城市]
- 用户说"考虑苏州的"、"换成杭州" → 调用 search_partner_candidates，传入 cities=["苏州"] 或 ["杭州"]

### 年龄相关
- 用户说"年龄差距大"、"年龄接近" → 根据用户年龄调整 age_min/age_max（缩小范围）
- 例：用户28岁，可设置 age_min=25, age_max=31

### 职业相关
- 用户说"职业不匹配"、"工作太忙" → 调整职业相关筛选参数
- 例：设置 exclude_job_requires_entertaining=true

### 生活节奏相关
- 用户说"太忙太卷"、"生活节奏不匹配" → 降低高强度工作标签权重

### 性格气质相关
- 用户说"性格气质不对" → 强化 MBTI/依恋匹配，可选推荐测评

### 外在条件相关
- 用户说"外在条件不合适" → 追问具体是哪个条件（年龄/学历/收入/城市）

## 输出风格（软约束）

- 口语化、自然、像真人红娘
- 根据用户性格调整语气（急性子简洁，慢性子详细）
- 根据会话长度调整详略（刚开始详细，后面简洁）
- 每次回复保持短，不要写成系统说明
```

---

## 七、约束分层设计

### ✅ 硬约束（保留在代码中）

```python
# 安全边界
if user.is_banned:
    raise PermissionError("用户已被封禁")

# 数据校验
if not feedback_text.strip():
    raise ValueError("反馈内容不能为空")

# 权限校验
if not session.is_active:
    raise PermissionError("会话已关闭")
```

### ✅ 软约束（在 Prompt 中表达）

```markdown
# 反馈处理策略（让 Agent 自主决策）
- 根据反馈类型调整搜索参数
- 根据用户性格和历史偏好灵活调整
- 追问时机自主判断
- 输出风格个性化
```

---

## 八、预期收益

| 维度 | 当前问题 | 重构后收益 |
|------|---------|-----------|
| **智能性** | 推荐千篇一律、调整策略僵化 | Agent 根据上下文灵活调整，更智能 |
| **个性化** | 回复模板化、千篇一律 | Agent 根据用户性格和会话长度调整语气 |
| **可维护性** | 规则分散在多处，修改一处可能导致不一致 | 单一真相来源，修改 Prompt 即生效 |
| **扩展性** | 新增反馈类型需要改多处代码 | 只需在 Prompt 中补充规则 |

---

## 九、风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|---------|
| **Agent 决策不稳定** | 中 | 添加置信度阈值，低置信度时回退到默认策略 |
| **Prompt 复杂度超出模型能力** | 低 | 当前使用 glm-5，Prompt 简化后可适配 |
| **重构影响现有功能** | 中 | 渐进式重构，每阶段验证后再继续 |
| **用户感知变化** | 低 | 用户感知变好（更智能、更个性化） |

---

## 十、关键文件清单

### 核心服务端逻辑文件

| 文件 | 行数 | if语句数 | 问题严重度 |
|------|------|---------|-----------|
| `service.py` | 2411 | 189 | 🔴 严重 |
| `agent_runtime.py` | 1523 | 144 | 🔴 严重 |
| `feedback_service.py` | 343 | 45 | 🟡 中等 |

### 提示词定义文件

| 文件 | 行数 | 问题 |
|------|------|------|
| `DISCOVERY_AGENT_SOUL.md` | 133 | 包含软约束硬编码（反馈类型映射表） |
| `agent_runtime.py` 第864-976行 | 113 | 包含大量工具使用规则和输出格式规定 |

### 工具定义文件

| 文件 | 问题 |
|------|------|
| `decision_models.py` | 返回值结构合理，无反模式 |
| `agent_runtime.py` 第1263-1377行 | 工具定义合理，无反模式 |

---

## 十一、诊断结论

**根本原因**：设计理念把 Agent 当成"规则执行器"，而非"决策引擎"，导致：
1. 业务逻辑被硬编码在代码中（软约束在代码中执行）
2. 职责边界模糊（规则分散在多处，重复定义）
3. 输出模板化（回复千篇一律，失去个性化）
4. 执行路径硬编码（Agent 无法自主编排）

**修复公式**：
```
职责边界清晰化 → 移除硬编码 → 简化工具返回 → 原始数据架构 → 升级适配模型
```

**核心原则**：Agent 是决策大脑，不是规则执行器。

---

## 十二、下一步行动

1. **Phase 1（最小改动）**：职责边界重构，移除 SOUL.md 和 agent_runtime.py 中的硬编码规则
2. **Phase 2（核心重构）**：移除 service.py 和 feedback_service.py 中的业务逻辑硬编码
3. **Phase 3（工具简化）**：工具返回原始数据，Agent 自主加工
4. **Phase 4（Prompt 重设计）**：软约束在 Prompt 中表达，单一真相来源

**建议**：先实施 Phase 1（影响最小），验证效果后再继续后续阶段。