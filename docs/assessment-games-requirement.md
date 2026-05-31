# 红娘页面测评与小游戏需求文档

> **文档版本**: v1.2
> **创建日期**: 2026-05-30
> **更新日期**: 2026-05-31
> **目标**: 为红娘匹配服务增加性格与恋爱观测评体系，提升匹配精准度、增强用户互动、形成产品差异化
> 
> **v1.1 更新内容**：
> - 优化 AI 响应慢问题：问卷用传统形式，AI 只做结果解读
> - 精简问卷长度：大五20题、依恋12题、恋爱语言10题
> - 明确切入点：对话中自然切入 + 输入框加号入口
> - 增加奖励机制设计
> 
> **v1.2 更新内容**：
> - **对话中直接生成UI**：测评不是跳转页面，而是在对话界面中以卡片形式展示
> - **写入现有偏好表**：测评结果写入 `user_personas.self_personality_traits_json` 字段
> - 新增大五人格完整落地方案

---

## 一、核心设计理念

### 1.1 测评不是"一次性测试"，而是"持续画像"

```
传统模式：
用户做测试 → 出报告 → 结束

AI Native 模式：
用户做测试 → AI 对话解读 → 画像存储 → 匹配增强 → 聊天应用 → 持续更新
```

### 1.2 测评是对话中的"卡片UI"，不是"跳转页面"

**核心设计**：
- 用户在对话中说"我想测测性格" → AI 返回测评介绍卡片
- 用户点"开始测评" → AI 返回题目卡片（在对话界面中）
- 用户点选项 → AI 返回下一题卡片或反馈卡片
- 答完所有题 → AI 返回结果卡片 + 解读卡片

**优势**：
- 用户不需要离开对话界面
- 测评过程自然流畅，像对话一样
- 测评结果直接进入对话历史，可随时回顾

### 1.3 测评结果写入现有偏好表，不新建独立表

**存储设计**：
- 测评结果写入 `user_personas.self_personality_traits_json` 字段
- 利用现有偏好表体系，不破坏原有架构
- 性格特质作为"自我属性"的一部分，与其他偏好统一管理

### 1.4 测评结果服务于匹配，而非标签化

- 画像数据用于匹配算法增强
- 用于生成破冰话题
- 用于关系辅导建议
- 不把用户贴上标签，而是提供可对话的素材

---

## 二、测评清单（分阶段落地）

### 📊 第一阶段：核心画像层（P0 - 必做）

**目标**: 建立用户画像基础，支撑匹配算法

| 测评名称 | 测评内容 | 选择理由 | 用户价值 | 实现方式 |
|---------|---------|---------|---------|---------|
| **大五人格测试** | 开放性、尽责性、外向性、宜人性、神经质五个维度 | 心理学界黄金标准，科学背书最强 | 了解性格底色，预测行为模式 | **精简版问卷（20题）** → 快速答题 → AI 个性化解读 |
| **依恋风格测验** | 安全型、焦虑型、回避型、恐惧型四种依恋类型 | 直接关联恋爱模式，预测关系质量 | 了解恋爱中的安全感来源 | **精简版问卷（12题）** → 快速答题 → AI 解读 + 匹配建议 |
| **恋爱五种语言** | 肯定言词、精心时刻、接受礼物、服务行动、身体接触 | 实用性强，直接指导相处方式 | 知道怎么表达爱对方才舒服 | **精简版问卷（10题）** → 快速答题 → AI 解读 + 破冰话题 |

**问卷精简说明**：

| 测评 | 原版题数 | 精简版题数 | 精简逻辑 | 完成时间 |
|------|---------|-----------|---------|---------|
| 大五人格 | 60题 | **20题** | 每维度4题，保留核心判断 | 约5分钟 |
| 依恋风格 | 36题 | **12题** | 每类型3题，直接判断类型 | 约3分钟 |
| 恋爱语言 | 30题 | **10题** | 每语言2题，直接排序 | 约2分钟 |

**组合逻辑**:
```
大五人格 → 性格底色（稳定特质）
依恋风格 → 拀恋安全感（关系模式）
恋爱语言 → 沟通偏好（相处方式）
```

**实现要点**:
- **问卷部分**：传统问卷形式（预设选项），用户快速选择，无卡顿感
- **答题过程**：后台异步计算结果，答题完成后结果已算好
- **结果展示**：立即显示基础结果，AI 解读异步加载（等2秒出现）
- **即时反馈**：答完每组题给小反馈（如答完外向性4题显示"你有点内向"）
- **AI 解读**：结果出来后，AI 生成个性化解读（非模板），结合用户上下文

---

### 🎮 第二阶段：互动破冰层（P1 - 差异化亮点）

**目标**: 促进用户互动，生成破冰话题

| 测评/游戏名称 | 测评内容 | 选择理由 | 用户价值 | 实现方式 |
|--------------|---------|---------|---------|---------|
| **36个问题坠入爱河** | 由浅入深的心理学问题，快速建立心理联结 | 经典心理学实验，传播性强，话题深度递进 | 陌生人快速熟悉，深度对话 | 双人互动问卷 → AI 生成"共鸣报告" |
| **房树人测验 (HTP)** | 画房子、树、人，投射潜意识 | 投射式测试，神秘感强，话题丰富 | 有趣、能传播、潜意识探索 | 用户画图上传 → AI 图像分析 → 心理解读 |
| **价值观拍卖会** | 用虚拟筹码竞拍"有钱/专一/好看/幽默/学历"等特质 | 直观看到核心底线，三观碰撞 | 快速了解三观是否合拍 | 游戏化界面 → AI 分析价值观排序 |
| **沙滩五样东西** | 沙滩上有爱情、友情、亲情、钱、自我，逐一放弃 | 价值观可视化，简单有趣 | 看最看重什么 | 互动选择 → AI 解读价值观优先级 |

**实现要点**:
- **36个问题**: 双人互动，每人回答后显示对方答案，做完生成共鸣点分析
- **房树人**: 用户画图上传 → AI 图像识别 → 心理分析 → 结果可分享
- **价值观拍卖**: 游戏化界面（拖动滑块分配筹码），完成后显示价值观排序 + 匹配分析
- **沙滩五样**: 互动选择界面，逐层放弃，最后解读价值观优先级

---

### 🔮 第三阶段：文化认同层（P2 - 市场差异化）

**目标**: 满足特定用户群体的文化需求

| 测评名称 | 测评内容 | 选择理由 | 用户价值 | 实现方式 |
|---------|---------|---------|---------|---------|
| **生辰八字合婚** | 输入出生年月日时，测算五行相生相克 | 本土化刚需，长辈认可，匹配场景刚需 | 传统家庭用户需求 | 输入生辰 → AI 解读 + 合盘分析 |
| **星盘对比** | 太阳、月亮、金星、火星等行星落座和相位 | 年轻用户群体大，话题性强 | 年轻女性用户需求 | 输入生日 → AI 解读 + 匹配分析 |
| **生命灵数** | 阳历生日数字相加，算出主命数（1-9） | 简单易算，神秘感强 | 玄学爱好者需求 | 输入生日 → AI 计算 + 解读 |

**AI Native 实现要点**:
- 不做成"迷信算命"，而是"文化解读 + AI 建议"
- AI 要给出可操作的建议（如：你们五行互补，相处时要注意...）
- 用户可选择是否做这类测评（非强制）

