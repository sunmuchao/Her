# 向量筛选 + Agent自主判断完整落地方案

> **文档版本**: v1.0
> **创建日期**: 2024-06-22
> **问题背景**: 用户反馈"我想找温柔、有上进心的"，系统向量筛选失效，推荐理由缺乏数据支撑

---

## 一、问题背景分析

### 1. 当前问题现象

**用户输入**：
```
"我想找温柔，有上进心的"
```

**系统实际行为**（从日志分析）：
```
【向量筛选开始】candidate_count=50
【向量搜索完成】找到 0 个相似用户
【向量筛选完成】with_data_count=0 without_data_count=50

问题：50个候选人都没有性格向量数据 → 向量筛选完全失效
```

**Agent输出**（推荐理由）：
```
• 于若岚 - ISFP性格天生温柔细腻，安全型依恋相处起来很舒服
• 萧思怡 - ESTJ很有事业心和执行力，医生职业本身就是高成就导向

问题：推荐理由是Agent基于MBTI通用标签推理，缺乏具体数据支撑
```

---

### 2. 根因分析（五问法）

```
问题现象：向量筛选失效，推荐理由缺乏数据支撑
├─ 为什么 1: 50个候选人都没有性格向量数据
│   → 检查：向量库数据缺失严重
├─ 为什么 2: 搜索工具只返回基础信息（profile_id/title/score）
│   → 检查：service_integrations.py返回数据结构不完整
├─ 为什么 3: Agent只能依赖state.current_results中的静态MBTI数据
│   → 检查：缺少完整画像数据加载环节
├─ 为什么 4: 没有从数据库/向量库加载候选人的完整系统信息
│   → 检查：缺少_enrich_candidates_with_full_profiles函数
└─ 为什么 5: 【根本原因】设计理念偏差：向量筛选后没有加载完整画像数据交给Agent判断

根本对策：
1. 向量筛选后加载候选人完整画像（7个维度数据）
2. 把完整信息结构化返回给Agent
3. Agent基于完整数据自主推理推荐理由
```

---

### 3. 架构演进对比

#### 当前架构（有问题）

```
用户输入 → Agent理解意图 → 调用search_partner_candidates
         ↓
    数据库搜索(硬约束) → 向量筛选(失效) → 截断
         ↓
    只返回基础信息(profile_id/title/score)
         ↓
    Agent基于静态MBTI数据推理推荐理由（缺乏数据支撑）
```

#### 目标架构（改进后）

```
用户输入 → Agent理解意图 → 调用search_partner_candidates
         ↓
    【阶段1】数据库搜索(硬约束) → 得到候选池(如50人)
         ↓
    【阶段2】向量筛选(性格相似度) → 得到相似候选人(如20人)
         ↓
    【阶段3】完整画像加载 → 拿到20人的所有系统数据
         ↓
    【阶段4】数据结构化返回 → 把完整信息传给Agent
         ↓
    【阶段5】Agent自主判断 → 基于完整数据推理推荐理由（有数据支撑）
```

---

## 二、数据库表结构梳理

### 核心表（需要加载的）

#### 1. profiles表（基础画像）

**用途**: 基础用户档案信息

**关键字段**:
```sql
id: bigint (主键)
name: varchar(255)  -- 姓名
gender: varchar(32)  -- 性别
age: int  -- 年龄
city: varchar(64)  -- 城市
education: varchar(64)  -- 学历
job: varchar(255)  -- 职业
income_range: varchar(64)  -- 收入范围
marital_status: varchar(64)  -- 婚姻状态
has_children: tinyint(1)  -- 是否有孩子
relationship_goal: varchar(64)  -- 关系目标（dating/marriage）
profile_status: varchar(32)  -- 活跃状态（active/paused/archived）
verified_level: varchar(32)  -- 认证等级
public_personality: text  -- 公开的性格描述
public_values: text  -- 公开的价值观描述
last_active_at: datetime  -- 最近活跃时间
```

---

#### 2. user_personas表（择偶偏好画像）

**用途**: 用户性格数据和择偶偏好

**关键字段**:
```sql
id: bigint (主键)
user_key: varchar(64) (唯一键)  -- 用户标识
profile_id: bigint (外键)  -- 关联profiles表

-- 【核心】性格数据（JSON格式）
self_personality_traits_json: text  -- 包含MBTI/依恋/价值观等

-- 挝偶硬约束
target_age_min: int  -- 年龄下限
target_age_max: int  -- 年龄上限
target_cities: text  -- 城市偏好（JSON数组）
target_education_min: varchar(32)  -- 学历要求
target_income_min_wan: int  -- 收入下限（万）
target_income_max_wan: int  -- 收入上限（万）
target_marital_statuses: text  -- 婚姻状态要求（JSON数组）
target_house_requirement: varchar(32)  -- 房产要求
target_car_requirement: varchar(32)  -- 车辆要求

-- 时间戳
last_confirmed_at: datetime  -- 最后确认时间
last_inferred_at: datetime  -- 最后推断时间
created_at: datetime
updated_at: datetime
```

