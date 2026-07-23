# 发现页图片搜索 AI Native 方案 B 任务拆分

日期：2026-07-21

> 本文档把《[发现页图片搜索 AI Native 方案 B 完整落地方案](./发现页图片搜索AI%20Native方案B完整落地方案.md)》拆成可执行任务清单。
>
> 方案 B 不是渐进式收口，而是一次更彻底的重构路线。目标不是“继续兼容着改”，而是把发现页图片搜索正式重建成统一 discovery multimodal turn 体系。

---

## 1. 总体说明

### 1.1 任务拆分原则

方案 B 的任务拆分遵循五条原则：

1. 先冻结旧入口，再建设新骨架
2. 先统一正式协议，再统一内部状态模型
3. 先建能力层，再让 Runtime 完整接管编排
4. 迁移期必须保留 shadow compare 和可回退能力
5. 旧入口、旧字段、旧抽象只能退场，不能继续长新逻辑

### 1.2 任务状态定义

- `未开始`：当前仓库中未看到明确实现
- `进行中`：已有部分骨架，但未形成完整方案 B 主链路
- `已完成`：已有完整实现且符合方案 B 要求

### 1.3 当前总体判断

基于 2026-07-21 当前仓库代码，方案 B 的总体状态可判断为：

- 第一阶段：`已完成`
- 第二阶段：`已完成`
- 第三阶段：`已完成`
- 第四阶段：`已完成`
- 第五阶段：`已完成`
- 第六阶段：`已完成`
- 第七阶段：`已完成`

原因：

1. `/v1/discovery/turns` 已成为唯一正式业务入口
2. `visual_memory` 已成为正式 session 视觉状态模型
3. capability layer、unified retrieval、structured visual plan 已全部接通
4. Runtime / Service / Gateway 的视觉链路职责已经重新收口
5. `/photo-search` 已正式退场，shadow compare 与迁移看板已补齐

---

## 2. 总体阶段划分

| 阶段 | 名称 | 当前状态 | 目标 |
|------|------|---------|------|
| 第一阶段 | 冻结旧入口与新协议定版 | 已完成 | 明确 `/v1/discovery/turns` 是唯一正式入口 |
| 第二阶段 | visual memory 正式建模 | 已完成 | 把视觉记忆升级成 session 默认状态模型 |
| 第三阶段 | 能力层重构 | 已完成 | 用 capability layer 取代旧模式骨架 |
| 第四阶段 | Runtime 完整接管 | 已完成 | 让 Agent Runtime 成为视觉搜索总编排者 |
| 第五阶段 | Gateway 变薄与旧入口退化 | 已完成 | 让 `/photo-search` 只剩迁移期转发职责 |
| 第六阶段 | shadow compare 与迁移联调 | 已完成 | 对比新旧链路、控制切换风险 |
| 第七阶段 | 下线旧结构与最终收尾 | 已完成 | 删除旧入口、旧字段、旧模式心智 |

---

## 3. 第一阶段：冻结旧入口与新协议定版

### 3.1 阶段目标

先把“什么是唯一正式协议”钉死，避免新旧路线继续混着长。

### 3.2 任务清单

#### 3.2.1 `B1-001` 明确 `/v1/discovery/turns` 为唯一正式入口

- 状态：`未开始`
- 目标：
  - 在文档、代码注释、接口层约束中明确 `/v1/discovery/turns` 是唯一正式能力入口
- 涉及文件：
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
  - [`frontend/her-app/lib/api/endpoints/discovery.ts`](../frontend/her-app/lib/api/endpoints/discovery.ts)
  - [`docs/发现页图片搜索AI Native方案B完整落地方案.md`](./发现页图片搜索AI%20Native方案B完整落地方案.md)
- 验收：
  - 所有正式调用说明都只指向 `/v1/discovery/turns`

#### 3.2.2 `B1-002` 冻结 `/photo-search` 新功能开发

- 状态：`未开始`
- 目标：
  - 明确 `/photo-search` 只能做兼容，不允许继续承载新功能
- 涉及文件：
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
  - 相关联调文档
- 验收：
  - 新功能 PR 不再允许围绕 `/photo-search` 扩展

#### 3.2.3 `B1-003` 定版新的顶层请求 schema

- 状态：`未开始`
- 目标：
  - 把方案 B 的正式请求 schema 定版成只允许：
    - `session_id`
    - `message.text`
    - `message.attachments`
    - `client_context`
- 涉及文件：
  - [`frontend/her-app/lib/types/discovery.ts`](../frontend/her-app/lib/types/discovery.ts)
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- 验收：
  - 顶层 schema 中不再正式允许 `mode / celebrity_name / photo_search`

#### 3.2.4 `B1-004` 前端删除对旧协议的正式依赖

