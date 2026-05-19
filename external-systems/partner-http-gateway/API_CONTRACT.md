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

## 搜索（`/v1/search`）

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/search/profiles` | Body：`source` 或 `sources`、可选 `criteria`、`self_profile`、`self_id`、`table_name`、`photos_table_name`、`limit`、`photo_preview_count`、`include_source`、`include_text`。`criteria` 支持 `verified_level_min`、`photo_verification_level_min`、`photo_verification_level`/`photo_verification_levels` 等可信度筛选项。响应直接返回 `partner-search` 结构化结果，包含 `verified_level`、`verified_label`、`photo_verification_level`、`photo_verification_label`、`verification_items`、`trust_summary`、`caution_items`、`trust_actions` 等可信度字段。 |

**JSON-RPC**：`search.search_profiles`，`params` 与上表一致。

## 发现页（`/v1/discovery`）

以下为当前仓库**已实现**的发现页 REST 契约摘要；网关入口以 `gateway/app.py` 为准，后端能力由 `external-systems/partner-discovery-system/` 提供。

发现页约束只有两条：
- 前端发送时只上传 `user_message` 或 `action_id`
- 前端展示时只渲染后端返回的 `view` 或 `detail_view`

前端不应上传 `intent`、`search_filters`、`should_search` 之类业务判断字段。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/discovery/sessions` | Body：`requester_id`、`profile_id`，可选 `now`。创建一个发现页 session，返回 `trace_id`、`session` 和首屏 `view`。 |
| `POST` | `/v1/discovery/sessions/{session_id}/turns` | Body 二选一：`user_message` 或 `action_id`，可选 `now`。提交一轮自然语言输入，或回传一个服务端生成的 `action_id`。返回新的 `trace_id`、`session`、`view`。 |
| `GET` | `/v1/discovery/sessions/{session_id}` | 返回当前 session 的完整 `view`，用于刷新恢复。前端不应自己重建消息、卡片或筛选状态。 |
| `GET` | `/v1/discovery/profiles/{profile_id}` | Query：可选 `session_id`。返回资料详情页专用 `detail_view`，不建议前端用列表卡片字段自行拼详情页。 |

发现页主接口成功返回统一结构：

```json
{
  "trace_id": "trace-3f1d9d7c",
  "session": {
    "session_id": "discovery-session-001",
    "status": "active",
    "phase": "collecting_preferences",
    "updated_at": "2026-05-14T14:30:00+08:00"
  },
  "view": {
    "timeline": [],
    "criteria_chips": [],
    "suggested_actions": [],
    "composer": {
      "placeholder": "告诉红娘你的偏好，她会替你整理并搜索。",
      "disabled": false
    }
  }
}
```

`session.phase` 建议先收敛为：
- `collecting_preferences`
- `searching`
- `results_shown`
- `no_result`

`view.timeline` 当前建议支持三类 item：
- `assistant_message`
- `user_message`
- `result_group`

`result_group.cards` 建议至少包含：
- `card_id`
- `profile_id`
- `title`
- `subtitle`
- `cover_image_url`
- `match_score`
- `trust_badges`
- `reason_summary`

`suggested_actions` 建议结构：

```json
[
  {
    "action_id": "act-002",
    "label": "只看无锡本地",
    "style": "secondary"
  }
]
```

说明：
- 前端只展示 `label`
- 前端点击后只回传 `action_id`
- 前端不理解该按钮背后的真实业务语义

### 创建 session 示例

请求：

```json
{
  "requester_id": 70001,
  "profile_id": 10001
}
```

响应：

```json
{
  "trace_id": "trace-7c22b8ea",
  "session": {
    "session_id": "discovery-session-001",
    "status": "active",
    "phase": "collecting_preferences",
    "updated_at": "2026-05-14T14:30:00+08:00"
  },
  "view": {
    "timeline": [
      {
        "item_type": "assistant_message",
        "item_id": "msg-a-001",
        "body": "先跟我说说你想找什么样的人，不用一次讲完整。"
      }
    ],
    "criteria_chips": [],
    "suggested_actions": [
      {
        "action_id": "act-open-001",
        "label": "先从城市和年龄说起",
        "style": "primary"
      }
    ],
    "composer": {
      "placeholder": "告诉红娘你的偏好，她会替你整理并搜索。",
      "disabled": false
    }
  }
}
```

