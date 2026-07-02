# 多类型认证审核系统 - 完整落地方案

**实施日期**: 2026-07-02
**实施方案**: 方案A（统一审核工作台，多Tab管理）
**预计工期**: 2-3天
**实施策略**: 快速扩展 + 高优先级优先

---

## 📋 Context

**背景**:
- 用户A完成学历认证 → 需要管理员审核 → **学历认证审核界面已完成**
- 其他认证类型（职业、收入、活体视频、照片风险、举报、申诉）→ **后端API完备，但前端审核界面缺失**

**现状分析**:
- ✅ 后端审核API全部完备
- ✅ 学历认证审核界面已完成（含PDF预览、审核历史、批量审核、统计、通知等优化）
- ❌ 其他认证类型审核界面缺失
- ❌ 管理员无法通过可视化界面审核其他类型

**目标**:
- 为所有认证类型提供统一审核界面
- 在运营工作台统一管理（多Tab切换）
- 完善审核功能（批量审核、统计、通知等）
- 提升审核效率和用户体验

---

## 🎯 认证审核类型清单

| 认证类型 | 后端API | 前端界面 | 优先级 | 复用性 | 预估时间 |
|----------|---------|----------|--------|--------|----------|
| **学历认证** | ✅ 完备 | ✅ 已完成 | — | 高（基准） | — |
| **职业认证** | ✅ 完备 | ❌ 缺失 | ⭐⭐⭐ 中 | ✅ 高（复用学历） | 0.5小时 |
| **收入认证** | ✅ 完备 | ❌ 缺失 | ⭐⭐⭐ 中 | ✅ 高（复用学历） | 0.5小时 |
| **活体视频认证** | ✅ 完备 | ❌ 缺失 | ⭐⭐⭐⭐⭐ 高 | ⚠️ 低（需新界面） | 1小时 |
| **举报审核** | ✅ 完备 | ❌ 缺失 | ⭐⭐⭐⭐ 高 | ⚠️ 低（需新界面） | 1小时 |
| **照片风险审核** | ✅ 完备 | ❌ 缺失 | ⭐⭐ 低 | ⚠️ 低（需新界面） | 1小时 |
| **申诉审核** | ✅ 完备 | ❌ 缺失 | ⭐ 低 | ⚠️ 低（需新界面） | 1小时 |

**总计预估时间**: 约5小时（实际可能更快）

---

## 💡 实施策略

### **核心策略**: 复用优先 + 快速扩展 + 高优先级优先

1. **高复用性类型优先**（职业/收入认证）
   - 直接复用学历认证界面
   - 修改字段选项即可
   - 快速扩展，验证复用方案可行性

2. **高优先级类型优先**（活体视频/举报审核）
   - 安全性和用户体验优先
   - 开发新审核界面
   - 满足核心业务需求

3. **低优先级类型后做**（照片风险/申诉审核）
   - 审核量相对较少
   - 可以后续扩展
   - 不影响核心业务

---

## 🏗️ 技术架构设计

### **统一审核工作台架构**

```
运营工作台 (/ops/workbench)
├─ [Tab切换]
│  ├─ 运营协作（原有功能）
│  └─ 资料审核（新增主Tab）
│     ├─ [子Tab切换]
│     ├─ 字段认证审核
│     │  ├─ 学历认证（已完成）
│     │  ├─ 职业认证（复用学历界面）
│     │  └─ 收入认证（复用学历界面）
│     ├─ 活体视频审核（新界面）
│     ├─ 举报审核（新界面）
│     ├─ 照片风险审核（新界面）
│     └─ 申诉审核（新界面）
```

### **组件复用策略**

| 功能模块 | 复用来源 | 复用程度 |
|----------|----------|----------|
| **审核队列列表** | 学历认证队列 | 100%复用 |
| **审核详情面板** | 学历认证详情面板 | 80%复用 |
| **批量审核功能** | 学历认证批量审核 | 100%复用 |
| **审核统计组件** | 学历认证统计 | 100%复用 |
| **审核历史组件** | 学历认证历史 | 100%复用 |
| **PDF/图片预览** | 学历认证预览 | 100%复用 |

---

## 📊 详细实施步骤

### **Phase 1: 扩展字段认证审核（职业/收入）**

**目标**: 快速扩展职业认证和收入认证审核界面

