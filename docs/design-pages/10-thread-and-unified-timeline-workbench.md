# 10. 沟通线程与统一时间线工作台

### 页面名称 & 功能概述
查看线程消息、跨推荐/撮合/聊天的统一时间线，并供运营人员理解当前关系推进状态。

### 页面布局架构
- 左侧会话列表或时间线节点
- 中部消息流
- 右侧线程摘要、风险摘要、案件与推荐联动面板

### 核心 UI 组件清单
- 线程列表
- 消息气泡列表
- 时间线 Timeline
- 线程摘要卡
- 风险概览卡
- 消息发送框

### 数据字段映射
- `thread.thread_id`：线程 ID
- `thread.case_id`：关联案件 ID
- `thread.relation_key`：关系键
- `thread.participant_a_id` / `participant_b_id`：双方用户 ID
- `messages[].message_id`：消息 ID
- `messages[].author_id`：发送者 ID
- `messages[].body`：消息正文
- `messages[].metadata`：消息元数据，可做悬停查看
- `messages[].created_at`：发送时间
- `summary`：线程摘要文本块
- `timeline.case_id`：时间线主键
- `timeline.chat`：聊天维度对象
- `timeline.matchmaking.case`：撮合案件摘要卡
- `timeline.matchmaking.events[]`：撮合事件时间线
- `timeline.recommendation.case`：推荐案件摘要卡
- `timeline.recommendation.events[]`：推荐动作时间线

### 交互与逻辑流
- 点击线程后，中部消息 Skeleton 加载
- 发送消息后，本地先插入消息占位，再回写正式消息
- 时间线节点点击后，可联动定位到对应消息或案件事件
- 若线程不可见或越权，页面显示无权限态而非空白
