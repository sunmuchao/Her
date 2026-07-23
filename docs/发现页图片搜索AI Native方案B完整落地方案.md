# 发现页图片搜索 AI Native 方案 B 完整落地方案

日期：2026-07-21

> 适用范围：发现页图片上传入口、Discovery Session、Gateway、discovery runtime、视觉搜索能力层、埋点、测试、上线迁移。
>
> 本文档描述的是“彻底重构版”方案 B，不是当前已经落地的渐进式方案。它假设团队决定用一次较大的架构重整，换取更高的 AI Native 纯度、更统一的协议和更干净的内部抽象。
>
> 对应任务拆分文档见：
> [发现页图片搜索 AI Native 方案 B 任务拆分](./发现页图片搜索AI%20Native方案B任务拆分.md)

---

## 1. 结论先行

方案 B 的本质不是继续修现有链路，而是把当前“新主链路 + 旧兼容层 + 老搜索结构”整体替换成一套新的统一视觉对话系统。

一句话版：

**前台、Gateway、runtime、工具层、视觉记忆、埋点、测试，都只围绕一条统一的 discovery multimodal turn 主链路重新建设。**

这意味着：

1. 不再保留 `/v1/discovery/photo-search` 作为正式能力入口
2. 不再把 `face/style/celebrity/hybrid` 作为顶层协议或主要内部骨架
3. 不再让 service 代码承担大部分视觉搜索编排逻辑
4. 让 Agent Runtime + Capability Layer 成为真正的总调度
5. 视觉记忆从“附加状态”升级成“会话一等公民”

---

## 2. 方案 B 适用前提

只有在下面条件同时成立时，方案 B 才值得做：

1. 团队明确接受一次中高风险重构
2. 允许存在较长的联调、回归和迁移周期
3. 可以为 discovery 图片搜索单独投入完整测试资源
4. 可以接受阶段性冻结老接口能力开发
5. 目标不是“尽快可用”，而是“长期架构更纯、更统一”

如果目标是“先稳住业务、持续演进”，应优先采用已落地的渐进式方案，而不是方案 B。

---

## 3. 方案 B 的目标形态

### 3.1 用户侧目标

用户侧只保留一种交互心智：

1. 上传图片
2. 可直接发送，也可补一句自然语言
3. 小雅自己判断该怎么找
4. 后续继续说“还是上一张那种感觉”“换成上海”“温柔一点”“像某个参考人物”
5. 系统始终沿着同一个 discovery 会话继续工作

用户侧不能再感知到：

- 按脸找
- 按感觉找
- 按某个明星找
- 走的是哪条搜索链路

### 3.2 系统侧目标

系统内部也切到统一心智：

1. 顶层只有一个请求协议：`discovery multimodal turn`
2. 顶层只有一个主入口：`/v1/discovery/turns`
3. 顶层只有一种编排者：`Discovery Agent Runtime`
4. 视觉理解、候选检索、过滤、重排、解释、记忆沉淀全部走能力工具
5. visual context 成为 session state 的默认组成部分，而不是条件分支里的附加字段

---

## 4. 方案 B 与当前渐进式方案的根本区别

### 4.1 当前渐进式方案

当前渐进式方案的特点是：

1. 主链路已经统一
2. 老 `/photo-search` 还保留兼容层角色
3. 内部仍保留 `face/style/celebrity/hybrid` 作为中间决策结果
4. 底层搜索能力仍沿用现有函数体系
5. service 仍承担较多视觉搜索编排责任

### 4.2 方案 B

方案 B 要进一步做到：

1. 彻底下线 `/photo-search` 正式入口
2. 顶层和中层都不再围绕 `mode` 组织代码
3. Agent Runtime 直接调能力工具，而不是间接走旧模式路由
4. 底层搜索函数降成更深层实现细节，甚至按新抽象重写
5. visual session memory 成为 Discovery Session 的默认状态模型

---

## 5. 最终架构

方案 B 推荐的最终架构如下：

```text
Discover Frontend
    |
    | send discovery multimodal turn
    v
POST /v1/discovery/turns
    |
    | validate / persist turn / load session state
    v
Discovery Agent Runtime
    |
    | read session memory + decide tool plan
    v
Visual Capability Layer
    |- load_visual_context
    |- analyze_visual_reference
    |- resolve_visual_constraints
    |- retrieve_visual_candidates
    |- filter_visual_candidates
    |- rerank_visual_candidates
    |- explain_visual_matches
    |- persist_visual_memory
    v
Discovery Timeline Builder
    |
    v
Unified Discovery View
```

### 5.1 核心原则

1. 顶层协议只有“turn”，没有“photo search mode”
2. Runtime 决定能力顺序，service 只做受控协调
3. visual context 和 text context 统一进入 session memory
4. 观测、审计、回放全部围绕统一 turn 构建
5. 所有老接口只允许存在于迁移期，不允许继续长新逻辑