**实施方案**:
1. 修改学历认证审核队列筛选逻辑，支持field_key参数
2. 在字段认证审核界面添加子Tab切换（学历/职业/收入）
3. 修改审核表单字段选项：
   - 学历认证：高中/大专/本科/硕士/博士
   - 职业认证：程序员/医生/教师/工程师/设计师/其他
   - 收入认证：5万以下/5-10万/10-20万/20-50万/50万以上

**技术实现**:
```typescript
// 审核队列筛选
const loadQueue = useCallback(async (fieldKey: string) => {
  const data = await fetchReviewQueue({
    status: 'submitted,under_review',
    field_key: fieldKey, // education/job/income
    limit: 20,
  })
  setQueue(data)
}, [])

// 审核表单选项配置
const FIELD_OPTIONS = {
  education: ['高中', '大专', '本科', '硕士', '博士'],
  job: ['程序员', '医生', '教师', '工程师', '设计师', '其他'],
  income: ['5万以下', '5-10万', '10-20万', '20-50万', '50万以上'],
}
```

**新增文件**: 无（直接修改现有组件）
**修改文件**: 3个（审核主组件、队列列表、详情面板）
**预估时间**: 0.5小时

---

### **Phase 2: 活体视频认证审核**

**目标**: 开发活体视频认证审核界面

**功能需求**:
1. 视频审核队列列表
2. 视频播放器组件
3. 活体检测结果展示（点头、眨眼、张嘴等动作）
4. 人脸匹配结果展示
5. 审核操作表单（通过/驳回）
6. 审核历史记录

**技术实现**:
```typescript
// 视频审核API
export async function fetchVideoReviewQueue(): Promise<VideoSubmission[]> {
  return gatewayJson('/v1/verifications/live-video-submissions', { includeAuth: true })
}

// 视频审核操作
export async function reviewVideoVerification(params: {
  submissionId: string
  decision: 'approve' | 'reject'
  reviewNote?: string
  livenessResult?: any
  faceMatchResult?: any
}): Promise<ReviewResult> {
  return gatewayJson(`/v1/verifications/live-video-submissions/${params.submissionId}/review`, {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify(params),
  })
}

// 视频播放器组件
<VideoPlayer
  src={submission.video_url}
  challenges={submission.challenges} // 挑战动作列表
  livenessResult={submission.liveness_result} // 活体检测结果
/>
```

**新增文件**: 4个
- `frontend/her-app/components/her/verification-review/video-review-tab.tsx`（主组件）
- `frontend/her-app/components/her/verification-review/video-player.tsx`（视频播放器）
- `frontend/her-app/components/her/verification-review/liveness-result-panel.tsx`（活体检测结果）
- `frontend/her-app/lib/api/endpoints/video-verification.ts`（API）

**修改文件**: 1个（审核主组件添加Tab）
**预估时间**: 1小时

---

### **Phase 3: 举报审核界面**

**目标**: 开发举报案例审核界面

**功能需求**:
1. 举报案例队列列表
2. 举报详情面板
   - 举报原因（骚扰、诈骗、虚假资料、行为异常等）
   - 举报证据（聊天记录截图、照片等）
   - 被举报用户信息
3. 审核操作表单
   - 处理决定：属实/不属实/需补充证据
   - 处罚措施：警告/封禁3天/封禁7天/永久封禁/解封
   - 审核备注
4. 审核历史记录

**技术实现**:
```typescript
// 举报审核API
export async function fetchReportReviewQueue(): Promise<ReportCase[]> {
  return gatewayJson('/v1/profile-review/risk-cases', { includeAuth: true })
}

// 举报审核操作
export async function reviewReportCase(params: {
  caseId: string
  decision: 'valid' | 'invalid' | 'need_evidence'
  penalty?: 'warning' | 'ban_3d' | 'ban_7d' | 'ban_permanent' | 'unban'
  reviewNote?: string
}): Promise<ReviewResult> {
  return gatewayJson(`/v1/profile-review/risk-cases/${params.caseId}/review`, {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify(params),
  })
}
```

**新增文件**: 3个
- `frontend/her-app/components/her/verification-review/report-review-tab.tsx`（主组件）
- `frontend/her-app/components/her/verification-review/report-detail-panel.tsx`（举报详情）
- `frontend/her-app/lib/api/endpoints/report-review.ts`（API）