**self_personality_traits_json示例**:
```json
{
  "mbti": {
    "type_code": "ISFP",
    "description": "温和细腻，重视和谐"
  },
  "attachment": {
    "type_code": "secure",
    "anxiety_score": 0.3,
    "avoidance_score": 0.2
  },
  "values": {
    "value_type": "稳定经营型",
    "top_values": ["稳定经营", "家庭责任"]
  },
  "big_five": {
    "scores": {
      "openness": 0.7,
      "conscientiousness": 0.8,
      "agreeableness": 0.9,  // 宜人性高 = 温柔
      "neuroticism": 0.3,
      "extraversion": 0.4
    }
  }
}
```

---

#### 3. conversation_summaries表（对话摘要）

**用途**: 从对话中提取的性格/偏好摘要

**关键字段**:
```sql
summary_id: bigint (主键)
conversation_id: varchar(191)  -- 对话ID
conversation_type: varchar(32)  -- 对话类型
requester_id: bigint  -- 请求者ID
profile_id: bigint  -- 用户ID
summary_key: varchar(50)  -- 摘要类型（如personality_traits/values）
summary_text: varchar(500)  -- 摘要文本内容
vector_status: varchar(20)  -- 向量状态
created_at: datetime
```

---

### 向量库维度（VECTOR_TYPES_CONFIG）

#### 配置位置
文件: `match_domain/vector_store_lite.py`

#### 向量类型定义

| 向量类型 | 说明 | 稳定性 | 衰减周期 |
|---------|------|--------|---------|
| `personality_traits` | 性格特质（温柔、内向） | 极稳定 | 365天 |
| `values` | 价值观（重视家庭、重视事业） | 极稳定 | 365天 |
| `life_attitude` | 生活态度（追求稳定） | 中等稳定 | 90天 |
| `partner_expectation` | 挝偶期望（希望温柔的人） | 中等稳定 | 90天 |
| `partner_personality_preference` | 性格偏好（温和、细腻） | 中等稳定 | 90天 |
| `partner_relationship_pacing` | 关系节奏（慢热、明确） | 中等稳定 | 90天 |
| `partner_lifestyle_preference` | 生活偏好（作息规律） | 中等稳定 | 90天 |
| `emotional_needs` | 情感需求（需要理解支持） | 波动大 | 30天 |

---

## 三、完整数据加载方案

### 需要加载的数据维度（返回给Agent）

#### 完整画像结构（7个维度）

```python
{
  # 【维度1】基础画像（来自profiles表）
  "basic_profile": {
    "profile_id": 6092,
    "name": "于若岚",
    "age": 27,
    "city": "无锡",
    "education": "博士",
    "job": "产品经理",
    "income_range": "20-30万",
    "marital_status": "未婚",
    "has_children": False,
    "relationship_goal": "dating",  # 关系目标
    "profile_status": "active",  # 活跃状态
    "verified_level": "basic",  # 认证等级

    # 公开展示的性格/价值观文本
    "public_personality": "ISFP，温和细腻",
    "public_values": "重视家庭，追求稳定"
  },

  # 【维度2】性格信号（来自user_personas.self_personality_traits_json）
  "personality_signals": {
    "mbti": {
      "type_code": "ISFP",
      "description": "温和细腻，重视和谐"  # 从向量摘要加载
    },
    "attachment": {
      "type_code": "secure",
      "anxiety_score": 0.3,
      "avoidance_score": 0.2,
      "description": "安全型依恋，相处舒服"
    },
    "values": {
      "value_type": "稳定经营型",
      "top_values": ["稳定经营", "家庭责任"],
      "description": "重视家庭稳定，有责任感"
    },
    "big_five": {
      "openness": 0.7,
      "conscientiousness": 0.8,
      "agreeableness": 0.9,  # 宜人性高 = 温柔
      "neuroticism": 0.3,
      "extraversion": 0.4
    }
  },

  # 【维度3】择偶偏好（来自user_personas表）
  "partner_preference": {
    "target_age_range": "26-32",
    "target_cities": ["无锡", "上海"],
    "target_education_min": "硕士",
    "target_income_range": "15-25万",
    "target_marital_statuses": ["未婚"],
    "target_house_requirement": "prefer_have",  # 希望有房
    "target_car_requirement": "accept_no",  # 接受无车

    # 性格偏好（从向量摘要加载）
    "target_personality_preference": "希望对方成熟稳重、有责任感",
    "target_relationship_pacing": "慢热，节奏明确",
    "target_lifestyle_preference": "作息规律、工作稳定"
  },

  # 【维度4】情感需求（从向量摘要加载）
  "emotional_needs": {
    "companionship_level": "高",  # 陪伴需求
    "communication_frequency": "每天沟通",
    "emotional_support_type": "需要理解和鼓励",
    "conflict_resolution_style": "理性沟通"
  },

  # 【维度5】生活偏好（从向量摘要加载）
  "lifestyle": {
    "life_pace": "适中",  # 生活节奏
    "hobbies": ["阅读", "瑜伽", "旅行"],
    "spending_style": "理性消费",
    "work_life_balance": "重视生活质量"
  },

  # 【维度6】向量相似度（如果有）
  "vector_similarity": {
    "personality_traits_similarity": 0.85,  # 性格相似度
    "values_similarity": 0.80,  # 价值观相似度
    "emotional_needs_similarity": 0.75  # 情感需求相似度
  },

  # 【维度7】历史行为（简要）
  "behavior": {
    "last_active_at": "2024-06-20",
    "profile_age_days": 180,  # 注册多久了
    "feedback_count": 3,  # 反馈次数
    "match_count": 2  # 匹配次数
  }
}
```

