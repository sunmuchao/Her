# 发现页测评画像接入方案 - AI自主判断版

> 修订日期：2026-06-05
> 当前定位：发现页测评画像接入的主落地文档
> 适用范围：Discovery 搜索链路、AI 解释链路、前端候选卡展示、灰度与验收

---

## 一句话先说清

现在系统已经做到“AI 能读测评并解释”，但还没有做到“测评真正参与排序”。  
这份方案的目标不是再讲原则，而是把剩余工作按阶段落到代码、接口、前端和验收口径里。

---

## 1. 当前真实状态

### 1.1 已完成

当前代码里已经落下去的部分：

1. 用户测评结果会写入 `user_personas.self_personality_traits_json`
2. 候选人搜索结果已经能带出 `personality_match_context`
3. Discovery 页面上下文 `page_summary.result_cards` 已经包含候选人的测评原始数据
4. AI 在用户追问“为什么推荐她”“MBTI/依恋为什么合拍”时，已经可以基于当前候选人直接解释
5. 如果模型没有正确解释，后端已有 fallback，可以直接按 MBTI / 依恋 / 价值观生成说明
6. 首轮结果返回时，后端已经会追加一段简短的测评解释文案
7. 前端候选卡已经能显示 MBTI 和依恋类型

### 1.2 还没完成

当前还缺的核心点：

1. 排序层还没有真正把测评作为排序因子
2. `reason_summary` 仍然经常是“城市一致、关系目标一致”这类基础资料理由，不是测评理由
3. “继续放宽 / 看更多匹配 / 再来一批”这些路径还没有统一成稳定的测评解释输出
4. 还没有灰度开关、trace 字段、观测指标，无法回答“这轮推荐到底有没有用上测评”
5. 还没有完整的线上验收清单，导致功能看起来“像做了”，但不好判断“到底落没落完”

### 1.3 所以现在系统的本质

当前系统不是“测评驱动匹配”，而是：

- 基础资料决定召回和主排序
- 测评数据主要用于解释层
- 前端只展示了少量测评字段

这也是为什么用户会看到：

- 卡片里有 MBTI / 依恋
- 但“小雅为什么推荐她”的正文里不一定总是解释测评原因
- “继续放宽”之后返回的理由也常常还是基础条件理由

---

## 2. 最终目标

把发现页升级成下面这套完整链路：

1. 基础资料继续负责硬筛和主召回
2. 测评数据进入排序层，但只做保守加权，不做硬筛
3. AI 直接读取原始测评数据，自主生成解释
4. 前端把“为什么推荐”明确展示给用户
5. 后端能记录每一轮是否真的用了测评，方便灰度和复盘

最终效果应该是：

- 候选人能因为测评更合拍而更靠前
- 用户追问时，AI 能说清楚为什么
- 用户不追问时，首轮推荐也能主动带一点测评理由
- 运营和研发能查到这轮推荐到底有没有用测评，以及用了什么

---

## 3. 核心设计原则

### 3.1 原始数据优先，不先翻译成人话标签

代码负责搬运原始数据，例如：

- `mbti.type_code`
- `attachment.type_code / anxiety / avoidance`
- `values.top_values`
- `big_five.scores`

不要在数据层提前写死：

- “INFP = 敏感”
- “secure = 稳定型”
- “这俩很配 = 0.8 分”

因为这样会丢信息，也会把 AI 锁死在模板解释里。

### 3.2 测评只做软排序，不做硬筛

不能把测评变成：

- 必须同 MBTI
- 必须安全型
- 必须价值观完全一致

正确做法是：

- 城市、年龄、恋爱目标继续硬筛
- 测评只做 bonus / penalty
- bonus 不能大到压过基础硬条件

### 3.3 排序层和解释层分工

排序层负责：

1. 结构化、稳定、可回放的加权
2. 给出一个有限的 `personality_bonus`
3. 产出用于排位和埋点的结构化结果

AI 层负责：

1. 读取双方原始测评
2. 结合候选人资料做自然语言解释
3. 在候选人没测评时，谨慎地根据资料做推断

---

## 4. 当前代码基线

以下能力已经在代码里存在，可作为后续改造基础：

### 4.1 后端

- `external-systems/partner-discovery-system/discovery_system/service_context.py`
  - `page_summary.result_cards` 已带上 `personality_match_context`
- `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`
  - prompt 已明确要求优先解释已展示候选人的测评原因
  - 已有解释类 fallback
- `external-systems/partner-discovery-system/discovery_system/service.py`
  - 已有服务层 explanation fallback
  - 已有首轮结果的主动测评 blurb