---

## 6. 新的顶层协议

### 6.1 唯一正式入口

方案 B 下，图片搜索的唯一正式入口是：

`POST /v1/discovery/turns`

请求形态：

```json
{
  "session_id": "discovery-session-xxx",
  "message": {
    "text": "还是上一张那种感觉，温柔一点，换成上海",
    "attachments": [
      {
        "type": "image",
        "source": "data:image/jpeg;base64,...",
        "role": "reference"
      }
    ]
  },
  "client_context": {
    "surface": "discover",
    "entry_point": "composer"
  }
}
```

### 6.2 顶层明确禁止的字段

顶层协议中不允许再出现：

- `mode`
- `face`
- `style`
- `celebrity_name`
- `photo_search`
- `query_type`

如果业务需要表达“某个参考人物”，必须作为自然语言意图的一部分出现，而不是顶层协议字段。

---

## 7. 内部能力模型重构

方案 B 不再让内部围绕“模式”组织，而是围绕“能力”组织。

### 7.1 统一能力集

推荐能力集合：

1. `load_visual_context`
2. `analyze_visual_reference`
3. `parse_visual_constraints`
4. `resolve_visual_followup_reference`
5. `retrieve_visual_candidates`
6. `apply_candidate_hard_filters`
7. `rerank_visual_candidates`
8. `explain_visual_matches`
9. `persist_visual_memory`

### 7.2 各能力职责

#### `load_visual_context`

读取当前 session 中最近一轮视觉上下文：

- 最近参考图
- 最近视觉偏好
- 最近结果 profile ids
- 最近 refinement 历史

#### `analyze_visual_reference`

从图片和文本里抽取结构化视觉线索：

- 五官 / 脸型倾向
- 气质 / 风格倾向
- 参考人物提示
- 是否需要沿用上一张图

#### `parse_visual_constraints`

把“温柔一点”“换成上海”“不要太成熟”这类自然语言，转成结构化 refinement 和 hard filter。

#### `resolve_visual_followup_reference`

解决“刚才那张”“上一张图”“还是这种感觉”这类引用问题，决定：

1. 是否沿用 session memory 中的 reference image
2. 是否需要追问用户重新发图
3. 是否需要同时继承上一轮的 refinement

#### `retrieve_visual_candidates`

统一候选检索入口，只暴露“给我按当前 visual plan 找候选人”，内部再决定：

- 更偏向五官相似
- 更偏向气质相似
- 更偏向参考人物
- 是否混合召回

#### `apply_candidate_hard_filters`

统一做城市、年龄、认证、教育等硬条件过滤。

#### `rerank_visual_candidates`

统一做视觉候选二次排序，包括：

- 视觉贴合度
- 当前 refinement 命中度
- 用户历史偏好
- 结果多样性

#### `explain_visual_matches`

负责把结果解释成人话，而不是由各检索器自己拼接文案。

#### `persist_visual_memory`

把本轮视觉理解结论沉淀进 session state，包括：

- active reference image
- active visual preference
- active constraints
- refinement history
- last result summary

---

## 8. Discovery Session 状态模型重构

方案 B 下，visual context 不再是补丁字段，而是正式 state schema。

### 8.1 推荐 session state 结构

```json
{
  "visual_memory": {
    "active_reference": {
      "source": "data:image/jpeg;base64,...",
      "mime_type": "image/jpeg",
      "updated_at": "2026-07-20T12:00:00+08:00"
    },
    "active_preference": {
      "visual_axes": ["soft", "gentle", "clean"],
      "reference_person": null,
      "updated_at": "2026-07-20T12:00:00+08:00"
    },
    "active_constraints": {
      "cities": ["上海"],
      "appearance_notes": ["温柔一点", "不要太成熟"]
    },
    "refinement_history": [
      "温柔一点",
      "换成上海"
    ],
    "last_result_profile_ids": [20001, 20005, 20009],
    "last_result_summary": "偏温柔、干净、通勤感的候选人",
    "updated_at": "2026-07-20T12:00:00+08:00"
  }
}
```

### 8.2 重构要求

1. `visual_memory` 成为固定 schema
2. 不再通过零散 `active_visual_intent.mode` 组织核心逻辑
3. 所有视觉 follow-up 都优先读取 `visual_memory`
4. session 回放、snapshot、调试接口统一暴露 `visual_memory`

---

## 9. Agent Runtime 重构

方案 B 的重点不是把 service 写得更复杂，而是把视觉搜索编排真正前移到 Agent Runtime。

### 9.1 Runtime 需要承担的职责

