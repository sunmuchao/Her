# 问题3完整改进方案：区分字段来源，放宽画像写入策略

> **核心问题**：画像写入策略过于保守，没有区分"明确表达"和"推断"，导致用户明确偏好被跳过无法写入画像。
>
> **改进目标**：放宽保守策略，推断字段也可写入画像（只要置信度够高），让更多用户偏好能被正确记录。
>
> **三个核心约束**：
> 1. ❌ **去掉保守策略**：推断字段也可以写入画像（只要置信度够高）
> 2. ❌ **profiles表不动**：系统不能自动写入profiles表（只允许用户手动编辑）
> 3. ✅ **只动persona表**：所有LLM提炼的内容写入persona表

---

## 一、问题根因分析（五问法）

```
问题现象：所有可量化字段被跳过，无法记录用户偏好
├─ 为什么 1：source_type被硬编码为"strong_inference"
│   → 代码位置：session_end_processor.py:1119
├─ 为什么 2：画像写入策略规定推断字段不持久化
│   → 代码位置：persona_memory_lib.py:1138
├─ 为什么 3：策略认为"推断"字段不可靠，不应写入画像
│   → 理解：推断可能不准确，避免污染画像（合理）
├─ 为什么 4：但实际上LLM提炼的字段并非都是"推断"
│   → 分析：
│     - age: "28" - 已知事实（从user_profile）
│     - city: "无锡" - 已知事实（从user_profile）
│     - partner_expectation: "想找比自己大的" - 用户明确表达
├─ 为什么 5：【根本原因】策略设计没有区分"明确表达"、"已知事实"和"推断"
│   → LLM提炼时没有标注来源
│   → 分流判断只看字段名，不看来源
│   → 写入时统一标记为strong_inference
```

**根本对策**：在LLM提炼时标注每个字段的来源，写入时动态设置source_type。

---

## 二、数据模型理解（核心约束）

### profiles表 vs persona表的区别

```
┌─────────────────────────────────────────────────────────────────┐
│  profiles 表（用户手动编辑，不能动）                             │
│                                                                 │
│  字段：                                                         │
│  - age: 28 ← 用户手动填写                                       │
│  - city: "无锡" ← 用户手动填写                                   │
│  - education: "硕士" ← 用户手动填写                              │
│  - gender: "女" ← 用户手动填写                                   │
│  - income: "年薪20万" ← 用户手动填写                             │
│  ...                                                            │
│                                                                 │
│  ❌ 系统不能自动写入这个表                                        │
│  ✅ 只允许用户手动编辑                                            │
│  ❌ LLM提炼的内容不能写入profiles表                              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  persona 表（画像表，可以动）                                     │
│                                                                 │
│  字段：                                                         │
│  - age: 28 ← 可以写入（从LLM提炼）                               │
│  - city: "无锡" ← 可以写入（从LLM提炼）                          │
│  - partner_expectation: "想找比自己大的女生" ← 可以写入           │
│  - mbti: "INFJ" ← 可以写入（推断，只要置信度够高）                │
│  - personality_traits: "性格温柔" ← 可以写入                     │
│  - smoking: "不抽烟" ← 可以写入                                  │
│  - drinking: "偶尔喝酒" ← 可以写入                               │
│  ...                                                            │
│                                                                 │
│  ✅ 系统可以自动写入这个表                                        │
│  ✅ 包括明确表达、已知事实、推断（只要置信度够高）                 │
│  ✅ 放宽策略：推断字段也写入（confidence > 60）                   │
└─────────────────────────────────────────────────────────────────┘
```

### 核心约束说明

| 约束 | 说明 | 实现方式 |
|------|------|---------|
| **去掉保守策略** | 推断字段也可以写入画像 | confidence > 60就写入persona表 |
| **profiles表不动** | 系统不能自动写入profiles表 | `sync_profile=False`硬编码 |
| **只动persona表** | 所有LLM提炼的内容写入persona表 | `apply_scope="persona_only"`硬编码 |

---

## 三、当前架构问题分析

