# 第 2 部分场景验证矩阵（货不对板 / 信任焦虑）

本文档只验证 [planning-her-debrief.md](archive/planning-her-debrief.md) 第 2 部分里**已经实现**的能力，不把还没做完的前端、审核后台和真人核验流程混进来。

这份矩阵要回答的问题只有一个：

- 当前系统，是否已经做到 `风险可见、可提示、可筛掉一部分、可拦住一部分`？

不回答这些问题：

- 是否已经彻底解决照骗
- 是否已经真正核实收入 / 职业 / 学历真实性
- 是否已经具备完整的人工审核、申诉和运营闭环

---

## 1. 验证范围

本轮只覆盖以下已落地能力：

- 搜索 / 推荐的字段级可信度展示
- 搜索侧可信度门槛筛选
- 推荐侧可信度文案与谨慎提示
- 聊天期明显诈骗话术识别
- 用户举报进入风险案件
- 风险审核动作阻断继续聊天
- 见面后“货不对板”结构化回流
- 误伤边界控制
- 多对象重复开场 / 高频私聊等第一版行为信号

---

## 2. 判定口径

- `通过`
  - 功能链路成立，返回结果与预期动作一致。
- `部分通过`
  - 主链路成立，但提示不完整，或只能在域层 / 接口层验证，用户侧还看不到完整闭环。
- `不通过`
  - 关键动作没触发，或触发方向明显错误。

---

## 3. 用例总览

| ID | 能力点 | 核心问题 | 当前自动化证据 |
|---|---|---|---|
| T01 | 可信度分层展示 | 系统会不会把“自填资料”和“已核验资料”明确区分开 | 已自动化 |
| T02 | 提高可信度门槛筛人 | 用户能不能把只会上传普通照片 / 低认证资料的人先筛掉 | 已自动化 |
| T03 | 推荐侧谨慎提示 | 推荐里会不会把低可信资料包装成“看起来都差不多” | 已自动化 |
| T04 | 明显诈骗话术识别 | 投资 / 转账 / 导流站外能不能自动命中 | 已自动化 |
| T05 | 风险审核动作生效 | 审核后能不能真的限制继续发言 | 已自动化 |
| T06 | 误伤边界 | 正常“投资研究”“AA 车费”会不会被误判成诈骗 | 已自动化 |
| T07 | 见面后货不对板回流 | 照片不符 / 资料不符 / 收入夸大会不会自动沉淀成风险 | 已自动化 |
| T08 | 资料水分优先补认证 | 资料水分会不会走 `require_verification`，而不是直接按诈骗冻结 | 已自动化 |
| T09 | 行为型风控信号 | 多对象重复开场 / 高频私聊能不能形成结构化信号 | 已自动化（域层） |

---

## 4. 详细用例

## T01 可信度分层展示

- `目标能力`
  - 搜索结果里明确区分字段级可信度，而不是只给一个总徽章。
- `场景`
  - 一个候选人完成线下核验，另一个候选人主要靠自填资料包装。
- `验证步骤`
  - 调用 `/v1/search/profiles` 拉取两位候选人。
- `期望结果`
  - 高可信候选人返回 `verified_level`、`photo_verification_level`、`verification_items`、`trust_summary`。
  - 低可信候选人会出现 `资料填写为主`、`待复核`、`risk_flags`、`caution_items`。
  - 系统不输出抽象“可信 82 分”这类黑盒总分。
- `自动化证据`
  - [test_realistic_user_flows.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py)
    - `test_realistic_search_and_recommendation_surface_trust_differences`

## T02 提高可信度门槛筛人

- `目标能力`
  - 用户能通过更高认证门槛，把低可信资料前置筛掉。
- `场景`
  - 搜索时要求至少 `photo` 认证，或至少 `live_video_verified` 的照片核验等级。
- `验证步骤`
  - 调用 `/v1/search/profiles`，分别传入 `verified_level_min=photo` 和 `photo_verification_level_min=live_video_verified`。
- `期望结果`
  - 只保留高可信候选人。
  - 只上传普通照片、主要靠自填资料的候选人被筛掉。
- `自动化证据`
  - [test_realistic_user_flows.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py)
    - `test_realistic_search_can_raise_trust_thresholds_to_filter_packaged_profiles`

## T03 推荐侧谨慎提示

- `目标能力`
  - 推荐系统不把低可信资料伪装成“看起来都差不多”。
- `场景`
  - 同一批候选人进入推荐卡片。
- `验证步骤`
  - 创建推荐订阅、刷新、派发，再查看 `/v1/recommendation/cards`。
- `期望结果`
  - 高可信卡片出现 `线下核验`、`可信度：已线下核验`。
  - 低可信卡片出现 `普通上传照片`、`谨慎点：`、`资料填写为主`。
- `自动化证据`
  - [test_realistic_user_flows.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py)
    - `test_realistic_search_and_recommendation_surface_trust_differences`

## T04 明显诈骗话术识别

- `目标能力`
  - 投资 / 转账 / 导流站外等明显风险，在聊天刚开始就能自动命中。
- `场景`
  - 对方发出“先加微信，我带你投资，转账后进群”。