**修改文件**: 1个（审核主组件添加Tab）
**预估时间**: 1小时

---

### **Phase 4: 照片风险审核**

**目标**: 开发照片风险审核界面

**功能需求**:
1. 照片审核队列列表（显示AI风险评分）
2. 照片详情面板
   - 照片展示（大图预览）
   - AI风险评分（0-100分，高风险标记）
   - AI检测结果（是否合成、是否盗用）
3. 审核操作表单
   - 审核决定：真实/合成/盗用/其他
   - 审核备注
4. 批量审核功能（批量通过真实照片）

**技术实现**:
```typescript
// 照片审核API
export async function fetchPhotoRiskQueue(): Promise<PhotoRiskItem[]> {
  return gatewayJson('/v1/profile-review/photo-risk/review-queue', { includeAuth: true })
}

// 照片审核操作
export async function reviewPhotoRisk(params: {
  photoId: string
  decision: 'real' | 'synthetic' | 'stolen' | 'other'
  reviewNote?: string
}): Promise<ReviewResult> {
  return gatewayJson(`/v1/profile-review/photo-risk/${params.photoId}/review`, {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify(params),
  })
}
```

**新增文件**: 3个
- `frontend/her-app/components/her/verification-review/photo-risk-tab.tsx`（主组件）
- `frontend/her-app/components/her/verification-review/photo-detail-panel.tsx`（照片详情）
- `frontend/her-app/lib/api/endpoints/photo-risk.ts`（API）

**修改文件**: 1个（审核主组件添加Tab）
**预估时间**: 1小时

---

### **Phase 5: 申诉审核界面**

**目标**: 开发申诉案例审核界面

**功能需求**:
1. 申诉案例队列列表
2. 申诉详情面板
   - 申诉理由
   - 申诉证据材料
   - 原处罚信息（为什么被封）
3. 审核操作表单
   - 审核决定：接受申诉/驳回申诉
   - 处理结果：解封/维持封禁
   - 审核备注
4. 审核历史记录

**技术实现**:
```typescript
// 申诉审核API
export async function fetchAppealReviewQueue(): Promise<AppealCase[]> {
  return gatewayJson('/v1/profile-review/case-appeals', { includeAuth: true })
}

// 申诉审核操作
export async function reviewAppeal(params: {
  appealId: string
  decision: 'accept' | 'reject'
  result?: 'unban' | 'maintain'
  reviewNote?: string
}): Promise<ReviewResult> {
  return gatewayJson(`/v1/profile-review/case-appeals/${params.appealId}/review`, {
    method: 'POST',
    includeAuth: true,
    body: JSON.stringify(params),
  })
}
```

**新增文件**: 3个
- `frontend/her-app/components/her/verification-review/appeal-review-tab.tsx`（主组件）
- `frontend/her-app/components/her/verification-review/appeal-detail-panel.tsx`（申诉详情）
- `frontend/her-app/lib/api/endpoints/appeal-review.ts`（API）

**修改文件**: 1个（审核主组件添加Tab）
**预估时间**: 1小时

---

### **Phase 6: 创建完整使用文档**

**目标**: 创建所有审核类型的完整使用文档

**文档内容**:
1. 统一审核工作台使用指南
2. 各审核类型操作流程
3. 审核规范和注意事项
4. 常见问题解答

**新增文件**: 2个
- `docs/design-pages/unified-review-workbench-usage-guide.md`（使用指南）
- `docs/design-pages/unified-review-workbench-complete-summary.md`（实施总结）

**预估时间**: 0.5小时

---

## 🔧 统一审核工作台设计

### **UI布局**