### 当前数据流程（有问题）

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1：LLM提炼（generate_structured_summary）                 │
│                                                                 │
│  Prompt: "提炼用户的所有结构化特征"                              │
│  ↓                                                              │
│  LLM返回: {                                                     │
│    "age": "28",                                                 │
│    "city": "无锡",                                              │
│    "partner_expectation": "想找比自己大的女生"                   │
│    "mbti": "INFJ"                                               │
│  }                                                              │
│                                                                 │
│  ❌ 问题：没有标注每个字段的来源                                  │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 2：分流判断（split_by_quantifiability）                   │
│                                                                 │
│  根据字段名白名单区分：                                          │
│  - age, city, mbti → 可量化字段                                 │
│  - partner_expectation → 不可量化字段                           │
│                                                                 │
│  ❌ 问题：只看字段名，不看来源                                    │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 3：写入画像（save_quantifiable_to_persona_tables）        │
│                                                                 │
│  硬编码：source_type = "strong_inference"                       │
│  ↓                                                              │
│  调用：apply_persona_patch(source_type="strong_inference")      │
│                                                                 │
│  ❌ 问题：所有字段统一标记为"推断"                                │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 4：画像策略判断（persona_memory_lib.py:merge_persona）    │
│                                                                 │
│  if source_type == "strong_inference":                          │
│      skip所有字段                                                │
│      note = "inference_not_persisted"                           │
│                                                                 │
│  ❌ 结果：所有字段被跳过，用户明确偏好无法记录                    │
└─────────────────────────────────────────────────────────────────┘
```

### 字段来源分类（实际应该区分）

| 字段 | 提取值 | 实际来源 | 应该设置的source_type | 当前设置 | 结果 |
|------|--------|---------|----------------------|---------|------|
| age | "28" | user_profile已知事实 | explicit | strong_inference | ❌跳过 |
| city | "无锡" | user_profile已知事实 | explicit | strong_inference | ❌跳过 |
| partner_expectation | "想找比自己大的女生" | 用户明确表达 | explicit | strong_inference | ❌跳过 |
| mbti | "INFJ" | 从对话推断 | strong_inference | strong_inference | ✅应跳过 |

**核心问题**：已知事实和明确表达也被当作"推断"跳过。

---

## 四、改进方案设计（放宽策略版）

### 方案核心思路

```
改进后的数据流程（放宽策略）：

┌─────────────────────────────────────────────────────────────────┐
│  Step 1：LLM提炼（改进版）                                       │
│                                                                 │
│  Prompt增加来源标注要求：                                        │
│  "为每个字段标注来源：explicit（明确表达）、known（已知）、      │
│   inferred（推断）和置信度"                                      │
│  ↓                                                              │
│  LLM返回: {                                                     │
│    "age": {"value": "28", "source": "known", "confidence": 100},│
│    "city": {"value": "无锡", "source": "known", "confidence": 100},│
│    "partner_expectation": {                                     │
│      "value": "想找比自己大的女生",                              │
│      "source": "explicit",                                      │
│      "confidence": 95                                           │
│    },                                                           │
│    "mbti": {"value": "INFJ", "source": "inferred", "confidence": 65}│
│  }                                                              │
│                                                                 │
│  ✅ 改进：每个字段标注来源和置信度                                │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 2：分流判断（改进版）                                       │
│                                                                 │
│  分离可量化字段，但保留来源信息：                                  │
│  quantifiable_data = {                                          │
│    "age": {"value": "28", "source": "known", "confidence": 100},│
│    "city": {"value": "无锡", "source": "known", "confidence": 100},│
│    "mbti": {"value": "INFJ", "source": "inferred", "confidence": 65}│
│  }                                                              │
│                                                                 │
│  ✅ 改进：保留来源信息                                            │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 3：写入persona表（放宽策略版）                              │
│                                                                 │
│  针对每个字段动态设置source_type：                                │
│  for each field in quantifiable_data:                           │
│      if field.source in {"explicit", "known"}:                  │
│          source_type = "explicit"  # 写入persona表              │
│      elif field.source == "inferred":                           │
│          if field.confidence > 60:                              │
│              source_type = "explicit"  # 写入persona表（放宽）   │
│          else:                                                  │
│              source_type = "weak_inference"  # 极低置信度跳过    │
│                                                                 │
│  ✅ 改进：放宽策略，推断字段也写入（confidence > 60）             │
│  ✅ 约束：只写persona表（apply_scope="persona_only"）            │
│  ✅ 约束：不动profiles表（sync_profile=False）                   │
└─────────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────────┐
│  Step 4：画像策略判断（放宽策略版）                                │
│                                                                 │
│  if source_type == "explicit":                                  │
│      写入persona表 ✅                                            │
│  if source_type == "weak_inference" and confidence < 60:        │
│      跳过 ❌（极低置信度才跳过）                                   │
│                                                                 │
│  ✅ 结果：明确表达、已知事实、高置信度推断都能写入persona表        │
│  ✅ 约束：只写persona表，不动profiles表                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、具体实现步骤

### Step 1：修改LLM提炼Prompt（增加来源标注）

**文件**：[match_domain/session_end_processor.py](match_domain/session_end_processor.py)

**修改位置**：`_build_summary_prompt()` 函数（第368行）

**修改内容**：

