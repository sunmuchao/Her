# 发现页长时间复杂对话真实测试记录

- 测试日期: 2026-06-23
- 测试方式: 真实调用 gateway 接口与数据库取证
- 测试目标: 验证发现页长时间复杂对话下的搜索、追问、画像写入/沉淀链路
- 说明: 本次只测试，不修复

## 结论

- 我实际跑了 2 个真实 session：
  - `discovery-session-e9407e46ee2f`
  - `discovery-session-7b23ae69785d`
- 搜索链路是通的，且会真实落 `discovery_search_runs`。
- Agent 能根据多轮输入做追问，也会在部分轮次把用户条件转成搜索条件。
- `sync_requester_persona_memory` 工具真实被调用了，但返回失败，错误是 `disabled_for_testing`。
- 尽管上面的实时 persona 同步失败，仍然观察到了会话后置沉淀：
  - `conversation_summaries` 有新增
  - `user_persona_observations` 有新增
  - `user_personas` 有更新
- 测试过程中存在明显接口阻塞现象：
  - 客户端脚本在后续轮次请求时长时间挂起
  - 但后端数据库里仍持续新增 `discovery_agent_turns` / `discovery_view_snapshots`
  - 这说明“客户端等待异常”和“服务端继续处理”可能同时存在

## 关键发现

1. 搜索结果并不是纯模板假回复，真实触发了搜索。
   证据：
   - `discovery-session-e9407e46ee2f` 有 `search_run_id=355,356`
   - `discovery-session-7b23ae69785d` 有 `search_run_id=357`
   - `criteria_json` 明确包含 `cities`、`age_min`、`age_max`、`gender`、`relationship_goals`

2. 实时画像同步链路当前是故意失败的。
   证据：
   - `discovery_agent_tool_calls.tool_name=sync_requester_persona_memory`
   - `status=failed`
   - `error_code=disabled_for_testing`
   - `message=硬禁用：验证方案文档的'不插手'理想设计`

3. 即使实时同步失败，后置沉淀仍发生了。
   证据：
   - `conversation_summaries` 新增了 `negative_preferences`、`values`、`life_attitude`、`emotional_needs`、`partner_personality_preference`
   - `user_persona_observations` 新增了 `target_age_min=25`、`target_age_max=33`
   - `user_personas` 更新为 `target_age_min=25`、`target_age_max=33`、`target_cities=无锡`

4. 存在明显的接口挂起/前后端不同步风险。
   证据：
   - 我本地真实请求在后续轮次阻塞，脚本需要人工中断
   - 但 `discovery-session-7b23ae69785d` 实际已经在库里继续写到了 `turn_id=649`
   - `discovery_view_snapshots` 也继续写到了 `snapshot_id=627`

## Session A

- Session ID: `discovery-session-e9407e46ee2f`
- 状态: `active`
- 最终 phase: `results_shown`

### 我发送了什么

1. `我想认真找对象，但我现在其实有点说不清自己到底适合什么样的人。`
2. `先说硬条件吧，我人在无锡发展，最好对方也在无锡或者苏州，异地不是完全不行，但同城优先。`
3. `年龄我原来想卡在25到29，不过如果人靠谱，30到33我也可以接受。`
4. `我比较看重工作稳定，但不是只看编制，长期稳定、情绪稳定都重要。`
5. `性格上我喜欢温柔一点、真诚一点的，但也别太闷，能沟通，别让我一直猜。`

### 系统返回了什么

1. 第 1 轮返回先引导测评与自我澄清，核心回复是：
   - “先从了解自己开始”
   - 推荐做 MBTI

2. 第 2 轮返回继续追问：
   - 年龄范围
   - 学历/职业
   - 婚史/小孩

3. 第 3 轮直接触发搜索并返回一批候选人：
   - 条件: `{"age_max":33,"age_min":25,"cities":["无锡","苏州"],"gender":"female","relationship_goals":["dating","认真恋爱"]}`
   - 返回 5 个候选人
   - 代表 ID: `6092, 2379, 5176, 5054, 6566`

4. 第 4 轮没有重新搜，而是基于上一批结果做了解释性筛选：
   - 提到了医生、银行职员、审计、后端工程师这些职业稳定性
   - 提到了安全型、焦虑型、回避型依恋

5. 第 5 轮继续基于上一批候选人做人设分析：
   - 明确点名 `刘舒彤`、`于若岚`、`林舒雯`、`萧思怡`
   - 分析了“温柔真诚”“回避型”“强势”等

### 数据库证据

- `discovery_search_runs`
  - `355`: 初始首屏搜索，条件约为 `无锡 + 女 + 26-36 + 认真恋爱`
  - `356`: 第 3 轮后搜索，条件升级为 `无锡/苏州 + 女 + 25-33 + 认真恋爱`

