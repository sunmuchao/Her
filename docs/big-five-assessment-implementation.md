# 大五人格测试完整落地方案

> **文档版本**: v1.1
> **创建日期**: 2026-05-31
> **所属项目**: Her 红娘测评体系
> **测评类型**: 核心画像层（P0 - 必做）

---

## 一、方案概述

### 1.1 大五人格是什么

大五人格（Big Five）是心理学界公认的黄金标准人格模型，从五个核心维度剖析真实性格：

| 维度 | 中文名称 | 测什么 | 高分特征 | 低分特征 |
|------|---------|--------|---------|---------|
| **Openness** | 开放性 | 是否愿意尝试新事物 | 好奇、创意、冒险 | 传统、务实、保守 |
| **Conscientiousness** | 尽责性 | 做事是否靠谱、有计划 | 负责、自律、有计划 | 随性、拖延、散漫 |
| **Extraversion** | 外向性 | 是否外向、喜欢社交 | 热情、健谈、活跃 | 内向、安静、独处 |
| **Agreeableness** | 宜人性 | 是否好相处、善良 | 善良、合作、信任 | 竞争、批判、冷漠 |
| **Neuroticism** | 神经质 | 情绪是否稳定 | 焦虑、情绪化、敏感 | 稳定、冷静、从容 |

### 1.2 为什么选择大五人格

- **科学背书最强**：心理学界公认标准，信度最高
- **匹配价值最高**：性格是匹配的核心维度，直接影响相处质量
- **预测能力强**：能预测行为模式、相处方式、关系稳定性
- **用户认知度高**：很多用户知道"性格测试"，容易接受

### 1.3 本方案核心设计

| 设计要点 | 方案 |
|---------|------|
| **触发方式** | AI 发现画像缺失 → 自然引导 → 用户说不知道 → 推荐测评 |
| **提问方式** | 硬编码20题（保证响应速度），用卡片UI展示 |
| **UI展示** | 对话中生成卡片UI，不跳转页面 |
| **问卷长度** | 精简版20题（原版60题），约5分钟完成 |
| **数据存储** | 写入现有偏好表 `user_personas.self_personality_traits_json` |
| **匹配应用** | 存入数据库后，AI 自主读取判断，不硬编码规则 |

### 1.4 自然引导设计（通过提示词 + Skill 实现）

**核心思路**：不硬编码流程，让 AI 自己判断时机并引导

**实现方式**：
```
提示词告诉 AI：
├─ 什么时候需要引导用户做测评
├─ 如何自然地引导用户
└─ 用户同意后调用 Skill 开始测评

Skill 提供：
├─ 推荐测评的能力
├─ 开始测评的能力
└─ 返回测评卡片的能力
```

### 1.4.1 提示词设计

**在 AI 的系统提示词中加入**：

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

**示例对话**：
用户："我喜欢看书"
AI："那你觉得自己是内向还是外向的人？"
用户："我不太清楚"
AI："很多人都不太了解自己的性格。要不做个小测试？
     大概5分钟，我帮你看看你的性格类型，
     这样以后匹配会更准确。"
用户："好啊"
AI：调用 `start_assessment` skill → 返回测评卡片
```

### 1.4.2 Skill 设计

**一个 Skill：开始测评（推荐 + 开始合并）**

```typescript
// skill: start_assessment
{
  name: "start_assessment",
  description: "开始性格测评。当用户同意做测评，或需要推荐测评时调用。",
  parameters: {
    assessment_type: {
      type: "string",
      enum: ["big_five", "attachment"],
      description: "测评类型"
    }
  },
  returns: {
    card_type: "assessment_intro",
    // 返回测评介绍卡片，包含开始按钮
  }
}
```

**说明**：
- 推荐测评和开始测评合并为一个 Skill
- AI 在提示词里自己判断什么时候调用
- 调用后返回测评介绍卡片
- 用户点"开始"后进入第一题

### 1.4.3 AI 自主判断流程

```
用户与 AI 对话
    ↓
AI 根据提示词判断：
    ├─ 是否需要引导测评？（画像缺失 + 相关话题）
    ├─ 什么时候引导？（聊到性格话题时）
    ├─ 怎么引导？（先问用户觉得自己什么性格）
    └─ 用户说不知道 → 自然推荐 → 用户同意 → 调用 skill
    ↓
AI 调用 start_assessment skill
    ↓
返回测评介绍卡片
    ↓
用户点"开始"
    ↓