### 提交一轮输入示例

自然语言请求：

```json
{
  "user_message": "我在无锡，想找认真恋爱、最好工作稳定一点的女生。"
}
```

按钮点击请求：

```json
{
  "action_id": "act-002"
}
```

禁止前端上传：

```json
{
  "intent": "refine_search",
  "filter_city": "无锡"
}
```

搜索结果响应示例：

```json
{
  "trace_id": "trace-d2a8290f",
  "session": {
    "session_id": "discovery-session-001",
    "status": "active",
    "phase": "results_shown",
    "updated_at": "2026-05-14T14:32:00+08:00"
  },
  "view": {
    "timeline": [
      {
        "item_type": "user_message",
        "item_id": "msg-u-003",
        "body": "我在无锡，想找认真恋爱、最好工作稳定一点的女生。"
      },
      {
        "item_type": "assistant_message",
        "item_id": "msg-a-003",
        "body": "我先按无锡、认真恋爱、工作稳定优先帮你缩一轮。"
      },
      {
        "item_type": "result_group",
        "item_id": "group-001",
        "title": "这一轮先给你看 3 位",
        "cards": [
          {
            "card_id": "candidate-1001",
            "profile_id": 1001,
            "title": "林知夏 29",
            "subtitle": "无锡 · 中学老师 · 硕士",
            "cover_image_url": "https://static.example.com/p/1001/cover.jpg",
            "match_score": 92,
            "trust_badges": ["真人照认证", "学历已核验"],
            "reason_summary": "目标一致、工作稳定、表达自然"
          }
        ]
      }
    ],
    "criteria_chips": [
      {"chip_id": "chip-city", "label": "无锡"},
      {"chip_id": "chip-goal", "label": "认真恋爱"},
      {"chip_id": "chip-prefer-1", "label": "工作稳定优先"}
    ],
    "suggested_actions": [
      {
        "action_id": "act-006",
        "label": "只看无锡本地",
        "style": "secondary"
      },
      {
        "action_id": "act-007",
        "label": "真人认证以上",
        "style": "secondary"
      }
    ],
    "composer": {
      "placeholder": "继续说你的要求，或点按钮让红娘继续筛",
      "disabled": false
    }
  }
}
```

### 资料详情页响应示例

```json
{
  "trace_id": "trace-f4380f20",
  "profile_id": 1001,
  "detail_view": {
    "hero": {
      "name": "林知夏",
      "age": 29,
      "city": "无锡",
      "headline": "中学老师 · 硕士 · 认真恋爱"
    },
    "photo_gallery": [
      {
        "image_url": "https://static.example.com/p/1001/1.jpg"
      }
    ],
    "verified_sections": [
      {
        "title": "已核验信息",
        "items": ["真人照认证", "学历已核验"]
      }
    ],
    "self_reported_sections": [
      {
        "title": "她的自我介绍",
        "items": ["平时作息规律，周末喜欢徒步和看展。"]
      }
    ],
    "caution_sections": [
      {
        "title": "你需要知道",
        "items": ["工作日回复可能偏晚。"]
      }
    ],
    "matchmaker_notes": [
      "和你这一轮条件的匹配点主要在生活稳定、城市一致、关系目标明确。"
    ]
  }
}
```

### 错误返回建议

```json
{
  "trace_id": "trace-err-001",
  "error_code": "DISCOVERY_ACTION_EXPIRED",
  "error_message": "action_id 已过期，请刷新当前发现页。",
  "retryable": true
}
```

建议预留这些错误码：
- `DISCOVERY_SESSION_NOT_FOUND`
- `DISCOVERY_SESSION_CLOSED`
- `DISCOVERY_INVALID_TURN_INPUT`
- `DISCOVERY_ACTION_NOT_FOUND`
- `DISCOVERY_ACTION_EXPIRED`
- `DISCOVERY_PROFILE_NOT_FOUND`
- `DISCOVERY_RENDER_FAILED`

**JSON-RPC**：暂未定义；建议 discovery system 和 `/v1/discovery/...` HTTP 契约先稳定后再补。

## 认证（`/v1/verifications`）

