# Persona Memory Sync 方案设计

## 1. 背景

当前系统已经有相亲候选库，核心数据在 MySQL 的 `profiles` 和 `profile_photos` 两张表里。

现在新增的需求不是“再做一次筛人”，而是给红娘系统增加一层长期记忆能力：

- 只要在聊天里越来越了解用户本人
- 只要逐渐确认用户喜欢什么类型的人
- 这些理解就应该沉淀到数据库
- 并且其中适合公开展示的部分，还要同步到 `profiles` 表，让别人也能看到这份画像

这个能力本质上是：

`内部主画像持续演化 + 对外公开资料受控同步`

## 2. 目标

### 2.1 业务目标

让系统具备以下能力：

- 自动记住用户的基础资料
- 自动记住用户的择偶硬条件
- 自动记住用户的长期偏好、雷点和风格倾向
- 后续筛人时默认复用，不需要每次重新输入
- 将适合公开展示的画像内容同步到 `profiles` 表，作为用户对外资料卡的一部分

### 2.2 系统目标

设计一套稳定、可追溯、可回滚的画像同步机制，避免：

- 把推断当成事实直接覆盖
- 把内部判断原样暴露给外部
- 后续修正时找不到来源
- `profiles` 被写脏、写乱

## 3. 核心原则

### 3.1 三层模型

系统中的“你是谁”不能只存在 `profiles`。

推荐采用三层结构：

1. `user_personas`
   这是后台主画像，作为用户长期画像的唯一真源。
2. `user_persona_observations`
   这是观察和增量证据日志，记录每次聊天中新确认或新推断出的内容。
3. `profiles`
   这是公开展示层，只同步适合外显的内容。

最核心的原则：

`user_personas` 是真源，`profiles` 是投影，不允许反过来让 `profiles` 成为主画像的来源。

### 3.2 明确表达和推断分开

不能把“用户明确说过的”和“系统推断出来的”混在一起直接入主表。

必须区分三种来源：

1. `explicit`
   用户明确说过。
2. `strong_inference`
   多轮对话中反复体现，系统高置信判断。
3. `weak_inference`
   轻微倾向，证据不足。

### 3.3 内部信息和公开信息分开

有些内容适合进入后台画像，但不适合原样公开展示。

例如：

- 后台可记录：`must_not_have = 冷暴力, 暧昧不清, 绿茶, 拜金`
- 前台不建议原样展示
- 前台应转译为更自然的公开文案，例如：
  - 希望关系清晰、真诚直接
  - 重视沟通和价值观一致
  - 不喜欢长期消耗型关系

## 4. 新 Skill 的定位

建议新增一个独立 skill，名称建议：

`persona-memory-sync`

### 4.1 职责

这个 skill 负责：

- 从对话中识别用户画像信号
- 判断是明确表达还是推断
- 记录 observation
- 合并到主画像
- 将适合公开的内容同步到 `profiles`

### 4.2 不负责的事情

这个 skill 不负责：

- 候选人搜索和排序
- 推荐逻辑
- 照片管理
- 聊天回复风格控制

### 4.3 与 `partner-search` 的关系

推荐职责拆分如下：

- `persona-memory-sync`：负责记住用户是谁、喜欢谁
- `partner-search`：负责基于画像筛人

后续在实际工作流里，`partner-search` 可以优先调用 `persona-memory-sync`，再执行搜索。

## 5. 数据模型

## 5.1 总体结构

新增两张表：

- `user_personas`
- `user_persona_observations`

保留现有：

- `profiles`
- `profile_photos`

## 5.2 user_personas

用途：

- 存储用户当前可直接用于筛人的主画像
- 存储用户的结构化条件、偏好标签和公开摘要

建议字段如下。

### 标识字段

- `id`
- `user_key`
  - 业务唯一标识，例如 `sunmuchao`
- `display_name`
  - 用户展示名，可选
- `profile_id`
  - 对应 `profiles.id`
  - 用来把后台画像和前台公开资料绑定起来

### 用户本人基础信息

- `self_gender`
- `self_age`
- `self_city`
- `self_district`
- `self_height`
- `self_education`
- `self_income_wan`
- `self_job`
- `self_marital_status`
- `self_has_children`
- `self_smoking`
- `self_drinking`
- `self_relationship_goal`

