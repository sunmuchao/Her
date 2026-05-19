# 🧭 系统概览 (System Overview)

## 系统名称与核心定位

**系统名称建议：HER 关系运营中台 / Relationship Operations Console**

这是一个围绕相亲/婚恋业务构建的复合型运营系统，整合了以下能力：
- 短信验证码登录与新老用户分流
- 智能发现式问答找人
- 档案搜索与持续推荐订阅
- 人工撮合池、匹配对、撮合案件流转
- 聊天线程、会话时间线与站内互动
- 聊天风控、举报、申诉、欺诈网络识别
- 资料字段核验、资料风险审核、活体视频验证
- Persona Memory 同步与公开资料渲染
- 异步任务运营监控

系统本质不是单一前台 App，而是“用户自助 + 运营审核 + 风控处置 + 推荐撮合”一体化的关系运营平台。

## 目标用户群体与主要痛点

### 目标用户
- 普通终端用户 `end_user`：登录、发现对象、查看推荐、提交验证、查看信任状态、申诉
- 运营人员 `ops_operator`：管理推荐订阅、撮合池、匹配案件、异步任务
- 风控审核人员 `risk_reviewer`：处理举报、聊天风险案件、欺诈网络、活体验证请求
- 资料审核人员 `profile_reviewer`：处理资料字段核验、照片风险、资料风险案件
- 客服 `customer_support`：查看用户信任中心、辅助处理投诉与申诉
- 平台管理员 `platform_admin`：全局配置、跨模块审查、所有任务监控

### 主要痛点
- 用户端痛点：找人效率低、资料真假难辨、沟通安全感不足、申诉路径不透明
- 运营端痛点：推荐、撮合、聊天、审核数据分散，缺少统一操作台
- 风控端痛点：案件证据链长、多个审核模块割裂、缺少统一风险画像和处置联动
- 审核端痛点：字段核验、活体视频、照片风险、资料争议分散在不同流程中


# 🎨 视觉风格与全局规范 (UI Style Guide)

## 整体视觉风格

**风格关键词：专业运营后台、可信赖、数据密集、风险敏感、轻科技感**

设计方向：
- 主基调为“专业商务 + 数据运营 + 婚恋信任服务”
- 不做娱乐化社交产品视觉，不使用轻浮粉紫系
- 强调状态颜色、审核流、时间线、证据链、风险等级
- 用户端自助页面可稍柔和；运营与审核后台必须理性、克制、可高密度浏览

## 全局配色方案建议

- 主色：`#2563EB`，用于主按钮、主导航高亮、可点击关键路径
- 辅助色：`#0F766E`，用于信任、验证通过、资料可信等正向状态
- 强提醒色：`#F97316`，用于待处理、提醒、需要人工跟进
- 风险色：`#DC2626`，用于高风险、封禁、驳回、欺诈、异常
- 成功色：`#16A34A`
- 中性色文字：`#1E293B`
- 弱文字：`#64748B`
- 背景色：`#F8FAFC`
- 卡片背景：`#FFFFFF`
- 分割线：`#E2E8F0`

## 排版感觉

- 标题字体感觉：技术感、精确、偏控制台气质
- 正文字体感觉：高可读、运营后台友好、适配中英文混排
- 推荐排版：
  - 页面标题：大号粗体，明确模块语义
  - 二级信息：使用数据标签、小号辅助文字、状态徽章
  - 表格：中等密度，行高紧凑但不拥挤
  - 时间线与审核记录：采用纵向事件流样式

## 整体布局结构

- 后台主框架：左侧侧边栏导航 + 顶部全局栏 + 中央内容区 + 右侧抽屉/详情面板
- 顶部全局栏：
  - 系统名称
  - 环境标识
  - 全局搜索
  - 待处理数量入口
  - 当前角色与用户菜单
- 左侧导航建议分组：
  - 用户与发现
  - 推荐与撮合
  - 沟通与信任
  - 审核与验证
  - 运营监控
