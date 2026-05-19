# 6. 推荐订阅详情页

### 页面名称 & 功能概述
查看某一订阅的完整配置、推荐结果、搜索运行历史、用户动作记录和投递状态。

### 页面布局架构
- 顶部为订阅头部摘要
- 中部使用 Tabs：`推荐结果` / `搜索运行记录` / `配置详情`
- 右侧固定操作栏：刷新、修改策略、投递、查看卡片

### 核心 UI 组件清单
- 头部摘要卡
- Tab 导航
- 推荐结果表格
- Run 时间线
- JSON 摘要卡
- 操作按钮组

### 数据字段映射
- 订阅头部复用上一页主要字段
- `recommendations[].recommendation_id`：推荐记录主键
- `recommendations[].candidate_id`：候选人 ID
- `recommendations[].candidate_name`：候选人姓名
- `recommendations[].score`：推荐分，粗体
- `recommendations[].delivery_status`：投递状态 Tag
- `recommendations[].final_review_status`：最终审核状态 Tag
- `recommendations[].last_action_type`：最近动作，展示为操作胶囊
- `recommendations[].cooling_until`：冷却截止时间
- `recommendations[].notified_at`：通知时间
- `recommendations[].active_match_case_id`：关联撮合案件链接
- `recommendations[].relation_key`：关系键，隐藏在详情
- `recommendations[].canonical_relation_status`：规范化关系状态
- `runs[].created_at`：运行时间
- `runs[].result_count`：命中结果数
- `runs[].top_candidate_ids[]`：Top 候选 ID 列表
- `runs[].status_counts`：状态分布
- `runs[].review_counts`：审核分布
- `runs[].persona_profile`：运行时 Persona 快照
- `runs[].effective_criteria`：实际生效条件
- `runs[].rule_provenance`：规则来源说明

### 交互与逻辑流
- 切换到“推荐结果”时默认按分数排序
- 点击候选人姓名打开候选人详情 Drawer
- 点击 `active_match_case_id` 跳转撮合案件详情
- 点击“修改策略”打开覆盖参数编辑 Drawer
- 点击“投递推荐卡”触发异步任务，顶部出现任务提示条
