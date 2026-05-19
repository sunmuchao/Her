# 17. 活体视频验证工作台

### 页面名称 & 功能概述
统一承接活体视频挑战生成、人工请求、用户上传、重新提交、人工审核与通知回流。

### 页面布局架构
- 顶部概览卡
- 左侧请求/提交列表
- 中部视频预览与审核区
- 右侧挑战信息、资料信息、通知记录

### 核心 UI 组件清单
- 活体验证请求表格
- 提交记录表格
- 视频播放器
- 挑战动作卡
- 审核表单
- 通知列表

### 数据字段映射
- 请求创建字段：
  - `user_id`
  - `profile_id`
  - `source_dsn`
  - `source_table_name`
  - `request_source`
  - `request_reason`
  - `signal_codes[]`
  - `risk_case_id`
  - `report_ids[]`
  - `requested_by`
  - `due_at`
- 挑战字段：
  - `challenge.challenge_token`
  - `challenge.challenge_phrase`
  - `challenge.challenge_actions[]`
  - `challenge.action_count`
- 提交字段：
  - `submission.submission_id`
  - `submission.user_id`
  - `submission.profile_id`
  - `submission.status`
  - `submission.content_type`
  - `submission.metadata`
  - `submission.photo_review_task`
  - `submission.created_at`
  - `submission.updated_at`
- 审核字段：
  - `reviewer_id`
  - `decision`
  - `review_note`
  - `liveness_result`
  - `face_match_result`
  - `profile_consistency_result`
- 通知字段：
  - `notifications[].submission_id`
  - `notifications[].user_id`
  - `notifications[].type`
  - `notifications[].created_at`

### 交互与逻辑流
- 用户侧：先生成 challenge，再打开摄像头上传视频
- 上传中使用大尺寸进度条，失败可断点重试或整条重提
- 审核员打开提交记录后，视频区自动加载播放器与挑战词
- 提交审核结论后，右侧通知流即时新增一条通知
