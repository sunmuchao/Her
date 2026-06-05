# 价值观拍卖会 v2 方案

> 目标：把现有“价值观拍卖会”从游戏化问答，升级为“有理论骨架的游戏化价值观测量”。

## 1. 为什么要改

当前版本已经有不错的交互包装，但底层有 4 个问题：

1. 后台价值字典是自定义拼装，不是稳定的价值观理论结构。
2. 逐个展示模式本质是“最多保留 3 个”，不是真实筹码竞拍。
3. 双人分析主要看 Top3 是否重合，没利用价值观之间“接近/冲突”的结构关系。
4. 单标签结果过于粗糙，容易把复杂用户压扁成“安全感型”“自由型”。

Schwartz 体系适合这里的原因很直接：

- 它不是一堆散点价值词，而是有结构的价值圆环。
- 能解释“像”和“对冲”。
- 很适合做双人匹配，不只看相同，还能看张力。

## 2. v2 的核心原则

前台继续保留游戏感，后台切到 Schwartz 双层结构。

- 前台：用户看到的是具体拍品和取舍压力。
- 后台第一层：拍品映射到 Schwartz 10 个价值。
- 后台第二层：10 个价值汇总到 4 个高阶方向。

四个高阶方向：

- `开放变化`：自我导向、刺激
- `保守维持`：安全、顺从、传统
- `自我提升`：成就、权力
- `超越自我`：仁爱、普遍主义

## 3. Schwartz 10 价值在产品里的翻译

建议系统内部统一使用以下 10 个标准 value key：

| key | 中文 | 大白话 |
|---|---|---|
| `self_direction` | 自我导向 | 想自己决定怎么活 |
| `stimulation` | 刺激 | 想新鲜、变化、冒险 |
| `hedonism` | 享乐 | 想快乐、享受、舒服 |
| `achievement` | 成就 | 想证明自己很行 |
| `power` | 权力 | 想掌控资源和影响力 |
| `security` | 安全 | 想稳定、可预测、不失控 |
| `conformity` | 顺从 | 不想越界惹事，希望关系和秩序稳 |
| `tradition` | 传统 | 看重延续、家庭责任、既有规范 |
| `benevolence` | 仁爱 | 看重身边人的福祉和照顾 |
| `universalism` | 普遍主义 | 看重公平、包容、社会责任 |

说明：

- `hedonism` 可以挂在 `开放变化` 和 `自我提升` 中间，先简化处理为偏开放变化。
- 如果后续要升级到 19 价值，可以在 v2 数据结构里保留 `sub_values` 扩展位。

## 4. 拍品设计怎么改

### 4.1 不建议继续只保留 9 个拍品

9 个拍品太少，容易出现两个问题：

- 覆盖不全，测不出细差异。
- 用户被迫在“作者预设的冲突”里选，不是自然暴露价值排序。

建议改为：

- `核心拍品池 16 个`
- 每次测评随机展示 `10-12 个`
- 保证 10 个价值至少各出现 1 次
- 保证相邻价值、对冲价值都能被采到

这样既不会太长，也不会过度简化。

### 4.2 拍品设计原则

每个拍品只承载 1 个主价值 + 1 个次价值，最多 2 个，不要再混 3 个以上。

原因：

- 现在很多拍品同时映射 3 个隐藏价值，解释空间太大。
- 拍品越“混”，结果越不稳定。

建议字段：

```ts
type SchwartzLot = {
  lot_id: string
  title: string
  short_tagline: string
  primary_value: SchwartzValueKey
  secondary_value?: SchwartzValueKey
  primary_weight: number
  secondary_weight?: number
  quadrant: 'openness' | 'conservation' | 'self_enhancement' | 'self_transcendence'
  tension_with: string[]
}
```

### 4.3 建议拍品映射表

下面这版不是最终文案稿，但已经能直接指导建模。

