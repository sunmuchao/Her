# 架构清理：统一换一批按钮语义

## 清理日期
2026-06-09

## 清理范围
移除 `refine_candidates` 的"换一批"语义，统一使用 `show_more_candidates`

## 清理原因

### 业务规则冲突
SOUL.md 明确要求"每次换一批都追问"，但 `refine_candidates` 不会触发追问，违反业务规则。

### 语义重叠
两个按钮语义重叠，职责边界模糊，违反单一真相来源原则。

### 无实际使用场景
检查发现 `refine_candidates` 只在测试用例和模型定义中使用，无实际生产代码使用。

## 清理方案：标记为废弃

### 为什么标记为废弃而非删除

| 原因 | 说明 |
|------|------|
| **向后兼容** | 可能有旧数据中使用 `refine_candidates` |
| **安全清理** | 避免删除模型定义导致解析错误 |
| **渐进式迁移** | 给团队时间清理旧数据 |

### 清理内容

#### 1. decision_models.py
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

#### 2. agent_runtime.py
- 移除对 `refine_candidates` 的引用
- 所有示例改为 `show_more_candidates`
- 明确标记为废弃

#### 3. tests/test_discovery_system.py
- 更新测试用例名称和说明
- 补充废弃标记说明
- 补充新的推荐测试用例

## 统一后的架构

### 单一真相来源

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

## 测试验证

```bash
$ python -m pytest external-systems/partner-discovery-system/tests/test_discovery_system.py -k "refine_candidates or show_more_candidates" -xvs

4 passed, 42 deselected in 3.06s
```

所有测试通过，包括：
- `test_batch_refresh_action_with_show_more_candidates_triggers_feedback_prompt`
- `test_discovery_action_suggestion_model_supports_deprecated_refine_candidates_hint`
- `test_discovery_action_suggestion_model_supports_deprecated_refine_candidates_payload`
- `test_discovery_action_suggestion_model_supports_show_more_candidates_for_batch_refresh`

## 后续维护建议

1. **如有旧数据中使用 `refine_candidates`**：可忽略但不应创建新的
2. **Agent指导检查**：确保所有示例使用 `show_more_candidates`
3. **定期清理**：如有机会，可清理数据库中的旧 `refine_candidates` 按钮
4. **文档维护**：补充废弃说明，提醒新开发者不要使用

## 架构原则遵循

### Agent Native原则
- ✅ Agent自主决策，但遵循业务规则约束（硬约束）
- ✅ 单一真相来源，避免规则分散
- ✅ 职责边界清晰，不越界

### 单一真相来源原则
- ✅ 业务规则只在一处定义（SOUL.md）
- ✅ Agent指导引用业务规则，不独立定义
- ✅ 代码实现遵循业务规则，不偏离

## 相关文档

- [BATCH_REFRESH_BUTTON_FIX.md](./BATCH_REFRESH_BUTTON_FIX.md)：详细修复说明
- [../DISCOVERY_AGENT_SOUL.md](../DISCOVERY_AGENT_SOUL.md)：业务规则定义
- [../agent_runtime.py](../agent_runtime.py)：Agent指导实现
- [../decision_models.py](../decision_models.py)：数据模型定义