### 择偶硬条件

- `target_gender`
- `target_age_min`
- `target_age_max`
- `target_cities`
- `target_height_min`
- `target_height_max`
- `target_education_min`
- `target_income_min_wan`
- `target_income_max_wan`
- `target_marital_statuses`
- `target_accept_partner_children`
- `target_accept_long_distance`
- `target_want_children`
- `target_marriage_timeline`

### 偏好与雷点

- `must_have_tags`
  - 例如：`情绪稳定,愿意沟通,消费观正常`
- `must_not_have_tags`
  - 例如：`抽烟,冷暴力,暧昧不清,绿茶,拜金`
- `preferred_traits`
  - 用于存偏好的软标签
- `disliked_traits`
  - 用于存反感的软标签

### 总结字段

- `persona_summary`
  - 后台内部版本，对用户的整体理解摘要
- `preference_summary`
  - 后台内部版本，对择偶倾向的摘要
- `public_profile_summary`
  - 面向 `profiles` 的公开版总结
- `public_preference_summary`
  - 面向 `profiles` 的公开版择偶偏好总结

### 元数据

- `last_confirmed_at`
- `last_inferred_at`
- `created_at`
- `updated_at`

## 5.3 user_persona_observations

用途：

- 记录每次画像更新的证据
- 给回滚、审计、调试提供依据

建议字段如下：

- `id`
- `user_key`
- `persona_id`
- `field_name`
- `field_value`
- `source_type`
  - `explicit` / `strong_inference` / `weak_inference`
- `confidence_score`
  - 0 到 100
- `evidence_text`
  - 证据摘要，不必存原始长对话
- `conversation_ref`
  - 可选，对应会话或时间戳
- `action_type`
  - `insert` / `update` / `skip`
- `applied_to_persona`
  - 是否写入 `user_personas`
- `applied_to_profile`
  - 是否同步到 `profiles`
- `created_at`

## 5.4 profiles

`profiles` 是现有公开资料表，不建议新增过多字段。

优先复用现有字段，将 `user_personas` 中适合公开展示的部分映射进来。

需要同步的主要是：

- 基础信息
- 择偶结构条件
- 公开文案字段

## 6. 字段同步规则

## 6.1 user_personas -> profiles 的映射

建议映射如下。

### 用户本人信息映射

- `self_gender -> profiles.gender`
- `self_age -> profiles.age`
- `self_city -> profiles.city`
- `self_district -> profiles.district`
- `self_height -> profiles.height`
- `self_education -> profiles.education`
- `self_job -> profiles.job`
- `self_marital_status -> profiles.marital_status`
- `self_has_children -> profiles.has_children`
- `self_smoking -> profiles.smoking`
- `self_drinking -> profiles.drinking`
- `self_relationship_goal -> profiles.relationship_goal`

### 收入映射

- `self_income_wan` 不直接进单值字段
- 需要转换成 `profiles.income_range`
- 例如：
  - 40 -> `36-45万/年`
  - 25 -> `20-30万/年`

### 择偶要求映射

- `target_age_min -> profiles.preferred_age_min`
- `target_age_max -> profiles.preferred_age_max`
- `target_cities -> profiles.preferred_cities`
- `target_height_min -> profiles.preferred_height_min`
- `target_height_max -> profiles.preferred_height_max`
- `target_education_min -> profiles.preferred_education_min`
- `target_income_min_wan -> profiles.preferred_income_min_wan`
- `target_income_max_wan -> profiles.preferred_income_max_wan`

### 公开文案映射

建议将公开版偏好映射到：

- `public_profile_summary -> profiles.personality`
- `public_preference_summary -> profiles.values`
- 必要时可把补充说明写到 `profiles.notes`

如果后续需要更细粒度表达，也可以按文案生成策略拆分到：

- `personality`
- `values`
- `lifestyle`
- `notes`

## 6.2 不建议直接同步的内容

以下内容不建议原样进入 `profiles`：

- `weak_inference`
- 原始负面标签原句
- 系统内部判断理由
- 风险标签
- 推断置信度
- 观察证据文本

## 7. 合并策略

## 7.1 总体规则

系统每次识别到新的画像信号后，先落 observation，再决定是否合并进主画像。

合并顺序：