```
┌─────────────────────────────────────────────────────┐
│  [运营协作] [资料审核]                                  │ ← 主Tab
├─────────────────────────────────────────────────────┤
│  [学历] [职业] [收入] [活体视频] [举报] [照片] [申诉]   │ ← 子Tab
├─────────────────────────────────────────────────────┤
│  审核统计概览                                          │ ← 统计面板
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                  │
│  │今日审核│ │通过率 │ │待审核│ │平均时长│                  │
│  └──────┘ └──────┘ └──────┘ └──────┘                  │
├─────────────────────────────────────────────────────┤
│  审核队列列表                                          │ ← 队列列表
│  ┌───────────────────────────────────────┐            │
│  │ 用户 #123 | 本科认证 | 10分钟前 | [待审核] │            │
│  └───────────────────────────────────────┘            │
│  ┌───────────────────────────────────────┐            │
│  │ 用户 #456 | 硕士认证 | 1小时前 | [审核中] │            │
│  └───────────────────────────────────────┘            │
├─────────────────────────────────────────────────────┤
│  [点击卡片弹出] 审核详情面板 (BottomSheet)              │ ← 详情面板
│  ┌───────────────────────────────────────┐            │
│  │ 用户信息 + 提交时间                      │            │
│  │ ─────────────────────────────────────  │            │
│  │ 材料预览 (图片/PDF/视频)                 │            │
│  │ ─────────────────────────────────────  │            │
│  │ 审核历史记录                            │            │
│  │ ─────────────────────────────────────  │            │
│  │ 审核操作表单                            │            │
│  │ [通过] [驳回] [补件]                     │            │
│  │ 审核备注: [____________]                 │            │
│  │ [提交审核]                              │            │
│  └───────────────────────────────────────┘            │
└─────────────────────────────────────────────────────┘
```

### **组件架构**

```typescript
// 统一审核工作台主组件
export default function UnifiedReviewWorkbench() {
  const [activeField, setActiveField] = useState<'education' | 'job' | 'income'>('education')
  const [activeTab, setActiveTab] = useState<'field' | 'video' | 'report' | 'photo' | 'appeal'>('field')

  return (
    <div>
      {/* 子Tab切换 */}
      <SubTabSwitcher activeTab={activeTab} onSwitch={setActiveTab} />

      {/* 统计面板 */}
      <ReviewStatisticsPanel type={activeTab} />

      {/* 根据Tab渲染不同审核队列 */}
      {activeTab === 'field' && (
        <FieldReviewTab fieldKey={activeField} />
      )}
      {activeTab === 'video' && (
        <VideoReviewTab />
      )}
      {activeTab === 'report' && (
        <ReportReviewTab />
      )}
      {activeTab === 'photo' && (
        <PhotoRiskTab />
      )}
      {activeTab === 'appeal' && (
        <AppealReviewTab />
      )}
    </div>
  )
}
```

---

## 📈 性能优化策略

### **1. 数据加载优化**

```typescript
// 分页加载
const loadQueue = useCallback(async (page: number = 1) => {
  const data = await fetchReviewQueue({
    page,
    limit: 20,
  })
  setQueue(data)
}, [])

// 增量加载
const loadMore = useCallback(async () => {
  const nextPage = page + 1
  const newData = await fetchReviewQueue({ page: nextPage, limit: 20 })
  setQueue([...queue, ...newData])
}, [queue, page])
```

### **2. 组件懒加载**

```typescript
// 按需加载不同审核类型组件
const VideoReviewTab = lazy(() => import('./video-review-tab'))
const ReportReviewTab = lazy(() => import('./report-review-tab'))
const PhotoRiskTab = lazy(() => import('./photo-risk-tab'))
const AppealReviewTab = lazy(() => import('./appeal-review-tab'))
```

### **3. 缓存优化**

```typescript
// 使用React Query缓存
const { data: queue } = useQuery({
  queryKey: ['reviewQueue', activeTab, activeField],
  queryFn: () => fetchReviewQueue({ field_key: activeField }),
  staleTime: 2 * 60 * 1000, // 2分钟缓存
})
```

---

## 🔐 权限控制策略

### **角色权限映射**

| 审核类型 | 需要角色 | 权限组 |
|----------|----------|--------|
| 字段认证审核 | `profile_reviewer` / `platform_admin` | PROFILE_REVIEW_ROLES |
| 活体视频审核 | `risk_reviewer` / `platform_admin` | VERIFICATION_REVIEW_ROLES |
| 举报审核 | `risk_reviewer` / `customer_support` / `platform_admin` | CHAT_RISK_REVIEW_ROLES |
| 照片风险审核 | `risk_reviewer` / `platform_admin` | VERIFICATION_REVIEW_ROLES |
| 申诉审核 | `risk_reviewer` / `platform_admin` | CHAT_RISK_REVIEW_ROLES |

### **权限验证逻辑**

