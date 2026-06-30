# 本地开发环境指南

## 唯一推荐启动方式

```bash
docker compose up -d
```

这条命令会启动完整本地栈：

- `mysql`
- `redis`
- `minio`
- `bootstrap`
- `gateway-public`
- `gateway-internal`
- `gateway-ops`
- `scheduler`
- `signaling-server`
- `frontend`

访问地址：

- 前端: `http://127.0.0.1:3000`
- Public Gateway: `http://127.0.0.1:8080`
- Internal Gateway: `http://127.0.0.1:8082`
- Ops Gateway: `http://127.0.0.1:8083`
- MinIO: `http://127.0.0.1:9000`
- MinIO Console: `http://127.0.0.1:9001`

## 启动前要求

根目录 `.env` 必须存在。

如果你保留旧 MySQL 数据卷，并且 root 有密码，需要在 `.env` 里配置：

```bash
MYSQL_ROOT_PASSWORD=你的真实root密码
```

如果仓库里已有密码文件，也可以先导出：

```bash
export MYSQL_ROOT_PASSWORD="$(cat secrets/mysql_root_password.txt)"
docker compose up -d
```

如果 Docker Hub 拉前端镜像超时，可改用镜像源：

```bash
export HER_FRONTEND_IMAGE=docker.m.daocloud.io/library/node:22-bookworm
docker compose up -d
```

## 常用命令

查看状态：

```bash
docker compose ps
```

查看关键日志：

```bash
docker compose logs -f bootstrap gateway-public frontend
```

停止整套环境：

```bash
docker compose down
```

连同孤儿容器一起清掉：

```bash
docker compose down --remove-orphans
```

## 故障判断

如果前端打不开，先看：

```bash
docker compose ps
```

正常情况下应满足：

- `bootstrap` 是 `Exited (0)`
- `gateway-public` 是 `Up`
- `frontend` 是 `Up`

如果 `bootstrap` 失败，优先检查 MySQL 密码是否正确：

```bash
docker compose logs --tail=100 bootstrap
```
