# 19. Persona Memory 同步与公开资料生成台

### 页面名称 & 功能概述
为运营或 AI 标注人员提供 Persona Patch 写入、Persona 与 Profile 同步、公开资料预览与落库能力。

### 页面布局架构
- 左侧 Persona Patch 编辑区
- 中部 Persona 规范化预览
- 右侧公开资料预览和同步结果区

### 核心 UI 组件清单
- JSON Patch 编辑器
- 字段表单模式切换
- 规范化预览卡
- 公开资料预览卡
- 同步执行按钮

### 数据字段映射
- `source`：来源库
- `user_key`：用户键
- `source_type`：Patch 来源类型
- `patch`：原始 Persona Patch
- `confidence_score`：可信分
- `evidence_text`：证据文本
- `conversation_ref`：会话引用
- `basis`：推断依据
- `apply_scope`：应用范围
- `sync_profile`：是否同步到 Profile
- Persona 规范化重点字段：
  - `self_gender`
  - `self_age`
  - `self_city`
  - `self_district`
  - `self_height`
  - `self_education`
  - `self_job`
  - `self_marital_status`
  - `self_has_children`
  - `self_children_count`
  - `self_smoking`
  - `self_drinking`
  - `self_relationship_goal`
  - `target_gender`
  - `target_age_min` / `target_age_max`
  - `target_cities[]`
  - `target_height_min` / `target_height_max`
  - `target_education_min`
  - `target_income_min_wan` / `target_income_max_wan`
  - `target_marital_statuses[]`
  - `target_accept_partner_children`
  - `target_accept_long_distance`
  - `target_want_children`
  - `target_marriage_timeline`
  - `must_have_tags[]`
  - `must_not_have_tags[]`
  - `preferred_traits[]`
  - `disliked_traits[]`
- `write_profile`：公开资料写回开关

### 交互与逻辑流
- 粘贴 Patch 后自动规范化并在中部预览
- 点击“同步 Persona 到 Profile”后显示结果 Diff
- 点击“生成公开资料”后右侧预览可切换“只预览/写回资料库”