---

### 数据加载优先级分层

| 优先级 | 数据维度 | 加载来源 | 必要性 | 缺失影响 |
|-------|---------|---------|--------|---------|
| **P0** | 基础画像（profiles） | MySQL profiles表 | 必须加载 | 无法推荐该候选人 |
| **P0** | 性格信号（MBTI/依恋/价值观） | user_personas.self_personality_traits_json | 必须加载 | 无法判断性格匹配 |
| **P1** | 择偶偏好（硬约束） | user_personas表字段 | 强烈建议加载 | Agent推理略通用 |
| **P1** | 性格摘要描述 | 向量库conversation_summaries | 强烈建议加载 | 推荐理由略通用 |
| **P2** | 向量相似度 | 向量库搜索结果 | 建议加载 | 缺少相似度参考 |
| **P3** | 历史行为 | profiles.last_active_at | 可选加载 | 不影响核心推荐 |

---

## 四、兜底机制设计

### 1. 数据缺失场景处理

#### 场景1：向量摘要缺失

**现象**: 向量库里没有性格摘要数据

**兜底方案**: 用MBTI/依恋/价值观通用描述模板

**实现逻辑**:
```python
# 第一层：尝试从向量库加载
summary = await vector_store.get_summary(user_id, vector_type="personality_traits")

if summary:
    return summary  # 成功加载

# 第二层：兜底 - 用MBTI通用描述
personality_signals = await get_personality_signals(user_id)
mbti_code = personality_signals.get("mbti", {}).get("type_code", "")

if mbti_code:
    # 预定义通用描述（兜底用）
    MBTI_DESCRIPTIONS = {
        "ISFP": "温和细腻，重视和谐，情感丰富，善于倾听",
        "ESTJ": "果断务实，执行力强，有事业心，善于规划",
        "ISTJ": "稳重可靠，重视责任，做事严谨，有耐心",
        # ...其他类型...
    }
    return MBTI_DESCRIPTIONS.get(mbti_code, "")
```

**用户体验**: 推荐理由略通用，但可用

---

#### 场景2：择偶偏好缺失

**现象**: user_personas表中择偶偏好字段为空

**兜底方案**: 不返回该字段，Agent不依赖

**实现逻辑**:
```python
partner_preference = await get_partner_preference(user_id)

if not partner_preference:
    # 不返回该字段，Agent只基于性格数据推理
    return {}
```

**用户体验**: 不影响核心推荐逻辑

---

#### 场景3：性格数据完全缺失

**现象**: user_personas.self_personality_traits_json为空或不存在

**兜底方案**: **不推荐该候选人**

**实现逻辑**:
```python
personality_signals = await get_personality_signals(user_id)

if not personality_signals:
    # 性格数据缺失，跳过该候选人
    logger.warning(f"候选人 {profile_id} 性格数据缺失，跳过推荐")
    return None
```

**用户体验**: 宁可少推荐，不要瞎推荐（确保推荐质量）

---

### 2. 兜底逻辑核心原则

**关键规则**:
- **宁可少推荐，不要瞎推荐**
- **性格数据缺失时，候选人应该被过滤掉，而非强行推荐**
- **摘要缺失时，用通用描述兜底（保证可用）**
- **择偶偏好缺失时，不影响核心推荐逻辑**

---

## 五、具体实现方案

### 1. 代码改动点

#### 改动文件
`external-systems/partner-discovery-system/discovery_system/service_integrations.py`

---

#### 新增函数：`_load_full_candidate_profiles`

**功能**: 加载候选人完整画像（7个维度数据）

**代码实现**:
```python
async def _load_full_candidate_profiles(
    candidate_ids: List[int],
    *,
    requester_traits: Dict[str, Any] | None = None,
) -> List[Dict[str, Any]]:
    """加载候选人完整画像（多维度数据）

    Args:
        candidate_ids: 候选人ID列表
        requester_traits: 请求者性格数据（用于计算相似度）

    Returns:
        候选人完整画像列表（过滤掉数据缺失的候选人）
    """

    # 并发加载所有候选人
    tasks = [_load_single_profile(id, requester_traits=requester_traits)
             for id in candidate_ids]
    results = await asyncio.gather(*tasks)

    # 过滤掉空结果（性格数据缺失的候选人）
    return [r for r in results if r]
```

