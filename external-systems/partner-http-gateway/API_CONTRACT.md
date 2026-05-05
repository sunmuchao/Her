# Partner HTTP Gateway — 客户端契约摘要

实现见 `gateway/app.py`。以下与运营排障、App 集成相关。

## 追踪（跨库案件 / 日志关联）

| 方向 | 说明 |
|------|------|
| **请求** | 可选头：`X-Trace-ID` 或 `X-Request-ID`（二者等价，取其一即可）。未传时服务端生成 UUID hex。 |
| **响应** | 所有响应带头 `X-Trace-ID`，与 `match_domain` 内 `set_trace_id` 一致，写入推荐动作等事件的 correlation。 |
| **结构化日志** | 每条请求结束后写一条 `her_kind=gateway_access` 的 pipeline 日志（含 `trace_id`、`client_ip`、`status_code`、`path`）。 |

## 鉴权与限流

| 环境变量 | 行为 |
|----------|------|
| `PARTNER_GATEWAY_API_KEY` | 若设置：除 `GET /health` 外需 `Authorization: Bearer <key>` 或 `X-API-Key: <key>`。 |
| `PARTNER_GATEWAY_RATE_LIMIT_PER_MINUTE` | 每客户端 IP 每分钟最大请求数（默认 `600`）；`0` 表示关闭限流。 |
| `PARTNER_GATEWAY_TRUST_X_FORWARDED_FOR` | 为 `1`/`true`/`yes` 时，客户端 IP 取自 `X-Forwarded-For` 第一段（需在反代后正确设置）。 |

## 幂等（推荐动作 / 审核）

适用于 **`POST /v1/recommendation/actions`**、**`POST /v1/recommendation/reviews`**。

- **HTTP 头**：`Idempotency-Key: <客户端唯一串>`（推荐，与 Stripe 等惯例一致）。  
- **JSON Body**（二选一）：`client_idempotency_key` 或 `idempotency_key`（与头同时存在时 **以头为准**）。  
- **语义**：同一 `recommendation_id` + 同一客户端键只执行一次写库；重复请求返回当前推荐行，并带 `idempotent_replay: true`。  
- **领域键**：事件内 `idempotency_key` 为 `match_domain.ids.idempotency_client_relation_action`（与仅时间桶的键区分）。  
- **响应**：成功体中含 `trace_id`；若提供了幂等键，另含 `client_idempotency_key`。

JSON-RPC：`recommendation.record_recommendation_action` / `record_user_review` 的 `params` 可含 `client_idempotency_key` 或 `idempotency_key`（无 HTTP 头时）。

## 已读回执（站内卡片）

- **`POST /v1/recommendation/cards/read`**  
  Body：`{ "requester_id": <int>, "card_ids": ["card-...", ...], "now": "<optional iso>" }`  
  行为：将对应行的 `card_status` 置为 `read`，并写 `read_at`。  
  响应：`{ "updated_count", "requester_id", "trace_id" }`。

- **JSON-RPC**：`recommendation.mark_in_app_cards_read`，`params` 同上字段。

## 连接池（可选）

| 环境变量 | 说明 |
|----------|------|
| `PARTNER_GATEWAY_DB_POOL_MAX` | 大于 `0` 时为推荐库、撮合库与 **聊天库** 各建一个固定上限连接池；默认 **`0`**（每请求新建连接，与旧行为一致）。 |

`GET /health` 返回体含 `db_connection_pool`、`api_key_required`、`rate_limit_per_minute`。

## 聊天（`/v1/chat`）