| 拍品 | 示例文案 | 主价值 | 次价值 |
|---|---|---|---|
| `live_by_my_rules` | 人生大事都由你自己拍板 | `self_direction` | `freedom` 替换为无，统一收敛到 `self_direction` |
| `quit_and_go` | 随时能换城市换生活 | `stimulation` | `self_direction` |
| `days_feel_good` | 日子舒服，有空享受生活 | `hedonism` | `security` |
| `peak_performance` | 在自己的领域做到顶尖 | `achievement` | `power` |
| `have_real_influence` | 你说的话能影响很多人 | `power` | `achievement` |
| `life_is_stable` | 不怕失业，不怕生活失控 | `security` | `conformity` |
| `relationship_is_reliable` | 关系里说到做到，不折腾 | `security` | `benevolence` |
| `everyone_knows_their_role` | 家里边界清楚、秩序稳定 | `conformity` | `security` |
| `family_values_continue` | 家庭责任和传统能传下去 | `tradition` | `benevolence` |
| `care_for_my_people` | 重要的人被你照顾得很好 | `benevolence` | `security` |
| `be_fair_to_more_people` | 尽量做对更多人都公平的事 | `universalism` | `benevolence` |
| `make_society_better` | 做的事能让社会更好一点 | `universalism` | `achievement` |
| `partner_truly_gets_me` | 亲密关系里有人真正理解你 | `benevolence` | `self_direction` |
| `no_need_to_please` | 不讨好也能坚定做自己 | `self_direction` | `security` |
| `win_public_respect` | 走到哪都被当作厉害的人 | `achievement` | `power` |
| `protect_peaceful_home` | 家稳定、心也稳 | `security` | `tradition` |

注：

- 现有系统里的 `love/family/companionship/meaning` 不建议继续作为一级 value key。
- 它们更适合留在“拍品语义层”或“解释层”，不要再和理论层混在一起。

## 5. 玩法怎么改

### 5.1 从“保留 3 个”改回“真实竞拍”

现版本逐个模式最终是：

- 保留的拍品统一记 3 筹码
- 其他拍品记 0 筹码

这会丢失大量信息。

建议改为真实出价：

- 总筹码 `10`
- 单拍品可投 `0-3`
- 至少对 `4` 个拍品有出价
- 最多允许 `1` 个拍品投到 `3`

这样能避免“孤注一掷”把结果打歪。

### 5.2 推荐交互流程

保留逐个展示，但每轮不只是“留/弃”，而是三选一：

1. `不投`
2. `投 1 筹码`
3. `加重到 2/3 筹码`

到后半程再加入替换压力：

- “你还剩 2 筹码，要不要给刚才那件补码？”
- “如果给这件加码，你可能要从另一个选择里撤码。”

这样既有游戏感，也更像拍卖。

## 6. 计分模型怎么改

### 6.1 基础计分

每个拍品根据出价分，映射到标准 value key：

```python
value_score[value_key] += bid_chips * weight
```

再归一化为 0-1。

### 6.2 高阶方向分

把 10 个价值汇总成 4 个方向分：

```python
openness = self_direction + stimulation + hedonism * 0.5
conservation = security + conformity + tradition
self_enhancement = achievement + power + hedonism * 0.5
self_transcendence = benevolence + universalism
```

### 6.3 输出不要只给单标签

结果页建议输出：

- 主方向：最高的 2 个高阶方向
- 价值 Top3：10 个标准价值里的前三
- 关系翻译：这些价值进到亲密关系里意味着什么
- 冲突提醒：你内部最拉扯的两股价值是什么

例如：

- 主方向：`保守维持 + 超越自我`
- Top3：`安全 / 仁爱 / 传统`
- 关系翻译：你更看重稳定投入、相互照顾、长期可靠
- 内部拉扯：`自我导向` 也不低，说明你既要稳定，又不想完全被关系吞掉

## 7. 双人匹配算法怎么改

### 7.1 不只看同拍品

现在主要看：

- Top3 是否重合
- 一方高投另一方低投

这太表层。

建议拆成 3 层：

1. `场景共鸣`
   看拍品是否相近，适合做展示。
2. `价值对齐`
   看 10 个标准价值向量的距离。
3. `结构张力`
   看双方高分是否落在对冲象限。

### 7.2 推荐评分公式

可先用简单可控版：

```python
alignment_score = 100 - euclidean_distance(value_vector_a, value_vector_b) * K
```

再加两个修正项：

- `resonance_bonus`：双方 Top 5 价值中相同或相邻价值多，加分
- `tension_penalty`：一方高 `self_direction/stimulation`，另一方高 `security/conformity/tradition`，且都超过阈值，扣分

### 7.3 冲突判断不要只看“没选同一件”