```python
def _build_summary_prompt(formatted_messages: str) -> str:
    """构造LLM提炼摘要的Prompt（改进版：增加来源标注）

    Args:
        formatted_messages: 格式化的对话文本

    Returns:
        LLM Prompt
    """
    return f"""请根据以下对话内容，提炼用户的所有结构化特征。

对话内容：
{formatted_messages}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【重要改进：每个字段必须标注来源和置信度】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

来源分类（source字段）：
- "explicit": 用户在对话中明确表达（如"我想找比我大的女生"）
- "known": 从用户profile已知的事实（如用户年龄28岁、城市无锡）
- "inferred": 从对话内容推断（如从言谈推测MBTI）

置信度（confidence字段）：
- 100: 已知事实（来自user_profile）
- 80-95: 用户明确表达（置信度很高）
- 60-80: 强推断（有明确线索但非直接表达）
- 40-60: 弱推断（基于间接线索）
- 0-40: 纯猜测（应避免）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【提炼规则】
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 性格特质（personality_traits）
2. 价值观（values）
3. 择偶期望（partner_expectation）
4. 生活态度（life_attitude）
5. 情感需求（emotional_needs）
6. 可量化字段（如果用户明确表达或已知）：
   - mbti_type、smoking、drinking、marital_status、has_children
   - city、education、age、height、income
7. 负面偏好（negative_preferences）

⚠️ 重要规则：
- 如果该维度用户没有提及，输出空字符串 ""（不要猜测）
- 每个字段必须标注来源（source）和置信度（confidence）
- 已知事实（如年龄、城市）标注为 source="known", confidence=100
- 用户明确表达标注为 source="explicit", confidence=80-95
- 推断标注为 source="inferred", confidence=根据线索强度评估

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【输出格式】（改进版：每个字段包含来源和置信度）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

示例输出：
{{
    "personality_traits": {{
        "value": "性格温柔、内向",
        "source": "explicit",
        "confidence": 85
    }},
    "values": {{
        "value": "重视家庭、重视事业",
        "source": "explicit",
        "confidence": 90
    }},
    "partner_expectation": {{
        "value": "希望找个能理解工作忙碌的人",
        "source": "explicit",
        "confidence": 95
    }},
    "age": {{
        "value": "28",
        "source": "known",
        "confidence": 100
    }},
    "city": {{
        "value": "无锡",
        "source": "known",
        "confidence": 100
    }},
    "mbti_type": {{
        "value": "INFJ",
        "source": "inferred",
        "confidence": 60
    }},
    "negative_preferences": {{
        "value": "不喜欢强势、霸道的人",
        "source": "explicit",
        "confidence": 90
    }}
}}

如果某字段用户没有提及，输出空对象 {{}} 或省略该字段。
"""
```

---

### Step 2：修改LLM返回解析逻辑（提取来源信息）

**文件**：[match_domain/session_end_processor.py](match_domain/session_end_processor.py)

**修改位置**：`generate_structured_summary()` 函数（第286行）

**修改内容**：

```python
async def generate_structured_summary(
    messages: list[dict[str, Any]],
    requester_id: int,
    *,
    llm_base_url: str | None = None,
    llm_api_key: str | None = None,
    llm_model: str | None = None,
) -> dict[str, Any]:
    """LLM提炼结构化摘要（改进版：包含来源和置信度）

    Args:
        messages: 聊天记录列表
        requester_id: 用户ID（用于日志）

    Returns:
        结构化摘要字典，格式（改进版）：
        {
            "personality_traits": {
                "value": "性格温柔、内向",
                "source": "explicit",
                "confidence": 85
            },
            "age": {
                "value": "28",
                "source": "known",
                "confidence": 100
            },
            ...
        }
    """
    formatted_messages = _format_messages_for_llm(messages)
    prompt = _build_summary_prompt(formatted_messages)

    try:
        summary_json = await _call_llm_for_json(
            prompt,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
        )

        if not isinstance(summary_json, dict):
            _logger.warning(f"LLM返回格式错误: {summary_json}")
            return {}

        # ✅ 改进：提取value、source、confidence，过滤空字段
        cleaned_summary = {}
        for field_name, field_data in summary_json.items():
            if not isinstance(field_data, dict):
                # 兼容旧格式（如果LLM返回的是字符串）
                if str(field_data or "").strip():
                    cleaned_summary[field_name] = {
                        "value": str(field_data).strip(),
                        "source": "unknown",  # 未知来源，后续需要判断
                        "confidence": 50  # 默认置信度
                    }
            else:
                # 新格式：包含value、source、confidence
                value = str(field_data.get("value") or "").strip()
                if value:
                    cleaned_summary[field_name] = {
                        "value": value,
                        "source": str(field_data.get("source") or "unknown"),
                        "confidence": int(field_data.get("confidence") or 50)
                    }

        _logger.info(
            f"LLM提炼成功（包含来源）: fields={list(cleaned_summary.keys())}, "
            f"explicit_fields={[k for k, v in cleaned_summary.items() if v['source'] == 'explicit']}, "
            f"known_fields={[k for k, v in cleaned_summary.items() if v['source'] == 'known']}, "
            f"inferred_fields={[k for k, v in cleaned_summary.items() if v['source'] == 'inferred']}"
        )

        return cleaned_summary

    except Exception as exc:
        _logger.error(f"LLM调用失败: requester_id={requester_id}, error={exc}")
        return {}
```

