# Her App Frontend

Her 主应用前端（Next.js App Router），通过 `app/api/gateway` 代理访问 partner-http-gateway，并保留开发环境 Mock 回退能力。

## 运行

1. 复制环境变量：

```bash
cp .env.example .env.local
```

2. 配置：

- `PARTNER_GATEWAY_BASE_URL`：当前后端 gateway 地址，例如 `http://127.0.0.1:8765`
- `PARTNER_GATEWAY_API_KEY`：如果 gateway 开启了 API key，则在这里配置
- `NEXT_PUBLIC_HER_REQUESTER_ID`：推荐 / discovery 使用的用户请求者 ID（登录后 session 可覆盖）
- `NEXT_PUBLIC_HER_PROFILE_ID`：discovery 和 trust hub 绑定的当前资料 ID
- `NEXT_PUBLIC_HER_USER_ID`：聊天 / trust hub 使用的用户 ID
- `NEXT_PUBLIC_HER_CASE_ID`：关系页 / 聊天页联调用的 case_id，例如 `case-frontend-demo`
- `NEXT_PUBLIC_ALLOW_MOCK_FALLBACK`：开发环境是否在接口失败时回退演示数据（生产务必 `false`）
- `NEXT_PUBLIC_ENABLE_DEMO_NAV`：非 development 时是否显示右下角页面导航（联调 E2E 可设 `true`）
- `NEXT_PUBLIC_USE_AUTH_STUB`：开发环境是否使用微信/一键登录 stub 凭证

字段认证写回的 `HER_PROFILE_SOURCE_DSN` / `HER_PROFILE_SOURCE_TABLE` 应配置在 **Gateway 服务端**，不要放入 `NEXT_PUBLIC_*`。

3. 安装并运行：

```bash
pnpm install
pnpm dev
```

## 质量检查

```bash
pnpm run lint        # ESLint（typescript-eslint flat config）
pnpm run test:unit   # Vitest 单元测试
pnpm run build       # 生产构建 + TypeScript 校验
```

CI：仓库根目录 `.github/workflows/frontend-her-app.yml`（push/PR 触及 `frontend/her-app` 或 E2E 依赖的后端路径时运行）。阻塞项包括 `e2e`（全栈 Playwright，`MOCK_FALLBACK=false`）与 `mock-fallback-regression`（开发 Mock 黄条回归）。Dev Mock 策略见 [`docs/MOCK_DEVELOPMENT.md`](docs/MOCK_DEVELOPMENT.md)。

## 路由（App Router）

| 路径 | 页面 |
|------|------|
| `/splash` | 启动页 |
| `/welcome` | 登录欢迎 |
| `/login/phone`、`/login/verify`、`/login/one-tap` | 登录流程 |
| `/recovery` | 账号找回 |
| `/discover`、`/relationships`、`/profile` | 主 Tab |
| `/inbox` | 推荐来信 |
| `/candidates/:id` | 候选人详情 |
| `/chat/:conversationId` | 聊天 |
| `/verification`、`/trust` | 认证 / 信任中心 |

根路径 `/` 会重定向到 `/splash`。会话 Token 通过 httpOnly Cookie（`/api/auth/session`）保存。

## 联调回归

当前仓库已经内置了真实前端联调用例：

- 手机验证码登录
- 微信登录 + 绑定手机号
- 本机号码一键登录
- 发现页会话 / 推荐动作
- 关系页 / 聊天发消息

先启动前端：

```bash
pnpm dev --hostname 127.0.0.1 --port 3000
```

如果你要直接跑一套可重复的 stub 联调回归：

```bash
pnpm e2e:her:stub
```

这个命令会：

- 自动起一个带 fresh 微信 stub 身份的 gateway
- 自动生成一个新的绑定手机号用于微信绑号测试
- 运行 `tests/e2e/her-flow.spec.ts`

如果你只想在当前环境直接跑 Playwright：

```bash
pnpm e2e:her
```

CI 同款全栈 E2E（MySQL bootstrap → gateway → production build → Playwright，mock 开关全关）：

```bash
# 需本地 MySQL 127.0.0.1:3307（见仓库根 start_partner_mysql.sh）
pnpm e2e:her:ci
```

## 当前状态

- 前端页面入口：`app/page.tsx`
- API 代理：`app/api/gateway/[...path]/route.ts`

## 改进方案

前端现状问题、分阶段改造计划、验收清单与 PR 拆分见：

- [`docs/frontend-improvement-plan.md`](../../docs/frontend-improvement-plan.md)
