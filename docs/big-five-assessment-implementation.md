# 大五人格测试完整落地方案

> **文档版本**: v1.0
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
| **UI展示方式** | 对话中生成卡片UI，不跳转页面 |
| **问卷长度** | 精简版20题（原版60题），约5分钟完成 |
| **数据存储** | 写入现有偏好表 `user_personas.self_personality_traits_json` |
| **即时反馈** | 答完每4题显示维度反馈 |
| **AI解读** | 结果出来后，AI生成个性化解读（等2秒） |
| **匹配应用** | 性格匹配分用于匹配算法增强 |

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
COMMENT '性格特质测评结果（JSON格式，包含大五人格、依恋风格、恋爱语言等）';
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
        dict: 性格特质数据，包含 big_five, attachment, love_language 等
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

## 五、匹配算法应用

### 5.1 匹配权重设计

```
总体性格匹配分 = 
  外向性匹配分 × 0.30
  + 神经质匹配分 × 0.30
  + 尽责性匹配分 × 0.20
  + 开放性匹配分 × 0.10
  + 宜人性匹配分 × 0.10

权重解释：
├─ 外向性权重高（0.30）：直接影响相处方式，内向+外向=互补高分
├─ 神经质权重高（0.30）：直接影响关系稳定性，情绪稳定=高分
├─ 尽责性权重中（0.20）：影响生活规划，相似=高分
├─ 开放性权重低（0.10）：影响兴趣爱好，差异可以互补
└─ 宜人性权重低（0.10）：影响相处融洽，相似=高分
```

### 5.2 各维度匹配逻辑

#### 外向性匹配

```
匹配原则：互补优先，相似次之，差异太大最低

计算公式：
diff = |用户A外向性 - 用户B外向性|

if diff 在 20-50 之间：
    匹配分 = 90  # 互补高分（内向+外向）
elif diff < 20：
    匹配分 = 70  # 相似（都内向或都外向）
else:
    匹配分 = 50  # 差异太大

示例：
用户A外向35（内向）+ 用户B外向70（外向）→ diff=35 → 匹配分90
用户A外向35（内向）+ 用户B外向40（偏内向）→ diff=5 → 匹配分70
用户A外向10（极度内向）+ 用户B外向90（极度外向）→ diff=80 → 匹配分50
```

#### 神经质匹配

```
匹配原则：都低最好，一高一低次之，都高最差

计算公式：
avg_neuroticism = (用户A神经质 + 用户B神经质) / 2

if avg_neuroticism < 30：
    匹配分 = 95  # 都情绪稳定（最健康组合）
elif 用户A神经质 < 30 and 用户B神经质 > 60：
    匹配分 = 70  # 一个稳住另一个
elif 用户A神经质 > 60 and 用户B神经质 < 30：
    匹配分 = 70  # 一个稳住另一个
elif avg_neuroticism > 60：
    匹配分 = 40  # 都情绪不稳定（互相引发情绪）
else：
    匹配分 = 75  # 都中等

示例：
用户A神经28 + 用户B神经30 → avg=29 → 匹配分95
用户A神经28 + 用户B神经70 → 匹配分70（稳住对方）
用户A神经70 + 用户B神经75 → avg=72.5 → 匹配分40
```

#### 尽责性匹配

```
匹配原则：相似优先，适度差异次之

计算公式：
diff = |用户A尽责性 - 用户B尽责性|

if diff < 15：
    匹配分 = 85  # 相似（都做事有计划）
elif diff 在 15-30：
    匹配分 = 65  # 适度差异（互补）
else：
    匹配分 = 50  # 差异太大（可能冲突）

示例：
用户A尽责78 + 用户B尽责72 → diff=6 → 匹配分85
用户A尽责78 + 用户B尽责50 → diff=28 → 匹配分65
用户A尽责90 + 用户B尽责20 → diff=70 → 匹配分50
```

#### 开放性匹配

```
匹配原则：差异可以互补，不太重要

计算公式：
diff = |用户A开放性 - 用户B开放性|

if diff < 30：
    匹配分 = 80  # 相似或适度差异
else：
    匹配分 = 60  # 差异大（可以互补）
```

#### 宜人性匹配

```
匹配原则：相似优先，都高最好

计算公式：
avg_agreeableness = (用户A宜人性 + 用户B宜人性) / 2

if avg_agreeableness > 60：
    匹配分 = 85  # 都善良好相处
elif diff < 20：
    匹配分 = 70  # 相似
else：
    匹配分 = 60  # 差异大
```

### 5.3 匹配算法实现