```typescript
// 前端权限检查
const canReviewField = roles.includes('profile_reviewer') || roles.includes('platform_admin')
const canReviewVideo = roles.includes('risk_reviewer') || roles.includes('platform_admin')
const canReviewReport = roles.includes('risk_reviewer') || roles.includes('customer_support') || roles.includes('platform_admin')

// 无权限时隐藏Tab
{canReviewField && <TabButton>字段认证</TabButton>}
{canReviewVideo && <TabButton>活体视频</TabButton>}
{canReviewReport && <TabButton>举报审核</TabButton>}
```

---

## 📊 验收标准

### **功能验收**

| 功能模块 | 验收标准 |
|----------|----------|
| 字段认证审核 | ✅ 支持学历/职业/收入三种类型审核 |
| 活体视频审核 | ✅ 视频播放正常，活体检测结果展示清晰 |
| 举报审核 | ✅ 举报证据展示完整，处理流程完整 |
| 照片风险审核 | ✅ AI评分显示准确，审核操作流畅 |
| 申诉审核 | ✅ 申诉材料展示完整，审核流程清晰 |
| 统计面板 | ✅ 统计数据准确，实时更新 |
| 批量审核 | ✅ 批量操作成功，结果提示清晰 |
| 审核历史 | ✅ 历史记录展示完整，时间线清晰 |

### **性能验收**

- ✅ 页面加载时间 < 2秒
- ✅ 队列加载时间 < 1秒
- ✅ 审核提交响应 < 500ms
- ✅ 视频播放流畅，无卡顿

### **用户体验验收**

- ✅ UI美观，符合设计规范
- ✅ 操作流程简洁，不超过3步
- ✅ 错误提示清晰，有重试机制
- ✅ 加载状态明确，有进度提示

---

## 🚀 实施时间计划

| Phase | 任务 | 预估时间 | 累计时间 |
|-------|------|----------|----------|
| Phase 1 | 扩展字段认证审核 | 0.5小时 | 0.5小时 |
| Phase 2 | 活体视频认证审核 | 1小时 | 1.5小时 |
| Phase 3 | 举报审核界面 | 1小时 | 2.5小时 |
| Phase 4 | 照片风险审核 | 1小时 | 3.5小时 |
| Phase 5 | 申诉审核界面 | 1小时 | 4.5小时 |
| Phase 6 | 创建使用文档 | 0.5小时 | 5小时 |

**总计预估**: 5小时（实际可能更快，AI辅助开发）

---

## 🎯 成功指标

### **业务指标**

- ✅ 审核效率提升 300%（批量审核）
- ✅ 审核覆盖率 100%（所有类型都有界面）
- ✅ 审核员满意度 > 90%（界面简洁好用）
- ✅ 用户等待时间减少 50%（审核通知及时）

### **技术指标**

- ✅ 代码复用率 > 70%（组件复用）
- ✅ 代码质量高（遵循规范）
- ✅ 文档完善（使用指南完整）
- ✅ 扩展性强（可快速添加新类型）

---

## 📖 后续扩展建议

### **短期扩展（可选）**

1. **审核员绩效统计**
   - 每个审核员审核数量
   - 审核准确率统计
   - 审核速度排行榜

2. **审核任务分配**
   - 自动分配审核任务
   - 审核员工作量均衡
   - 审核优先级排序

3. **审核质量监控**
   - 审核结果抽检
   - 审核错误率统计
   - 审核员培训建议

### **长期扩展（可选）**

4. **AI辅助审核**
   - OCR自动识别（学历/职业证书）
   - 人脸自动匹配（活体视频）
   - 举报智能分类（自动判断类型）
   - 照片风险智能评分（AI自动打分）

5. **审核工作流引擎**
   - 审核流程可视化
   - 审核节点自定义
   - 审核规则配置
   - 审核触发器

---

## 🎊 总结

**核心成果**:
- ✅ 统一审核工作台（所有类型统一管理）
- ✅ 6种审核类型全覆盖（字段/视频/举报/照片/申诉）
- ✅ 高代码复用率（70%组件复用）
- ✅ 完善审核功能（批量/统计/历史/通知）
- ✅ 完整使用文档（操作指南完整）

**关键优势**:
1. **快速交付**: 5小时完成所有类型
2. **低成本**: 高组件复用率，维护成本低
3. **易扩展**: 可快速添加新审核类型
4. **用户友好**: 统一入口，简洁操作

---

**准备开始实施！**