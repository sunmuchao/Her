# 发现页测评画像接入方案 - AI自主判断版

> **修订日期**: 2026-06-05
> **设计原则**: Agent Native - 不要替 AI 解释 INFP，直接把 INFP 给 AI
> **核心变化**: 删除硬编码评分公式，让 AI 自己判断适配性

---

## 一、核心设计原则

### 1.1 原始数据优先

```
❌ 错误做法：
代码写：焦虑+回避 = 0.2分（硬编码）
AI 只能：照着 0.2 分说"不太匹配"

✅ 正确做法：
代码给：用户焦虑=0.8，候选人回避=0.9（原始数据）
AI 自己：判断重要性，自己解释"这个组合可能不稳定"
```

### 1.2 AI 是决策大脑

```
代码职责：
├─ 搬运原始数据（从数据库读取）
├─ 标准化数据结构（字段名统一）
├─ 判断数据可用性（有还是没有）
└─ 不做适配性判断

AI 职责：
├─ 读取原始数据
├─ 自己判断适配性
├─ 自己决定重要性
├─ 自己生成解释
└─ 自己决定排序建议
```

---

## 二、简化后的数据结构

### 2.1 PersonalityTraitsContext（只含原始数据）

```python
@dataclass
class PersonalityTraitsContext:
    """原始测评数据（不含任何判断结论）"""
    
    # MBTI 原始数据
    mbti: Optional[dict] = None
    # {"type_code": "ESTJ", "scores": {"ei": 64.6, "sn": 50, ...}}
    
    # 依恋风格原始数据
    attachment: Optional[dict] = None
    # {"type_code": "secure", "anxiety": 25, "avoidance": 25}
    
    # 大五人格原始数据
    big_five: Optional[dict] = None
    # {"scores": {"openness": 37.5, "neuroticism": 55, ...}}
    
    # 价值观原始数据
    values: Optional[dict] = None
    # {"value_type": "成就驱动型", "top_values": ["财务自由", ...]}
    
    # 爱情三元原始数据
    sternberg: Optional[dict] = None
    # {"scores": {"intimacy": 25, "passion": 25, ...}}
    
    # 数据可用性（只判断有还是没有，不做重要性判断）
    availability: dict = field(default_factory=dict)
    # {"has_mbti": True, "has_attachment": True, ...}
    
    # ❌ 不包含：
    # - compatibility_score（适配分）
    # - matched_on（匹配原因）
    # - risk_flags（风险标记）
    # - 这些都由 AI 自己判断
```

---

## 三、改造点清单（简化版）

### 3.1 新增文件（只有一个）

| 文件 | 职责 |
|------|------|
| **personality_traits_reader.py** | 从数据库读取测评原始数据 |

```python
# personality_traits_reader.py

def load_traits_for_profile(source: str, profile_id: int) -> PersonalityTraitsContext:
    """
    只做数据搬运，不做适配判断
    
    职责：
    1. 从 user_personas 表读取 self_personality_traits_json
    2. 标准化字段名（统一格式）
    3. 判断数据是否存在（has_mbti=True/False）
    4. 返回原始数据
    
    不做：
    - 不计算适配分
    - 不生成匹配原因
    - 不判断重要性
    """
    # 读取原始 JSON
    persona_row = query_user_personas(source, profile_id)
    traits_json = persona_row.get("self_personality_traits_json")
    
    if not traits_json:
        return PersonalityTraitsContext()  # 空数据
    
    # 解析原始数据
    return PersonalityTraitsContext(
        mbti=traits_json.get("mbti"),           # 原始数据
        attachment=traits_json.get("attachment"), # 原始数据
        big_five=traits_json.get("big_five"),   # 原始数据
        values=traits_json.get("values"),       # 原始数据
        sternberg=traits_json.get("sternberg"), # 原始数据
        availability={
            "has_mbti": traits_json.get("mbti") is not None,
            "has_attachment": traits_json.get("attachment") is not None,
            "has_big_five": traits_json.get("big_five") is not None,
            "has_values": traits_json.get("values") is not None,
            "overall_completeness": _calc_completeness(traits_json),
        },
        meta={
            "profile_id": profile_id,
            "source": "user_personas.self_personality_traits_json",
        }
    )
```

### 3.2 修改文件

| 文件 | 改什么 |
|------|--------|
| **discovery_system/service_integrations.py** | 搜索结果注入 traits 原始数据 |
| **discovery_system/agent_runtime.py** | official_context 增加 personality_context |
| **discovery_system/view_models.py** | candidate_card 增加 personality 字段 |

---

## 四、AI 上下文注入

### 4.1 official_context 增加什么

