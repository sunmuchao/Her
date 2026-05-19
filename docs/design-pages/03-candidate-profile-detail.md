# 3. 候选人档案详情页 / 详情抽屉

### 页面名称 & 功能概述
展示搜索结果或发现结果中的单个候选人详细档案、信任状态、照片预览与推荐理由。

### 页面布局架构
- 左侧大图区为头像/照片轮播
- 右侧为基础档案卡、匹配理由卡、信任状态卡
- 底部可附加扩展文字资料、择偶偏好、风险提示

### 核心 UI 组件清单
- 照片轮播
- 基础资料描述列表
- 匹配得分环形图或横向分数条
- 状态 Tag 组
- 验证项列表
- 风险提示 Alert
- 推荐动作按钮组

### 数据字段映射
- `id`：档案 ID，小号辅助信息
- `name`：主标题
- `score`：主匹配分，粗体高亮
- `fit_score`：适配分，次级数值
- `confidence_score`：可信度分，辅助展示
- `risk_score`：风险分，红橙渐变条
- `verified_level` / `verified_label`：认证等级，用可信标签展示
- `photo_verification_level` / `photo_verification_label`：照片核验等级标签
- `photo_count`：照片数量小徽标
- `last_active_at` / `activity_label`：最近活跃时间与活跃状态
- `verification_items[]`：逐项图标列表
- `trust_summary`：独立可信概览卡
- `caution_items[]`：警示文案，用黄色提示卡
- `trust_actions[]`：平台建议动作，用操作建议清单展示
- `matched_on[]`：命中条件，绿色 Tag
- `reciprocal_on[]`：双向匹配点，蓝色 Tag
- `missing_fields[]`：资料缺失项，灰色信息条
- `self_profile_gaps[]`：自身偏好缺失项，提示补充
- `risk_flags[]`：风险标记，红色 Tag
- `match_evidence[]`：推荐证据列表
- `follow_up_questions[]`：建议继续追问的问题列表
- `photo_preview[]`：照片预览缩略图
- `profile.*`：完整档案字段，按“基础信息/生活方式/婚育观/偏好”分组展示

### 交互与逻辑流
- 打开详情时先展示抽屉 Skeleton，再填充内容
- 点击照片可进入全屏预览
- 点击匹配标签可回跳高亮搜索条件
- 风险标记较高时，顶部出现固定警示条
