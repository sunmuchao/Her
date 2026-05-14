# Permission Matrix

## 1. 目标

这份表是当前代码已经落地的权限真相，避免再靠口头约定理解“谁能看、谁能改、谁能代操作”。

当前权限模型有两个核心原则：

1. 普通用户只能操作自己的资源。
2. 运营/审核/客服/平台/worker 这些内部角色，只有在明确需要时才能代查或批量操作。

---

## 2. 角色

| 角色 | 含义 | 典型来源 |
| --- | --- | --- |
| `end_user` | 普通用户 | App / H5 用户 token |
| `ops_operator` | 运营执行角色 | 后台运营 |
| `risk_reviewer` | 风险审核角色 | 风控审核 |
| `profile_reviewer` | 资料审核角色 | 资料审核 |
| `customer_support` | 客服角色 | 客服后台 |
| `platform_admin` | 平台管理员 | 管理员后台 / 运维 |
| `service_worker` | 系统作业角色 | worker / 定时任务 / 管理脚本 |

说明：

- `ops_operator`、`risk_reviewer`、`profile_reviewer`、`customer_support`、`platform_admin`、`service_worker` 都属于“可 override 的内部角色”。
- override 的意思是：内部人员可以代查/代操作别人的资源，但会打审计日志。

---

## 3. 资源规则

### 3.1 推荐系统

| 资源/动作 | `end_user` | 内部角色 |
| --- | --- | --- |
| 创建订阅 `create_subscription` | 只能给自己建 | 可代建 |
| 查看订阅 `get_subscription` | 只能看自己的订阅 | 可代查 |
| 改订阅覆盖项 `update_subscription_overrides` | 只能改自己的 | 可代改 |
| 单订阅刷新 `refresh_subscription` | 只能刷新自己的 | 可代刷 |
| 列推荐结果/搜索运行记录 | 只能看自己的 | 可代查 |
| 列卡片/标记已读 | 只能看自己的、只能标自己的 | 可代查/代标 |
| 记录推荐动作 `record_recommendation_action` | 只能记自己的动作 | 可代操作，但会记录 override |
| 记录预审选择 `record_user_review` | 只能记自己的选择 | 可代操作，但会记录 override |
| 批量刷新到期订阅 `refresh_due_subscriptions` | 不允许 | 仅内部角色 |
| 批量投递卡片 `deliver_in_app_recommendations` | 不允许 | 仅内部角色 |

推荐系统 owner 字段：

- 订阅 / 卡片 / 推荐结果都以 `requester_id` 作为 owner。
- 网关会把当前 token 的 `actor_id` 和 `requester_id` 做强校验。

### 3.2 撮合系统

| 资源/动作 | `end_user` | 内部角色 |
| --- | --- | --- |
| 创建/更新 pool member | 只能操作自己的 `user_key` | 可代操作 |
| 查看 member | 只能看自己的 | 可代查 |
| 修改 member 状态 | 只能改自己的 | 可代改 |
| 单 member 刷新 | 只能刷自己的 | 可代刷 |
| 批量刷新 pool | 不允许 | 仅内部角色 |
| 构建 pair | 不允许 | 仅内部角色 |
| 打开 case | 不允许 | 仅内部角色 |
| 查看单 case | 只能看和自己有关的 case | 可代查 |
| 回复 case `record_case_reply` | 只能以自己名下 member 回复 | 可代回复 |
| 记录 feedback | 只能给自己名下 member 记反馈 | 可代记 |
| 列所有 case / pair | 不允许 | 仅内部角色 |
| 查看单 pair | 不允许 | 仅内部角色 |
| 派发联系方式 `dispatch_case_contact` | 不允许 | 仅内部角色 |
| 关闭超时 case | 不允许 | 仅内部角色 |

撮合系统 owner 字段：

- member 以 `user_key` 作为 owner。
- case 的 owner 通过 `first_contact_member_id / second_contact_member_id -> member.user_key` 反查。

### 3.3 聊天 / 风控 / 资料审核

这一块此前已经接入第一版权限模型，本轮没有推翻，只把统一 actor/audit 基础接上。

已保留的原则：

- 普通用户不能冒充别人的 `requester_id / reviewer_id / resolver_id / appellant_id`。
- 审核、客服、风控接口继续按角色限制。
- 所有请求现在都会带统一 actor 上下文进入底层日志。

---

## 4. Override 规则

内部角色可以 override，但不是“静默代操作”。

当前代码里，以下场景会打审计日志：

- staff 代查别人资源
- staff 代操作别人的 owner 绑定字段
- staff 走内部专用接口
- 401 鉴权失败
- 403 权限拒绝
- 后台 outbox / 管理脚本执行高风险命令

审计日志统一输出到 `her.pipeline`，字段至少包括：

- `her_kind=audit`
- `audit_action`
- `actor_id`
- `actor_roles`
- `resource_type`
- `resource_id`
- `outcome`
- `reason`
- `impersonated_owner_id`
- `trace_id`

---

## 5. 后台脚本与 Worker

以下脚本已经接入统一 actor/audit：

- `external-systems/partner-recommendation-system/scripts/manage_recommendation_outbox.py`
- `external-systems/partner-matchmaking-system/scripts/manage_matchmaking_outbox.py`
- `external-systems/partner-chat-system/scripts/manage_chat_outbox.py`
- `external-systems/partner-recommendation-system/scripts/create_saved_search_subscription.py`
- `external-systems/partner-recommendation-system/scripts/record_recommendation_action.py`
- `external-systems/partner-recommendation-system/scripts/record_user_review.py`
- `external-systems/partner-recommendation-system/scripts/request_proxy_intro.py`

统一参数：

- `--actor-id`
- `--actor-roles`
- `--audit-reason`

默认情况下，这些脚本会用系统 actor，例如：

- `system:recommendation-outbox`
- `system:matchmaking-outbox`
- `system:chat-outbox`
- `system:recommendation-admin`

---

## 6. 当前边界

这套 P1 权限模型已经解决的是：

- 前门锁了，推荐/撮合侧门也锁上了
- 请求链路和脚本链路都能知道“当前是谁”
- 代查/代操作不再是黑盒，有统一审计

还没做的是更细颗粒度的 RBAC/ABAC，例如：

- “客服只能看投诉相关 case，不能看全部撮合数据”
- “审核员只能 review，不能批量运营刷新”
- “某个部门只能看自己负责城市/业务线”

那部分属于下一阶段更细权限模型，不属于这次 P1 的收口范围。