**用户群体适配建议**:
- 用户群体偏传统/有长辈参与 → 优先做八字
- 用户群体偏年轻女性 → 优先做星盘
- 用户群体偏玄学爱好者 → 做生命灵数
- 用户群体不吃这套 → 可跳过此阶段

---

### 🩺 第四阶段：关系诊断层（P3 - 深度服务）

**目标**: 为已有关系的用户提供诊断和疗愈

| 测评名称 | 测评内容 | 选择理由 | 用户价值 | 实现方式 |
|---------|---------|---------|---------|---------|
| **Gottman 关系健康检查** | 评估挑剔、鄙视、防御、冷战四大感情杀手 | 临床权威，预测离婚率高达90% | 关系危机预警 | 问卷 → AI 诊断 + 修复建议 |
| **爱情三元论测评** | 激情、亲密、承诺三个维度诊断 | 诊断缺啥补啥，关系健康度评估 | 了解关系处于什么阶段 | 问卷 → AI 分析 + 改进建议 |
| **亲密关系满意度量表 (CSI)** | 32个精细维度评估 | 精准定位问题来源 | 找出关系问题症结 | 问卷 → AI 分析 + 改进建议 |
| **非暴力沟通 (NVC) 练习** | 观察→感受→需要→请求四步沟通法 | 实用工具，疗愈效果好 | 冲突化解技巧 | AI 引导练习 → 反馈优化 |

**AI Native 实现要点**:
- AI 成为"情感咨询师"，持续追踪关系健康度
- 主动发现问题并推送建议（如：你们最近聊天频率下降，可能是因为...）
- 提供可操作的改进建议（如：建议你们这周末做个深度对话...）

---

## 三、明确不做的测评

| 测评名称 | 不建议原因 |
|---------|----------|
| **DISC性格测试** | 职场向太强，与恋爱场景弱相关 |
| **霍兰德职业兴趣测试** | 职业导向，与红娘场景不匹配 |
| **人类图** | 太小众，学习成本高，解释复杂 |
| **MHC气味测试** | 无法线上实现，需要实体接触 |
| **心率同步实验** | 需要智能手表等硬件设备，门槛高 |
| **账单对齐实验** | 隐私敏感，用户抵触情绪强 |
| **聊天记录关键词检索** | 隐私敏感，容易引发争议 |
| **玛雅历法** | 太小众，解释复杂 |
| **阿卡西记录冥想** | 太玄，用户难以理解 |
| **组织相容性抗原测试** | 需要医学检测，无法线上实现 |

---

## 四、用户画像数据结构设计

### 4.1 核心画像数据模型

```typescript
interface UserPersona {
  // === 核心特质（稳定，不易变化）===
  personality: {
    bigFive: {
      openness: number;          // 开放性 (0-100)
      conscientiousness: number; // 尽责性 (0-100)
      extraversion: number;      // 外向性 (0-100)
      agreeableness: number;     // 宜人性 (0-100)
      neuroticism: number;       // 神经质 (0-100)
      assessedAt: Date;          // 测评时间
      confidence: number;        // 可信度 (0-1)
    };
    enneagram: {
      type: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9; // 九型人格类型
      wing: number;              // 侧翼类型
      assessedAt: Date;
      confidence: number;
    };
    attachment: {
      type: 'secure' | 'anxious' | 'avoidant' | 'fearful'; // 依恋类型
      scores: {
        secure: number;
        anxious: number;
        avoidant: number;
        fearful: number;
      };
      assessedAt: Date;
      confidence: number;
    };
  };

  // === 恋爱偏好（可变，随经历更新）===
  loveProfile: {
    loveLanguages: {
      primary: string;           // 主要恋爱语言
      secondary: string;         // 次要恋爱语言
      ranking: Array<{           // 排序
        language: string;
        score: number;
      }>;
      assessedAt: Date;
    };
    loveStyle: string;           // 恋爱风格（浪漫型/实用型/游戏型等）
    valuesRanking: Array<{       // 价值观排序（来自价值观拍卖）
      value: string;             // 如：专一、有钱、好看、幽默
      priority: number;          // 优先级
    }>;
  };

  // === 文化认同（可选，用户自主选择）===
  culturalBeliefs: {
    zodiac: {
      sunSign: string;           // 太阳星座
      moonSign: string;          // 月亮星座
      risingSign: string;        // 上升星座
      venusSign: string;         // 金星星座
      marsSign: string;          // 火星星座
      assessedAt: Date;
    } | null;
    bazi: {
      year: string;              // 年柱
      month: string;             // 月柱
      day: string;               // 日柱
      hour: string;              // 时柱
      fiveElements: {            // 五行分布
        gold: number;
        wood: number;
        water: number;
        fire: number;
        earth: number;
      };
      assessedAt: Date;
    } | null;
    numerology: {
      lifePathNumber: number;    // 生命灵数 (1-9)
      assessedAt: Date;
    } | null;
    beliefLevel: {               // 用户对传统文化的态度
      zodiac: 'believe' | 'entertainment' | 'disbelieve';
      bazi: 'need' | 'neutral' | 'oppose';
      numerology: 'believe' | 'entertainment' | 'disbelieve';
    };
  };

  // === 关系状态（动态，持续更新）===
  relationshipStatus: {
    currentStage: 'single' | 'dating' | 'committed' | 'married';
    satisfaction: number;        // 满意度评分 (0-100)
    loveTriangle: {              // 爱情三元论
      intimacy: number;          // 亲密度
      passion: number;           // 激情度
      commitment: number;        // 承诺度
      type: 'romantic' | 'companionate' | 'consummate' | 'fatuous' | 'empty';
      assessedAt: Date;
    } | null;
    lastCheckin: Date;           // 最后关系检查时间
  };

  // === 投射测试结果（趣味性，可选）===
  projectiveTests: {
    htp: {                       // 房树人
      houseAnalysis: string;     // 房子分析（家庭观）
      treeAnalysis: string;      // 树分析（成长观）
      personAnalysis: string;    // 人分析（自我观）
      overall: string;           // 整体解读
      assessedAt: Date;
    } | null;
    forestAnimals: {             // 森林动物
      finalAnimal: string;       // 最后留下的动物
      interpretation: string;    // 解读
      assessedAt: Date;
    } | null;
    beachFive: {                 // 沙滩五样
      finalItem: string;         // 最后留下的东西
      order: string[];           // 放弃顺序
      interpretation: string;
      assessedAt: Date;
    } | null;
  };

  // === 画像来源追溯（可审计）===
  sources: Array<{
    assessmentId: string;        // 测评ID
    assessmentType: string;      // 测评类型
    timestamp: Date;             // 测评时间
    confidence: number;          // 可信度
    source: 'self_report' | 'ai_analysis' | 'behavior_inference'; // 来源类型
  }>;

  // === 画像更新历史（可回溯）===
  evolution: Array<{
    field: string;               // 更新的字段
    oldValue: any;
    newValue: any;
    reason: string;              // 更新原因
    timestamp: Date;
  }>;
}
```

### 4.2 匹配数据模型

