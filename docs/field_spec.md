# Discovery 候选人卡片字段规范

## 文档说明

本文档定义了后端返回给前端的候选人卡片字段规范，确保字段命名统一、类型一致。

---

## 候选人卡片核心字段（必须）

| 字段名 | 类型 | 说明 | 示例值 | 前端用途 |
|--------|------|------|--------|---------|
| `card_id` | string | 卡片唯一标识 | `"candidate-123"` | 前端路由、缓存key |
| `profile_id` | int | 用户画像ID | `123` | 点击跳转、API调用 |
| `title` | string | 卡片标题（姓名+年龄） | `"张三 28"` | 卡片头部显示 |
| `subtitle` | string | 卡片副标题（城市·职业·学历） | `"苏州 · 工程师 · 本科"` | 卡片副标题显示 |
| `match_score` | float | 匹配分数（0-1） | `0.85` | 分数展示、排序 |
| `reason_summary` | string | 推荐理由（一句话） | `"性格温柔，符合你的要求"` | 推荐理由展示 |
| `cover_image_url` | string | 封面图片URL | `"https://..."` | 卡片封面图 |

---

## 性格匹配相关字段（可选）

| 字段名 | 类型 | 说明 | 示例值 | 前端用途 |
|--------|------|------|--------|---------|
| `personality_match_context` | dict | 性格匹配上下文 | `{mbti: "INTJ", ...}` | 性格匹配详情展示 |
| `personality_availability` | dict | 性格数据可用性 | `{mbti: true, ...}` | 判断是否显示性格标签 |
| `personality_reasons` | list[str] | 性格匹配理由列表 | `["温柔", "内向"]` | 性格标签展示 |
| `personality_reasoning` | dict | 性格推理详情 | `{summary: "..."}` | 性格匹配详情页 |
| `personality_bonus` | float | 性格加分 | `0.15` | 性格分数展示 |
| `base_score` | float | 基础分数 | `0.70` | 分数分解展示 |
| `personality_scoring_trace` | dict | 性格评分追踪 | `{steps: [...]}` | 评分详情页 |

### personality_match_context 结构

```python
{
    "mbti": {
        "type_code": "INTJ",  # MBTI类型代码
        "type_name": "建筑师",  # MBTI类型名称
        "confidence": 0.85,  # 置信度
    },
    "attachment": {
        "type_code": "secure",  # 依恋类型代码
        "type_name": "安全型",  # 依恋类型名称
        "confidence": 0.90,
    },
    "values": {
        "top_values": ["家庭", "事业"],  # 价值观前两项
        "confidence": 0.80,
    },
}
```

---

## 其他可选字段

| 字段名 | 类型 | 说明 | 示例值 |
|--------|------|------|--------|
| `trust_badges` | list[str] | 认证标签 | `["实名认证", "学历认证"]` |
| `match_highlights` | list[str] | 匹配亮点 | `["温柔", "苏州"]` |
| `open_profile_action` | dict | 打开详情页动作 | `{type: "open_profile", profile_id: 123}` |

---

## 前端渲染字段（特殊用途）

| 字段名 | 类型 | 说明 | 前端用途 |
|--------|------|------|---------|
| `item_type` | string | 项目类型 | 前端路由判断（如 `"candidate_card"`） |
| `component_type` | string | 组件类型（可选） | 前端组件选择（如 `"candidate_card"`） |

**注意**：
- `item_type` 是前端路由必需字段，后端必须返回
- `component_type` 是可选字段，前端组件内部可自行判断，后端不必强制返回

---

## 字段命名规则

### 1. 命名风格

- **后端字段名**：snake_case（如 `personality_traits`）
- **前端字段名**：保持一致（不转换）
- **禁止改名**：后端返回的字段名，前端不得修改（避免混乱）

### 2. 新增字段流程

1. 在本规范文档中定义新字段（类型、说明、示例）
2. 后端在 `view_models.py` 中添加字段
3. 前端在组件中使用字段（并添加验证）

### 3. 字段废弃流程

1. 标记字段为 `deprecated`（在本文档中）
2. 保留字段3个月（向后兼容）
3. 3个月后正式删除（并通知前端）

---

## 字段验证规范

### 后端验证（在 view_models.py）

```python
def validate_candidate_card(card: dict[str, Any]) -> list[str]:
    """验证候选人卡片字段"""
    errors: list[str] = []

    # 必须字段验证
    required_fields = ["card_id", "profile_id", "title", "subtitle"]
    for field in required_fields:
        if field not in card:
            errors.append(f"缺少必须字段: {field}")

    # 类型验证
    if card.get("profile_id") and not isinstance(card["profile_id"], int):
        errors.append("profile_id 必须是 int 类型")

    if card.get("match_score") and not isinstance(card["match_score"], (int, float)):
        errors.append("match_score 必须是数字类型")

    return errors
```

### 前端验证（在 CandidateCard.tsx）

```typescript
interface CandidateCardProps {
  card_id: string;
  profile_id: number;
  title: string;
  subtitle: string;
  // 可选字段
  personality_match_context?: PersonalityContext;
  personality_reasons?: string[];
}

function CandidateCard({ card }: { card: CandidateCardProps }) {
  // 字段验证
  if (!card.card_id || !card.profile_id) {
    console.error("候选人卡片缺少必须字段", card);
    return <ErrorCard message="数据格式错误" />;
  }

  // 渲染逻辑
  return <div>...</div>;
}
```

---

## 常见错误示例

### 错误1：字段名不一致

```python
# ❌ 错误：后端返回 personality_traits，前端期望 personality_type
card = {
    "personality_traits": {...},  # 后端字段名
    # 前端期望: personality_type
}

# ✅ 正确：后端和前端字段名一致
card = {
    "personality_match_context": {...},  # 后端和前端都使用这个名字
}
```

### 错误2：类型不一致

```python
# ❌ 错误：profile_id 是字符串
card = {
    "profile_id": "123",  # 字符串类型
}

# ✅ 正确：profile_id 是整数
card = {
    "profile_id": 123,  # 整数类型
}
```

### 错误3：缺少必须字段

```python
# ❌ 错误：缺少 title 字段
card = {
    "card_id": "candidate-123",
    "profile_id": 123,
    # 缺少 title
}

# ✅ 正确：包含所有必须字段
card = {
    "card_id": "candidate-123",
    "profile_id": 123,
    "title": "张三 28",
    "subtitle": "苏州 · 工程师",
}
```

---

## 版本管理

| 版本 | 日期 | 变更内容 | 作者 |
|------|------|---------|------|
| 1.0 | 2026-06-17 | 初始版本，定义核心字段和性格字段 | Claude |

---

## 参考文档

- [view_models.py](../external-systems/partner-discovery-system/discovery_system/view_models.py) - 后端字段构建
- [decision_models.py](../external-systems/partner-discovery-system/discovery_system/decision_models.py) - Agent决策模型
- [session-end-to-vector-logic.md](../memory/session-end-to-vector-logic.md) - 向量库写入逻辑