1. 先记录 observation
2. 判断 source 类型
3. 应用字段级覆盖规则
4. 更新 `user_personas`
5. 生成公开文案
6. 同步到 `profiles`

## 7.2 字段覆盖优先级

优先级从高到低：

1. 最新的 `explicit`
2. 更高置信的 `strong_inference`
3. 较弱的 `strong_inference`
4. `weak_inference`

### 具体规则

- `explicit` 可以覆盖旧的 `explicit`
  - 例如用户后来把年龄、城市、目标改了，允许直接更新
- `strong_inference` 不允许覆盖已有的明确结构化字段
  - 例如用户明确说过 `无锡`，系统推断他可能接受苏州，这种不能改 `self_city`
- `weak_inference` 只进 observation，不进主画像
- 标签类字段允许累积，但必须去重

## 7.3 硬字段和软字段分开处理

### 硬字段

例如：

- 年龄
- 城市
- 身高
- 学历
- 婚况
- 是否接受异地
- 是否接受对方有孩子

规则：

- 只有 `explicit` 才能直接更新
- `inference` 只能提出候选，不直接覆盖

### 软字段

例如：

- 喜欢情绪稳定
- 偏好沟通顺畅
- 讨厌暧昧拉扯
- 偏务实

规则：

- `strong_inference` 可写入主画像标签区
- `weak_inference` 只记 observation

## 8. 公开文案生成策略

## 8.1 为什么要生成公开文案

后台画像常常是结构化和原始表达混合的，不适合直接给别人看。

例如：

- 后台：`must_not_have = 绿茶,拜金,暧昧不清`
- 前台不应该直接显示成这种句子

需要做“转译”。

## 8.2 转译原则

公开文案应该：

- 自然
- 克制
- 可读
- 不攻击人
- 保留真实偏好

## 8.3 示例

### 后台原始画像

- 重视：情绪稳定、愿意沟通、消费观正常
- 雷点：冷暴力、暧昧不清、拜金

### 对外公开版

- 重视情绪稳定、沟通顺畅和消费观一致
- 希望关系边界清晰，认真推进，不喜欢长期拉扯和价值观冲突

## 8.4 推荐公开字段写法

### `profiles.personality`

主要描述“你本人是什么样的人”

例如：

- 稳定务实，结婚意愿明确，偏好简单真诚的相处方式

### `profiles.values`

主要描述“你看重什么”

例如：

- 看重情绪稳定、沟通顺畅和消费观正常，希望双方关系清晰、认真推进

### `profiles.notes`

补充不适合放在结构字段里的说明

例如：

- 不接受长期暧昧和高消耗型相处模式

## 9. 触发时机

这个 skill 应在以下场景自动触发。

### 9.1 用户明确补充自身资料

例如：

- 我 28 岁
- 我在无锡
- 我是本科
- 我结婚导向

处理：

- 记 `explicit`
- 更新 `user_personas`
- 同步到 `profiles`

### 9.2 用户明确补充择偶要求

例如：

- 想找无锡本地
- 不接受异地
- 不接受有孩子
- 本科及以上

处理：

- 记 `explicit`
- 更新主画像
- 同步 `profiles` 的择偶字段

### 9.3 用户对候选人连续反馈

例如：

- 这类太会喝酒了，不行
- 太暧昧了，不喜欢
- 这个消费观不太对

处理：

- 初次反馈记 observation
- 多次同向反馈后提升到 `strong_inference`
- 更新主画像标签
- 仅在适合公开时更新公开文案

### 9.4 系统高置信总结

例如：

- 多轮对话显示用户明显偏好“沟通清晰、关系明确、同城稳定推进”

处理：

- 记 `strong_inference`
- 更新 `user_personas`
- 生成更自然的公开偏好文案

## 10. 同步边界

## 10.1 建议默认策略

建议默认采用：

`后台自动演化，前台受控同步`

即：

- `user_personas` 自动更新
- `profiles` 只同步明确表达或适合公开的高置信内容

## 10.2 保守模式

如果更保守，可以采用：

- `explicit` 才允许进 `profiles`
- `strong_inference` 只进 `user_personas`

优点：

- 最安全
- 不容易写错公开资料

缺点：

- `profiles` 更新速度会慢一些

## 10.3 激进模式

如果更强调自动化，可以采用：

- `explicit` 和高置信 `strong_inference` 都允许进 `profiles`