1. 理解本轮是视觉搜索、视觉 refinement、还是普通对话
2. 决定是否立刻检索还是先追问
3. 决定使用哪些能力工具以及顺序
4. 决定结果解释方式
5. 决定哪些信息需要沉淀进 visual memory

### 9.2 Runtime 不再承担的职责

以下逻辑不应继续主要写死在 service 中：

1. “看到这句话就走 face”
2. “看到那句话就走 style”
3. “有图就默认 hybrid”
4. “上一张图”的解析规则散落在 service if/else 中

这些逻辑要迁移成：

1. Runtime prompt + tool decision
2. 结构化 visual plan
3. 明确的 tool call trace

### 9.3 Runtime 输出

Runtime 每轮必须输出：

1. `turn_kind`
2. `visual_plan`
3. `tool_calls`
4. `assistant_message`
5. `result_payload`
6. `memory_patch`

---

## 10. 底层视觉搜索能力重构

方案 B 不是要求所有底层搜索算法完全推倒，但要把“旧模式函数”从主骨架上摘下来。

### 10.1 当前问题

当前底层更像：

1. `search_similar_face_candidates`
2. `search_style_candidates`
3. `search_hybrid_photo_candidates`
4. `celebrity/reference` 兼容逻辑

这会让中层天然继续围绕“模式”编排。

### 10.2 新抽象

方案 B 推荐中层统一只看一个总入口：

`retrieve_visual_candidates(plan, visual_context, constraints)`

它内部再决定：

1. 哪些召回器参与
2. 各召回器权重
3. 是并行还是串行
4. 是否 fallback

### 10.3 迁移策略

迁移期可以保留旧函数，但位置下沉：

1. 第一层：Capability API
2. 第二层：Retriever Orchestrator
3. 第三层：Legacy Search Functions

最终目标是让 Runtime 和 Service 永远不直接关心第三层名字。

---

## 11. Gateway 重构

### 11.1 路由目标

方案 B 下 Gateway 只保留：

1. `/v1/discovery/turns`
2. `/v1/discovery/sessions/*`
3. 监控与调试相关 ops 接口

### 11.2 `/photo-search` 的处理

方案 B 里，`/v1/discovery/photo-search` 只允许经历两个阶段：

#### 阶段 1：只转发，不承载任何业务逻辑

它收到请求后只做：

1. 参数兼容转换
2. 转发到 `/v1/discovery/turns`
3. 返回兼容结构

禁止继续：

1. 在该路由里新增搜索决策
2. 在该路由里新增新功能
3. 在该路由里新增新埋点语义

#### 阶段 2：正式下线

在完成调用方迁移后：

1. 直接返回废弃错误
2. 或仅在白名单环境保留短期兼容

---

## 12. 前端重构

### 12.1 目标

前端彻底只保留“自然对话 + 图片附件”的交互模型。

### 12.2 必做项

1. 删除所有 `photoSearchMode` 状态
2. 删除所有模式切换文案
3. 删除对 `/photo-search` 的正式依赖
4. 图片发送统一走 `submitDiscoveryTurn`
5. 图片 follow-up 统一走同一个 composer

### 12.3 前端文案原则

前端允许说：

- 我先看看这张图
- 你也可以补一句你更想要的感觉
- 这轮我还没找到特别贴的

前端不允许说：

- 当前按脸找
- 当前按风格找
- 当前按明星模式

---

## 13. 数据与埋点重构

方案 B 下，埋点也要围绕统一 turn，而不是围绕旧 photo-search route。

### 13.1 统一事件模型

推荐统一事件：

1. `visual_turn_received`
2. `visual_turn_clarification`
3. `visual_turn_search_started`
4. `visual_turn_results_ready`
5. `visual_turn_empty`
6. `visual_turn_failed`
7. `visual_turn_memory_reused`
8. `visual_turn_refinement_applied`

### 13.2 关键指标

至少要有：

1. 图片 turn 成功率
2. 视觉追问率
3. 上一张图复用成功率
4. refinement 生效率
5. 首轮出结果率
6. 空结果后二次交互率
7. 新旧链路迁移完成率

### 13.3 兼容期指标

迁移期要额外监控：

1. `/photo-search` 调用量
2. `/photo-search -> /turns` 转发成功率
3. 旧客户端残留占比
4. 新旧链路结果差异率

---

## 14. 测试策略

方案 B 必须把测试当成主工程，而不是附属工作。

### 14.1 单元测试

覆盖：

1. 视觉引用解析
2. refinement 结构化
3. visual memory 读写
4. capability tool 输出
5. timeline 构建

### 14.2 集成测试

覆盖：

1. 只发图
2. 发图 + 一句话
3. 继续说“按刚才那张找”
4. “还是这种感觉，换成上海”
5. 无 reference 先追问
6. 空结果
7. 服务失败
8. `/photo-search` 兼容转发

### 14.3 回归测试

覆盖：

