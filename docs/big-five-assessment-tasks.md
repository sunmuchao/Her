# 大五人格测评开发任务清单

> **文档版本**: v1.0
> **创建日期**: 2026-05-31
> **来源文档**: big-five-assessment-implementation.md
> **预估工期**: 2-3 周

---

## 任务概览

| 模块 | 任务数 | 预估工期 | 优先级 |
|------|--------|---------|--------|
| 数据库 | 2 | 1天 | P0 |
| 后端接口 | 6 | 3-4天 | P0 |
| 前端组件 | 5 | 2-3天 | P0 |
| Skill 开发 | 1 | 0.5天 | P1 |
| 提示词更新 | 1 | 0.5天 | P1 |
| 测试验收 | 3 | 2天 | P0 |

---

## 一、数据库任务

### 任务 1.1：新增 personality_traits 字段 ✅ 已完成

**任务描述**：在 `user_personas` 表新增字段存储性格特质

**具体内容**：
```sql
ALTER TABLE user_personas 
ADD COLUMN self_personality_traits_json TEXT DEFAULT NULL 
COMMENT '性格特质测评结果（JSON格式，包含大五人格、依恋风格、恋爱语言等）';
```

**验收标准**：
- 字段已添加到表中
- 字段类型正确（TEXT）
- 字段默认值为 NULL

**涉及文件**：
- 数据库迁移文件（新增）

**完成情况**：
- ✅ 迁移脚本已创建：`db_migrations/targets/persona/m0006_add_personality_traits_json.py`
- ✅ 字段位置：`self_relationship_goal` 之后
- ⏳ 待执行迁移脚本应用到数据库

---

### 任务 1.2：更新 Python 画像字段集合

**任务描述**：在 Python 代码中新增字段定义

**具体内容**：
```python
# persona_memory_sync/persona_memory_lib.py

PERSONALITY_TRAITS_FIELDS = {
    "self_personality_traits_json",
}

USER_PERSONA_FIELDS = USER_PERSONA_FIELDS | PERSONALITY_TRAITS_FIELDS
```

**验收标准**：
- 字段已添加到 USER_PERSONA_FIELDS
- 画像更新逻辑能处理该字段

**涉及文件**：
- `persona_memory_sync/persona_memory_lib.py`

---

## 二、后端接口任务

### 任务 2.1：开发测评开始接口

**任务描述**：开发 `/assessment/start` 接口

**接口定义**：
```python
POST /api/assessment/start

Request:
{
    "user_key": "string",
    "assessment_type": "big_five"
}

Response:
{
    "card_type": "assessment_intro",
    "assessment_type": "big_five",
    "assessment_id": "bf_xxx",
    "intro_data": {
        "title": "大五人格测试",
        "description": "了解你的性格底色",
        "duration": "约5分钟 · 20题",
        "reward": "匹配质量提升10%"
    }
}
```

**验收标准**：
- 接口返回正确的卡片数据
- assessment_id 正确生成

**涉及文件**：
- 新增：`src/api/assessment.py`

---

### 任务 2.2：开发获取第一题接口

**任务描述**：开发 `/assessment/begin` 接口

**接口定义**：
```python
POST /api/assessment/begin

Request:
{
    "assessment_id": "string"
}

Response:
{
    "card_type": "assessment_question",
    "assessment_id": "bf_xxx",
    "question_data": {
        "current_question": 1,
        "total_questions": 20,
        "question_text": "你喜欢尝试新的餐厅、新的食物吗？",
        "options": [...],
        "progress": 5
    }
}
```

**验收标准**：
- 返回第一题数据
- 题目内容正确（从硬编码数据读取）

**涉及文件**：
- `src/api/assessment.py`
- `src/assessment/big_five_questions.py`（新增，存储20题数据）

---

### 任务 2.3：开发答题接口

**任务描述**：开发 `/assessment/answer` 接口（核心接口）