```typescript
interface MatchAnalysis {
  userId1: string;
  userId2: string;

  // === 性格匹配度 ===
  personalityMatch: {
    overall: number;             // 总体匹配度 (0-100)
    bigFiveCompatibility: number; // 大五匹配度
    enneagramCompatibility: number; // 九型匹配度
    attachmentCompatibility: number; // 依恋匹配度
    analysis: string;            // AI 分析文本
  };

  // === 恋爱偏好匹配度 ===
  loveProfileMatch: {
    loveLanguageMatch: number;   // 恋爱语言匹配度
    valuesAlignment: number;     // 价值观对齐度
    analysis: string;
  };

  // === 文化认同匹配（可选）===
  culturalMatch: {
    zodiacMatch: number | null;  // 星座匹配度
    baziMatch: number | null;    // 八字匹配度
    numerologyMatch: number | null; // 灵数匹配度
    analysis: string | null;
  };

  // === 破冰话题建议 ===
  icebreakerTopics: Array<{
    topic: string;               // 话题内容
    source: string;              // 来源（如：36个问题第5题）
    reason: string;              // 为什么推荐这个话题
  }>;

  // === 匹配建议 ===
  recommendations: Array<{
    type: 'strength' | 'caution' | 'suggestion';
    content: string;             // 建议/预警内容
    reason: string;              // 原因分析
  }>;
}
```

---

## 五、用户路径设计

### 5.1 切入点设计

**两种切入点并行**：

#### 方案 A：对话中自然切入

```
场景：用户在聊天中提到某个话题

用户：我想测测我的性格

AI：好的，我们来测测你的性格底色
    （返回测评介绍卡片）

┌─────────────────────────────────────┐
│  📊 大五人格测试                     │
│  了解你的性格底色                     │
│  约5分钟 · 20题                      │
│  完成后匹配质量提升10%               │
│  [开始测评]                          │
└─────────────────────────────────────┘

用户点"开始测评"：
↓ AI 返回第一题卡片（在对话界面中）
↓ 用户在对话界面答题
↓ 完成后显示结果卡片
```

#### 方案 B：输入框加号入口（用户主动测评）

```
聊天界面输入框右侧有"+"按钮：

┌─────────────────────────────────┐
│  聊天界面                        │
├─────────────────────────────────┤
│                                 │
│  [消息记录区域]                  │
│  （测评卡片也在这里显示）        │
│                                 │
│  ┌─────────────────────┐       │
│  │ 输入消息...      [+] │ ← 点这里
│  └─────────────────────┘       │
│                                 │
└─────────────────────────────────┘

用户点"+"后弹出菜单：

┌─────────────────────────────────┐
│  选择功能                        │
├─────────────────────────────────┤
│  ├─ 📊 性格测试                 │
│  ├─ 💕 恋爱语言                  │
│  ├─ 🎮 36个问题                  │
│  ├─ 🏠 房树人                    │
│  ├─ 💰 价值观拍卖                │
│  └─ ...更多                      │
└─────────────────────────────────┘

用户选择后：
↓ 测评卡片发送到聊天中
↓ 用户在对话界面完成测评
↓ 结果卡片也在对话界面显示
```

### 5.2 对话式测评卡片流程

```
┌─────────────────────────────────────────────────────────────┐
│               对话式测评完整流程（卡片式）                    │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 用户说："我想测测我的性格"                               │
│     ↓                                                       │
│  2. AI 返回测评介绍卡片                                     │
│     ├─ card_type: 'assessment_intro'                        │
│     ├─ 内容：测评介绍 + [开始测评] 按钮                      │
│     └─ 用户在对话界面看到卡片                               │
│                                                             │
│  3. 用户点 [开始测评]                                        │
│     ↓                                                       │
│  4. AI 返回第一题卡片                                       │
│     ├─ card_type: 'assessment_question'                     │
│     ├─ 内容：第1题 + 选项 A/B/C/D/E                         │
│     └─ 用户在对话界面答题                                   │
│                                                             │
│  5. 用户点选项（如选 A）                                     │
│     ↓                                                       │
│  6. 后端保存答案，判断下一步                                 │
│     ├─ 答完4题 → 返回反馈卡片 + 下一题                      │
│     ├─ 答完20题 → 计算结果 → 写入偏好表 → 返回结果卡片      │
│     ├─ 否则 → 返回下一题卡片                                │
│                                                             │
│  7. 对话界面渲染对应卡片                                    │
│     ├─ 反馈卡片：显示2秒后自动消失                          │
│     ├─ 题目卡片：等待用户选择                               │
│     └─ 结果卡片：显示结果 + 按钮                            │
│                                                             │
│  8. 结果卡片显示后                                          │
│     ├─ 立即显示基础结果（分数 + 标签）                      │
│     ├─ 异步请求 AI 解读（等2秒）                            │
│     └─ 显示解读卡片                                         │
│                                                             │
│  9. 用户选择下一步                                          │
│     ├─ [分享朋友圈] → 生成分享卡片                          │
│     ├─ [查看匹配建议] → 返回匹配建议卡片                    │
│     └─ [继续聊天] → 回到正常对话                            │
│                                                             │
│  10. 测评结果已写入偏好表                                    │
│     ├─ user_personas.self_personality_traits_json           │
│     └─ 后续匹配时使用这些数据                               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5.3 测评触发时机

| 触发时机 | 引导测评 | 切入方式 | 用户价值 |
|---------|---------|---------|---------|
| **注册完成后** | 大五人格 + 依恋风格 | 注册引导页 | 建立画像基础，匹配质量提升20% |
| **匹配成功后** | 恋爱五种语言 | 对话中提示 / "+"入口 | 解锁相处建议，破冰话题 |
| **聊天过程中** | 36个问题 / 价值观拍卖 | 对话中自然切入 / "+"入口 | 双人互动，快速熟悉 |
| **关系确认后** | Gottman检查 + 爱情三元论 | 对话中自然切入 | 关系诊断，预警危机 |

### 5.4 测评完成策略

**核心画像（引导但不强制）**:
- 注册后引导做大五人格 + 依恋风格
- 不做完也能匹配，但匹配质量下降（提示："完善画像可提升匹配质量"）
- 完成后匹配权重提升 + 解锁详细匹配分析

**破冰测评（匹配成功后引导）**:
- 对话中自然切入或用户点"+"主动发起
- 不强制，但完成后有奖励（解锁相处建议、话题库）
- 双人互动完成后生成共鸣报告

**关系诊断（已有关系后引导）**:
- 对话中自然切入（AI 发现关系状态变化）
- 不强制，但定期提醒
- 发现关系异常时主动推送

---

## 六、匹配算法增强设计

### 6.1 匹配权重设计

```typescript
interface MatchWeights {
  // === 硬匹配（价值观冲突直接过滤）===
  hardFilters: {
    valuesConflict: boolean;     // 价值观是否冲突
    // 如：一个想要孩子，一个不想要 → 直接过滤
    // 如：一个看重专一，一个看重有钱 → 不冲突，但降低权重
  };

  // === 软匹配（性格互补性加权）===
  softWeights: {
    bigFive: {
      // 大五人格匹配权重
      opennessMatch: number;     // 开放性相似度权重
      extraversionMatch: number; // 外向性互补权重（内向+外向=高分）
      neuroticismMatch: number;  // 神经质相似度权重（都低=高分）
    };
    attachment: {
      // 依恋类型匹配权重
      // 安全型+任何 = 高分
      // 焦虑型+回避型 = 低分（追逐-逃跑模式）
      // 安全型+安全型 = 最高分
      compatibility: number;
    };
    loveLanguages: {
      // 恋爱语言匹配权重
      // 语言相近 = 高分
      // 语言互补 = 中分（但可以互相学习）
      compatibility: number;
    };
  };