进入第一题 → 开始测评
```

**AI 自己决定**：
- 什么时候引导（不固定时机）
- 怎么引导（不固定话术）
- 说什么话（个性化表达）
- 用户同意后调用 start_assessment skill

---

## 二、精简版20题设计

### 2.1 精简原则

原版大五人格60题，每维度12题，信度0.9。

精简版20题，每维度4题，信度约0.75（足够用于匹配）。

**精简逻辑**：
- 选择每个维度最核心、最能区分高低的4题
- 避免重复相似的问题
- 问题表述简单易懂

### 2.2 完整题目内容

#### 开放性（第1-4题）

```
第1题：你喜欢尝试新的餐厅、新的食物吗？
选项：
A. 非常喜欢     （得分：5）
B. 比较喜欢     （得分：4）
C. 无所谓       （得分：3）
D. 不太喜欢     （得分：2）
E. 非常不喜欢   （得分：1）

第2题：你对艺术、音乐、文学感兴趣吗？
选项：
A. 非常感兴趣   （得分：5）
B. 比较感兴趣   （得分：4）
C. 一般         （得分：3）
D. 不太感兴趣   （得分：2）
E. 完全不感兴趣 （得分：1）

第3题：你喜欢思考抽象的问题、探索新的想法吗？
选项：
A. 非常喜欢     （得分：5）
B. 比较喜欢     （得分：4）
C. 一般         （得分：3）
D. 不太喜欢     （得分：2）
E. 非常不喜欢   （得分：1）

第4题：你更喜欢熟悉的事物，还是新奇的事物？
选项：
A. 更喜欢新奇   （得分：5）
B. 都可以       （得分：4）
C. 无所谓       （得分：3）
D. 更喜欢熟悉   （得分：2）
E. 只喜欢熟悉   （得分：1）
```

#### 尽责性（第5-8题）

```
第5题：你做事前会制定详细的计划吗？
选项：
A. 总是如此     （得分：5）
B. 经常如此     （得分：4）
C. 有时如此     （得分：3）
D. 很少如此     （得分：2）
E. 几乎从不     （得分：1）

第6题：你能按时完成任务，不拖延吗？
选项：
A. 总是如此     （得分：5）
B. 经常如此     （得分：4）
C. 有时如此     （得分：3）
D. 很少如此     （得分：2）
E. 几乎从不     （得分：1）

第7题：你注重细节，做事追求完美吗？
选项：
A. 总是如此     （得分：5）
B. 经常如此     （得分：4）
C. 有时如此     （得分：3）
D. 很少如此     （得分：2）
E. 几乎从不     （得分：1）

第8题：你有明确的目标，并为之努力吗？
选项：
A. 总是如此     （得分：5）
B. 经常如此     （得分：4）
C. 有时如此     （得分：3）
D. 很少如此     （得分：2）
E. 几乎从不     （得分：1）
```

#### 外向性（第9-12题）

```
第9题：你喜欢参加热闹的聚会、社交活动吗？
选项：
A. 非常喜欢     （得分：5）
B. 比较喜欢     （得分：4）
C. 无所谓       （得分：3）
D. 不太喜欢     （得分：2）
E. 非常不喜欢   （得分：1）

第10题：你容易和陌生人聊天、交朋友吗？
选项：
A. 非常容易     （得分：5）
B. 比较容易     （得分：4）
C. 一般         （得分：3）
D. 不太容易     （得分：2）
E. 非常困难     （得分：1）

第11题：你更喜欢独处，还是和一群人在一起？
选项：
A. 更喜欢一群人 （得分：5）
B. 都可以       （得分：4）
C. 无所谓       （得分：3）
D. 更喜欢独处   （得分：2）
E. 只喜欢独处   （得分：1）

第12题：你是一个活泼、健谈的人吗？
选项：
A. 非常活泼     （得分：5）
B. 比较活泼     （得分：4）
C. 一般         （得分：3）
D. 不太活泼     （得分：2）
E. 非常安静     （得分：1）
```

#### 宜人性（第13-16题）

```
第13题：你愿意帮助别人，即使对自己没好处吗？
选项：
A. 非常愿意     （得分：5）
B. 比较愿意     （得分：4）
C. 一般         （得分：3）
D. 不太愿意     （得分：2）
E. 非常不愿意   （得分：1）

第14题：你相信大多数人都是善良的、值得信任的吗？
选项：
A. 非常相信     （得分：5）
B. 比较相信     （得分：4）
C. 一般         （得分：3）
D. 不太相信     （得分：2）
E. 完全不相信   （得分：1）

第15题：你避免和别人发生冲突，愿意妥协吗？
选项：
A. 总是如此     （得分：5）
B. 经常如此     （得分：4）
C. 有时如此     （得分：3）
D. 很少如此     （得分：2）
E. 几乎从不     （得分：1）