---

#### 新增函数：`_load_single_profile`

**功能**: 加载单个候选人完整画像（严格兜底）

**代码实现**:
```python
async def _load_single_profile(
    profile_id: int,
    *,
    requester_traits: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    """加载单个候选人画像，严格兜底逻辑

    Returns:
        None: 性格数据缺失，跳过推荐
        Dict: 完整画像数据
    """

    # 【P0 必须加载】基础画像
    basic_profile = await _get_basic_profile(profile_id)
    if not basic_profile:
        _logger.warning(f"候选人 {profile_id} 基础画像缺失，跳过推荐")
        return None

    # 【P0 必须加载】性格信号
    personality_signals = await _get_personality_signals(profile_id)
    if not personality_signals:
        _logger.warning(f"候选人 {profile_id} 性格数据缺失，跳过推荐")
        return None

    # 【P1 强烈建议】择偶偏好
    partner_preference = await _get_partner_preference(profile_id) or {}

    # 【P1 强烈建议】性格摘要描述（从向量库）
    personality_summary = await _get_personality_summary_from_vector(profile_id) or {}

    # 【用摘要丰富性格信号】
    enriched_personality = _enrich_personality_with_summary(
        personality_signals,
        personality_summary
    )

    # 【P2 建议】向量相似度（如果有请求者数据）
    vector_similarity = {}
    if requester_traits:
        vector_similarity = await _get_vector_similarity(
            profile_id,
            requester_traits=requester_traits
        ) or {}

    # 【P3 可选】历史行为（简要）
    behavior = await _get_user_behavior_summary(profile_id) or {}

    # 组装完整数据
    return {
        "basic_profile": basic_profile,
        "personality_signals": enriched_personality,
        "partner_preference": partner_preference,
        "emotional_needs": personality_summary.get("emotional_needs", {}),
        "lifestyle": personality_summary.get("lifestyle", {}),
        "vector_similarity": vector_similarity,
        "behavior": behavior,
    }
```

---

#### 新增函数：`_get_basic_profile`

**功能**: 从profiles表加载基础画像

**代码实现**:
```python
async def _get_basic_profile(profile_id: int) -> Dict[str, Any] | None:
    """从profiles表加载基础画像"""

    query = """
        SELECT
            id as profile_id,
            name, age, city, education, job, income_range,
            marital_status, has_children, relationship_goal,
            profile_status, verified_level,
            public_personality, public_values,
            last_active_at
        FROM profiles
        WHERE id = ?
    """

    try:
        result = await db_query(query, (profile_id,))
        if not result:
            return None

        row = result[0]

        # 计算注册天数（profile_age_days）
        created_at = row.get("created_at")
        if created_at:
            profile_age_days = (datetime.now() - created_at).days
        else:
            profile_age_days = 0

        return {
            "profile_id": row["profile_id"],
            "name": row["name"],
            "age": row["age"],
            "city": row["city"],
            "education": row["education"],
            "job": row["job"],
            "income_range": row["income_range"],
            "marital_status": row["marital_status"],
            "has_children": row["has_children"],
            "relationship_goal": row["relationship_goal"],
            "profile_status": row["profile_status"],
            "verified_level": row["verified_level"],
            "public_personality": row["public_personality"],
            "public_values": row["public_values"],
            "last_active_at": row["last_active_at"],
            "profile_age_days": profile_age_days,
        }

    except Exception as e:
        _logger.error(f"加载基础画像失败: profile_id={profile_id}, error={e}")
        return None
```

---

#### 新增函数：`_get_personality_signals`

**功能**: 从user_personas表加载性格信号

**代码实现**:
```python
async def _get_personality_signals(profile_id: int) -> Dict[str, Any] | None:
    """从user_personas表加载性格信号"""

    query = """
        SELECT
            self_personality_traits_json
        FROM user_personas
        WHERE profile_id = ?
    """

    try:
        result = await db_query(query, (profile_id,))

        if not result or not result[0].get("self_personality_traits_json"):
            return None

        # 解析JSON
        traits_json = result[0]["self_personality_traits_json"]
        personality_signals = json.loads(traits_json)

        return personality_signals

    except Exception as e:
        _logger.error(f"加载性格信号失败: profile_id={profile_id}, error={e}")
        return None
```

---

#### 新增函数：`_get_partner_preference`

**功能**: 从user_personas表加载择偶偏好

