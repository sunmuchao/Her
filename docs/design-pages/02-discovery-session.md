# 2. 智能发现会话页

## 1. General Design Brief

- **System Type:** 婚恋关系运营平台中的用户侧智能发现 Web/App 页面
- **Target Audience:** 正在寻找匹配对象的终端用户，以及需要代用户查看会话过程的客服/运营人员
- **Visual Style:** Clean Modern Light Mode，信任导向，蓝青色企业级配色，柔和卡片阴影，12 栏响应式栅格，8px spacing system
- **Global Layout:** 顶部状态栏 + 中央双栏主内容区 + 底部固定输入操作区；桌面端为左主右辅布局，移动端折叠为上下结构，右侧信息区收纳为 Tab/Bottom Sheet
- **Design Principles:** 会话优先、结果实时反馈、低认知负担、可持续推进、适配高频迭代的模块化卡片结构

## 2. Page: 智能发现会话页

### 页面目标

这是一个通过自然语言逐步收集择偶偏好的会话式搜索页面。用户不需要一次性填写长表单，而是通过聊天逐步表达条件，系统实时：

- 记录会话状态 `session`
- 判断当前阶段 `decision.phase`
- 生成 AI 回复 `decision.assistant_message`
- 生成下一步快捷动作 `decision.suggested_actions[]`
- 输出偏好摘要 `decision.criteria_labels`
- 输出候选人结果 `decision.selected_candidates[]` 与 `search_response.results`

### Layout

- **Top Header 区**
  - 左侧：页面标题“智能发现”
  - 中间：当前阶段标签、会话进度条、当前轮次提示
  - 右侧：会话状态、保存订阅入口、更多操作菜单
- **Main Content 双栏**
  - 左侧 8/12：会话主区，承载消息流、引导问题、系统响应
  - 右侧 4/12：偏好摘要卡 + 推荐候选人卡片列表
- **Bottom Composer 固定区**
  - 输入框、发送按钮、快捷动作 Chips、辅助提示
- **Responsive Rule**
  - `>=1280px`：左右双栏固定显示
  - `768px-1279px`：右侧栏缩为窄栏，候选人卡片单列滚动
  - `<768px`：右侧信息区折叠为顶部切换 Tab：`对话` / `偏好` / `结果`

### Auto Layout / Constraints

- 所有卡片、消息项、候选人项、输入区均使用 Auto Layout
- 页面外层容器采用垂直 Auto Layout，间距 `24`
- 主内容区采用水平 Auto Layout，间距 `24`
- 左侧会话主区宽度 `Fill container`
- 右侧侧栏宽度桌面端固定 `360-420px`
- 底部输入区固定吸底，水平 `Fill container`
- 所有按钮高度遵循统一尺寸：
  - Large `48`
  - Medium `40`
  - Small `32`
- 所有输入组件圆角 `12`
- 卡片圆角 `16`
- 页面安全内边距：
  - Desktop `32`
  - Tablet `24`
  - Mobile `16`

## 3. UI Components

### 3.1 Top Header

- **Page Title**
  - 文案：`智能发现`
  - 字号：`28/34`, Semibold
  - 颜色：`#0F172A`
- **Session Meta Row**
  - `session_id` 作为弱化次级信息展示
  - `requester_id` 不作为主视觉元素，仅在调试或运营模式显示
- **Phase Badge**
  - 根据 `decision.phase` 展示状态
  - 状态样式建议：
    - `collecting_preferences` = Blue badge
    - `searching` = Amber badge + spinner
    - `results_shown` = Green badge
    - `no_result` = Slate/Orange mixed empty-state badge
- **Progress Step Bar**
  - 4 段步骤：`了解需求` / `补充偏好` / `搜索匹配` / `查看结果`
  - 当前步骤高亮，前置步骤实心，后续步骤线框

### 3.2 Conversation Panel

- **Conversation Container**
  - 白色卡片背景
  - 顶部 sticky 小标题：`发现对话`
  - 内容区垂直滚动
  - 消息区内边距 `24`
- **Message Bubbles**
  - 用户消息：右对齐，蓝色浅底，最大宽度 `72%`
  - AI 消息：左对齐，白底描边，最大宽度 `78%`
  - 系统提示消息：居中小胶囊，用于状态变化或搜索中提示
