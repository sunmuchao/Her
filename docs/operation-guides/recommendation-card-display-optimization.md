# 推荐卡片显示优化方案

## 问题清单

### 1. "25-29岁"含义不明
- **现象**: 用户看到"25-29岁"，不知道是年龄段还是年龄偏好
- **根因**: 后端使用 `_age_bracket()` 将年龄转换为年龄段（bucket），前端直接显示
- **数据来源**: `requester_summary.age_bracket`（格式："25-29岁"）

### 2. "dating"显示英文
- **现象**: 关系目标显示为英文 "dating"
- **根因**: 后端直接使用 `relationship_goal` 的英文枚举值，前端未做映射
- **数据来源**: `requester_summary.relationship_goal`（值："dating"、"marriage"、"friends"）

### 3. 重要信息缺失
- **现象**: 卡片只显示"资料待补充"，缺少学历、身高、匹配点等关键信息
- **根因**: 前端只使用 `occupation` 字段，未充分利用 `requester_summary` 的其他信息
- **数据来源**: `requester_summary` 包含 `education`、`height_bracket`、`matched_on` 等字段

---

## 方案对比

| 维度 | 方案一（前端优化） | 方案二（后端重构） |
|------|-------------------|-------------------|
| **改动范围** | 仅前端（2个文件） | 后端+前端（5个文件） |
| **实施时间** | 1小时 | 3-4小时 |
| **数据一致性** | 前端映射，可能不一致 | 后端统一处理，一致性强 |
| **可维护性** | 前端多处维护映射表 | 后端单一真相来源 |
| **适用场景** | 快速修复，不影响后端 | 长期优化，需要后端配合 |

---

## 方案一：前端优化（推荐）

### 改动文件清单

1. **frontend/her-app/hooks/use-recommendation-inbox.ts** - 数据格式化优化
2. **frontend/her-app/components/her/discover-page.tsx** - 卡片显示优化

### 实施步骤

#### Step 1: 添加关系目标映射表

在 `use-recommendation-inbox.ts` 中添加：

```typescript
// 关系目标中英文映射表
const RELATIONSHIP_GOAL_DISPLAY: Record<string, string> = {
  'dating': '先谈恋爱看',
  'marriage': '奔着结婚去',
  'friends': '找搭子/扩列',
  '认真恋爱': '认真恋爱',
  '结婚导向': '结婚导向',
}

function formatRelationshipGoal(value: string): string {
  return RELATIONSHIP_GOAL_DISPLAY[value] || value || '关系目标待补充'
}
```

#### Step 2: 添加年龄段格式化函数

```typescript
// 年龄段格式化：提取年龄段或显示实际年龄
function formatAgeDisplay(age: number, ageBracket?: string): string {
  // 如果有年龄段，显示为"约25-29岁"
  if (ageBracket) {
    return `约${ageBracket}`
  }
  // 如果有实际年龄，显示年龄
  if (age > 0) {
    return `${age}岁`
  }
  return '年龄待补充'
}
```

#### Step 3: 构建完整信息卡片

修改 `mapProxyIntroCaseToInboxItem` 函数：