```python
def calculate_big_five_match_score(
    user_key1: str,
    user_key2: str
) -> dict:
    """
    计算大五人格匹配分
    
    Returns:
        dict: {
            "score": 总体匹配分(0-100),
            "dimension_scores": 各维度匹配分,
            "analysis": AI分析文本,
            "has_data": 是否双方都有数据
        }
    """
    # 获取双方大五人格得分
    scores1 = get_big_five_scores(user_key1)
    scores2 = get_big_five_scores(user_key2)
    
    if not scores1 or not scores2:
        return {
            "score": None,
            "has_data": False,
            "reason": "缺少大五人格数据"
        }
    
    # 计算各维度匹配分
    extraversion_match = calculate_extraversion_match(
        scores1.get("extraversion", 50),
        scores2.get("extraversion", 50)
    )
    
    neuroticism_match = calculate_neuroticism_match(
        scores1.get("neuroticism", 50),
        scores2.get("neuroticism", 50)
    )
    
    conscientiousness_match = calculate_conscientiousness_match(
        scores1.get("conscientiousness", 50),
        scores2.get("conscientiousness", 50)
    )
    
    openness_match = calculate_openness_match(
        scores1.get("openness", 50),
        scores2.get("openness", 50)
    )
    
    agreeableness_match = calculate_agreeableness_match(
        scores1.get("agreeableness", 50),
        scores2.get("agreeableness", 50)
    )
    
    # 计算总体匹配分
    total_score = (
        extraversion_match * 0.30 +
        neuroticism_match * 0.30 +
        conscientiousness_match * 0.20 +
        openness_match * 0.10 +
        agreeableness_match * 0.10
    )
    
    # 生成分析文本
    analysis = generate_match_analysis(
        scores1, scores2,
        {
            "extraversion": extraversion_match,
            "neuroticism": neuroticism_match,
            "conscientiousness": conscientiousness_match,
            "openness": openness_match,
            "agreeableness": agreeableness_match
        }
    )
    
    return {
        "score": round(total_score, 1),
        "dimension_scores": {
            "extraversion": extraversion_match,
            "neuroticism": neuroticism_match,
            "conscientiousness": conscientiousness_match,
            "openness": openness_match,
            "agreeableness": agreeableness_match
        },
        "analysis": analysis,
        "has_data": True
    }

def generate_match_analysis(scores1: dict, scores2: dict, dimension_matches: dict) -> str:
    """
    生成匹配分析文本
    """
    analysis_parts = []
    
    # 外向性分析
    ext_diff = abs(scores1["extraversion"] - scores2["extraversion"])
    if ext_diff > 20 and ext_diff < 50:
        if scores1["extraversion"] < scores2["extraversion"]:
            analysis_parts.append("你内向，对方外向，你们是互补组合，对方能带动气氛。")
        else:
            analysis_parts.append("你外向，对方内向，你们是互补组合，你能带动气氛。")
    elif ext_diff < 20:
        analysis_parts.append("你们性格相似，都偏内向或都偏外向。")
    
    # 神经质分析
    neuro_avg = (scores1["neuroticism"] + scores2["neuroticism"]) / 2
    if neuro_avg < 30:
        analysis_parts.append("你们情绪都很稳定，这是最健康的组合。")
    elif scores1["neuroticism"] < 30 and scores2["neuroticism"] > 60:
        analysis_parts.append("你情绪稳定，对方情绪敏感，你能给对方安全感。")
    elif neuro_avg > 60:
        analysis_parts.append("你们情绪都较敏感，可能需要更多互相理解。")
    
    # 尽责性分析
    con_diff = abs(scores1["conscientiousness"] - scores2["conscientiousness"])
    if con_diff < 15:
        analysis_parts.append("你们做事风格相似，都很有计划或都比较随性。")
    elif con_diff > 30:
        analysis_parts.append("你们做事风格差异较大，可能需要磨合。")
    
    return " ".join(analysis_parts)
```

---

## 六、破冰话题生成

### 6.1 话题生成规则

根据双方大五人格差异，生成个性化话题建议：

| 维度差异 | 话题建议 |
|---------|---------|
| **外向性差异大** | "你平时喜欢热闹还是安静的活动？"<br>"你周末通常怎么过？在家还是出门？" |
| **神经质相似（都稳定）** | "你面对压力时会怎么处理？"<br>"你觉得恋爱中最重要的是什么？" |
| **尽责性相似** | "你做事喜欢提前计划还是随性？"<br>"你对未来有什么规划？" |
| **开放性差异大** | "你喜欢尝试新事物还是喜欢熟悉的？"<br>"你最近有什么新的兴趣或爱好？" |
| **宜人性差异** | "你觉得恋爱中怎么处理分歧比较好？"<br>"你是一个愿意妥协的人吗？" |

### 6.2 话题数据结构

