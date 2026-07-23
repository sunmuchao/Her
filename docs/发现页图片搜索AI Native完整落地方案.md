# 发现页图片搜索 AI Native 完整落地方案

日期：2026-07-18

> 适用范围：发现页图片上传入口、discovery 会话、Gateway、photo search 服务、Agent 编排、埋点、验收。
>
> 本文档不是“把现有图片搜索修一修”的小改方案，而是一份面向 AI Native 目标形态的完整落地方案。它默认当前仓库已经具备部分照片检索、发现页 session、Agent 容器和埋点基础，但尚未形成统一的多模态会话搜索系统。

---

## 1. 结论先行

当前发现页的图片找人能力，还不算真正的 AI Native。

现在的真实状态更接近：

- 前台已经开始往自然对话靠
- 后台仍保留老的模式搜索接口心智
- 普通聊天和图片搜索还是两条链路
- “让小雅自己判断”更多是产品文案，不是完整系统能力

真正的 AI Native 目标应该是：

1. 用户只需要发图、说人话、继续追问
2. 系统自己理解这轮是在“按脸找”“按感觉找”“按参考人物找”还是“混合找”
3. 系统自己决定调哪些内部能力，不要求用户先选模式
4. 图、文字、历史上下文、上一轮结果都属于同一个会话上下文
5. 后续“像刚才那张图那样的”“成熟一点”“还是这类气质但在上海”都能接住

一句话版：

**前台只有一个自然对话入口，后台是一个多模态 Agent 驱动的统一搜索编排系统。**

---

## 2. 当前问题与根因

### 2.1 当前用户体验问题

用户理想中的动作是：

1. 上传一张图
2. 直接发，或者补一句自然话
3. 小雅自己看图、理解、搜索
4. 后面继续围绕这张图聊

但当前系统里，用户实际会遇到这些问题：

- 发图后系统并不总能真正“自己判断”
- “找像上面那张图里的女生”这类追问不一定复用上一张图
- 出错时会统一退化成“你重新发一次”，不像真的理解了问题

### 2.2 当前架构根因

根因不是一个 bug，而是三层断裂：

1. **协议层断裂**
   - 前端自然对话化了
   - 后端 `/v1/discovery/photo-search` 仍然是模式接口心智
   - `mode=auto`、`mode=face/style/celebrity` 仍然是顶层接口设计的一部分

2. **会话层断裂**
   - 发图搜索是一条链
   - 普通 discovery 对话又是一条链
   - “上一张图”没有成为统一 session memory 的一部分

3. **决策层断裂**
   - 系统内部虽然有 Agent、route、intent、hybrid 搜索等能力碎片
   - 但“什么时候搜、怎么搜、要不要追问、如何继承上一张图”还没有完全统一交给 Agent

### 2.3 当前代码状态

基于当前仓库，可以归纳为：

- 前端发现页已有图片挂输入框、缩略图展示、图片发送链路
  - [`frontend/her-app/components/her/discover-page.tsx`](../frontend/her-app/components/her/discover-page.tsx)
- discovery 会话与 timeline 已可持久化并刷新回显
  - [`frontend/her-app/hooks/use-discovery-session.ts`](../frontend/her-app/hooks/use-discovery-session.ts)
  - [`external-systems/partner-discovery-system/discovery_system/view_models.py`](../external-systems/partner-discovery-system/discovery_system/view_models.py)
