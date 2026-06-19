"""字段对比分析：资料表 vs 偏好表 vs 搜索指令"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 一、三个存储位置的字段对比
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
┌─────────────────────────────────────────────────────────┐
│  profile_part（资料表 - profiles 表）                   │
│                                                         │
│  存储位置：MySQL profiles 表                             │
│  特点：需要用户确认后生效                                 │
│  用途：用户真实身份信息                                   │
└─────────────────────────────────────────────────────────┘

字段列表：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 基础信息：
- name（姓名）
- gender（性别）
- age（年龄）
- city（所在城市）
- district（区县）
- height（身高）
- education（学历）
- job（职业）
- income_range（收入范围）

✅ 婚姻家庭：
- marital_status（婚姻状况）
- has_children（是否有孩子）
- children_count（孩子数量）
- children_living_with_self（孩子是否同住）

✅ 生活习惯：
- smoking（抽烟）
- drinking（喝酒）
- relationship_goal（恋爱目标）

✅ 映射字段（self_ 前缀）：
- self_gender → gender
- self_age → age
- self_city → city
- self_height → height
- self_education → education
- self_job → job
- self_marital_status → marital_status
- self_has_children → has_children
- self_smoking → smoking
- self_drinking → drinking
- self_relationship_goal → relationship_goal

❌ 不存储的字段：
- 偏好数据（那是 persona）
- 搜索条件（那是 search_part）
- 内部状态字段


┌─────────────────────────────────────────────────────────┐
│  persona_part（偏好表 - persona-memory-sync 服务）      │
│                                                         │
│  存储位置：persona-memory-sync 服务（可能是 MySQL/Elasticsearch）│
│  特点：直接写入，不需要确认                               │
│  用途：长期择偶偏好                                       │
└─────────────────────────────────────────────────────────┘

字段列表：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 目标条件（target_ 前缀）：
- target_gender（目标性别）
- target_age_min（年龄下限）
- target_age_max（年龄上限）
- target_cities（目标城市列表）
- target_height_min（身高下限）
- target_height_max（身高上限）
- target_education_min（学历下限）
- target_income_min_wan（收入下限）
- target_income_max_wan（收入上限）
- target_marital_statuses（目标婚姻状态）
- target_accept_partner_children（是否接受对方有孩子）
- target_accept_long_distance（是否接受异地）
- target_want_children（是否想要孩子）
- target_marriage_timeline（结婚时间规划）

✅ 必须条件：
- must_have_tags（必须有标签）
- must_not_have_tags（必须没有标签）
- preferred_traits（偏好特质）
- disliked_traits（讨厌特质）

✅ 个人特质（self_ 前缀，但不映射到 profile）：
- self_life_rhythm（生活节奏）
- self_work_pattern（工作模式）
- self_expression_style（表达风格）
- self_smoking（抽烟习惯）
- self_drinking（喝酒习惯）
- self_relationship_goal（恋爱目标）

✅ 白名单补充：
- display_name（昵称）

✅ 兜底字段（任意非标准字段）：
- "喜欢吃辣的人"
- "喜欢养猫的人"
- "喜欢看电影的人"
- ...（用户说的任意偏好）


┌─────────────────────────────────────────────────────────┐
│  search_part（搜索指令 - working_criteria）             │
│                                                         │
│  存储位置：session.state["working_criteria"]            │
│  特点：立即生效，用于当前搜索                             │
│  用途：当前搜索条件                                       │
└─────────────────────────────────────────────────────────┘

字段列表：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ 搜索条件（黑名单排除）：
- cities（城市列表）
- districts（区县列表）
- age_min（年龄下限）
- age_max（年龄上限）
- height_min（身高下限）
- height_max（身高上限）
- education_min（学历下限）
- income_min（收入下限）
- income_max（收入上限）
- marital_statuses（婚姻状态列表）
- relationship_goals（恋爱目标列表）
- housing_statuses（住房状态）
- car_statuses（车状态）
- must_have（必须有标签）
- must_not_have（必须没有标签）
- prefer（偏好标签）
- personality_traits（性格特质偏好）
- limit（返回数量）
- offset（分页偏移）

❌ 黑名单字段（不参与搜索）：
- session_id、requester_id、profile_id、user_key
- created_at、updated_at、working_criteria
- personality_trace、user_personality_traits
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 二、搜索指令存在的必要性分析
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
问题：为什么需要 search_part？不能直接用 persona_part 的偏好搜索吗？

答案：需要！因为用户意图有三种场景：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

场景1：立即搜索，不记长期偏好
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

用户说："帮我搜一下北京的，看看有什么人"

意图分析：
- 用户只是想"看看"，不是长期偏好
- 这次搜索北京，下次可能搜上海
- 不需要记到 persona_part

分流逻辑：
- cities: ["北京"] → search_part（立即搜索）
- 不写入 persona_part（不记长期偏好）

大白话类比：
- 你去餐厅："随便看看有什么菜" → 服务员不记偏好，只帮你找菜


场景2：长期偏好，但不立即搜索
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

用户说："我比较喜欢北京的人，以后优先推荐北京的"

意图分析：
- 用户在说长期偏好，不是立即搜索
- 记录下来，下次推荐时优先北京
- 不需要立即搜索

分流逻辑：
- target_cities: ["北京"] → persona_part（长期偏好）
- 不写入 search_part（不立即搜索）

大白话类比：
- 你去餐厅："我比较喜欢吃辣的" → 服务员记偏好，但不立即下单


场景3：既要长期偏好，又要立即搜索
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

用户说："我想找北京的，以后也优先推荐北京的"

意图分析：
- 用户既想立即搜索，又想长期偏好
- 两个字段都写入

分流逻辑：
- target_cities: ["北京"] → persona_part（长期偏好）
- cities: ["北京"] → search_part（立即搜索）

大白话类比：
- 你去餐厅："我喜欢辣的，给我来一份辣的菜" → 服务员既记偏好又立即下单
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 三、字段对比表：三个存储位置的区别
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
┌───────────────────────────────────────────────────────────────┐
│  字段对比表：资料表 vs 偏好表 vs 搜索指令                       │
├─────────────┬─────────────┬─────────────┬─────────────────────┤
│ 字段类型    │ profile_part│ persona_part│ search_part         │
├─────────────┼─────────────┼─────────────┼─────────────────────┤
│ age         │ ✅ 本人年龄 │ ❌           │ ✅ 搜索年龄范围     │
│ city        │ ✅ 本人城市 │ ❌           │ ❌（用 cities）     │
│ cities      │ ❌          │ ❌           │ ✅ 搜索城市列表     │
│ target_age  │ ❌          │ ✅ 目标年龄  │ ❌                  │
│ target_city │ ❌          │ ✅ 目标城市  │ ❌                  │
│ smoking     │ ✅ 本人抽烟 │ ✅ 抽烟习惯  │ ❌                  │
│ marital     │ ✅ 本人婚姻 │ ✅ 目标婚姻  │ ✅ 搜索婚姻状态     │
│ personality │ ❌          │ ✅ 性格偏好  │ ✅ 性格搜索条件     │
└─────────────┴─────────────┴─────────────┴─────────────────────┘

关键区别：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 字段名前缀：
   - self_* → 本人信息（profile 或 persona）
   - target_* → 目标偏好（persona）
   - 无前缀 → 搜索条件（search）

2. 数据类型：
   - profile_part：单个值（age: 28）
   - persona_part：单个值或列表（target_age_min: 26）
   - search_part：列表或范围（age_min: 26, age_max: 30）

3. 存储位置：
   - profile_part：MySQL profiles 表
   - persona_part：persona-memory-sync 服务
   - search_part：session.state（临时状态）

4. 生效方式：
   - profile_part：需要用户确认
   - persona_part：直接写入
   - search_part：立即执行
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 四、搜索指令存在的必要性：三个理由
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
理由1：支持临时搜索（不记长期偏好）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

场景：
- 用户说"帮我搜一下上海的，看看有什么人"
- 用户只是想"看看"，不是长期偏好上海
- 下次可能搜北京、广州

解决方案：
- search_part 存储临时搜索条件
- 不写入 persona_part（不记长期偏好）
- 下次搜索不受影响

大白话类比：
- 你去餐厅："随便看看有什么菜" → 服务员不记偏好


理由2：支持动态调整（覆盖长期偏好）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

场景：
- 用户长期偏好北京（persona_part: target_cities: ["北京"]）
- 但这次想搜上海（search_part: cities: ["上海"]）
- 搜索时优先用 search_part（当前意图），而非 persona_part（长期偏好）

解决方案：
- search_part 优先级高于 persona_part
- 用户动态调整时，当前意图优先
- 下次搜索恢复长期偏好

大白话类比：
- 你长期喜欢吃辣（记在偏好篮）
- 但今天想吃清淡（点菜篮：清淡）
- 服务员优先做清淡（当前意图），下次恢复辣（长期偏好）


理由3：支持渐进式搜索（累积条件）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

场景：
- 用户第一次说"帮我搜北京的" → working_criteria: {cities: ["北京"]}
- 用户第二次说"26-30岁" → working_criteria: {cities: ["北京"], age_min: 26, age_max: 30}
- 用户第三次说"身高175以上" → working_criteria: {cities: ["北京"], age_min: 26, age_max: 30, height_min: 175}

解决方案：
- search_part 通过 merge_working_criteria 累积
- 支持用户逐步调整条件
- persona_part 是静态偏好，不支持累积

大白话类比：
- 你去餐厅：先说"辣的"，再说"不要香菜"，再说"少油"
- 服务员累积调整：辣 + 不要香菜 + 少油
- 偏好篮是静态的（长期喜欢辣），点菜篮是动态的（累积调整）
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 五、总结：三个存储位置的职责边界
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
┌───────────────────────────────────────────────────────────────┐
│  职责边界清晰化：三个存储位置各司其职                           │
├─────────────┬─────────────┬─────────────┬─────────────────────┤
│ 存储位置    │ profile_part│ persona_part│ search_part         │
├─────────────┼─────────────┼─────────────┼─────────────────────┤
│ 职责        │ 真实身份    │ 长期偏好    │ 当前搜索             │
│ 特点        │ 需要确认    │ 直接写入    │ 立即执行             │
│ 持久性      │ 永久        │ 长期        │ 临时（会话级）       │
│ 优先级      │ 最高        │ 中          │ 最高（当前意图）     │
│ 支持累积    │ ❌          │ ❌          │ ✅                   │
└─────────────┴─────────────┴─────────────┴─────────────────────┘

大白话总结：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

profile_part（身份证）：
- 存的是"真实信息"（姓名、年龄、地址）
- 必须核实是真的（不能随便改）

persona_part（日记本）：
- 存的是"长期偏好"（喜欢什么类型的人）
- 直接记录，不核实真实性

search_part（购物清单）：
- 存的是"当前要买的东西"（这次要搜什么）
- 立即去买，买完就扔（临时状态）

三者关系：
- 身份证（profile）：你是谁
- 日记本（persona）：你喜欢什么
- 购物清单（search）：你现在要买什么

搜索时的优先级：
- 购物清单（search）优先于日记本（persona）
- 当前意图优先于长期偏好
"""

print(__doc__)