- **Bubble Content Structure**
  - 头像
  - 发送者名
  - 正文
  - 时间戳
  - 可选的推荐动作区
- **AI Message Rich Blocks**
  - 支持多段正文
  - 支持内嵌标签组
  - 支持下一步动作按钮
  - 支持“系统理解如下”摘要框

### 3.3 Preference Summary Sidebar

- **Summary Card**
  - 标题：`当前偏好摘要`
  - 右上角：编辑按钮 `调整条件`
  - 内容：将 `decision.criteria_labels` 渲染为 Tag Group
- **Tag Styles**
  - 城市/地域：Blue tint tag
  - 年龄/身高：Cyan tint tag
  - 婚育/关系目标：Teal tint tag
  - 必须项：Dark blue solid tag
  - 偏好项：Light outlined tag
- **Missing Preference Hint**
  - 当偏好仍不完整时，底部显示提示卡
  - 文案示例：`你还没有明确城市范围，结果可能偏宽。`

### 3.4 Candidate Results Panel

- **Section Header**
  - 标题来自 `decision.result_group_title`
  - 右侧动作：`查看更多`、`保存订阅`
- **Candidate Cards**
  - 单列堆叠卡片，支持桌面端 2 列紧凑模式
  - 每张卡片包含：
    - 头像/照片
    - 姓名或昵称
    - 年龄、城市、身高
    - 推荐理由摘要
    - 匹配标签
    - CTA：`查看详情`
- **Result State Variants**
  - Loading：3 张 Skeleton 卡片
  - Result：正常候选人卡片列表
  - Empty：无结果插画 + 放宽条件按钮 + 保存订阅按钮

### 3.5 Bottom Composer

- **Input Field**
  - 占满宽度
  - Placeholder：`例如：我希望对方在上海，年龄 28 到 35 岁，最好也想认真结婚`
  - 支持多行自动增高，最多 4 行
- **Primary Send Button**
  - 文案：`发送`
  - Loading 状态带 spinner
- **Suggested Action Chips**
  - 映射 `decision.suggested_actions[].label`
  - 根据 `decision.suggested_actions[].style` 显示主次样式
  - 点击后携带 `semantic_payload`
- **Helper Text**
  - 小字提示：`系统会根据你的表达自动补全条件，不必一次说全。`

## 4. Backend-to-UI Mapping

### 会话级字段

- `session_id`
  - 显示在 Header 次级信息
  - 样式：12px Monospace / Slate text
- `requester_id`
  - 仅客服/运营模式显示在调试抽屉
- `profile_id`
  - 当前绑定目标档案 ID
  - 不在主界面直出，作为详情跳转上下文

### 决策级字段

- `decision.phase`
  - 映射 Header 阶段 Badge 和进度条状态
- `decision.assistant_message`
  - 映射 AI 主消息气泡正文
- `decision.criteria_labels`
  - 映射右侧偏好摘要 Tag 组
- `decision.suggested_actions[].label`
  - 映射底部快捷操作按钮文案
- `decision.suggested_actions[].style`
  - 映射按钮视觉层级
  - `primary` = 实心主按钮
  - `secondary` = 描边按钮
  - `ghost` = 轻量 Chip
- `decision.suggested_actions[].semantic_payload`
  - 不直接展示
  - 点击时作为隐藏动作参数提交
- `decision.result_group_title`
  - 映射候选人列表模块标题
- `decision.selected_candidates[].profile_id`
  - 候选人卡片主键
- `decision.selected_candidates[].reason_summary`
  - 映射卡片中的推荐理由文案

### 搜索结果级字段

- `search_response.results`
  - 作为候选人结果的主数据源
  - 每条建议渲染为 Candidate Card
- 推荐 Candidate Card 结构映射：
  - `profile_id`
  - `name` / `nickname`
  - `age`
  - `city`
  - `height`
  - `photo_url`
  - `reason_summary`
  - `matched_on[]`
  - `verified_label`

## 5. Detailed Interaction Specification

### 核心交互

- 用户输入 `user_message` 后：
  - 本地立即插入用户气泡
  - 发送按钮切换 Loading
  - 输入框临时禁用或保留可编辑态
  - 页面自动滚动到底部
