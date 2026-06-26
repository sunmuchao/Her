# 智能一键启动脚本

## 功能说明

**自动完成所有准备工作**：
- ✅ 停止本地服务栈
- ✅ 检测 Whisper 模型是否已下载
- ✅ 自动下载模型（如果未下载）
- ✅ 启动本地服务栈（MySQL、Gateway、Frontend）

---

## 使用方法

### 方式 1：一键启动（最简单）

```bash
cd /Users/sunmuchao/Downloads/Her
./scripts/restart_with_whisper.sh
```

**自动完成**：
1. 停止所有正在运行的服务
2. 检查 Whisper 模型是否已缓存
3. 如果未下载，自动下载模型（1-2 分钟）
4. 启动 MySQL、Gateway、Frontend
5. 显示服务状态和下一步操作

---

### 方式 2：带任务调度器启动

```bash
./scripts/restart_with_whisper.sh --with-scheduler
```

**额外启动**：
- ✅ Task Scheduler（触发 opening_probe、silence_probe 等定时任务）

---

### 方式 3：查看帮助

```bash
./scripts/restart_with_whisper.sh --help
```

---

## 脚本执行流程

```
步骤 1: 停止本地服务栈
  ├─ 停止 frontend (port 3000)
  ├─ 停止 gateway (port 8765)
  ├─ 停止 SSE server (port 8081)
  └─ 停止 scheduler（可选）

步骤 2: 检测 Whisper 模型
  ├─ 检查 ~/.cache/huggingface/hub/models--Systran--faster-whisper-small/
  └─ 判断是否需要下载

步骤 3: 自动下载模型（如果未存在）
  ├─ 使用中国镜像 https://hf-mirror.com
  ├─ 下载 small 模型（约 500MB）
  └─ 预估时间：1-2 分钟

步骤 4: 启动本地服务栈
  ├─ 启动 MySQL
  ├─ 启动 SSE server (http://127.0.0.1:8081)
  ├─ 启动 Gateway (http://127.0.0.1:8765)
  ├─ 启动 Frontend (http://127.0.0.1:3000)
  └─ 启动 Scheduler（可选）
```

---

## 输出示例

### 模型已存在

```
======================================================================
智能一键启动脚本 - Whisper 语音识别集成
======================================================================

✓ Python 虚拟环境已就绪

步骤 1：停止本地服务栈
----------------------------------------------------------------------
Stopping Her local stack...
Stopped frontend
Stopped gateway
Stopped sse-server
Her local stack stopped.

步骤 2：检测 Whisper 模型
----------------------------------------------------------------------
模型大小配置: small
模型缓存目录: ~/.cache/huggingface/hub/models--Systran--faster-whisper-small
✓ Whisper 模型已存在 (3 个文件)
无需重新下载

步骤 3：跳过模型下载（已存在）
----------------------------------------------------------------------

步骤 4：启动本地服务栈
----------------------------------------------------------------------
Starting local MySQL...
Started sse-server (pid 12345)
Started gateway (pid 12346)
Started frontend (pid 12347)

======================================================================
✅ 智能启动完成
======================================================================

服务状态：
  - MySQL:         运行中
  - SSE Server:     运行中 (http://127.0.0.1:8081)
  - Gateway:        运行中 (http://127.0.0.1:8765)
  - Frontend:       运行中 (http://127.0.0.1:3000)

Whisper 语音识别：
  - 状态: 已就绪（模型已缓存）
  - 可以立即使用语音识别功能

下一步：
  1. 打开浏览器访问 http://127.0.0.1:3000
  2. 进入发现页测试语音识别
  3. 按住麦克风说话，松开自动发送
```

---

### 模型未下载

```
步骤 2：检测 Whisper 模型
----------------------------------------------------------------------
模型大小配置: small
模型缓存目录: ~/.cache/huggingface/hub/models--Systran--faster-whisper-small
⚠ Whisper 模型未下载
开始自动下载...

步骤 3：自动下载 Whisper 模型
----------------------------------------------------------------------
使用配置：
  - 模型大小: small
  - HF 镜像: https://hf-mirror.com
  - 预估时间: 1-2 分钟

✓ 已加载环境配置: /Users/sunmuchao/Downloads/Her/.env
✓ 使用 Hugging Face 镜像: https://hf-mirror.com

======================================================================
Whisper 模型预热（提前下载）
======================================================================

配置:
  - 模型大小: small
  - 运行设备: cpu
  - 计算类型: int8
  - HF 镜像: https://hf-mirror.com
  - 预估大小: ~500MB

开始下载模型...
⚠ 使用镜像站点 https://hf-mirror.com，下载速度更快

✅ 模型下载并加载成功！
✓ 模型测试成功
  - 语言检测: zh (概率: 1.00)

======================================================================
✅ Whisper 模型已准备好，可以立即使用语音识别
======================================================================

✓ Whisper 模型下载成功
```

---

## 对比传统启动方式

### 传统方式（需要手动准备）

```bash
# 1. 停止服务
./scripts/stop_local_stack.sh

# 2. 检查模型是否存在
ls ~/.cache/huggingface/hub/models--Systran--faster-whisper-small/

# 3. 如果不存在，手动下载
python scripts/preload_whisper_model.py

# 4. 启动服务
./scripts/start_local_stack.sh
```

**问题**：
- ❌ 需要手动判断模型是否存在
- ❌ 需要手动运行多个脚本
- ❌ 容易遗漏步骤
- ❌ 首次使用体验差

---

### 智能一键启动（自动化）

```bash
./scripts/restart_with_whisper.sh
```

**优势**：
- ✅ 一条命令完成所有操作
- ✅ 自动检测模型状态
- ✅ 自动下载模型（如果需要）
- ✅ 无需记忆多个步骤
- ✅ 首次使用体验好

---

## 常见问题排查

### Q1: 模型下载失败

**可能原因**：
- 网络连接问题
- 防火墙阻止访问镜像站点
- 磁盘空间不足

**解决方案**：
```bash
# 尝试其他镜像站点
export HF_ENDPOINT=https://huggingface.co
./scripts/restart_with_whisper.sh

# 或手动下载
python scripts/preload_whisper_model.py
```

---

### Q2: 虚拟环境不存在

**错误现象**：
```
✗ Python 虚拟环境不存在
```

**解决方案**：
```bash
bash scripts/dev_setup.sh
```

---

### Q3: 服务启动失败

**检查日志**：
```bash
tail -f .run/logs/gateway.log
tail -f .run/logs/frontend.log
```

**常见问题**：
- MySQL 未启动：`./start_partner_mysql.sh`
- 端口冲突：检查端口 3000/8765/8081 是否被占用

---

## 进阶用法

### 只启动核心服务（不含调度器）

```bash
./scripts/restart_with_whisper.sh
```

**适用场景**：
- 开发调试
- 测试语音识别
- 快速启动

---

### 启动完整服务栈（含调度器）

```bash
./scripts/restart_with_whisper.sh --with-scheduler
```

**适用场景**：
- 模拟生产环境
- 测试定时任务
- 完整功能测试

---

## 脚本源码

参见：[restart_with_whisper.sh](../scripts/restart_with_whisper.sh)

---

生成时间：2026-06-26
作者：Claude Code