- 内容区统一规范：
  - 顶部页面标题区
  - 第二层筛选/操作工具栏
  - 主内容为卡片、表格、时间线、图表、详情抽屉
- 详情查看优先使用 Drawer 抽屉，复杂流程使用独立详情页
- 所有异步请求必须有 Skeleton、Spinner、Empty、Error 四类状态


# 🗺️ 页面地图与路由 (Page Map)

## 公共与用户侧页面

- `POST /v1/auth/sms/send-code` / `POST /v1/auth/sms/verify-code`
  - 页面：短信验证码登录页
- `POST /v1/discovery/sessions`
  - 页面：智能发现启动页
- `GET /v1/discovery/sessions/{session_id}`
  - 页面：智能发现会话页
- `POST /v1/discovery/sessions/{session_id}/turns`
  - 交互：发现会话消息发送/动作触发
- `GET /v1/discovery/profiles/{profile_id}`
  - 页面：候选人档案详情弹窗/详情页
- `GET /v1/recommendation/cards`
  - 页面：推荐卡片中心
- `POST /v1/recommendation/cards/read`
  - 交互：卡片已读
- `GET /v1/user-center/trust-hub`
  - 页面：用户信任中心
- `POST /v1/verifications/live-video-challenges`
  - 页面：活体验证挑战准备页
- `POST /v1/verifications/live-video-submissions`
  - 页面：活体验证上传页
- `POST /v1/verifications/live-video-submissions/{submission_id}/resubmit`
  - 交互：重新提交视频
- `GET /v1/verifications/notifications`
  - 页面：验证通知中心

## 运营后台页面

- `POST /v1/search/profiles`
  - 页面：档案搜索与即时匹配页
- `POST /v1/recommendation/subscriptions`
  - 页面：新建持续推荐订阅弹窗
- `GET /v1/recommendation/subscriptions/{subscription_id}`
  - 页面：推荐订阅详情页
- `PATCH /v1/recommendation/subscriptions/{subscription_id}/overrides`
  - 交互：订阅规则调整
- `POST /v1/recommendation/subscriptions/{subscription_id}/refresh`
  - 交互：单条订阅立即刷新
- `POST /v1/recommendation/subscriptions/refresh-due`
  - 交互：批量刷新到期订阅
- `GET /v1/recommendation/subscriptions/{subscription_id}/recommendations`
  - 页面：推荐结果列表
- `GET /v1/recommendation/subscriptions/{subscription_id}/runs`
  - 页面：搜索运行记录页
- `POST /v1/recommendation/deliver`
  - 交互：批量投递推荐卡
- `POST /v1/recommendation/actions`
  - 交互：推荐动作记录
- `POST /v1/recommendation/reviews`
  - 交互：用户评价记录
- `POST /v1/matchmaking/members`
  - 页面：录入撮合池成员
- `GET /v1/matchmaking/members/{member_id}`
  - 页面：撮合成员详情页
- `PATCH /v1/matchmaking/members/{member_id}/status`
  - 交互：更新成员状态
- `POST /v1/matchmaking/members/{member_id}/refresh`
  - 交互：刷新单个成员匹配资格
- `POST /v1/matchmaking/pool/refresh`
  - 交互：批量刷新撮合池
- `GET /v1/matchmaking/pairs`
  - 页面：匹配对管理页
- `GET /v1/matchmaking/pairs/{pair_key}`
  - 页面：匹配对详情抽屉
- `POST /v1/matchmaking/pairs/build`
  - 交互：生成匹配对任务
- `GET /v1/matchmaking/cases`
  - 页面：撮合案件列表页
- `GET /v1/matchmaking/cases/{case_id}`
  - 页面：撮合案件详情页
- `POST /v1/matchmaking/cases/open`
  - 交互：批量开案
- `POST /v1/matchmaking/cases/{case_id}/dispatch`
  - 交互：触达/派发案件
- `POST /v1/matchmaking/cases/{case_id}/reply`
  - 交互：记录双方回复
- `POST /v1/matchmaking/cases/close-stale`
  - 交互：关闭超时案件