优点：

- 公开资料更快变得像用户本人

缺点：

- 更容易把推断写成事实

## 10.4 推荐模式

推荐采用折中策略：

- 结构化硬字段：只接受 `explicit`
- 偏好总结文案：允许 `strong_inference`
- 弱推断：只记 observation

## 11. 典型案例

## 11.1 当前用户案例

以当前对话为例，已确认信息如下。

### 明确表达

- 男
- 28 岁
- 无锡
- 178
- 211 本科
- 40w
- 未婚
- 无孩子
- 不抽烟
- 少喝酒
- 结婚导向

### 明确择偶条件

- 找女生
- 24-30 岁
- 无锡
- 160+
- 本科及以上
- 未婚
- 不接受有孩子
- 不接受异地

### 明确必须有

- 情绪稳定
- 愿意沟通
- 消费观正常

### 明确不能有

- 抽烟
- 冷暴力
- 暧昧不清
- 绿茶
- 拜金

### 可以形成的高置信推断

- 用户明显偏好同城稳定推进关系
- 用户较重视关系边界清晰
- 用户偏务实，不喜欢高消耗、含糊型相处

## 11.2 进入 user_personas 的内容

结构化字段直接进入主画像。

标签类建议写入：

- `must_have_tags = 情绪稳定,愿意沟通,消费观正常`
- `must_not_have_tags = 抽烟,冷暴力,暧昧不清,绿茶,拜金`

内部总结示例：

- `persona_summary`
  - 无锡本地，结婚导向，偏务实，倾向稳定清晰的长期关系
- `preference_summary`
  - 看重情绪稳定、沟通和消费观，不接受异地、有孩子或长期暧昧拉扯型关系

## 11.3 同步到 profiles 的建议文案

不建议把原始负面词直接公开。

建议公开版：

- `personality`
  - 无锡本地，生活方式稳定，认真以结婚为导向
- `values`
  - 看重情绪稳定、沟通顺畅和消费观一致，希望关系清晰、认真推进
- `notes`
  - 更适合同城稳定发展的关系，不喜欢长期暧昧和高消耗型相处

## 12. 技术实现建议

## 12.1 Skill 目录结构

建议新增：

```text
local-skills/
  persona-memory-sync/
    SKILL.md
    agents/
      openai.yaml
    scripts/
      ensure_persona_tables.py
      upsert_persona_memory.py
      sync_persona_to_profile.py
    references/
      schema.md
      merge-rules.md
      public-rendering.md
```

## 12.2 脚本职责

### `ensure_persona_tables.py`

负责：

- 创建 `user_personas`
- 创建 `user_persona_observations`
- 建必要索引

### `upsert_persona_memory.py`

负责：

- 接收结构化输入或提取后的画像片段
- 先写 observation
- 再合并入 `user_personas`

### `sync_persona_to_profile.py`

负责：

- 读取 `user_personas`
- 生成公开文案
- 将公开字段同步到 `profiles`

## 12.3 推荐工作流

推荐工作流如下：

1. 从对话中抽取画像信号
2. 形成标准化 patch
3. 调用 `upsert_persona_memory.py`
4. 由脚本记录 observation
5. 合并进 `user_personas`
6. 调用 `sync_persona_to_profile.py`
7. 更新 `profiles`

## 13. SQL 设计建议

以下为建议方向，不要求第一版完全一致。

### 13.1 user_personas