---

### Step 3：修改分流判断逻辑（保留来源信息）

**文件**：[match_domain/session_end_processor.py](match_domain/session_end_processor.py)

**修改位置**：`split_by_quantifiability()` 函数（第994行）

**修改内容**：

```python
def split_by_quantifiability(
    summary_data: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """分流：分离可量化字段和不可量化字段（改进版：保留来源信息）

    Args:
        summary_data: LLM提炼的结构化摘要（包含value、source、confidence）

    Returns:
        (quantifiable_data, non_quantifiable_data)
        - quantifiable_data: 可量化字段（包含来源信息）
        - non_quantifiable_data: 不可量化字段（包含来源信息）

    例子：
        输入：{
            "age": {"value": "28", "source": "known", "confidence": 100},
            "personality_traits": {"value": "性格温柔", "source": "explicit", "confidence": 85}
        }

        输出：
        quantifiable_data = {
            "age": {"value": "28", "source": "known", "confidence": 100}
        }
        non_quantifiable_data = {
            "personality_traits": {"value": "性格温柔", "source": "explicit", "confidence": 85}
        }
    """
    # 导入可量化字段白名单
    try:
        from match_domain.profile_write_guard import QUANTIFIABLE_FIELDS
    except ImportError:
        QUANTIFIABLE_FIELDS = frozenset({
            "age", "age_min", "age_max",
            "height", "height_min", "height_max",
            "mbti_type", "personality_type",
            "marital_status", "has_children",
            "smoking", "drinking",
            "city", "cities",
            "education",
            "income", "income_min", "income_max",
            "gender",
        })

    quantifiable_data = {}
    non_quantifiable_data = {}

    for field_name, field_data in summary_data.items():
        # ✅ 改进：保留完整的字段数据（包含来源和置信度）
        if field_name in QUANTIFIABLE_FIELDS:
            quantifiable_data[field_name] = field_data
        else:
            non_quantifiable_data[field_name] = field_data

    _logger.info(
        f"分流完成（包含来源）: "
        f"quantifiable={list(quantifiable_data.keys())}, "
        f"non_quantifiable={list(non_quantifiable_data.keys())}, "
        f"quantifiable_sources={[(k, v['source']) for k, v in quantifiable_data.items()]}"
    )

    return quantifiable_data, non_quantifiable_data
```

---

### Step 4：修改画像写入逻辑（放宽策略版）

**文件**：[match_domain/session_end_processor.py](match_domain/session_end_processor.py)

**修改位置**：`save_quantifiable_to_persona_tables()` 函数（第1080行）

**修改内容**：