- `external-systems/partner-discovery-system/discovery_system/view_models.py`
  - 候选卡已带 `personality_match_context`

### 4.2 前端

- `frontend/her-app/components/her/discovery-candidate-card.tsx`
  - 已显示 MBTI / 依恋
- `frontend/her-app/lib/discovery/map-discovery-view.ts`
  - 已把后端 `personality_match_context` 透传到卡片

### 4.3 测试

已经有对应单测覆盖：

1. `page_summary.result_cards` 是否带测评上下文
2. 用户追问时是否能输出测评解释
3. 首轮结果是否追加主动测评说明
4. 前端映射后是否还能拿到 MBTI / 依恋字段

---

## 5. 完整落地方案

按四个阶段推进，前两阶段是必须完成，后两阶段是上线前建议完成。

### Phase 1：解释链路彻底统一

目标：无论用户是“首轮看到结果”，还是“继续放宽”“看更多匹配”“为什么推荐她”，都能稳定产出测评解释。

#### 5.1 要解决的问题

当前问题不是“AI 不会解释”，而是“不同结果路径里，`reason_summary` 和 assistant message 的生成逻辑不统一”。

#### 5.2 后端改造

需要统一这几类输出入口：

1. 初次开场推荐
2. 用户继续放宽条件后的推荐
3. 用户点击“看更多匹配”后的推荐
4. 用户追问某个候选人的推荐理由

具体改造建议：

1. 在 `service.py` 增加统一的 `build_personality_reason_summary(...)`
2. 在 `view_models.py` 里让 `reason_summary` 优先使用测评理由，基础资料理由降级为兜底
3. 在 `_build_result_cards(...)` 这条链路里，所有 `selected_candidates` 都走同一套理由生成器
4. 如果候选人有测评：
   - 优先写 MBTI / 依恋 / 价值观
5. 如果候选人没测评：
   - 用“从资料看”“可能”“更像”这类谨慎措辞

#### 5.3 推荐的数据结构

为每个候选人补一个统一解释结构，供埋点、AI、前端共用：

```json
{
  "personality_reasoning": {
    "used": true,
    "source": "traits_pair" ,
    "signals": ["mbti", "attachment", "values"],
    "summary": "MBTI 节奏接近，依恋都偏安全型，价值观也有重叠",
    "confidence": "medium"
  }
}
```

说明：

1. `used`：这轮卡片理由是否真的使用了测评
2. `source`：
   - `traits_pair`：双方都有测评
   - `candidate_only_traits`：只有候选人有测评
   - `profile_inference`：无测评，基于资料推断
3. `signals`：本轮真正用了哪些维度
4. `summary`：给前端和埋点复用的短说明
5. `confidence`：避免把弱推断说得太满

#### 5.4 Phase 1 验收标准

以下场景都要成立：

1. 首轮推荐文案里出现测评理由
2. “继续放宽”后的文案里仍然出现测评理由
3. “看更多匹配”后的新一轮结果里，至少前 2 张卡片有测评解释
4. 用户问“为什么推荐张安萌”时，不会退回“我先整理一下你的偏好”
5. 候选人没测评时，文案不会伪造 MBTI 或依恋类型

---

### Phase 2：测评进入排序层

目标：不只是“会解释”，而是“真的影响排序”，但影响要可控。

#### 5.5 排序策略

排序公式建议采用：

```text
final_score = base_score + personality_bonus
```

其中：

- `base_score`：现有搜索链路已有主分
- `personality_bonus`：新增测评加权

约束：

1. `personality_bonus` 上限建议控制在主分的 10% 到 15%
2. 只有双方存在可比较维度时才加权
3. 某一维度缺失时直接跳过，不补默认分

#### 5.6 personality_bonus 的建议拆分

先做轻量版，不要一步上复杂公式：

```text
personality_bonus =
  values_bonus
  + attachment_bonus
  + temperament_bonus
```

建议权重：

1. `values_bonus`
   - 优先级最高
   - 看 `top_values` 重叠
2. `attachment_bonus`
   - 次高
   - 安全型+安全型加分
   - 焦虑高 + 回避高这类追逃组合减分
3. `temperament_bonus`
   - 最轻
   - 优先大五，其次 MBTI

#### 5.7 代码落点

建议新增或改造：

1. `partner_search/personality_traits_reader.py`
   - 继续负责读取和标准化测评原始数据
2. `external-systems/partner-discovery-system/discovery_system/service_integrations.py`
   - 在搜索结果拼装处加入 personality bonus 与 trace
