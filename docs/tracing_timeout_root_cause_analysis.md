# OpenAI Agents SDK Tracing超时根因分析与修复方案

**生成时间**: 2026-06-23
**问题**: 发现页对话响应超时19秒失败

---

## 一、问题现象

```
16:11:53 - Tracing: request failed: timed out
16:11:53 - Tracing: max retries reached, giving up
16:12:02 - Error streaming response: Request timed out.
```

---

## 二、五问法根因分析

```
问题现象：Tracing系统请求超时，导致整个Agent流程失败
├─ 为什么 1: Tracing请求发送到错误的目标URL
│   → 检查：Tracing默认发送到 https://api.openai.com/v1/traces/ingest
├─ 为什么 2: 我们使用的是百炼API（阿里云），不是OpenAI API
│   → 检查：base_url配置为 https://dashscope.aliyuncs.com/compatible-mode/v1
├─ 为什么 3: Tracing系统独立配置，没有使用正确的base_url
│   → 检查：processors.py第34行硬编码OpenAI URL
├─ 为什么 4: Tracing向OpenAI发送请求但网络不通或API key无效
│   → 检查：没有OPENAI_API_KEY环境变量，只有百炼API key
└─ 为什么 5: 【根本原因】Tracing系统未适配非OpenAI的LLM服务提供商

根本对策：
1. 禁用Tracing（简单有效，不影响核心业务）
2. 配置Tracing使用正确的API endpoint（复杂，需要自定义exporter）
```

---

## 三、关键证据

### 证据 #1: Tracing默认发送到OpenAI

```python
# agents/tracing/processors.py 第34行
_OPENAI_TRACING_INGEST_ENDPOINT = "https://api.openai.com/v1/traces/ingest"
```

### 证据 #2: timeout配置60秒，但实际5秒连接超时

```python
# agents/tracing/processors.py 第79行
self._client = httpx.Client(timeout=httpx.Timeout(timeout=60, connect=5.0))
```

**说明**：
- 总timeout：60秒
- 连接timeout：5秒（连接到OpenAI API的超时）
- 连接5秒失败后，会重试3次（max_retries=3）
- 每次重试间隔1-30秒（base_delay=1.0, max_delay=30.0）

### 证据 #3: 我们使用百炼API，不是OpenAI

```python
# agent_runtime.py 第67行
_BAILIAN_RESPONSES_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

**冲突**：
- LLM调用：发送到百炼API（阿里云） ✅ 正常工作
- Tracing调用：发送到OpenAI API ❌ 网络不通，超时失败

---

## 四、为什么LLM调用成功，但Tracing失败？

**关键发现**：OpenAI Agents SDK有两个独立的HTTP客户端：

### 客户端 #1: LLM调用客户端（正常工作）

```python
# agent_runtime.py 第354-363行
client = AsyncOpenAI(
    base_url=base_url,  # ✅ 使用百炼API URL
    api_key=api_key,    # ✅ 使用百炼API key
    timeout=120.0,      # ✅ timeout 120秒
)
set_default_openai_client(client, use_for_tracing=False)  # ✅ 明确标记：不用于Tracing
```

**关键参数**：`use_for_tracing=False` - 明确标记这个客户端**不用于Tracing**

### 客户端 #2: Tracing专用客户端（失败）

```python
# agents/tracing/processors.py 第79行
self._client = httpx.Client(timeout=httpx.Timeout(timeout=60, connect=5.0))
# ❌ 独立的httpx客户端，硬编码发送到OpenAI URL
# ❌ 使用OPENAI_API_KEY环境变量（但我们没有设置）
# ❌ 连接不到OpenAI API，5秒后超时
```

**根本问题**：
- Tracing客户端是**独立创建的httpx.Client**，不受`set_default_openai_client()`影响
- Tracing客户端**硬编码发送到OpenAI URL**，不使用百炼API URL
- Tracing客户端**需要OPENAI_API_KEY**，但我们只有百炼API key

---

## 五、修复方案对比

### 方案1：禁用Tracing（推荐）

**优点**：
- ✅ 简单，半小时就能修复
- ✅ 立即生效，Agent能正常工作
- ✅ 不影响核心业务（Tracing只是辅助功能）

**缺点**：
- ❌ 没有Tracing日志，不利于监控和调试
- ❌ 无法追踪Agent的详细执行过程

**实施步骤**：
1. 确保环境变量设置：`HER_DISCOVERY_AGENT_DISABLE_TRACING=1`
2. 确保初始化时调用 `_ensure_agents_sdk_client_initialized()`
3. 验证Tracing确实被禁用（日志中不再出现Tracing相关警告）

---

### 方案2：适配Tracing到百炼API（复杂，不推荐）

**优点**：
- ✅ 保留Tracing功能，便于监控和调试
- ✅ 完整的执行过程追踪

**缺点**：
- ❌ 复杂，需要自定义TracingProcessor和Exporter
- ❌ 百炼API可能不支持 `/v1/traces/ingest` endpoint
- ❌ 需要大量测试验证
- ❌ 可能需要1-2天开发时间

**实施步骤**：
1. 自定义BackendSpanExporter，修改endpoint为百炼API URL
2. 或者实现自定义TracingProcessor，将trace数据保存到本地文件/数据库
3. 替换default_exporter
4. 测试验证Tracing能正常工作

---

## 六、为什么Tracing禁用没生效？

### 问题排查

```python
# agent_runtime.py 第374-381行
disable_tracing = env_first(
    "HER_DISCOVERY_AGENT_DISABLE_TRACING",
    default="1",
).lower()
if disable_tracing in ("1", "true", "yes"):
    set_tracing_disabled(True)
