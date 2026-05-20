# Her App Frontend

这是接入当前 `Her` 后端网关的用户端前端子应用，基于 Next.js App Router。

## 运行

1. 复制环境变量：

```bash
cp .env.example .env.local
```

2. 配置：

- `PARTNER_GATEWAY_BASE_URL`：当前后端 gateway 地址，例如 `http://127.0.0.1:8765`
- `PARTNER_GATEWAY_API_KEY`：如果 gateway 开启了 API key，则在这里配置
- `NEXT_PUBLIC_HER_REQUESTER_ID`：推荐 / discovery 使用的用户请求者 ID
- `NEXT_PUBLIC_HER_PROFILE_ID`：discovery 和 trust hub 绑定的当前资料 ID
- `NEXT_PUBLIC_HER_USER_ID`：聊天 / trust hub 使用的用户 ID
- `NEXT_PUBLIC_HER_CASE_ID`：如果要直接联调关系页 / 聊天页，可填一个已有 case_id

3. 安装并运行：

```bash
pnpm install
pnpm dev
```

## 当前已接入

- 发现页：`/v1/discovery/sessions`、`/turns`、`/profiles/{id}`
- 推荐页：`/v1/recommendation/cards`
- 信任中心：`/v1/user-center/trust-hub`
- 聊天 / 关系页：`/v2/chat/cases/{case_id}/timeline`、`/v2/chat/conversations/{conversation_id}`

## 当前限制

- 关系页和聊天页需要已存在的 `case_id`
- 活体视频认证流程已接入 challenge 获取，但浏览器端真实录像上传仍保留为前端扩展项
- 字段核验页目前以用户流程展示为主，真实文件上传需要结合具体 OSS / 文件服务继续补
