# 9. 匹配对与撮合案件页

### 页面名称 & 功能概述
这是人工撮合的核心工作区，先查看 `pairs`，再进入 `cases` 处理触达、回复、接受、拒绝、超时等流程。

### 页面布局架构
- 双栏主界面
- 左侧为“匹配对列表”
- 右侧为“撮合案件列表 / 当前选中详情”
- 顶部提供“生成匹配对”“开案”“关闭超时”按钮

### 核心 UI 组件清单
- Pair Data Table
- Case Data Table
- Case 详情时间线
- 状态标签
- 回复录入弹窗
- 反馈录入弹窗

### 数据字段映射
- `pairs[].pair_key`：匹配对主键
- `pairs[].canonical_pair_key`：规范化键，二级信息
- `pairs[].pair_status`：成对状态 Tag
- `pairs[].canonical_pair_status`：统一状态，用于筛选
- `pairs[].block_reason`：阻断原因，红色说明
- `pairs[].cooling_until`：冷却到期时间
- `cases[].case_id`：案件编号
- `cases[].pair_key`：关联匹配对
- `cases[].status`：案件原始状态 Tag
- `cases[].canonical_case_status`：统一案件状态，用主筛选
- `cases[].first_contact_member_id` / `second_contact_member_id`：双方联系顺序
- `cases[].expires_at`：超时截止时间
- `events[].event_type`：事件类型
- `events[].actor_id`：操作人
- `events[].occurred_at`：事件时间
- `events[].payload`：事件详情
- `feedback.feedback_id`：反馈 ID
- `feedback.member_id`：反馈成员
- `feedback.feedback_kind` / `feedback.feedback_type`：反馈类型
- `feedback.feedback_text`：反馈正文

### 交互与逻辑流
- 点击“生成匹配对”或“开案”后，顶部显示异步任务成功提示
- 点击某个 `pair`，右侧高亮相关案件
- 点击某个 `case`，右侧切换为详情时间线
- 点击“记录回复”时弹出 Modal，要求填写 `member_id`、回复结果等
- 案件状态发生变化后，时间线实时追加新节点
