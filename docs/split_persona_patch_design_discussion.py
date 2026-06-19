"""分流逻辑详解：split_persona_patch 的设计意图和潜在问题"""

# 核心数据结构（从 profile_write_guard.py 和 collected_profile.py）

# 1. 可写入的 profile 字段（用户资料）
_WRITABLE_PROFILE_COLUMNS = frozenset({
    "name", "gender", "age", "city", "height", "education", "job",
    "marital_status", "has_children", "children_count", "smoking", "drinking",
    "relationship_goal", ...
})

# 2. self_ 字段到 profile 字段的映射
_PERSONA_SELF_TO_PROFILE = {
    "self_gender": "gender",
    "self_age": "age",
    "self_city": "city",
    "self_height": "height",
    "self_education": "education",
    ...
}

# 3. persona 白名单（择偶偏好）
COLLECTED_PERSONA_FIELDS = frozenset({
    "display_name", "self_smoking", "self_drinking",
    "target_gender", "target_age_min", "target_age_max",
    "target_cities", "target_height_min", "target_height_max",
    "must_have_tags", "must_not_have_tags", ...
})

# 4. 搜索条件黑名单（不参与搜索）
_EXCLUDED_SEARCH_KEYS = frozenset({
    "session_id", "requester_id", "profile_id", "user_key",
    "created_at", "updated_at", "working_criteria",
    "limit", "offset", ...
})


# 分流逻辑的6个判断分支（优先级从高到低）