**代码实现**:
```python
async def _get_partner_preference(profile_id: int) -> Dict[str, Any] | None:
    """从user_personas表加载择偶偏好"""

    query = """
        SELECT
            target_age_min, target_age_max,
            target_cities, target_education_min,
            target_income_min_wan, target_income_max_wan,
            target_marital_statuses,
            target_house_requirement, target_car_requirement
        FROM user_personas
        WHERE profile_id = ?
    """

    try:
        result = await db_query(query, (profile_id,))

        if not result:
            return None

        row = result[0]

        return {
            "target_age_range": f"{row['target_age_min']}-{row['target_age_max']}",
            "target_cities": json.loads(row['target_cities'] or "[]"),
            "target_education_min": row['target_education_min'],
            "target_income_range": f"{row['target_income_min_wan']}-{row['target_income_max_wan']}万",
            "target_marital_statuses": json.loads(row['target_marital_statuses'] or "[]"),
            "target_house_requirement": row['target_house_requirement'],
            "target_car_requirement": row['target_car_requirement'],
        }

    except Exception as e:
        _logger.error(f"加载择偶偏好失败: profile_id={profile_id}, error={e}")
        return None
```

---

#### 新增函数：`_get_personality_summary_from_vector`

**功能**: 从向量库加载性格摘要（带兜底）

**代码实现**:
```python
async def _get_personality_summary_from_vector(profile_id: int) -> Dict[str, Any]:
    """从向量库加载性格摘要（两层兜底机制）"""

    # 【第一层】尝试从向量库加载
    try:
        summaries = await vector_store.get_user_vectors(
            user_id=profile_id,
            vector_types=[
                "personality_traits",
                "values",
                "emotional_needs",
                "partner_personality_preference",
                "partner_relationship_pacing",
                "partner_lifestyle_preference",
            ]
        )

        # 如果有摘要数据，解析返回
        if summaries:
            return _parse_vector_summaries(summaries)

    except Exception as e:
        _logger.warning(f"向量库摘要加载失败: profile_id={profile_id}, error={e}")

    # 【第二层】兜底：用MBTI/依恋通用描述
    personality_signals = await _get_personality_signals(profile_id)
    if personality_signals:
        return _generate_fallback_summary(personality_signals)

    # 完全缺失，返回空
    return {}
```

---

#### 新增函数：`_enrich_personality_with_summary`

**功能**: 用摘要描述丰富性格信号

**代码实现**:
```python
def _enrich_personality_with_summary(
    personality_signals: Dict[str, Any],
    personality_summary: Dict[str, Any],
) -> Dict[str, Any]:
    """用摘要描述丰富性格信号"""

    enriched = deepcopy(personality_signals)

    # 补充MBTI描述
    mbti_code = enriched.get("mbti", {}).get("type_code", "")
    if mbti_code:
        if personality_summary.get("mbti_description"):
            enriched["mbti"]["description"] = personality_summary["mbti_description"]
        else:
            # 兜底：用通用描述
            enriched["mbti"]["description"] = MBTI_DESCRIPTIONS.get(mbti_code, "")

    # 补充依恋描述
    attachment_code = enriched.get("attachment", {}).get("type_code", "")
    if attachment_code:
        if personality_summary.get("attachment_description"):
            enriched["attachment"]["description"] = personality_summary["attachment_description"]
        else:
            enriched["attachment"]["description"] = ATTACHMENT_DESCRIPTIONS.get(attachment_code, "")

    # 补充价值观描述
    value_type = enriched.get("values", {}).get("value_type", "")
    if value_type:
        if personality_summary.get("values_description"):
            enriched["values"]["description"] = personality_summary["values_description"]
        else:
            enriched["values"]["description"] = VALUES_DESCRIPTIONS.get(value_type, "")

    return enriched
```

---

#### 预定义通用描述（兜底用）

**代码实现**:
```python
# MBTI通用描述模板
MBTI_DESCRIPTIONS = {
    "ISFP": "温和细腻，重视和谐，情感丰富，善于倾听",
    "ESTJ": "果断务实，执行力强，有事业心，善于规划",
    "ISTJ": "稳重可靠，重视责任，做事严谨，有耐心",
    "ESFJ": "热情友善，重视关系，善于照顾他人",
    "ISFJ": "温和体贴，重视细节，有奉献精神",
    "ESTP": "灵活务实，行动力强，善于应变",
    "ESFP": "活泼开朗，享受当下，善于社交",
    "ISTP": "冷静理性，善于分析，动手能力强",
    "INFJ": "理想主义，重视深度，善于洞察",
    "INTJ": "战略思维，重视规划，执行力强",
    "INFP": "理想主义，重视价值，情感丰富",
    "INTP": "逻辑思维，善于分析，追求真理",
    "ENFJ": "热情领袖，善于激励，重视团队",
    "ENTJ": "果断领袖，重视效率，善于决策",
    "ENFP": "热情创意，善于启发，追求自由",
    "ENTP": "灵活创新，善于辩论，追求挑战",
}

# 依恋风格通用描述模板
ATTACHMENT_DESCRIPTIONS = {
    "secure": "安全型依恋，相处舒服，沟通顺畅，情感稳定",
    "avoidant": "回避型依恋，重视独立空间，情感表达较少",
    "anxious": "焦虑型依恋，渴望亲密，容易患得患失",
    "fearful": "恐惧型依恋，既渴望亲密又害怕受伤",
}

# 价值观通用描述模板
VALUES_DESCRIPTIONS = {
    "稳定经营型": "重视家庭稳定，有责任感，追求长期关系",
    "独立清醒型": "重视个人空间，追求生活质感，理性独立",
    "家庭投入型": "重视家庭责任，愿意投入家庭，有牺牲精神",
    "事业成就型": "重视事业成就，追求职业发展，有上进心",
    "生活享乐型": "重视生活质量，追求快乐体验，善于享受",
    "自我实现型": "重视个人成长，追求自我价值，有探索精神",
}
```

