# Her 重试策略（Outbox + Async Jobs）

本文档统一描述异步出站（outbox）与异步任务（async_jobs）的重试语义，便于运维与告警对齐。

## 1. Outbox（推荐 / 撮合 / 聊天）

实现：`match_domain/outbox_runtime.py`  
各子系统通过环境变量前缀覆盖默认值。

| 参数 | 默认 | 环境变量后缀 |
|------|------|----------------|
| 首次重试延迟 | 60s | `_RETRY_DELAY_SECONDS` |
| 退避倍数 | 2 | `_RETRY_BACKOFF_MULTIPLIER` |
| 最大延迟 | 600s | `_RETRY_MAX_DELAY_SECONDS` |
| 最大尝试次数 | 3 | `_MAX_ATTEMPTS` |
| 认领超时 | 300s | `_CLAIM_TIMEOUT_SECONDS` |
| 批大小 | 200 | `_BATCH_LIMIT` |

**前缀**：

- `HER_CHAT_OUTBOX`
- `HER_RECOMMENDATION_OUTBOX`
- `HER_MATCHMAKING_OUTBOX`

**延迟公式**：

```
delay = min(base_delay × multiplier^attempts, max_delay)
```

状态流转：`pending` → `processing` → `published` | `retry_pending` → … → `failed`（超过 max_attempts）。

**运维 CLI**：

```bash
python external-systems/partner-chat-system/scripts/manage_chat_outbox.py summary
python external-systems/partner-recommendation-system/scripts/manage_recommendation_outbox.py consume --limit 50
```

## 2. Async Jobs

实现：`async_jobs/queue.py`

| 参数 | 默认 | 可配置 |
|------|------|--------|
| 首次重试延迟 | 15s | 代码 `run_async_job_worker` 参数 |
| 退避倍数 | 2 | 同上 |
| 最大延迟 | 300s | 同上 |
| 最大尝试次数 | 3 | 每 handler `max_attempts` |
| 认领超时 | 300s | 同上 |

**延迟公式**：

```
delay = min(base_delay × multiplier^(attempt_count - 1), max_delay)
```

## 3. 告警阈值（Outbox）

`observability/outbox_health.py` 在消费循环后评估 `summarize_outbox()`：

| 信号 | 默认阈值 env | 含义 |
|------|----------------|------|
| `{system}.outbox_backlog` | `HER_ALERT_{SYSTEM}_OUTBOX_BACKLOG` = 50 | pending + retry_due |
| `{system}.outbox_failed_depth` | `HER_ALERT_{SYSTEM}_OUTBOX_FAILED` = 10 | failed 行数 |
| `{system}.outbox_processing_stale` | `HER_ALERT_{SYSTEM}_OUTBOX_PROCESSING_STALE` = 5 | 超时 processing |

`SYSTEM` ∈ `CHAT`, `RECOMMENDATION`, `MATCHMAKING`。

另有 dispatch 失败即时告警：`{system}.outbox_dispatch_failed`（`outbox_runtime.consume_outbox_batch`）。

## 4. Async Job 告警

`observability/health.py` → `emit_async_job_gauges()`：

| 信号 | 默认阈值 |
|------|----------|
| `{system}.async_job_backlog` | `HER_ALERT_{SYSTEM}_ASYNC_JOB_BACKLOG` = 20 |
| `{system}.async_job_failed_depth` | `HER_ALERT_{SYSTEM}_ASYNC_JOB_FAILED` = 5 |
| `{system}.async_job_processing_overdue` | `HER_ALERT_{SYSTEM}_ASYNC_JOB_PROCESSING_OVERDUE` = 1 |

## 5. 生产建议

1. Outbox 与 async job 告警接入日志采集（`her.pipeline` JSON，`her_kind=alert`）。
2. 聊天 outbox 间隔保持 ≤ 撮合/推荐（`HER_SCHED_CHAT_OUTBOX_SEC=15`）。
3. 不要在生产调大 `MAX_ATTEMPTS` 掩盖业务 bug；优先修 handler + 死信人工 requeue。
