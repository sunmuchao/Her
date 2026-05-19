# 16. 资料风险与照片风险页

### 页面名称 & 功能概述
处理资料一致性问题、照片同人风险、资料风控案件、资料申诉。

### 页面布局架构
- 顶部使用二级 Tabs：`资料风险案件` / `照片风险评分` / `照片复核队列` / `资料申诉`
- 列表点击进入右侧详情抽屉

### 核心 UI 组件清单
- Tab 导航
- Data Table
- 风险评分条
- 审核表单
- 申诉详情卡

### 数据字段映射
- `risk_case.profile_review_case_id`：资料风险案件 ID
- `risk_case.profile_id`：档案 ID
- `risk_case.subject_user_id`：主体用户
- `risk_case.status`：案件状态
- `risk_case.recommended_action`：建议动作
- `risk_case.applied_action`：已执行动作
- `risk_case.resolution_note`：处理说明
- `score_run.score_run_id`：照片评分运行 ID
- `score_run.profile_review_case_id`：关联资料风险案件
- `score_run.profile_id`：档案 ID
- `score_run.subject_user_id`：主体用户
- `score_run` 内评分与风险明细：以分数条、风险标签、可疑说明展示
- `review_queue[].queue_status`：队列状态
- `appeal.appeal_id`：资料申诉 ID
- `appeal.appeal_status`：申诉状态
- `appeal.reason_text`：申诉理由
- `appeal.evidence`：申诉材料
- `appeal.resolution_note`：申诉处理说明

### 交互与逻辑流
- 点击“评估资料风险”后生成案件并刷新列表
- 点击评分记录可查看照片风险明细
- 点击“处理申诉”打开审核 Drawer
- 照片复核队列中待处理项应支持高优先级排序和批量认领