```sql
CREATE TABLE user_personas (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_key VARCHAR(64) NOT NULL UNIQUE,
  display_name VARCHAR(64) DEFAULT NULL,
  profile_id BIGINT DEFAULT NULL,

  self_gender VARCHAR(8) DEFAULT NULL,
  self_age INT DEFAULT NULL,
  self_city VARCHAR(64) DEFAULT NULL,
  self_district VARCHAR(64) DEFAULT NULL,
  self_height INT DEFAULT NULL,
  self_education VARCHAR(32) DEFAULT NULL,
  self_income_wan INT DEFAULT NULL,
  self_job VARCHAR(64) DEFAULT NULL,
  self_marital_status VARCHAR(32) DEFAULT NULL,
  self_has_children TINYINT(1) DEFAULT NULL,
  self_smoking VARCHAR(16) DEFAULT NULL,
  self_drinking VARCHAR(16) DEFAULT NULL,
  self_relationship_goal VARCHAR(32) DEFAULT NULL,

  target_gender VARCHAR(8) DEFAULT NULL,
  target_age_min INT DEFAULT NULL,
  target_age_max INT DEFAULT NULL,
  target_cities TEXT,
  target_height_min INT DEFAULT NULL,
  target_height_max INT DEFAULT NULL,
  target_education_min VARCHAR(32) DEFAULT NULL,
  target_income_min_wan INT DEFAULT NULL,
  target_income_max_wan INT DEFAULT NULL,
  target_marital_statuses TEXT,
  target_accept_partner_children VARCHAR(16) DEFAULT NULL,
  target_accept_long_distance VARCHAR(16) DEFAULT NULL,
  target_want_children VARCHAR(16) DEFAULT NULL,
  target_marriage_timeline VARCHAR(32) DEFAULT NULL,

  must_have_tags TEXT,
  must_not_have_tags TEXT,
  preferred_traits TEXT,
  disliked_traits TEXT,

  persona_summary TEXT,
  preference_summary TEXT,
  public_profile_summary TEXT,
  public_preference_summary TEXT,

  last_confirmed_at DATETIME DEFAULT NULL,
  last_inferred_at DATETIME DEFAULT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 13.2 user_persona_observations

```sql
CREATE TABLE user_persona_observations (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  user_key VARCHAR(64) NOT NULL,
  persona_id BIGINT DEFAULT NULL,
  field_name VARCHAR(64) NOT NULL,
  field_value TEXT,
  source_type ENUM('explicit','strong_inference','weak_inference') NOT NULL,
  confidence_score INT DEFAULT NULL,
  evidence_text TEXT,
  conversation_ref VARCHAR(128) DEFAULT NULL,
  action_type ENUM('insert','update','skip') NOT NULL DEFAULT 'insert',
  applied_to_persona TINYINT(1) NOT NULL DEFAULT 0,
  applied_to_profile TINYINT(1) NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_user_persona_observations_user_key (user_key),
  KEY idx_user_persona_observations_persona_id (persona_id),
  KEY idx_user_persona_observations_field_name (field_name)
) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 14. 风险与防护

## 14.1 风险一：推断过度

表现：

- 系统把一两句情绪化表达当成长期偏好

防护：

- 引入 `weak_inference`
- 没到阈值不进主画像

## 14.2 风险二：公开资料写脏

表现：

- 把后台原始措辞直接同步到 `profiles`

防护：

- 公开字段统一走文案转译
- 不允许原始负面词直接上屏

## 14.3 风险三：覆盖用户明确表达

表现：

- 系统推断把硬字段改掉

防护：

- 结构化硬字段只允许 `explicit` 更新

## 14.4 风险四：后续修正困难

表现：

- 不知道某个字段为什么被改成现在这样

防护：

- 必须有 observation 日志
- 每次更新都记录 `source_type` 和 `evidence_text`

## 15. MVP 版本建议

第一版不需要一步做到最复杂。

建议 MVP 范围如下：

### 第一阶段

- 建 `user_personas`
- 建 `user_persona_observations`
- 支持显式字段写入
- 支持基础字段同步到 `profiles`

### 第二阶段

- 支持 `strong_inference`
- 支持标签累积
- 支持公开文案自动生成

### 第三阶段

- 根据用户对候选人的连续反馈自动修正画像
- 引入阈值和置信度衰减
- 更智能地区分硬条件和软偏好

## 16. 推荐默认决策

如果要快速进入实现，建议默认采用以下策略：

1. `user_personas` 作为唯一真源
2. `profiles` 作为公开投影
3. `explicit` 可进主画像并同步到 `profiles`
4. `strong_inference` 可进主画像，但只允许更新公开文案，不覆盖硬结构字段
5. `weak_inference` 只进 observation
6. 所有更新都留痕

## 17. 最终结论

这套方案的本质不是“多加一张表”，而是建立一套稳定的画像演化机制。

正确的系统关系应该是：

`对话 -> observation -> user_personas -> public rendering -> profiles`

这样可以同时满足三件事：

- 系统会越来越懂用户
- 后续筛人不需要反复重输条件
- 别人看到的公开资料也会越来越像用户本人

并且整个过程可追溯、可修正、可控。
