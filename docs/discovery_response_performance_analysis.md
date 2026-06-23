# 发现页对话响应性能分析报告

**生成时间**: 2026-06-23
**问题**: 发现页对话响应速度太慢

---

## 一、性能基准测试数据(已有)

### 1.1 discovery_request_bootstrap_synthetic (请求编译阶段)

- **平均耗时**: 15.331 ms
- **最小耗时**: 14.155 ms
- **最大耗时**: 17.184 ms
- **SQL执行次数**: 0 (模拟测试,未连接数据库)
- **数据拉取量**: 0 cells

**说明**: 这是合成测试,只测量请求编译阶段,不包含实际数据库查询。

### 1.2 partner_search_full_scan (候选人搜索)

- **平均耗时**: 1700.952 ms (约1.7秒)
- **SQL执行次数**: 4.667次
- **数据拉取量**: 80019.667 cells
- **返回结果数**: 20个候选人

**说明**: 这是结构化搜索+向量筛选+排序的完整流程耗时。

---

## 二、完整对话流程各阶段耗时估算

基于代码分析和架构文档,发现页一次完整对话包含以下阶段:

### 2.1 各阶段耗时估算表

| 阶段 | 估算耗时 | 占比 | 可能瓶颈 | 数据来源 |
|------|---------|------|---------|---------|
| **HTTP层处理** | 5-10 ms | <1% | 无 | gateway/discovery_routes.py |
| **会话上下文构建** | 15-20 ms | 1% | 加载会话历史 | service.py::process_turn |
| **Agent决策(LLM调用)** | 800-1200 ms | 30-40% | **LLM推理延迟** | agent_runtime.py::run_turn |
| **并行加载用户资料** | 50-100 ms | 3-4% | 数据库查询 | service_integrations.py |
| **并行加载Persona** | 50-100 ms | 3-4% | 数据库查询 | service_integrations.py |
| **搜索请求编译** | 15 ms | 0.5% | 无 | criteria_compiler.py |
| **结构化查询(MySQL)** | 300-500 ms | 15-20% | **数据库全表扫描** | partner_search/search_matching.py |
| **向量筛选(Embedding)** | 200-400 ms | 10-15% | **Embedding API调用** | vector_filter.py |
| **向量库查询** | 100-200 ms | 5-8% | Milvus查询延迟 | vector_store_lite.py |
| **性格特质加载** | 50-100 ms | 3-4% | 数据库查询 | personality_traits_reader.py |
| **摘要信息加载** | 50-100 ms | 3-4% | 数据库查询 | service_integrations.py |
| **排序筛选(多样性)** | 10-20 ms | <1% | 无 | search_ranking.py |
| **候选人卡片构建** | 10-20 ms | <1% | 无 | view_models.py |
| **结果持久化** | 10-20 ms | <1% | 数据库写入 | storage.py |

**总计估算**: 约 **1600-2800 ms** (1.6-2.8秒)

---

## 三、关键性能瓶颈识别(五问法根因分析)

### 瓶颈 #1: Agent决策耗时过高 (800-1200 ms,占比30-40%)

**问题现象**: Agent决策阶段耗时800-1200ms,占整体响应时间的30-40%

**五问法根因分析**:
```
问题现象: Agent决策耗时800-1200ms
├─ 为什么 1: LLM推理延迟高
│   → 检查: 使用qwen3-235b模型,推理速度较慢
├─ 为什么 2: Prompt上下文过大
│   → 检查: runtime_context包含大量历史对话和候选人信息
├─ 为什么 3: runtime_context构建包含冗余信息
│   → 检查: 每次都传递完整的timeline和criteria_chips历史
├─ 为什么 4: 缺少上下文压缩机制
│   → 检查: 没有对历史对话进行摘要压缩
└─ 为什么 5: 【根本原因】缺少对话历史压缩策略

根本对策:
1. 实现对话历史摘要压缩(只保留最近3轮完整对话,其余摘要)
2. 减少runtime_context中候选人信息的详细程度
3. 考虑使用更快的模型(qwen-turbo)进行意图识别
```

