# 18. 异步任务总控看板

### 页面名称 & 功能概述
监控 recommendation、matchmaking、chat 三大子系统的异步任务状态、积压、失败与近期运行情况。

### 页面布局架构
- 顶部全局总量卡
- 中部按系统分三列
- 底部为任务类型排行与最近任务表

### 核心 UI 组件清单
- 总量 KPI 卡
- 系统状态卡
- 状态分布图
- 任务类型排行表
- 最近任务表

### 数据字段映射
- `totals.total`：任务总量
- `totals.backlog_open`：未完结积压
- `totals.due_now`：当前到期
- `totals.processing_overdue`：处理超时
- `totals.pending` / `processing` / `retry_pending` / `succeeded` / `failed`：状态数量
- `systems.recommendation.available` / `systems.matchmaking.available` / `systems.chat.available`：系统可用状态
- `systems.*.summary`：系统级摘要
- `systems.*.job_types[]`：任务类型维度统计
- `systems.*.recent_jobs[]`：最近任务
- `recent_jobs[].job_id`：任务 ID
- `recent_jobs[].target`：所属系统
- `recent_jobs[].job_type`：任务类型
- `recent_jobs[].status`：状态 Tag
- `recent_jobs[].poll_path`：详情链接
- 常见时间字段：`created_at`、`started_at`、`finished_at`
- 错误字段：存在时使用红色内联错误提示

### 交互与逻辑流
- 点击某个系统卡，过滤底部任务列表
- 点击 `job_id` 打开任务详情抽屉
- 当 `available=false` 时，整块卡片显示降级状态与错误文案
- 失败任务支持快速跳转到对应业务模块