- 状态：`未开始`
- 目标：
  - 前端正式代码不再保留对旧 photo-search 正式调用的依赖
- 涉及文件：
  - [`frontend/her-app/components/her/discover-page.tsx`](../frontend/her-app/components/her/discover-page.tsx)
  - [`frontend/her-app/lib/api/endpoints/discovery.ts`](../frontend/her-app/lib/api/endpoints/discovery.ts)
- 验收：
  - 前端图片发送只走 `submitDiscoveryTurn`

### 3.3 第一阶段验收

满足以下条件即通过：

1. `/v1/discovery/turns` 被明确为唯一正式入口
2. `/photo-search` 被明确冻结
3. 顶层协议正式定版
4. 前端主链路不再依赖旧 photo-search 正式调用

---

## 4. 第二阶段：visual memory 正式建模

### 4.1 阶段目标

把 visual context 从“附加状态”升级成 Discovery Session 默认状态模型。

### 4.2 任务清单

#### 4.2.1 `B2-001` 定义正式 `visual_memory` schema

- 状态：`未开始`
- 目标：
  - 定义稳定的 session state 结构：
    - active reference
    - active preference
    - active constraints
    - refinement history
    - last result summary
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/agent_session_store.py`](../external-systems/partner-discovery-system/discovery_system/agent_session_store.py)
  - [`external-systems/partner-discovery-system/discovery_system/service.py`](../external-systems/partner-discovery-system/discovery_system/service.py)
- 验收：
  - visual memory 结构固定且可稳定序列化

#### 4.2.2 `B2-002` 旧 visual context 向新 schema 迁移

- 状态：`未开始`
- 目标：
  - 实现旧 state 到新 `visual_memory` 的迁移器
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/agent_session_store.py`](../external-systems/partner-discovery-system/discovery_system/agent_session_store.py)
  - [`external-systems/partner-discovery-system/discovery_system/storage.py`](../external-systems/partner-discovery-system/discovery_system/storage.py)
- 验收：
  - 老会话恢复时不会丢视觉上下文

#### 4.2.3 `B2-003` snapshot 与调试接口统一暴露 `visual_memory`

- 状态：`未开始`
- 目标：
  - 所有 runtime context、snapshot、调试接口都统一输出 `visual_memory`
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/service.py`](../external-systems/partner-discovery-system/discovery_system/service.py)
  - [`external-systems/partner-discovery-system/discovery_system/service_context.py`](../external-systems/partner-discovery-system/discovery_system/service_context.py)
- 验收：
  - 调试和排查时不再需要拼多个旧字段看视觉状态

### 4.3 第二阶段验收

满足以下条件即通过：

1. visual memory 成为正式 state schema
2. 老状态可迁移
3. snapshot 与调试接口可直接查看 visual memory

---

## 5. 第三阶段：能力层重构

### 5.1 阶段目标

把内部“按模式组织”改成“按能力组织”。

### 5.2 任务清单

#### 5.2.1 `B3-001` 定义统一 capability API

- 状态：`未开始`
- 目标：
  - 抽出统一视觉能力集合：
    - `load_visual_context`
    - `analyze_visual_reference`
    - `parse_visual_constraints`
    - `resolve_visual_followup_reference`
    - `retrieve_visual_candidates`
    - `apply_candidate_hard_filters`
    - `rerank_visual_candidates`
    - `explain_visual_matches`
    - `persist_visual_memory`
- 涉及文件：
  - 可能新增 [`match_domain/visual_capabilities.py`](../match_domain/visual_capabilities.py)
  - [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
- 验收：
  - Runtime 只看到 capability，不直接看到 legacy route

#### 5.2.2 `B3-002` 建立 visual retrieval orchestrator

- 状态：`未开始`
- 目标：
  - 为候选检索建立统一总入口，内部再决定召回器和权重
- 涉及文件：
  - 可能新增 [`match_domain/visual_retrieval_orchestrator.py`](../match_domain/visual_retrieval_orchestrator.py)
  - [`match_domain/photo_discovery_search.py`](../match_domain/photo_discovery_search.py)
- 验收：
  - 中层不再直接围绕 face/style/hybrid 函数编排

#### 5.2.3 `B3-003` legacy 搜索函数下沉

- 状态：`已完成`
- 目标：
  - 让现有 face/style/reference/hybrid 只保留为 capability 内部实现细节
- 涉及文件：
  - [`match_domain/photo_discovery_search.py`](../match_domain/photo_discovery_search.py)
  - [`match_domain/photo_intent_agent.py`](../match_domain/photo_intent_agent.py)
- 验收：
  - Service / Runtime 不再直接感知 legacy 函数名字

### 5.3 第三阶段验收

满足以下条件即通过：

1. Runtime 只面向 capability
2. 检索总入口统一
3. legacy 搜索函数已下沉为更深层实现

---

## 6. 第四阶段：Runtime 完整接管

### 6.1 阶段目标

让 Discovery Agent Runtime 成为视觉搜索唯一总编排者。

### 6.2 任务清单

#### 6.2.1 `B4-001` 生成结构化 visual plan

- 状态：`已完成`
- 目标：
  - Runtime 每轮输出结构化 visual plan，而不是散落的 if/else 决策
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
  - [`external-systems/partner-discovery-system/discovery_system/decision_models.py`](../external-systems/partner-discovery-system/discovery_system/decision_models.py)
- 验收：
  - visual search 的追问、检索、解释路径都能回放

#### 6.2.2 `B4-002` 让 Runtime 决定工具顺序

- 状态：`已完成`
- 目标：
  - 让 Runtime 决定：
    - 先追问还是先搜
    - 是否沿用上一张图
    - 是否先过滤再重排
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
- 验收：
  - 主要视觉搜索编排不再写死在 service 中

#### 6.2.3 `B4-003` service 缩成受控协调层

- 状态：`已完成`
- 目标：
  - service 主要负责：
    - 权限校验
    - 持久化
    - timeline 落地
    - 失败回滚
  - 不再承担主要视觉搜索策略决策
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/service.py`](../external-systems/partner-discovery-system/discovery_system/service.py)
- 验收：
  - service 代码中的模式分支明显减少

