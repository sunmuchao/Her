# HER 系统架构改进方案

> **文档生成日期**: 2026-06-27
> **改进目标**: 从"开发环境优先"架构重构为"生产运维优先"架构
> **实施方式**: 分阶段系统性重构而非增量修补

---

## 📋 目录

- [一、问题现象与五问法根因分析](#一问题现象与五问法根因分析)
- [二、架构重构方案（分阶段）](#二架构重构方案分阶段)
- [三、实施优先级矩阵](#三实施优先级矩阵)
- [四、架构设计原则](#四架构设计原则)
- [五、验证方法](#五验证方法)

---

## 一、问题现象与五问法根因分析

### 问题 1：高可用性缺失 - 关键服务无健康检查

**问题现象**：Gateway、Scheduler、SSE Server 等核心业务服务没有健康检查机制，只有 Signaling Server 有简单的 socket 检查。

```
问题现象：Gateway/Scheduler/SSE 服务挂掉后无法自动恢复
├─ 为什么 1: Docker compose 配置中未定义 healthcheck
├─ 为什么 2: Gateway 服务虽然代码中有 /health 端点，但 docker-compose.yml 未使用
├─ 为什么 3: 开发阶段优先关注功能实现，未考虑生产级运维需求
├─ 为什么 4: 缺乏统一的健康检查标准和配置清单
└─ 为什么 5: 【根本原因】架构设计理念停留在"开发环境优先"，未从生产运维视角设计

根本对策：建立生产级健康检查规范（应用层 + Docker层 + Kubernetes层三层健康检查）
```

**影响**：
- Gateway挂掉后，所有用户请求失败，无自动恢复
- Scheduler持续运行但调用失败，产生大量错误日志
- 无法通过 Docker/Kubernetes 自动重启或流量切换

---

### 问题 2：单实例部署 - 无法水平扩展

**问题现象**：所有服务都是单实例，无副本配置。

```
问题现象：业务增长时无法通过增加实例扩容
├─ 为什么 1: Docker compose 配置中未定义 replicas 参数
├─ 为什么 2: Gateway 使用单进程 WSGI server（wsgiref.simple_server），而非生产级服务器
├─ 为什么 3: 开发阶段未考虑多实例部署的场景
├─ 为什么 4: 缺乏无状态设计指导原则（Session状态、本地缓存等）
└─ 为什么 5: 【根本原因】架构设计未遵循"云原生12因素应用"原则（可扩展性优先）

根本对策：重构为无状态服务 + 外部状态存储 + 负载均衡 + 自动扩缩容
```

**影响**：
- 单点故障风险高
- 无法应对流量峰值
- 无法通过增加实例提升吞吐量

---

### 问题 3：安全性薄弱 - 数据库空密码 + 端口全暴露

**问题现象**：MySQL 空密码、MinIO 弱密码、所有端口暴露到外部。

```
问题现象：数据库和对象存储可被外部直接访问，存在严重安全风险
├─ 为什么 1: docker-compose.yml 中 MYSQL_ALLOW_EMPTY_PASSWORD: yes
├─ 为什么 2: MinIO 密码写在配置文件中（her_minio_admin / her_minio_password）
├─ 为什么 3: 所有端口映射到宿主机（8080-8082, 3000, 9000-9001, 19530等）
├─ 为什么 4: 开发阶段优先考虑便利性，未考虑安全隔离
└─ 为什么 5: 【根本原因】缺乏"安全优先"的架构设计理念，开发和生产环境未分离

根本对策：建立安全隔离机制（网络隔离 + 密钥管理 + 端口最小暴露原则）
```

**影响**：
- 数据库可被任意连接
- MinIO 数据可被任意读写
- 生产环境部署后存在严重安全隐患

---

### 问题 4：资源管理缺失 - 无 CPU/内存限制

**问题现象**：所有服务没有配置资源限制，可能互相抢占资源。

```
问题现象：服务无资源配额，可能因资源耗尽导致整体崩溃
├─ 为什么 1: Docker compose 配置中未定义 deploy.resources 参数
├─ 为什么 2: 开发阶段未考虑多服务资源竞争场景
├─ 为什么 3: 缺乏资源监控和配额管理机制
├─ 为什么 4: 未建立服务优先级和资源分配策略
└─ 为什么 5: 【根本原因】缺乏"资源治理"的架构设计原则，未从运维成本角度考虑

根本对策：建立资源配额体系（CPU/内存限制 + 优先级分级 + 监控告警）
```

**影响**：
- Gateway 可能因大请求（小雅分析）耗尽内存，影响其他服务
- MySQL 无限制可能导致数据导入时耗尽宿主机内存
- 无法预测和规划生产环境资源需求

---

### 问题 5：依赖链脆弱 - 缺乏服务降级和熔断

**问题现象**：Bootstrap 依赖 MySQL，Gateway 依赖 Bootstrap 和 MinIO，Scheduler 依赖 Gateway，但缺少降级机制。

```
问题现象：关键服务挂掉后，依赖服务继续运行但产生大量错误
├─ 为什么 1: depends_on 只保证启动顺序，不保证运行时依赖健康
├─ 为什么 2: Gateway 连接数据库失败时无降级逻辑（如返回503而非直接报错）
├─ 为什么 3: Scheduler 调用 Gateway Internal 失败时无重试+熔断机制
├─ 为什么 4: 缺乏服务降级和熔断的设计指导
└─ 为什么 5: 【根本原因】架构设计未遵循"韧性优先"原则，未考虑分布式系统故障场景

根本对策：建立服务韧性机制（降级 + 熔断 + 重试 + 超时控制）
```

**影响**：
- MySQL 短暂重启时，Gateway 返回500而非优雅降级
- Gateway Internal 挂掉时，Scheduler 持续报错浪费资源
- 无法区分"暂时故障"和"永久故障"

---

### 问题 6：部署一致性差 - 本地 vs Docker 配置分裂

**问题现象**：本地部署和 Docker 部署配置不一致。

```
问题现象：本地启动脚本和 Docker compose 配置不同，导致行为差异
├─ 为什么 1: 历史 shell 启动和 Docker compose 并存，导致本地入口不一致
├─ 为什么 2: 端口映射不一致（本地Gateway 8765，Docker Gateway 8080）
├─ 为什么 3: 环境变量分散在多处（docker-compose.yml、.env、启动脚本硬编码）
├─ 为什么 4: 缺乏统一的配置管理规范
└─ 为什么 5: 【根本原因】缺乏"配置一致性"的架构设计原则，开发和生产环境未标准化

根本对策：建立统一配置管理体系（单一真相来源 + 环境分层 + 配置校验）
```

**影响**：
- 开发和生产环境行为不一致，难以排查问题
- 配置变更需要同步多处，容易遗漏
- 新开发者难以理解部署流程

---

### 问题 7：数据库架构风险 - 多业务共用单 MySQL 实例

**问题现象**：推荐、撮合、聊天、发现、关系账本等多个数据库共用一个 MySQL 实例。

```
问题现象：多业务共用数据库实例，相互影响性能和稳定性
├─ 为什么 1: docker-compose.yml 只启动一个 MySQL 容器
├─ 为什么 2: 通过多个 database name 分离业务，而非独立实例
├─ 为什么 3: 开发阶段优先考虑简化部署，未考虑业务隔离
├─ 为什么 4: 缺乏数据库资源隔离和优先级策略
└─ 为什么 5: 【根本原因】架构设计未遵循"故障隔离"原则，未考虑业务边界

根本对策：建立数据库隔离机制（业务分库 + 独立实例 + 资源配额 + 读写分离）
```

**影响**：
- 聊天系统高频写入影响推荐系统查询性能
- 单个业务的数据导入可能拖慢所有业务
- 无法针对不同业务独立扩容

---

### 问题 8：可观测性缺失 - 无监控指标导出

**问题现象**：Gateway、Scheduler、SSE Server 等服务无监控指标导出。

```
问题现象：无法实时监控服务健康状态和性能指标
├─ 为什么 1: Gateway 代码中未集成 Prometheus metrics 导出
├─ 为什么 2: Scheduler 只有日志输出，无结构化指标
├─ 为什么 3: 开发阶段未考虑生产级监控需求
├─ 为什么 4: 缺乏可观测性设计规范（指标 + 日志 + 链路追踪）
└─ 为什么 5: 【根本原因】架构设计未遵循"可观测性优先"原则，未从运维视角设计

根本对策：建立完整可观测性体系（Prometheus指标 + 结构化日志 + Jaeger链路追踪）
```

**影响**：
- 无法提前发现性能瓶颈
- 故障排查依赖人工查看日志
- 无法建立自动化告警机制

---

## 二、架构重构方案（分阶段）

### Phase 1：生产级基础设施重构（P0 - 立即行动）

#### 1.1 健康检查体系

**改进目标**：建立三层健康检查机制（应用层 + Docker层 + Kubernetes层）

**实施步骤**：

1. **应用层健康检查端点**
   - Gateway: `/health` 详细状态（数据库、MinIO、依赖服务）
   - Scheduler: 自检机制（数据库、Gateway Internal）
   - SSE Server: WebSocket 连接数监控

2. **Docker层健康检查配置**
   ```yaml
   services:
     gateway-public:
       healthcheck:
         test: ["CMD", "curl", "-f", "http://127.0.0.1:8080/health"]
         interval: 30s
         timeout: 10s
         retries: 3
         start_period: 40s
       restart: unless-stopped
   ```

3. **统一健康状态格式**
   ```json
   {
     "status": "healthy",
     "timestamp": "2026-06-27T10:00:00Z",
     "checks": {
       "database": {"status": "healthy", "latency_ms": 5},
       "minio": {"status": "healthy", "latency_ms": 12},
       "redis": {"status": "healthy", "latency_ms": 2}
     }
   }
   ```

---

#### 1.2 安全隔离重构

**改进目标**：建立安全隔离机制（网络隔离 + 密钥管理 + 端口最小暴露）

**实施步骤**：

1. **密钥生成与管理**
   - 创建 `scripts/generate_secrets.sh` 生成随机密钥
   - 创建 `secrets/` 目录存储密钥文件
   - 使用 Docker Secrets 机制注入密钥

2. **网络隔离设计**
   - `frontend_net`: 可访问外部（Gateway公开端口）
   - `backend_net`: 内部网络（Gateway/Scheduler通信）
   - `data_net`: 数据层网络（MySQL/MinIO/Redis严格隔离）

3. **端口最小暴露原则**
   - 仅公开 Gateway Public (8080) 和 Frontend (3000)
   - MySQL/MinIO/Redis 不暴露端口
   - Gateway Ops/Internal 仅内网访问

---

#### 1.3 服务韧性机制

**改进目标**：建立降级 + 熔断 + 重试 + 超时控制机制

**实施步骤**：

1. **Gateway 降级逻辑**
   - 数据库不可用时返回 503 + retry_after
   - MinIO 不可用时返回降级响应（无图片但可继续操作）
   - 依赖服务不可用时返回优雅错误提示

2. **Scheduler 熔断机制**
   - 使用 circuitbreaker 库实现熔断
   - Gateway Internal 连续失败5次后熔断60秒
   - 熔断期间跳过任务执行，避免资源浪费

3. **超时控制**
   - Gateway: 每个请求最长30秒
   - Scheduler: 调用 Gateway Internal 超时10秒
   - 数据库查询超时5秒

---

### Phase 2：无状态化与可观测性重构（P1 - 短期重构）

#### 2.1 无状态化重构

**改进目标**：移除本地状态，改为外部状态存储（Redis）

**实施步骤**：

1. **Redis 集成**
   - 添加 Redis 服务到 docker-compose.yml
   - 配置持久化存储（appendonly yes）
   - 设置资源限制（256MB）

2. **Gateway 会话状态外置**
   - 移除本地缓存
   - 会话状态存储到 Redis
   - 支持 TTL 过期机制

3. **Gateway 生产级服务器**
   - 从 wsgiref.simple_server 切换到 Gunicorn
   - 多进程 + 多线程配置
   - 支持 preload + gevent worker

---

#### 2.2 可观测性体系

**改进目标**：建立 Prometheus + Grafana + AlertManager 监控体系

**实施步骤**：

1. **Prometheus 指标导出**
   - Gateway: 集成 prometheus_client
   - 定义核心指标（请求计数、延迟、活跃连接）
   - 添加 `/metrics` 端点

2. **Grafana 监控面板**
   - Gateway 性能面板（QPS、延迟分布、错误率）
   - Scheduler 任务面板（成功率、执行时间）
   - 数据库监控面板（连接数、查询延迟）

3. **AlertManager 告警规则**
   - Gateway 错误率 > 5% 告警
   - Scheduler 任务失败 > 3次/小时 告警
   - MySQL 连接数 > 80% 告警

---

### Phase 3：配置统一管理（P2 - 长期演进）

#### 3.1 环境分层配置

**改进目标**：建立单一真相来源 + 环境分层配置体系

**实施步骤**：

1. **环境分层目录结构**
   ```
   config/environments/
   ├── development/
   │   ├── .env.development
   │   ├── docker-compose.override.yml
   ├── staging/
   │   ├── .env.staging
   │   ├── docker-compose.staging.yml
   └── production/
       ├── .env.production
       ├── docker-compose.production.yml
       ├── kubernetes/
   ```

2. **配置校验脚本**
   - `scripts/validate_config.py`: 校验环境变量完整性
   - 校验密钥强度、端口冲突、依赖关系
   - 启动前自动校验

3. **配置注入机制**
   - 使用 envsubst 替换环境变量
   - 启动脚本自动加载对应环境配置
   - 支持配置热更新（部分配置）

---

## 三、实施优先级矩阵

| 问题 | 严重程度 | 实施难度 | 优先级 | 预估工期 | 实施状态 |
|------|---------|---------|--------|---------|---------|
| **安全性薄弱** | 🔴 Critical | 🟢 Easy | **P0** | 1天 | ⏳ 待实施 |
| **高可用性缺失** | 🔴 Critical | 🟡 Medium | **P0** | 2天 | ⏳ 待实施 |
| **依赖链脆弱** | 🔴 Critical | 🟡 Medium | **P0** | 3天 | ⏳ 待实施 |
| **单实例部署** | 🟡 High | 🟠 Hard | **P1** | 5天 | ⏳ 待实施 |
| **数据库架构风险** | 🟡 High | 🟠 Hard | **P1** | 7天 | ⏳ 待实施（暂缓） |
| **可观测性缺失** | 🟡 High | 🟡 Medium | **P1** | 4天 | ⏳ 待实施 |
| **部署一致性差** | 🟢 Medium | 🟡 Medium | **P2** | 3天 | ⏳ 待实施 |
| **资源管理缺失** | 🟢 Medium | 🟢 Easy | **P2** | 1天 | ⏳ 待实施 |

---

## 四、架构设计原则

基于这次深度分析，建立以下架构设计原则：

### **1. 生产优先原则**
- ❌ 开发便利性不应牺牲生产稳定性
- ✅ 每个配置都要考虑生产环境的影响
- ✅ 优先考虑运维成本和故障恢复

### **2. 故障隔离原则**
- ❌ 多业务共用关键资源（数据库、网络）
- ✅ 业务边界清晰，故障不传播
- ✅ 关键服务独立部署，资源隔离

### **3. 韧性优先原则**
- ❌ 依赖服务挂掉时继续报错
- ✅ 自动降级、熔断、重试
- ✅ 区分"暂时故障"和"永久故障"

### **4. 可观测性优先原则**
- ❌ 故障排查依赖人工查看日志
- ✅ 结构化指标、自动化告警
- ✅ 监控驱动决策，而非猜测驱动

### **5. 安全优先原则**
- ❌ 密钥写在配置文件、端口全部暴露
- ✅ 密钥管理、网络隔离、最小权限
- ✅ 安全作为架构设计的第一要素

### **6. 配置一致性原则**
- ❌ 配置分散在多处，难以维护
- ✅ 单一真相来源、环境分层
- ✅ 配置变更可追溯、可验证

---

## 五、验证方法

### 5.1 功能验证

**安全性验证**：
```bash
# 验证密钥强度
scripts/validate_config.py --check-secrets

# 验证网络隔离
docker network inspect her_data_net
# 应看到 internal: true

# 验证端口暴露
docker ps --format "table {{.Names}}\t{{.Ports}}"
# 仅应看到 8080 和 3000 暴露
```

**健康检查验证**：
```bash
# 验证 Gateway 健康检查
curl http://127.0.0.1:8080/health
# 应返回 detailed health status

# 验证 Docker 健康检查
docker inspect gateway-public | grep -A5 Health
# 应看到 healthcheck 配置
```

**韧性验证**：
```bash
# 验证 Gateway 降级
docker stop mysql
curl http://127.0.0.1:8080/v1/candidates
# 应返回 503 + retry_after

# 验证 Scheduler 熔断
docker stop gateway-internal
# Scheduler 应在连续失败后熔断
```

---

### 5.2 性能验证

**无状态化验证**：
```bash
# 启动多个 Gateway 实例
docker compose up -d --scale gateway-public=3

# 验证 Redis 会话状态
redis-cli GET session:123
# 应看到会话数据
```

**可观测性验证**：
```bash
# 验证 Prometheus 指标
curl http://127.0.0.1:8080/metrics
# 应看到 gateway_requests_total 等指标

# 验证 Grafana 面板
curl http://127.0.0.1:3001/api/dashboards
# 应看到 Gateway 性能面板
```

---

### 5.3 故障演练

**故障注入测试**：
```bash
# MySQL 故障演练
docker stop mysql
# Gateway 应返回 503 而非 500
# Scheduler 应熔断而非持续报错

# MinIO 故障演练
docker stop minio
# Gateway 应返回降级响应（无图片但可继续操作）

# Gateway 故障演练
docker stop gateway-public
# Docker 应自动重启
# Frontend 应显示优雅错误页面
```

---

## 六、实施记录

### 实施进度跟踪

| 阶段 | 任务 | 开始时间 | 完成时间 | 状态 | 备注 |
|------|------|---------|---------|------|------|
| Phase 1 | 安全性加固 | 2026-06-27 | 2026-06-27 | ✅ 已完成 | 密钥生成、网络隔离、docker-compose.production.yml |
| Phase 1 | 健康检查体系 | 2026-06-27 | 2026-06-27 | ✅ 已完成 | Gateway/Scheduler/SSE 增强健康检查 |
| Phase 1 | 服务韧性机制 | 2026-06-27 | 2026-06-27 | ✅ 已完成 | Gateway降级、Scheduler熔断 |
| Phase 2 | 无状态化重构 | 2026-06-27 | 2026-06-27 | ✅ 已完成 | Redis集成到docker-compose.production.yml |
| Phase 2 | 可观测性体系 | 2026-06-27 | 2026-06-27 | ✅ 已完成 | Prometheus配置、Grafana面板、Gateway metrics |
| Phase 3 | 配置统一管理 | 2026-06-27 | 2026-06-27 | ✅ 已完成 | validate_config.py配置校验脚本 |

### 关键成果

**新增文件清单**：
- scripts/generate_secrets.sh（密钥生成脚本）
- docker-compose.production.yml（生产级部署配置）
- gateway/health_check.py（Gateway增强健康检查）
- scheduler/health_check.py（Scheduler健康检查）
- gateway/degradation.py（Gateway降级逻辑）
- scheduler/circuit_breaker.py（Scheduler熔断机制）
- gateway/metrics.py（Prometheus指标导出）
- config/prometheus.yml（Prometheus监控配置）
- config/grafana/dashboards/gateway_performance.json（Grafana监控面板）
- scripts/validate_config.py（配置校验脚本）
- docs/ARCHITECTURE_IMPROVEMENT_IMPLEMENTATION_REPORT.md（实施报告）

**配置改进清单**：
- 密钥管理：空密码 → 随机生成强密钥（Docker Secrets）
- 网络隔离：单网络 → 三层网络（frontend/backend/data）
- 端口暴露：全端口暴露 → 仅暴露8080和3000
- 健康检查：仅MySQL有健康检查 → 所有核心服务都有健康检查
- 资源限制：无限制 → 所有服务都有CPU/内存配额
- 多实例：单实例 → Gateway Public支持2副本
- Redis集成：无 → Redis 7-alpine（持久化 + 密钥认证）

---

## 七、附录

### 相关文档

- [docker-compose.yml](../docker-compose.yml) - 主容器编排配置
- [docker-compose.milvus.yml](../docker-compose.milvus.yml) - Milvus向量库配置
- [scripts/start_everything.sh](../scripts/start_everything.sh) - 全量启动脚本
- [scripts/start_local_stack.sh](../scripts/start_local_stack.sh) - 已废弃，转发到 `docker compose up -d`

### 参考资料

- [云原生12因素应用](https://12factor.net/)
- [Docker Compose 生产最佳实践](https://docs.docker.com/compose/production/)
- [Prometheus 最佳实践](https://prometheus.io/docs/practices/)
- [微服务架构设计模式](https://microservices.io/patterns/)
