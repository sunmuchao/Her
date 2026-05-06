# partner-chat-system

MySQL-backed chat threads and messages for match cases (`docs/chat-agent-architecture.md`).

- **DSN**: `PARTNER_CHAT_DB` (default `mysql://root@127.0.0.1:3307/her_chat`).
- **Tests**: `PARTNER_CHAT_TEST_DB` (default `mysql://root@127.0.0.1:3307/her_chat_test`).

Gateway REST: `/v1/chat/...`, `/v1/timeline`, maintenance `POST /v1/chat/maintenance/run`; JSON-RPC `chat.*` and `timeline.get_for_case`.

当前已包含一条最小风控闭环：

- 用户可通过 `POST /v1/chat/threads/{thread_id}/reports` 提交举报。
- 系统会对 dyadic 消息自动命中第一版反诈关键词规则（如导流站外、投资、转账）并生成 `system_rule` 举报。
- 举报会聚合成 `chat_risk_cases`，运营可通过 `/v1/chat/risk-cases` 查看、审核，并通过 `review` 接口施加 `warn` / `limit_chat` / `freeze`。
- 当某个 case 被审核为 `limit_chat` 或 `freeze` 后，该用户会被阻止继续在该线程发送 dyadic 消息。

Env: `HER_CHAT_PERSONA_MYSQL_SOURCE` (persona jobs); `OPENAI_API_KEY`, `HER_CHAT_ASSISTANT_MODEL`, optional `HER_CHAT_ASSISTANT_FAST_MODEL`, `HER_CHAT_ASSISTANT_MAX_TOKENS`, `HER_CHAT_ASSISTANT_TIMEOUT_SEC`, optional `HER_CHAT_ASSISTANT_BASE_URL` or `OPENAI_BASE_URL` (DashScope 等兼容端点); `HER_ROLEPLAY_MODEL`, optional `HER_ROLEPLAY_FAST_MODEL`, `HER_ROLEPLAY_MESSAGE_MODEL`, `HER_ROLEPLAY_MESSAGE_MAX_TOKENS`, `HER_ROLEPLAY_EVAL_MODEL`, `HER_ROLEPLAY_TIMEOUT_SEC`; `HER_SCHED_CHAT_DB`, `HER_SCHED_CHAT_MAINTENANCE_SEC`, `HER_SCHED_CHAT_FLUSH_OUTBOX`, `HER_SCHED_CHAT_OUTBOX_CONSUME`, `HER_CHAT_MAINTENANCE_SKIP_SUMMARY`; **`HER_PROFILE_MYSQL_DSN`**（默认 `mysql://root@127.0.0.1:3307/her`）用于从 **`profiles`** 表加载完整画像扮演用户。

相关文档：

- 架构总览：[`docs/chat-agent-architecture.md`](../../docs/chat-agent-architecture.md)
- 助手评估与改造：[`docs/chat-assistant-improvement-plan.md`](../../docs/chat-assistant-improvement-plan.md)

## 双智能体角色扮演（救场式助手 + 人设自评）

在**真实** `chat_threads` 上跑两个「虚拟相亲用户」LLM，交替发 **dyadic** 消息。

- **默认 `--assistant-mode proactive`**：每轮发言前先走一层**规则快路径**，把场景分成 `repair / probe_lightly / hold / none` 四类。只有更像“双方都还想继续聊，但这轮卡在沟通上”时才会走 `repair`；若只是意愿不明确，只给 `probe_lightly` 低压试探；若对方明显低投入或碰到边界，则走 `hold`，不再把用户往讨好式救场上推。模糊情况再用**调度模型**只看「双方可见」记录做同样判断；需要时再调 **`assistant_query`** 给**即将开口的那一方**私下指出问题并给出建议。
- **`fixed_turns`**：兼容旧行为，`--assistant-on-turns 0,2` 指定回合先问助手。
- **`none`**：全程不调助手。
- **`--simulate-read-interaction-mode`**：仅离线 `roleplay` 实验使用。打开后，模拟回复生成器会额外读到当前 `interaction_mode`，用于验证“模式建议是否可执行”；这不是线上产品能力，更不代表系统会约束真实用户必须怎么回。

结束时由**同一套人设 system** 让双方 **第一人称** 自评 JSON：对这次聊天是否满意、对助手是否满意。

### 数据库画像 + 压力剧情（尬聊/冷场/边界/极端场景）

