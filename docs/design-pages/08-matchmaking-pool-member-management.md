# 8. 撮合池成员管理页

### 页面名称 & 功能概述
管理进入人工撮合池的成员，维护其搜索状态、可用渠道和匹配资格。

### 页面布局架构
- 顶部 KPI 与状态筛选
- 中部成员表格
- 右侧成员详情抽屉
- 底部或顶部支持批量刷新操作

### 核心 UI 组件清单
- 成员列表表格
- 状态过滤 Tabs
- 新建成员 Drawer
- 详情 Drawer
- 批量操作条

### 数据字段映射
- `member_id`：成员编号
- `user_key`：用户唯一标识
- `source`：来源库
- `self_id`：档案 ID
- `status`：成员状态 Tag
- `is_still_searching`：是否仍在找对象，用开关/图标
- `allowed_channels[]`：允许撮合渠道，标签组
- `min_pair_score`：最低成对分阈值
- `needs_refresh`：是否待刷新，用橙色点状态
- `search_criteria`：撮合条件摘要
- `self_profile`：本人画像摘要
- `created_at` / `updated_at`：时间列

### 交互与逻辑流
- 点击“录入成员”打开表单 Drawer
- 修改状态时采用行内下拉 + 确认
- `needs_refresh=1` 时行背景带浅橙提示
- 支持批量刷新池成员，调用异步任务后跳转任务看板
