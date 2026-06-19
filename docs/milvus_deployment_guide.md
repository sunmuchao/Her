# Milvus 向量数据库部署方案

## 一、方案概述

### 为什么选择 Milvus

| 优势 | 说明 |
|------|------|
| **高性能** | 专门为向量搜索设计，毫秒级搜索1000万向量 |
| **开源免费** | 无需付费，自主可控 |
| **功能丰富** | 支持多种索引类型、时间衰减、版本管理 |
| **易于扩展** | 支持分布式部署，可扩展到大规模 |
| **成熟稳定** | 被大量企业使用，社区活跃 |

### 适用场景

- 用户规模：1000-10000+ 用户
- 向量数量：每个用户 5-10 个向量（personality_traits、values 等）
- 搜索需求：语义相似度搜索，时间衰减，版本管理

---

## 二、部署方式

### 方式1：Docker Compose（推荐用于开发和小规模生产）

```yaml
# docker-compose.yml
version: '3.5'

services:
  etcd:
    container_name: milvus-etcd
    image: quay.io/coreos/etcd:v3.5.5
    environment:
      - ETCD_AUTO_COMPACTION_MODE=revision
      - ETCD_AUTO_COMPACTION_RETENTION=1000
      - ETCD_QUOTA_BACKEND_BYTES=4294967296
    volumes:
      - ${DOCKER_VOLUME_DIRECTORY:-.}/volumes/etcd:/etcd
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd
    healthcheck:
      test: ["CMD", "etcdctl", "endpoint", "health"]
      interval: 30s
      timeout: 20s
      retries: 3

  minio:
    container_name: milvus-minio
    image: minio/minio:RELEASE.2023-03-20T20-16-18Z
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    volumes:
      - ${DOCKER_VOLUME_DIRECTORY:-.}/volumes/minio:/minio_data
    command: minio server /minio_data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 20s
      retries: 3

  milvus:
    container_name: milvus-standalone
    image: milvusdb/milvus:v2.3.3
    command: ["milvus", "run", "standalone"]
    security_opt:
      - seccomp:unconfined
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    volumes:
      - ${DOCKER_VOLUME_DIRECTORY:-.}/volumes/milvus:/var/lib/milvus
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]
      interval: 30s
      start_period: 90s
      timeout: 20s
      retries: 3
    ports:
      - "19530:19530"
      - "9091:9091"
    depends_on:
      - "etcd"
      - "minio"

networks:
  default:
    name: milvus
```

**启动命令**：
```bash
# 启动 Milvus
docker-compose up -d

# 查看状态
docker-compose ps

# 停止 Milvus
docker-compose down
```

---

### 方式2：Milvus Lite（最简单，适合开发测试）

```bash
# 安装 Milvus Lite（Python 包）
pip install milvus-lite

# 启动 Milvus Lite（本地文件存储）
# 不需要 Docker，直接在 Python 中启动
```

```python
# 使用 Milvus Lite
from milvus_lite import MilvusServer

# 启动本地服务器（数据存储在 ./milvus_data）
server = MilvusServer()
server.start()

# 连接地址
connection_addr = server.local_address  # 默认 localhost:19530
```

---

### 方式3：Kubernetes（适合大规模生产）

```yaml
# 使用 Milvus Operator
# 需要先安装 Kubernetes 和 Milvus Operator
# 详情参考官方文档
```

---

## 三、Python SDK 安装

```bash
# 安装 Milvus Python SDK
pip install pymilvus

# 验证安装
python -c "from pymilvus import connections; print('Milvus SDK 安装成功')"
```

---

## 四、Collection 设计

### 表结构

| 字段名 | 类型 | 说明 |
|--------|------|------|
| `vector_id` | INT64 (主键) | 向量唯一标识 |
| `user_id` | INT64 | 用户ID |
| `conversation_id` | VARCHAR(50) | 对话ID |
| `vector_type` | VARCHAR(50) | 向量类型（personality_traits/values等） |
| `vector_version` | INT64 | 版本号（用于版本管理） |
| `embedding` | FLOAT_VECTOR(768) | 768维向量（BGE-large-zh） |
| `raw_text` | VARCHAR(500) | 原始文本 |
| `create_time` | INT64 | 创建时间戳 |
| `is_active` | BOOL | 是否激活（用于软删除） |

### 向量类型定义

| vector_type | 描述 | update_policy | decay_days |
|-------------|------|---------------|------------|
| `personality_traits` | 性格特质（温柔、内向） | replace | 30 |
| `values` | 价值观（重视家庭、事业） | replace | 60 |
| `partner_expectation` | 择偶期望 | average | 30 |
| `life_attitude` | 生活态度（追求稳定） | replace | 30 |
| `emotional_needs` | 情感需求 | average | 15 |

### 索引设计

```python
# 使用 HNSW 索引（高性能，适合大规模）
index_params = {
    "metric_type": "COSINE",  # 余弦相似度
    "index_type": "HNSW",     # 高效索引
    "params": {
        "M": 16,              # 连接数
        "efConstruction": 200  # 构建参数
    }
}
```

---

## 五、环境变量配置

```bash
# Milvus 连接配置
MILVUS_HOST=localhost
MILVUS_PORT=19530

# Embedding 模型配置
EMBEDDING_MODEL=BGE-large-zh  # 中文模型
# 或
EMBEDDING_MODEL=text-embedding-3-small  # OpenAI 模型
EMBEDDING_API_KEY=your_api_key
EMBEDDING_BASE_URL=https://api.openai.com/v1  # OpenAI
# 或
EMBEDDING_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  # 阿里云
```

---

## 六、快速验证脚本

```python
# scripts/test_milvus_connection.py
from pymilvus import connections, utility

# 连接 Milvus
connections.connect(
    alias="default",
    host="localhost",
    port="19530"
)

# 检查连接
print("Milvus 连接成功！")

# 查看已有 Collection
collections = utility.list_collections()
print(f"已有 Collection: {collections}")

# 断开连接
connections.disconnect("default")
```

---

## 七、部署步骤总结

1. **安装 Docker**（如果使用 Docker Compose）
2. **启动 Milvus**：`docker-compose up -d`
3. **安装 Python SDK**：`pip install pymilvus`
4. **验证连接**：运行快速验证脚本
5. **配置环境变量**
6. **创建 Collection**（代码自动创建）

---

## 八、成本预估

| 部署方式 | 硬件成本 | 运维成本 | 适用场景 |
|---------|---------|---------|---------|
| Docker Compose | 服务器资源（2核4G起） | 低（手动维护） | 小规模生产 |
| Milvus Lite | 无额外硬件 | 无运维 | 开发测试 |
| Kubernetes | 集群资源 | 中（需要运维团队） | 大规模生产 |

---

## 九、下一步

1. 运行部署脚本（启动 Milvus）
2. 创建 Collection（代码实现）
3. 集成 embedding 模型
4. 集成到 session_end_processor.py
5. 测试向量搜索功能