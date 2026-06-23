# 异步资源清理修复总结

## 问题描述

### 错误信息
```
2026-06-23 13:24:13,694 ERROR asyncio Task exception was never retrieved
future: <Task finished name='Task-3934' coro=<AsyncClient.aclose() done, defined at ...> 
exception=RuntimeError('Event loop is closed')>
```

### 错误堆栈
```
Traceback (most recent call last):
  File "/path/to/httpx/_client.py", line 1985, in aclose
    await self._transport.aclose()
  File "/path/to/httpx/_transports/default.py", line 406, in aclose
    await self._pool.aclose()
  File "/path/to/httpcore/_async/connection_pool.py", line 353, in aclose
    await self._close_connections(closing_connections)
  ...
  RuntimeError: Event loop is closed
```

## 根因分析（五问法）

```
问题现象: Task exception was never retrieved - RuntimeError('Event loop is closed')
├─ 为什么 1: AsyncClient.aclose() 在事件循环关闭后执行
│   → httpx 尝试在已关闭的事件循环中清理异步连接
├─ 为什么 2: 程序退出时,事件循环先关闭,然后 httpx 连接池清理任务才执行
│   → Task-3934 是 httpx 的异步清理任务
├─ 为什么 3: Milvus Lite 的 MilvusClient 没有在事件循环关闭前被正确清理
│   → VectorStoreLite.close() 只设置了 self._client = None,没有调用 MilvusClient.close()
├─ 为什么 4: MilvusClient.close() 方法存在,但代码中没有调用
│   → 代码注释中说"MilvusClient 没有 close() 方法",这是错误的假设
└─ 为什么 5: 【根本原因】VectorStoreLite.close() 实现错误,缺少对 MilvusClient.close() 的调用

根本对策: 在 VectorStoreLite.close() 中正确调用 MilvusClient.close()
```

## 修复内容

### 1. 修复 VectorStoreLite.close() 实现

**文件**: `match_domain/vector_store_lite.py`

**修复前**:
```python
def close(self) -> None:
    if self._client is not None:
        try:
            # MilvusClient 没有 close() 方法，但我们可以通过删除引用来触发清理
            # 实际的连接清理由 Milvus Lite 内部管理
            self._client = None
            _logger.info("MilvusClient 连接已关闭，资源已释放")
        except Exception as exc:
            _logger.warning(f"关闭 MilvusClient 连接失败: {exc}")
```

**修复后**:
```python
def close(self) -> None:
    if self._client is not None:
        try:
            # 【修复】正确调用 MilvusClient.close() 来清理 httpx 异步连接池
            # MilvusClient.close() 会清理内部的 gRPC 和 httpx 异步连接
            self._client.close()
            self._client = None
            _logger.info("MilvusClient 连接已正确关闭，httpx 异步连接池已清理")
        except Exception as exc:
            _logger.warning(f"关闭 MilvusClient 连接失败: {exc}")
            # 即使关闭失败，也要设置为 None，避免重复关闭
            self._client = None
```

**关键改进**:
- ✅ 正确调用 `MilvusClient.close()` 来清理 httpx 异步连接池
- ✅ 避免 httpx 在事件循环关闭后尝试清理连接的错误
- ✅ 更详细的日志记录，便于调试

### 2. 修复 process_pending_vectors.py 缺少清理逻辑

**文件**: `scripts/process_pending_vectors.py`

**修复前**: 缺少 try-finally 清理块

**修复后**: 添加了完整的资源清理逻辑
```python
embedding_service = EmbeddingService(model_name="text-embedding-v3")
vector_store = VectorStoreLite()

try:
    # ... 业务逻辑 ...
finally:
    # ⚠️ 重要：主动关闭连接，避免 "Task exception was never retrieved" 错误
    await embedding_service.aclose()
    vector_store.close()
```

## 已正确使用的地方（无需修复）

### 1. ai_merge_handler.py
- ✅ 所有使用 VectorStoreLite 的地方都有 try-finally
- ✅ 正确调用 `embedding_service.aclose()` 和 `vector_store.close()`

**示例**:
```python
embedding_service = EmbeddingService(model_name="text-embedding-v3")
vector_store = VectorStoreLite()

try:
    final_vector = await embedding_service.generate_embedding(new_text)
    result = vector_store.save_vector_with_version(...)
finally:
    await embedding_service.aclose()
    vector_store.close()
```

### 2. vector_filter.py
- ✅ 有完整的 try-finally 清理逻辑
- ✅ 正确调用清理方法

### 3. session_end_scheduler.py
- ✅ 有完整的 try-finally 清理逻辑
- ✅ 在定时任务循环中正确清理

### 4. generate_vectors_only.py
- ✅ 有完整的清理逻辑

## 验证测试

### 测试脚本
创建了 `scripts/test_async_cleanup.py` 来验证修复效果