**接口定义**：
```python
POST /api/assessment/answer

Request:
{
    "assessment_id": "string",
    "question_index": 0-19,
    "answer": "A/B/C/D/E",
    "user_key": "string"
}

Response（三种情况）：

情况1：答完4题，返回反馈 + 下一题
{
    "card_type": "assessment_feedback",
    "feedback_data": {...},
    "next_question": {...}
}

情况2：答完20题，返回结果
{
    "card_type": "assessment_result",
    "result_data": {
        "scores": {...},
        "labels": [...],
        ...
    }
}

情况3：普通情况，返回下一题
{
    "card_type": "assessment_question",
    "question_data": {...}
}
```

**验收标准**：
- 答案正确保存
- 每答完4题计算维度得分并返回反馈
- 答完20题计算完整结果并写入偏好表
- 进度条正确计算

**涉及文件**：
- `src/api/assessment.py`
- `src/assessment/scoring.py`（新增，计分逻辑）

---

### 任务 2.4：开发写入偏好表逻辑

**任务描述**：实现将测评结果写入 `user_personas` 表的逻辑

**具体内容**：
```python
# persona_memory_sync/persona_memory_lib.py

async def save_big_five_to_persona(
    user_key: str,
    assessment_id: str,
    scores: dict,
    labels: list
):
    # 1. 获取现有 personality_traits_json
    # 2. 更新 big_five 字段
    # 3. 写入 user_personas 表
    # 4. 写入 user_persona_observations 表
```

**验收标准**：
- 数据正确写入 `self_personality_traits_json.big_five`
- JSON 格式正确
- 同时写入 observations 表记录来源

**涉及文件**：
- `persona_memory_sync/persona_memory_lib.py`

---

### 任务 2.5：开发获取 AI 解读接口

**任务描述**：开发 `/assessment/interpretation` 接口

**接口定义**：
```python
POST /api/assessment/interpretation

Request:
{
    "assessment_id": "string",
    "user_key": "string"
}

Response:
{
    "card_type": "assessment_interpretation",
    "interpretation_data": {
        "summary": "...",
        "love_style": "...",
        "match_suggestions": [...]
    }
}
```

**验收标准**：
- 调用 AI 生成解读
- 返回正确的解读数据

**涉及文件**：
- `src/api/assessment.py`
- `src/assessment/interpretation.py`（新增）

---

### 任务 2.6：开发画像读取接口

**任务描述**：开发 `/persona/personality-traits` 接口（供 AI 使用）

**接口定义**：
```python
GET /api/persona/personality-traits?user_key=xxx

Response:
{
    "big_five": {...},
    "attachment": {...},
    "love_language": {...}
}
```

**验收标准**：
- 正确读取 `self_personality_traits_json`
- 返回 JSON 数据

**涉及文件**：
- `src/api/persona.py`

---

## 三、前端组件任务

### 任务 3.1：开发测评介绍卡片组件

**任务描述**：开发 `AssessmentIntroCard` 组件

**组件功能**：
- 显示测评标题、描述、时长、奖励
- 显示 [开始测评] 按钮
- 点击按钮触发开始测评

**验收标准**：
- 卡片正确渲染
- 点击按钮触发正确事件

**涉及文件**：
- 新增：`frontend/her-app/components/assessment/AssessmentIntroCard.tsx`

---

### 任务 3.2：开发测评题目卡片组件

**任务描述**：开发 `AssessmentQuestionCard` 组件（核心组件）

**组件功能**：
- 显示题目内容
- 显示 5 个选项（A/B/C/D/E）
- 显示进度条
- 点击选项自动提交答案并切换下一题
- 显示 [上一题] 按钮（第1题隐藏）

**验收标准**：
- 题目正确显示
- 点击选项触发答题接口
- 进度条正确显示
- 上一题按钮功能正常

**涉及文件**：
- 新增：`frontend/her-app/components/assessment/AssessmentQuestionCard.tsx`