第16题：你是一个善良、体贴的人吗？
选项：
A. 非常善良     （得分：5）
B. 比较善良     （得分：4）
C. 一般         （得分：3）
D. 不太善良     （得分：2）
E. 非常冷漠     （得分：1）
```

#### 神经质（第17-20题）

```
第17题：你容易感到焦虑、紧张吗？
选项：
A. 经常如此     （得分：1）← 反向计分
B. 有时如此     （得分：2）
C. 偶尔如此     （得分：3）
D. 很少如此     （得分：4）
E. 几乎从不     （得分：5）

第18题：你情绪波动大吗？（容易生气、伤心、情绪化）
选项：
A. 经常如此     （得分：1）← 反向计分
B. 有时如此     （得分：2）
C. 偶尔如此     （得分：3）
D. 很少如此     （得分：4）
E. 几乎从不     （得分：5）

第19题：你容易感到沮丧、失落吗？
选项：
A. 经常如此     （得分：1）← 反向计分
B. 有时如此     （得分：2）
C. 偶尔如此     （得分：3）
D. 很少如此     （得分：4）
E. 几乎从不     （得分：5）

第20题：你面对压力时能保持冷静吗？
选项：
A. 非常冷静     （得分：5）
B. 比较冷静     （得分：4）
C. 一般         （得分：3）
D. 不太冷静     （得分：2）
E. 非常焦虑     （得分：1）← 反向计分
```

### 2.3 计分规则

**正向计分题目**（A=5, B=4, C=3, D=2, E=1）：
- 开放性：第1-4题
- 尽责性：第5-8题
- 外向性：第9-12题
- 宜人性：第13-16题

**反向计分题目**（A=1, B=2, C=3, D=4, E=5）：
- 神经质：第17-20题（因为神经质高=情绪不稳定，是负向特质）

**维度得分计算**：
```
每维度4题总分：4~20分
转换为0-100分：
得分 = (总分 - 4) / 16 * 100

示例：
用户选 A+A+A+A = 20分 → (20-4)/16*100 = 100分
用户选 C+C+C+C = 12分 → (12-4)/16*100 = 50分
用户选 E+E+E+E = 4分 → (4-4)/16*100 = 0分
```

---

## 三、对话式测评卡片设计

### 3.1 卡片类型定义

测评过程中使用5种卡片类型：

| 卡片类型 | 用途 | 出现时机 |
|---------|------|---------|
| **assessment_intro** | 测评介绍 | 用户说"想测性格"时 |
| **assessment_question** | 测评题目 | 用户答题过程中 |
| **assessment_feedback** | 维度反馈 | 答完每4题后 |
| **assessment_result** | 测评结果 | 答完20题后 |
| **assessment_interpretation** | AI解读 | 结果出来后等2秒 |

### 3.2 卡片数据结构

```typescript
interface AssessmentCard {
  card_type: 'assessment_intro' | 'assessment_question' | 'assessment_feedback' | 'assessment_result' | 'assessment_interpretation';
  
  // 测评元数据
  assessment_type: 'big_five';
  assessment_id: string;
  
  // 测评介绍数据（intro类型）
  intro_data?: {
    title: string;
    description: string;
    duration: string;
    reward: string;
  };
  
  // 题目数据（question类型）
  question_data?: {
    current_question: number;    // 第几题（1-20）
    total_questions: number;     // 总题数（20）
    question_text: string;       // 题目内容
    options: Array<{
      label: string;             // A, B, C, D, E
      text: string;              // 选项文字
      score: number;             // 分数（前端可选使用）
    }>;
    progress: number;            // 进度百分比（0-100）
  };
  
  // 反馈数据（feedback类型）
  feedback_data?: {
    dimension: string;           // 'openness', 'conscientiousness', etc.
    dimension_name: string;      // '开放性', '尽责性', etc.
    dimension_index: number;     // 第几个维度（0-4）
    score: number;               // 该维度得分（0-100）
    feedback_text: string;       // 反馈文字
  };
  
  // 结果数据（result类型）
  result_data?: {
    scores: {
      openness: number;
      conscientiousness: number;
      extraversion: number;
      agreeableness: number;
      neuroticism: number;
    };
    labels: string[];            // 趣味标签（如："安静的观察者"）
    match_quality_boost: number; // 匹配质量提升百分比
    badges: string[];            // 获得的勋章
  };
  
  // 解读数据（interpretation类型）
  interpretation_data?: {
    summary: string;             // 性格总结
    love_style: string;          // 恋爱中的表现
    match_suggestions: string[]; // 匹配建议
    action_prompt: string;       // 行动引导
  };
}
```

### 3.3 卡片UI设计

#### 测评介绍卡片

```
┌─────────────────────────────────────────────────────────────┐
│  📊 大五人格测试                                              │
│                                                             │
│  了解你的性格底色                                             │
│  找到更适合你的人                                             │
│                                                             │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  ⏱️ 约5分钟 · 20题                                           │
│  🎁 完成后匹配质量提升10%                                     │
│                                                             │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  [开始测评]                                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 测评题目卡片

