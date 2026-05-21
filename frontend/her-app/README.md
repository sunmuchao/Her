# Her App Frontend

当前仓库已接入 `/Users/sunmuchao/Downloads/her-app-design_5` 的最新前端页面；`frontend/her-app` 同时保留了系统已有的 `app/api/gateway` 代理接口。

## 运行

1. 复制环境变量：

```bash
cp .env.example .env.local
```

2. 配置：

- `PARTNER_GATEWAY_BASE_URL`：当前后端 gateway 地址，例如 `http://127.0.0.1:8765`
- `PARTNER_GATEWAY_API_KEY`：如果 gateway 开启了 API key，则在这里配置
- `NEXT_PUBLIC_HER_REQUESTER_ID`：推荐 / discovery 使用的用户请求者 ID
- `NEXT_PUBLIC_HER_PROFILE_ID`：discovery 和 trust hub 绑定的当前资料 ID，本地 demo 可直接用 `1`
- `NEXT_PUBLIC_HER_USER_ID`：聊天 / trust hub 使用的用户 ID
- `NEXT_PUBLIC_HER_CASE_ID`：如果要直接联调关系页 / 聊天页，可填一个已有 case_id
- `NEXT_PUBLIC_HER_PROFILE_SOURCE_DSN`：字段认证写回资料所需的数据源 DSN
- `NEXT_PUBLIC_HER_PROFILE_SOURCE_TABLE`：字段认证写回资料所需的表名，默认 `profiles`

3. 安装并运行：

```bash
pnpm install
pnpm dev
```

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

## 当前状态

- 前端页面入口：`app/page.tsx`
- API 代理：`app/api/gateway/[...path]/route.ts`