- `验证步骤`
  - 创建线程，发送高风险消息，再查询 `/v1/chat/reports`、`/v1/chat/risk-cases`、`/v1/chat/risk-signals`。
- `期望结果`
  - 自动生成 `system_rule` 举报。
  - 命中 `investment`、`money_transfer`、`off_platform` 信号。
  - 风险案件严重度为 `high`，建议动作为 `limit_chat`。
- `自动化证据`
  - [test_realistic_user_flows.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py)
    - `test_realistic_scam_flow_can_be_reported_reviewed_and_blocked`

## T05 风险审核动作生效

- `目标能力`
  - 风险案件不是只“记下来”，而是能真正阻断继续伤害。
- `场景`
  - 审核员确认高风险诈骗话术后，对案件施加 `limit_chat`。
- `验证步骤`
  - 调用 `/v1/chat/risk-cases/{id}/review` 应用 `limit_chat`，再尝试继续发 dyadic 消息。
- `期望结果`
  - 案件状态变成 `action_applied`。
  - 被限制方再次发私聊消息时被拒绝。
- `自动化证据`
  - [test_realistic_user_flows.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py)
    - `test_realistic_scam_flow_can_be_reported_reviewed_and_blocked`

## T06 误伤边界

- `目标能力`
  - 正常聊天语境不会因为包含敏感词就被误判。
- `场景`
  - 用户说“我在券商做投资研究”“这顿饭 AA 就行，车费我自己来”。
- `验证步骤`
  - 创建线程后发送两条边界消息，再查询 `/v1/chat/reports` 和 `/v1/chat/risk-cases`。
- `期望结果`
  - 不生成举报。
  - 不生成风险案件。
- `自动化证据`
  - [test_realistic_user_flows.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py)
    - `test_realistic_benign_boundary_messages_do_not_trigger_false_positive`

## T07 见面后货不对板回流

- `目标能力`
  - 见面后“照片修太重 / 资料有隐瞒 / 收入职业夸大”能进入结构化风险链路。
- `场景`
  - 见面后用户反馈：照片差异大、资料隐藏、收入职业夸大、长期拒绝视频。
- `验证步骤`
  - 调用 `/v1/chat/threads/{thread_id}/meeting-feedback`，再查询 `/v1/chat/meeting-feedback`、`/v1/chat/reports`、`/v1/chat/threads/{thread_id}/risk-overview`。
- `期望结果`
  - 自动生成 `photo_mismatch`、`profile_mismatch`、`income_mismatch`、`video_refusal`。
  - 风险概览提示 `资料一致性风险` 和 `回避视频`。
- `自动化证据`
  - [test_realistic_user_flows.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py)
    - `test_realistic_meeting_feedback_turns_mismatch_into_verification_followup`

## T08 资料水分优先补认证

- `目标能力`
  - 资料不符类问题优先走“补认证 / 复核”，而不是跟诈骗风险混为一类。
- `场景`
  - 用户反馈收入和职业存在明显夸大。
- `验证步骤`
  - 通过见面后反馈或直接举报提交 `income_mismatch`，查看风险案件建议动作。
- `期望结果`
  - 建议动作是 `require_verification`。
  - 不直接升级成诈骗冻结动作。
- `自动化证据`
  - [test_realistic_user_flows.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway/gateway_tests/test_realistic_user_flows.py)
    - `test_realistic_meeting_feedback_turns_mismatch_into_verification_followup`
  - [test_chat_system.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/tests/test_chat_system.py)
    - `test_income_mismatch_can_recommend_require_verification`

## T09 行为型风控信号

- `目标能力`
  - 第一版行为型规则能识别“多对象重复开场 + 高频私聊”。
- `场景`
  - 同一账号在多个线程里重复发“你好呀，我们加微信聊更方便”。
- `验证步骤`
  - 连续创建多个线程并重复发送同类开场，再查询 `reports` 和 `risk_signals`。
- `期望结果`
  - 生成 `off_platform`、`repeated_opening`、`high_frequency_outreach` 等信号。
- `自动化证据`
  - [test_chat_system.py](/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system/tests/test_chat_system.py)
    - `test_behavior_signal_records_repeated_opening_and_high_frequency_outreach`

---

## 5. 当前不纳入本轮验收的内容

这些能力在第 2 部分被明确标为“还没真正完成”，不应混入本轮通过标准：

- 真正的活体自拍视频上传、审核与补件流程
- 自动识别过度修图、换脸、盗图、同人照片
- 学历 / 职业 / 收入区间的硬核验闭环
- 全局推荐降曝光、全局聊天冻结、跨场景统一处置
- 审核后台页面、申诉入口、误伤回查看板
- 正式前端页面里的详情页、聊天页、举报页完整交互
- 线上 A/B、误伤率、漏报率、真实行为变化验证

---

## 6. 一句话验收结论模板

如果以上用例都通过，对第 2 部分当前实现的最准确说法应是：

- `已经把货不对板和明显风险做成可见、可提示、可筛掉一部分、可拦住一部分`

不能说成：

- `已经彻底解决照骗、收入虚标和职业骗子问题`