```typescript
function mapProxyIntroCaseToInboxItem(caseItem: ProxyIntroCase): InboxItem {
  const requesterSummary = caseItem.outreach_payload?.requester_summary || {}
  const counterpartProfile = caseItem.counterpart_profile || {}

  // 提取基本信息
  const name = requesterSummary.requester_name
    || String(counterpartProfile.display_name || counterpartProfile.name || '')
    || '有人'

  // 年龄显示：优先使用年龄段，否则使用实际年龄
  const ageBracket = requesterSummary.age_bracket
  const actualAge = parseInt(String(counterpartProfile.age || '0')) || 0
  const ageDisplay = formatAgeDisplay(actualAge, ageBracket)

  // 构建完整信息标签
  const infoTags: string[] = []

  // 1. 年龄段（如果有）
  if (ageBracket) {
    infoTags.push(ageBracket)
  }

  // 2. 城市
  const city = requesterSummary.city || String(counterpartProfile.city || '') || ''
  if (city) {
    infoTags.push(city)
  }

  // 3. 职业（如果有）
  const occupation = requesterSummary.occupation
    || String(counterpartProfile.job || counterpartProfile.occupation || '')
  if (occupation) {
    infoTags.push(occupation)
  }

  // 4. 学历（如果有）
  const education = requesterSummary.education || String(counterpartProfile.education || '')
  if (education) {
    infoTags.push(education)
  }

  // 5. 关系目标（映射为中文）
  const relationshipGoal = requesterSummary.relationship_goal
    || String(counterpartProfile.relationship_goal || '')
  if (relationshipGoal) {
    infoTags.push(formatRelationshipGoal(relationshipGoal))
  }

  // 构建 message（完整信息展示）
  const messageParts: string[] = []
  if (infoTags.length > 0) {
    messageParts.push(infoTags.join('；'))
  }
  if (requesterSummary.summary_text) {
    messageParts.push(requesterSummary.summary_text)
  }
  const message = messageParts.join('\n') || `${name}想通过平台进一步认识你`

  return {
    id: String(caseItem.counterpart_profile_id || caseItem.case_id),
    listKey: `case:${caseItem.case_id}`,
    cardId: undefined,
    subscriptionId: undefined,
    recommendationId: undefined,
    candidateId: caseItem.counterpart_profile_id ?? undefined,
    caseId: String(caseItem.case_id),
    name,
    age: actualAge,
    city: city || '未知',
    occupation: occupation || '资料待补充',
    matchScore: 0,
    image: resolveProfileImageUrl(
      requesterSummary.avatar_url
      || String(counterpartProfile.avatar_url || counterpartProfile.photo_url || ''),
      PLACEHOLDER_AVATAR
    ),
    type: 'interest',
    message,  // 使用构建的完整信息
    time: caseItem.created_at || '刚刚',
    isRead: caseItem.case_status !== 'awaiting_reply',
    conversionStage: undefined,
  }
}
```

#### Step 4: 卡片显示优化（可选）

在 `discover-page.tsx` 中优化卡片显示布局，将关键信息分行展示：

```typescript
// 推荐来信卡片显示优化
<div className="bg-card border border-border rounded-xl p-3">
  {/* 基本信息：姓名 + 年龄段 */}
  <div className="flex items-center gap-2">
    <span className="font-medium">{item.name}</span>
    <span className="text-xs text-muted-foreground">{item.ageDisplay}</span>  {/* 年龄段 */}
  </div>

  {/* 关键信息标签 */}
  <div className="flex flex-wrap gap-1 mt-1">
    {item.city && <span className="text-xs">{item.city}</span>}
    {item.occupation && <span className="text-xs">{item.occupation}</span>}
    {item.education && <span className="text-xs">{item.education}</span>}
    {item.relationshipGoal && <span className="text-xs">{item.relationshipGoal}</span>}
  </div>

  {/* 匹配点（如果有） */}
  {item.matchedOn && item.matchedOn.length > 0 && (
    <div className="mt-2">
      <p className="text-xs text-muted-foreground">匹配点：</p>
      <div className="flex flex-wrap gap-1">
        {item.matchedOn.map((point, idx) => (
          <span className="px-2 py-0.5 text-xs bg-primary/10 rounded">{point}</span>
        ))}
      </div>
    </div>
  )}
</div>
```

---

## 方案二：后端重构（长期优化）

### 改动文件清单

1. **matchmaking_system/proxy_intro_core.py** - 添加中文映射逻辑
2. **frontend/her-app/hooks/use-recommendation-inbox.ts** - 数据格式化优化
3. **frontend/her-app/components/her/discover-page.tsx** - 卡片显示优化
4. **match_domain/onboarding_search.py** - 统一映射表定义
5. **outer_system_mysql_schema.py** - 数据库字段扩展（可选）

### 实施步骤

#### Step 1: 后端统一映射表

在 `onboarding_search.py` 中定义统一映射表：

```python
# 关系目标中英文映射（单一真相来源）
RELATIONSHIP_GOAL_DISPLAY_CN: dict[str, str] = {
    "dating": "先谈恋爱看",
    "marriage": "奔着结婚去",
    "friends": "找搭子/扩列",
    "认真恋爱": "认真恋爱",
    "结婚导向": "结婚导向",
    "认真相处": "认真相处",
    "long_term": "长期关系",
}

def format_relationship_goal_cn(value: str | None) -> str | None:
    """格式化关系目标为中文显示"""
    if not value:
        return None
    return RELATIONSHIP_GOAL_DISPLAY_CN.get(value, value)
```

