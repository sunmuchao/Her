# 本地开发环境指南

## 快速启动

### 一键启动所有服务

```bash
./scripts/start_local_dev.sh
```

此脚本会:
1. ✅ 检查 Docker daemon 是否运行
2. ✅ 检查 MySQL、MinIO、Signaling Server 状态
3. ✅ 自动启动缺失的服务
4. ✅ 验证服务健康状态

### 仅检查服务状态

```bash
./scripts/start_local_dev.sh --check-only
```

---

## 必需服务清单

| 服务 | 端口 | 说明 | Docker Compose 服务名 |
|------|------|------|----------------------|
| MySQL | 3307 | 关系 ledger、推荐、匹配、聊天数据库 | `mysql` |
| MinIO | 9000 | 图片上传媒体存储 | `minio` |
| Signaling Server | 8765 | WebRTC 视频通话信令 | `signaling-server` |

---

## 手动启动单个服务

```bash
# 启动 MySQL
docker compose up -d mysql

# 启动 MinIO(图片上传需要)
docker compose up -d minio

# 启动 Signaling Server(视频通话需要)
docker compose up -d signaling-server

# 启动所有服务
docker compose up -d
```

---

## MinIO 配置信息

- **API 端点**: http://127.0.0.1:9000
- **Web 控制台**: http://127.0.0.1:9001
- **用户名**: `her_minio_admin`
- **密码**: `her_minio_password`
- **Bucket**: `her-media`

环境变量配置见 `.env`:

```bash
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=her_minio_admin
MINIO_SECRET_KEY=her_minio_password
MINIO_BUCKET=her-media
MINIO_SECURE=false
```

---

## 常见问题

### Q: 图片上传失败,提示连接 127.0.0.1:9000 被拒绝?

**原因**: MinIO 服务未启动

**解决**:

```bash
# 方法 1: 一键启动
./scripts/start_local_dev.sh

# 方法 2: 手动启动 MinIO
docker compose up -d minio

# 验证 MinIO 是否运行
curl -f http://127.0.0.1:9000/minio/health/live
```

### Q: Docker 命令失败?

**原因**: Docker daemon 未运行

**解决**:

1. 打开 Docker Desktop 应用
2. 等待 Docker 图标变绿
3. 重新执行命令

---

## 服务健康检查 API

在代码中集成健康检查:

```python
from local_dev_health_check import check_all_services, enforce_service_available

# 检查所有服务
if not check_all_services():
    print("部分服务未启动")

# 强制检查特定服务(不可用时抛异常)
enforce_service_available("minio")

# 快速检查 MinIO
from local_dev_health_check import quick_minio_check
if not quick_minio_check():
    raise RuntimeError("MinIO 服务未启动")
```

---

## 开发最佳实践

1. **启动 Gateway 前先检查服务**:
   ```bash
   ./scripts/start_local_dev.sh --check-only
   python -m gateway --host 127.0.0.1 --port 8080
   ```

2. **在应用启动时集成检查**:
   ```python
   # gateway/__main__.py 或应用入口
   import local_dev_health_check
   local_dev_health_check.check_all_services()
   ```

3. **依赖服务失败时提供清晰提示**:
   ```python
   try:
       result = upload_image(data, filename, user_id)
   except RuntimeError as e:
       if "MinIO service unavailable" in str(e):
           print("请先启动 MinIO: docker compose up -d minio")
       raise
   ```

---

## 参考文档

- Docker Compose 配置: [docker-compose.yml](docker-compose.yml)
- MinIO 存储实现: [external-systems/partner-chat-system/chat_system/media_storage.py](external-systems/partner-chat-system/chat_system/media_storage.py)
- 健康检查模块: [local_dev_health_check.py](local_dev_health_check.py)
- 环境变量配置: [.env](.env)