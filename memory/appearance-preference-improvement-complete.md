---
name: appearance-preference-improvement-complete
description: 外貌偏好学习改进方案落地完成（分离质量和风格，删除颜值平均分逻辑）
metadata:
  type: project
---

# 外貌偏好学习改进方案落地完成

## 📅 完成时间
2026-07-08

## 🎯 问题根因

用户反馈指出两个核心问题：

### 问题1：颜值平均分没有意义
```
错误逻辑：
  用户点了5个候选人（颜值92、88、90、85、89）
  → 系统算平均分88分
  → 系统总结："你偏好颜值88分以上的人"

但这错了！因为：
  - 所有人都喜欢颜值高的（这是共性，不是偏好）
  - 颜值评分已经在候选人基础分里了
  - 真正的偏好应该是"风格偏好"，而不是"质量偏好"
```

### 问题2：颜值重复加分
```
错误逻辑：
  候选人A：颜值92分
    → 基础分：+10分（因为颜值高）
    → 偏好匹配：再+10分（因为你点的人都颜值高）
    → 总分：+20分
    
这是重复加分！颜值分已经算在基础分里了，不应该再算一遍
```

---

## ✅ 改进方案

### 核心原则

**原则1：分离"质量"和"风格"**
```
质量评分（全局，所有人都喜欢）：
  - beauty_score：颜值评分（已在基础分）
  - photo_quality_score：照片质量评分
  - photo_authenticity_score：照片真实性评分
  
风格偏好（个性化，每个人不同）：
  - appearance_keywords：风格标签（清纯、甜妹、成熟、知性等）
```

**原则2：偏好学习只学"风格"，不学"质量"**
```
正确逻辑：
  用户点了5个候选人（清纯甜妹风×4，成熟知性风×1）
  → 系统学"风格偏好：清纯甜妹风"
  → 这才是每个人的真实偏好
```

**原则3：推荐排序分离"基础质量分"和"偏好匹配分"**
```
推荐得分 = 
  基础质量分（包含颜值分） +
  偏好匹配分（只看风格匹配） +
  其他分

注意：偏好匹配分不看颜值高低，只看风格是否匹配
```

---

## 📝 修改清单

### 1. 数据库表结构修改

**迁移脚本**：[m0018_fix_appearance_preference_fields.py](db_migrations/targets/persona/m0018_fix_appearance_preference_fields.py)

**删除错误字段**：
```sql
ALTER TABLE user_appearance_preferences 
  DROP COLUMN preferred_mature_score,
  DROP COLUMN preferred_clean_score,
  DROP COLUMN preferred_gentle_score,
  DROP COLUMN preferred_sunny_score,
  DROP COLUMN preferred_stylish_score;
```

**新增正确字段**：
```sql
ALTER TABLE user_appearance_preferences 
  ADD COLUMN preferred_style_tags JSON COMMENT '偏好的风格标签列表',
  ADD COLUMN preferred_style_weights JSON COMMENT '每个风格标签的权重',
  ADD COLUMN disliked_style_tags JSON COMMENT '明确不喜欢的风格标签列表',
  ADD COLUMN style_preference_summary TEXT COMMENT '风格偏好总结文本',
  ADD COLUMN last_preference_rebuild_at DATETIME COMMENT '最后偏好重建时间';
```

---

### 2. 偏好学习算法修改

**新增函数**：[build_style_preference_from_feedback](match_domain/appearance_features.py:2459-2582)

**核心逻辑**：
```python
# 统计风格标签频率（不是评分平均分）
style_tag_weights = {}
for event in events:
    keywords = candidate["appearance_keywords_json"]
    weight = event_weight × time_decay
    for keyword in keywords:
        style_tag_weights[keyword] += weight

# 提取正向偏好和负向偏好
preferred_tags = [tag for tag, w in style_tag_weights.items() if w > 0]
disliked_tags = [tag for tag, w in style_tag_weights.items() if w < 0]

# 生成偏好总结
summary = "特别喜欢清纯,甜妹风格。不太喜欢成熟,知性风格"
```

---

### 3. 推荐排序算法修改

**新增函数**：[compute_style_preference_bonus](match_domain/appearance_features.py:737-813)

**核心逻辑**：
```python
# 计算风格偏好加分（不看颜值）
bonus = 0.0

# 正向匹配：候选人风格符合用户偏好
for keyword in candidate_keywords:
    if keyword in preferred_weights:
        bonus += preferred_weights[keyword] × 5.0

# 负向匹配：候选人风格不符合用户偏好
for keyword in candidate_keywords:
    if keyword in disliked_tags:
        bonus -= 5.0

return bonus  # 正数=匹配，负数=不匹配
```

---

### 4. 偏好重建触发点修改

**修改文件**：[service.py](external-systems/partner-discovery-system/discovery_system/service.py:2617-2639)

