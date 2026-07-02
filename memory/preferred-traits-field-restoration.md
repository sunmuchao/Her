---
name: preferred-traits-field-restoration
description: 恢复 preferred_traits 和 disliked_traits 字段（修复 m0009 分类错误）
metadata:
  type: feedback
---

## 问题现象

前端保存标签失败：`Unknown column 'preferred_traits' in 'field list'`

## 根因分析（五问法）

```
问题现象：保存标签失败，数据库报错 "Unknown column 'preferred_traits'"
├─ 为什么 1: 数据库表中没有 preferred_traits 字段
├─ 为什么 2: 迁移 m0009 删除了 preferred_traits 字段
├─ 为什么 3: 迁移认为 preferred_traits 是"不可量化字段"，不应存储在 persona 表
├─ 为什么 4: 架构要求不可量化字段存储在向量库或摘要表
└─ 为什么 5: 【根本原因】架构分类错误：标签数组应归类为"tags"（可量化字段）
```

## 架构澄清

m0009 注释明确："Persona table should only contain quantifiable fields (numeric ranges, enums, booleans, locations, **tags**)"

**关键矛盾**：
- `preferred_traits` 和 `disliked_traits` 是标签数组（如 `["情绪稳定", "生活规律"]`）
- 应归类为"tags"（可量化字段），而非"不可量化字段"
- 业务逻辑依赖这些字段（匹配、前端编辑）

## 修复方案

1. **创建反向迁移** `m0013_restore_trait_tag_fields.py`
2. **手动添加字段**（立即恢复功能）
3. **保留迁移文件**（记录架构澄清）

## 业务依赖统计

- 14处业务代码依赖 `preferred_traits`
- `reciprocal_preferences.py` 使用它构建 `matcher_preferences`
- 前端 `profile-page.tsx` 有编辑标签功能

## Why

m0009 的分类逻辑有误：虽然"性格特质偏好"听起来主观，但从数据结构看是标签数组，应归类为可量化字段。删除导致业务功能中断。

## How to apply

1. **迁移分类时，区分数据结构和业务含义**：
   - 数据结构：标签数组 → 可量化
   - 业务含义：主观描述 → 不可量化

2. **删除字段前，必须检查业务依赖**：
   - 使用 `grep -r "field_name" --include="*.py"` 检查代码依赖
   - 确认前端是否有相关功能

3. **架构文档必须明确分类标准**：
   - "tags"应包含所有标签数组字段
   - 不能因业务含义"主观"而归为不可量化

[[candidate-filtering-bug-fix]] — 类似问题：架构重构未同步代码导致功能失效