### 6.3 第四阶段验收

满足以下条件即通过：

1. Runtime 产出结构化 visual plan
2. Runtime 决定 tool order
3. service 缩成受控协调层

---

## 7. 第五阶段：Gateway 变薄与旧入口退化

### 7.1 阶段目标

让 Gateway 不再承担视觉搜索业务判断，旧入口只剩转发职责。

### 7.2 任务清单

#### 7.2.1 `B5-001` `/photo-search` 只保留兼容转发

- 状态：`已完成`
- 目标：
  - `/photo-search` 只做：
    - 参数转换
    - 转发 `/turns`
    - 兼容返回
- 涉及文件：
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- 验收：
  - `/photo-search` 内不再保留搜索业务逻辑

#### 7.2.2 `B5-002` 清理 Gateway 内旧模式判断

- 状态：`已完成`
- 目标：
  - 清理 Gateway 中围绕 `mode` 的主要判断分支
- 涉及文件：
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- 验收：
  - Gateway 不再承担“这是 face 还是 style”的业务判断

#### 7.2.3 `B5-003` 统一 ops 监控语义

- 状态：`已完成`
- 目标：
  - ops dashboard 统一围绕 visual turn 语义观测，而不是围绕 photo-search route
- 涉及文件：
  - [`observability/photo_search_metrics.py`](../observability/photo_search_metrics.py)
  - [`external-systems/partner-http-gateway/gateway/ops_routes.py`](../external-systems/partner-http-gateway/gateway/ops_routes.py)
- 验收：
  - dashboard 能把 legacy compat 和 new unified turn 清晰对比

### 7.3 第五阶段验收

满足以下条件即通过：

1. `/photo-search` 只保留转发
2. Gateway 内旧模式判断基本清空
3. ops 监控语义统一

---

## 8. 第六阶段：shadow compare 与迁移联调

### 8.1 阶段目标

在正式切断旧链路前，建立新旧链路结果对比和迁移风险控制机制。

### 8.2 任务清单

#### 8.2.1 `B6-001` 建立 shadow compare 双跑机制

- 状态：`已完成`
- 目标：
  - 对关键视觉请求同时跑新旧链路，对比结果但不直接返回 shadow 结果
- 涉及文件：
  - discovery runtime / gateway / 测试脚本
- 验收：
  - 能看到新旧结果差异率

#### 8.2.2 `B6-002` 建迁移完成率看板

- 状态：`已完成`
- 目标：
  - 观测：
    - 旧入口调用量
    - 旧客户端残留量
    - `/photo-search -> /turns` 转发成功率
- 涉及文件：
  - [`observability/photo_search_metrics.py`](../observability/photo_search_metrics.py)
  - [`external-systems/partner-http-gateway/gateway/ops_routes.py`](../external-systems/partner-http-gateway/gateway/ops_routes.py)
- 验收：
  - 联调环境可稳定看到迁移推进情况

#### 8.2.3 `B6-003` 补完整方案 B 测试矩阵

- 状态：`已完成`
- 目标：
  - 单测、集成测试、回归测试、shadow 对比测试一并补齐
- 涉及文件：
  - 前端单测
  - Gateway 测试
  - discovery runtime 测试
  - match domain 测试
- 验收：
  - 关键视觉会话场景全部自动化覆盖

### 8.3 第六阶段验收

满足以下条件即通过：

1. 新旧链路可双跑对比
2. 迁移完成率可观测
3. 方案 B 测试矩阵完整