- `POST /v1/matchmaking/feedback`
  - 页面：撮合反馈录入弹窗

## 沟通与风控后台页面

- `GET /v1/chat/threads/{thread_id}`
  - 页面：聊天线程详情页
- `GET /v1/chat/threads/{thread_id}/messages`
  - 页面：线程消息流
- `POST /v1/chat/threads/{thread_id}/messages`
  - 交互：发送消息
- `GET /v1/chat/threads/{thread_id}/summary`
  - 页面：线程摘要卡
- `GET /v1/timeline`
  - 页面：跨推荐/撮合/聊天统一时间线页
- `GET /v2/chat/cases/{case_id}/conversations`
  - 页面：案件会话列表
- `GET /v2/chat/cases/{case_id}/timeline`
  - 页面：案件会话时间线
- `POST /v2/chat/cases/{case_id}/assistant-layout`
  - 交互：生成助理工作区布局
- `GET /v1/chat/reports`
  - 页面：举报列表页
- `GET /v1/chat/meeting-feedback`
  - 页面：见面反馈列表页
- `GET /v1/chat/risk-cases`
  - 页面：聊天风险案件列表页
- `GET /v1/chat/risk-cases/{risk_case_id}`
  - 页面：聊天风险案件详情页
- `POST /v1/chat/risk-cases/{risk_case_id}/review`
  - 交互：审核风险案件
- `POST /v1/chat/risk-cases/batch-review`
  - 交互：批量审核风险案件
- `GET /v1/chat/risk-signals`
  - 页面：风险信号库页
- `GET /v1/chat/risk-appeals`
  - 页面：聊天申诉列表页
- `GET /v1/chat/risk-appeals/{appeal_id}`
  - 页面：聊天申诉详情页
- `POST /v1/chat/risk-appeals/{appeal_id}/review`
  - 交互：审核聊天申诉
- `GET /v1/chat/fraud-networks`
  - 页面：欺诈网络列表页
- `GET /v1/chat/fraud-networks/{subject_user_id}`
  - 页面：欺诈网络画像详情页
- `POST /v1/chat/fraud-networks/observations`
  - 交互：录入网络观察
- `POST /v1/chat/fraud-networks/evaluate`
  - 交互：重新评估网络风险
- `GET /v1/chat/risk-dashboard/weekly`
  - 页面：聊天风控周看板
- `GET /v1/chat/threads/{thread_id}/risk-overview`
  - 页面：线程风险摘要侧栏
- `POST /v1/chat/threads/{thread_id}/reports`
  - 页面：提交举报弹窗
- `POST /v1/chat/threads/{thread_id}/meeting-feedback`
  - 页面：提交见面反馈弹窗

## 审核与验证后台页面

- `GET /v1/profile-verifications/policies`
  - 页面：资料核验规则中心
- `POST /v1/profile-verifications/submissions`
  - 页面：发起资料字段核验
- `GET /v1/profile-verifications/submissions`
  - 页面：资料字段核验列表页
- `GET /v1/profile-verifications/submissions/{submission_id}`
  - 页面：资料字段核验详情抽屉
- `POST /v1/profile-verifications/submissions/{submission_id}/resubmit`
  - 交互：补充材料
- `POST /v1/profile-verifications/submissions/{submission_id}/dispute`
  - 交互：发起争议
- `POST /v1/profile-verifications/submissions/{submission_id}/review`
  - 交互：审核字段核验
- `POST /v1/profile-verifications/expire-due`
  - 交互：过期处理
- `POST /v1/profile-review/risk-cases/evaluate`
  - 交互：生成资料风险案件
- `GET /v1/profile-review/risk-cases`
  - 页面：资料风险案件列表
- `GET /v1/profile-review/risk-cases/{profile_review_case_id}`
  - 页面：资料风险案件详情
- `POST /v1/profile-review/risk-cases/{profile_review_case_id}/review`
  - 交互：审核资料风险案件
- `GET /v1/profile-review/photo-risk/runs`
  - 页面：照片风险评分记录页
