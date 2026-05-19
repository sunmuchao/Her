# 4. 档案搜索与即时匹配页

### 页面名称 & 功能概述
供运营或高级用户直接输入搜索条件，立即执行 `/v1/search/profiles`，查看候选池、结果、回退结果和诊断信息。

### 页面布局架构
- 顶部为高级筛选栏
- 左侧为“本人画像/Persona 输入区”
- 中部为匹配结果列表
- 右侧为候选池统计、诊断、推荐动作区

### 核心 UI 组件清单
- 多段筛选表单
- 条件分组折叠面板
- 搜索按钮与重置按钮
- 结果 Data Table / 卡片切换
- 池子统计卡
- 诊断说明面板
- 批量加入订阅按钮

### 数据字段映射
- `source`：数据源选择器
- `table_name` / `photos_table_name`：高级数据源配置，可隐藏在高级设置
- `self_id`：本人档案 ID 输入框
- `limit`：结果数量输入框
- `photo_preview_count`：照片预览数量选择器
- `criteria.gender`：性别单选
- `criteria.age_min` / `criteria.age_max`：年龄范围滑块
- `criteria.height_min` / `criteria.height_max`：身高范围滑块
- `criteria.cities[]` / `districts[]` / `settlement_cities[]`：城市多选
- `criteria.relationship_goals[]`：关系目标多选标签
- `criteria.must_have[]` / `prefer[]` / `must_not_have[]`：关键词标签输入
- `criteria.smoking` / `drinking` / `long_distance`：生活方式单选
- `criteria.housing_statuses[]` / `car_statuses[]`：资产条件多选
- `criteria.marital_statuses[]` / `has_children` / `want_children`：婚育条件
- `criteria.verified_level_min` / `photo_verification_level_min`：认证门槛
- `criteria.active_within_days`：活跃天数
- `criteria.photo_count_min`：最少照片数
- `pool_summary.scanned_count`：扫描人数统计卡
- `pool_summary.passed_count`：通过人数统计卡
- `pool_summary.usable_count`：可用人数统计卡
- `fallback_results[]`：无完全匹配时的回退候选
- `diagnostics`：诊断面板，采用结构化说明和小图表

### 交互与逻辑流
- 点击搜索后，顶部筛选栏保持可见，中部结果区 Skeleton 化
- 有完全结果时，优先展示 `results`
- 无完全结果时，显示 `fallback_results`，并在侧栏展示为什么无完全命中
- 支持多选结果并创建持续推荐订阅