```
┌─────────────────────────────────────────────────────────────┐
│  第1题 / 共20题                                              │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  你喜欢尝试新的餐厅、新的食物吗？                             │
│                                                             │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  ○ A. 非常喜欢                                               │
│  ○ B. 比较喜欢                                               │
│  ○ C. 无所谓                                                 │
│  ○ D. 不太喜欢                                               │
│  ○ E. 非常不喜欢                                             │
│                                                             │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  进度：■○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○○  5%  │
│                                                             │
│  [上一题]（第1题时隐藏）                                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘

交互方式：
- 用户点选项 → 自动跳到下一题（无需点"下一题"按钮）
- 点选项后，卡片自动切换为下一题卡片
```

#### 维度反馈卡片

```
┌─────────────────────────────────────────────────────────────┐
│  💡 小提示                                                   │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  你的开放性：65分                                             │
│                                                             │
│  你愿意尝试新事物，但不会太冲动                               │
│  你对新想法感兴趣，但也尊重传统                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘

显示方式：
- 答完每4题后出现
- 显示2秒后自动消失
- 同时显示下一题卡片
```

#### 测评结果卡片

```
┌─────────────────────────────────────────────────────────────┐
│  🎉 测评完成！                                                │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  "你是安静的观察者"                                          │
│                                                             │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  开放性：65 ████████░░░░░░░░░░                               │
│  尽责性：78 ██████████░░░░░░░░                               │
│  外向性：35 ████░░░░░░░░░░░░░░░░░░░░░░                       │
│  宜人性：72 █████████░░░░░░░░░░                              │
│  神经质：28 ███░░░░░░░░░░░░░░░░░░░░░░░░░░                    │
│                                                             │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  标签："安静的观察者" "稳重靠谱" "内心细腻"                  │
│                                                             │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  🎁 匹配质量提升 10%                                         │
│  🏅 获得"画像建立"勋章                                       │
│                                                             │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  [分享朋友圈]  [查看匹配建议]  [继续聊天]                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### AI解读卡片

```
┌─────────────────────────────────────────────────────────────┐
│  AI 解读                                                     │
│  ────────────────────────────────────────────────────────  │
│                                                             │
│  "我看你的结果，你是一个内向但稳重的人。                      │
│   你喜欢安静的生活，做事有计划，情绪很稳定。                  │
│                                                             │
│   在恋爱中，你可能不太主动表达，但很靠谱、很稳定。            │
│   你是默默付出的类型，需要找一个能读懂你的人。               │
│                                                             │
│   ────────────────────────────────────────────────────────  │
│                                                             │
│   建议你找一个：                                             │
│   • 外向性60-80的人（能带动气氛，但不会太吵）                 │
│   • 神经质低的人（情绪稳定，和你一样）                        │
│   • 尽责性高的人（和你一样做事有计划）                        │
│                                                             │
│   ────────────────────────────────────────────────────────  │
│                                                             │
│   我帮你匹配看看这样的人..."                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘

显示方式：
- 结果卡片出现后，等2秒再显示解读卡片
- 作为对话中的一条新消息出现
```

---

## 四、数据存储方案

### 4.1 写入现有偏好表

大五人格测评结果写入现有 `user_personas` 表，不新建独立表。

**新增字段**：

```sql
-- 数据库迁移脚本
ALTER TABLE user_personas 
ADD COLUMN self_personality_traits_json TEXT DEFAULT NULL 
COMMENT '性格特质测评结果（JSON格式，包含大五人格、依恋风格等）';
```

### 4.2 存储内容结构

```json
{
  "big_five": {
    "assessed_at": "2026-05-31T10:00:00Z",
    "assessment_id": "bf_abc123",
    "scores": {
      "openness": 65,
      "conscientiousness": 78,
      "extraversion": 35,
      "agreeableness": 72,
      "neuroticism": 28
    },
    "labels": ["安静的观察者", "稳重靠谱", "内心细腻"],
    "confidence": 0.75,
    "version": "v1.0",
    "source": "assessment"
  }
}
```

### 4.3 写入逻辑实现

```python
# persona_memory_sync/persona_memory_lib.py

