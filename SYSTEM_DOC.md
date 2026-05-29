# Her 系统架构文档

> **文档生成时间**: 2026-05-29
> **基于代码分析**: 全量扫描核心配置与业务逻辑（不含历史 MD 文档）

---

## 一、系统愿景与定位

### 1.1 核心愿景

**Her** 是一个 **AI Native 婚恋社交操作系统**，旨在通过 AI 智能代理重构传统婚恋平台的交互范式与价值主张。

**核心愿景**:
- **从"功能驱动"到"意图驱动"**: 用户无需在复杂菜单中寻找功能，通过自然对话表达意图，AI 自动理解并执行
- **从"静态推荐"到"动态生成"**: 推荐结果与展示形态根据用户画像、上下文情境实时生成，实现"千人千面"
- **从"被动匹配"到"主动代理"**: AI Agent 持续感知用户状态与环境变化，主动推送建议、编排工作流
- **从"工具辅助"到"智能伙伴"**: AI 记忆用户偏好，从历史交互学习，长期进化为用户的"恋爱顾问"

### 1.2 解决的核心痛点

**传统婚恋平台的问题**:

| 痛点 | 传统方案 | Her 的解决方式 |
|------|----------|----------------|
| **信息不对称** | 用户被动填写固定表单，AI 仅做辅助筛选 | AI Agent 主动从对话中提取偏好，动态更新画像 |
| **匹配效率低** | 硬编码规则匹配，无法理解隐性需求 | AI 深度理解意图，综合考虑上下文、情境、关系历史 |
| **交互繁琐** | 复杂表单 + 多级菜单导航 | 对话式交互，AI 自动提取参数并执行 |
| **推荐千篇一律** | 固定模板展示，千人一面 | Generative UI，界面根据任务类型动态生成 |
| **缺乏持续关怀** | 匹配后平台退出，用户独自面对 | AI Agent 持续跟进，主动推送约会建议、沟通策略 |
| **信任缺失** | 用户资料真实性难以验证 | 多维度认证体系（活体检测、语音验证、视频审核） |

### 1.3 目标用户

**核心用户画像**:
- **单身青年 (25-35岁)**: 追求高效、真实的婚恋体验，期望智能化服务
- **二次交友用户**: 对传统平台失望，寻求更智能的匹配方式
- **高净值人群**: 注重隐私与定制化服务，期望专属恋爱顾问

---

## 二、系统架构概览

### 2.1 整体架构模式

**AI Native 三层分离架构**:

```
┌─────────────────────────────────────────────────────────────────┐
│                     前端交互层 (Generative UI)                   │
│                                                                 │
│  - Next.js 16 + React 19                                        │
│  - 对话式界面 (Chat-first)                                       │
│  - 动态组件渲染 (根据 component_type)                            │
│  - 实时状态同步 (WebSocket)                                      │
└─────────────────────────────────────────────────────────────────┘
                           ↓ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────────┐
│                     AI Agent 决策层                              │
│                                                                 │
│  - Discovery Agent (发现页智能对话)                              │
│  - Chat Agent (聊天助手小雅)                                     │
│  - Matchmaker Agent (匹配决策引擎)                               │
│  - 基于 Agents SDK (OpenAI/百炼 Responses)                       │
└─────────────────────────────────────────────────────────────────┘
                           ↓ 调用工具
┌─────────────────────────────────────────────────────────────────┐
│                     业务服务层 (Microservices)                   │
│                                                                 │
│  ├─ partner-recommendation-system (推荐系统)                    │
│  ├─ partner-matchmaking-system (匹配系统)                       │
│  ├─ partner-chat-system (聊天系统)                              │
│  ├─ partner-discovery-system (发现系统)                         │
│  └─ partner-http-gateway (统一网关)                             │
└─────────────────────────────────────────────────────────────────┘
                           ↓ 数据访问
┌─────────────────────────────────────────────────────────────────┐
│                     数据存储层                                   │
│                                                                 │
│  ├─ her_recommendation (推荐库)                                 │
│  ├─ her_matchmaking (匹配库)                                    │
│  ├─ her_chat (聊天库)                                           │
│  ├─ her_discovery (发现库)                                      │
│  ├─ her_relationship_ledger (关系账本)                          │
│  ├─ her (主资料库)                                              │
│  └─ MinIO (媒体存储)                                            │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 核心设计理念

**AI Native 架构原则**:
- **Agent 作为决策大脑**: 所有业务逻辑由 AI Agent 自主决策，而非硬编码规则
- **工具纯执行**: 服务层工具只负责数据查询与执行，不包含业务逻辑
- **Prompt 表达规则**: 软约束在 Prompt 中表达，而非代码硬编码
- **原始数据返回**: 工具返回原始数据（含 component_type），AI 自主决定输出方式
- **Generative UI**: 前端根据 component_type 动态渲染组件，而非固定模板

### 2.3 技术栈

**后端**:
- Python 3.10+
- OpenAI Agents SDK / 百炼 Responses API
- PyMySQL + Pydantic (数据模型)
- APScheduler (定时任务)
- Docker (容器化部署)

**前端**:
- Next.js 16.2.6 (App Router)
- React 19
- TypeScript 5.7.3
- Tailwind CSS 4.2.0
- Radix UI (组件库)
- Playwright (E2E 测试)
- Vitest (单元测试)

**存储**:
- MySQL (多库分离)
- MinIO (媒体存储)
- Redis (缓存，可选)

---

## 三、核心功能模块详解

### 3.1 发现系统 (Discovery System)

**定位**: 用户意图理解与候选人探索的智能入口

**核心能力**:
- **智能对话引导**: AI Agent 通过自然对话理解用户偏好
- **动态候选人生成**: 根据对话上下文实时生成候选人列表
- **意图识别**: 从对话中自动提取搜索参数（年龄、地区、职业等）
- **开场白生成**: AI 自动生成个性化开场白建议

**关键文件**:
- [partner_search/search_candidates.py](partner_search/search_candidates.py): 搜索匹配核心引擎
- [match_domain/onboarding_search.py](match_domain/onboarding_search.py): 新用户首次搜索逻辑
- [match_domain/criteria_compiler.py](match_domain/criteria_compiler.py): 搜索条件编译器
- [frontend/her-app/components/her/discover-page.tsx](frontend/her-app/components/her/discover-page.tsx): 发现页前端界面

**交互流程**:
```
用户输入意图 → Discovery Agent 解析 → 编译搜索条件 → 执行搜索
→ 评估候选人 → AI 自主排序 → 返回原始数据 → 前端动态渲染
```

### 3.2 推荐系统 (Recommendation System)

**定位**: 基于用户画像与关系历史的智能推荐引擎

**核心能力**:
- **订阅式推荐刷新**: 定期刷新候选人池，推送新推荐
- **多维度评分**: 综合硬性指标、软性偏好、风险标记评分
- **置信度评估**: AI 评估推荐置信度，高置信度自主推送
- **反欺诈图谱**: 基于规则图谱识别异常用户行为

**关键文件**:
- [external-systems/partner-recommendation-system/recommendation_system/](external-systems/partner-recommendation-system/recommendation_system/)
- [match_domain/rule_config.py](match_domain/rule_config.py): 推荐规则配置
- [match_domain/gate_runner.py](match_domain/gate_runner.py): 推荐门控逻辑
- [match_domain/search_scoring_config.py](match_domain/search_scoring_config.py): 评分配置

**数据库表**:
- `profile_recommendations`: 推荐-用户关系表
- `recommendation_criteria_snapshots`: 搜索条件快照
- `rule_config_versions`: 规则配置版本表

### 3.3 匹配系统 (Matchmaking System)

**定位**: 双向匹配决策与关系状态管理

**核心能力**:
- **双向匹配**: 综合双方偏好、互惠性、风险因素
- **关系状态机**: 管理关系全生命周期（推荐→保存→冷却→匹配→关闭）
- **代理介绍 (Proxy Intro)**: AI Agent 代为联系，降低社交压力
- **冷却机制**: 防止频繁切换，保护用户心理体验

**关键文件**:
- [match_domain/ledger.py](match_domain/ledger.py): 关系账本核心逻辑
- [match_domain/model.py](match_domain/model.py): 关系状态模型定义
- [match_domain/outbox_runtime.py](match_domain/outbox_runtime.py): 异步事件发布
- [external-systems/partner-matchmaking-system/matchmaking_system/](external-systems/partner-matchmaking-system/matchmaking_system/)

**关系状态流转**:
```
NEW → RECOMMENDED → SAVED → PROXY_INTRO_ACTIVE → MATCHED → CLOSED
                 ↘ SKIPPED ↘ COOLING ↘ DIRECT_GREET_STARTED