- **`--profile-a-id` / `--profile-b-id`**：从 **`profiles`**（`--profile-dsn`，默认 `her` 库）读整行，拼成扮演 brief；参与者 ID 为 `profile-<id>`。
- **`--stress`**：`auto`（有双画像时默认 **`rotate`** 轮播全部内置剧情）、`rotate`、`random`、`none`。每回合给**当前发言方**一条隐藏导演指令，覆盖冷场、尬聊、物质/隐私追问、前任雷区、过快热情、轻微冒犯、价值观试探等（见 `chat_system/scenario_stress.py`）。
- **`--list-stress-beats`**：打印全部 `beat_id`。**`--stress-beat-ids`**：只用子集。**`--rounds`** 建议 ≥ 剧情条数以便 `rotate` 扫全。

```bash
PYTHONPATH=../.. python scripts/run_dyadic_agent_roleplay.py \
  --profile-a-id 1 --profile-b-id 2 --profile-dsn 'mysql://root@127.0.0.1:3307/her' \
  --rounds 30 --stress rotate --assistant-mode proactive --output /tmp/roleplay_profiles.json
```

```bash
cd external-systems/partner-chat-system
PYTHONPATH=../.. python scripts/run_dyadic_agent_roleplay.py --rounds 6 --assistant-mode proactive --output /tmp/roleplay.json
# 无有效 API Key 时先跑通链路（内置占位 LLM + 助手占位建议）：
PYTHONPATH=../.. python scripts/run_dyadic_agent_roleplay.py --rounds 4 --assistant-mode proactive --local-demo --output /tmp/roleplay_demo.json
# 做 T9 对比实验时，可分别跑一组 off/on：
PYTHONPATH=../.. python scripts/run_dyadic_agent_roleplay.py --rounds 6 --assistant-mode proactive --output /tmp/roleplay_mode_off.json
PYTHONPATH=../.. python scripts/run_dyadic_agent_roleplay.py --rounds 6 --assistant-mode proactive --simulate-read-interaction-mode --output /tmp/roleplay_mode_on.json
```

- `--case-id`：省略则每次随机新 `case_id`。  
- `--resume-existing`：显式允许把新回合追加到同一个 `case_id` 的旧线程；默认会直接报错，避免实验串台。  
- `--base-time`：模拟消息时间戳起点，默认固定为 `2026-05-04T12:00:00`，也会写回输出 JSON。  
- 输出 JSON 额外包含 `roleplay_experiment.simulated_reply_reads_interaction_mode`、`turn_evaluations[].assistant_latency_ms`、`turn_evaluations[].message_generation_source`、`turn_evaluations[].mutual_intent_assessment`、`turn_evaluations[].interaction_mode`、`turn_evaluations[].simulated_reply_mode_prompted`、`turn_evaluations[].simulated_reply_mode_alignment`、`turn_evaluations[].recovery_score_1to3_turns`、`turn_evaluations[].graceful_exit_score`、`assistant_metrics.assistant_invoke_avg_ms`、`assistant_metrics.assistant_invoke_max_ms`、`assistant_metrics.heuristic_decision_turns`、`assistant_metrics.repair_intervention_turns`、`assistant_metrics.probe_intervention_turns`、`assistant_metrics.hold_decision_turns`、`assistant_metrics.overpush_risk_turns`、`assistant_metrics.simulated_reply_mode_alignment_rate`、`assistant_metrics.improved_recovery_rate`、`assistant_metrics.graceful_exit_rate`、`assistant_metrics.clarified_low_interest_rate`、`assistant_metrics.fallback_message_turns`、`assistant_metrics.llm_error_fallback_turns`、`assistant_metrics.graceful_exit_advice_turns`、`llm_stats`，便于排查“到底是调度慢、主回复慢，还是助手建议慢”，也能把“局部救回来一点”“该收住时有没有体面收住”“模拟回复是否按模式执行”拆开看。  
- 单测：`pytest tests/test_dyadic_roleplay.py`。

导出某次 roleplay 的**完整库内消息**（含双方可见 + 仅自己可见）：

```bash
PYTHONPATH=../.. python scripts/export_chat_thread.py --roleplay-json /tmp/her_roleplay_out.json -o /tmp/her_roleplay_transcript.md
PYTHONPATH=../.. python scripts/export_chat_thread.py --thread-id cht-xxxx --format json -o /tmp/messages.json
```