async def save_big_five_to_persona(
    user_key: str,
    assessment_id: str,
    scores: dict,
    labels: list
):
    """
    写入大五人格测评结果到 user_personas 表
    
    Args:
        user_key: 用户标识
        assessment_id: 测评ID
        scores: 五个维度得分
        labels: 趣味标签
    """
    # 1. 获取现有 personality_traits_json
    persona = get_user_persona(user_key)
    existing_traits = persona.get("self_personality_traits_json") or {}
    if isinstance(existing_traits, str):
        existing_traits = json.loads(existing_traits)
    
    # 2. 构建大五人格数据
    big_five_data = {
        "assessed_at": datetime.now().isoformat(),
        "assessment_id": assessment_id,
        "scores": scores,
        "labels": labels,
        "confidence": 0.75,  # 精简版可信度
        "version": "v1.0",
        "source": "assessment"
    }
    
    # 3. 更新 big_five 字段
    existing_traits["big_five"] = big_five_data
    
    # 4. 写入 user_personas 表
    update_user_persona(
        user_key,
        {"self_personality_traits_json": json.dumps(existing_traits)}
    )
    
    # 5. 同时写入 user_persona_observations 表（记录来源）
    insert_observation(
        user_key=user_key,
        persona_id=persona.get("id"),
        field_name="self_personality_traits_json.big_five",
        field_value=json.dumps(big_five_data),
        source_type="explicit",  # 用户主动测评
        confidence_score=75,
        evidence_text=f"用户完成大五人格测评（{assessment_id}）",
        source_channel="assessment"
    )
```

### 4.4 读取性格特质用于匹配

```python
def get_user_personality_traits(user_key: str) -> dict:
    """
    从 user_personas 表读取性格特质
    
    Returns:
        dict: 性格特质数据，包含 big_five、attachment 等
    """
    persona = get_user_persona(user_key)
    traits_json = persona.get("self_personality_traits_json")
    
    if traits_json:
        if isinstance(traits_json, str):
            return json.loads(traits_json)
        return traits_json
    
    return {}

def get_big_five_scores(user_key: str) -> dict:
    """
    获取用户大五人格得分
    
    Returns:
        dict: 五个维度得分，或 None（如果没有测评）
    """
    traits = get_user_personality_traits(user_key)
    big_five = traits.get("big_five", {})
    
    if big_five and "scores" in big_five:
        return big_five["scores"]
    
    return None
```

---

## 五、数据使用说明

### 5.1 AI 匹配时的使用方式

**核心原则**：不硬编码匹配规则，让 AI 自主判断

```
数据存储后，AI 在匹配时的流程：

用户发起匹配请求
    ↓
AI 读取双方画像数据
    ├─ user_personas.self_personality_traits_json
    ├─ 包括大五人格、依恋风格等
    └─ AI 获取完整画像
    ↓
AI 自主判断匹配度
    ├─ AI 理解双方性格特征
    ├─ AI 分析是否合适
    ├─ AI 生成匹配建议
    └─ AI 给出匹配分（AI 自主决定）
    ↓
返回匹配结果
```

### 5.2 AI 如何使用画像数据

AI 在匹配时会：
- 读取双方的 `self_personality_traits_json`
- 理解双方的性格特征（如："内向"、"情绪稳定"）
- 自主判断是否匹配（不是按硬编码规则）
- 给出个性化建议（如："你们互补，他能带动气氛"）

**示例**：
```
AI 看到：
用户A：外向35、尽责78、神经28 → 内向、稳重、情绪稳定
用户B：外向70、尽责75、神经30 → 外向、稳重、情绪稳定

AI 自主判断：
"你们性格互补，你内向他外向，他能带动气氛。
 你们都情绪稳定，相处会很舒服。
 匹配度：85分"