  // === 文化匹配（可选，用户自主选择）===
  culturalWeights: {
    zodiac: number | null;       // 星座匹配权重（用户信则用，不信则忽略）
    bazi: number | null;         // 八字匹配权重
  };

  // === 最终匹配分计算 ===
  calculateTotal(): number;      // 计算总分 (0-100)
}
```

### 6.2 匹配规则示例

**大五人格匹配规则**:
```
外向性:
- 高外向 + 低外向 = 互补高分（一个带动气氛，一个享受安静）
- 高外向 + 高外向 = 相似高分（一起热闹）
- 低外向 + 低外向 = 相似中分（一起安静，但可能缺乏活力）

神经质:
- 低神经质 + 低神经质 = 高分（情绪都稳定）
- 低神经质 + 高神经质 = 中分（一个稳住另一个）
- 高神经质 + 高神经质 = 低分（容易互相引发情绪）

开放性:
- 高开放 + 高开放 = 高分（一起探索新事物）
- 高开放 + 低开放 = 中分（可能产生分歧）
```

**依恋类型匹配规则**:
```
安全型 + 任何 = 高分（安全型能适应任何类型）
安全型 + 安全型 = 最高分（最健康组合）
焦虑型 + 回避型 = 低分（追逐-逃跑恶性循环）
焦虑型 + 焦虑型 = 中分（可能过度依赖）
回避型 + 回避型 = 低分（可能互相疏离）
恐惧型 + 任何 = 低分（需要心理辅导）
```

---

## 七、测评实现要点

### 7.1 对话中生成测评卡片UI

**核心思路**：测评不是跳转页面，而是在对话界面中以卡片形式展示

```
┌─────────────────────────────────────────────────────────────┐
│                   对话式测评卡片流程                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户消息："我想测测我的性格"                                │
│     ↓                                                       │
│  AI 返回测评介绍卡片                                        │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  📊 大五人格测试                                      │   │
│  │  了解你的性格底色                                      │   │
│  │  约5分钟 · 20题                                       │   │
│  │  [开始测评]                                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  用户点 [开始测评]                                           │
│     ↓                                                       │
│  AI 返回题目卡片（在对话界面中）                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  第1题/共20题                                         │   │
│  │  你喜欢尝试新的餐厅、新的食物吗？                     │   │
│  │  ○ A. 非常喜欢  ○ B. 比较喜欢  ○ C. 无所谓          │   │
│  │  ○ D. 不太喜欢  ○ E. 非常不喜欢                      │   │
│  │  进度：■○○○○○○○○○○○○○○○○○○○○                      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  用户点选项 → AI 返回下一题卡片                              │
│     ↓                                                       │
│  答完每4题 → AI 返回反馈卡片（显示2秒后消失）                │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  💡 小提示                                            │   │
│  │  你的开放性：65分                                      │   │
│  │  你愿意尝试新事物，但不会太冲动                        │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  答完20题 → AI 返回结果卡片                                 │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  🎉 测评完成！                                        │   │
│  │  "你是安静的观察者"                                    │   │
│  │  开放性：65 ████████░░                                │   │
│  │  尽责性：78 █████████░                                │   │
│  │  外向性：35 ███░░░░░░░░                               │   │
│  │  宜人性：72 ███████░░░                                │   │
│  │  神经质：28 ██░░░░░░░░░░                              │   │
│  │  [分享朋友圈] [查看匹配建议]                          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  等2秒后 → AI 返回解读卡片                                  │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  AI 解读                                              │   │
│  │  "你是一个内向但稳重的人..."                          │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 测评卡片数据结构

```typescript
// 测评卡片类型定义
interface AssessmentCard {
  card_type: 'assessment_intro' | 'assessment_question' | 'assessment_feedback' | 'assessment_result' | 'assessment_interpretation';
  
  // 测评元数据
  assessment_type: 'big_five' | 'attachment' | 'love_language';
  assessment_id: string;
  
  // 题目数据（question类型）
  question_data?: {
    current_question: number;
    total_questions: number;
    question_text: string;
    options: Array<{
      label: string;      // A, B, C, D, E
      text: string;       // 选项文字
      score: number;      // 分数（前端可选使用）
    }>;
    progress: number;     // 0-100
  };
  
  // 反馈数据（feedback类型）
  feedback_data?: {
    dimension: string;    // 'openness', 'conscientiousness', etc.
    dimension_name: string; // '开放性', '尽责性', etc.
    score: number;        // 0-100
    feedback_text: string;
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
    labels: string[];
    match_quality_boost: number;
    badges: string[];
  };
  
  // 解读数据（interpretation类型）
  interpretation_data?: {
    summary: string;
    love_style: string;
    match_suggestions: string[];
  };
}
```

### 7.3 前端卡片渲染逻辑

```typescript
// 消息渲染组件
const MessageRenderer = ({ message }) => {
  // 判断是否有卡片类型
  if (message.card_type) {
    return <CardRenderer card={message} />;
  }
  
  // 渲染普通文本消息
  return <TextMessage content={message.content} />;
};

// 卡片渲染组件
const CardRenderer = ({ card }) => {
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
      return <GenericCard data={card} />;
  }
};

// 题目卡片交互逻辑
const AssessmentQuestionCard = ({ data }) => {
  const handleSelect = async (option) => {
    // 发送答案到后端
    const response = await submitAnswer({
      assessment_id: data.assessment_id,
      question_index: data.question_data.current_question - 1,
      answer: option.label
    });
    
    // 后端返回下一题卡片或反馈卡片
    // 前端自动渲染返回的卡片
  };
  
  return (
    <div className="assessment-question-card">
      <div className="progress">
        第{data.question_data.current_question}题/共{data.question_data.total_questions}题
      </div>
      <div className="question-text">
        {data.question_data.question_text}
      </div>
      <div className="options">
        {data.question_data.options.map(option => (
          <button onClick={() => handleSelect(option)}>
            {option.label}. {option.text}
          </button>
        ))}
      </div>
      <ProgressBar value={data.question_data.progress} />
    </div>
  );
};
```

### 7.4 后端卡片生成接口

