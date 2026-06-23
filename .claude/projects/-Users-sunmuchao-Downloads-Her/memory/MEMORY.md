# Memory Index

## Session & Vector Logic

- [会话结束和搜索完整逻辑](session-end-and-search-complete-flow.md) — 会话结束后写入画像+搜索推荐的完整系统逻辑梳理（推荐阅读）
- [会话结束写入向量库逻辑](session-end-to-vector-logic.md) — 会话结束后写入向量库和摘要信息的完整链路
- [发现页搜索推荐逻辑](discovery-page-search-logic.md) — 发现页搜索推荐的完整流程与数据结构
- [会话结束和搜索问题清单](session-end-and-search-issues.md) — 问题根因分析、严重程度评估、解决方案
- [向量筛选Agent判断完整方案](vector-filter-and-agent-judgment-complete-solution.md) — 向量筛选失效+推荐理由缺乏数据支撑的完整落地方案（数据库表结构、数据加载方案、兜底机制、实施步骤）

## Bug Fixes & Improvements

- [异步资源清理修复](async-resource-cleanup-fix.md) — 2026-06-23：修复 "Event loop is closed" 错误（VectorStoreLite.close() 正确调用 MilvusClient.close()）
- [四个核心问题修复总结](four-core-issues-fix-summary.md) — 第一批（2026-06-17）：触发时机、数据一致性、版本管理、字段统一；第二批（2026-06-18）：多样性筛选删除、LLM成本优化、向量缓存优化
- [gRPC too_many_pings 错误修复](grpc-too-many-pings-fix.md) — 2026-06-23：修复 Milvus Lite gRPC 连接错误（keepalive 配置优化）
- [JSON 序列化错误完整修复](json-serialization-error-fix-complete.md) — 2026-06-23：修复 search_partner_candidates 工具的 set → list 转换问题（三道防线：源头、中间层、终端层）

## Status & State Management

- [档案状态转换逻辑](profile_status_transition_logic.md) — profile_status四种状态（active/matched/paused/archived）的定义、转换机制和业务场景

## Testing & Monitoring

- [发现页边缘测试场景](discovery-page-edge-test-scenarios.md) — 发现页搜索推荐的复杂/边缘测试场景设计（Agent幻觉、条件冲突、多轮对话等）
- [发现页深层验证场景](discovery-page-deep-validation-scenarios.md) — 发现页画像写入、AI合并、推荐理由溯源、向量筛选正确性的深层验证场景（包含自动化验证脚本）
- [优化效果监控指标设计](optimization-monitoring-metrics-design.md) — 成本和性能监控指标设计方案（LLM调用、向量缓存、推荐质量）
- [优化修复灰度发布方案](optimization-grayscale-release-design.md) — 灰度发布流程、控制方案、回滚方案、AB测试方案