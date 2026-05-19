# 15. 资料字段核验页

### 页面名称 & 功能概述
处理如收入、职业、教育、婚育等字段真实性核验，支持提交、补件、争议、审核。

### 页面布局架构
- 顶部规则说明区
- 中部核验申请列表
- 右侧详情抽屉展示单条申请、材料与审核记录

### 核心 UI 组件清单
- 规则列表卡
- 提交申请 Drawer
- 核验表格
- 审核时间线
- 补件/争议按钮

### 数据字段映射
- `policies[]`：字段核验规则卡片
- `submission_id`：申请编号
- `field_key`：被核验字段，主标签
- `profile_id`：档案 ID
- `source_dsn` / `source_table_name`：来源库信息，小号展示
- `subject_user_id`：申请归属用户
- `declared_value`：用户声明值
- `approved_value`：审核通过值
- `evidence`：证据材料缩略区
- `evidence_type`：证据类型 Tag
- `evidence_channel`：材料来源渠道
- `required_documents[]`：要求补充文件列表
- `status`：申请状态
- `dispute_status`：争议状态
- `reviewer_id`：审核员
- `review_note`：审核备注
- `requested_documents[]`：审核追加要求
- `validity_days`：有效期
- `next_review_days`：下次复核周期
- `reverify_strategy`：复核策略
- `reviews[]`：审核记录时间线

### 交互与逻辑流
- 点击“发起核验”打开 Drawer，选择字段并上传证据
- 状态为补件或争议中时，详情页展示醒目的行动按钮
- 审核员点击“通过/驳回/要求补件”后，时间线立即追加审核节点