---

### 2. 改造search_partner_candidates工具返回结构

#### 改动前的返回结构（不完整）

```python
{
  'has_match': True,
  'result_count': 5,
  'results': [
    {
      'profile_id': 6092,
      'title': '于若岚',
      'summary': '27岁，无锡，产品经理，博士',
      'score': 130
    }
  ]
}
```

---

#### 改动后的返回结构（完整画像）

```python
{
  'has_match': True,
  'result_count': 5,
  'results': [
    {
      'profile_id': 6092,
      'title': '于若岚',
      'subtitle': '27岁，无锡，产品经理，博士',

      # 【新增】完整画像（Agent用于推理）
      'full_profile': {
        'basic_profile': {
          'name': '于若岚',
          'age': 27,
          'city': '无锡',
          'job': '产品经理',
          'education': '博士',
          'income_range': '20-30万',
          'marital_status': '未婚',
          'has_children': False,
          'relationship_goal': 'dating',
          'profile_status': 'active'
        },

        'personality_signals': {
          'mbti': {
            'type_code': 'ISFP',
            'description': '温和细腻，重视和谐'  # 有数据支撑
          },
          'attachment': {
            'type_code': 'secure',
            'description': '安全型依恋，相处舒服'
          },
          'values': {
            'value_type': '稳定经营型',
            'top_values': ['稳定经营', '事业成长'],
            'description': '重视事业成长，有上进心'
          },
          'big_five': {
            'agreeableness': 0.9,  # 宜人性高 = 温柔
            'conscientiousness': 0.8  # 尽责性高 = 有上进心
          }
        },

        'partner_preference': {
          'target_age_range': '26-32',
          'target_cities': ['无锡', '上海'],
          'target_education_min': '硕士',
          'target_income_range': '15-25万'
        },

        'emotional_needs': {
          'companionship_level': '高',
          'communication_frequency': '每天沟通',
          'emotional_support_type': '需要理解和鼓励'
        },

        'lifestyle': {
          'life_pace': '适中',
          'hobbies': ['阅读', '瑜伽', '旅行'],
          'spending_style': '理性消费',
          'work_life_balance': '重视生活质量'
        },

        'vector_similarity': {
          'personality_traits_similarity': 0.85,
          'values_similarity': 0.80
        },

        'behavior': {
          'last_active_at': '2024-06-20',
          'profile_age_days': 180
        }
      },

      # 兼容旧逻辑
      'score': 130,
      'compatibility_summary': "MBTI ISFP；依恋偏secure"
    }
  ]
}
```

---

## 六、Agent推理逻辑调整

### 1. Agent Prompt调整

**调整位置**: `discovery_system/agent_runtime.py`（SOUL.md或Agent instructions）

**调整内容**:

#### 当前Prompt（只告诉Agent看personality_signals）

```markdown
返回数据：
- 基础信息：姓名、年龄、城市、职业等
- 性格数据：personality_signals包含MBTI、依恋风格、价值观等原始数据
- Agent自主判断性格匹配度，生成推荐理由
```

---

#### 新Prompt（告诉Agent看完整画像）

```markdown
返回数据：
- **完整画像**：每个候选人包含以下维度
  - basic_profile：基础信息（年龄/城市/职业/学历/收入/婚姻状态）
  - personality_signals：性格数据（MBTI/依恋/价值观 + 详细描述）
  - partner_preference：择偶偏好（年龄范围/城市偏好/学历要求/收入要求）
  - emotional_needs：情感需求（陪伴需求/沟通频率/情感支持类型）
  - lifestyle：生活偏好（生活节奏/兴趣爱好/消费观）
  - vector_similarity：向量相似度（性格相似度/价值观相似度）

Agent判断逻辑：
- **基于完整画像做匹配推理**
- 不只看MBTI标签，要结合：
  - MBTI描述（是否温和、细腻）
  - 依恋类型（是否安全型、相处舒服）
  - 价值观（是否有上进心、重视事业）
  - 情感需求（是否匹配你的需求）

- **推荐理由要具体**：
  - 解释为什么某个维度匹配用户需求
  - 引用具体描述（如："ISFP温和细腻，价值观重视事业成长"）

- **诚实说明不匹配**：
  - 如果某个维度不匹配，诚实说明（如："她的相处节奏可能和你不太合")

- **不要瞎推理**：
  - 如果某个维度数据缺失，不要硬编理由
  - 诚实说明数据不足（如："她的情感需求数据暂未完善，建议先聊聊看")
```