#### Step 2: 后端构建摘要时使用映射

修改 `build_requester_safe_summary` 函数：

```python
def build_requester_safe_summary(subscription: dict[str, Any]) -> dict[str, Any]:
    """构建发起方信息摘要，使用中文映射"""
    self_profile = json_loads(subscription.get("self_profile_json"), {})

    # 格式化年龄段：添加"约"前缀，提升可读性
    age_bracket_raw = _age_bracket(self_profile.get("age"))
    age_bracket_display = f"约{age_bracket_raw}" if age_bracket_raw else None

    # 格式化身高段：添加"约"前缀
    height_bracket_raw = _height_bracket(self_profile.get("height"))
    height_bracket_display = f"约{height_bracket_raw}" if height_bracket_raw else None

    # 格式化关系目标：使用中文映射
    relationship_goal_raw = self_profile.get("relationship_goal")
    relationship_goal_display = format_relationship_goal_cn(relationship_goal_raw)

    safe_summary = {
        "requester_name": self_profile.get("display_name") or self_profile.get("name") or "有人",
        "age_bracket": age_bracket_display,  # 使用格式化后的值
        "city": self_profile.get("city") or self_profile.get("settlement_city"),
        "height_bracket": height_bracket_display,  # 使用格式化后的值
        "education": self_profile.get("education"),
        "occupation": self_profile.get("job") or self_profile.get("occupation"),
        "relationship_goal": relationship_goal_display,  # 使用中文映射
        "matched_on": [],  # TODO: 从 subscription 的 criteria 中提取匹配点
        "subscription_title": subscription.get("title"),
        "avatar_url": self_profile.get("avatar_url") or self_profile.get("photo_url"),
    }

    # 构建 summary_text：使用中文值拼接
    safe_summary["summary_text"] = "；".join(
        part for part in [
            safe_summary["age_bracket"],
            safe_summary["city"],
            safe_summary["education"],
            safe_summary["occupation"],
            safe_summary["relationship_goal"],
        ] if part
    )

    return safe_summary
```

#### Step 3: 后端构建消息时优化格式

修改 `build_outreach_payload_from_requester` 函数：

```python
def build_outreach_payload_from_requester(
    requester_summary: dict[str, Any],
    *,
    outreach_channel: str = DEFAULT_OUTREACH_CHANNEL,
) -> dict[str, Any]:
    """构建发给被请求方的消息，格式化关键信息"""
    requester_name = requester_summary.get("requester_name") or "有人"

    # 构建基本信息部分
    info_parts = [
        requester_summary.get("age_bracket"),
        requester_summary.get("city"),
        requester_summary.get("occupation"),
        requester_summary.get("relationship_goal"),
    ]
    info_line = "；".join(part for part in info_parts if part)

    # 构建匹配点部分
    matched_on = requester_summary.get("matched_on")
    match_line = None
    if matched_on and len(matched_on) > 0:
        match_line = "匹配点：" + "；".join(str(item) for item in matched_on[:3])

    # 组装消息
    lines = [
        f"{requester_name}想通过平台进一步认识你。",
        info_line,
        match_line,
    ]
    body = "\n".join(line for line in lines if line)

    return {
        "channel": outreach_channel,
        "title": f"{requester_name}想认识你",
        "body": body,
        "requester_summary": requester_summary,
    }
```

#### Step 4: 前端适配（简化）

前端只需简单处理：