当前后端已支持三种活体认证接法：
- `上传自拍视频后做机器预审`
- `先领取实时动作 challenge，再由前端实时完成眨眼 / 张嘴 / 转头，最后连同视频证据一起提交`
- `开启本地开源 provider：MediaPipe 动作 + Silent-Face-Anti-Spoofing 防翻拍 + faster-whisper 语音口令`

服务端会把结果统一落到同一条认证单里，并自动分流为 `approved` / `under_review` / `resubmission_required`；人工复核通过后会回写资料 `photo_verification_level=live_video_verified`。当前机器预审只支持：
- `local_oss`：后端自己跑 `Silent-Face-Anti-Spoofing` 和 `faster-whisper`。

除直接提交活体视频外，当前还支持“照片风险补录任务”闭环：
- 风险审核命中照片类信号后，可先创建一条 `awaiting_submission` 的补录任务。
- 用户第一次补录时可直接带 `submission_id` 提交到这条任务上，而不是新建无关联认证单。
- 任务详情会附带 `photo_review_task`、`workflow_history`、`notifications`、`derived_status`，方便前端做补录中心与状态页。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/verifications/live-video-requests` | Body：`user_id`、可选 `profile_id`、`source_dsn`、`source_table_name`、`signal_codes`、`risk_case_id`、`request_reason`、`requested_by`、`due_at`、`metadata`、`now`。创建或刷新一条照片补录任务，返回统一的 `request` 对象，状态初始为 `awaiting_submission`。 |
| `GET` | `/v1/verifications/live-video-requests` | Query：可选 `user_id`、`status` / `statuses`、`profile_id`、`limit`。列出照片补录任务。 |
| `GET` | `/v1/verifications/live-video-requests/{submission_id}` | 返回单个照片补录任务详情；底层仍复用同一条活体认证单。 |
| `POST` | `/v1/verifications/live-video-challenges` | Body：`user_id`、可选 `profile_id`、`challenge_actions` / `required_actions`、`challenge_action_pool` / `allowed_actions`、`action_count`、`now`。如果传 `challenge_actions`，服务端会按这个固定顺序出题；如果只传 `challenge_action_pool`，服务端会从动作池里随机抽取并打乱顺序。返回 `challenge_token`、`required_actions`、`challenge_phrase`、`spoken_code`、`prompt_steps`、`expires_at`。前端拿到后应把整句 challenge 和当前步骤提示实时展示给用户。 |
| `POST` | `/v1/verifications/live-video-submissions` | Body：`user_id`、`video_base64`、`file_name`、可选 `submission_id`、`content_type`、`profile_id`、`source_dsn`、`source_table_name`、`challenge_token`、`challenge_phrase`、`metadata`、`now`。提交一次新的活体自拍视频认证。若带 `submission_id` 且该单当前为 `awaiting_submission`，则会把这次上传直接接到已有照片补录任务上。若带 `challenge_token`，则要求 `metadata.action_result` 一起提交，服务端会校验 challenge 是否过期、动作是否完成，再统一跑机器预审；返回的 `submission` 会直接带 `machine_review`、`recommended_decision`、`recommended_next_step`、`confidence_band`，状态可能直接变成 `approved` / `under_review` / `resubmission_required`。 |
| `GET` | `/v1/verifications/live-video-submissions` | Query：可选 `user_id`、`status` / `statuses`、`profile_id`、`limit`。列出活体自拍视频认证单及其素材 / 审核记录。 |
| `GET` | `/v1/verifications/live-video-submissions/{submission_id}` | 返回单个认证单详情，含素材列表、审核记录、机器预审结果、推荐下一步和最新同步状态。 |
| `POST` | `/v1/verifications/live-video-submissions/{submission_id}/resubmit` | Body：`user_id`、`video_base64`、`file_name`、可选 `content_type`、`challenge_token`、`challenge_phrase`、`metadata`、`now`。当审核要求补录时，用户重新上传视频；如果这次走实时动作 challenge，也可一并带上新的 `challenge_token` 和 `metadata.action_result`。服务端会再次跑机器预审，可能直接自动通过，也可能继续要求补录或转人工。 |
| `POST` | `/v1/verifications/live-video-submissions/{submission_id}/review` | Body：`reviewer_id`、`decision`（`approve` / `reject` / `request_resubmission`）、可选 `review_note`、`liveness_result`、`face_match_result`、`profile_consistency_result`、`metadata`、`now`。审核通过时会尝试把资料表回写为 `live_video_verified`。 |
| `GET` | `/v1/verifications/notifications` | Query：可选 `submission_id`、`user_id`、`type` / `types`、`limit`。列出活体认证 / 照片补录相关通知记录，例如 `photo_review_requested`、`photo_review_resubmission_required`、`photo_review_approved`。 |

`metadata.action_result` 建议结构：

```json
{
  "capture_mode": "realtime_challenge",
  "completed_actions": ["blink", "open_mouth", "turn_left"],
  "action_events": [
    {
      "action": "blink",
      "step_index": 1,
      "detected_at_ms": 720,
      "score": 96
    },
    {
      "action": "open_mouth",
      "step_index": 2,
      "detected_at_ms": 1510,
      "score": 92
    },
    {
      "action": "turn_left",
      "step_index": 3,
      "detected_at_ms": 2290,
      "score": 91
    }
  ],
  "action_scores": {
    "blink": 96,
    "open_mouth": 92,
    "turn_left": 91
  },
  "face_count_max": 1,
  "challenge_phrase_rendered": true,
  "spoken_prompt_rendered": true,
  "spoken_prompt_display_ms": 1800,
  "audio_recorded": true,
  "recording_started_at_ms": 0,
  "recording_duration_ms": 4200,
  "video_recorded": true
}
```

补充说明：
- `action_events` 必须按真实完成顺序提交，服务端会用它核对 challenge 顺序；顺序错了会直接拒绝。
- `challenge_phrase_rendered` 表示整句 challenge 文案已经被写进录制视频画面里。
- `spoken_prompt_rendered` / `spoken_prompt_display_ms` 用来标记随机数字口令是否也已经展示在视频中。

`metadata.speech_challenge_result` 建议结构：

```json
{
  "provider": "browser_speech_recognition",
  "transcript_text": "四七",
  "transcript_confidence": 91,
  "speech_started_at_ms": 2780,
  "speech_ended_at_ms": 3510,
  "audio_video_sync_score": 78
}
```

补充说明：
- 如果 challenge 带 `spoken_code`，后端会把 `speech_challenge_result` 和 challenge 里的随机数字做比对。
- 至少会校验：`有没有音频`、`有没有转写文本`、`转写数字是否命中本次 spoken_code`、`说话时间是否落在动作完成之后`。
- `audio_video_sync_score` 当前是可选字段，留给后续第三方语音/活体引擎或服务端音视频同步模型回填。
- 当 `HER_VERIFICATION_PROVIDER=local_oss` 时，`speech_challenge_result` 可以不传，后端会优先用 `faster-whisper` 直接转写上传的视频音轨，并覆盖浏览器侧的临时识别结果。

本地开源 provider 相关环境变量：

| 环境变量 | 说明 |
|------|------|
| `HER_VERIFICATION_PROVIDER=local_oss` | 默认值；开启后端本地开源活体链路。 |
| `HER_VERIFICATION_LOCAL_CACHE_DIR` | 本地模型缓存根目录；默认落到仓库 `tmp/verification_models/`。 |
| `HER_VERIFICATION_SILENT_FACE_DIR` | 可选，手动指定 `Silent-Face-Anti-Spoofing` 资源根目录；未配时后端会自动下载官方 `RetinaFace` 检测模型和两份 `MiniFASNet` 权重。 |
| `HER_VERIFICATION_FACE_MATCH_MODEL_DIR` | 可选，手动指定本地同人比对模型目录；目录内需包含 `face_detection_yunet_2023mar.onnx` 和 `face_recognition_sface_2021dec.onnx`。未配时后端会自动下载 OpenCV `YuNet + SFace` 模型。 |
| `HER_VERIFICATION_WHISPER_MODEL` | `faster-whisper` 模型名，默认 `tiny`。想要更稳可以改成 `base` 或 `small`。 |
| `HER_VERIFICATION_WHISPER_MODEL_DIR` | 可选，直接指定本地已转换好的 whisper 模型目录；配了以后后端只走本地目录，不再去 HuggingFace 拉模型。 |
| `HER_VERIFICATION_WHISPER_CACHE_DIR` | Whisper 模型缓存目录。 |
| `HER_VERIFICATION_LOCAL_SAMPLE_FRAMES` | Silent-Face 抽样帧数，默认 `7`。 |

**JSON-RPC**：`verification.request_live_video`、`verification.create_live_challenge`、`verification.submit_live_video`、`verification.list_photo_review_requests`、`verification.list_submissions`、`verification.get_submission`、`verification.list_notifications`、`verification.resubmit_live_video`、`verification.review_submission`。

## 用户自助中心（`/v1/user-center`）

把 `核验中心`、`申诉中心`、`风险记录`、`通知` 和轻量 FAQ 聚合成一个统一入口，方便前端一次性拉全量闭环数据。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v1/user-center/trust-hub` | Query：`user_id`，可选 `profile_id`、`limit`。返回 `summary`、`verification_center.items`、`appeal_center.items`、`risk_records.items`、`notifications`、`faqs`。其中 `verification_center` 会把照片补录、字段核验待提交项和历史补件状态一起聚合；`appeal_center` 会把聊天限制申诉、资料一致性申诉、字段驳回复核统一收敛。 |