---

### 任务 3.3：开发测评反馈卡片组件

**任务描述**：开发 `AssessmentFeedbackCard` 组件

**组件功能**：
- 显示维度名称和得分
- 显示反馈文本
- 显示 2 秒后自动消失

**验收标准**：
- 反馈正确显示
- 2 秒后自动消失

**涉及文件**：
- 新增：`frontend/her-app/components/assessment/AssessmentFeedbackCard.tsx`

---

### 任务 3.4：开发测评结果卡片组件

**任务描述**：开发 `AssessmentResultCard` 组件

**组件功能**：
- 显示五个维度得分（进度条形式）
- 显示趣味标签
- 显示奖励信息
- 显示 [分享朋友圈] [继续聊天] 按钮
- 结果显示后 2 秒自动请求 AI 解读

**验收标准**：
- 结果正确显示
- 2 秒后自动请求解读
- 按钮功能正常

**涉及文件**：
- 新增：`frontend/her-app/components/assessment/AssessmentResultCard.tsx`

---

### 任务 3.5：开发卡片渲染器组件

**任务描述**：开发 `AssessmentCardRenderer` 组件（统一渲染入口）

**组件功能**：
- 根据 card_type 渲染对应卡片组件
- 统一处理卡片数据

**验收标准**：
- 正确渲染各种卡片类型

**涉及文件**：
- 新增：`frontend/her-app/components/assessment/AssessmentCardRenderer.tsx`
- 修改：`frontend/her-app/components/chat/MessageRenderer.tsx`（集成卡片渲染器）

---

## 四、Skill 开发任务

### 任务 4.1：开发开始测评 Skill

**任务描述**：开发 `start_assessment` Skill（推荐 + 开始合并为一个）

**Skill 定义**：
```typescript
{
  name: "start_assessment",
  description: "开始性格测评。当用户同意做测评，或需要推荐测评时调用。",
  parameters: {
    assessment_type: {
      type: "string",
      enum: ["big_five", "attachment", "love_language"],
      description: "测评类型"
    }
  }
}
```

**验收标准**：
- Skill 正确注册
- AI 能调用该 Skill
- 返回测评介绍卡片

**涉及文件**：
- 新增：`src/skills/start_assessment.py`

**说明**：
- 推荐测评和开始测评合并为一个 Skill
- AI 在提示词里自己判断什么时候调用
- 调用后返回测评介绍卡片，用户点开始进入第一题

---

## 五、提示词更新任务

### 任务 5.1：更新 AI 系统提示词

**任务描述**：在 AI 系统提示词中添加性格画像引导说明

**具体内容**：
```markdown
## 性格画像引导

当以下情况发生时，考虑引导用户完成性格测评：

1. **画像缺失**：用户的性格画像（大五人格）缺失或未完成
2. **相关话题**：用户聊到性格、兴趣爱好、生活方式等话题
3. **匹配请求**：用户请求匹配，但性格画像缺失

**引导方式**：
- 不要直接说"你需要做测评"
- 先自然地问用户觉得自己是什么性格
- 如果用户说"不知道/不清楚/不确定"，自然推荐测评
- 说明测评的好处（了解自己、匹配更精准）
- 说明测评很短（约5分钟）

**用户同意后**：
- 调用 `start_assessment` skill 开始测评
```

**验收标准**：
- 提示词已更新
- AI 能根据提示词自然引导

**涉及文件**：
- `src/prompts/system_prompt.md`（或相应的提示词文件）

---

## 六、测试验收任务

### 任务 6.1：后端接口单元测试

**任务描述**：编写后端接口的单元测试

**测试内容**：
- 测试 `/assessment/start` 接口
- 测试 `/assessment/answer` 接口（各种情况）
- 测试计分逻辑
- 测试写入偏好表逻辑

**验收标准**：
- 所有测试通过
- 测试覆盖率 > 80%