```typescript
function mapProxyIntroCaseToInboxItem(caseItem: ProxyIntroCase): InboxItem {
  const requesterSummary = caseItem.outreach_payload?.requester_summary || {}

  // 后端已处理好中文映射和格式化，前端直接使用
  const infoTags = [
    requesterSummary.age_bracket,
    requesterSummary.city,
    requesterSummary.occupation,
    requesterSummary.education,
    requesterSummary.relationship_goal,
  ].filter(Boolean)

  const matchedOn = requesterSummary.matched_on || []

  return {
    id: String(caseItem.counterpart_profile_id || caseItem.case_id),
    listKey: `case:${caseItem.case_id}`,
    cardId: undefined,
    subscriptionId: undefined,
    recommendationId: undefined,
    candidateId: caseItem.counterpart_profile_id ?? undefined,
    caseId: String(caseItem.case_id),
    name: requesterSummary.requester_name || '有人',
    age: parseInt(String(caseItem.counterpart_profile?.age || '0')) || 0,
    city: requesterSummary.city || '未知',
    occupation: requesterSummary.occupation || '资料待补充',
    matchScore: 0,
    image: resolveProfileImageUrl(
      requesterSummary.avatar_url || PLACEHOLDER_AVATAR
    ),
    type: 'interest',
    message: requesterSummary.summary_text || `${name}想通过平台进一步认识你`,
    time: caseItem.created_at || '刚刚',
    isRead: caseItem.case_status !== 'awaiting_reply',
    conversionStage: undefined,
    // 新增字段：供卡片详细显示
    infoTags,
    matchedOn,
    ageDisplay: requesterSummary.age_bracket,
    relationshipGoal: requesterSummary.relationship_goal,
    education: requesterSummary.education,
  }
}
```

---

## 数据流对比

### 当前流程（问题）

```
用户年龄30 → _age_bracket() → "25-29岁"
                                ↓
            summary_text拼接 → "25-29岁；无锡；dating"  ← 英文直接拼接
                                ↓
                        前端显示 → 用户困惑
```

### 优化后流程（方案一）

```
用户年龄30 → _age_bracket() → "25-29岁"
                                ↓
            summary_text拼接 → "25-29岁；无锡；dating"
                                ↓
                    前端映射 → "约25-29岁；无锡；先谈恋爱看"
                                ↓
                        卡片显示 → 用户清晰理解
```

### 优化后流程（方案二）

```
用户年龄30 → _age_bracket() → "约25-29岁"  ← 后端添加"约"前缀
                                ↓
            后端中文映射 → "约25-29岁；无锡；先谈恋爱看"  ← 后端统一处理
                                ↓
                    前端直接显示 → "约25-29岁；无锡；先谈恋爱看"
                                ↓
                        卡片显示 → 用户清晰理解
```

---

## 测试验证

### 测试场景清单

| 场景 | 输入数据 | 期望输出 |
|------|---------|---------|
| 年龄段显示 | `age_bracket: "25-29岁"` | 显示："约25-29岁" |
| 关系目标映射 | `relationship_goal: "dating"` | 显示："先谈恋爱看" |
| 关系目标映射 | `relationship_goal: "marriage"` | 显示："奔着结婚去" |
| 关系目标映射 | `relationship_goal: "friends"` | 显示："找搭子/扩列" |
| 信息缺失兜底 | `occupation: null` | 显示："资料待补充" |
| 完整信息展示 | 多个字段有值 | 分行显示各字段 |
| 匹配点展示 | `matched_on: ["本科", "同城"]` | 显示匹配点标签 |

---

## 推荐方案

**短期推荐：方案一（前端优化）**
- 快速修复，不影响后端
- 实施时间短（1小时）
- 可立即上线验证效果

**长期推荐：方案二（后端重构）**
- 单一真相来源，数据一致性强
- 后端统一处理，可维护性好
- 需要后端配合，实施时间较长（3-4小时）

---

## 附录：关键文件路径

| 文件 | 路径 | 改动点 |
|------|------|--------|
| 后端年龄分段函数 | `external-systems/partner-matchmaking-system/matchmaking_system/proxy_intro_core.py:82-90` | `_age_bracket()` 函数 |
| 后端摘要构建 | `proxy_intro_core.py:131-167` | `build_requester_safe_summary()` 函数 |
| 后端消息构建 | `proxy_intro_core.py:199-234` | `build_outreach_payload_from_requester()` 函数 |
| 前端数据格式化 | `frontend/her-app/hooks/use-recommendation-inbox.ts:64-127` | `mapProxyIntroCaseToInboxItem()` 函数 |
| 前端卡片显示 | `frontend/her-app/components/her/discover-page.tsx:1108-1212` | 推荐来信卡片渲染 |
| 关系目标映射表 | `match_domain/onboarding_search.py:25-42` | `_RELATIONSHIP_GOAL_DISPLAY` |