### 测试结果
```
✅ 所有测试完成，没有出现 'Event loop is closed' 错误
```

**测试覆盖**:
1. ✅ 基本资源清理
2. ✅ 异常情况下的清理
3. ✅ 多次操作后的清理

## 其他使用 AsyncOpenAI 的地方（已有正确清理）

### 1. EmbeddingService (match_domain/embedding_service.py)
- ✅ 使用单例模式管理 AsyncOpenAI 客户端
- ✅ 提供 `aclose()` 方法
- ✅ 注册 atexit 钩子（但有改进空间）

### 2. Agents SDK (discovery_system/agent_runtime.py)
- ✅ 使用全局单例
- ✅ 提供 `cleanup_agents_sdk_client()` 方法
- ✅ 注册 atexit 钩子

### atexit 钩子的局限性
⚠️ 注意: atexit 钩子在事件循环关闭后执行，可能也会出现错误

**EmbeddingService 的实现**:
```python
def _sync_cleanup(self) -> None:
    if self._async_client is not None:
        try:
            # 创建新事件循环来运行异步清理
            loop = asyncio.new_event_loop()
            loop.run_until_complete(self._async_client.close())
            loop.close()
            self._async_client = None
            _logger.info("AsyncOpenAI 客户端已通过 atexit 自动关闭")
        except Exception as exc:
            _logger.warning(f"atexit 清理失败（可能事件循环已关闭）：{exc}")
```

**建议**:
- ✅ 主要依赖 try-finally 显式清理
- ⚠️ atexit 作为兜底，但可能失败
- ✅ 优先使用 `aclose()` 方法显式清理

## 最佳实践总结

### 1. 异步资源生命周期管理原则
- ✅ **在事件循环关闭前清理所有异步资源**
- ✅ 使用 try-finally 确保清理逻辑执行
- ✅ 正确调用清理方法（如 `client.close()`, `await client.aclose()`）

### 2. 使用模式
```python
# ✅ 正确模式
async_client = AsyncClient()
sync_client = SomeClient()

try:
    # 业务逻辑
    result = await async_client.do_something()
    sync_client.do_another()
finally:
    # 关键：在事件循环关闭前清理
    await async_client.aclose()
    sync_client.close()
```

### 3. 避免 atexit 的陷阱
- ⚠️ atexit 钩子在事件循环关闭后执行
- ⚠️ 无法可靠清理异步资源
- ✅ 使用 try-finally 作为主要清理机制
- ✅ atexit 作为辅助兜底

### 4. 单例模式的管理
- ✅ 全局单例需要提供清理方法
- ✅ 使用者负责在适当时机调用清理
- ⚠️ 不要依赖自动清理（如 atexit）

## 影响范围

### 修复的文件
1. ✅ `match_domain/vector_store_lite.py` - 核心修复
2. ✅ `scripts/process_pending_vectors.py` - 补充清理逻辑

### 受益的系统
1. ✅ 向量存储服务（VectorStoreLite）
2. ✅ Embedding 服务（EmbeddingService）
3. ✅ 会话结束处理器（使用 VectorStoreLite）
4. ✅ 向量筛选逻辑（vector_filter）
5. ✅ 所有使用异步 HTTP 客户端的代码

## 监控建议

### 1. 日志监控
监控以下日志关键词:
- ✅ `"Task exception was never retrieved"`
- ✅ `"Event loop is closed"`
- ✅ `"MilvusClient 连接已正确关闭"`
- ✅ `"AsyncOpenAI 客户端已关闭"`

### 2. 验证脚本
定期运行验证脚本:
```bash
python scripts/test_async_cleanup.py
```

### 3. CI/CD 检查
在 CI 流程中添加检查:
- ✅ 运行测试后检查日志，确保无 "Event loop is closed" 错误
- ✅ 运行异步清理测试脚本

## 参考资料

### 相关文档
- [Milvus Lite Documentation](https://milvus.io/docs/milvus_lite.md)
- [httpx AsyncClient Documentation](https://www.python-httpx.org/advanced/#closing-connections)
- [Python asyncio Event Loop Management](https://docs.python.org/3/library/asyncio-eventloop.html)

### 类似问题案例
- [GitHub Issue: httpx Event loop is closed](https://github.com/encode/httpx/issues/xxx)
- [StackOverflow: Task exception was never retrieved](https://stackoverflow.com/questions/xxx)

## 总结

### 核心问题
Milvus Lite 的 httpx 异步连接池没有在事件循环关闭前被正确清理

### 根本原因
VectorStoreLite.close() 缺少对 MilvusClient.close() 的调用

### 修复方案
正确调用 MilvusClient.close() 清理异步连接池

### 验证结果
✅ 所有测试通过，无 "Event loop is closed" 错误

### 最佳实践
**在事件循环关闭前清理所有异步资源，使用 try-finally 确保清理执行**