- `GET /v1/profile-review/photo-risk/runs/{score_run_id}`
  - 页面：照片风险评分详情抽屉
- `GET /v1/profile-review/photo-risk/review-queue`
  - 页面：照片风险复核队列
- `GET /v1/profile-review/appeals`
  - 页面：资料风险申诉列表
- `GET /v1/profile-review/appeals/{appeal_id}`
  - 页面：资料风险申诉详情
- `POST /v1/profile-review/risk-cases/{profile_review_case_id}/appeals`
  - 页面：提交资料风险申诉
- `POST /v1/profile-review/appeals/{appeal_id}/review`
  - 交互：审核资料申诉
- `POST /v1/verifications/live-video-requests`
  - 页面：发起活体验证请求弹窗
- `GET /v1/verifications/live-video-requests`
  - 页面：活体验证请求列表
- `GET /v1/verifications/live-video-submissions`
  - 页面：活体验证提交列表
- `GET /v1/verifications/live-video-submissions/{submission_id}`
  - 页面：活体验证详情
- `POST /v1/verifications/live-video-submissions/{submission_id}/review`
  - 交互：审核活体验证

## 运营监控与内部工具页面

- `GET /v1/ops/async-jobs/dashboard`
  - 页面：异步任务总控看板
- `GET /v1/recommendation/jobs`
  - 页面：推荐任务列表
- `GET /v1/matchmaking/jobs`
  - 页面：撮合任务列表
- `GET /v1/chat/jobs`
  - 页面：聊天任务列表
- `persona_memory_sync` API
  - 页面：Persona Memory 同步与公开资料生成台
- `profile_service` API
  - 页面：资料源探测与档案源管理页


# 📄 逐页详细 UI 描述 (Detailed Page Specifications)

逐页设计已拆分到独立文档，统一放在 [docs/design-pages/README.md](docs/design-pages/README.md)。

1. [1. 短信验证码登录页](docs/design-pages/01-sms-login.md)
2. [2. 智能发现会话页](docs/design-pages/02-discovery-session.md)
3. [3. 候选人档案详情页 / 详情抽屉](docs/design-pages/03-candidate-profile-detail.md)
4. [4. 档案搜索与即时匹配页](docs/design-pages/04-profile-search-and-instant-match.md)
5. [5. 推荐订阅管理页](docs/design-pages/05-recommendation-subscription-management.md)
6. [6. 推荐订阅详情页](docs/design-pages/06-recommendation-subscription-detail.md)
7. [7. 推荐卡片中心](docs/design-pages/07-recommendation-card-center.md)
8. [8. 撮合池成员管理页](docs/design-pages/08-matchmaking-pool-member-management.md)
9. [9. 匹配对与撮合案件页](docs/design-pages/09-pairs-and-matchmaking-cases.md)
10. [10. 沟通线程与统一时间线工作台](docs/design-pages/10-thread-and-unified-timeline-workbench.md)
11. [11. 用户信任中心](docs/design-pages/11-user-trust-hub.md)
12. [12. 聊天风控总览页](docs/design-pages/12-chat-risk-dashboard.md)
13. [13. 聊天风险案件列表与详情页](docs/design-pages/13-chat-risk-case-list-and-detail.md)
14. [14. 欺诈网络画像页](docs/design-pages/14-fraud-network-profile.md)
15. [15. 资料字段核验页](docs/design-pages/15-profile-field-verification.md)
16. [16. 资料风险与照片风险页](docs/design-pages/16-profile-and-photo-risk.md)
17. [17. 活体视频验证工作台](docs/design-pages/17-live-video-verification-workbench.md)
18. [18. 异步任务总控看板](docs/design-pages/18-async-job-control-dashboard.md)
19. [19. Persona Memory 同步与公开资料生成台](docs/design-pages/19-persona-memory-sync-and-public-profile.md)
20. [20. 资料源探测与档案源管理页](docs/design-pages/20-source-detection-and-profile-source-management.md)