```python
# 开始测评
@router.post("/assessment/start")
async def start_assessment(
    user_key: str,
    assessment_type: str
):
    """返回测评介绍卡片"""
    assessment_id = generate_assessment_id()
    
    return {
        "card_type": "assessment_intro",
        "assessment_type": assessment_type,
        "assessment_id": assessment_id,
        "intro_data": {
            "title": "大五人格测试",
            "description": "了解你的性格底色",
            "duration": "约5分钟 · 20题",
            "reward": "匹配质量提升10%"
        }
    }

# 用户点开始后，获取第一题
@router.post("/assessment/begin")
async def begin_assessment(assessment_id: str):
    """返回第一题卡片"""
    return {
        "card_type": "assessment_question",
        "assessment_id": assessment_id,
        "question_data": {
            "current_question": 1,
            "total_questions": 20,
            "question_text": "你喜欢尝试新的餐厅、新的食物吗？",
            "options": [
                {"label": "A", "text": "非常喜欢", "score": 5},
                {"label": "B", "text": "比较喜欢", "score": 4},
                {"label": "C", "text": "无所谓", "score": 3},
                {"label": "D", "text": "不太喜欢", "score": 2},
                {"label": "E", "text": "非常不喜欢", "score": 1}
            ],
            "progress": 5
        }
    }

# 提交答案，获取下一题或反馈
@router.post("/assessment/answer")
async def submit_answer(
    assessment_id: str,
    question_index: int,
    answer: str
):
    """返回下一题卡片或反馈卡片"""
    # 保存答案
    save_answer(assessment_id, question_index, answer)
    
    # 答完每4题显示反馈
    if (question_index + 1) % 4 == 0:
        dimension_scores = calculate_dimension_scores(assessment_id, question_index)
        
        return {
            "card_type": "assessment_feedback",
            "feedback_data": {
                "dimension": get_dimension_name(question_index),
                "dimension_name": "开放性",
                "score": dimension_scores,
                "feedback_text": "你愿意尝试新事物，但不会太冲动"
            },
            # 同时返回下一题
            "next_question": {
                "card_type": "assessment_question",
                "question_data": get_next_question(question_index + 1)
            }
        }
    
    # 答完20题显示结果
    if question_index + 1 >= 20:
        final_scores = calculate_final_scores(assessment_id)
        
        # 写入偏好表
        save_to_persona(user_key, final_scores)
        
        return {
            "card_type": "assessment_result",
            "result_data": {
                "scores": final_scores,
                "labels": generate_labels(final_scores),
                "match_quality_boost": 10,
                "badges": ["画像建立"]
            }
        }
    
    # 返回下一题
    return {
        "card_type": "assessment_question",
        "question_data": get_next_question(question_index + 1)
    }

# 获取AI解读
@router.post("/assessment/interpretation")
async def get_interpretation(assessment_id: str):
    """返回AI解读卡片"""
    scores = get_assessment_scores(assessment_id)
    interpretation = await generate_ai_interpretation(scores)
    
    return {
        "card_type": "assessment_interpretation",
        "interpretation_data": interpretation
    }
```

### 7.5 即时反馈设计

**答完每4题后显示小反馈卡片**：

```
答完开放性4题后：

┌─────────────────────────────────────┐
│  💡 小提示                           │
│                                     │
│  你的开放性：65分                    │
│                                     │
│  你愿意尝试新事物，但不会太冲动       │
│                                     │
└─────────────────────────────────────┘

显示方式：
- 在对话界面中作为一条消息出现
- 显示2秒后自动消失（或用户点继续）
- 同时显示下一题卡片
```

---

## 八、奖励机制设计

### 8.1 奖励体系概览

```
┌─────────────────────────────────────────────────────────────┐
│                    奖励机制体系                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  【即时反馈】答题过程中就有收获感                              │
│   ├─ 答完每组题给小反馈                                       │
│   └─ 用户不觉得无聊，愿意继续答完                             │
│                                                             │
│  【结果有趣】测评结果要吸引人                                 │
│   ├─ 个性化解读（非模板）                                    │
│   ├─ 趣味标签（"安静的观察者"、"专一至上"）                   │
│   └─ 可分享朋友圈                                            │
│                                                             │
│  【功能解锁】做完测评解锁新功能                               │
│   ├─ 完成恋爱语言 → 解锁"相处建议"                           │
│   ├─ 完成36个问题 → 解锁"共鸣话题库"                         │
│   └─ 完成核心画像 → 解锁详细匹配分析                         │
│                                                             │
│  【匹配质量提升】实际价值奖励                                 │
│   ├─ 完成大五人格 → 匹配质量提升10%                          │
│   ├─ 完成依恋风格 → 匹配质量提升10%                          │
│   └─ 完成核心画像 → 匹配质量提升20%                          │
│                                                             │
│  【勋章成就】社交炫耀                                        │
│   ├─ 完成核心画像 → "自我认知达人"勋章                       │
│   ├─ 完成36个问题 → "深度对话者"勋章                         │
│   └─ 完成房树人 → "内心探索者"勋章                           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 8.2 具体奖励设计

| 做完的测评 | 即时奖励 | 功能奖励 | 匹配奖励 | 勋章奖励 |
|-----------|---------|---------|---------|---------|
| **大五人格** | 每答5题给小反馈 | - | 匹配质量 +10% | - |
| **依恋风格** | 每答4题给小反馈 | - | 匹配质量 +10% | - |
| **恋爱语言** | 每答2题给小反馈 | 解锁"相处建议" | - | - |
| **核心画像全部完成** | - | 解锁详细匹配分析 | 匹配质量 +20% | "自我认知达人"勋章 |
| **36个问题** | 每答6题给小反馈 | 解锁"共鸣话题库" | - | "深度对话者"勋章 |
| **房树人** | - | 画作可分享朋友圈 | - | "内心探索者"勋章 |
| **价值观拍卖** | - | 价值观卡片可分享 | - | - |
| **全部测评完成** | - | - | - | "全方位画像"勋章 |

### 8.3 勋章设计

```
┌─────────────────────────────────────┐
│  用户勋章墙                          │
├─────────────────────────────────────┤
│                                     │
│  🏅 自我认知达人                     │
│     完成核心画像（大五+依恋+恋爱语言） │
│                                     │
│  🎯 深度对话者                       │
│     完成36个问题                     │
│                                     │
│  🎨 内心探索者                       │
│     完成房树人测验                   │
│                                     │
│  💎 价值观清晰                       │
│     完成价值观拍卖                   │
│                                     │
│  🌟 全方位画像                       │
│     完成所有测评                     │
│                                     │
│  🤝 关系守护者                       │
│     定期做关系诊断                   │
│                                     │
│  📤 分享达人                         │
│     分享测评结果到朋友圈             │
│                                     │
└─────────────────────────────────────┘
```

### 8.4 分享激励机制

**测评结果可分享朋友圈**：

```
大五人格结果卡片：

┌─────────────────────────────┐
│                             │
│    "安静的观察者"            │
│                             │
│    内向35 · 稳重78 ·         │
│    情绪稳定28                │
│                             │
│    "我喜欢在角落观察世界     │
│     内心丰富但不太表达"      │
│                             │
│    [Her 红娘]                │
│                             │
└─────────────────────────────┘

分享朋友圈的好处：
├─ 朋友看到觉得有趣
├─ 朋友也来做测评
└─ 用户获得"分享达人"勋章
```

### 8.5 奖励展示时机

```
用户做完测评后：

