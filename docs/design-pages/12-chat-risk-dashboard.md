# 12. 聊天风控总览页

### 页面名称 & 功能概述
提供聊天风险的周度总览、举报聚合、风险案件分布、申诉准确率和欺诈网络态势，是风控团队的首屏。

### 页面布局架构
- 顶部多张 KPI 卡
- 中部左侧风险趋势与结构图
- 中部右侧处置分布、欺诈网络动作分布
- 底部为高优先级案件与高风险主体列表

### 核心 UI 组件清单
- KPI 卡片
- 柱状图 / 环形图 / 堆叠条形图
- 风险分级图
- 行动分布图
- 表格列表

### 数据字段映射
- `window_start` / `window_end`：分析周期
- `days`：统计天数
- `risk_case_count`：风险案件总数
- `reviewed_case_count`：已审核案件数
- `confirmed_case_count`：确认风险数
- `dismissed_case_count`：驳回数
- `appeal_count`：申诉数
- `appeal_upheld_count`：申诉成立数
- `appeal_rejected_count`：申诉驳回数
- `active_moderation_state_count`：当前生效限制数
- `fraud_network_profile_count`：已识别网络画像数
- `high_risk_network_count`：高风险网络数
- `severity_breakdown`：按严重程度分布
- `action_breakdown`：按处置动作分布
- `network_action_breakdown`：按网络处置动作分布
- `confirmed_rate`：确认率
- `false_positive_rate`：误伤率
- `recurrence_rate`：复发率
- `repeat_subject_count`：重复主体数

### 交互与逻辑流
- 顶部可切换 7 天、14 天、30 天视图
- 点击图表某个严重等级，联动过滤下方案件列表
- 点击高风险网络数，跳转欺诈网络列表页
