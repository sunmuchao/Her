# 5. 推荐订阅管理页

### 页面名称 & 功能概述
用于创建和管理持续推荐订阅，控制通知策略、推荐模式、主动打招呼阈值和冷却规则。

### 页面布局架构
- 顶部为订阅总览 KPI
- 中部左侧为订阅列表表格
- 右侧为选中订阅的摘要卡和快捷操作
- 新建/编辑使用右侧 Drawer

### 核心 UI 组件清单
- KPI 卡片
- 订阅列表 Data Table
- 状态筛选 Tabs
- 新建订阅 Drawer
- 刷新订阅按钮
- 批量到期刷新按钮

### 数据字段映射
- `subscription_id`：订阅编号，灰色副标题
- `requester_id`：订阅所属用户 ID
- `title`：订阅名称，主列
- `status`：状态 Tag，`active` 等
- `is_still_searching`：开关状态
- `source`：来源库
- `self_id`：本人档案 ID
- `limit_count`：每次搜索候选量
- `top_k`：保留 Top K
- `min_notify_score`：通知阈值，进度条数值展示
- `daily_notification_cap`：每日通知上限
- `quiet_hours_start` / `quiet_hours_end`：静默时段，用时间胶囊展示
- `refresh_interval_hours`：刷新频率
- `skip_cooldown_days`：跳过后冷却天数
- `recommendation_mode`：推荐模式，用分段选择器
- `max_review_candidates_per_refresh`：每轮审核候选上限
- `min_direct_greet_score`：主动打招呼最低分
- `auto_reject_on_follow_up_questions`：布尔开关
- `auto_reject_on_risk_flags`：布尔开关
- `last_result_count`：最近一次结果数
- `last_refreshed_at`：最近刷新时间
- `search_criteria_json`：条件摘要，以标签组方式展示
- `subscription_overrides_json`：覆盖策略摘要卡
- `direct_greet_profile_json`：主动打招呼画像设置

### 交互与逻辑流
- 点击“新建订阅”打开 Drawer，左侧填写条件，右侧实时预览订阅摘要
- 点击某行进入订阅详情页
- 点击“立即刷新”触发单条刷新，显示行内 Loading
- 点击“批量刷新到期订阅”弹出确认 Modal，成功后跳任务详情