┌─────────────────────────────────────────┐
│  测评完成！                              │
├─────────────────────────────────────────┤
│                                         │
│  🎉 匹配质量提升 20%                     │
│                                         │
│  🏅 获得"自我认知达人"勋章               │
│                                         │
│  ✨ 解锁详细匹配分析                      │
│                                         │
│  📤 [分享朋友圈] [查看结果] [开始匹配]    │
│                                         │
└─────────────────────────────────────────┘
```

---

## 九、技术实现建议

### 9.1 测评引擎架构

```
┌─────────────────────────────────────────────────────────────┐
│                     测评引擎架构                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  用户入口                                                    │
│     ↓                                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │            Assessment Orchestrator                   │    │
│  │  (决定用什么测评、何时用、如何组合)                    │    │
│  └─────────────────────────────────────────────────────┘    │
│     ↓                                                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ 心理测评引擎 │  │ 投射测评引擎 │  │ 文化测评引擎 │       │
│  │ (大五/依恋)  │  │ (房树人)     │  │ (八字/星盘)  │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│     ↓                ↓                ↓                     │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              Persona Fusion Engine                   │    │
│  │  (多源画像融合、冲突解决、置信度计算)                 │    │
│  └─────────────────────────────────────────────────────┘    │
│     ↓                                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │            Match Enhancement Layer                   │    │
│  │  (匹配算法增强、破冰话题生成、关系建议)               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 技术选型建议

| 模块 | 技术选型 | 原因 |
|------|---------|------|
| **心理测评引擎** | 自研问卷 + AI 解读 | 问卷逻辑简单，AI 解读是核心差异化 |
| **投射测评引擎（房树人）** | AI 图像识别 + 心理分析模型 | 需要图像识别能力，可接入 Claude Vision |
| **文化测评引擎（八字/星盘）** | 自研计算 + AI 解读 | 八字星盘计算有成熟算法，AI 解读增值 |
| **画像融合引擎** | 自研规则 + AI 综合判断 | 需要处理多源数据冲突和置信度 |
| **匹配增强层** | 自研算法 + AI 建议 | 算法部分规则化，建议部分 AI 生成 |

### 9.3 第三方服务接入建议

| 服务 | 是否接入 | 原因 |
|------|---------|------|
| **专业心理测评平台 API** | 不建议 | 解读权不在我们手里，无法 AI Native |
| **八字/星盘计算 API** | 可接入 | 计算复杂，有成熟服务可调用 |
| **AI 图像识别（房树人）** | 接入 Claude Vision | 图像识别能力 Claude 已具备 |
| **AI 对话式测评** | 自研 | 这是核心差异化能力，必须自研 |

---

## 十、数据隐私与安全

### 10.1 敏感数据定义

| 数据类型 | 隐私等级 | 存储策略 |
|---------|---------|---------|
| **性格测评结果** | 中敏感 | 加密存储，用户可删除 |
| **投射测试结果（房树人）** | 高敏感 | 加密存储，用户可删除 |
| **八字/星盘数据** | 中敏感 | 用户自主选择是否提供 |
| **关系诊断数据** | 高敏感 | 加密存储，仅用户可见 |
| **画像更新历史** | 中敏感 | 存储但定期清理 |

### 10.2 用户授权策略

```
注册时：
"我们需要了解你的性格来帮你匹配，你可以选择：
1. 完成核心测评（推荐） - 匹配更精准
2. 暂时跳过 - 匹配质量可能下降
3. 不参与测评 - 仅基础匹配"

提供八字/星盘时：
"你是否愿意提供生辰信息？
1. 愿意 - 可获得传统文化匹配分析
2. 不愿意 - 仅现代心理学匹配
说明：你的生辰信息仅用于匹配分析，不会用于其他用途"
```

### 10.3 数据删除权

- 用户可随时删除任何测评结果
- 删除后画像相应维度标记为"未知"
- 删除不影响已建立的匹配关系

---

## 十一、已确认的关键问题

### 11.1 产品决策问题（已确认）

| 问题 | 确认方案 |
|------|---------|
| **AI 响应慢怎么办？** | ✅ 问卷部分用传统形式（快速无卡顿），AI 只做结果解读 |
| **问卷太长怎么办？** | ✅ 精简版（大五20题、依恋12题、恋爱语言10题），分批做 |
| **切入点怎么设计？** | ✅ 对话中自然切入 + 输入框加号入口（用户可主动测评） |
| **如何激励用户做完？** | ✅ 即时反馈 + 结果有趣可分享 + 功能解锁 + 匹配质量提升 + 勋章成就 |

### 11.2 技术决策问题（待确认）

| 问题 | 选项 | 待确认 |
|------|------|--------|
| **房树人图像识别用什么模型？** | A. Claude Vision / B. 自研模型 / C. 第三方服务 | ? |
| **八字星盘计算自研还是接入？** | A. 自研 / B. 接入第三方 API | ? |
| **画像数据存储在哪里？** | A. MySQL / B. MongoDB / C. Redis + MySQL | ? |
| **AI 解读用什么模型？** | A. Claude / B. Qwen / C. GLM | ? |

---

## 十二、下一步行动

### 12.1 立即启动

1. **确认产品决策问题**（第 10.1 节）
2. **确认技术决策问题**（第 10.2 节）
3. **设计核心画像数据结构**（第 4.1 节）
4. **设计第一阶段测评内容**（大五人格 + 依恋风格）

### 12.2 设计阶段

1. **AI 对话式测评流程设计**
2. **测评结果解读模板设计**
3. **匹配算法权重设计**
4. **破冰话题生成逻辑设计**

### 12.3 开发阶段

1. **测评引擎 MVP 开发**（第一阶段测评）
2. **画像存储与更新机制**
3. **匹配算法集成**
4. **AI 解读生成服务**

---

## 附录：参考资料

### A. 测评理论来源

- **大五人格**: Costa & McCrae (1992), NEO-PI-R
- **依恋理论**: Bowlby (1969), Hazan & Shaver (1987)
- **恋爱五种语言**: Gary Chapman (1995)
- **九型人格**: Riso & Hudson (1996)
- **36个问题**: Aron et al. (1997)
- **房树人测验**: Buck (1948), Hammer (1958)
- **爱情三元论**: Sternberg (1986)
- **Gottman 关系检查**: John Gottman (1990s)

### B. 实现参考

- MBTI 官方测试流程
- 16Personalities 网站体验
- Gottman Card Decks App
- We're Not Really Strangers 卡牌设计

---

**文档结束**

> **已确认方案**：
> - AI 响应慢 → 问卷用传统形式，AI 只做结果解读
> - 问卷太长 → 精简版（大五20题、依恋12题、恋爱语言10题）
> - 切入点 → 对话中自然切入 + 输入框加号入口
> - 奖励机制 → 即时反馈 + 结果可分享 + 功能解锁 + 匹配提升 + 勋章成就
> - **UI展示 → 对话中生成卡片UI，不跳转页面**
> - **数据存储 → 写入现有 user_personas.self_personality_traits_json 字段**
>
> **下一步**：确认技术决策问题（11.2 节），然后进入具体测评内容设计。

---

## 附录 C：大五人格完整落地方案

### C.1 大五人格五维度

| 维度 | 中文名称 | 测什么 | 高分特征 | 低分特征 |
|------|---------|--------|---------|---------|
| **Openness** | 开放性 | 是否愿意尝试新事物 | 好奇、创意、冒险 | 传统、务实、保守 |
| **Conscientiousness** | 尽责性 | 做事是否靠谱、有计划 | 负责、自律、有计划 | 随性、拖延、散漫 |
| **Extraversion** | 外向性 | 是否外向、喜欢社交 | 热情、健谈、活跃 | 内向、安静、独处 |
| **Agreeableness** | 宜人性 | 是否好相处、善良 | 善良、合作、信任 | 竞争、批判、冷漠 |
| **Neuroticism** | 神经质 | 情绪是否稳定 | 焦虑、情绪化、敏感 | 稳定、冷静、从容 |