**涉及文件**：
- 新增：`tests/assessment_test.py`

---

### 任务 6.2：前端组件测试

**任务描述**：编写前端组件的测试

**测试内容**：
- 测试各卡片组件渲染
- 测试用户交互（点击选项、点击按钮）
- 测试答题流程

**验收标准**：
- 所有测试通过

**涉及文件**：
- 新增：`frontend/her-app/components/assessment/__tests__/`

---

### 任务 6.3：端到端测试

**任务描述**：编写完整流程的端到端测试

**测试内容**：
- 模拟用户对话触发测评
- 模拟用户完成 20 题
- 验证数据写入偏好表
- 验证 AI 解读生成

**验收标准**：
- 完整流程正常
- 数据正确存储

**涉及文件**：
- 新增：`tests/e2e/assessment_e2e_test.py`

---

## 七、硬编码数据准备

### 任务 7.1：准备 20 题数据

**任务描述**：将大五人格 20 题硬编码为数据文件

**具体内容**：
```python
# src/assessment/big_five_questions.py

BIG_FIVE_QUESTIONS = [
    # 开放性（第1-4题）
    {
        "text": "你喜欢尝试新的餐厅、新的食物吗？",
        "options": [
            {"label": "A", "text": "非常喜欢", "score": 5},
            {"label": "B", "text": "比较喜欢", "score": 4},
            {"label": "C", "text": "无所谓", "score": 3},
            {"label": "D", "text": "不太喜欢", "score": 2},
            {"label": "E", "text": "非常不喜欢", "score": 1}
        ],
        "dimension": "openness",
        "reverse": False
    },
    # ... 其他19题
]
```

**验收标准**：
- 20 题数据完整
- 计分规则正确（正向/反向）

**涉及文件**：
- 新增：`src/assessment/big_five_questions.py`

---

## 八、任务依赖关系

```
任务依赖图：

数据库任务
├─ 1.1 新增字段 ───────────────┐
├─ 1.2 更新字段集合 ───────────┤
                              ↓
后端接口任务                   │
├─ 2.1 测评开始接口 ───────────┤
├─ 2.2 获取第一题接口 ─────────┤
├─ 2.3 答题接口（核心） ←──────┤
├─ 2.4 写入偏好表逻辑 ←────────┘
├─ 2.5 AI 解读接口
├─ 2.6 画像读取接口

前端组件任务
├─ 3.1 介绍卡片组件 ───────────┐
├─ 3.2 题目卡片组件 ───────────┤
├─ 3.3 反馈卡片组件 ───────────┤
├─ 3.4 结果卡片组件 ───────────┤
├─ 3.5 卡片渲染器 ←────────────┘（依赖上述所有）

Skill 开发任务
├─ 4.1 开始测评 Skill（推荐+开始合并）

提示词更新任务
├─ 5.1 更新系统提示词

测试验收任务
├─ 6.1 后端单元测试 ←─ 依赖后端接口
├─ 6.2 前端组件测试 ←─ 依赖前端组件
├─ 6.3 端到端测试 ←─ 依赖全部完成
```

---

## 九、执行建议

### 第一阶段（核心功能）

1. 完成数据库任务（1.1、1.2）
2. 完成后端核心接口（2.1、2.2、2.3、2.4）
3. 准备硬编码数据（7.1）
4. 完成前端核心组件（3.2、3.5）

### 第二阶段（完整功能）

5. 完成前端其他组件（3.1、3.3、3.4）
6. 完成后端其他接口（2.5、2.6）
7. 完成 Skill（4.1、4.2）
8. 更新提示词（5.1）

### 第三阶段（测试验收）

9. 完成单元测试（6.1、6.2）
10. 完成端到端测试（6.3）
11. 集成测试和验收

---

**文档结束**

> 总任务数：17 个
> 预估工期：2-3 周
> 核心任务：数据库 + 后端核心接口 + 前端题目卡片