3. `partner_search` 搜索排序逻辑
   - 在现有 base score 基础上叠加 personality bonus

建议输出：

```json
{
  "score": 0.81,
  "base_score": 0.74,
  "personality_bonus": 0.07,
  "personality_scoring_trace": {
    "values_bonus": 0.04,
    "attachment_bonus": 0.02,
    "temperament_bonus": 0.01,
    "used_dimensions": ["values", "attachment", "mbti"]
  }
}
```

#### 5.8 排序层必须遵守的边界

1. 不根据单一 MBTI 直接把人顶到最前
2. 不因为没做测评就一刀切降权
3. 测评 bonus 只在候选人基础条件已过关后生效
4. 候选人没有测评时，不能产生伪造 bonus

#### 5.9 Phase 2 验收标准

1. 同一批候选人在开启 personality ranking 前后，排序有小幅变化，但不会颠覆基础条件
2. trace 能说明某人为什么多了 0.07 分
3. 没测评的候选人不会被异常打压
4. 双方价值观明显重叠时，候选人更容易进入前排

---

### Phase 3：灰度、trace、可观测性

目标：上线后能回答“到底有没有用”“效果怎么样”。

#### 5.10 必加的开关

至少加 3 个 feature flag：

1. `discovery_personality_explanation_enabled`
   - 控制解释层
2. `discovery_personality_ranking_enabled`
   - 控制排序加权
3. `discovery_personality_card_badges_enabled`
   - 控制前端卡片展示

#### 5.11 必打的 trace 字段

每轮搜索结果建议记录：

```json
{
  "personality_trace": {
    "self_traits_available": true,
    "candidate_traits_count": 6,
    "ranking_enabled": true,
    "explanation_enabled": true,
    "top_candidates_used_personality": [1001, 1004],
    "fallback_explanation_used": false
  }
}
```

#### 5.12 必看的指标

上线后至少观察：

1. 测评解释触发率
2. 首轮结果里测评理由覆盖率
3. 用户追问“为什么推荐”的占比
4. 展示后点击候选卡 CTR
5. 展示后继续追问率 / 继续放宽率
6. 开启 personality ranking 前后的候选卡点击变化

#### 5.13 Phase 3 验收标准

1. 任意一轮推荐都能查到是否用了测评
2. 排序 bonus 能回放
3. fallback 是否触发可见
4. 灰度关闭后，系统回退到原有逻辑而不出错

---

### Phase 4：前端呈现和产品打磨

目标：用户不需要追问，也能感知“为什么是这几位”。

#### 5.14 卡片层建议

当前卡片只展示 MBTI / 依恋，建议补 2 个点：

1. 在卡片 `matchReason` 里优先展示测评短理由
2. 在卡片详情或展开态里增加“测评角度”小模块

建议展示样式：

- `MBTI 节奏接近`
- `依恋都偏安全型`
- `都看重长期稳定`

不要展示：

- 大段理论解释
- 看起来像算命的话
- 绝对化语气，例如“你们一定很合适”

#### 5.15 结果组文案建议

每一组结果的 assistant message 推荐结构：

1. 先说这轮为什么扩大范围
2. 再说“从测评角度看”谁更值得先看
3. 最后给一个继续动作

例如：

```text
这轮我先把年龄和城市稍微放宽了一点，帮你多看几位。
从测评角度看，A 和你在价值观、依恋节奏上更顺，B 虽然类型不同，但相处方式比较稳。
你要是愿意，我可以继续往外扩一层，或者单独展开讲其中某一位。
```

#### 5.16 Phase 4 验收标准

1. 用户首屏就能看到“为什么推荐”
2. 卡片上的理由和 AI 正文不要互相打架
3. 无测评用户不会看到生硬的空占位

---

## 6. 推荐实施顺序

建议按下面顺序落，不要一口气同时改完所有层：

### 第一周

1. 统一 `reason_summary` 生成逻辑
2. 打通 “继续放宽 / 看更多匹配” 的测评解释
3. 补后端单测

### 第二周

1. 接入 `personality_bonus`
2. 输出 `base_score / personality_bonus / trace`
3. 做 ranking flag 灰度

### 第三周

1. 前端卡片改成优先显示测评理由
2. 补结果组文案样式
3. 加日志和指标看板

---

## 7. 项目执行清单

这一节不是讲原则，而是给排期和分工用的。

### 7.1 P0 / P1 / P2 总览