---

### 2. Agent推理示例对比

#### 当前推理（缺乏数据支撑）

**用户说**: "我想找温柔、有上进心的"

**Agent只看到**:
```json
{
  "mbti": {"type_code": "ISFP"},
  "attachment": {"type_code": "secure"}
}
```

**Agent推理**:
```
"ISFP天生温柔"（没有数据支撑，只是MBTI通用标签）
"ESTJ有事业心"（也是通用标签，没有个性化描述）
```

---

#### 改进后推理（有数据支撑）

**用户说**: "我想找温柔、有上进心的"

**Agent看到完整数据**:
```json
{
  "mbti": {
    "type_code": "ISFP",
    "description": "温和细腻，重视和谐"  // 有具体描述
  },
  "values": {
    "top_values": ["事业成长", "稳定经营"],  // 有价值观数据
    "description": "重视事业成长，有上进心"
  },
  "big_five": {
    "agreeableness": 0.9,  // 宜人性高 = 温柔（有数据支撑）
    "conscientiousness": 0.8  // 尽责性高 = 有上进心
  }
}
```

**Agent推理**:
```
"推荐于若岚：
- ISFP性格温和细腻（描述明确提到"温和"）
- 大五人格宜人性0.9，说明性格温柔（有数据支撑）
- 价值观重视'事业成长'，有上进心（价值观数据支撑）
- 产品经理 + 博士学历，事业上有追求（职业数据支撑）"
```

---

## 七、实施步骤和优先级

### Phase 1：数据层补全（优先级最高）

**目标**: 确保向量库有完整的性格摘要数据

| 步骤 | 动作 | 时间 | 验证方式 |
|-----|------|------|---------|
| 1 | 统计缺失情况 | 1天 | `SELECT COUNT(*) FROM user_vectors WHERE summary IS NULL` |
| 2 | 编写补全脚本 | 2天 | 运行脚本，检查写入数据 |
| 3 | 批量补全摘要 | 3天 | 验证摘要字段非空 |
| 4 | 增量写入机制 | 1天 | 新用户注册时自动写入摘要 |

**负责人**: 数据团队
**依赖**: 无

---

### Phase 2：数据加载逻辑改造（优先级高）

**目标**: 搜索工具返回完整画像

| 步骤 | 动作 | 时间 | 验证方式 |
|-----|------|------|---------|
| 1 | 实现`_load_full_profiles`函数 | 2天 | 单元测试，检查返回数据结构 |
| 2 | 实现兜底逻辑（静态描述） | 1天 | 测试缺失数据场景 |
| 3 | 改造`search_partner_candidates`返回结构 | 1天 | 集成测试，检查Agent收到的数据 |
| 4 | 性能优化（并发加载） | 1天 | 测试加载耗时 < 500ms |

**负责人**: 后端开发团队
**依赖**: Phase 1完成

---

### Phase 3：Agent推理能力提升（优先级中）

**目标**: Agent基于完整数据自主判断

| 步骤 | 动作 | 时间 | 验证方式 |
|-----|------|------|---------|
| 1 | 调整Prompt（告诉Agent看完整画像） | 1天 | 测试Agent输出质量 |
| 2 | 测试推荐理由准确性 | 2天 | 人工评估推荐理由是否合理 |
| 3 | 优化Agent推理逻辑 | 2天 | A/B测试，对比新旧推荐效果 |

**负责人**: AI团队
**依赖**: Phase 2完成

---

### Phase 4：监控与验证（持续）

**目标**: 确保数据质量持续稳定

| 监控指标 | 说明 | 阈值 | 告警方式 |
|---------|------|------|---------|
| `vector_summary_coverage` | 向量摘要覆盖率 | > 95% | 低于90%告警 |
| `profile_load_success_rate` | 画像加载成功率 | > 99% | 低于95%告警 |
| `agent_reasoning_quality` | 推荐理由质量评分 | > 4.0分 | 低于3.5分告警 |
| `recommendation_click_rate` | 推荐点击率 | > 30% | 低于25%告警 |

**负责人**: 数据团队 + 运维团队
**依赖**: Phase 1-3全部完成

---

## 八、性能优化方案

### 1. 数据加载并发化

**优化点**: 候选人画像加载并发执行

**代码实现**:
```python
async def _load_full_candidate_profiles(...) -> List[Dict[str, Any]]:
    """并发加载候选人画像"""

    # 并发加载所有候选人
    tasks = [_load_single_profile(id) for id in candidate_ids]
    results = await asyncio.gather(*tasks)

    return [r for r in results if r]
```

**耗时预估**:
- 单个候选人加载: ~50ms（并发加载7个维度）
- 5个候选人加载: ~250ms（并发）
- **可接受范围**: < 500ms