持久化库由 **`PARTNER_CHAT_DB`** 指定（默认 `mysql://root@127.0.0.1:3307/her_chat`）。设计见仓库根目录 **`docs/chat-agent-architecture.md`**。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/chat/threads` | Body：`case_id`、`relation_key`、`participant_a_id`、`participant_b_id`、可选 `metadata`、`now`。同一 `case_id` 幂等返回已有线程。 |
| `GET` | `/v1/chat/threads/{thread_id}` | Query：`requester_id`（须为参与者）。 |
| `GET` | `/v1/chat/threads/{thread_id}/messages` | Query：`requester_id`、可选 `limit`、`before_message_id`。 |
| `POST` | `/v1/chat/threads/{thread_id}/messages` | Body：`author_id`、`body`；可选 `visibility`（`dyadic` / `owner_only` / `system`）、`source`、`message_recipient_id`（`owner_only` 必填）、`reply_to_message_id`、`now`。幂等同推荐：`Idempotency-Key` 或 `client_idempotency_key`。 |
| `POST` | `/v1/chat/threads/{thread_id}/assistant/query` | Body：`user_id`、`query_text`、可选 `now`。侧信道写入用户问题与助手问题诊断/回复建议。 |
| `POST` | `/v1/chat/threads/{thread_id}/messages/adopt-draft` | Body：`draft_message_id`、`adopter_user_id`、必填 `body_override`、可选 `now`；幂等键同上。助手侧信道内容不能原样直发。 |

**JSON-RPC**：`chat.get_thread`、`chat.get_or_create_thread`、`chat.list_messages`、`chat.post_message`、`chat.assistant_query`、`chat.adopt_draft`（`params` 与上表字段一致；`chat.post_message` 可含 `client_idempotency_key`）。

**维护与投递（运营 / worker）**

- **`POST /v1/chat/maintenance/run`**  
  Body：可选 `persona_limit`（默认 `20`）、`flush_outbox`（`true`/`false`，未传则读环境变量 `HER_SCHED_CHAT_FLUSH_OUTBOX`）。  
  行为：可选将聊天库 `outbox_events` 中 `pending` 批置为 `published`（占位消费者）；并处理 `persona_sync_jobs` 中 `pending` 任务（未设置 `HER_CHAT_PERSONA_MYSQL_SOURCE` 时标记为 `needs_review`）。

- **JSON-RPC**：`chat.list_pending_outbox`（`limit`）、`chat.process_persona_jobs`（`limit`）、`chat.run_maintenance`（`persona_limit`、`flush_outbox`）。

## 统一时间线（跨聊天 + 撮合案例）

- **`GET /v1/timeline`**  
  Query：`case_id`、`viewer_id`（须为聊天参与者之一）、可选 `message_limit`。  
  响应：`chat`（`build_chat_timeline`：线程 + 对该 `viewer_id` 可见的消息）、`matchmaking`（若能用同一 `case_id` 在撮合库命中则含 `case` 与 `match_case_events`，否则为空列表）、`recommendation` 当前为 `null`（预留）。

- **JSON-RPC**：`timeline.get_for_case`，`params`：`case_id`、`viewer_id`、可选 `message_limit`。

## 摘要与助手

- **`GET /v1/chat/threads/{thread_id}/summary`**  
  Query：`requester_id`（参与者）。返回 `summary` 行（`chat_thread_summaries`）；未跑维护任务前可能为 `null`。

- **助手模型（可选）**：设置 **`OPENAI_API_KEY`** 后，`POST .../assistant/query` 基于最近 **双方可见** 消息生成中文问题诊断与回复建议，不提供可直接发送成稿。默认直连 OpenAI：`HER_CHAT_ASSISTANT_MODEL` 默认 `gpt-4o-mini`。  
  **OpenAI 兼容 API**（如阿里云百炼 Coding 版）：同时设置  
  `HER_CHAT_ASSISTANT_BASE_URL=https://coding.dashscope.aliyuncs.com/v1`、`HER_CHAT_ASSISTANT_MODEL=glm-5`（与控制台一致即可）。也可用通用名 **`OPENAI_BASE_URL`**。未设置 key 时仍为占位文案。

## Outbox 消费与环境变量

- 定时/维护任务在 **`HER_SCHED_CHAT_FLUSH_OUTBOX=1`** 时处理 outbox：默认 **`HER_SCHED_CHAT_OUTBOX_CONSUME=1`** 表示对每条 `pending` 打 **`her.pipeline` 漏斗** `chat / outbox_dispatched` 后再标记 `published`；设为 `0` 则仅批量标记已发布（无漏斗日志）。
- **`HER_CHAT_MAINTENANCE_SKIP_SUMMARY=1`**：维护任务跳过摘要刷新（减轻负载）。