| 优先级 | 目标 | 负责人类型 | 预估人天 | 是否上线前必须 |
|---|---|---|---:|---|
| P0 | 统一解释链路 + 测评进入排序 + 基础 trace | 后端 | 3-5 | 是 |
| P1 | 灰度开关 + 埋点观测 + 前端理由展示 | 后端 + 前端 | 2-4 | 建议是 |
| P2 | 结果文案优化 + 详情页测评角度 + 精细化排序 | 后端 + 前端 + 产品 | 2-3 | 否 |

### 7.2 P0 执行项

#### P0-1 统一推荐理由生成

- 目标：所有推荐入口都稳定输出测评理由
- 负责人类型：后端
- 文件落点：
  - `external-systems/partner-discovery-system/discovery_system/service.py`
  - `external-systems/partner-discovery-system/discovery_system/view_models.py`
- 要做的事：
  - 抽统一的 `build_personality_reason_summary(...)`
  - 首轮推荐、继续放宽、看更多匹配、追问解释都走同一套逻辑
  - `reason_summary` 优先测评理由，基础资料改为兜底
- 验收标准：
  - 首轮推荐有测评理由
  - “继续放宽”不退回基础条件话术
  - “看更多匹配”新卡片仍然有测评理由

#### P0-2 接入 personality bonus

- 目标：测评真实参与排序，但只做小幅加权
- 负责人类型：后端
- 文件落点：
  - `external-systems/partner-discovery-system/discovery_system/service_integrations.py`
  - `partner_search/personality_traits_reader.py`
  - `partner_search` 现有排序逻辑所在文件
- 要做的事：
  - 增加 `final_score = base_score + personality_bonus`
  - bonus 先拆成 `values_bonus + attachment_bonus + temperament_bonus`
  - 控制 bonus 上限，避免压过基础条件
- 验收标准：
  - 排序会有小幅变化
  - 没测评的候选人不被异常降权
  - 日志里能看到 `base_score` 和 `personality_bonus`

#### P0-3 补基础 trace

- 目标：每轮推荐都能查到有没有用测评
- 负责人类型：后端
- 文件落点：
  - `external-systems/partner-discovery-system/discovery_system/service_integrations.py`
  - Discovery 搜索结果持久化或日志输出位置
- 要做的事：
  - 输出 `self_traits_available`
  - 输出 `used_dimensions`
  - 输出 `fallback_explanation_used`
  - 输出 `top_candidates_used_personality`
- 验收标准：
  - 任意一轮推荐都能回放是否用了测评
  - 排序和解释是否命中测评可查

#### P0-4 补测试

- 目标：避免后面路径一改就把解释打回去
- 负责人类型：后端
- 文件落点：
  - `external-systems/partner-discovery-system/tests/test_discovery_system.py`
- 要做的事：
  - 补“继续放宽”解释测试
  - 补“看更多匹配”解释测试
  - 补“无测评候选人”保守措辞测试
  - 补 `personality_bonus` trace 测试
- 验收标准：
  - P0 新增测试全部通过
  - 关键路径回归不破

### 7.3 P1 执行项

#### P1-1 加 feature flag

- 目标：支持灰度和快速回退
- 负责人类型：后端
- 文件落点：
  - Discovery 配置和 feature flag 读取位置
- 要做的事：
  - 增加 `discovery_personality_explanation_enabled`
  - 增加 `discovery_personality_ranking_enabled`
  - 增加 `discovery_personality_card_badges_enabled`
- 验收标准：
  - 每个能力都能单独开关
  - 关闭后系统回退到旧逻辑不报错

#### P1-2 前端展示测评短理由

- 目标：用户不追问也能看懂推荐原因
- 负责人类型：前端
- 文件落点：
  - `frontend/her-app/components/her/discovery-candidate-card.tsx`
  - `frontend/her-app/lib/types/discovery.ts`
  - `frontend/her-app/lib/discovery/map-discovery-view.ts`
- 要做的事：
  - 卡片优先显示 `personality_reasoning.summary`
  - 无测评时正常回退基础理由
  - 保留 MBTI / 依恋标签显示
- 验收标准：
  - 卡片理由与 assistant message 基本一致
  - 无测评卡片不出现空块或脏字段

#### P1-3 补埋点与观测

- 目标：上线后能看效果
- 负责人类型：后端 + 数据
- 文件落点：
  - 推荐结果日志
  - 埋点事件定义
- 要做的事：
  - 记录测评解释覆盖率
  - 记录候选卡 CTR
  - 记录“为什么推荐”追问率
  - 记录 ranking 开关前后点击变化
- 验收标准：
  - 看板上能看到核心指标
  - 能按开关状态切分数据

### 7.4 P2 执行项

#### P2-1 结果组文案优化

