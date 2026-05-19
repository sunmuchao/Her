# 13. 聊天风险案件列表与详情页

### 页面名称 & 功能概述
管理举报触发的聊天风险案件，支持证据回放、批量审核、申诉处理与处置动作落地。

### 页面布局架构
- 列表页：顶部筛选栏 + 表格 + 批量操作条
- 详情页：左侧案件摘要，中部证据回放，右侧风险画像和处理表单

### 核心 UI 组件清单
- 风险案件表格
- 批量勾选栏
- 案件详情 Drawer/独立页
- 证据时间线
- 举报卡片
- 见面反馈卡片
- 审核表单

### 数据字段映射
- `risk_case.risk_case_id`：案件 ID
- `risk_case.subject_user_id`：被举报主体
- `risk_case.thread_id`：关联线程
- `risk_case.status`：状态 Tag
- `risk_case.severity`：严重程度，红黄绿标签
- `risk_case.signal_codes[]`：风险信号标签组
- `risk_case.report_count`：举报数
- `risk_case.recommended_action`：建议动作
- `risk_case.applied_action`：已执行动作
- `risk_case.resolution_note`：处置说明
- `risk_case.evidence_summary`：证据摘要卡
- `reports[]`：举报列表
- `signals[]`：风险信号明细
- `meeting_feedback[]`：见面反馈记录
- `appeals[]`：相关申诉
- `moderation_state`：当前限制状态
- `fraud_network`：关联欺诈网络概览

### 交互与逻辑流
- 点击表格行打开详情页
- 点击“批量审核”弹出批量操作 Modal，填写 `status`、`applied_action`、`resolution_note`
- 审核提交后，详情页时间线新增处置节点
- 若存在申诉，详情顶部显示醒目“待申诉处理”横幅
