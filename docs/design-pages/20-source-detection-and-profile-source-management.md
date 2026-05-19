# 20. 资料源探测与档案源管理页

### 页面名称 & 功能概述
帮助内部人员探测外部 MySQL 档案源表结构、字段映射、照片表与单个档案记录，便于配置搜索和核验流程。

### 页面布局架构
- 顶部为数据源连接配置
- 左侧为表与字段浏览器
- 中部为档案列表
- 右侧为单档案 JSON 详情与字段映射建议

### 核心 UI 组件清单
- DSN 输入框
- 自动探测按钮
- 表列表树
- 字段表
- 档案列表表格
- JSON 详情面板

### 数据字段映射
- `source_dsn`：数据源 DSN
- `source_table_name`：档案表
- `photos_table_name`：照片表
- `detect_profile_table()` 返回结果：建议档案表
- `list_profile_columns()`：字段列表
- `list_profiles()`：档案记录列表
- `get_profile(profile_id)`：单条档案 JSON
- 常见字段别名映射重点：
  - `id`
  - `name`
  - `gender`
  - `age`
  - `city`
  - `profile_status`
  - `verified_level`

### 交互与逻辑流
- 点击“自动探测”后，先显示表列表，再高亮最佳候选表
- 选择字段后，右侧实时显示规范化字段名建议
- 点击档案行，右侧 JSON 详情面板展开