```

### 5.3 只需要存储，不需要规则

**我们只需要做**：
- 测评结果存入数据库 ✓
- AI 能读取这些数据 ✓

**不需要做**：
- ❌ 硬编码匹配规则（如：外向差20-50=90分）
- ❌ 预设匹配算法
- ❌ 固定的匹配建议模板

**AI 会自己处理**：
- AI 根据画像数据自主判断匹配度
- AI 生成个性化的匹配建议
- AI 可能考虑我们没有想到的因素

---

## 六、总结

**本方案核心要点**：

1. **对话中生成UI**：测评卡片在对话界面中展示，不跳转页面
2. **精简版20题**：每维度4题，约5分钟完成
3. **写入现有偏好表**：`user_personas.self_personality_traits_json`
4. **AI 自主判断匹配**：不硬编码规则，AI 根据画像自主判断

**不需要我们设计的**：
- ❌ 硬编码的匹配规则
- ❌ 固定的匹配算法
- ❌ 预设的话题生成逻辑

**AI 会自己处理**：
- AI 读取画像数据
- AI 自主判断匹配度
- AI 生成个性化建议
- AI 生成破冰话题

---

## 七、完整用户流程

```
┌─────────────────────────────────────────────────────────────┐
│               大五人格测评完整流程                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 用户在对话中说："我想测测我的性格"                        │
│     ↓                                                       │
│  2. AI 返回测评介绍卡片                                     │
│     [开始测评]                                              │
│                                                             │
│  3. 用户点开始 → AI 返回题目卡片                            │
│     用户在对话界面答题                                       │
│                                                             │
│  4. 答完每4题 → 显示维度反馈（2秒消失）                      │
│     继续下一题                                              │
│                                                             │
│  5. 答完20题 → 显示结果卡片                                 │
│     ├─ 五维度得分                                           │
│     ├─ 趣味标签                                             │
│     └─ 写入偏好表                                           │
│                                                             │
│  6. 等2秒 → 显示AI解读卡片                                  │
│     ├─ 性格总结                                             │
│     ├─ 恋爱表现                                             │
│     └─ AI 匹配建议                                          │
│                                                             │
│  7. 用户选择下一步                                          │
│     ├─ [分享朋友圈]                                         │
│     ├─ [继续聊天]                                           │
│     └─ 测评数据已存入数据库                                 │
│                                                             │
│  8. 后续：AI 匹配时使用这些数据                              │
│     AI 自主判断匹配度                                       │
│     AI 生成个性化建议                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 时间估算

| 步骤 | 时间 |
|------|------|
| 答题（20题） | 约5分钟 |
| 反馈显示 | 约10秒 |
| 结果展示 | 约30秒 |
| AI解读 | 约2秒等待 + 30秒查看 |
| 总计 | 约6分钟 |

---

## 八、技术实现细节

### 8.1 后端接口设计

```python
# 测评相关接口

@router.post("/assessment/start")
async def start_assessment(
    user_key: str,
    assessment_type: str = "big_five"
):
    """
    开始测评，返回介绍卡片
    """
    assessment_id = f"bf_{uuid.uuid4().hex[:12]}"
    
    return {
        "card_type": "assessment_intro",
        "assessment_type": "big_five",
        "assessment_id": assessment_id,
        "intro_data": {
            "title": "大五人格测试",
            "description": "了解你的性格底色",
            "duration": "约5分钟 · 20题",
            "reward": "匹配质量提升10%"
        }
    }


@router.post("/assessment/begin")
async def begin_assessment(assessment_id: str):
    """
    用户点开始后，返回第一题
    """
    return {
        "card_type": "assessment_question",
        "assessment_id": assessment_id,
        "question_data": {
            "current_question": 1,
            "total_questions": 20,
            "question_text": BIG_FIVE_QUESTIONS[0]["text"],
            "options": BIG_FIVE_QUESTIONS[0]["options"],
            "progress": 5
        }
    }


@router.post("/assessment/answer")
async def submit_answer(
    assessment_id: str,
    question_index: int,
    answer: str,
    user_key: str
):
    """
    提交答案，返回下一题或反馈或结果
    
    关键：答完20题后，写入偏好表
    """
    # 保存答案
    save_answer(assessment_id, question_index, answer)
    
    # 答完每4题显示反馈
    if (question_index + 1) % 4 == 0 and question_index < 19:
        dimension_scores = calculate_dimension_scores(assessment_id, question_index // 4)
        
        return {
            "card_type": "assessment_feedback",
            "feedback_data": {
                "dimension": ...,
                "score": dimension_scores,
                "feedback_text": ...
            },
            "next_question": {...}
        }
    
    # 答完20题显示结果 + 写入偏好表
    if question_index >= 19:
        final_scores = calculate_final_scores(assessment_id)
        labels = generate_labels(final_scores)
        
        # ★ 核心：写入偏好表
        save_big_five_to_persona(user_key, assessment_id, final_scores, labels)
        
        return {
            "card_type": "assessment_result",
            "result_data": {
                "scores": final_scores,
                "labels": labels,
                "match_quality_boost": 10,
                "badges": ["画像建立"]
            }
        }
    
    # 返回下一题
    return {
        "card_type": "assessment_question",
        "question_data": get_question_data(question_index + 1)
    }


@router.post("/assessment/interpretation")
async def get_interpretation(assessment_id: str, user_key: str):
    """
    获取AI解读
    """
    scores = get_assessment_scores(assessment_id)
    interpretation = await generate_ai_interpretation(user_key, scores)
    
    return {
        "card_type": "assessment_interpretation",
        "interpretation_data": interpretation
    }


# 画像读取接口（供 AI 使用）

@router.get("/persona/personality-traits")
async def get_personality_traits(user_key: str):
    """
    获取用户性格特质画像
    
    AI 在匹配时会调用此接口获取画像数据
    """
    persona = get_user_persona(user_key)
    traits_json = persona.get("self_personality_traits_json")
    
    if traits_json:
        return json.loads(traits_json)
    
    return {}
```

