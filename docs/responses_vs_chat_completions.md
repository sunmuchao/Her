# Responses模式 vs Chat Completions模式详解

**生成时间**: 2026-06-23

---

## 📖 什么是Responses模式？

### Responses API

**官方定义**: OpenAI Responses API是OpenAI专门为Agent场景设计的新一代API。

**核心特点**:
1. **专为Agent设计**: 支持多轮对话、工具调用、状态管理
2. **Structured Output原生支持**: 强制LLM返回特定格式的JSON
3. **状态管理**: 支持`previous_response_id`，Agent SDK自动管理对话历史
4. **工具调用增强**: 支持parallel tool calls、tool output streaming
5. **更好的兼容性**: 专门为Agent SDK的output_type设计

**API Endpoint**: `/v1/responses`

**适用场景**:
- ✅ Agent应用（需要LLM自主决策）
- ✅ 需要structured output
- ✅ 需要状态管理和对话历史
- ✅ 需要复杂的工具调用逻辑

---

### Chat Completions API

**官方定义**: OpenAI Chat Completions API是传统的对话补全API。

**核心特点**:
1. **通用对话**: 适用于所有对话场景
2. **Message-based**: 通过messages数组管理对话历史
3. **Function Calling**: 支持function calling，但不如Responses增强
4. **JSON Mode**: 通过`response_format={"type": "json_object"}`要求JSON输出
5. **更广泛支持**: 所有OpenAI兼容的API都支持（包括百炼、DeepSeek等）

**API Endpoint**: `/v1/chat/completions`

**适用场景**:
- ✅ 简单对话场景
- ✅ 需要兼容非OpenAI API（百炼、DeepSeek）
- ✅ 不需要Agent SDK的状态管理
- ❌ 不适合需要严格structured output的Agent场景

---

## 🔄 关键区别对比表

| 特性 | Responses API | Chat Completions API |
|------|--------------|---------------------|
| **API Endpoint** | `/v1/responses` | `/v1/chat/completions` |
| **设计目标** | Agent应用 | 通用对话 |
| **Structured Output** | ✅ 原生支持（output_type） | ⚠️ 需要JSON mode |
| **状态管理** | ✅ 自动管理（previous_response_id） | ❌ 需手动管理messages |
| **工具调用** | ✅ 增强（parallel calls、streaming） | ⚠️ 基础支持 |
| **Agent SDK兼容** | ✅ 完美兼容 | ⚠️ 需要额外配置 |
| **第三方兼容** | ❌ 仅OpenAI官方支持 | ✅ 所有兼容API支持 |
| **百炼支持** | ❌ 不支持responses endpoint | ✅ 支持（coding.dashscope） |
| **DeepSeek支持** | ❌ 不支持 | ✅ 支持 |

---

## 🎯 为什么我们的Agent出现JSON格式错误？

### 问题分析

**当前配置**:
```
HER_DISCOVERY_AGENT_WIRE_API=chat_completions  # 使用chat_completions模式
HER_DISCOVERY_AGENT_BASE_URL=https://coding.dashscope.aliyuncs.com/v1  # 百炼API
HER_DISCOVERY_AGENT_MODEL=qwen3.7-plus  # 百炼模型
```

**Agent SDK代码**:
```python
agent = Agent(
    name="discovery_matchmaker",
    output_type=DiscoveryDecisionModel,  # ✅ 要求返回Decision格式
    ...
)
```

**冲突原因**:
1. Agent SDK默认使用Responses API的structured output机制
2. 但coding.dashscope不支持Responses API（只有chat_completions）
3. Chat Completions模式下，Agent SDK无法强制LLM返回特定格式
4. 所以LLM自由发挥，返回了runtime_input而不是Decision

---

## 🔧 解决方案对比

### 方案A: 切换到Responses模式（不推荐）

**优点**:
- ✅ Agent SDK完美支持
- ✅ Structured output原生支持

**缺点**:
- ❌ coding.dashscope不支持responses endpoint
- ❌ 需要切换到标准OpenAI API（可能更贵）
- ❌ 失去百炼API的优势