```python
async def save_quantifiable_to_persona_tables(
    user_key: str,
    profile_id: str | None,
    session_id: str,
    quantifiable_data: dict[str, Any],  # ✅ 改进：包含来源信息
    *,
    dsn: str | None = None,
) -> dict[str, Any]:
    """保存可量化字段到画像表（放宽策略版：推断字段也写入）

    Args:
        user_key: 用户ID
        profile_id: Profile ID
        session_id: 会话ID
        quantifiable_data: 可量化字段数据（包含value、source、confidence）
        dsn: 数据库连接字符串

    Returns:
        写入结果

    改进版关键设计（放宽策略）：
    - 根据字段来源和置信度动态设置source_type
    - explicit/known → source_type="explicit"（写入persona表）
    - inferred + confidence > 60 → source_type="explicit"（写入persona表）
    - inferred + confidence < 60 → source_type="weak_inference"（跳过）

    核心约束：
    - ✅ 只写persona表（apply_scope="persona_only"）
    - ✅ 不动profiles表（sync_profile=False）
    - ✅ 推断字段也写入（放宽策略，confidence > 60）
    """
    try:
        from persona_memory_sync.persona_memory_lib import apply_persona_patch
    except ImportError:
        _logger.error("导入 apply_persona_patch 失败，无法写入画像")
        return {"success": False, "error": "import_failed"}

    resolved_dsn = dsn or os.environ.get("HER_PERSONA_DB") or os.environ.get("PARTNER_DISCOVERY_DB") or ""

    if not resolved_dsn:
        _logger.warning("没有配置数据库连接，无法写入画像")
        return {"success": False, "error": "dsn_not_configured"}

    def _save_sync() -> dict[str, Any]:
        """同步写入画像表（放宽策略版：按字段分批写入）"""
        try:
            all_results = []
            applied_fields = []
            skipped_fields = []

            # ✅ 改进：按字段逐个处理，放宽策略
            for field_name, field_data in quantifiable_data.items():
                value = field_data.get("value")
                source = field_data.get("source", "unknown")
                confidence = field_data.get("confidence", 50)

                # ✅ 改进：放宽策略，推断字段也写入（confidence > 60）
                if source in {"explicit", "known"}:
                    source_type = "explicit"  # 明确表达或已知事实 → 写入persona表
                elif source == "inferred":
                    if confidence > 60:
                        # ✅ 放宽策略：高置信度推断也写入persona表
                        source_type = "explicit"  # 当作"明确"处理，写入persona表
                        _logger.info(
                            f"放宽策略：推断字段写入persona表: field={field_name}, "
                            f"confidence={confidence}（放宽策略，不再跳过）"
                        )
                    else:
                        # 极低置信度推断 → 跳过
                        source_type = "weak_inference"
                        _logger.info(
                            f"极低置信度推断跳过: field={field_name}, "
                            f"confidence={confidence}（confidence < 60）"
                        )
                else:
                    # 未知来源，保守处理：当作推断，根据置信度决定
                    if confidence > 60:
                        source_type = "explicit"  # 写入persona表
                        _logger.warning(
                            f"字段来源未知但置信度高，写入persona表: field={field_name}, "
                            f"source={source}, confidence={confidence}"
                        )
                    else:
                        source_type = "weak_inference"  # 跳过
                        _logger.warning(
                            f"字段来源未知且置信度低，跳过: field={field_name}, "
                            f"source={source}, confidence={confidence}"
                        )

                # 构造 evidence_text（记录溯源）
                evidence_text = (
                    f"会话结束后LLM提炼（session_id={session_id}, "
                    f"field={field_name}, source={source}, confidence={confidence})"
                )

                # ✅ 约束：只写persona表，不动profiles表
                result = apply_persona_patch(
                    source=resolved_dsn,
                    user_key=user_key,
                    source_type=source_type,  # ✅ 改进：动态设置（放宽策略）
                    source_channel="discovery_session_end",
                    normalized_patch={field_name: value},  # 单字段写入
                    confidence_score=confidence,  # ✅ 改进：使用LLM返回的置信度
                    evidence_text=evidence_text,
                    conversation_ref=session_id,
                    apply_scope="persona_only",  # ✅ 约束：只写persona表
                    sync_profile=False,  # ✅ 约束：不动profiles表
                )

                all_results.append({
                    "field_name": field_name,
                    "source": source,
                    "source_type": source_type,
                    "confidence": confidence,
                    "applied": result.get("applied_fields", []),
                    "skipped": result.get("skipped_fields", []),
                })

                if result.get("applied_fields"):
                    applied_fields.extend(result["applied_fields"])
                if result.get("skipped_fields"):
                    skipped_fields.extend(result["skipped_fields"])

            _logger.info(
                f"可量化字段写入完成（放宽策略版）: user_key={user_key}, "
                f"applied={applied_fields}, skipped={skipped_fields}, "
                f"sources={[(r['field_name'], r['source'], r['confidence']) for r in all_results]}"
            )

            return {
                "success": True,
                "user_key": user_key,
                "applied_fields": applied_fields,
                "skipped_fields": skipped_fields,
                "field_results": all_results,  # ✅ 改进：详细的字段级结果
                "synced_profile": False,  # ✅ 约束：不动profiles表
            }

        except Exception as exc:
            _logger.error(f"可量化字段写入失败: user_key={user_key}, error={exc}")
            return {"success": False, "error": str(exc)[:200]}

    return await asyncio.to_thread(_save_sync)
```

---

### Step 5：修改画像策略（放宽策略版）

**文件**：[persona_memory_sync/persona_memory_lib.py](persona_memory_sync/persona_memory_lib.py)

**修改位置**：`merge_persona()` 函数（第1130行）

**放宽策略改进**：