"""
第1层：特殊标识符（优先级最高）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if key in {"profile_id", "user_key"}:
    persona_part[key] = value
    continue

设计意图：
- profile_id/user_key 是数据归属标识符
- 必须写入 persona 表，用于关联用户数据
- 不参与搜索，不修改 profile

示例：
- user_key: "12345" → persona_part


第2层：可直接写入的 profile 字段
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if key in _WRITABLE_PROFILE_COLUMNS:
    profile_part[key] = value
    continue

设计意图：
- 这些字段可以直接写入 profiles 表
- 需要用户确认后生效
- 涉及真实身份信息

示例：
- age: 28 → profile_part
- city: "北京" → profile_part


第3层：self_ 字段映射转换
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if key in _PERSONA_SELF_TO_PROFILE:
    profile_part[_PERSONA_SELF_TO_PROFILE[key]] = value
    continue

设计意图：
- 用户说"我28岁" → Agent 收到 self_age
- 需要转换成 age（profiles 表字段名）
- 同样需要用户确认

示例：
- self_age: 28 → profile_part["age"] = 28
- self_city: "北京" → profile_part["city"] = "北京"


第4层：搜索条件（黑名单排除）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if is_search_criteria_key(key):
    search_part[key] = value
    continue

设计意图：
- Agent Native 设计：从白名单改为黑名单
- 除了明确排除的字段，其他都允许参与搜索
- 支持灵活的搜索条件透传

示例：
- cities: ["北京"] → search_part
- age_min: 26 → search_part
- personality_traits: ["内向"] → search_part


第5层：persona 白名单或特殊前缀
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if key in COLLECTED_PERSONA_FIELDS or key.startswith("target_") or key.startswith("self_"):
    persona_part[key] = value
    continue

设计意图：
- target_ 前缀：择偶偏好（长期记忆）
- self_ 前缀：个人特质（长期记忆）
- COLLECTED_PERSONA_FIELDS：白名单补充

示例：
- target_age_min: 26 → persona_part
- self_life_rhythm: "早睡早起" → persona_part
- preferred_traits: ["温和"] → persona_part


第6层：兜底逻辑（所有其他字段）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
persona_part[key] = value

设计意图：
- 未被前述规则拦截的字段都进入 persona_part
- 支持非标准字段的长期记忆
- Agent Native：允许任意字段沉淀

示例：
- "喜欢养猫的人" → persona_part（非标准字段）
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 分流逻辑的核心设计理念
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
核心设计理念：三层分离架构
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

┌─────────────────────────────────────────────────────────┐
│  profile_part（用户资料层）                              │
│                                                         │
│  ✅ 特征：                                              │
│  - 涉及真实身份信息                                      │
│  - 需要用户确认后生效                                    │
│  - 写入 profiles 表                                     │
│                                                         │
│  ❌ 不能做的事：                                         │
│  - 直接写入（必须有确认流程）                            │
│  - 包含偏好数据（那是 persona）                          │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  persona_part（偏好画像层）                              │
│                                                         │
│  ✅ 特征：                                              │
│  - 主观偏好，不需要核对真实性                            │
│  - 直接写入长期记忆                                      │
│  - 写入 persona-memory-sync 服务                        │
│                                                         │
│  ✅ 兜底逻辑：                                           │
│  - 所有未被前述规则拦截的字段都到这里                    │
│  - 支持非标准字段的沉淀                                  │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  search_part（搜索条件层）                               │
│                                                         │
│  ✅ 特征：                                              │
│  - 用于当前搜索                                          │
│  - 合并到 working_criteria                              │
│  - 黑名单排除设计（Agent Native）                        │
│                                                         │
│  ✅ 灵活性：                                             │
│  - 任意非黑名单字段都可透传                              │
│  - 支持动态搜索条件                                      │
└─────────────────────────────────────────────────────────┘
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 分流逻辑的潜在问题和改进方向
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
问题1：优先级冲突
━━━━━━━━━━━━━━━━━

场景：用户传入 self_city: "北京"

分流路径：
- 第3层：self_city → profile_part["city"] = "北京"
- 但第2层：city 也可能直接传入 → profile_part["city"] = "北京"

潜在问题：
- 如果用户同时传入 {self_city: "北京", city: "上海"}
- 结果：profile_part["city"] = "上海"（后者覆盖前者）
- Agent Native：允许这种覆盖，但可能导致混淆

改进方向：
- 在 Agent Prompt 中明确说明字段命名规范
- 工具层不做硬约束，Agent 自主决定


问题2：target_ 前缀和搜索指令都要写入（已纠正）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

场景：用户传入 target_cities: ["北京"]

分流路径：
- 第5层：target_cities → persona_part（长期记忆）
- 第4层：cities 也可能传入 → search_part（当前搜索）

设计意图（不是问题）：
- 用户说"我想找北京的" → 可能同时触发两个动作：
  - 长期偏好：target_cities: ["北京"] → persona_part（长期记忆）
  - 当前搜索：cities: ["北京"] → search_part（立即搜索）
- **两个都写入，既记录偏好又立即执行**

大白话类比（餐厅点菜）：
- 用户说"我喜欢辣的菜" → 服务员：
  - 记在偏好篮：target_spicy: "辣"（长期偏好）
  - 送去厨房：spicy_level: "辣"（当前点菜）
- **既记录偏好，又立即执行，这是合理设计**

改进方向：
- 无需改进，这是设计意图
- Agent 自主判断用户意图，同时写入两个字段


问题3：兜底逻辑过于宽松
━━━━━━━━━━━━━━━━━━━━━━━━━

场景：用户传入任意非标准字段

分流路径：
- 第6层：所有未被拦截的字段 → persona_part

潜在问题：
- 用户说"我喜欢吃辣" → persona_part["喜欢吃辣"] = True
- 但这个字段可能没有明确的语义
- 可能导致 persona 表字段爆炸

改进方向：
- Agent Native：允许这种情况（用户意图沉淀）
- 但需要在 Persona Memory 服务层做字段规范化
- 或者 Agent 自主判断是否值得沉淀


问题4：city vs cities 处理不一致（已修复）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

场景：用户传入 city: "北京"

分流路径：
- split_persona_patch：city → search_part（保持原样）
- merge_working_criteria：city → cities（转换成数组）

问题（已修复）：
- 数据结构不一致
- 旧的 city 字段没被清理
- 导致两个字段同时存在

修复方案（已应用）：
- 在 merge_working_criteria 中：
  1. 如果用户传了 cities，就清理旧的 city
  2. 最终返回前，确保 city 字段被清理

修复验证（已通过）：
- 场景1：用户传 city → 结果：只有 cities
- 场景2：用户改传 cities → 结果：只有新的 cities，旧的 city 已清理
- 场景3：用户同时传两个 → 结果：只有 cities
- 所有测试通过，数据结构一致
"""

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Agent Native 设计理念：为什么这样分流？
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
Agent Native 核心原则：职责分离
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

传统设计：
- 代码硬编码字段映射
- 规则引擎决定分流
- 工具层包含业务逻辑

Agent Native 设计：
- Prompt 表达字段语义
- Agent 自主判断意图
- 工具层只做数据分流（不做业务判断）

示例：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

用户说："我想找北京的"

传统设计：
- 代码硬编码：city → search_part
- 工具层判断：这是搜索意图

Agent Native 设计：
- Agent 自主判断：
  - 用户说"帮我搜北京的" → 传入 cities
  - 用户说"我长期偏好北京" → 传入 target_cities
- 工具层只做分流，不判断意图

优势：
- 更灵活的意图理解
- 支持非标准字段
- Agent 自主决策
"""

print(__doc__)