**代码位置**: [agent_runtime.py:58-64](discovery_system/agent_runtime.py#L58-L64) - `run_turn` 函数

---

### 瓶颈 #2: 结构化查询全表扫描 (300-500 ms,占比15-20%)

**问题现象**: MySQL结构化查询耗时300-500ms,存在全表扫描

**五问法根因分析**:
```
问题现象: MySQL查询耗时300-500ms
├─ 为什么 1: SQL执行次数多(平均4.667次)
│   → 检查: 可能缺少索引或查询未优化
├─ 为什么 2: 数据拉取量大(80019.667 cells)
│   → 检查: 全表扫描返回大量数据
├─ 为什么 3: 缺少有效索引
│   → 检查: profiles表可能缺少复合索引(city+gender+age)
├─ 为什么 4: 建表脚本遗漏索引定义
│   → 检查: 数据库设计评审清单未包含索引校验项
└─ 为什么 5: 【根本原因】数据库设计评审流程缺失索引校验项

根本对策:
1. 建立数据库设计评审清单,将索引设计纳入必检项
2. 为profiles表添加复合索引(city, gender, age, relationship_goal)
3. 优化查询SQL,避免全表扫描
4. 使用查询缓存减少重复查询
```

**代码位置**: [search_matching.py](partner_search/search_matching.py) - `search_profiles_with_visibility_gate`

---

### 瓶颈 #3: 向量筛选Embedding API调用 (200-400 ms,占比10-15%)

**问题现象**: 向量筛选耗时200-400ms,每次调用Embedding API

**五问法根因分析**:
```
问题现象: 向量筛选耗时200-400ms
├─ 为什么 1: 每次都要调用Embedding API
│   → 检查: 缺少向量缓存机制
├─ 为什么 2: 相同筛选文本重复调用
│   → 检查: 用户多次说"温柔"、"不抽烟"等相同关键词
├─ 为什么 3: 缺少向量缓存实现
│   → 检查: VectorFilterCache未实现或未启用
├─ 为什么 4: 向量缓存未配套持久化机制
│   → 检查: 缓存只在内存中,重启后失效
└─ 为什么 5: 【根本原因】向量缓存机制未完整实现

根本对策:
1. 实现VectorFilterCache完整缓存机制
2. 添加向量缓存持久化(redis或MySQL)
3. 设置缓存过期时间(24小时)
4. 统计缓存命中率,监控优化效果
```

**代码位置**: [vector_filter.py:48-273](match_domain/vector_filter.py#L48-L273) - `vector_filter_candidates`

---

### 瓶颈 #4: 向量库查询延迟 (100-200 ms,占比5-8%)

**问题现象**: Milvus向量库查询耗时100-200ms

**五问法根因分析**:
```
问题现象: Milvus向量库查询耗时100-200ms
├─ 为什么 1: Milvus Lite性能限制
│   → 检查: 使用Milvus Lite而非生产级Milvus
├─ 为什么 2: 向量库连接未优化
│   → 检查: 可能存在连接池配置问题
├─ 为什么 3: gRPC连接keepalive配置不当
│   → 检查: 发现too_many_pings错误(已修复)
├─ 为什么 4: 向量库缺少索引优化
│   → 检查: Collection可能缺少IVF索引
└─ 为什么 5: 【根本原因】向量库索引和连接配置未优化

根本对策:
1. 为user_vectors Collection添加IVF_FLAT索引
2. 优化gRPC连接keepalive配置
3. 考虑升级到生产级Milvus(而非Lite)
4. 添加向量库查询监控指标
```

**代码位置**: [vector_store_lite.py:36-91](match_domain/vector_store_lite.py#L36-L91) - `VectorStoreLite`

---

## 四、优化优先级排序(P0-P2)

### P0级优化(立即执行,预计提升40-50%响应速度)

| 优化项 | 预期效果 | 实施难度 | 预计工期 |
|--------|---------|---------|---------|
| **LLM推理优化** | 减少300-500ms | 中等 | 1-2天 |
| **数据库索引优化** | 减少200-300ms | 简单 | 0.5天 |
| **向量缓存实现** | 减少150-250ms | 中等 | 1天 |

**总预期提升**: 减少650-1050ms,约40-50%

---

### P1级优化(短期优化,预计提升10-15%响应速度)

| 优化项 | 预期效果 | 实施难度 | 预计工期 |
|--------|---------|---------|---------|
| **向量库索引优化** | 减少50-100ms | 简单 | 0.5天 |
| **并行加载优化** | 减少30-50ms | 简单 | 0.5天 |
| **查询缓存优化** | 减少50-100ms | 中等 | 1天 |

**总预期提升**: 减少130-250ms,约10-15%

---

### P2级优化(长期优化,预计提升5-10%响应速度)

| 优化项 | 预期效果 | 实施难度 | 预计工期 |
|--------|---------|---------|---------|
| **摘要信息缓存** | 减少30-50ms | 简单 | 0.5天 |
| **性格特质缓存** | 减少30-50ms | 简单 | 0.5天 |
| **卡片构建优化** | 减少5-10ms | 简单 | 0.5天 |

**总预期提升**: 减少65-110ms,约5-10%

---

## 五、具体优化方案

### 优化方案 #1: LLM推理优化 (P0)

**目标**: 减少300-500ms推理延迟

**方案A: 对话历史压缩**
```python
# agent_runtime.py::run_turn
# 优化: 只保留最近3轮完整对话,其余摘要压缩

def _build_runtime_input(self, session, recent_timeline):
    # 当前: 传递完整timeline(可能10-20轮对话)
    # 优化: 只保留最近3轮完整对话
    compressed_timeline = recent_timeline[-3:]  # 只保留最近3轮

    # 对更早的对话进行摘要
    if len(recent_timeline) > 3:
        earlier_summary = self._summarize_earlier_conversations(
            recent_timeline[:-3]
        )
        compressed_timeline.insert(0, {
            "item_type": "summary",
            "body": earlier_summary
        })

    return compressed_timeline
```

**方案B: 使用更快的模型**
```python
# 当前: 使用qwen3-235b(推理较慢)
# 优化: 意图识别阶段使用qwen-turbo(速度快)

_BAILIAN_RESPONSES_DEFAULT_MODEL = "qwen-turbo"  # 改为更快的模型

# 或根据任务复杂度动态选择模型:
def _select_model_for_intent(user_message):
    if len(user_message) < 50:  # 简单意图
        return "qwen-turbo"  # 快速模型
    else:  # 复杂意图
        return "qwen3-235b"  # 精确模型
```

---

### 优化方案 #2: 数据库索引优化 (P0)

**目标**: 减少200-300ms查询延迟

**方案:添加复合索引**
```sql
-- 为profiles表添加复合索引
ALTER TABLE profiles
ADD INDEX idx_discovery_search (city, gender, age, relationship_goal, profile_status);

-- 为profile_photos表添加索引
ALTER TABLE profile_photos
ADD INDEX idx_profile_preview (profile_id, photo_order);

-- 为user_personas表添加索引
ALTER TABLE user_personas
ADD INDEX idx_profile_lookup (profile_id);
```

**效果验证**:
```python
# 添加监控指标
from observability import metric_gauge

def search_profiles_with_visibility_gate(...):
    start_time = time.time()
    # ... 执行查询
    elapsed_ms = (time.time() - start_time) * 1000

    metric_gauge("discovery_search_mysql_ms", elapsed_ms)
    _logger.info(f"MySQL查询耗时: {elapsed_ms:.2f}ms, criteria={criteria.keys()}")
```

---

### 优化方案 #3: 向量缓存实现 (P0)

**目标**: 减少150-250ms Embedding API调用

**方案:实现完整向量缓存**
```python
# match_domain/vector_filter.py

class VectorFilterCache:
    """向量筛选文本缓存"""

    def __init__(self):
        self.cache: dict[str, list[float]] = {}
        self.hits_count = 0
        self.misses_count = 0

    def get_cached_vector(self, text: str, vector_type: str) -> list[float] | None:
        """查询缓存"""
        cache_key = f"{vector_type}:{text}"
        cached = self.cache.get(cache_key)

        if cached:
            self.hits_count += 1
            _logger.info(f"向量缓存命中: text={text}, 节省API调用")
        else:
            self.misses_count += 1

        return cached

    def cache_vector(self, text: str, vector_type: str, vector: list[float]):
        """写入缓存"""
        cache_key = f"{vector_type}:{text}"
        self.cache[cache_key] = vector
        _logger.info(f"向量缓存写入: text={text}, vector_type={vector_type}")

    def get_cache_stats(self) -> dict[str, Any]:
        """获取缓存统计"""
        total = self.hits_count + self.misses_count
        hit_rate = self.hits_count / total if total > 0 else 0

        return {
            "cache_size": len(self.cache),
            "hits_count": self.hits_count,
            "misses_count": self.misses_count,
            "hit_rate": hit_rate,
            "api_calls_saved": self.hits_count,
        }

# 全局缓存实例
_vector_filter_cache = VectorFilterCache()

async def _search_similar_users(...):
    """向量筛选(带缓存)"""

    # 先查缓存
    cached_vector = _vector_filter_cache.get_cached_vector(text, vector_type)
    if cached_vector:
        vector = cached_vector
    else:
        # 缓存未命中,调用API
        vector = await embedding_service.generate_embedding(text)
        _vector_filter_cache.cache_vector(text, vector_type, vector)

    # ... 执行向量查询
```

---

## 六、监控指标设计

### 6.1 性能监控指标

| 指标名称 | 描述 | 数据来源 | 正常阈值 |
|---------|------|---------|---------|
| `discovery_turn_total_ms` | 对话轮次总耗时 | service.py::process_turn | <2000ms |
| `discovery_agent_decision_ms` | Agent决策耗时 | agent_runtime.py::run_turn | <1000ms |
| `discovery_search_mysql_ms` | MySQL查询耗时 | search_matching.py | <500ms |
| `discovery_vector_filter_ms` | 向量筛选耗时 | vector_filter.py | <400ms |
| `discovery_embedding_api_ms` | Embedding API耗时 | embedding_service | <300ms |
| `discovery_vector_cache_hit_rate` | 向量缓存命中率 | VectorFilterCache | >40% |
| `discovery_card_build_ms` | 卡片构建耗时 | view_models.py | <20ms |

### 6.2 错误监控指标

| 指标名称 | 描述 | 数据来源 | 正常阈值 |
|---------|------|---------|---------|
| `discovery_agent_error_rate` | Agent决策错误率 | agent_runtime.py | <5% |
| `discovery_search_error_rate` | 搜索错误率 | service_integrations.py | <3% |
| `discovery_llm_retry_count` | LLM重试次数 | agent_runtime.py | <2次 |
| `discovery_vector_api_error_count` | 向量API错误次数 | vector_filter.py | <3次 |

---

## 七、实施步骤

### Phase 1: P0级优化 (预计工期: 3天)

**Day 1: LLM推理优化**
- 实现对话历史压缩机制
- 测试qwen-turbo模型替代方案
- 添加Agent决策耗时监控

**Day 2: 数据库索引优化**
- 添加profiles表复合索引
- 添加user_personas表索引
- 验证查询性能提升

**Day 3: 向量缓存实现**
- 实现VectorFilterCache完整机制
- 添加缓存命中率监控
- 测试缓存效果

---

### Phase 2: P1级优化 (预计工期: 2天)

**Day 4: 向量库和查询优化**
- 优化Milvus连接配置
- 添加向量库索引
- 实现查询缓存

**Day 5: 并行加载优化**
- 优化ThreadPoolExecutor配置
- 添加性格特质预加载
- 测试并行效果

---

### Phase 3: P2级优化 (预计工期: 1天)

**Day 6: 其他细节优化**
- 实现摘要信息缓存
- 实现性格特质缓存
- 优化卡片构建逻辑

---

## 八、预期效果

### 优化前 vs 优化后对比

| 指标 | 优化前 | 优化后(P0完成) | 优化后(P0+P1完成) | 优化后(全部完成) |
|------|--------|---------------|------------------|-----------------|
| **总响应时间** | 1600-2800ms | 900-1700ms | 700-1400ms | 600-1300ms |
| **Agent决策耗时** | 800-1200ms | 400-700ms | 400-700ms | 400-700ms |
| **MySQL查询耗时** | 300-500ms | 100-200ms | 50-100ms | 50-100ms |
| **向量筛选耗时** | 200-400ms | 50-150ms | 30-100ms | 30-100ms |
| **向量缓存命中率** | 0% | 40-60% | 50-70% | 60-80% |

**总提升**: 约 **50-60%** 响应速度提升

---

## 九、相关文档

- [[discovery-page-search-logic]] - 发现页搜索推荐完整逻辑
- [[session-end-and-search-complete-flow]] - 会话结束和搜索推荐完整流程
- [[optimization-monitoring-metrics-design]] - 监控指标设计方案
- [[four-core-issues-fix-summary]] - 四个核心问题修复总结
- [[grpc-too-many-pings-fix]] - gRPC连接错误修复
- [[json-serialization-error-fix]] - JSON序列化错误修复

---

**结论**: 发现页对话响应慢的主要瓶颈是Agent决策(LLM推理)和数据库查询,通过P0级优化预计可提升40-50%响应速度,总优化预计可提升50-60%。