```python
def merge_persona(
    existing: Optional[Dict[str, Any]],
    patch: Dict[str, Any],
    source_type: str,
    confidence_score: int = 85,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """合并画像（放宽策略版：推断字段也写入）

    Args:
        existing: 现有画像
        patch: 待写入的字段
        source_type: 来源类型
        confidence_score: 置信度

    Returns:
        (merged_persona, field_results)

    放宽策略版核心改进：
    - ❌ 去掉保守策略：推断字段也写入persona表（只要confidence > 60）
    - ✅ 约束：只写persona表，不动profiles表
    - ✅ 约束：写入时携带置信度和来源信息
    """
    existing = deepcopy(existing or {})
    merged = deepcopy(existing)
    field_results: List[Dict[str, Any]] = []

    if source_type not in {"explicit", "strong_inference", "weak_inference", "profile_form", "explicit_confirmation"}:
        raise ValueError(f"Unsupported source_type: {source_type}")

    # ✅ 放宽策略：推断字段也写入（只要confidence > 60）
    # 原来：source_type in {"strong_inference", "weak_inference"} → 全部跳过
    # 现在：只有confidence < 60才跳过
    if source_type in {"strong_inference", "weak_inference"}:
        if confidence_score > 60:
            # ✅ 放宽策略：高置信度推断也写入persona表
            for field_name, new_value in patch.items():
                old_value = merged.get(field_name)
                action_type = "skip"
                applied = False
                note = ""

                if field_name in LIST_FIELDS:
                    new_items = items_from_csv(new_value)
                    candidate_value = csv_from_items(new_items)
                    if candidate_value != old_value:
                        merged[field_name] = candidate_value
                        action_type = "insert" if old_value in {None, ""} else "update"
                        applied = True
                        note = "inference_persisted_with_confidence"  # ✅ 放宽策略
                    else:
                        note = "no_change"
                else:
                    # 单值字段处理
                    if new_value != old_value:
                        merged[field_name] = new_value
                        action_type = "insert" if old_value in {None, ""} else "update"
                        applied = True
                        note = "inference_persisted_with_confidence"  # ✅ 放宽策略
                    else:
                        note = "no_change"

                field_results.append({
                    "field_name": field_name,
                    "old_value": old_value,
                    "new_value": new_value,
                    "stored_value": merged.get(field_name),
                    "action_type": action_type,
                    "applied_to_persona": applied,
                    "note": note,
                    "confidence_score": confidence_score,
                    "source_type": source_type,
                })
        else:
            # 极低置信度推断 → 跳过
            for field_name, new_value in patch.items():
                field_results.append({
                    "field_name": field_name,
                    "old_value": merged.get(field_name),
                    "new_value": new_value,
                    "stored_value": merged.get(field_name),
                    "action_type": "skip",
                    "applied_to_persona": False,
                    "note": "low_confidence_inference_skipped",  # ✅ 放宽策略
                    "confidence_score": confidence_score,
                    "source_type": source_type,
                })

        merged = sanitize_persona_summary_fields(merged)
        for item in field_results:
            item["stored_value"] = merged.get(item["field_name"])
        merged["updated_at"] = now_string()
        return merged, field_results

    # explicit、profile_form、explicit_confirmation 的处理保持不变（写入persona表）
    try:
        from match_domain.collected_profile import filter_explicit_patch
        patch = filter_explicit_patch(patch, source_type)
    except ImportError:
        pass

    for field_name, new_value in patch.items():
        old_value = merged.get(field_name)
        action_type = "skip"
        applied = False
        note = ""

        if field_name in LIST_FIELDS:
            new_items = items_from_csv(new_value)
            candidate_value = csv_from_items(new_items)
            if candidate_value != old_value:
                merged[field_name] = candidate_value
                action_type = "insert" if old_value in {None, ""} else "update"
                applied = True
                note = "explicit_persisted"
            else:
                note = "no_change"
        else:
            if new_value != old_value:
                merged[field_name] = new_value
                action_type = "insert" if old_value in {None, ""} else "update"
                applied = True
                note = "explicit_persisted"
            else:
                note = "no_change"

        field_results.append({
            "field_name": field_name,
            "old_value": old_value,
            "new_value": new_value,
            "stored_value": merged.get(field_name),
            "action_type": action_type,
            "applied_to_persona": applied,
            "note": note,
            "confidence_score": confidence_score,
            "source_type": source_type,
        })

    merged = sanitize_persona_summary_fields(merged)
    for item in field_results:
        item["stored_value"] = merged.get(item["field_name"])
    merged["updated_at"] = now_string()
    return merged, field_results
```

---

## 五、改进效果对比（放宽策略版）

### 改进前后对比

| 场景 | 改进前 | 改进后（放宽策略） |
|------|--------|------------------|
| 用户说："我想找比我大的女生" | ❌ 跳过（标记为strong_inference） | ✅ 写入persona表（标记为explicit） |
| 已知事实：age=28（来自profiles） | ❌ 跳过（标记为strong_inference） | ✅ 写入persona表（标记为known） |
| 推断：mbti=INFJ（confidence=65） | ❌ 跳过（保守策略） | ✅ 写入persona表（放宽策略，confidence > 60） |
| 低置信度推断（confidence=40） | ❌ 跳过 | ❌ 跳过（confidence < 60） |

### 预期效果（放宽策略版）

1. **明确表达的偏好能被记录**
   - 用户说："我想找比我大的女生" → 写入persona表 → 后续推荐利用这个偏好 ✅

2. **已知事实能被利用**
   - age=28、city=无锡 → 写入persona表 → 推荐系统可利用 ✅

3. **推断字段也能被利用（放宽策略）**
   - MBTI=INFJ（推断，confidence=65） → 写入persona表 → 推荐系统可利用 ✅
   - 这是放宽策略的核心改进！

4. **极低置信度推断仍然跳过**
   - confidence < 60 → 跳过 → 避免极低质量推断污染画像 ❌

### 画像覆盖率提升（放宽策略版）