**修改内容**：
```python
# 改前：调用错误的偏好学习函数
rebuild_user_preference_from_history(...)

# 改后：调用正确的偏好学习函数
build_style_preference_from_feedback(...)
```

---

## 🧪 测试验证

**测试脚本**：[test_style_preference_improvement.py](tests/test_style_preference_improvement.py)

**测试结果**：
```
✅ 所有测试通过！改进方案逻辑正确

【测试1】风格偏好学习函数
  ✅ 正确：统计风格标签频率（不是颜值平均分）
  ✅ 正确：清纯出现3次（正向）→ preferred_tags=['清纯']
  ✅ 正确：成熟出现1次（负向）→ disliked_tags=['成熟']
  ✅ 正确：颜值评分不作为偏好维度

【测试2】风格偏好加分函数
  ✅ 正确：候选人A和B颜值相同（92分），但风格偏好加分不同
  ✅ 正确：候选人A（清纯甜妹）→ 加30分
  ✅ 正确：候选人B（成熟知性）→ 减10分
  ✅ 正确：颜值评分不影响偏好加分（已在基础分里）

【测试3】照片加分分解函数（新版本）
  ✅ 正确：质量加分（照片质量+真实性）= 全局加分
  ✅ 正确：风格偏好加分 = 个性化加分
  ✅ 正确：总加分 = 质量加分 + 风格偏好加分
  ✅ 正确：颜值评分不在加分项里（已在基础分）
```

---

## 📊 效果对比

### 修改前（错误逻辑）

```json
{
  "preferred_mature_score": 71,    // 成熟感评分偏好（错误）
  "preferred_gentle_score": 81,    // 温柔感评分偏好（错误）
  "preferred_beauty_score": 88,    // 颜值评分偏好（错误）
  
  "偏好总结": "你偏好颜值88分以上的人",  // 错误总结
  
  "推荐逻辑": {
    "候选人A": {
      "颜值": 92,
      "加分": +20  // 基础分+10 + 偏好匹配+10（重复加分）
    }
  }
}
```

### 修改后（正确逻辑）

```json
{
  "preferred_style_tags": ["清纯", "甜妹", "阳光"],
  "preferred_style_weights": {"清纯": 3, "甜妹": 4, "阳光": 3},
  "disliked_style_tags": ["成熟", "知性"],
  
  "style_preference_summary": "特别喜欢清纯甜妹风格，不太喜欢成熟知性风格",  // 正确总结
  
  "推荐逻辑": {
    "候选人A": {
      "颜值": 92,  // 基础分已包含，不重复加分
      "风格": ["清纯", "甜妹"],
      "加分": +30  // 只加风格匹配分（不看颜值）
    },
    "候选人B": {
      "颜值": 92,  // 基础分已包含，不重复加分
      "风格": ["成熟", "知性"],
      "加分": -10  // 只减风格不匹配分（不看颜值）
    }
  }
}
```

---

## 🎯 大白话总结

### 核心改进

**1. 颜值评分不作为偏好维度**
> 颜值高就像"好吃的"，所有人都喜欢，这不是偏好
> 
> 风格（清纯、甜妹、成熟、知性）就像"口味"，这才是每个人的偏好

**2. 偏好学习只学风格，不学颜值**
> 用户点了5个候选人（清纯甜妹风×4，成熟知性风×1）
> 
> 系统总结："你喜欢清纯甜妹风，不太喜欢成熟知性风"
> 
> 这才是真实偏好！

**3. 推荐排序只看风格匹配，不看颜值高低**
> 候选人A和B颜值都是92分
> 
> 候选人A（清纯甜妹）→ 加30分（风格匹配）
> 
> 候选人B（成熟知性）→ 减10分（风格不匹配）
> 
> 颜值已经在基础分里了，不重复加分

---

## 📋 后续步骤

### 步骤1：运行数据库迁移脚本
```bash
python db_migrations/run_migration.py --target persona --migration m0018
```

### 步骤2：重新构建容器镜像
```bash
docker compose build gateway-internal
docker compose restart gateway-internal
```

### 步骤3：验证改进效果
```bash
python3 tests/test_style_preference_improvement.py
```

---

## 💡 关键洞察

用户提出的两个问题非常敏锐：

1. **颜值平均分没有意义**
   - 所有人都喜欢颜值高的，这不是个性化偏好
   - 真正的偏好应该是"风格偏好"

2. **颜值不应该再加分**
   - 颜值评分已经在候选人基础分里了
   - 不应该在偏好匹配时再加分（重复加分）

这个改进方案解决了这两个问题，让推荐逻辑更合理：
- 颜值评分：全局质量加分（大家都喜欢）
- 风格偏好：个性化偏好加分（每个人不同）

---

## 🔗 相关记忆

- [[photo-analysis-refactor-summary]]：照片分析系统重构（删除硬编码公式，强制AI真实分析）
- [[her-system-complete-logic-overview]]：系统四大核心逻辑完整梳理