```

**理论上应该禁用**，但实际没生效，可能原因：

1. **初始化顺序问题**：
   - 可能Agent创建时Tracing已经启动
   - set_tracing_disabled()调用太晚

2. **环境变量未正确读取**：
   - env_first()函数可能有问题
   - 或者环境变量被其他值覆盖

3. **TracingProcessor已注册**：
   - 即使调用set_tracing_disabled(True)
   - 已注册的TracingProcessor仍然会工作

---

## 七、最终修复方案（组合方案）

### 立即修复（P0）：强制禁用Tracing

**做法**：在Agent Runtime初始化的最开始强制禁用

```python
# agent_runtime.py
# 在文件顶部，导入agents后立即禁用
from agents import set_tracing_disabled

# ✅ 强制禁用Tracing（不依赖环境变量）
set_tracing_disabled(True)
```

**为什么这样修复**：
- 不依赖环境变量读取
- 在所有初始化之前禁用
- 确保Tracing永远不会启动

---

### 后续优化（P1）：实现自定义TracingProcessor

**做法**：实现本地文件Tracing，不发送到远程API

```python
# 新增文件：discovery_system/local_tracing_processor.py

import json
import logging
from pathlib import Path
from agents.tracing import TracingProcessor, Span, Trace

_logger = logging.getLogger(__name__)

class LocalFileTracingProcessor(TracingProcessor):
    """将trace数据保存到本地文件，不发送到远程API"""

    def __init__(self, log_dir: str = "/tmp/discovery_traces"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def on_trace_start(self, trace: Trace) -> None:
        """trace开始时记录"""
        _logger.info(f"Trace started: {trace.trace_id}")

    def on_span_start(self, span: Span) -> None:
        """span开始时记录"""
        _logger.debug(f"Span started: {span.type} - {span.span_id}")

    def on_span_end(self, span: Span) -> None:
        """span结束时保存到文件"""
        trace_file = self.log_dir / f"{span.trace_id}.jsonl"
        span_data = {
            "trace_id": span.trace_id,
            "span_id": span.span_id,
            "type": span.type,
            "data": span.data,
            "timestamp": span.started_at,
        }
        with open(trace_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(span_data, ensure_ascii=False) + "\n")

    def on_trace_end(self, trace: Trace) -> None:
        """trace结束时记录"""
        _logger.info(f"Trace ended: {trace.trace_id}")

    def shutdown(self, timeout: float | None = None):
        """关闭processor"""
        _logger.info("LocalFileTracingProcessor shutdown")
```

**使用方式**：
```python
# agent_runtime.py
from .local_tracing_processor import LocalFileTracingProcessor
from agents import set_tracing_disabled, add_trace_processor

# 先禁用默认Tracing
set_tracing_disabled(True)

# 然后启用本地文件Tracing
add_trace_processor(LocalFileTracingProcessor())
```

**优点**：
- ✅ 保留Tracing功能
- ✅ 不发送到远程API，避免超时
- ✅ 本地文件便于调试和分析
- ✅ 实施成本低，半天就能完成

---

## 八、实施步骤（组合方案）

### Step 1: 立即禁用Tracing（半小时）

```python
# 修改 agent_runtime.py
# 在文件顶部导入后立即禁用

from agents import set_tracing_disabled
set_tracing_disabled(True)  # ✅ 强制禁用，不依赖环境变量
```

### Step 2: 测试验证（15分钟）

运行端到端测试，验证：
- Tracing警告消失
- Agent能正常工作
- 对话响应时间恢复正常（<5秒）

### Step 3: 实现本地Tracing（半天，可选）

如果需要保留Tracing功能：
- 实现 LocalFileTracingProcessor
- 注册自定义processor
- 测试验证本地文件trace正常

---

## 九、预期效果

| 指标 | 当前状态 | 修复后（禁用Tracing） | 修复后（本地Tracing） |
|------|---------|---------------------|---------------------|
| **响应时间** | 19秒超时失败 | 3-5秒正常响应 | 3-5秒正常响应 |
| **成功率** | 0% | 80-90% | 80-90% |
| **Tracing** | 超时失败 | 无Tracing | 本地文件记录 |
| **监控能力** | 无 | 基础日志 | 详细trace |

---

## 十、相关文档

- [[discovery_response_performance_analysis]] - 性能瓶颈分析
- [[agent-native-development-practices]] - Agent Native开发实践

---

## 结论

**根本原因**：OpenAI Agents SDK的Tracing系统硬编码发送到OpenAI API，但我们使用百炼API，导致Tracing请求失败并超时。

**修复优先级**：
- P0（立即）：强制禁用Tracing，半小时修复
- P1（后续）：实现本地文件Tracing，半天完成

**建议**：先用P0修复让系统能用，再考虑P1优化保留Tracing功能。