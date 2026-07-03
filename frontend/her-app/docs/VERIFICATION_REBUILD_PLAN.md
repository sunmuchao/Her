# 身份认证重构方案

## 背景

当前身份认证前端只覆盖了最薄的一层提交流程：

- 视频认证：开始录制、预览、提交、等待审核
- 字段认证：上传文件、提交、等待审核

而后端已经支持更完整的 challenge、审核、补录、通知、争议复核与信任中心聚合能力。前后端能力存在明显断层，导致用户只能“交材料”，却不知道：

- 本次具体要做什么动作
- 是否需要读随机数字
- 挑战还有多久过期
- 提交后的机器预审结果如何
- 为什么被打回
- 下一步是补录、补件还是等待人工审核
- 认证多久有效、什么时候需要重审

## 目标

把当前“单次上传页”升级为“完整认证闭环系统”，分阶段落地：

1. 先补全 challenge 展示、录制引导、状态分流、补录入口等高收益能力
2. 再补认证中心、详情页、争议复核、通知中心
3. 最后补实时动作检测与更真实的浏览器侧质检

## 现状问题

### 1. 视频 challenge 信息未展示完整

后端 challenge 已返回：

- `required_actions`
- `challenge_phrase`
- `spoken_code`
- `prompt_steps`
- `expires_at`

当前前端只在极少数位置用到 `challenge_phrase`，录制页文案仍然写死为“请缓慢转动头部”。

### 2. 录制中没有过程反馈

前端当前只使用 `MediaRecorder` 盲录 6 秒，不知道用户有没有完成动作，也不会告诉用户当前是第几步、下一步是什么。

### 3. 提交后状态过于粗糙

后端支持返回：

- `machine_review`
- `recommended_decision`
- `recommended_next_step`
- `confidence_band`

当前前端统一展示“已提交，预计 1-2 个工作日完成审核”，没有根据真实状态分流。

### 4. 补录、申诉、有效期能力未接入

后端支持：

- `live-video-requests`
- `resubmit_live_video`
- 字段核验 `resubmit`
- 字段核验 `dispute`
- `verification_expires_at`
- `next_review_due_at`

当前前端没有面向用户的补录、争议复核和有效期展示入口。

### 5. 认证中心能力未整合

后端 `trust-hub` 已可聚合：

- `verification_center`
- `appeal_center`
- `risk_records`
- `notifications`
- `faqs`

当前身份认证流程仍然是孤立页面，没有形成完整闭环。

## 完整改进方案

### 一、视频认证重做

#### 1. 录制前页

录制前页需要展示：

- challenge 标题和说明
- 本次 challenge 句子 `challenge_phrase`
- 动作步骤列表 `prompt_steps`
- 随机数字口令 `spoken_code`
- 过期时间 `expires_at`
- 环境要求与失败说明

#### 2. 录制中页

第一阶段不依赖实时 AI 检测，先实现“引导式 challenge”：

- 当前第几步
- 当前动作大字提示
- 下一步动作提示
- spoken code 提示
- 录制进度条
- challenge 到期提示

第二阶段再补浏览器侧实时检测：

- `blink`
- `open_mouth`
- `turn_left`
- `turn_right`
- `nod_up`

#### 3. 录制确认页

提交前确认页展示：

- 本次 challenge 文案
- 动作列表
- 录制时长
- 是否包含 spoken code
- 重录入口

#### 4. 提交后状态页

按后端状态分流：

- `submitted` / `under_review`
- `approved`
- `resubmission_required`
- `rejected`

展示：

- 审核标题
- 推荐下一步 `recommended_next_step`
- 机器预审建议 `recommended_decision`
- 置信度 `confidence_band`
- 最近通知文案
- 重新录制入口

### 二、字段认证增强

#### 1. 动态规则驱动

字段认证前端应读取后端策略，而不是仅依赖写死文案：

- accepted documents
- accepted evidence types
- accepted evidence channels
- 默认有效期
- 默认重审策略

#### 2. 状态闭环

字段认证需要支持展示：

- `submitted`
- `under_review`
- `approved`
- `rejected`
- `resubmission_required`
- `expired`
- `disputed`

用户动作：

- 重新补件
- 申请复核
- 查看审核意见
- 查看有效期与下次复核时间

### 三、认证中心

新增统一认证中心，展示：

- 已完成认证数
- 待处理认证数
- 需要补件数
- 视频认证、学历、职业、收入认证的最新状态
- 通知、申诉、风险提示入口

### 四、通知和申诉

通知不能只展示一段文本，要结构化为：

- 审核通过
- 审核拒绝
- 需要补录
- 需要补件
- 即将过期
- 已过期

并附带下一步操作入口。

### 五、数据层改造

前端 API 层需补充：

- challenge 的 `spoken_code` / `prompt_steps`
- submission 的机器预审字段
- 视频补录与重新提交接口
- 字段核验策略、重提、争议复核接口
- trust-hub 更完整映射

## 分阶段实施

### Phase 1：立即落地

本轮直接实现：

- 接入并展示 `required_actions`、`prompt_steps`、`spoken_code`、`expires_at`
- 修正 challenge 动作池，与后端真实动作库对齐
- 录制页改为分步引导，而不是写死“转头”
- 录制确认页补 challenge 信息
- 提交后状态页按 submission / notification 信息分流
- 字段与视频等待页展示更真实的状态文案

### Phase 2：后续迭代

- 认证中心首页
- 视频/字段认证详情页
- 视频补录闭环
- 字段争议复核
- 通知中心结构化

### Phase 3：技术增强

- 浏览器实时动作检测
- 浏览器语音识别辅助
- 自动质检与更真实的 `action_events`

## 本轮落地范围

本轮代码改造以 Phase 1 为准，目标是先把“用户不知道在做什么、提交后不知道发生了什么”的核心问题解决掉，并为后续认证中心和实时检测留出稳定的数据结构。