1. 普通 discovery 文本对话不能被破坏
2. 推荐卡片、timeline、SSE 刷新不能被破坏
3. profile update prompt 不能被破坏
4. 旧客户端兼容阶段不能被破坏

### 14.4 Shadow 对比

在迁移期推荐增加 shadow compare：

1. 同一图片请求同时跑旧链路和新链路
2. 对比结果数、top ids、用户解释
3. 不直接返回 shadow 结果，只用于评估新链路

---

## 15. 迁移步骤

方案 B 推荐按 8 步走。

### 15.1 B1 建新协议

1. 冻结 `/photo-search` 新能力开发
2. 明确 `/v1/discovery/turns` 为唯一正式协议
3. 清理前端对 `mode` 的正式依赖

### 15.2 B2 建新 state schema

1. 正式定义 `visual_memory`
2. 所有 session snapshot、view、调试接口接入新 schema
3. 完成旧 state 到新 state 的迁移器

### 15.3 B3 建新 capability layer

1. 抽出统一视觉能力接口
2. Runtime 只认 capability，不认 legacy route
3. 旧函数下沉成内部实现

### 15.4 B4 Runtime 接管编排

1. 让 Runtime 生成结构化 visual plan
2. 让 Runtime 决定检索、追问、解释、记忆
3. Service 只保留 orchestration guard 和 persistence

### 15.5 B5 Gateway 变薄

1. `/photo-search` 只转发
2. `/turns` 成为唯一正式入口
3. 清理 Gateway 内的模式业务判断

### 15.6 B6 做 shadow compare

1. 关键流量双跑新旧链路
2. 建立结果差异看板
3. 达到阈值后推进切换

### 15.7 B7 下线旧入口

1. 关闭正式 `/photo-search`
2. 清理前端残留调用
3. 清理旧测试和旧文档入口

### 15.8 B8 收尾清理

1. 删除 mode 心智残留字段
2. 删除旧 route 专属埋点
3. 删除 legacy-only 代码路径

---

## 16. 文件改造范围

### 16.1 前端

- `frontend/her-app/components/her/discover-page.tsx`
- `frontend/her-app/hooks/use-discovery-session.ts`
- `frontend/her-app/lib/api/endpoints/discovery.ts`
- `frontend/her-app/lib/types/discovery.ts`
- `frontend/her-app/lib/discovery/map-discovery-view.ts`

### 16.2 Gateway

- `external-systems/partner-http-gateway/gateway/discovery_routes.py`
- `external-systems/partner-http-gateway/gateway/ops_routes.py`

### 16.3 Discovery Runtime / Service

- `external-systems/partner-discovery-system/discovery_system/agent_runtime.py`
- `external-systems/partner-discovery-system/discovery_system/service.py`
- `external-systems/partner-discovery-system/discovery_system/agent_session_store.py`
- `external-systems/partner-discovery-system/discovery_system/decision_models.py`
- `external-systems/partner-discovery-system/discovery_system/view_models.py`

### 16.4 Match Domain / Search

- `match_domain/photo_discovery_search.py`
- `match_domain/photo_intent_agent.py`
- 可能新增 `match_domain/visual_retrieval_orchestrator.py`
- 可能新增 `match_domain/visual_capabilities.py`

---

## 17. 风险

### 17.1 最大风险：重构期链路失稳

方案 B 的最大风险不是写不完，而是写完后把当前可用链路弄坏。

### 17.2 次级风险：迁移不彻底

最危险的状态不是“没做方案 B”，而是“做了一半”：

1. 顶层协议一半新一半旧
2. Runtime 一半能力化一半模式化
3. 埋点和测试各自说各自的话

### 17.3 组织风险

方案 B 需要：

1. 前端
2. Gateway
3. Discovery Runtime
4. Search / Match Domain
5. QA / 联调

同时协作，否则容易在中间层卡死。

---

## 18. 验收标准

方案 B 只有同时满足下面条件，才算真正完成：

1. 用户侧完全感知不到模式心智
2. 顶层正式协议中完全没有 `mode`
3. `/photo-search` 不再承担正式业务入口角色
4. Runtime 已成为视觉搜索总编排者
5. visual memory 已是 session 默认状态模型
6. 能力层接口已替代旧模式函数成为主骨架
7. 新旧迁移监控与 shadow compare 完整可观测
8. 关键视觉用例测试矩阵完整通过

---

## 19. 最终判断

方案 B 会得到一个更纯、更统一、更接近理想 AI Native 的系统。

但代价也非常明确：

1. 周期更长
2. 风险更高
3. 回归更重
4. 迁移更难

所以方案 B 不是“比当前方案更正确”，而是“更激进、更彻底”的另一条路线。

一句话收尾：

**方案 A 是边营业边翻新，方案 B 是按新图纸重建。**