建议定义 3 类关系：

- `同向`
  双方高分价值相同或相邻，比如 `security` 和 `benevolence`
- `差异但可协商`
  双方高分价值不一样，但不对冲，比如 `achievement` 和 `security`
- `结构冲突`
  双方高分价值位于对冲区域，比如 `self_direction` 对 `conformity/tradition`

### 7.4 双人结果页建议文案结构

不要只写“你们都看重 X / 你们冲突在 Y”，建议固定成：

1. 你们天然同频的地方
2. 你们排序不同但未必冲突的地方
3. 你们最需要提前说开的价值议题
4. 推荐聊的现实问题

例如：

- 同频：你们都看重稳定投入，不喜欢关系里反复试探。
- 排序不同：你更重家庭秩序，TA 更重个人空间，这不是三观不合，是生活边界分配不同。
- 需提前说开：居住安排、亲密节奏、节假日家庭责任。

## 8. 结果卡和数据结构建议

### 8.1 后端结果结构

```json
{
  "schema_version": "v2",
  "top_lots": [],
  "schwartz_values": {
    "self_direction": 0.18,
    "stimulation": 0.06,
    "hedonism": 0.08,
    "achievement": 0.12,
    "power": 0.05,
    "security": 0.22,
    "conformity": 0.09,
    "tradition": 0.07,
    "benevolence": 0.21,
    "universalism": 0.10
  },
  "higher_order_values": {
    "openness_to_change": 0.28,
    "conservation": 0.38,
    "self_enhancement": 0.17,
    "self_transcendence": 0.31
  },
  "internal_tensions": [
    {
      "left": "self_direction",
      "right": "security",
      "intensity": 0.11
    }
  ]
}
```

### 8.2 前端结果卡

建议增加三个固定模块：

- `价值地图`
  显示 4 大方向强弱。
- `你的排序逻辑`
  用 2-3 句解释为什么会重注这些拍品。
- `关系里的真实影响`
  翻译成沟通、边界、承诺、现实安排上的偏好。

## 9. 迁移策略

### Phase 1：兼容上线

- 保留现有 UI 框架
- 新增 `schema_version = v2`
- 拍品仍可先沿用现有文案，但重做 value 映射
- 单人结果页先切到“标准价值 + 四方向”

### Phase 2：玩法修正

- 把“保留/放弃”改成真实加价
- 增加撤码和补码机制
- 双人分析切到价值向量距离

### Phase 3：完整理论化

- 拍品池扩充到 16+
- 引入相邻价值和对冲价值的结构提示
- A/B test 旧版标签解读 vs 新版价值地图解读

## 10. 对当前代码的直接修改建议

### 10.1 `assessment/values_auction_lots.py`

建议：

- 把 `HIDDEN_VALUE_KEYS` 替换成 Schwartz 10 value keys
- 每个 lot 改成 `primary_value + secondary_value`
- 不再使用 `love/family/companionship/meaning` 作为底层 key

### 10.2 `assessment/values_auction_service.py`

建议：

- `calculate_hidden_values()` 改为标准价值计算
- 新增 `calculate_higher_order_values()`
- 新增 `calculate_internal_tensions()`
- `classify_value_type_from_hidden()` 改成多轴解释，不再只给单标签

### 10.3 `frontend/her-app/components/values-auction/SequentialBiddingCard.tsx`

建议：

- 从 keep/discard 模式改成分步加价模式
- 保留沉浸式动画，不动整体视觉方向
- 新增“补码”“撤码”“改投”交互

### 10.4 `ValuesMatchAnalysisCard`

建议：

- 新增“价值方向对照”
- 新增“差异但可协商”模块
- 冲突文案从拍品层，提升到价值结构层

## 11. 最小可行版本

如果想低风险快速试，先做这个 MVP：

1. 不改 UI，只改后台映射。
2. 先把 9 个现有拍品重新映射到 Schwartz 10 价值。
3. 单人结果页增加四方向分布。
4. 双人结果页增加“同向/可协商/结构冲突”三段式分析。

这样改动最小，但结果质量会先明显提升。

## 12. 一句话结论

v1 的重点是“好玩”，v2 应该变成“好玩 + 测得准 + 能解释为什么合不合”。

真正该升级的不是动画，而是底层价值结构。