**注意**：不需要匹配相关的接口，AI 会自己读取画像数据并判断匹配度。

### 8.2 前端卡片组件设计

```typescript
// 卡片渲染组件
const AssessmentCardRenderer: React.FC<{ card: AssessmentCard }> = ({ card }) => {
  switch (card.card_type) {
    case 'assessment_intro':
      return <AssessmentIntroCard data={card} />;
    
    case 'assessment_question':
      return <AssessmentQuestionCard data={card} />;
    
    case 'assessment_feedback':
      return <AssessmentFeedbackCard data={card} />;
    
    case 'assessment_result':
      return <AssessmentResultCard data={card} />;
    
    case 'assessment_interpretation':
      return <AssessmentInterpretationCard data={card} />;
    
    default:
      return null;
  }
};

// 题目卡片组件
const AssessmentQuestionCard: React.FC<{ data: AssessmentCard }> = ({ data }) => {
  const [selected, setSelected] = useState<string | null>(null);
  
  const handleSelect = async (optionLabel: string) => {
    setSelected(optionLabel);
    
    // 发送答案到后端
    const response = await fetch('/api/assessment/answer', {
      method: 'POST',
      body: JSON.stringify({
        assessment_id: data.assessment_id,
        question_index: data.question_data!.current_question - 1,
        answer: optionLabel,
        user_key: currentUserKey
      })
    });
    
    const nextCard = await response.json();
    
    // 触发新卡片渲染
    onNewCard(nextCard);
  };
  
  return (
    <div className="assessment-question-card">
      <div className="header">
        第{data.question_data!.current_question}题 / 共{data.question_data!.total_questions}题
      </div>
      
      <div className="question-text">
        {data.question_data!.question_text}
      </div>
      
      <div className="options">
        {data.question_data!.options.map(option => (
          <button
            key={option.label}
            className={`option ${selected === option.label ? 'selected' : ''}`}
            onClick={() => handleSelect(option.label)}
          >
            {option.label}. {option.text}
          </button>
        ))}
      </div>
      
      <div className="progress">
        <ProgressBar value={data.question_data!.progress} />
      </div>
    </div>
  );
};

// 反馈卡片组件（2秒后自动消失）
const AssessmentFeedbackCard: React.FC<{ data: AssessmentCard }> = ({ data }) => {
  useEffect(() => {
    // 2秒后触发消失
    const timer = setTimeout(() => {
      onFeedbackDismiss();
    }, 2000);
    
    return () => clearTimeout(timer);
  }, []);
  
  return (
    <div className="assessment-feedback-card">
      <div className="icon">💡</div>
      <div className="dimension">
        你的{data.feedback_data!.dimension_name}：{data.feedback_data!.score}分
      </div>
      <div className="feedback">
        {data.feedback_data!.feedback_text}
      </div>
    </div>
  );
};

// 结果卡片组件
const AssessmentResultCard: React.FC<{ data: AssessmentCard }> = ({ data }) => {
  const [showInterpretation, setShowInterpretation] = useState(false);
  
  useEffect(() => {
    // 2秒后请求AI解读
    const timer = setTimeout(async () => {
      const response = await fetch('/api/assessment/interpretation', {
        method: 'POST',
        body: JSON.stringify({
          assessment_id: data.assessment_id,
          user_key: currentUserKey
        })
      });
      
      const interpretationCard = await response.json();
      onNewCard(interpretationCard);
    }, 2000);
    
    return () => clearTimeout(timer);
  }, []);
  
  return (
    <div className="assessment-result-card">
      <div className="title">🎉 测评完成！</div>
      
      <div className="label">
        "你是{data.result_data!.labels[0]}"
      </div>
      
      <div className="scores">
        <ScoreBar dimension="开放性" score={data.result_data!.scores.openness} />
        <ScoreBar dimension="尽责性" score={data.result_data!.scores.conscientiousness} />
        <ScoreBar dimension="外向性" score={data.result_data!.scores.extraversion} />
        <ScoreBar dimension="宜人性" score={data.result_data!.scores.agreeableness} />
        <ScoreBar dimension="神经质" score={data.result_data!.scores.neuroticism} />
      </div>
      
      <div className="tags">
        {data.result_data!.labels.map(label => (
          <span className="tag">{label}</span>
        ))}
      </div>
      
      <div className="reward">
        🎁 匹配质量提升 {data.result_data!.match_quality_boost}%
        🏅 获得"{data.result_data!.badges[0]}"勋章
      </div>
      
      <div className="actions">
        <button onClick={onShare}>分享朋友圈</button>
        <button onClick={onViewMatch}>查看匹配建议</button>
        <button onClick={onContinueChat}>继续聊天</button>
      </div>
    </div>
  );
};
```