- 系统返回后：
  - 渲染 `decision.assistant_message`
  - 更新 `decision.phase`
  - 更新右侧 `decision.criteria_labels`
  - 渲染 `decision.suggested_actions[]`
  - 如有结果，刷新 `search_response.results`

### Suggested Action 交互

- 点击某个快捷动作：
  - 立即进入选中态
  - 将 `action_id` 或 `semantic_payload` 发给后端
  - 不要求用户再次手输文本
- 若为高优先动作：
  - 使用主按钮样式
  - 示例：`开始搜索`、`保存为持续推荐`

### 搜索中状态

- 当 `decision.phase=searching`
  - 顶部阶段 Badge 显示搜索中
  - 会话流中插入“正在查找符合条件的人”系统提示条
  - 右侧结果区域显示 Skeleton 卡
  - 底部输入区可保留，但发送按钮进入轻禁用态，避免用户误触高频提交

### 无结果状态

- 当 `decision.phase=no_result`
  - 右侧结果区显示 Empty State
  - Empty State 包含：
    - 插画或抽象图形
    - 标题：`暂时没有完全符合条件的人`
    - 说明文字：鼓励放宽 1 到 2 个条件
    - 按钮：`放宽条件`、`保存订阅`、`重新描述需求`

### 查看候选人详情

- 点击候选人卡片：
  - 桌面端：右侧抽屉打开详情
  - 移动端：全屏详情页打开
  - 带入 `profile_id`

## 6. Visual Design System

### Color Tokens

- `Primary / 600` = `#2563EB`
- `Primary / 50` = `#EFF6FF`
- `Trust / 600` = `#0F766E`
- `Trust / 50` = `#ECFDF5`
- `Accent / 500` = `#06B6D4`
- `Warning / 500` = `#F59E0B`
- `Danger / 600` = `#DC2626`
- `Text / Strong` = `#0F172A`
- `Text / Secondary` = `#475569`
- `Text / Tertiary` = `#94A3B8`
- `Border / Subtle` = `#E2E8F0`
- `Surface / Base` = `#F8FAFC`
- `Surface / Card` = `#FFFFFF`

### Typography

- Page Title: `28/34 Semibold`
- Section Title: `18/26 Semibold`
- Card Title: `16/24 Medium`
- Body: `14/22 Regular`
- Secondary Meta: `12/18 Regular`
- Button Label: `14/20 Medium`
- Number/Code: `12/18 Medium Monospace`

### Spacing & Radius

- Base unit: `8`
- Page section gap: `24`
- Card internal padding: `20` 或 `24`
- Bubble gap: `12`
- Tag gap: `8`
- Radius:
  - Input `12`
  - Button `12`
  - Card `16`
  - Chip `999`

### Elevation

- Level 1: 轻阴影用于卡片
- Level 2: Hover 卡片或抽屉
- Level 3: 全局浮层、候选人详情抽屉

## 7. Editability Requirements

- 所有区块需按 Figma/Sketch 可编辑结构拆层：
  - `Page / Discovery Session`
  - `Header / Phase Meta`
  - `Main / Conversation Panel`
  - `Main / Preference Sidebar`
  - `Main / Results Panel`
  - `Bottom / Composer`
- 每个消息项、Tag、卡片、按钮为独立组件实例
- 候选人卡片使用可复用组件：
  - `Candidate Card / Default`
  - `Candidate Card / Hover`
  - `Candidate Card / Loading`
  - `Candidate Card / Empty`
- 快捷动作使用变体组件：
  - `Action Chip / Primary`
  - `Action Chip / Secondary`
  - `Action Chip / Ghost`
- 阶段 Badge 使用状态变体：
  - `Phase Badge / Collecting`
  - `Phase Badge / Searching`
  - `Phase Badge / Results`
  - `Phase Badge / Empty`

## 8. Deliverable Expectation

请按高保真方式渲染此页面，确保：

- 会话区、偏好摘要区、候选人区具备真实产品质感
- 所有输入、卡片、消息、标签间距统一
- Loading、Empty、Result 三种状态完整
- 页面可直接作为 Web/App UI 设计稿基础
- 所有层级、约束、Auto Layout 结构清晰，便于后续继续扩展为设计系统组件
