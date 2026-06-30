# Her 前端改进方案

> 文档版本：2026-05-21  
> 适用范围：`frontend/her-app`  
> 目标：从「设计稿 + Demo 导航 + 部分联调」升级为可上线、可维护的生产前端。

---

## 目录

1. [一句话目标](#一句话目标)
2. [现状与问题摘要](#现状与问题摘要)
3. [改进前后对比（白话）](#改进前后对比白话)
4. [分步施工计划（白话）](#分步施工计划白话)
5. [目标架构（技术）](#目标架构技术)
6. [分阶段实施方案](#分阶段实施方案)
7. [关键文件改造对照](#关键文件改造对照)
8. [环境变量规范](#环境变量规范)
9. [错误处理规范](#错误处理规范)
10. [后端接口对齐清单](#后端接口对齐清单)
11. [依赖与 UI 组件清理](#依赖与-ui-组件清理)
12. [排期与人力](#排期与人力)
13. [上线验收总清单](#上线验收总清单)
14. [建议 PR 拆分](#建议-pr-拆分)
15. [相关文档](#相关文档)

---

## 一句话目标

把前端从 **「能演示的样板房」** 改成 **「用户真能用、出错能看出来、程序员好改」** 的正式 App。

---

## 现状与问题摘要

### 当前是什么状态？

- 界面完整，但 **部分数据写死在代码里**（演示数据），只有登录、发现、聊天等 **部分功能** 接了 Gateway。
- 开发用的 **右下角页面跳转菜单** 会打进生产构建。
- 几乎所有逻辑挤在 **`app/page.tsx`（约 541 行）** 一个文件里。

### 问题分类

| 类别 | 主要问题 |
|------|----------|
| **架构** | 单文件承载路由 + 认证 + 主 Tab；无 App Router 页面拆分；Demo 导航常驻 |
| **数据** | Mock 与真实 API 混用；失败时静默回退假数据；资料/详情/认证/Onboarding 未接 API |
| **工程** | `typescript.ignoreBuildErrors: true`；ESLint 未安装；几乎无单元测试 |
| **UI** | `components/ui` 约 57 个 shadcn 组件，业务页几乎未使用；两套 UI 体系 |
| **安全** | `NEXT_PUBLIC_HER_PROFILE_SOURCE_DSN` 暴露数据库连接；Token 仅存 localStorage |
| **体验** | 错误处理不一致；未读角标写死；聊天标题用 participant_id |

更完整的问题列表见前期代码审查结论（可对仓库 git 历史或评审记录追溯）。

---

## 改进前后对比（白话）

| 维度 | 现在 | 改完之后 |
|------|------|----------|
| 用户填资料 | 可能只存在网页里，没存服务器 | 保存到服务器，刷新仍在 |
| 接口挂了 | 仍显示假推荐、假聊天 | 提示「加载失败」，可重试 |
| 右下角菜单 | 生产环境也有 | 仅开发环境可见 |
| 改一个功能 | 动 500+ 行大文件 | 按模块修改 |
| 上线前检查 | 能 `build` 即可 | 类型 + Lint + 测试均通过 |

---

## 分步施工计划（白话）

按顺序执行，不建议跳步。

```
第 1 步 拆危险品（止血）
    ↓
第 2 步 装门禁监控（工程基线）
    ↓
第 3 步 分房间装修（架构拆分）
    ↓
第 4 步 接通水电（数据真实化，需后端）
    ↓
第 5 步 统一装修 + 验收（UI 统一与测试）
```

| 步骤 | 工期（参考） | 核心产出 |
|------|--------------|----------|
| 第 1 步 | 1～2 天 | 生产无 Demo 菜单；DSN 不进客户端；鉴权统一 |
| 第 2 步 | 2～3 天 | TS 构建校验；ESLint；删死代码；CI |
| 第 3 步 | 5～7 天 | `page.tsx` 拆分为模块；API 层独立 |
| 第 4 步 | 7～10 天 | 各页接真实 API；Mock 仅 dev 可选 |
| 第 5 步 | 3～5 天 | 统一 UI；E2E/单元测试扩展 |

**总计约 4～6 周**（1 名熟悉 Next.js 的前端；第 4 步依赖后端接口）。

### 今天就能做的 3 件事（收益最大）

1. **隐藏** 生产环境右下角 Demo 导航  
2. **打开** TypeScript 构建检查（去掉 `ignoreBuildErrors`），修复报错  
3. **约定**：接口失败必须展示错误，禁止静默 Mock  

---

## 目标架构（技术）

### 目录结构（终态）

```
frontend/her-app/
├── app/
│   ├── layout.tsx              # ThemeProvider、Toaster、ErrorBoundary
│   ├── (auth)/                 # 登录相关路由组（Phase 6 可选）
│   ├── (main)/                 # 主应用
│   └── api/gateway/[...path]/route.ts
├── lib/
│   ├── api/                    # gateway 客户端、endpoints
│   ├── auth/                   # session、auth-api
│   ├── env.ts                  # 环境变量 zod 校验
│   └── types/                  # 共享 API 类型
├── hooks/                      # useAuth、useDiscovery、useChat...
├── components/
│   ├── app/                    # AppShell、DemoNav（仅 dev）
│   ├── her/                    # 业务 UI
│   └── ui/                     # shadcn（删除未引用）
└── tests/
    ├── unit/
    └── e2e/
```

### 路由策略

| 方案 | 说明 | 建议阶段 |
|------|------|----------|
| **B. 壳路由 + 状态机** | 仍单入口，拆 `AppShell` + navigation store | Phase 2（过渡） |
| **A. App Router 真路由** | `/discover`、`/chat/[id]` 等 | Phase 6（可选） |

---

## 分阶段实施方案

### Phase 0：止血（1～2 天，必须先做）

**目标**：消除安全与「假上线」风险。

| # | 任务 | 具体做法 |
|---|------|----------|
| 0.1 | 移除生产 Demo 导航 | `DemoNav` 仅在 `NODE_ENV === 'development'` 或 `NEXT_PUBLIC_ENABLE_DEMO_NAV=true` 时渲染 |
| 0.2 | DSN 移出客户端 | `NEXT_PUBLIC_HER_PROFILE_SOURCE_DSN` → 服务端 `HER_PROFILE_SOURCE_DSN`；写回走 BFF/网关 |
| 0.3 | 统一鉴权头 | `gatewayJson`：有 token 默认带 `Authorization`；写操作显式校验 |
| 0.4 | JSON 解析安全 | 对空 body、非 JSON 做 try/catch，抛出 `GatewayClientError` |
| 0.5 | 删除调试残留 | 移除或 gitignore `one_tap_probe.js`、`test-results/` |

**验收**

- [x] 生产 build 无右下角 Demo 菜单  
- [x] 客户端 bundle 无 `mysql://` 等 DSN  
- [x] 登录后需鉴权接口均带 `Bearer`  

---

### Phase 1：工程基线（2～3 天）

**目标**：构建与 CI 真实拦住问题。

| # | 任务 | 具体做法 |
|---|------|----------|
| 1.1 | 恢复类型检查 | 删除 `next.config.mjs` 中 `typescript.ignoreBuildErrors` |
| 1.2 | 接入 ESLint | `eslint` + `typescript-eslint` flat config；`pnpm lint` 进 CI |
| 1.3 | 环境变量校验 | `lib/env.ts` + zod 校验必填项 |
| 1.4 | 包名与脚本 | `"name": "her-app"`；README 统一包管理器说明 |
| 1.5 | 清理死代码 | 删除未引用：`auth-flow.tsx`、`recommendations-page.tsx`（或合并）、`styles/globals.css`；合并重复 hook |
| 1.6 | CI | `lint` + `build` + `e2e:her:stub` |

**验收**

- [x] `npm run build` 无 TS 错误  
- [x] `npm run lint` 通过（CI 已配置）  

---

### Phase 2：架构重构（5～7 天）

**目标**：拆掉巨型 `page.tsx`，建立分层。

#### 2.1 导航与壳

- `lib/navigation/`：`types.ts`、`app-store.ts`（或 zustand）  
- `components/app/app-shell.tsx`、`demo-nav.tsx`（仅 dev）  
- `app/page.tsx` 目标 **< 80 行**  

#### 2.2 认证模块

```
lib/auth/
  session.ts        # token 读写（抽象 storage）
  auth-api.ts       # SMS / 微信 / 一键登录 API
  use-auth-flow.ts  # 状态机
```

- 去掉硬编码 `wx-code-1`、`carrier-token-1`：仅 `NEXT_PUBLIC_USE_AUTH_STUB=true` 且 development 使用  
- `device_id` 由 `lib/device-id.ts` 生成并持久化  

#### 2.3 API 层

```
lib/api/
  client.ts         # gatewayJson
  errors.ts
  endpoints/
    discovery.ts
    recommendation.ts
    chat.ts
    trust.ts
    profile.ts
```

#### 2.4 共享类型

扩展 `lib/types/`（`candidate`、`discovery`、`chat`、`trust`、`profile`、`auth`），删除页面内重复 `type XxxResponse`。

**验收**

- [x] 认证 API 改动只动 `lib/auth/auth-api.ts`  
- [x] 业务组件不直接 `JSON.parse`（统一 `gatewayJson`）  

---

### Phase 3：数据真实化（7～10 天，需后端对齐）

**目标**：用户可见页面接 API，或明确「未配置 / 失败」。

#### Mock 统一规则

```ts
// lib/mock.ts
export const useMockFallback =
  process.env.NODE_ENV === 'development' &&
  process.env.NEXT_PUBLIC_ALLOW_MOCK_FALLBACK === 'true'
```

| 环境 | API 失败时 |
|------|------------|
| **生产** | 错误页 / Toast，**禁止** Mock |
| **开发 + 开关开** | 可 Mock + 顶部 Banner「演示数据」 |
| **开发 + 开关关** | 同生产 |

**禁止** 空 `catch {}` 静默吞错（`discover-page`、`chat-page`、`relationships-page` 等需改造）。

#### 按页面接 API

| 页面 | 现状 | 改进 |
|------|------|------|
| Profile | 硬编码 | `GET/PATCH` 用户资料 API |
| Candidate Detail | 本地字典 | `GET /v1/candidates/:id` 或卡片 payload |
| Onboarding | 无提交 | `POST`  onboarding / profile |
| Verification Flow | 纯 UI | trust-hub 提交 + 上传 |
| Account Recovery | 纯 UI | 接 API 或隐藏入口 |
| Discover | 部分 | `submitTurn` 失败 Toast；无 session 引导重试 |
| Relationships | 依赖 env | 登录响应写入 `case_id` |
| Chat | 部分 | 昵称展示；发送失败回滚 optimistic |
| Trust Center | 已有 | 作为错误态模板推广 |

#### Session

登录成功后持久化：

```ts
type SessionContext = {
  accessToken: string
  userId: string
  requesterId: number
  profileId: number
  caseId?: string
}
```

`NEXT_PUBLIC_*` 仅作开发默认值；运行时以登录响应为准。

#### 未读角标

`inboxUnreadCount`、`chatUnreadCount` 改为 API 拉取，去掉 `page.tsx` 硬编码。

**验收**

- [x] 生产关闭 Mock 后断网显示错误  
- [x] Onboarding 完成后写入 `profiles`（`PATCH /v1/auth/onboarding`）  
- [ ] E2E：登录 → 发现 → 推荐动作 → 聊天 → 资料（需 Gateway 联调手跑）  

---

### Phase 4：UI 统一 + 错误体验（4～5 天）

| # | 任务 |
|---|------|
| 4.1 | `knip` / `ts-prune` 审计，删除未使用 `components/ui` |
| 4.2 | 业务页改用 `Button`、`Input`、`Dialog`、`Toaster` |
| 4.3 | `layout.tsx` 挂载全局 Toaster；API 错误统一 `toast.error` |
| 4.4 | 每页：Loading（Skeleton）/ Empty / Error 三态 |
| 4.5 | `ThemeProvider`（next-themes）接入 layout；收敛 `theme-toggle` 自研逻辑 |

---

### Phase 5：性能、可访问性、测试（3～5 天）

| # | 任务 |
|---|------|
| 5.1 | `images.remotePatterns`；去掉 unsplash 硬编码；`unoptimized: false` |
| 5.2 | 大页 `dynamic import` 懒加载 |
| 5.3 | 拆分 `discover-page`（Header / Chat / Carousel / Inbox） |
| 5.4 | 表单 a11y；移除 `metadata.generator: v0.app` |
| 5.5 | 单元测试：gateway、auth 状态机、env；扩展 E2E |

---

### Phase 6（可选）：App Router + 安全加固

- 文件路由：`(auth)` / `(main)`，`/chat/[conversationId]`  
- Token：中期 BFF httpOnly Cookie；长期 refresh token  
- 聊天 WebSocket / SSE、未读推送  

---

## 关键文件改造对照

| 现有 | 终态 |
|------|------|
| `app/page.tsx`（541 行） | 薄入口 + `components/app/*` + hooks |
| `lib/gateway.ts` | `lib/api/client.ts` + `lib/auth/session.ts` |
| `lib/her-types.ts` | `lib/types/*.ts` |
| `lib/runtime-context.ts` | 合并入 session 或删除 |
| `components/theme-provider.tsx` | 接入 `app/layout.tsx` |
| `components/her/profile-page.tsx` | + `useProfile()` |
| `components/her/candidate-detail-page.tsx` | + `useCandidate(id)` |
| `components/her/auth/onboarding-page.tsx` | + `submitOnboarding()` |
| Demo 导航 | `components/app/demo-nav.tsx`（仅 dev） |

---

## 环境变量规范

### 终态示例（`.env.example`）

```bash
# 服务端 only（不可 NEXT_PUBLIC）
PARTNER_GATEWAY_BASE_URL=http://127.0.0.1:8080
PARTNER_GATEWAY_API_KEY=
HER_PROFILE_SOURCE_DSN=
HER_PROFILE_SOURCE_TABLE=profiles

# 客户端
NEXT_PUBLIC_HER_USER_ID=              # 仅 dev 默认；登录后由 session 覆盖
NEXT_PUBLIC_HER_REQUESTER_ID=
NEXT_PUBLIC_HER_PROFILE_ID=
NEXT_PUBLIC_HER_CASE_ID=

# 行为开关
NEXT_PUBLIC_ALLOW_MOCK_FALLBACK=false
NEXT_PUBLIC_ENABLE_DEMO_NAV=false
NEXT_PUBLIC_USE_AUTH_STUB=false
```

### 校验

`lib/env.ts` 在启动时 zod 校验；开发缺项时 Console 报错 + 可选 ConfigError 页。

---

## 错误处理规范

```tsx
const { data, isLoading, error, refetch } = useDiscoverySession()

if (isLoading) return <DiscoverPageSkeleton />
if (error) return <ErrorState message={error.message} onRetry={refetch} />
if (!data?.length) return <EmptyRecommendations />
```

- **禁止**：`catch {}` 静默失败  
- **允许**：`useMockFallback` 时回退 Mock + 「演示数据」Banner  

---

## 后端接口对齐清单

Phase 3 开工前与后端确认：

| # | 能力 | 建议路径（待确认） |
|---|------|-------------------|
| 1 | 用户资料读写 | `GET/PATCH /v1/user-center/profile` |
| 2 | 候选人详情 | `GET /v1/candidates/:id` |
| 3 | 新用户资料提交 | `PATCH /v1/auth/onboarding`（写入 `profiles`） |
| 4 | 认证材料 | `POST /v1/trust/verification/*` |
| 5 | 登录响应字段 | 是否含 `case_id`、`profile_id`、`requester_id` |
| 6 | 未读角标 | `GET /v1/notifications/unread` 或各模块聚合 |

**无接口时**：前端显示「即将上线」或 dev-only Mock（带 Banner）。

---

## 依赖与 UI 组件清理

- **删除**（确认无引用后）：未使用的 Radix 包、recharts、大量 `components/ui` 文件  
- **保留并用**：`zod`（env + 响应）、`react-hook-form`（表单）、`sonner` / Toaster  

---

## 排期与人力

| 阶段 | 工期 | 依赖 |
|------|------|------|
| Phase 0 | 1～2 天 | — |
| Phase 1 | 2～3 天 | Phase 0 |
| Phase 2 | 5～7 天 | Phase 1 |
| Phase 3 | 7～10 天 | Phase 2 + 后端接口 |
| Phase 4 | 4～5 天 | 可与 Phase 3 后半并行 |
| Phase 5 | 3～5 天 | Phase 3 核心完成 |
| Phase 6 | 按需 | 上线后迭代 |

---

## 上线验收总清单

- [x] 生产无 Demo 导航、无静默 Mock（`isDemoNavEnabled` / `isMockFallbackAllowed`）  
- [x] `npm run build`、`npm run lint`、`npm run test:unit`（CI：`.github/workflows/frontend-her-app.yml`）  
- [x] E2E 全绿（`pnpm e2e:her:stub`，4/4 通过，2026-05-21 本机验证）  
- [x] 无 `NEXT_PUBLIC` 数据库连接串  
- [x] 登录 → 发现/来信/聊天/资料/Onboarding 主流程接 API  
- [x] API 失败有 Toast/错误页，可重试  
- [x] `app/page.tsx` 已拆分；`tests/unit` 覆盖 env 与 gateway 客户端  
- [x] 未使用 `components/ui` 已精简（保留 `button` / `input` / `sonner`）  
- [x] README、`.env.example` 与实现一致  

---

## 建议 PR 拆分

1. `chore: hide demo nav in production + safe gateway JSON parse`  
2. `chore: enable typescript build + eslint + env validation`  
3. `refactor: extract auth module from page.tsx`  
4. `refactor: api client and shared types`  
5. `feat: profile and candidate detail API`  
6. `feat: onboarding submit + explicit mock policy`  
7. `refactor: her pages use shadcn primitives + toaster`  
8. `chore: prune unused ui components`  
9. `test: unit + e2e expansion`  

---

## 相关文档

- 前端运行说明：[`frontend/her-app/README.md`](../frontend/her-app/README.md)  
- 设计页说明：[`docs/design-pages/README.md`](./design-pages/README.md)  
- 用户信任中心设计：[`docs/design-pages/11-user-trust-hub.md`](./design-pages/11-user-trust-hub.md)  
- E2E 说明：[`docs/e2e-test-suite.md`](./e2e-test-suite.md)  
- 认证后端设计：[`docs/auth-backend-design.md`](./auth-backend-design.md)  

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-05-21 | 初版：问题摘要、五阶段白话计划、技术分阶段方案、验收与 PR 拆分 |
| 2026-05-21 | 落地实施：架构拆分、API/Session 层、Mock 策略、错误态、Demo 导航 gated、TS 构建校验、`/v1/auth/me` 与 discovery 详情接 API |
| 2026-05-21 | 收尾：Onboarding 写 `profiles`、未读角标 API、`verification` 状态拉取、UI 精简、单元测试与 CI |

### 落地状态（2026-05-21，与代码同步）

| 项 | 状态 | 说明 |
|----|------|------|
| Phase 0 止血 | ✅ | Demo 导航仅 dev / `NEXT_PUBLIC_ENABLE_DEMO_NAV`；gateway 鉴权与 JSON 安全；客户端无 DSN |
| Phase 1 工程基线 | ✅ | TS 构建校验；ESLint；`lib/env.ts` zod；死代码清理；GitHub Actions `frontend-her-app.yml` |
| Phase 2 架构 | ✅ | `app/page.tsx` 薄入口；`HerApp` / `AppShell` / hooks；`lib/api` / `lib/auth` |
| Phase 3 数据 | ✅ | 发现/聊天/关系/详情/`auth/me`/Onboarding/未读来信/认证状态/账号找回 API |
| Phase 4 UI | ✅ | Toaster、ErrorState、DemoDataBanner、next-themes；登录/Onboarding 使用 shadcn `Button`/`Input`；`components/ui` 仅保留 3 个文件 |
| Phase 5 测试 | ✅ | `vitest` 5 用例；`pnpm e2e:her:stub` 4/4 通过；CI workflow 已加 |
| Phase 6 App Router | ✅ | `app/[...slug]` + `lib/navigation/routes.ts` + `useAppRouter`（`/discover`、`/chat/:id` 等） |
| 安全加固 httpOnly | ✅ | `POST/DELETE /api/auth/session`；Gateway 代理读 `her_access_token` Cookie |
| 关系未读角标 | ✅ | timeline 末条消息作者推导 + 30s 轮询刷新 |
| 账号找回 | ✅ | 手机验证码 / 微信登录接真实 API |
| 活体认证提交 | ✅ | `live-video-challenges` + `live-video-submissions` |

**后端环境（已配置）**：根目录 `.env` 含 `HER_PROFILE_SOURCE_DSN`、`PARTNER_*_DB` 等；Gateway `profile_source_defaults.py` 服务端补全 DSN。

**后续仅基础设施级**：Gateway 原生 WebSocket/SSE 推送（当前用轮询）、学历/职业材料上传需 trust-hub 写字段 API 时再对接。
