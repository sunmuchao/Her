# 换一批按钮语义修复说明

## 问题诊断

### 问题现象
用户点击"换一批"按钮，Agent直接返回新推荐，跳过了询问反馈的环节。

### 根本原因
**设计冲突**：存在两个语义重叠的按钮（refine_candidates vs show_more_candidates），职责边界模糊，违反单一真相来源原则。

### 证据链

1. **Agent Runtime 指导**（agent_runtime.py:905）：
   ```python
   suggested_actions_json: [{"label":"换一批","style":"secondary","semantic_payload":{"kind":"refine_candidates"}}]
   ```
   明确指导Agent返回 `refine_candidates` 类型的"换一批"按钮。

2. **Service 处理逻辑**（service.py:392-405）：
   ```python
   if action_kind == "show_more_candidates":
       runtime_result = self._build_batch_refresh_prompt_result(run_input)  # ✅ 会追问
   elif action_kind == "rejection_feedback":
       runtime_result = self._force_rejection_feedback_turn(...)  # ✅ 处理反馈
   else:
       runtime_result = self.runtime.run_turn(...)  # ❌ refine_candidates走这里，直接调Agent
   ```
   只对 `show_more_candidates` 做追问，`refine_candidates` 直接走Agent决策。

3. **SOUL.md 设计意图**（第32-44行）：
   ```markdown
   当用户说"换一批"、"重新找"、"再看几位"时：

   **追问策略**：
   - **每次"换一批"都追问**：信号收集最大化，快速建立偏好画像
   ```
   明确要求每次换一批都要追问。

## 架构清理：统一为单一按钮

### 设计缺陷分析

| 维度 | `refine_candidates` | `show_more_candidates` |
|------|---------------------|----------------------|
| **设计意图** | 调整特定候选人（有candidates/hint字段） | 纯粹换一批（无额外字段） |
| **Service处理** | else分支 → Agent决策 | 走 `_build_batch_refresh_prompt_result` → 追问 |
| **是否追问** | ❌ 不追问 | ✅ 追问反馈 |
| **Agent指导示例** | 用于"换一批" ❌ | 无明确指导 |
| **实际使用场景** | ❌ 无实际生产代码使用 | ✅ 符合业务规则 |

**关键问题**：
1. 业务规则明确"每次换一批都追问"，不存在"不追问的换一批"场景
2. `refine_candidates` 无实际使用场景，仅为历史遗留
3. 两个按钮语义重叠，违反单一真相来源原则

### 清理方案：标记为废弃

#### 1. 保留模型定义（向后兼容）

```python
class DiscoveryRefineCandidatesPayloadModel(BaseModel):
    """
    【已废弃】原设计用于调整特定候选人，但无实际使用场景。

    废弃原因：
    1. 业务规则要求"每次换一批都追问"，不存在"不追问的换一批"场景
    2. 与 show_more_candidates 语义重叠，职责边界模糊
    3. Agent指导已统一为 show_more_candidates

    替代方案：统一使用 show_more_candidates

    保留定义是为了向后兼容（可能有旧数据中使用），但新代码不应使用。
    """
    kind: Literal["refine_candidates"]
    candidates: list[int] | None = Field(default=None, min_length=1)
    hint: str | None = Field(default=None)
```

#### 2. 统一Agent指导

```python
# agent_runtime.py 更新
- semantic_payload.kind 只用这些值：
  - show_more_candidates：换一批（会触发追问反馈）
  - ...
- **"换一批"按钮必须使用 show_more_candidates**，这会触发系统追问上一批哪里不合适。
- **注意**：refine_candidates 已废弃，不要使用。如有旧数据中使用，可忽略但不应创建新的。
```

#### 3. 更新测试用例

```python
# 测试废弃按钮的向后兼容性
def test_discovery_action_suggestion_model_supports_deprecated_refine_candidates_payload(self) -> None:
    """验证废弃的refine_candidates按钮仍能被模型解析（向后兼容）"""
    # 测试代码...

# 测试推荐按钮的正确使用
def test_discovery_action_suggestion_model_supports_show_more_candidates_for_batch_refresh(self) -> None:
    """验证show_more_candidates按钮的正确使用（推荐方式）"""
    # 测试代码...
```

## 修复内容总结

### 核心修复（已完成）

1. **agent_runtime.py 第 850-862 行**：修复 `_prompt_needs_rejection_feedback_mode` 函数
   - 新增检查：`show_more_candidates` 按钮
   - 确保Agent在处理"换一批"按钮时，系统prompt包含反馈闭环指导

2. **agent_runtime.py 第 905、914、1327、946-958 行**：
   - 所有示例改为 `show_more_candidates`
   - 移除对 `refine_candidates` 的引用
   - 明确标记为废弃

3. **decision_models.py 第 84-91 行**：
   - 补充废弃说明文档
   - 保留模型定义（向后兼容）

4. **tests/test_discovery_system.py**：
   - 更新测试用例名称和说明
   - 补充新的推荐测试用例

### 两个按钮的最终状态

| 按钮 | 状态 | 用途 |
|------|------|------|
| `show_more_candidates` | ✅ 推荐使用 | "换一批"按钮，触发追问反馈 |
| `refine_candidates` | ⚠️ 已废弃 | 无实际使用场景，保留定义仅为向后兼容 |

### 为什么标记为废弃而非删除

1. **向后兼容**：可能有旧数据中使用 `refine_candidates`
2. **安全清理**：避免删除模型定义导致解析错误
3. **渐进式迁移**：给团队时间清理旧数据

### 测试验证结果

```bash
$ python -m pytest external-systems/partner-discovery-system/tests/test_discovery_system.py -k "refine_candidates or show_more_candidates" -xvs

4 passed, 42 deselected in 3.06s
```

所有测试通过，包括：
- `test_batch_refresh_action_with_show_more_candidates_triggers_feedback_prompt`
- `test_discovery_action_suggestion_model_supports_deprecated_refine_candidates_hint`
- `test_discovery_action_suggestion_model_supports_deprecated_refine_candidates_payload`
- `test_discovery_action_suggestion_model_supports_show_more_candidates_for_batch_refresh`

## 后续注意事项

1. **Agent指导一致性**：所有示例和指导必须明确使用 `show_more_candidates`
2. **测试覆盖**：确保测试覆盖"换一批"按钮的追问行为
3. **文档同步**：SOUL.md、agent_runtime.py、service.py、decision_models.py 的业务规则定义必须一致
4. **单一真相来源**：业务规则只在一处定义，避免分散导致冲突
5. **废弃清理**：如有旧数据中使用 `refine_candidates`，可忽略但不应创建新的

## 架构原则遵循

### 单一真相来源（Single Source of Truth）

| 规则 | 定义位置 | 是否唯一 |
|------|---------|---------|
| "每次换一批都追问" | SOUL.md | ✅ 业务规则唯一来源 |
| "换一批按钮用 show_more_candidates" | agent_runtime.py | ✅ Agent指导唯一来源 |
| "show_more_candidates 触发追问" | service.py | ✅ 处理逻辑唯一来源 |

### 职责边界清晰化

| 层级 | 职责 | 内容 |
|------|------|------|
| **SOUL.md** | 业务规则定义 | "每次换一批都追问" |
| **agent_runtime.py** | Agent指导 | 示例、指导、废弃说明 |
| **decision_models.py** | 数据模型 | 模型定义、废弃标记 |
| **service.py** | 处理逻辑 | 分支判断、追问实现 |
| **tests/** | 测试验证 | 向后兼容、推荐使用 |

## 修复日期

2026-06-09