**可行性**: ❌ 不可行（coding.dashscope不支持）

---

### 方案B: 保持chat_completions + 调整Prompt（推荐）

**优点**:
- ✅ coding.dashscope支持
- ✅ 保持百炼API优势
- ✅ 可行性强

**缺点**:
- ⚠️ 需要调整Prompt
- ⚠️ 可能不够严格（LLM可能偏离格式）

**实施步骤**:
1. 在System Prompt中明确要求返回Decision格式
2. 提供JSON schema示例
3. 使用JSON mode强制JSON输出
4. 添加fallback解析逻辑

**代码示例**:
```python
# agent_runtime.py
instructions = """
你是智能红娘助手。

重要：你必须返回以下JSON格式的Decision：
{
  "phase": "collecting_preferences" | "searching" | "results_shown" | "refining_criteria",
  "assistant_message": "你的回复文字",
  "suggested_actions": [...],
  "candidate_selection": [...],
  "criteria_changes": [...]
}

不要返回其他格式，不要返回runtime_input内容。
"""

# Agent配置
agent = Agent(
    instructions=instructions,
    output_type=DiscoveryDecisionModel,  # Agent SDK会尝试解析
    ...
)
```

---

### 方案C: 使用Chat Completions的JSON Mode（推荐）

**优点**:
- ✅ coding.dashscope支持
- ✅ 强制JSON输出
- ✅ 可行性强

**缺点**:
- ⚠️ 无法强制特定schema（只能强制JSON格式）
- ⚠️ 需要额外的解析和验证逻辑

**实施步骤**:
1. 在Agent SDK中设置`response_format={"type": "json_object"}`
2. Prompt明确要求Decision格式
3. 添加fallback解析逻辑（如果格式不对）

**代码示例**:
```python
# 可能需要修改Agents SDK的调用方式
# 或者等待Agent SDK支持chat_completions的JSON mode
```

---

### 方案D: 切换到标准百炼API（可选）

**优点**:
- ✅ 标准百炼API可能支持responses endpoint
- ✅ 保持百炼API优势

**缺点**:
- ⚠️ 需要验证标准百炼是否支持responses
- ⚠️ 可能需要更换API key

**配置修改**:
```bash
HER_DISCOVERY_AGENT_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
HER_DISCOVERY_AGENT_WIRE_API=responses  # 尝试responses模式
```

---

## 📊 推荐优先级

| 方案 | 优先级 | 可行性 | 推荐理由 |
|------|--------|--------|---------|
| **方案B** | P0（推荐） | ✅ 高 | 可行性强，保持百炼优势 |
| **方案D** | P1（可选） | ⚠️ 中 | 需要验证百炼responses支持 |
| **方案C** | P2（备选） | ⚠️ 中 | 需要额外解析逻辑 |
| **方案A** | ❌ 不推荐 | ❌ 低 | coding.dashscope不支持 |

---

## 🎯 立即行动建议

**建议**: 优先实施方案B（调整Prompt）

**理由**:
1. 可行性最高
2. 保持coding.dashscope优势
3. 修改成本低（只需调整Prompt）
4. 可以立即测试验证

**实施步骤**:
1. 修改`DISCOVERY_AGENT_SOUL.md`或instructions构建函数
2. 明确要求返回Decision JSON格式
3. 提供schema示例
4. 测试验证

---

## 📝 参考资料

- OpenAI Responses API官方文档: https://platform.openai.com/docs/api-reference/responses
- OpenAI Agents SDK源码: `/agents/models/openai_responses.py`
- 百炼API兼容性文档: https://help.aliyun.com/document_detail/2712195.html

---

## 结论

**Responses模式**: OpenAI专门为Agent设计的API，原生支持structured output和状态管理。

**Chat Completions模式**: 传统对话API，兼容性强但structured output支持较弱。

**当前问题**: coding.dashscope不支持responses，导致Agent SDK无法强制LLM返回Decision格式。

**推荐方案**: 调整Prompt明确要求Decision格式（方案B），保持coding.dashscope优势。