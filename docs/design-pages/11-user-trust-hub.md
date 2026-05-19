# 11. 用户信任中心

### 页面名称 & 功能概述
面向用户、客服和审核协作展示验证进度、风险记录、申诉状态和通知信息，是“为什么我被限制/还需要做什么”的统一解释中心。

### 页面布局架构
- 顶部为信任总览卡
- 中部三列：验证中心、申诉中心、风险记录
- 底部为通知流和 FAQ

### 核心 UI 组件清单
- Summary KPI 卡
- 状态进度列表
- 风险记录表
- 通知时间线
- FAQ 折叠面板

### 数据字段映射
- `summary.pending_verification_count`：待完成验证数
- `summary.pending_appeal_count`：待处理申诉数
- `summary.active_risk_count`：活动风险数
- `summary.notification_count`：通知数
- `verification_center.items[]`：验证事项卡片列表
- `appeal_center.items[]`：申诉事项卡片列表
- `risk_records.items[]`：风险记录列表
- `notifications[]`：用户通知时间线
- `faqs[].question` / `faqs[].answer`：帮助内容

### 交互与逻辑流
- 点击验证事项，跳转到对应资料核验或活体验证页
- 点击申诉事项，打开申诉详情 Drawer
- 点击通知，定位到对应流程或案件
- 有 `action_required` 状态时，页面顶部显示固定行动横幅