**JSON-RPC**：`user.get_trust_hub`。

## 资料字段核验（`/v1/profile-verifications`）

用于 `education` / `job` / `income` 三类高决策字段的补件、审核、争议复核与到期重审。当前后端已支持：
- 字段级核验策略查询
- 材料提交、驳回重提、人工审核
- 证据类型 / 证据渠道结构化记录
- 核验有效期、下次复核时间、重审策略
- 争议复核重新打开审核流
- 到期批量失效，并把资料字段状态回写成 `expired`

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/v1/profile-verifications/policies` | 返回字段级核验策略，含 `accepted_documents`、`accepted_evidence_types`、`accepted_evidence_channels`、默认有效期、默认重审策略等。 |
| `POST` | `/v1/profile-verifications/submissions` | Body：`field_key`（`education` / `job` / `income`）、`profile_id`、`source_dsn`，可选 `source_table_name`、`subject_user_id`、`declared_value`、`required_documents`、`evidence`、`evidence_type`、`evidence_channel`、`now`。创建一条字段核验提交单，并把资料字段状态回写为 `pending`。 |
| `GET` | `/v1/profile-verifications/submissions` | Query：可选 `field_key`、`subject_user_id`、`profile_id`、`status` / `statuses`、`dispute_status` / `dispute_statuses`、`limit`。列出字段核验单。 |
| `GET` | `/v1/profile-verifications/submissions/{submission_id}` | 返回单个字段核验单详情，含证据、审核记录、争议状态、有效期与最近同步结果。 |
| `POST` | `/v1/profile-verifications/submissions/{submission_id}/resubmit` | Body：可选 `subject_user_id`、`declared_value`、`required_documents`、`evidence`、`evidence_type`、`evidence_channel`、`now`。适用于 `rejected` / `resubmission_required` / `expired` 状态的重新补件。 |
| `POST` | `/v1/profile-verifications/submissions/{submission_id}/dispute` | Body：`dispute_reason`，可选 `subject_user_id`、`evidence`、`now`。把当前字段核验单重新打开为争议复核状态，并把资料字段状态回写为 `disputed`。 |
| `POST` | `/v1/profile-verifications/submissions/{submission_id}/review` | Body：`reviewer_id`、`decision`（`approve` / `reject` / `request_resubmission`），可选 `review_note`、`approved_value`、`requested_documents`、`metadata`、`validity_days`、`next_review_days`、`reverify_strategy`、`now`。审核通过后会写回字段值 / `verified` 状态，并记录 `verification_expires_at`、`next_review_due_at`。 |
| `POST` | `/v1/profile-verifications/expire-due` | Body：可选 `limit`、`now`。批量扫描已过有效期的字段核验单，标记为 `expired`，并把资料字段状态回写为 `expired`。 |

**JSON-RPC**：`profile.get_field_verification_policies`、`profile.submit_field_verification`、`profile.list_field_verifications`、`profile.get_field_verification`、`profile.resubmit_field_verification`、`profile.dispute_field_verification`、`profile.review_field_verification`、`profile.expire_due_field_verifications`。

## 资料一致性复核（`/v1/profile-review`）

用于把资料里“收入 / 职业 / 城市 / 频繁改动”等不一致信号转成结构化风险 case，并联动搜索 / 推荐 / 聊天侧的谨慎提示和降曝光能力。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/profile-review/risk-cases/evaluate` | Body：`profile_id`、`source_dsn`，可选 `source_table_name`、`subject_user_id`、`now`。按当前规则评估资料是否存在明显不一致，必要时创建或更新 `risk_case`，并联动要求补核验或降曝光。 |
| `GET` | `/v1/profile-review/risk-cases` | Query：可选 `profile_id`、`subject_user_id`、`status` / `statuses`、`limit`。列出资料一致性复核 case。 |
| `GET` | `/v1/profile-review/risk-cases/{profile_review_case_id}` | 返回单个资料一致性 case 及其规则命中事件。 |
| `GET` | `/v1/profile-review/photo-risk/runs` | Query：可选 `profile_id`、`subject_user_id`、`profile_review_case_id`、`limit`。列出照片风控评分运行记录，包含本次总分、子分、风险标记、判定结果。 |
| `GET` | `/v1/profile-review/photo-risk/runs/{score_run_id}` | 返回单次照片风控评分详情，包含落库后的素材资产、特征快照、评分结果、判定结果、关联复核队列。 |
| `GET` | `/v1/profile-review/photo-risk/review-queue` | Query：可选 `queue_status` / `statuses`、`profile_id`、`subject_user_id`、`limit`。列出照片风控人工复核队列。 |
| `POST` | `/v1/profile-review/risk-cases/{profile_review_case_id}/review` | Body：`resolver_id`、`status`，可选 `applied_action`、`resolution_note`、`now`。用于人工确认资料不一致后的最终处置或恢复。 |
| `POST` | `/v1/profile-review/risk-cases/{profile_review_case_id}/appeals` | Body：`appellant_id`、`reason_text`，可选 `evidence`、`now`。当资料一致性 case 已触发 `limited_exposure` 时，用户可提交自助申诉，补充文字说明和证明材料。 |
| `GET` | `/v1/profile-review/appeals` | Query：可选 `profile_review_case_id`、`subject_user_id`、`status` / `statuses`、`limit`。列出资料一致性申诉单。 |
| `GET` | `/v1/profile-review/appeals/{appeal_id}` | 返回单个资料一致性申诉单详情。 |
| `POST` | `/v1/profile-review/appeals/{appeal_id}/review` | Body：`resolver_id`、`appeal_status`（`submitted` / `under_review` / `upheld` / `rejected`），可选 `resolution_note`、`now`。申诉成立时会自动把对应资料一致性 case 结案并恢复曝光状态。 |