- `discovery_agent_tool_calls`
  - `search_partner_candidates`: `succeeded`
  - `suggest_assessment`: `succeeded`
  - `sync_requester_persona_memory`: `failed`

- `conversation_summaries`
  - `negative_preferences`: `不喜欢太闷的，不喜欢让人一直猜心思的，不接受完全异地`
  - `values`: `看重工作长期稳定，情绪稳定`
  - `life_attitude`: `追求长期稳定`
  - `emotional_needs`: `需要对方情绪稳定，能直接沟通，不让自己一直猜心思`
  - `partner_personality_preference`: `情绪稳定，性格温柔真诚...`

- `user_persona_observations`
  - `target_age_min=25`
  - `target_age_max=33`

- `user_personas`
  - `target_age_min=25`
  - `target_age_max=33`
  - `target_cities=无锡`

## Session B

- Session ID: `discovery-session-7b23ae69785d`
- 状态: `active`
- 最终 phase: `collecting_preferences`

### 我发送了什么

1. `我想认真找对象，但我现在其实有点说不清自己到底适合什么样的人。`
2. `先说硬条件吧，我人在无锡发展，最好对方也在无锡或者苏州，异地不是完全不行，但同城优先。`
3. `年龄我原来想卡在25到29，不过如果人靠谱，30到33我也可以接受。`
4. `我比较看重工作稳定，但不是只看编制，长期稳定、情绪稳定都重要。`
5. `性格上我喜欢温柔一点、真诚一点的，但也别太闷，能沟通，别让我一直猜。`
6. `我自己有点慢热，之前在关系里比较缺安全感，所以希望对方愿意主动表达，不要冷暴力。`
7. `还有一点比较现实，我不太想找烟酒都很重的人，偶尔社交喝酒能接受。`

### 系统返回了什么

1. 首屏先返回一批默认候选人：
   - criteria labels: `无锡 / 女 / 26-36岁 / 先谈恋爱`
   - 候选人 ID: `6092, 2379, 6566, 7799, 1661`

2. 第 1 轮建议先做性格测试，没有直接推进搜索。

3. 第 2 到第 7 轮主要是持续追问和重复确认：
   - 年龄范围
   - 关系目标
   - 价值观与依恋风格
   - 生活习惯

4. 到第 7 轮时，系统已经把需求整理成一段总结，但仍停留在“最后确认关系目标再搜索”。

### 数据库证据

- `discovery_search_runs`
  - 只有 1 条：`357`
  - 条件仍是初始首屏条件：`{"age_max":36,"age_min":26,"cities":["无锡"],"gender":"female","relationship_goals":["dating","认真恋爱"]}`
  - 说明这段长追问过程中，尚未触发新的正式搜索

- `discovery_agent_tool_calls`
  - `search_partner_candidates`: `succeeded`
  - `suggest_assessment`: `succeeded`
  - `sync_requester_persona_memory`: `failed`

### 额外异常

- 我本地客户端在后续请求时出现长时间挂起。
- 但数据库显示后端其实继续写入了：
  - `discovery_agent_turns` 到 `turn_id=649`
  - `discovery_view_snapshots` 到 `snapshot_id=627`
- 这说明调用方感知和服务端实际执行状态可能不同步。

## 问题清单

1. `sync_requester_persona_memory` 当前真实不可用。
   - 这不是猜测，是实际 tool call 失败结果。

2. 长时间复杂对话下，接口存在挂起风险。
   - 客户端等待异常明显。
   - 但后端又继续写库，说明可能存在响应返回阶段的问题。

3. Session B 中，Agent 持续追问较久，但没有及时把已收集条件转成新的搜索。
   - 用户已提供城市、年龄、稳定性、性格、沟通方式、生活习惯
   - 但数据库只有初始首屏搜索，没有新 search run

4. Session A 与 Session B 的起始状态都带有默认候选人和默认 criteria。
   - 首屏并不是空白会话，而是先给一批默认推荐
   - 这会干扰“从零开始澄清需求”的真实体验判断

## 原始证据摘要

- `discovery-session-e9407e46ee2f`
  - turn 数: `6`
  - tool call 数: `4`
  - search run 数: `2`

- `discovery-session-7b23ae69785d`
  - turn 数: `8`
  - tool call 数: `3`
  - search run 数: `1`

- 画像沉淀结果
  - `conversation_summaries`: 有
  - `user_persona_observations`: 有
  - `user_personas`: 有更新
  - `discovery_profile_update_requests`: 本次未观察到关键新增

## 补充说明

- 我已经把真实运行中看到的“我发了什么、系统返回了什么、数据库里实际写了什么”都记录到这份文档。
- 如果你需要，我下一步可以继续补一份更偏“逐轮完整 JSON 原文”的附录版文档，但这次我先把高信号测试结论和关键证据固定下来。