### C.2 精简版20题具体内容

每维度4题，共20题：

#### 开放性（4题）

```
第1题：你喜欢尝试新的餐厅、新的食物吗？
A. 非常喜欢  B. 比较喜欢  C. 无所谓  D. 不太喜欢  E. 非常不喜欢

第2题：你对艺术、音乐、文学感兴趣吗？
A. 非常感兴趣  B. 比较感兴趣  C. 一般  D. 不太感兴趣  E. 完全不感兴趣

第3题：你喜欢思考抽象的问题、探索新的想法吗？
A. 非常喜欢  B. 比较喜欢  C. 一般  D. 不太喜欢  E. 非常不喜欢

第4题：你更喜欢熟悉的事物，还是新奇的事物？
A. 更喜欢新奇  B. 都可以  C. 无所谓  D. 更喜欢熟悉  E. 只喜欢熟悉
```

#### 尽责性（4题）

```
第5题：你做事前会制定详细的计划吗？
A. 总是如此  B. 经常如此  C. 有时如此  D. 很少如此  E. 几乎从不

第6题：你能按时完成任务，不拖延吗？
A. 总是如此  B. 经常如此  C. 有时如此  D. 很少如此  E. 几乎从不

第7题：你注重细节，做事追求完美吗？
A. 总是如此  B. 经常如此  C. 有时如此  D. 很少如此  E. 几乎从不

第8题：你有明确的目标，并为之努力吗？
A. 总是如此  B. 经常如此  C. 有时如此  D. 很少如此  E. 几乎从不
```

#### 外向性（4题）

```
第9题：你喜欢参加热闹的聚会、社交活动吗？
A. 非常喜欢  B. 比较喜欢  C. 无所谓  D. 不太喜欢  E. 非常不喜欢

第10题：你容易和陌生人聊天、交朋友吗？
A. 非常容易  B. 比较容易  C. 一般  D. 不太容易  E. 非常困难

第11题：你更喜欢独处，还是和一群人在一起？
A. 更喜欢一群人  B. 都可以  C. 无所谓  D. 更喜欢独处  E. 只喜欢独处

第12题：你是一个活泼、健谈的人吗？
A. 非常活泼  B. 比较活泼  C. 一般  D. 不太活泼  E. 非常安静
```

#### 宜人性（4题）

```
第13题：你愿意帮助别人，即使对自己没好处吗？
A. 非常愿意  B. 比较愿意  C. 一般  D. 不太愿意  E. 非常不愿意

第14题：你相信大多数人都是善良的、值得信任的吗？
A. 非常相信  B. 比较相信  C. 一般  D. 不太相信  E. 完全不相信

第15题：你避免和别人发生冲突，愿意妥协吗？
A. 总是如此  B. 经常如此  C. 有时如此  D. 很少如此  E. 几乎从不

第16题：你是一个善良、体贴的人吗？
A. 非常善良  B. 比较善良  C. 一般  D. 不太善良  E. 非常冷漠
```

#### 神经质（4题）

```
第17题：你容易感到焦虑、紧张吗？
A. 经常如此  B. 有时如此  C. 偶尔如此  D. 很少如此  E. 几乎从不

第18题：你情绪波动大吗？（容易生气、伤心、情绪化）
A. 经常如此  B. 有时如此  C. 偶尔如此  D. 很少如此  E. 几乎从不

第19题：你容易感到沮丧、失落吗？
A. 经常如此  B. 有时如此  C. 偶尔如此  D. 很少如此  E. 几乎从不

第20题：你面对压力时能保持冷静吗？
A. 非常冷静  B. 比较冷静  C. 一般  D. 不太冷静  E. 非常焦虑
```

### C.3 数据存储：写入现有偏好表

#### C.3.1 字段设计

```sql
-- 新增字段到 user_personas 表
ALTER TABLE user_personas 
ADD COLUMN self_personality_traits_json TEXT DEFAULT NULL 
COMMENT '性格特质测评结果（JSON格式，包含大五人格、依恋风格、恋爱语言等）';
```

#### C.3.2 存储内容结构

```json
// self_personality_traits_json 存储内容示例
{
  "big_five": {
    "assessed_at": "2026-05-31T10:00:00Z",
    "scores": {
      "openness": 65,
      "conscientiousness": 78,
      "extraversion": 35,
      "agreeableness": 72,
      "neuroticism": 28
    },
    "labels": ["安静的观察者", "稳重靠谱", "内心细腻"],
    "confidence": 0.75,
    "version": "v1.0"
  },
  
  "attachment": {
    "assessed_at": "2026-05-31T10:05:00Z",
    "type": "secure",
    "scores": {
      "secure": 85,
      "anxious": 15,
      "avoidant": 10,
      "fearful": 5
    },
    "confidence": 0.80
  },
  
  "love_language": {
    "assessed_at": "2026-05-31T10:10:00Z",
    "primary": "肯定言词",
    "secondary": "精心时刻",
    "ranking": [
      {"language": "肯定言词", "score": 85},
      {"language": "精心时刻", "score": 70},
      {"language": "身体接触", "score": 60},
      {"language": "服务行动", "score": 50},
      {"language": "接受礼物", "score": 40}
    ]
  }
}
```

#### C.3.3 写入逻辑

```python
# 写入性格特质到偏好表
async def save_personality_traits_to_persona(
    user_key: str,
    assessment_type: str,  # 'big_five', 'attachment', etc.
    traits_data: dict
):
    """
    将性格特质测评结果写入 user_personas 表
    """
    # 1. 获取现有 personality_traits_json
    persona = get_user_persona(user_key)
    existing_traits = persona.get("self_personality_traits_json") or {}
    
    # 2. 更新对应测评类型的数据
    existing_traits[assessment_type] = traits_data
    
    # 3. 写入 user_personas 表
    update_user_persona(
        user_key,
        {"self_personality_traits_json": json.dumps(existing_traits)}
    )
    
    # 4. 同时写入 user_persona_observations 表（记录来源）
    insert_observation(
        user_key=user_key,
        field_name=f"self_personality_traits_json.{assessment_type}",
        field_value=json.dumps(traits_data),
        source_type="explicit",  # 用户主动测评
        confidence_score=traits_data.get("confidence", 0.75),
        evidence_text=f"用户完成{assessment_type}测评",
        source_channel="assessment"
    )

# 具体写入大五人格
async def save_big_five_to_persona(
    user_key: str,
    scores: dict,
    labels: list
):
    """
    写入大五人格测评结果
    """
    traits_data = {
        "assessed_at": datetime.now().isoformat(),
        "scores": scores,
        "labels": labels,
        "confidence": 0.75,  # 精简版可信度
        "version": "v1.0"
    }
    
    await save_personality_traits_to_persona(
        user_key,
        "big_five",
        traits_data
    )
```

### C.4 匹配算法应用

#### C.4.1 匹配权重设计

```
总体匹配分 = 
  外向性匹配分 × 0.3
  + 尽责性匹配分 × 0.2
  + 神经质匹配分 × 0.3
  + 开放性匹配分 × 0.1
  + 宜人性匹配分 × 0.1

权重解释：
- 外向性权重高（0.3）：影响相处方式，内向+外向=互补高分
- 神经质权重高（0.3）：影响关系稳定性，情绪稳定=高分
- 尽责性权重中等（0.2）：影响生活规划，相似=高分
- 开放性权重低（0.1）：影响兴趣爱好，差异可以互补
- 宜人性权重低（0.1）：影响相处融洽，相似=高分
```

