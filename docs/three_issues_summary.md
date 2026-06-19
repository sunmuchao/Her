# 三个问题完整解析总结

## 问题1：AI合并判断失败

**根本原因**：格式化字符串错误，LLM返回的JSON被当作f-string处理

**解决方案**：
1. 在错误日志中使用`repr()`包装异常信息
2. 增强LLM返回验证

**修复位置**：match_domain/session_end_processor.py:887

---

## 问题2：清空working_criteria失败

**根本原因**：字段名错误，代码使用`session_state`，实际字段是`state_json`

**解决方案**：
修改 match_domain/session_end_processor.py:934和962：
```python
SELECT state_json FROM discovery_agent_sessions
UPDATE discovery_agent_sessions SET state_json = ?
```

---

## 问题3：可量化字段被跳过

**根本原因**：策略过于保守，没有区分"明确表达"和"推断"，导致用户明确偏好也被跳过

**解决方案**：
区分字段来源：
- 已知事实(city、age) → source_type="explicit"
- 明确表达(partner_expectation) → source_type="explicit"
- 真正推断(MBTI推测) → source_type="strong_inference"

**修复位置**：
1. match_domain/session_end_processor.py:1115 - 动态设置source_type
2. LLM提炼Prompt - 要求标注字段来源