| 字段类型 | 改进前覆盖率 | 改进后覆盖率 | 提升 |
|---------|-------------|-------------|------|
| 明确表达字段 | 0%（全部跳过） | 100%（写入） | ↑100% |
| 已知事实字段 | 0%（全部跳过） | 100%（写入） | ↑100% |
| 高置信度推断（>60） | 0%（全部跳过） | 100%（写入） | ↑100% |
| 低置信度推断（<60） | 0%（跳过） | 0%（跳过） | 不变 |

**预期覆盖率提升**：从0% → 约80%（confidence > 60的字段占比约80%）

---

## 六、风险评估（放宽策略版）

### 风险点（放宽策略版）

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM标注来源不准确 | 可能误判"推断"为"明确表达" | 增加置信度阈值验证（confidence > 60） |
| 推断字段质量不高 | 可能写入低质量推断 | 只写入confidence > 60的推断 |
| 放宽策略可能激进 | 可能污染画像 | 灰度发布，监控画像质量，可回滚 |
| Prompt复杂度增加 | LLM可能返回格式错误 | 兼容旧格式，增加格式验证 |

### 缓解措施（放宽策略版）

1. **置信度阈值控制**
   - ✅ 只写入confidence > 60的字段（包括推断）
   - ❌ confidence < 60的推断仍然跳过
   - 阈值可配置，可根据效果调整

2. **格式兼容**
   - 兼容LLM返回旧格式（字符串）
   - 增加格式验证和fallback

3. **日志详细**
   - 记录每个字段的来源、source_type、confidence、处理结果
   - 便于问题排查和策略调优

4. **灰度发布**
   - 先在测试环境验证
   - 灰度发布到部分用户（10% → 50% → 100%）
   - 监控画像质量和推荐效果
   - 可回滚（保留旧代码分支）

5. **核心约束严格执行**
   - ✅ 只写persona表（apply_scope="persona_only"硬编码）
   - ✅ 不动profiles表（sync_profile=False硬编码）
   - 这两个约束是硬约束，不能违反

---

## 七、测试验证方案（放宽策略版）

### 测试场景设计（放宽策略版）

```python
# 测试场景1：明确表达偏好（应写入persona表）
user_input = "我想找比我大的女生，温柔一点的"
expected_result = {
    "partner_expectation": {
        "value": "想找比自己大的女生、温柔",
        "source": "explicit",
        "confidence": 90,
        "applied": True,  # ✅ 应写入persona表
        "written_to": "persona_table"  # ✅ 只写persona表
    }
}

# 测试场景2：已知事实（应写入persona表）
user_profile = {"age": 28, "city": "无锡"}
expected_result = {
    "age": {
        "value": "28",
        "source": "known",
        "confidence": 100,
        "applied": True,  # ✅ 应写入persona表
        "written_to": "persona_table"  # ✅ 只写persona表
    },
    "city": {
        "value": "无锡",
        "source": "known",
        "confidence": 100,
        "applied": True,  # ✅ 应写入persona表
        "written_to": "persona_table"  # ✅ 只写persona表
    }
}

# 测试场景3：推断字段（confidence > 60，应写入persona表）
user_input = "我喜欢思考人生的意义，喜欢独处"
expected_result = {
    "mbti": {
        "value": "INFJ",
        "source": "inferred",
        "confidence": 65,  # confidence > 60
        "applied": True,  # ✅ 放宽策略：应写入persona表
        "written_to": "persona_table"  # ✅ 只写persona表
    }
}

# 测试场景4：低置信度推断（confidence < 60，应跳过）
user_input = "我觉得他可能是个好人"
expected_result = {
    "personality": {
        "value": "好人",
        "source": "inferred",
        "confidence": 40,  # confidence < 60
        "applied": False,  # ❌ 应跳过
        "note": "low_confidence_inference_skipped"
    }
}

# 测试场景5：验证核心约束
test_constraint = {
    "all_fields": {
        "written_to": "persona_table",  # ✅ 所有字段只写persona表
        "profiles_table": "unchanged",  # ❌ profiles表不变
        "sync_profile": False,  # ✅ 硬编码约束
        "apply_scope": "persona_only"  # ✅ 硬编码约束
    }
}
```

### 验证步骤

1. **单元测试**
   - 测试 `_build_summary_prompt()` 输出格式
   - 测试 `generate_structured_summary()` 解析逻辑
   - 测试 `split_by_quantifiability()` 分流逻辑
   - 测试 `save_quantifiable_to_persona_tables()` 写入逻辑

2. **集成测试**
   - 模拟完整会话流程
   - 验证画像写入结果
   - 检查日志输出

3. **效果验证**
   - 对比改进前后的画像字段覆盖率
   - 验证推荐质量是否提升
   - 监控推断字段是否误写入

---

## 八、实施计划（放宽策略版）

### Phase 1：最小改动（1-2天）