```typescript
interface IcebreakerTopic {
  topic_id: string;
  topic_content: string;         // 话题内容
  source_dimension: string;      // 来源维度
  reason: string;                // 为什么推荐
  type: 'question' | 'discussion';
  priority: number;              // 推荐优先级（0-100）
}
```

### 6.3 话题生成实现

```python
def generate_icebreaker_topics(
    user_key1: str,
    user_key2: str,
    limit: int = 3
) -> list:
    """
    根据大五人格差异生成破冰话题
    
    Args:
        user_key1: 用户A
        user_key2: 用户B
        limit: 返回话题数量
    
    Returns:
        list: IcebreakerTopic列表
    """
    scores1 = get_big_five_scores(user_key1)
    scores2 = get_big_five_scores(user_key2)
    
    if not scores1 or not scores2:
        return get_default_topics(limit)
    
    topics = []
    
    # 外向性差异话题
    ext_diff = abs(scores1["extraversion"] - scores2["extraversion"])
    if ext_diff > 20:
        topics.append({
            "topic_id": "ext_1",
            "topic_content": "你平时喜欢热闹还是安静的活动？",
            "source_dimension": "extraversion",
            "reason": f"你们外向性差异{ext_diff}分，可以聊聊相处方式",
            "type": "question",
            "priority": 90
        })
    
    # 神经质话题
    neuro_avg = (scores1["neuroticism"] + scores2["neuroticism"]) / 2
    if neuro_avg < 30:
        topics.append({
            "topic_id": "neuro_1",
            "topic_content": "你面对压力时会怎么处理？",
            "source_dimension": "neuroticism",
            "reason": "你们情绪都稳定，可以聊聊应对压力的方式",
            "type": "question",
            "priority": 85
        })
    
    # 尽责性话题
    con_diff = abs(scores1["conscientiousness"] - scores2["conscientiousness"])
    if con_diff < 20:
        topics.append({
            "topic_id": "con_1",
            "topic_content": "你做事喜欢提前计划还是随性？",
            "source_dimension": "conscientiousness",
            "reason": "你们做事风格相似，可以聊聊生活规划",
            "type": "question",
            "priority": 80
        })
    
    # 开放性话题
    open_diff = abs(scores1["openness"] - scores2["openness"])
    if open_diff > 30:
        topics.append({
            "topic_id": "open_1",
            "topic_content": "你喜欢尝试新事物还是喜欢熟悉的？",
            "source_dimension": "openness",
            "reason": "你们开放性差异大，可以聊聊兴趣爱好",
            "type": "question",
            "priority": 75
        })
    
    # 按优先级排序，返回前N个
    topics.sort(key=lambda x: x["priority"], reverse=True)
    return topics[:limit]
```

---

## 七、完整用户流程

### 7.1 流程图