- 目标：推荐文案更自然，不像系统拼接
- 负责人类型：产品 + 后端
- 文件落点：
  - `external-systems/partner-discovery-system/discovery_system/service.py`
  - `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`
- 要做的事：
  - 统一“为什么放宽 + 从测评角度看谁更值得先看 + 下一步动作”结构
- 验收标准：
  - 首轮和放宽后的话术都更自然

#### P2-2 详情页补测评角度模块

- 目标：点开候选人后能看更完整的解释
- 负责人类型：前端 + 后端
- 文件落点：
  - discovery 详情 view model
  - discovery 详情相关组件
- 要做的事：
  - 增加测评摘要模块
  - 展示 MBTI / 依恋 / 价值观短解释
- 验收标准：
  - 详情页能承接卡片里的短理由

#### P2-3 精细化排序

- 目标：在轻量 bonus 稳定后，再提高区分度
- 负责人类型：后端
- 文件落点：
  - 排序逻辑所在文件
- 要做的事：
  - 优化价值观顺序权重
  - 优化依恋风险分级
  - 优先用大五，MBTI 作为补充
- 验收标准：
  - 调整后排序波动可解释
  - 没有出现异常大跳变

### 7.5 推荐排期

如果按最小可上线版本推进，建议这样排：

1. 第 1 周：完成 P0
2. 第 2 周：完成 P1
3. 第 3 周：按资源决定是否做 P2

### 7.6 负责人建议

最省事的配置是：

1. 1 名后端主负责 P0 和 P1 后端项
2. 1 名前端负责卡片展示和详情承接
3. 1 名产品或运营负责验收文案与灰度观察

### 7.7 上线口径

只有下面条件同时成立，才算可以说“测评接入发现页落地完成”：

1. 推荐结果正文稳定出现测评理由
2. 卡片理由和正文理由一致
3. 测评对排序有真实但有限的影响
4. 任意一轮都能查到是否用了测评
5. 开关关闭后能稳定回退

---

## 8. 需要改的文件清单

### 必改

1. `external-systems/partner-discovery-system/discovery_system/service.py`
   - 统一解释入口
   - 统一结果组文案
2. `external-systems/partner-discovery-system/discovery_system/view_models.py`
   - `reason_summary` 优先级调整
   - 增加 `personality_reasoning`
3. `external-systems/partner-discovery-system/discovery_system/service_integrations.py`
   - 拼装 personality score / trace
4. `partner_search/personality_traits_reader.py`
   - 继续保证原始测评读取和标准化稳定
5. `frontend/her-app/components/her/discovery-candidate-card.tsx`
   - 展示测评短理由
6. `frontend/her-app/lib/types/discovery.ts`
   - 补充新增字段类型

### 建议补充

1. `external-systems/partner-discovery-system/tests/test_discovery_system.py`
   - 增加“继续放宽 / 看更多匹配 / 无测评候选人”覆盖
2. 前端 discovery 映射相关测试
   - 增加 `personality_reasoning.summary` 透传断言

---

## 9. 完整验收清单

只有下面这些都成立，才算真正落完：

1. 用户首次进入发现页，首轮推荐正文里出现测评理由
2. 用户点“看更多匹配”，新结果仍然有测评理由
3. 用户说“继续放宽”，结果不是只返回基础资料理由
4. 用户追问“为什么推荐她”，AI 会基于当前卡片直接解释
5. 候选卡展示的理由与 assistant message 基本一致
6. 排序日志里能看到 `personality_bonus`
7. 关闭 ranking flag 后，系统还能稳定回退
8. 候选人无测评时，解释语气谨慎，不伪造结果

---

## 10. 风险与边界

### 10.1 最大风险

不是“AI 看不懂测评”，而是：

1. 解释层和排序层口径不一致
2. 前端展示了测评，但排序并没真正使用
3. 开启排序后 bonus 过大，压过基础条件

### 10.2 控制方式

1. 先统一解释，再上排序
2. 排序 bonus 限幅
3. 所有加分项必须可追踪
4. 没测评时不强行算分

---

## 11. 最终结论

这件事的正确落法不是“继续补 MBTI 文案”，而是分成两步：

1. 先把解释链路彻底统一，让所有结果路径都能稳定说清“为什么推荐她”
2. 再把测评以保守 bonus 的方式接进排序层，并加上 trace、flag、验收指标

到这一步，发现页才算真正从：

- “基础资料筛人 + 测评点缀解释”

升级成：

- “基础资料主导召回 + 测评参与排序 + AI 自主解释推荐原因”