```

### 3.4 聊天系统 (Chat System)

**定位**: 智能对话助手与用户沟通桥梁

**核心能力**:
- **小雅 AI 助手**: 智能聊天代理，主动提供约会建议
- **主动提示机制**: 小雅根据聊天内容主动提示下一步行动
- **私信管理**: 用户与候选人、小雅的双通道私信
- **媒体分享**: 图片、语音、视频通话集成
- **活体认证**: 视频验证用户身份真实性

**关键文件**:
- [external-systems/partner-chat-system/chat_system/](external-systems/partner-chat-system/chat_system/)
- [frontend/her-app/components/her/chat-page.tsx](frontend/her-app/components/her/chat-page.tsx): 聊天页面（含小雅）
- [frontend/her-app/components/her/video-call-modal.tsx](frontend/her-app/components/her/video-call-modal.tsx): 视频通话组件

**小雅主动提示逻辑**:
```typescript
// 检查聊天内容是否触发提示
if (containsActionKeywords(lastMessage)) {
  xiaoyaTriggerReason = 'detect_action_keywords'
  setShowXiaoyaChat(true) // 自动展开小雅面板
}
```

### 3.5 关系账本系统 (Relationship Ledger)

**定位**: 跨域关系时间线与状态一致性保证

**核心能力**:
- **事件溯源 (Event Sourcing)**: 所有关系变更记录为不可变事件
- **状态降维 (State Reduction)**: 从事件流降维到当前状态
- **跨域时间线**: 统一推荐、匹配、聊天、认证的时间线视图
- **审计追踪**: 完整操作日志，支持事后回溯

**关键文件**:
- [match_domain/ledger.py](match_domain/ledger.py): 账本核心逻辑
- [match_domain/outbox.py](match_domain/outbox.py): 异步事件总线
- [match_domain/ids.py](match_domain/ids.py): 实体 ID 生成规范

**事件类型**:
- `recommendation_created`: 推荐生成
- `recommendation_delivered`: 推荐送达
- `relation_action`: 用户操作（保存、跳过、联系）
- `case_event`: 代理介绍案件事件
- `relation_state_revision`: 状态快照修订

### 3.6 认证系统 (Verification System)

**定位**: 用户身份真实性验证与信任建设

**核心能力**:
- **活体检测**: 本地开源活体识别（Silent-Face / Whisper）
- **语音验证**: 语音特征比对
- **照片审核**: AI 自动审核照片真实性
- **反欺诈图谱**: 关联分析识别异常用户

**关键文件**:
- [external-systems/partner-chat-system/chat_system/verification.py](external-systems/partner-chat-system/chat_system/verification.py)
- [external-systems/partner-chat-system/chat_system/verification_photo_review.py](external-systems/partner-chat-system/chat_system/verification_photo_review.py)
- [external-systems/partner-chat-system/chat_system/fraud_graph.py](external-systems/partner-chat-system/chat_system/fraud_graph.py)
- [config/fraud_graph_rules.yaml](config/fraud_graph_rules.yaml): 反欺诈规则配置

### 3.7 用户画像系统 (Persona Memory)

**定位**: 用户偏好记忆与动态画像更新

**核心能力**:
- **收集层 (Collected Profile)**: 从对话中自动收集偏好陈述
- **推断层 (Inference Layer)**: AI 推断隐性偏好
- **持久化层**: 画像数据持久化到主资料库
- **审计追踪**: 画像变更来源可追溯（用户陈述、AI 推断、系统默认）

**关键文件**:
- [match_domain/collected_profile.py](match_domain/collected_profile.py): 收集层逻辑
- [match_domain/persona_loader.py](match_domain/persona_loader.py): 画像加载器
- [persona_memory_sync/](persona_memory_sync/): 画像同步模块

---

## 四、前端架构详解

### 4.1 核心页面组件

**主要页面**:
- [discover-page.tsx](frontend/her-app/components/her/discover-page.tsx): 发现/探索页
- [relationships-page.tsx](frontend/her-app/components/her/relationships-page.tsx): 关系管理页
- [chat-page.tsx](frontend/her-app/components/her/chat-page.tsx): 聊天页（含小雅）
- [profile-page.tsx](frontend/her-app/components/her/profile-page.tsx): 个人资料页
- [candidate-detail-page.tsx](frontend/her-app/components/her/candidate-detail-page.tsx): 候选人详情页
- [trust-center-page.tsx](frontend/her-app/components/her/trust-center-page.tsx): 信任中心
- [verification-flow-page.tsx](frontend/her-app/components/her/verification-flow-page.tsx): 认证流程页

### 4.2 核心 Hooks

**业务 Hooks**:
- [use-discovery-session.ts](frontend/her-app/hooks/use-discovery-session.ts): 发现会话管理
- [use-recommendation-inbox.ts](frontend/her-app/hooks/use-recommendation-inbox.ts): 推荐收件箱
- [use-auth-flow.ts](frontend/her-app/hooks/use-auth-flow.ts): 登录认证流程
- [use-onboarding-guard.ts](frontend/her-app/hooks/use-onboarding-guard.ts): 新用户引导守卫
- [use-voice-input.ts](frontend/her-app/hooks/use-voice-input.ts): 语音输入
- [use-webrtc-call.ts](frontend/her-app/hooks/use-webrtc-call.ts): 视频通话
- [use-signaling-websocket.ts](frontend/her-app/hooks/use-signaling-websocket.ts): WebSocket 信令

### 4.3 API 端点模块

**核心 API**:
- [discovery.ts](frontend/her-app/lib/api/endpoints/discovery.ts): 发现接口
- [recommendation.ts](frontend/her-app/lib/api/endpoints/recommendation.ts): 推荐接口
- [chat.ts](frontend/her-app/lib/api/endpoints/chat.ts): 聊天接口
- [proxy-intro.ts](frontend/her-app/lib/api/endpoints/proxy-intro.ts): 代理介绍接口
- [relations.ts](frontend/her-app/lib/api/endpoints/relations.ts): 关系接口
- [trust-hub.ts](frontend/her-app/lib/api/endpoints/trust-hub.ts): 信任中心接口
- [verification.ts](frontend/her-app/lib/api/endpoints/verification.ts): 认证接口

### 4.4 Generative UI 实现

**动态渲染逻辑**:
```typescript
// 工具返回包含 component_type
const response = await api.call('search_candidates')
if (response.data.component_type === 'DiscoveryCandidateList') {
  // 前端根据 component_type 动态选择组件
  return <DiscoveryCandidateList candidates={response.data.candidates} />
}
```

**支持的 component_type**:
- `DiscoveryCandidateList`: 发现页候选人列表
- `MatchCardList`: 匹配卡片列表
- `XiaoyaChatPanel`: 小雅聊天面板
- `VerificationFlow`: 认证流程组件
- `TrustHubDashboard`: 信任中心仪表盘

---

## 五、数据库架构详解

### 5.1 数据库分离策略

**多库分离设计**:
```
her_recommendation     → 推荐系统专用
her_matchmaking        → 匹配系统专用
her_chat               → 聊天系统专用
her_discovery          → 发现系统专用
her_relationship_ledger → 关系账本专用
her                    → 主资料库（共享）
```

**设计原则**:
- **业务隔离**: 每个领域独立数据库，避免耦合
- **扩展性**: 可按业务独立扩容
- **性能隔离**: 高频业务不影响其他系统

### 5.2 核心数据表

**推荐域**:
- `profile_recommendations`: 推荐-用户关系
- `recommendation_criteria_snapshots`: 搜索条件快照
- `rule_config_versions`: 规则配置版本

**匹配域**:
- `matchmaking_pool`: 匹配池成员
- `matchmaking_cases`: 代理介绍案件
- `matchmaking_events`: 匹配事件日志

**聊天域**:
- `chat_conversations`: 会话表
- `chat_messages`: 消息表
- `chat_participants`: 参与者表
- `verification_requests`: 认证请求
- `verification_assets`: 认证资产

**关系账本域**:
- `relation_ledger_events`: 关系事件日志
- `case_ledger_events`: 案件事件日志
- `ledger_outbox`: 异步事件发布队列

**主资料域**:
- `profiles`: 用户主资料表
- `collected_profile_statements`: 收集层陈述
- `profile_facts`: 画像事实表

### 5.3 数据迁移管理

**迁移框架**:
- [db_migrations/](db_migrations/): 迁移脚本目录
- 支持多目标库独立迁移
- 自动版本管理与回滚

**迁移示例**:
```python
# db_migrations/targets/recommendation/m0001_baseline.py
class Migration:
    def up(self, db):
        db.execute("""
            CREATE TABLE profile_recommendations (
                id INT AUTO_INCREMENT PRIMARY KEY,
                owner_id INT NOT NULL,
                target_id INT NOT NULL,
                delivery_status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
```

---

## 六、AI Agent 设计详解

### 6.1 Discovery Agent

**定位**: 发现页智能对话代理

**核心职责**:
- 理解用户自然语言意图
- 提取搜索参数（年龄、地区、职业等）
- 决策搜索策略（首搜、刷新、定向）
- 生成开场白建议
- 自主选择展示形态

**Prompt 设计原则**:
- 不包含触发词映射表
- 用自然语言描述角色与职责
- 软约束在 Prompt 表达（同城优先、年龄范围）
- 硬约束在工具执行（安全边界、数据校验）

**工具设计**:
```python
# 工具只返回原始数据
{
    "component_type": "DiscoveryCandidateList",
    "candidates": [...],
    "user_preferences": {...},
    # 不包含 instruction/output_hint
}
```

### 6.2 Chat Agent (小雅)

**定位**: 聊天助手与恋爱顾问

**核心职责**:
- 分析用户与候选人聊天内容
- 主动提示下一步行动建议
- 提供约会策略指导
- 记忆用户偏好与历史交互
- 长期进化为用户的"恋爱伙伴"

**主动提示触发条件**:
- 检测聊天中出现行动关键词（"见面"、"约会"、"吃饭"）
- 分析聊天情感走向（冷场、尴尬、积极）
- 用户长时间未回复候选人

### 6.3 Matchmaker Agent

**定位**: 匹配决策引擎

**核心职责**:
- 综合评估双向匹配度
- 决策推荐优先级排序
- 评估置信度并自主推送
- 编排代理介绍工作流

**置信度阈值设计**:
- 高置信度 (>0.85): AI 自主推送推荐
- 中置信度 (0.6-0.85): 展示但降低排序
- 低置信度 (<0.6): 需用户主动搜索

---

## 七、产品规划建议

### 7.1 当前成熟度评估

**AI Native 成熟度等级**: **L3 (代理级)**

**已实现**:
- ✅ AI 自主规划执行（Discovery Agent、Chat Agent）
- ✅ 高置信度自主推送（推荐系统）
- ✅ 多步工作流编排（代理介绍）
- ✅ 对话式交互（发现页、小雅）
- ✅ Generative UI（前端动态渲染）

**未实现**:
- ❌ 用户偏好记忆系统（L4）
- ❌ AI 从历史交互学习（L4）
- ❌ 长期个性化进化（L5）

### 7.2 未来 3-6 个月迭代方向

#### Phase 1: AI Native 深化 (Month 1-2)

**目标**: 达到 L4 (伙伴级)

**核心任务**:
1. **用户偏好记忆系统**
   - 实现 `collected_profile_statements` 完整采集链路
   - 构建偏好记忆存储与检索 API
   - Agent 集成记忆读取能力

2. **历史交互学习**
   - 构建用户行为日志分析管道
   - 实现偏好权重动态调整算法
   - Agent 根据历史优化推荐策略

3. **主动关怀增强**
   - 小雅定时推送约会建议
   - 情感状态感知与安慰机制
   - 关系进展提醒与策略指导

#### Phase 2: 信任体系完善 (Month 3-4)

**目标**: 构建完整信任闭环

**核心任务**:
1. **多维度认证集成**
   - 活体检测完整链路（生产级）
   - 语音验证集成
   - 社交账号关联验证

2. **反欺诈智能化**
   - AI 自动识别异常用户
   - 动态风控规则生成
   - 黑名单自动更新

3. **信用评分体系**
   - 构建用户信用评分模型
   - 评分影响推荐排序
   - 评分透明化展示

#### Phase 3: 商业化与运营体系 (Month 5-6)

**目标**: 构建可持续商业模式

**核心任务**:
1. **付费会员体系**
   - VIP 专属 AI 服务（深度恋爱顾问）
   - 高级认证特权
   - 无限推荐刷新

2. **运营工具体系**
   - Ops Workbench 完善（运营后台）
   - 用户行为分析仪表盘
   - AI 配置可视化编辑器

3. **增长引擎**
   - 智能邀请裂变机制
   - 新用户引导优化
   - 留存预测与干预

### 7.3 技术优化建议

#### 7.3.1 性能优化

**推荐**:
- 引入 Redis 缓存推荐结果
- 优化搜索查询（索引、分库分表）
- 异步任务队列（Celery/RQ）

**前端**:
- 图片懒加载与 CDN 加速
- WebSocket 消息压缩
- 组件级缓存

#### 7.3.2 可观测性增强

**日志**:
- 结构化日志（JSON 格式）
- Trace ID 全链路追踪
- 关键路径埋点（推荐、匹配、聊天）

**监控**:
- Grafana 业务仪表盘
- Prometheus 指标采集
- 异常告警（PagerDuty）

#### 7.3.3 安全加固

**认证**:
- OAuth 2.0 标准化
- JWT Token 短期有效
- 敏感操作二次验证

**数据**:
- 敏感字段加密存储
- 数据访问审计日志
- GDPR 合规准备

---

## 八、附录

### 8.1 关键配置文件索引

| 文件 | 用途 |
|------|------|
| [pyproject.toml](pyproject.toml) | Python 项目配置 |
| [.env.example](.env.example) | 环境变量模板 |
| [docker-compose.yml](docker-compose.yml) | Docker 编排 |
| [config/fraud_graph_rules.yaml](config/fraud_graph_rules.yaml) | 反欺诈规则 |

### 8.2 核心代码文件索引

**后端核心**:
- [partner_search/search_candidates.py](partner_search/search_candidates.py): 搜索引擎
- [match_domain/ledger.py](match_domain/ledger.py): 关系账本
- [match_domain/model.py](match_domain/model.py): 状态模型
- [match_domain/criteria_compiler.py](match_domain/criteria_compiler.py): 条件编译

**前端核心**:
- [frontend/her-app/components/her/discover-page.tsx](frontend/her-app/components/her/discover-page.tsx): 发现页
- [frontend/her-app/components/her/chat-page.tsx](frontend/her-app/components/her/chat-page.tsx): 聊天页
- [frontend/her-app/components/her/relationships-page.tsx](frontend/her-app/components/her/relationships-page.tsx): 关系页

### 8.3 外部系统索引

| 系统 | 目录 | 用途 |
|------|------|------|
| 推荐系统 | [external-systems/partner-recommendation-system/](external-systems/partner-recommendation-system/) | 推荐生成与推送 |
| 匹配系统 | [external-systems/partner-matchmaking-system/](external-systems/partner-matchmaking-system/) | 双向匹配与代理介绍 |
| 聊天系统 | [external-systems/partner-chat-system/](external-systems/partner-chat-system/) | 私信与小雅助手 |
| 发现系统 | [external-systems/partner-discovery-system/](external-systems/partner-discovery-system/) | 发现页智能探索 |
| HTTP Gateway | [external-systems/partner-http-gateway/](external-systems/partner-http-gateway/) | 统一 API 网关 |

---

## 九、总结

**Her** 是一个真正践行 **AI Native 架构原则** 的婚恋社交操作系统，通过:

1. **AI Agent 作为决策大脑**: 所有业务逻辑由 AI 自主决策
2. **对话式交互范式**: 用户通过自然语言表达意图
3. **Generative UI**: 界面根据任务动态生成
4. **持续主动代理**: AI 持续感知环境变化并主动行动
5. **事件溯源架构**: 关系状态通过事件流降维保证一致性

当前系统已达到 **L3 (代理级)** 成熟度，具备 AI 自主规划执行、多步工作流编排、高置信度自主推送能力。

未来迭代方向聚焦于:

- **深化 AI Native**: 达到 L4 (伙伴级)，实现用户偏好记忆与历史学习
- **完善信任体系**: 多维度认证、智能反欺诈、信用评分
- **构建商业模式**: 付费会员体系、运营工具、增长引擎

---

**文档维护者**: Claude Code
**最后更新**: 2026-05-29
**基于代码分析**: 全量扫描核心配置与业务逻辑