```
┌─────────────────────────────────────────────────────────────┐
│               大五人格测评完整流程                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 用户在对话中说："我想测测我的性格"                        │
│     ↓                                                       │
│  2. AI 返回测评介绍卡片                                     │
│     ├─ 显示测评介绍                                         │
│     ├─ 显示时长、奖励                                       │
│     └─ [开始测评] 按钮                                      │
│                                                             │
│  3. 用户点 [开始测评]                                        │
│     ↓                                                       │
│  4. AI 返回第1题卡片（在对话界面中）                         │
│     ├─ 第1题 + 5个选项                                      │
│     ├─ 进度条显示5%                                         │
│     └─ 用户点选项 → 自动跳下一题                            │
│                                                             │
│  5. 用户连续答题                                            │
│     ├─ 第1题 → 点选项 → 第2题                               │
│     ├─ 第2题 → 点选项 → 第3题                               │
│     ├─ 第3题 → 点选项 → 第4题                               │
│     └─ 第4题 → 点选项 → 显示反馈卡片                        │
│                                                             │
│  6. 反馈卡片出现                                            │
│     ├─ "你的开放性：65分"                                   │
│     ├─ 显示2秒后消失                                        │
│     └─ 继续第5题                                            │
│                                                             │
│  7. 重复步骤5-6                                             │
│     ├─ 第5-8题 → 尽责性反馈                                 │
│     ├─ 第9-12题 → 外向性反馈                                │
│     ├─ 第13-16题 → 宜人性反馈                               │
│     └─ 第17-20题 → 神经质反馈                               │
│                                                             │
│  8. 答完第20题                                              │
│     ├─ 后端计算完整结果                                     │
│     ├─ 写入偏好表                                           │
│     └─ 返回结果卡片                                         │
│                                                             │
│  9. 结果卡片显示                                            │
│     ├─ 五个维度得分                                         │
│     ├─ 趣味标签                                             │
│     ├─ 勋章奖励                                             │
│     └─ [分享朋友圈] [查看匹配建议] 按钮                     │
│                                                             │
│  10. 等2秒后                                                │
│      ├─ 异步请求 AI 解读                                    │
│      └─ 显示解读卡片                                        │
│                                                             │
│  11. AI解读卡片显示                                         │
│      ├─ 性格总结                                            │
│      ├─ 恋爱中的表现                                        │
│      ├─ 匹配建议                                            │
│      └─ "我帮你匹配看看..."                                 │
│                                                             │
│  12. 用户选择下一步                                         │
│      ├─ [分享朋友圈] → 生成分享卡片                         │
│      ├─ [查看匹配建议] → 返回匹配建议卡片                   │
│      └─ [继续聊天] → 回到正常对话                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 时间估算

| 步骤 | 时间 |
|------|------|
| 答题（20题） | 约5分钟（每题约15秒） |
| 反馈显示（5次） | 约10秒（每次2秒） |
| 结果展示 | 约30秒 |
| AI解读 | 约2秒等待 + 30秒查看 |
| 总计 | 约6-7分钟 |

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
    
    Request:
        user_key: 用户标识
        assessment_type: 测评类型
    
    Response:
        AssessmentCard (intro类型)
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
    
    Response:
        AssessmentCard (question类型)
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
    
    Request:
        assessment_id: 测评ID
        question_index: 题目索引（0-19）
        answer: 答案（A/B/C/D/E）
        user_key: 用户标识
    
    Response:
        AssessmentCard (question/feedback/result类型)
    """
    # 保存答案
    save_answer(assessment_id, question_index, answer)
    
    # 答完每4题显示反馈
    if (question_index + 1) % 4 == 0 and question_index < 19:
        dimension_index = question_index // 4
        dimension_scores = calculate_dimension_scores(assessment_id, dimension_index)
        
        return {
            "card_type": "assessment_feedback",
            "feedback_data": {
                "dimension": DIMENSIONS[dimension_index],
                "dimension_name": DIMENSION_NAMES[dimension_index],
                "dimension_index": dimension_index,
                "score": dimension_scores,
                "feedback_text": generate_dimension_feedback(dimension_scores)
            },
            # 同时返回下一题
            "next_question": {
                "card_type": "assessment_question",
                "assessment_id": assessment_id,
                "question_data": get_question_data(question_index + 1)
            }
        }
    
    # 答完20题显示结果
    if question_index >= 19:
        final_scores = calculate_final_scores(assessment_id)
        labels = generate_labels(final_scores)
        
        # 写入偏好表
        save_big_five_to_persona(user_key, assessment_id, final_scores, labels)
        
        return {
            "card_type": "assessment_result",
            "assessment_id": assessment_id,
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
        "assessment_id": assessment_id,
        "question_data": get_question_data(question_index + 1)
    }


@router.post("/assessment/interpretation")
async def get_interpretation(assessment_id: str, user_key: str):
    """
    获取AI解读
    
    Response:
        AssessmentCard (interpretation类型)
    """
    scores = get_assessment_scores(assessment_id)
    
    # 调用AI生成解读
    interpretation = await generate_ai_interpretation(user_key, scores)
    
    return {
        "card_type": "assessment_interpretation",
        "assessment_id": assessment_id,
        "interpretation_data": interpretation
    }


# 匹配相关接口

@router.post("/match/big-five/score")
async def calculate_match_score(user_key1: str, user_key2: str):
    """
    计算大五人格匹配分
    
    Response:
        {
            "score": 匹配分,
            "dimension_scores": 各维度分,
            "analysis": 分析文本,
            "has_data": bool
        }
    """
    return calculate_big_five_match_score(user_key1, user_key2)


@router.post("/match/icebreaker/topics")
async def generate_topics(user_key1: str, user_key2: str, limit: int = 3):
    """
    生成破冰话题
    
    Response:
        list[IcebreakerTopic]
    """
    return generate_icebreaker_topics(user_key1, user_key2, limit)
```

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

### 10.1 后续可接入的测评

完成大五人格后，后续可接入：

| 测评 | 存储位置 | 用于 |
|------|---------|------|
| **依恋风格** | `self_personality_traits_json.attachment` | 预测关系安全感 |
| **恋爱语言** | `self_personality_traits_json.love_language` | 相处建议 |
| **九型人格** | `self_personality_traits_json.enneagram` | 核心动机分析 |

### 10.2 数据更新机制

```
用户重新测评时：
├─ 保留历史记录（user_persona_observations）
├─ 更新 self_personality_traits_json
├─ 记录测评时间
└─ 更新匹配算法使用的画像
```

---

**文档结束**

> 本方案为 Her 红娘测评体系的第一个核心测评，后续测评（依恋风格、恋爱语言等）可参考此方案进行设计。