---

### 2. 缓存机制

**优化点**: 候选人画像短时缓存

**代码实现**:
```python
from cachetools import TTLCache

# 缓存候选人画像（5分钟缓存）
PROFILE_CACHE = TTLCache(maxsize=1000, ttl=300)

async def _load_single_profile(profile_id: int) -> Dict[str, Any] | None:
    # 先查缓存
    cached = PROFILE_CACHE.get(profile_id)
    if cached:
        return cached

    # 缓存未命中，加载并缓存
    profile = await _do_load_profile(profile_id)
    if profile:
        PROFILE_CACHE.set(profile_id, profile)

    return profile
```

**效果**:
- 缓存命中率: ~80%（同一候选人短时间内多次加载）
- 平均加载耗时: 从250ms降到50ms（缓存命中时）

---

### 3. 数据库查询优化

**优化点**: 批量查询候选人画像

**代码实现**:
```python
async def _batch_load_basic_profiles(profile_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """批量加载基础画像（一次查询）"""

    query = """
        SELECT
            id as profile_id,
            name, age, city, education, job, income_range,
            marital_status, has_children, relationship_goal,
            profile_status, verified_level
        FROM profiles
        WHERE id IN (?)
    """

    results = await db_query(query, (profile_ids,))

    # 组装成字典 {profile_id: profile_data}
    return {r["profile_id"]: r for r in results}
```

**效果**:
- 减少数据库连接次数: 从5次降到1次
- 查询耗时: 从200ms降到50ms

---

## 九、风险和注意事项

### 1. 数据缺失风险

**风险**: 向量库性格数据缺失严重

**应对**:
- Phase 1优先补全数据
- 兜底机制确保可用性（用通用描述模板）

---

### 2. 性能风险

**风险**: 加载完整画像耗时过长（> 1秒）

**应对**:
- 并发加载 + 缓存机制
- 批量查询优化
- 监控加载耗时，超过阈值告警

---

### 3. Agent推理质量风险

**风险**: Agent拿到完整数据后推理质量不稳定

**应对**:
- Phase 3人工评估推荐理由质量
- A/B测试对比新旧推荐效果
- 监控推荐点击率，低于阈值告警

---

### 4. 兜底机制失效风险

**风险**: 性格数据完全缺失时，候选人被过滤，推荐数量不足

**应对**:
- 向量筛选阶段放宽阈值（确保有足够候选人）
- 监控`profile_load_success_rate`，低于95%告警
- 增加降级方案：性格数据缺失时，仍展示基础信息（诚实说明数据不足）

---

## 十、验收标准

### 1. 数据层验收

- [ ] 向量摘要覆盖率 > 95%
- [ ] 新用户注册时自动写入摘要
- [ ] 摘要数据质量合格（人工抽查10个样本）

---

### 2. 加载层验收

- [ ] `_load_full_profiles`函数单元测试通过
- [ ] 兜底逻辑测试通过（模拟数据缺失场景）
- [ ] 性能测试通过（加载耗时 < 500ms）

---

### 3. Agent推理层验收

- [ ] Agent输出包含具体推荐理由（引用性格描述）
- [ ] 人工评估推荐理由质量 > 4.0分
- [ ] 推荐点击率 > 30%

---

### 4. 监控验收

- [ ] 监控指标已配置（覆盖率/加载成功率/推荐质量）
- [ ] 告警阈值已设置
- [ ] 告警通知已测试

---

## 十一、总结

### 核心改动

1. **数据层**: 向量库补全性格摘要数据
2. **加载层**: 搜索工具返回完整画像（7个维度）
3. **推理层**: Agent基于完整数据自主判断

---

### 预期效果

- **向量筛选真正有效**: similar_count > 0
- **推荐理由有数据支撑**: 引用具体性格描述
- **推荐质量提升**: 推荐点击率提升

---

### 关键原则

- **向量筛选是初筛**（找性格相似的人）
- **数据加载是关键**（把完整信息拿出来）
- **Agent判断是核心**（基于数据自主推理）
- **宁可少推荐，不要瞎推荐**（确保推荐质量）

---

## 附录：代码文件清单

### 需要改动的文件

| 文件路径 | 改动内容 |
|---------|---------|
| `external-systems/partner-discovery-system/discovery_system/service_integrations.py` | 新增 `_load_full_candidate_profiles` 等函数，改造返回结构 |
| `match_domain/vector_store_lite.py` | 新增通用描述模板（MBTI/依恋/价值观） |
| `discovery_system/agent_runtime.py` | 调整Agent Prompt，告诉Agent看完整画像 |

---

### 需要新增的脚本

| 脚本路径 | 功能 |
|---------|------|
| `scripts/backfill_vector_summaries.py` | 批量补全向量库性格摘要 |
| `scripts/check_vector_coverage.py` | 检查向量摘要覆盖率 |

---

**文档结束**