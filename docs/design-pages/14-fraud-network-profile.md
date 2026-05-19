# 14. 欺诈网络画像页

### 页面名称 & 功能概述
用于识别同设备、同联系方式、同话术模板等关联主体，辅助风险扩散判断。

### 页面布局架构
- 顶部为主体风险画像总览
- 左侧为关联网络图或关系列表
- 右侧为当前限制状态和人工观察录入表单
- 底部为关联账户清单

### 核心 UI 组件清单
- 网络评分卡
- 节点关系图
- 账户关联表
- 观察录入表单
- 风险动作建议卡

### 数据字段映射
- `subject_user_id`：主体用户 ID
- `network_profile.graph_risk_score`：网络风险总分，核心视觉重点
- `network_profile.review_status`：审核状态
- `network_profile.recommended_action`：建议动作
- `network_profile.applied_action`：已应用动作
- `moderation_state`：当前风控状态
- `account_links[].linked_user_id`：关联用户
- `account_links[].linked_network_profile`：关联用户风险画像
- `account_links[]` 其余字段：作为关系强度、关联类型、证据摘要展示
- 观察录入表单字段：
  - `subject_user_id`
  - `profile_id`
  - `thread_id`
  - `case_id`
  - `risk_case_id`
  - `report_id`
  - `source_type`
  - `event_type`
  - `signal_codes[]`
  - `evidence`
  - `message_body`
  - `evaluate`

### 交互与逻辑流
- 列表页点击主体进入画像页
- 录入观察后，页面右上角显示评估成功提示，并刷新网络图
- 当 `graph_risk_score >= 60` 时，页头采用高风险红色警示带