- Gateway 已有照片搜索 REST 接口
  - [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
- 后端已有 face/style/hybrid/celebrity 的底层照片搜索函数
  - [`match_domain/photo_discovery_search.py`](../match_domain/photo_discovery_search.py)
- 已有 `PhotoPreferenceIntent` 和兼容层执行函数
  - [`match_domain/photo_intent_agent.py`](../match_domain/photo_intent_agent.py)

这些基础够支撑 AI Native 改造，但还没统一成一套体系。

---

## 3. AI Native 目标定义

### 3.1 本方案中的“AI Native”指什么

本方案对 AI Native 的定义不是“哪里用了模型”，而是下面五件事同时成立：

1. **单入口**
   - 用户不学模式，不选模式，不切工具

2. **统一会话**
   - 图片、文字、历史消息、结果卡片、上一轮引用，都属于一个会话上下文

3. **Agent 决策**
   - 是否直接搜
   - 要不要先追问
   - 用脸相似、风格相似、参考人物、混合搜索还是多轮 refinement
   - 这些都由 Agent 决策，而不是前端或 Gateway 顶层硬分流

4. **工具编排**
   - face/style/reference/hard-filter/rerank 这些都是内部能力
   - 不是对外暴露给前台的顶层业务模式

5. **自然延续**
   - 用户后面说“刚才那张”“还是这种感觉”“不要那么成熟”
   - 系统能沿着上一轮视觉上下文继续工作

### 3.2 非目标

本方案明确不追求：

1. 让模型直接端到端生成最终候选，不经过受控检索
2. 把 Gateway 变成不可控的自由文本接口
3. 把前端重新做成图片工具页
4. 为了“像 AI”而削弱可观测性、审计和回滚能力

---

## 4. 最终目标形态

### 4.1 用户视角

用户看到的形态应该只有这些：

1. 在发现页上传一张图片
2. 输入框里只显示图片预览
3. 可以直接发送，也可以补一句话
4. 小雅回复时像在自然聊天，不解释内部模式
5. 后续继续说：
   - `就这种感觉`
   - `还是上一张那种长相`
   - `不要太成熟`
   - `换成北京的`
   系统都能接住

### 4.2 系统视角

系统内部应该是一个统一流水线：

1. 读取本轮输入
   - 图片
   - 文本
   - 用户动作
2. 读取会话上下文
   - 最近图片
   - 最近一次视觉搜索意图
   - 最近一次候选结果
   - 当前已知硬条件
3. Agent 做本轮决策
   - 直接搜 / 先追问
   - 调哪些内部能力
   - 搜完如何解释
4. 产出统一 discovery timeline
   - 用户消息
   - 助手消息
   - 结果组
   - 后续建议

---

## 5. 总体架构

推荐把发现页图片搜索改造成下面这套架构：

```text
Discover Frontend
    |
    | 统一发送消息（文本 / 图片 / 图文）
    v
Discovery Session API
    |
    | 持久化 turn + session memory + audit
    v
Discovery Agent Runtime
    |
    | 读取统一上下文并做决策
    v
Tool Registry / Capability Layer
    |- visual_understanding
    |- search_face_similarity
    |- search_style_similarity
    |- search_reference_person
    |- apply_hard_filters
    |- rerank_candidates
    |- load_recent_visual_context
    |- persist_visual_search_memory
    v
Discovery View Builder
    |
    v
Frontend Timeline
```

### 5.1 核心原则

1. 前端只发“统一消息”，不发“图片搜索模式”
2. Agent 决定走哪种视觉理解和检索策略
3. Gateway 和 service 层提供受控工具，不做产品模式树
4. session memory 保存视觉上下文，而不只是保存文字历史

---

## 6. 核心设计：统一消息，而不是模式请求

### 6.1 废弃顶层“模式接口心智”

当前 `POST /v1/discovery/photo-search` 的问题，不只是 `auto` 支持与否，而是接口本身仍然要求调用方先理解模式。

AI Native 目标下，顶层不应再以这些问题建模：

- 这是 face 吗
- 这是 style 吗
- 这是 celebrity 吗

顶层应该统一为“发现页自然对话 turn”。

### 6.2 新的顶层请求语义

推荐最终统一成 discovery turn 请求，允许带媒体：

```json
{
  "session_id": "xxx",
  "message": {
    "text": "找长得像这张图里的女生",
    "attachments": [
      {
        "type": "image",
        "source": "data:image/jpeg;base64,..."
      }
    ]
  },
  "client_context": {
    "surface": "discover",
    "entry_point": "composer"
  }
}
```

这层语义里不再出现：

- `mode`
- `face`
- `style`
- `celebrity`

这些只能是 Agent 内部的中间推理结果，不能是顶层协议强约束。

### 6.3 兼容策略

考虑当前已有 `photo-search` 接口和前端代码，推荐分两步：

1. **第一步：兼容期**
   - discovery turn 支持 `attachments`
   - `/photo-search` 继续保留，但只作为内部兼容入口
   - 前端新链路逐步切到统一 turn

2. **第二步：收口期**
   - 前端完全不再直接调用 `/photo-search`
   - `/photo-search` 仅供内部 fallback 或旧版本兼容

---

## 7. 核心设计：统一视觉会话记忆

### 7.1 为什么必须补这一层

没有视觉会话记忆，就不可能真正支持：

- `像刚才那张图那样的`
- `按上面那张继续找`
- `不要那么成熟`
- `再像一点`

因为这些话本质上都在引用历史视觉上下文，而不是只引用文字。

### 7.2 建议新增的 session memory 结构

建议在 discovery session memory 里新增一个 `visual_context` 块：

```json
{
  "visual_context": {
    "active_reference_image": {
      "message_id": "msg-u-123",
      "media_url": "...",
      "created_at": "2026-07-18T10:00:00Z"
    },
    "active_visual_intent": {
      "mode": "hybrid",
      "query_text": "找长得像这张图里的女生",
      "confidence": 0.87,
      "routing_reasons": ["user_provided_reference_image", "text_mentions_appearance_similarity"]
    },
    "active_constraints": {
      "city": "上海",
      "age_min": 24,
      "age_max": 31
    },
    "last_result_group_id": "result-group-789",
    "last_result_profile_ids": [10001, 10028, 10051]
  }
}
```

### 7.3 维护原则

1. 用户发新图时，替换 `active_reference_image`
2. 用户继续围绕同一张图说话时，沿用已有 `active_reference_image`
3. 用户明确切换话题时，Agent 可以清空或降级 visual context
4. 结果卡片并不是记忆本身，记忆里只保留轻量引用和必要摘要

---

## 8. 核心设计：Agent 决策层

### 8.1 Agent 的职责

在 AI Native 形态里，Agent 负责的不是“陪聊”，而是完整的发现页视觉搜索决策：

1. 判断本轮是不是视觉搜索
2. 判断是否在引用上一张图
3. 判断应该直接搜，还是先追问
4. 判断适合单路召回还是多路融合
5. 判断要不要继承上一轮硬条件
6. 判断搜完后怎么解释、要不要建议下一步 refinement

### 8.2 Agent 不应做的事

Agent 不直接：

1. 绕开受控服务去拼 SQL
2. 自己构造未经校验的候选卡片
3. 直接修改 session 底层结构
4. 直接访问不受控的 profile 原始敏感字段

### 8.3 建议的 Agent 输出

Agent 每轮至少输出这些结构化结果：

```json
{
  "turn_type": "visual_search",
  "should_search_now": true,
  "should_ask_clarifying_question": false,
  "resolved_visual_plan": {
    "strategy": "hybrid",
    "reference_image_source": "active_reference_image",
    "query_text": "找长得像这张图里的女生",
    "hard_filters": {
      "city": "上海"
    }
  },
  "assistant_summary": "我先按这张图里的长相和整体感觉一起找一轮。",
  "follow_up_suggestions": [
    "偏长相一点",
    "偏气质一点",
    "换个城市"
  ]
}
```

这里的 `face/style/celebrity/hybrid` 只是 Agent 内部 plan，不是顶层接口暴露给前端的业务模式。

---

## 9. 工具层设计

### 9.1 顶层工具原则

发现页 Agent 对外不应该看到一堆“业务模式工具”：

- `search_face_mode`
- `search_style_mode`
- `search_celebrity_mode`

这种设计还是模式树，只是换了个壳。

顶层更合理的是看到一组“能力型工具”。

### 9.2 推荐工具集合

建议 Agent 可调用的工具包括：

1. `load_recent_visual_context`
   - 读取当前 session 最近视觉上下文

2. `analyze_reference_image`
   - 对图片做轻量视觉理解
   - 输出脸部可用性、风格特征、是否适合 face/style 路径

3. `parse_visual_user_intent`
   - 结合文本和上下文，解析本轮视觉意图

4. `search_face_similarity_candidates`
   - 按脸部相似检索

5. `search_style_similarity_candidates`
   - 按风格/气质/整体感觉检索

6. `search_reference_person_candidates`
   - 参考人物检索

7. `apply_candidate_hard_filters`
   - 年龄、城市、认证、关系目标等硬条件筛选

8. `rerank_visual_candidates`
   - 多路召回结果融合排序

9. `persist_visual_search_memory`
   - 把本轮视觉上下文更新回 session memory

10. `build_visual_search_timeline_items`
   - 产出 discovery timeline 结构

### 9.3 当前代码的承接关系

当前仓库已有以下可复用底层能力：

- face 相似搜索
  - [`search_similar_face_candidates`](../match_domain/photo_discovery_search.py)
- style 搜索
  - [`search_style_candidates`](../match_domain/photo_discovery_search.py)
- hybrid 搜索
  - [`search_hybrid_photo_candidates`](../match_domain/photo_discovery_search.py)
- 意图结构
  - [`PhotoPreferenceIntent`](../match_domain/photo_intent_agent.py)

建议不是推翻重写，而是：

1. 保留这些底层能力
2. 把它们从“顶层接口模式”降级成“Agent 可编排内部能力”

---

## 10. 搜索执行策略

### 10.1 默认策略

用户只发图、不补文字时，推荐默认不是硬选 `face` 或 `style`，而是：

- `hybrid` 优先

原因很简单：

1. 用户没有义务替系统先分类
2. 小雅“自己判断”的最好体现，不是先猜一个模式，而是先综合用最稳妥的策略

### 10.2 文本强提示时的策略

当文本里出现明显信号时，Agent 可以偏向某一路，但不应完全丢掉别的线索：

- `像这张脸 / 长得像 / 脸型像 / 五官像`
  - face 为主，style 为辅
- `这种感觉 / 这类气质 / 整体氛围 / 很清爽`
  - style 为主，face 为辅
- `像刘亦菲 / 像高圆圆`
  - reference person 为主，必要时补 face/style

### 10.3 多轮 refinement

如果用户是在上一轮基础上继续收窄：

- `不要太成熟`
- `再温柔一点`
- `长发一点`
- `城市换成上海`

系统不应把这视为“重新开一轮全新搜索”，而应视为：

- 在 `active_reference_image + active_visual_intent + active_constraints` 上做 refinement

### 10.4 先追问的条件

以下情况下，Agent 可以不立即搜，而是先追问一句：

1. 图片质量太差，脸部信息无法用
2. 文本目标太模糊，且结果空间过大
3. 用户说“像她”，但当前会话里没有可用 reference
4. 用户同时给出了互相冲突的高优先级条件

追问要短，不讲模式，不教用户系统怎么工作。

---

## 11. 前端落地方案

### 11.1 前端原则

前端只做三件事：

1. 展示统一聊天输入区
2. 允许消息附带图片
3. 展示 timeline 返回的结构化结果

前端不要做：

1. 模式选择
2. 图片搜索策略判断
3. “这句话是按脸还是按感觉”的本地规则判断

### 11.2 输入区交互

上传图片后：

- 只显示图片缩略图
- 用户可直接发
- 用户也可补一句自然话
- 发送行为仍然走统一 discovery turn

### 11.3 前端请求改造

推荐从：

- `submitPhotoSearch()`
- `submitTurn()`

逐步收敛到：

- `submitTurn({ text, attachments })`

过渡期可保留两个函数，但它们最终都应该汇流到同一个后端 discovery turn 入口。

### 11.4 错误呈现

前端不能再把所有错误都翻译成：

- `这张图我刚才没处理成功，你重新发一次`

建议按错误类型分层：

1. 图片无法读取
2. 当前没有找到特别贴的
3. 需要补一句更明确的话
4. 服务暂时繁忙

---

## 12. Gateway 与 Service 落地方案

### 12.1 Gateway 角色

Gateway 的职责不应该是顶层模式分流，而应该是：

1. 鉴权
2. schema 校验
3. 把统一 turn 请求转给 discovery runtime
4. 返回结构化 timeline
5. 记录审计和埋点

### 12.2 需要新增或改造的接口

推荐新增或强化以下接口：

1. `POST /v1/discovery/turns`
   - 支持 `text + attachments`
   - 成为统一入口

2. `GET /v1/discovery/sessions/{session_id}`
   - 继续作为权威视图读取入口

3. 内部兼容：
   - `/v1/discovery/photo-search`
   - 仅作为兼容层，不再作为长期前台主入口

### 12.3 需要新增的内部 service 能力

建议在 discovery 系统里补一个统一的多模态 turn 编排层，例如：

- `process_discovery_multimodal_turn(...)`

其职责：

1. 写入用户 turn
2. 解析 attachments
3. 调 Agent
4. 执行工具
5. 写回 session memory
6. 构建 timeline

---

## 13. 数据与存储改造

### 13.1 session memory

需要把视觉上下文纳入 discovery session，而不是仅在前端内存里存在。

建议存储：

1. 当前 active reference image
2. 当前 visual intent 摘要
3. 当前 hard filters
4. 当前 result group 引用
5. 最近一次 visual failure 原因

### 13.2 timeline metadata

用户消息和助手消息建议允许更丰富 metadata：

```json
{
  "media_type": "image",
  "media_url": "...",
  "visual_context_ref": {
    "reference_image_message_id": "msg-u-123",
    "intent_version": "visual-intent-v2"
  }
}
```

### 13.3 审计与回放

需要保留这些可审计对象：

1. 用户原始输入
2. Agent 决策摘要
3. 工具调用序列
4. 中间 visual plan
5. 最终结果集和排序摘要

这对线上排障、灰度和 prompt 评估都很关键。

---

## 14. 明星参考人物能力的正确归位

### 14.1 当前问题

当前 celebrity 既像一个业务模式，又像一个底层能力，还部分处于兼容/废弃状态，边界不清。

### 14.2 AI Native 方案中的定位

在 AI Native 体系里，参考人物不应是顶层业务模式，而应是：

- `reference_person_search` 这一类内部搜索策略

用户说：

- `像刘亦菲`
- `像高圆圆那种`

系统内部可以：

1. 识别 reference person
2. 获取可信参考图或参考 embedding
3. 再走受控视觉搜索

但前台不应该出现“像某明星”这种模式入口。

---

## 15. 分阶段实施方案

### 15.1 第一阶段：止血与收口

目标：先把当前“看起来自然对话，实际上协议打架”的问题止住。

要做的事：

1. 前端不再依赖模式 UI
2. 后端兼容 `auto`
3. `auto` 默认走 `hybrid`
4. 错误提示按真实类型分层
5. 补基础监控，确认图片消息成功率

产出标准：

- 上传图片直接发，不再因为 `mode` 不兼容而失败
- 不再大量出现“重新发一次”的伪错误

### 15.2 第二阶段：统一 discovery turn

目标：把图片搜索从独立请求，收口到统一 discovery turn。

要做的事：

1. discovery turn 支持 attachments
2. 前端图文消息统一走 discovery turn
3. Gateway 把多模态 turn 交给 discovery runtime
4. `/photo-search` 退居兼容层

产出标准：

- 发图和发普通文字共享一条主链路

### 15.3 第三阶段：补视觉 session memory

目标：让系统真的能接住“上一张图”“继续找”“细化一下”。

要做的事：

1. session memory 新增 visual_context
2. Agent 支持历史视觉引用
3. refinement 请求不再被当成全新孤立搜索

产出标准：

- “像刚才那张图那样的”可稳定复用上一张图

### 15.4 第四阶段：Agent 完整接管视觉搜索决策

目标：让 search strategy 真正由 Agent 决定。

要做的事：

1. 把 face/style/reference/hybrid 降级为内部能力
2. Agent 自主决定调用顺序
3. 支持必要时先追问
4. 支持多路召回与融合

产出标准：

- 用户不需要知道任何模式概念
- 系统内部不再以模式字段为顶层边界

### 15.5 第五阶段：评估、灰度与替换旧链路

目标：稳定上线并逐步淘汰旧模式接口心智。

要做的事：

1. 新旧链路 AB 对比
2. 引用上一张图成功率评估
3. 无结果满意度与二次 refinement 率评估
4. 清理前台模式残留
5. 逐步下线前台对 `/photo-search` 的直接依赖

---

## 16. 代码落点建议

### 16.1 前端

- [`frontend/her-app/components/her/discover-page.tsx`](../frontend/her-app/components/her/discover-page.tsx)
  - 保持微信式上传 UI
  - 最终把图片发送收口到统一 turn

- [`frontend/her-app/hooks/use-discovery-session.ts`](../frontend/her-app/hooks/use-discovery-session.ts)
  - 扩展 `submitTurn()`，支持 attachments
  - 减少“普通消息”和“图片消息”双轨逻辑

- [`frontend/her-app/lib/api/endpoints/discovery.ts`](../frontend/her-app/lib/api/endpoints/discovery.ts)
  - 新增统一 discovery turn 的多模态请求定义
  - 保留 photo-search 兼容入口直至迁移完成

### 16.2 Gateway

- [`external-systems/partner-http-gateway/gateway/discovery_routes.py`](../external-systems/partner-http-gateway/gateway/discovery_routes.py)
  - 新增或改造多模态 turn 入口
  - 把图片理解相关逻辑从顶层模式接口心智中抽离

### 16.3 Discovery 系统

- [`external-systems/partner-discovery-system/discovery_system/service.py`](../external-systems/partner-discovery-system/discovery_system/service.py)
- [`external-systems/partner-discovery-system/discovery_system/agent_runtime.py`](../external-systems/partner-discovery-system/discovery_system/agent_runtime.py)
- [`external-systems/partner-discovery-system/discovery_system/agent_session_store.py`](../external-systems/partner-discovery-system/discovery_system/agent_session_store.py)
- [`external-systems/partner-discovery-system/discovery_system/view_models.py`](../external-systems/partner-discovery-system/discovery_system/view_models.py)

建议在这里补：

1. visual_context memory
2. multimodal turn 编排
3. tool registry 扩展
4. timeline 视图映射

### 16.4 Match Domain

- [`match_domain/photo_discovery_search.py`](../match_domain/photo_discovery_search.py)
  - 保留 face/style/hybrid/reference 的底层能力
  - 逐步从“顶层模式服务”转成“内部受控能力层”

- [`match_domain/photo_intent_agent.py`](../match_domain/photo_intent_agent.py)
  - 从兼容式 intent 翻译层，逐步演化为 Agent 可调用的 visual plan builder

---

## 17. 验收标准

### 17.1 用户体验验收

1. 上传图片后只看到图片，不看到模式选择
2. 用户可直接发送，不需要先学会如何“按脸找/按感觉找”
3. 用户后续说“像刚才那张图”“成熟一点”“还是这种感觉”时，系统能稳定接住
4. 错误文案不再统一怪用户“重发一次”

### 17.2 架构验收

1. discovery turn 成为统一主入口
2. 顶层协议不再依赖 `mode`
3. visual context 正式进入 session memory
4. Agent 决定视觉搜索策略
5. face/style/reference/hybrid 退居内部能力层

### 17.3 数据验收

至少补以下核心指标：

1. 图片消息发送成功率
2. 有图消息转成有效 visual search 的成功率
3. “引用上一张图”识别成功率
4. refinement 成功率
5. 首轮出结果率
6. 无结果后二次交互留存率

---

## 18. 风险与应对

### 18.1 风险：一次性大改太多

应对：

- 分阶段迁移
- 保留旧接口兼容期
- 先收口协议，再收口链路，再切 Agent 决策

### 18.2 风险：Agent 自主决策导致可控性下降

应对：

- tool schema 受控
- visual plan 结构化输出
- 保留审计日志与回放
- 为高风险路径保留 deterministic fallback

### 18.3 风险：多模态上下文膨胀，影响性能

应对：

- session memory 存摘要，不存大对象
- 图片本体只保留引用
- 历史结果只保留轻量引用和 top ids

---

## 19. 最终判断

如果只修当前 bug，把 `auto` 改通，最多只能算“修好了自然对话入口的一个断点”。

如果要真正做到 AI Native，必须同时完成四件事：

1. **顶层协议统一成 discovery 多模态 turn**
2. **视觉上下文正式进入 session memory**
3. **Agent 接管视觉搜索决策**
4. **face/style/reference/hybrid 降级成内部能力层**

这四件事缺一不可。

一句话收尾：

**真正的 AI Native 不是把“让小雅自己判断”写在界面上，而是让系统内部真的具备“统一理解图、话、历史，并自主编排搜索”的能力。**

---

## 20. 方案 B 参考

如果团队决定不走当前这种渐进式收口方案，而是改走“彻底重构版”路线，可参考独立文档：

- [发现页图片搜索 AI Native 方案 B 完整落地方案](./发现页图片搜索AI%20Native方案B完整落地方案.md)

该文档描述的是：

1. 只保留 `/v1/discovery/turns` 作为正式入口
2. 彻底下线 `/photo-search` 的正式业务角色
3. 不再让 `face/style/celebrity/hybrid` 继续作为中层主骨架
4. 让 Runtime + Capability Layer 成为视觉搜索真正总编排者