`/v1/profile-review/risk-cases/evaluate` 的响应现在还会额外返回 `photo_risk_service`，里面带 `score_run_id`、`decision_id`、`review_queue_item_id` 以及对应详情，方便直接排查本次照片风控判定。

**JSON-RPC**：`profile.evaluate_risk_case`、`profile.list_risk_cases`、`profile.get_risk_case`、`profile.list_photo_risk_runs`、`profile.get_photo_risk_run`、`profile.list_photo_risk_review_queue`、`profile.review_risk_case`、`profile.submit_risk_case_appeal`、`profile.list_risk_case_appeals`、`profile.get_risk_case_appeal`、`profile.review_risk_case_appeal`。

## 聊天（`/v1/chat`）

持久化库由 **`PARTNER_CHAT_DB`** 指定（默认 `mysql://root@127.0.0.1:3307/her_chat`）。设计见仓库根目录 **`docs/chat-agent-architecture.md`**。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v1/chat/threads` | Body：`case_id`、`relation_key`、`participant_a_id`、`participant_b_id`、可选 `metadata`、`now`。同一 `case_id` 幂等返回已有线程。 |
| `GET` | `/v1/chat/threads/{thread_id}` | Query：`requester_id`（须为参与者）。 |
| `GET` | `/v1/chat/threads/{thread_id}/messages` | Query：`requester_id`、可选 `limit`、`before_message_id`。 |
| `POST` | `/v1/chat/threads/{thread_id}/messages` | Body：`author_id`、`body`；可选 `visibility`（`dyadic` / `owner_only` / `system`）、`source`、`message_recipient_id`（`owner_only` 必填）、`reply_to_message_id`、`metadata`、`now`。幂等同推荐：`Idempotency-Key` 或 `client_idempotency_key`。网关会自动把请求侧 `client_ip` / `user_agent` 写入 `metadata.risk_observation`，前端也可补充 `device_fingerprint`、`registration_path`、`contact_handles` 等深度反诈观察字段。 |
| `POST` | `/v1/chat/threads/{thread_id}/reports` | Body：`reporter_id`、`report_type`、可选 `reason_text`、`message_id`、`reported_user_id`、`evidence`、`now`。用户举报入口；系统也会对聊天消息自动命中第一版反诈关键词规则并生成 `system_rule` 举报。举报证据和消息元数据会自动沉淀到设备 / IP / 话术 / 联系方式图谱。 |
| `POST` | `/v1/chat/threads/{thread_id}/meeting-feedback` | Body：`reviewer_id`、可选 `counterpart_user_id`、`photo_match_status`、`profile_consistency_status`、`income_job_consistency_status`、`safety_concern_status`、`willing_video_status`、`willing_offline_status`、`notes`、`now`。见面后结构化回流；会自动生成 `photo_mismatch`、`income_mismatch`、`fraud` 等风险举报。 |
| `GET` | `/v1/chat/reports` | Query：可选 `thread_id`、`risk_case_id`、`reported_user_id`、`limit`。运营 / 审核查看举报明细。 |
| `GET` | `/v1/chat/meeting-feedback` | Query：可选 `thread_id`、`counterpart_user_id`、`reviewer_id`、`limit`。查看见面后结构化反馈记录。 |
| `GET` | `/v1/chat/risk-cases` | Query：可选 `status` / `statuses`、`subject_user_id`、`thread_id`、`limit`。返回最小审核后台可用的风险 case 列表。 |
| `GET` | `/v1/chat/risk-signals` | Query：可选 `thread_id`、`subject_user_id`、`signal_code`、`limit`。查看行为型 / 举报型风控信号明细（如重复开场、高频私聊、导流站外等）。 |
| `POST` | `/v1/chat/fraud-networks/observations` | Body：`subject_user_id`，可选 `source_dsn`、`source_table_name`、`profile_id`、`thread_id`、`case_id`、`risk_case_id`、`report_id`、`source_type`、`event_type`、`signal_codes`、`message_body`、`evidence`、`evaluate`、`now`。手工写入设备 / IP / 会话 / 联系方式 / 头像 / 话术模板等图谱观察。 |
| `POST` | `/v1/chat/fraud-networks/evaluate` | Body：`subject_user_id`，可选 `source_dsn`、`source_table_name`、`profile_id`、`propagate`、`now`。重算该账号的深度反诈网络分、关联账号和联动处置；命中高阈值时会自动写入全局 moderation。 |
| `GET` | `/v1/chat/fraud-networks` | Query：可选 `status` / `statuses`、`subject_user_id`、`minimum_score`、`limit`。列出深度反诈网络档案。 |
| `GET` | `/v1/chat/fraud-networks/{subject_user_id}` | 返回单个账号的图谱画像、关联账号边、当前 moderation 状态。 |
| `GET` | `/v1/chat/risk-cases/{risk_case_id}` | 返回单个风险 case、关联举报、申诉、moderation 状态，以及该主体对应的 `fraud_network` 图谱概览。 |
| `POST` | `/v1/chat/risk-cases/{risk_case_id}/review` | Body：`resolver_id`、`status`、可选 `applied_action`（`warn` / `require_verification` / `limit_chat` / `freeze`）、`resolution_note`、`now`。当 `status=action_applied` 时必须给 `applied_action`；`limit_chat` / `freeze` 会阻止该用户继续在该线程发送 dyadic 消息。 |
| `POST` | `/v1/chat/risk-cases/{risk_case_id}/appeals` | Body：`appellant_id`、`reason_text`，可选 `evidence`、`now`。用户对 `limit_chat` / `freeze` 等聊天风控动作发起申诉。 |
| `GET` | `/v1/chat/risk-appeals` | Query：可选 `risk_case_id`、`subject_user_id`、`status` / `statuses`、`limit`。列出聊天风控申诉单。 |
| `GET` | `/v1/chat/risk-appeals/{appeal_id}` | 返回单个聊天风控申诉单详情。 |
| `POST` | `/v1/chat/risk-appeals/{appeal_id}/review` | Body：`resolver_id`、`appeal_status`（`submitted` / `under_review` / `upheld` / `rejected`），可选 `resolution_note`、`now`。申诉成立时会自动恢复对应风险 case。 |
| `GET` | `/v1/chat/threads/{thread_id}/risk-overview` | Query：`requester_id`（参与者）。返回对方当前线程内的风险概览、命中的 signal codes、`fraud_network_profile` 与谨慎提示文案，供聊天页展示“不要转账 / 不要离开平台沟通”类提醒。 |

`/v1/chat/risk-dashboard/weekly` 现已同时汇总 `fraud_network_profile_count`、`high_risk_network_count`、`network_action_breakdown`，用于观察图谱反诈命中与处置分布。

**JSON-RPC**：`chat.get_thread`、`chat.get_or_create_thread`、`chat.list_messages`、`chat.post_message`、`chat.submit_member_report`、`chat.submit_meeting_feedback`、`chat.list_member_reports`、`chat.list_meeting_feedback`、`chat.list_risk_cases`、`chat.list_risk_signals`、`chat.record_fraud_network_observation`、`chat.evaluate_fraud_network`、`chat.list_fraud_networks`、`chat.get_fraud_network`、`chat.get_risk_case`、`chat.review_risk_case`、`chat.submit_risk_appeal`、`chat.list_risk_appeals`、`chat.get_risk_appeal`、`chat.review_risk_appeal`、`chat.get_thread_risk_overview`（`params` 与上表字段一致；`chat.post_message` 可含 `client_idempotency_key`）。 

## 多会话聊天 v2（`/v2/chat`）

用于 **A-C 私聊 / B-C 私聊 / A-B-C 主群聊** 模式。与旧 `/v1/chat/threads` 并存，不替换旧双人线程。

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/v2/chat/cases/{case_id}/assistant-layout` | Body：`relation_key`、`participant_a_id`、`participant_b_id`、`agent_id`、可选 `conversation_ids`（键：`main_group` / `assistant_dm_a` / `assistant_dm_b`）、`metadata`、`now`。幂等创建 3 条会话：`main_group`、`assistant_dm_a`、`assistant_dm_b`。 |
| `GET` | `/v2/chat/cases/{case_id}/conversations` | Query：`requester_id`。仅返回该请求者可见的会话及成员列表。 |
| `GET` | `/v2/chat/cases/{case_id}/timeline` | Query：`requester_id`、可选 `message_limit`。返回该请求者在该 case 下可见的所有会话，以及每条会话的近期消息。 |
| `GET` | `/v2/chat/conversations/{conversation_id}` | Query：`requester_id`。返回单条会话详情；若请求者无权查看则拒绝。 |
| `GET` | `/v2/chat/conversations/{conversation_id}/messages` | Query：`requester_id`、可选 `limit`、`before_message_id`。拉取该会话历史消息。 |
| `POST` | `/v2/chat/conversations/{conversation_id}/messages` | Body：`author_id`、`body`；可选 `source`（`user` / `agent` / `system`）、`reply_to_message_id`、`metadata`、`now`。幂等同旧聊天：`Idempotency-Key` 或 `client_idempotency_key`。 |

权限模型：

- `participant_a_id` 可见：`main_group`、`assistant_dm_a`
- `participant_b_id` 可见：`main_group`、`assistant_dm_b`
- `agent_id` 可见：3 条会话全部

**JSON-RPC**：`chat.create_assistant_layout`、`chat.get_conversation`、`chat.list_case_conversations`、`chat.get_case_conversation_timeline`、`chat.list_conversation_messages`、`chat.post_conversation_message`。

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

## 摘要

- **`GET /v1/chat/threads/{thread_id}/summary`**  
  Query：`requester_id`（参与者）。返回 `summary` 行（`chat_thread_summaries`）；未跑维护任务前可能为 `null`。

## Outbox 消费与环境变量

- 定时/维护任务在 **`HER_SCHED_CHAT_FLUSH_OUTBOX=1`** 时处理 outbox：默认 **`HER_SCHED_CHAT_OUTBOX_CONSUME=1`** 表示对每条 `pending` 打 **`her.pipeline` 漏斗** `chat / outbox_dispatched` 后再标记 `published`；设为 `0` 则仅批量标记已发布（无漏斗日志）。
- **`HER_CHAT_MAINTENANCE_SKIP_SUMMARY=1`**：维护任务跳过摘要刷新（减轻负载）。