#### C.4.2 各维度匹配逻辑

**外向性匹配**：
```
用户A外向性：35（内向）
用户B外向性：70（外向）

差值 = |35 - 70| = 35
互补评分：差值在20-50之间 = 90分（互补高分）

公式：
差值在20-50 → 匹配分 = 90（互补）
差值 < 20 → 匹配分 = 70（相似）
差值 > 50 → 匹配分 = 50（差异太大）
```

**神经质匹配**：
```
用户A神经质：28（稳定）
用户B神经质：30（稳定）

都低 → 匹配分 = 95（最健康组合）
一高一低 → 匹配分 = 70（一个稳住另一个）
都高 → 匹配分 = 40（互相引发情绪）
```

#### C.4.3 匹配实现代码

```python
# 读取性格特质用于匹配
def get_user_personality_traits(user_key: str) -> dict:
    """从 user_personas 表读取性格特质"""
    persona = get_user_persona(user_key)
    traits_json = persona.get("self_personality_traits_json")
    
    if traits_json:
        return json.loads(traits_json)
    
    return {}

# 计算大五人格匹配分
def calculate_big_five_match_score(
    user_key1: str,
    user_key2: str
) -> dict:
    """计算大五人格匹配分"""
    traits1 = get_user_personality_traits(user_key1)
    traits2 = get_user_personality_traits(user_key2)
    
    big_five1 = traits1.get("big_five", {}).get("scores", {})
    big_five2 = traits2.get("big_five", {}).get("scores", {})
    
    if not big_five1 or not big_five2:
        return {"score": None, "reason": "缺少大五人格数据"}
    
    # 计算各维度匹配分
    extraversion_match = calculate_extraversion_match(
        big_five1.get("extraversion", 50),
        big_five2.get("extraversion", 50)
    )
    
    neuroticism_match = calculate_neuroticism_match(
        big_five1.get("neuroticism", 50),
        big_five2.get("neuroticism", 50)
    )
    
    conscientiousness_match = calculate_conscientiousness_match(
        big_five1.get("conscientiousness", 50),
        big_five2.get("conscientiousness", 50)
    )
    
    openness_match = calculate_openness_match(
        big_five1.get("openness", 50),
        big_five2.get("openness", 50)
    )
    
    agreeableness_match = calculate_agreeableness_match(
        big_five1.get("agreeableness", 50),
        big_five2.get("agreeableness", 50)
    )
    
    # 综合匹配分
    total_score = (
        extraversion_match * 0.3 +
        neuroticism_match * 0.3 +
        conscientiousness_match * 0.2 +
        openness_match * 0.1 +
        agreeableness_match * 0.1
    )
    
    return {
        "score": total_score,
        "dimension_scores": {
            "extraversion": extraversion_match,
            "neuroticism": neuroticism_match,
            "conscientiousness": conscientiousness_match,
            "openness": openness_match,
            "agreeableness": agreeableness_match
        }
    }
```

### C.5 破冰话题生成

#### C.5.1 话题生成规则

根据双方大五人格差异，生成话题建议：

```
外向性差异大（用户内向，对方外向）：
→ "你平时喜欢热闹还是安静的活动？"
→ "你周末通常怎么过？在家还是出门？"

神经质相似（都情绪稳定）：
→ "你面对压力时会怎么处理？"
→ "你觉得恋爱中最重要的是什么？"

尽责性相似（都做事有计划）：
→ "你做事喜欢提前计划还是随性？"
→ "你对未来有什么规划？"

开放性差异大：
→ "你喜欢尝试新事物还是喜欢熟悉的？"
→ "你最近有什么新的兴趣或爱好？"
```

#### C.5.2 话题数据结构

```typescript
interface IcebreakerTopic {
  topicId: string;
  topicContent: string;         // 话题内容
  source: string;               // 来源维度（如：外向性差异）
  reason: string;               // 为什么推荐这个话题
  type: 'question' | 'discussion' | 'activity';
  suitableFor: 'first_chat' | 'deep_chat' | 'conflict';
}
```

### C.6 完整用户流程

```
┌─────────────────────────────────────────────────────────────┐
│               大五人格测评完整流程                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 用户说："我想测测我的性格"                                │
│     ↓                                                       │
│  2. AI 返回测评介绍卡片                                     │
│     └─────────────────────────────────────┐               │
│     │ 📊 大五人格测试                       │               │
│     │ 约5分钟 · 20题                       │               │
│     │ [开始测评]                            │               │
│     └─────────────────────────────────────┘               │
│                                                             │
│  3. 用户点 [开始测评]                                        │
│     ↓                                                       │
│  4. AI 返回第1题卡片（在对话界面中）                         │
│     └─────────────────────────────────────┐               │
│     │ 第1题/共20题                          │               │
│     │ 你喜欢尝试新的餐厅吗？                │               │
│     │ ○ A. 非常喜欢 ○ B. 喜欢 ○ C. 无所谓  │               │
│     │ ○ D. 不太喜欢 ○ E. 非常不喜欢        │               │
│     │ 进度：■○○○○○○○○○○○○○○○○○○○○          │               │
│     └─────────────────────────────────────┘               │
│                                                             │
│  5. 用户连续答题（点选项 → 下一题卡片）                      │
│     ↓                                                       │
│  6. 答完4题后，显示反馈卡片                                  │
│     └─────────────────────────────────────┐               │
│     │ 💡 你的开放性：65分                   │               │
│     │ 你愿意尝试新事物，但不会太冲动        │               │
│     └─────────────────────────────────────┘               │
│     （显示2秒后消失，继续答题）                              │
│                                                             │
│  7. 答完20题后，显示结果卡片                                 │
│     └─────────────────────────────────────┐               │
│     │ 🎉 测评完成！                         │               │
│     │ "你是安静的观察者"                    │               │
│     │ 开放性：65 ████████░░                 │               │
│     │ 尽责性：78 █████████░                 │               │
│     │ 外向性：35 ███░░░░░░░░                │               │
│     │ 宜人性：72 ███████░░░                 │               │
│     │ 神经质：28 ██░░░░░░░░░░               │               │
│     │ [分享朋友圈] [查看匹配建议]           │               │
│     └─────────────────────────────────────┘               │
│                                                             │
│  8. 等2秒后，显示AI解读卡片                                 │
│     └─────────────────────────────────────┐               │
│     │ AI 解读                               │               │
│     │ "你是一个内向但稳重的人..."           │               │
│     │ "建议你找一个外向性60-80的人..."      │               │
│     └─────────────────────────────────────┘               │
│                                                             │
│  9. 测评结果写入偏好表                                       │
│     ├─ user_personas.self_personality_traits_json           │
│     └─ 后续匹配时使用这些数据                               │
│                                                             │
│  10. 用户选择下一步                                         │
│     ├─ [分享朋友圈] → 生成分享卡片                          │
│     ├─ [查看匹配建议] → 返回匹配建议卡片                    │
│     └─ [继续聊天] → 回到正常对话                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

**附录 C 结束**