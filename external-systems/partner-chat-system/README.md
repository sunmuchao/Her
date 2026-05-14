# partner-chat-system

MySQL-backed chat threads and messages for match cases (`docs/chat-agent-architecture.md`).

- `PARTNER_CHAT_DB`: 默认 `mysql://root@127.0.0.1:3307/her_chat`
- `PARTNER_CHAT_TEST_DB`: 默认 `mysql://root@127.0.0.1:3307/her_chat_test`

Gateway REST:

- `/v1/chat/threads`
- `/v1/chat/threads/{thread_id}/messages`
- `/v1/chat/threads/{thread_id}/summary`
- `/v1/chat/threads/{thread_id}/reports`
- `/v1/chat/threads/{thread_id}/meeting-feedback`
- `/v1/chat/risk-cases`
- `/v1/chat/risk-signals`
- `/v1/timeline`
- `/v2/chat/cases/{case_id}/assistant-layout`
- `/v2/chat/cases/{case_id}/conversations`
- `/v2/chat/cases/{case_id}/timeline`
- `/v2/chat/conversations/{conversation_id}`
- `/v2/chat/conversations/{conversation_id}/messages`

当前保留能力：

- 匹配用户之间的基础聊天线程与消息
- 同一 `case_id` 下的多会话布局：`A-C`、`B-C`、`A-B-C`
- 线程摘要刷新
- 举报、自动风险信号、风险 case 审核
- 线下见面后的反馈回流
- persona memory 同步任务
- 基于 v2 会话消息触发的红娘 C session / task / maintenance 流水线
- 活体视频 challenge、补录工单、默认且唯一支持的 `local_oss` 机器预审 provider

活体视频本地开源模式：

- `HER_VERIFICATION_PROVIDER=local_oss`
- 这是默认值，不配环境变量时也会按 `local_oss` 跑
- 后端会保留前端 `MediaPipe` 动作挑战结果，并在服务端追加：
  - `Silent-Face-Anti-Spoofing`：防照片 / 防屏幕翻拍 / 防明显回放攻击
  - `YuNet + SFace`：把资料主图 / 相册图和活体视频关键帧做人脸同人比对，产出真正的 `face_match_score`
  - `faster-whisper`：直接从上传视频音轨转写 challenge 数字口令
- 首次运行会自动下载 `Silent-Face` 官方 `RetinaFace` 检测模型、两份 `MiniFASNet` 权重，以及 OpenCV `YuNet + SFace` 同人比对模型到 `tmp/verification_models/`
- `faster-whisper` 默认模型是 `tiny`，可通过 `HER_VERIFICATION_WHISPER_MODEL` 调整为 `base` 或 `small`
- 如果外网拉不动 HuggingFace，可直接把已转换好的 whisper 模型目录放到本机，再配 `HER_VERIFICATION_WHISPER_MODEL_DIR=/abs/path/to/model`
- 如果外网拉不动 OpenCV 同人比对模型，也可以手动准备包含 `face_detection_yunet_2023mar.onnx` 和 `face_recognition_sface_2021dec.onnx` 的目录，再配 `HER_VERIFICATION_FACE_MATCH_MODEL_DIR=/abs/path/to/model_dir`
- 当后端 whisper 临时不可用时，系统会保留 `Silent-Face` 结果，并优先沿用浏览器已识别出的数字口令，不再整条回退成 `analysis_unavailable`

红娘 C 运行所需环境变量：

- `OPENAI_API_KEY`: 供应商 key
- `OPENAI_BASE_URL`: OpenAI 兼容接口根地址，例如 `https://coding.dashscope.aliyuncs.com/v1`
- `HER_CHAT_AGENT_MODEL`: 例如 `glm-5`
- `HER_CHAT_AGENT_RUNTIME`: 默认 `agents_sdk`
- `HER_CHAT_AGENT_OPENAI_API`: 对兼容 `chat/completions` 的供应商填 `chat_completions`
- `HER_CHAT_AGENT_DISABLE_TRACING`: 第三方兼容接口建议设 `1`

最短联调方式：

1. 安装依赖：`pip install openai-agents`
2. 在仓库根目录准备 `.env`
3. 运行：
   `python external-systems/partner-chat-system/scripts/run_matchmaker_c_smoke.py --reset`

这个脚本会自动：

- 创建 `A-C`、`B-C`、`A-B-C` 三条会话
- 向 `main_group` 发一条用户消息
- 跑一次 maintenance
- 输出 session、task 和红娘回到 `assistant_dm_a` / `assistant_dm_b` 的消息结果

已移除：

- 历史侧信道
- 草稿采纳入口
- 主动提示 / coaching
- roleplay、延迟压测和相关脚本