| 任务 | 文件 | 改动 | 约束 |
|------|------|------|------|
| 修改Prompt | session_end_processor.py:368 | 增加来源标注要求 | 无约束 |
| 修改解析逻辑 | session_end_processor.py:286 | 提取value、source、confidence | 无约束 |
| 修改分流逻辑 | session_end_processor.py:994 | 保留来源信息 | 无约束 |
| 修改写入逻辑 | session_end_processor.py:1080 | 放宽策略：confidence > 60写入persona表 | ✅ 只写persona表 |
| 修改画像策略 | persona_memory_lib.py:1130 | 放宽策略：推断字段也写入 | ✅ 只写persona表 |

**目标**：
- ✅ 明确表达、已知事实、高置信度推断都能写入persona表
- ✅ profiles表不动（硬约束）

### Phase 2：灰度发布与监控（3-5天）

| 任务 | 内容 |
|------|------|
| 测试环境验证 | 验证放宽策略效果，排查问题 |
| 灰度发布 | 先发布到10%用户，监控效果 |
| 监控指标 | 画像覆盖率、推荐质量、推断字段质量、profiles表是否被误写 |
| 调整阈值 | 根据效果调整confidence阈值（60 → 可调整） |
| 全量发布 | 根据灰度效果决定是否全量 |

---

## 九、总结（放宽策略版）

**核心改进**：

1. **LLM提炼增加来源标注** - 区分explicit、known、inferred和置信度
2. **分流判断保留来源信息** - 不丢失字段来源和置信度
3. **写入persona表放宽策略** - 推断字段也写入（confidence > 60）
4. **核心约束严格执行** - 只写persona表，不动profiles表

**预期效果**：

- ✅ 用户明确表达的偏好能被记录（提升推荐质量）
- ✅ 已知事实能被利用（提升画像覆盖率）
- ✅ 高置信度推断也能被利用（放宽策略，提升覆盖率约80%）
- ✅ profiles表不被误写（硬约束保护）

**风险控制**：

- 置信度阈值控制（confidence > 60才写入）
- 格式兼容（兼容LLM返回旧格式）
- 详细日志（便于问题排查）
- 灰度发布（降低风险，可回滚）
- 核心约束严格执行（只写persona表）

**三个核心约束**：

| 约束 | 实现 | 验证方式 |
|------|------|---------|
| ❌ 去掉保守策略 | confidence > 60就写入 | 测试推断字段是否写入 |
| ❌ profiles表不动 | `sync_profile=False`硬编码 | 验证profiles表是否变化 |
| ✅ 只动persona表 | `apply_scope="persona_only"`硬编码 | 验证只写persona表 |

---

## 十、附录：关键代码位置

| 功能 | 文件 | 行号 | 改动 | 约束 |
|------|------|------|------|------|
| LLM Prompt构造 | session_end_processor.py | 368 | 增加来源标注 | 无约束 |
| LLM返回解析 | session_end_processor.py | 286 | 提取来源信息 | 无约束 |
| 分流判断 | session_end_processor.py | 994 | 保留来源信息 | 无约束 |
| 画像写入 | session_end_processor.py | 1080 | 放宽策略：confidence > 60写入 | ✅ 只写persona表 |
| 画像策略 | persona_memory_lib.py | 1130 | 放宽策略：推断字段也写入 | ✅ 只写persona表 |

---

## 十一、核心约束验证清单

| 验证项 | 验证方式 | 预期结果 | 实际结果 |
|--------|---------|---------|---------|
| profiles表是否变化 | 查询profiles表记录 | 不变化 | 待验证 |
| persona表是否写入 | 查询persona表记录 | 写入成功 | 待验证 |
| 推断字段是否写入 | 查询confidence > 60的推断字段 | 写入persona表 | 待验证 |
| confidence < 60是否跳过 | 查询confidence < 60的推断字段 | 跳过 | 待验证 |
| apply_scope是否正确 | 查看日志apply_scope字段 | "persona_only" | 待验证 |
| sync_profile是否正确 | 查看日志sync_profile字段 | False | 待验证 |

---

## 十二、大白话总结

**一句话大白话解释**：

```
原来：无论用户明确说、已知事实还是推断，统统跳过，不写画像
现在：
- 用户明确说的 → 写入persona表 ✅
- 已知的事实 → 写入persona表 ✅
- 推断的（只要置信度>60） → 也写入persona表 ✅（放宽策略）
- 推断的（置信度<60） → 跳过 ❌

核心约束：
- profiles表不动（用户手动编辑的，不能动）❌
- 只写persona表（画像表，可以动）✅
```

**类比总结**：

```
相亲顾问记笔记：
- 用户明确说"我想找比我大的女生" → 记下来 ✅
- 用户资料上有"年龄28岁" → 记下来 ✅
- 从言谈推测"MBTI可能是INFJ，置信度65分" → 也记下来 ✅（放宽策略）
- 从言谈推测"性格好人，置信度40分" → 不记 ❌（太不确定）

但有一个硬约束：
- 用户自己填写的资料表（profiles表）不能改 ❌
- 只能记到自己的笔记本（persona表）✅
```