### 8.3 题目数据定义

```python
# 20题数据定义
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
        "dimension": "openness"
    },
    # ... 其他19题类似定义
]

DIMENSIONS = ["openness", "conscientiousness", "extraversion", "agreeableness", "neuroticism"]
DIMENSION_NAMES = ["开放性", "尽责性", "外向性", "宜人性", "神经质"]

# 维度反馈文本模板
DIMENSION_FEEDBACKS = {
    "openness": {
        "high": "你很有好奇心，喜欢探索新事物",
        "medium": "你愿意尝试新事物，但不会太冲动",
        "low": "你喜欢熟悉的事物，比较传统务实"
    },
    "conscientiousness": {
        "high": "你做事很有计划，很靠谱自律",
        "medium": "你做事有一定计划，但偶尔拖延",
        "low": "你比较随性，不太喜欢严格计划"
    },
    "extraversion": {
        "high": "你很外向，喜欢社交和热闹",
        "medium": "你有点外向，但不排斥独处",
        "low": "你比较内向，喜欢安静独处"
    },
    "agreeableness": {
        "high": "你很善良，好相处，乐于助人",
        "medium": "你对人友善，但有自己的底线",
        "low": "你比较独立，不太在意他人看法"
    },
    "neuroticism": {
        "high": "你情绪较敏感，容易焦虑紧张",
        "medium": "你情绪基本稳定，偶尔波动",
        "low": "你情绪很稳定，很少焦虑紧张"
    }
}
```

---

## 九、AI解读生成

### 9.1 解读模板结构

```
解读模板：

第1段：性格总结
"我看你的结果，你是一个[性格形容词]的人。
 [具体特征1]，[具体特征2]，[具体特征3]。"

第2段：恋爱中的表现
"在恋爱中，你可能[恋爱特征]。
 [恋爱建议1]，[恋爱建议2]。"

第3段：匹配建议
"建议你找一个：
 • [匹配建议1]
 • [匹配建议2]
 • [匹配建议3]"

第4段：行动引导
"我帮你匹配看看这样的人..."
```

### 9.2 性格形容词组合

```
外向性 + 尽责性 + 神经质 → 性格形容词

组合示例：
├─ 内向(35) + 稳重(78) + 稳定(28) → "内向但稳重"
├─ 外向(80) + 随性(40) + 情绪化(70) → "热情但情绪化"
├─ 中等(50) + 稳重(85) + 稳定(20) → "平衡且稳重"
├─ 内向(20) + 随性(30) + 稳定(50) → "安静且随性"
└─ 外向(70) + 稳重(75) + 稳定(30) → "热情且靠谱"
```

### 9.3 解读生成实现

```python
async def generate_ai_interpretation(user_key: str, scores: dict) -> dict:
    """
    调用AI生成个性化解读
    
    Args:
        user_key: 用户标识（用于获取上下文）
        scores: 大五人格得分
    
    Returns:
        dict: {
            "summary": 性格总结,
            "love_style": 恋爱中的表现,
            "match_suggestions": 匹配建议列表,
            "action_prompt": 行动引导
        }
    """
    # 构建prompt
    prompt = f"""
请为以下大五人格测试结果生成个性化解读：

开放性：{scores['openness']}分
尽责性：{scores['conscientiousness']}分
外向性：{scores['extraversion']}分
宜人性：{scores['agreeableness']}分
神经质：{scores['neuroticism']}分

要求：
1. 性格总结：用一句话概括性格特点，然后描述3个具体特征
2. 恋爱表现：描述在恋爱中的表现，给出2个建议
3. 匹配建议：建议找什么样的对象（3条具体建议）
4. 行动引导：一句话引导下一步行动

输出格式：
{
    "summary": "...",
    "love_style": "...",
    "match_suggestions": ["...", "...", "..."],
    "action_prompt": "..."
}
"""
    
    # 调用AI
    response = await call_ai_model(prompt)
    
    # 解析返回
    interpretation = parse_ai_response(response)
    
    return interpretation
```

---

## 十、后续扩展

完成大五人格后，后续测评也写入同一字段：

```json
// self_personality_traits_json 存储结构
{
  "big_five": {...},           // 大五人格
  "attachment": {...},         // 依恋风格
  "enneagram": {...}           // 九型人格（可选）
}
```

AI 在匹配时会读取完整画像，自主判断匹配度。

---

**文档结束**

> **核心要点**：
> - 对话中生成卡片UI
> - 精简版20题
> - 写入 `self_personality_traits_json`
> - AI 自主判断匹配（不硬编码规则）
