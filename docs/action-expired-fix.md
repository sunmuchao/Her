# 问题定位总结

## 问题：用户点击反馈选项后没有返回候选人卡片

**用户反馈**："帮我换一批" → 系统追问 → 点击"职业不太匹配" → 只返回文案，没有候选人卡片

## 根因：suggested_actions的semantic_payload是空对象

Agent生成反馈选项时没有设置semantic_payload，导致：
1. Agent无法识别这是"反馈选项点击"
2. 不调用submit_rejection_feedback工具
3. 不执行搜索，不返回候选人卡片

## 修复：已修改agent_runtime.py，强制要求semantic_payload必须完整

```json
{
  "label": "职业不太匹配",
  "semantic_payload": {
    "kind": "rejection_feedback",
    "feedback_type": "occupation_mismatch",
    "feedback_text": "职业不太匹配"
  }
}
```

## 需要重启Gateway让Prompt生效

```bash
docker-compose restart gateway
# 或
pkill -f gateway && python -m gateway.main
```

## 验证步骤

重启后测试：
1. 用户说"换一批"
2. 检查suggested_actions的payload是否完整
3. 点击选项后，检查是否返回候选人卡片

**重启后问题应该解决！**