---

## 9. 第七阶段：下线旧结构与最终收尾

### 9.1 阶段目标

真正删除旧入口、旧字段、旧模式骨架，完成方案 B 收尾。

### 9.2 任务清单

#### 9.2.1 `B7-001` 正式下线 `/photo-search`

- 状态：`已完成`
- 目标：
  - 在迁移完成后正式关闭 `/photo-search`
- 涉及文件：
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- 验收：
  - 正式环境不再以 `/photo-search` 承担业务入口

#### 9.2.2 `B7-002` 删除顶层和中层 `mode` 残留

- 状态：`已完成`
- 目标：
  - 删除对 `mode / face / style / celebrity / hybrid` 的中层主骨架依赖
- 涉及文件：
  - [`external-systems/partner-discovery-system/discovery_system/service.py`](../external-systems/partner-discovery-system/discovery_system/service.py)
  - [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
  - [`match_domain/photo_intent_agent.py`](../match_domain/photo_intent_agent.py)
- 验收：
  - 视觉搜索主骨架已不再围绕旧模式字段组织

#### 9.2.3 `B7-003` 删除 legacy-only 埋点与测试

- 状态：`已完成`
- 目标：
  - 清理只服务于旧 `/photo-search` 的测试和埋点残留
- 涉及文件：
  - ops 监控
  - gateway 测试
  - 文档
- 验收：
  - 代码库中不再继续维护纯 legacy-only 路径

#### 9.2.4 `B7-004` 更新所有正式文档

- 状态：`已完成`
- 目标：
  - 所有正式技术文档、接口文档、联调文档只描述方案 B 主形态
- 涉及文件：
  - `docs/`
  - gateway API contract
- 验收：
  - 正式文档中不再把旧 route 当成正式入口描述

### 9.3 第七阶段验收

满足以下条件即通过：

1. `/photo-search` 正式退场
2. `mode` 不再是主骨架
3. legacy-only 埋点和测试清理完成
4. 正式文档切换到方案 B 主形态

---

## 10. 总体验收标准

方案 B 只有同时满足下面条件才算真正完成：

1. 用户侧完全感知不到旧模式心智
2. 顶层正式协议中完全没有 `mode`
3. `/v1/discovery/turns` 是唯一正式业务入口
4. Runtime 已成为视觉搜索总编排者
5. visual memory 已成为 session 默认状态模型
6. capability layer 已取代旧模式骨架
7. shadow compare 与迁移看板完整
8. 关键视觉用例测试矩阵完整通过

---

## 11. 涉及文件总表

### 11.1 前端

- [`frontend/her-app/components/her/discover-page.tsx`](../frontend/her-app/components/her/discover-page.tsx)
- [`frontend/her-app/hooks/use-discovery-session.ts`](../frontend/her-app/hooks/use-discovery-session.ts)
- [`frontend/her-app/lib/api/endpoints/discovery.ts`](../frontend/her-app/lib/api/endpoints/discovery.ts)
- [`frontend/her-app/lib/types/discovery.ts`](../frontend/her-app/lib/types/discovery.ts)
- [`frontend/her-app/lib/discovery/map-discovery-view.ts`](../frontend/her-app/lib/discovery/map-discovery-view.ts)

### 11.2 Gateway

- [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- [`external-systems/partner-http-gateway/gateway/ops_routes.py`](../external-systems/partner-http-gateway/gateway/ops_routes.py)

### 11.3 Discovery Runtime / Service

- [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
- [`external-systems/partner-discovery-system/discovery_system/service.py`](../external-systems/partner-discovery-system/discovery_system/service.py)
- [`external-systems/partner-discovery-system/discovery_system/agent_session_store.py`](../external-systems/partner-discovery-system/discovery_system/agent_session_store.py)
- [`external-systems/partner-discovery-system/discovery_system/decision_models.py`](../external-systems/partner-discovery-system/discovery_system/decision_models.py)
- [`external-systems/partner-discovery-system/discovery_system/view_models.py`](../external-systems/partner-discovery-system/discovery_system/view_models.py)

### 11.4 Match Domain / Search

- [`match_domain/photo_discovery_search.py`](../match_domain/photo_discovery_search.py)
- [`match_domain/photo_intent_agent.py`](../match_domain/photo_intent_agent.py)
- `match_domain/visual_capabilities.py`
- `match_domain/visual_retrieval_orchestrator.py`

---

## 12. 最终判断

方案 B 的优势是：

1. 协议更统一
2. 内部抽象更纯
3. 长期演进成本更低

方案 B 的代价是：

1. 重构周期更长
2. 风险更高
3. 迁移和回归更重

一句话收尾：

**方案 B 不是“继续优化当前系统”，而是“按统一 AI Native 图纸重建当前系统”。**