```python
# 在 _build_runtime_prompt() 中注入

official_context["personality_context"] = {
    # 用户自己的测评数据（原始）
    "self_traits": {
        "mbti": {"type_code": "ESTJ", "scores": {...}},
        "attachment": {"anxiety": 25, "avoidance": 25},
        "values": {"top_values": ["财务自由", "社会地位"]},
    },
    
    # 数据可用性
    "self_availability": {
        "has_mbti": True,
        "has_attachment": True,
        "has_values": True,
    },
}
```

### 4.2 候选人数据增加什么

```python
# 在候选人搜索结果中注入

candidate["personality_traits"] = {
    # 候选人的测评数据（原始）
    "mbti": {"type_code": "ISFP", ...},      # 如果她做了测评
    "attachment": {"anxiety": 30, ...},      # 如果她做了测评
    "values": {"top_values": [...]},        # 如果她做了测评
    
    # 数据可用性
    "availability": {"has_mbti": True, ...},
}
```

---

## 五、AI Prompt 示例

### 5.1 AI 看到的数据

```json
{
  "official_context": {
    "requester_profile_snapshot": {...},
    "personality_context": {
      "self_traits": {
        "mbti": {"type_code": "ESTJ", "scores": {"ei": 64.6, "sn": 50, "tf": 75, "jp": 75}},
        "attachment": {"type_code": "secure", "anxiety": 25, "avoidance": 25},
        "big_five": {"scores": {"neuroticism": 55, "agreeableness": 60}},
        "values": {"value_type": "成就驱动型", "top_values": ["财务自由", "社会地位", "稳定关系"]}
      },
      "self_availability": {"has_mbti": true, "has_attachment": true, "has_big_five": true, "has_values": true}
    }
  },
  "candidates": [
    {
      "profile_id": 123,
      "name": "郑星涵",
      "age": 27,
      "city": "无锡",
      "personality_traits": {
        "mbti": {"type_code": "ISFP", "scores": {"ei": 17, "sn": 68, "tf": 40, "jp": 39}},
        "attachment": {"type_code": "secure", "anxiety": 30, "avoidance": 20},
        "values": {"top_values": ["财务自由", "家庭责任"]}
      },
      "availability": {"has_mbti": true, "has_attachment": true, "has_values": true}
    },
    {
      "profile_id": 456,
      "name": "张安萌",
      "age": 27,
      "city": "无锡",
      "personality_traits": null,  // 没做测评
      "availability": {"has_mbti": false, ...}
    }
  ]
}
```

### 5.2 AI 自己判断什么

```
AI 需要自己判断：

1. MBTI 判断：
   - 看到 ESTJ 和 ISFP 的原始分数
   - AI 自己判断："ESTJ 务实，ISFP 艺术感，可能互补但也可能节奏不一致"
   - AI 自己决定重要性："MBTI 是民间测评，仅供参考"

2. 依恋判断：
   - 看到 anxiety=25 和 anxiety=30
   - AI 自己判断："都是低焦虑，相处稳定"
   - AI 自己决定重要性："依恋风格影响相处节奏，比较重要"

3. 价值观判断：
   - 看到 ["财务自由", "社会地位"] 和 ["财务自由", "家庭责任"]
   - AI 自己判断："都看重财务自由，但其他价值观有差异"
   - AI 自己决定："价值观相似度中等"

4. 无测评候选人：
   - 看到 personality_traits = null
   - AI 自己判断："这个人没做测评，只能看资料推断"
   - AI 自己说："从资料看可能适合..."

最终输出：
AI 自己生成的解释，不是代码硬编码的模板
```

---

## 六、对比：方案一 vs 方案二

| 对比项 | 方案一（硬编码） | 方案二（AI 判断） |
|--------|-----------------|------------------|
| **评分公式** | 代码算分（焦虑+回避=0.2） | AI 自己判断重要性 |
| **匹配原因** | 代码生成模板 | AI 自己生成解释 |
| **风险标记** | 代码硬编码规则 | AI 自己判断风险 |
| **灵活性** | 固定规则，千篇一律 | AI 根据场景调整 |
| **科学依据** | 推断的数字（没论文依据） | AI 参考原始数据，不硬编码 |
| **出错处理** | 公式错了 AI 没法纠正 | AI 可以根据上下文调整 |

---

## 七、验证标准

方案二成功的标准：

1. ✅ AI 能看到测评原始数据（MBTI: ESTJ，依恋: anxiety=25）
2. ✅ AI 自己生成解释（不是代码模板）
3. ✅ 候选人无测评时，AI 能基于资料推断
4. ✅ 不同用户看到的解释不同（个性化）
5. ✅ 前端显示原始 MBTI 类型（不翻译）

---

## 八、一句话总结

**方案二：代码只搬运原始数据，让 AI 自己判断适配性、自己生成解释。**

核心变化：
- 删除硬编码评分公式
- 删除评分矩阵和权重表
- 只保留数据读取和标准化
- AI 自己决定重要性，自己生成解释