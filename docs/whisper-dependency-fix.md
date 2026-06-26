# Whisper 语音识别依赖问题修复

## 问题现象

### 问题 1：NumPy 版本冲突

```
A module that was compiled using NumPy 1.x cannot be run in
NumPy 2.0.2 as it may crash.
```

**原因**：
- NumPy 2.0 引入了 breaking changes
- faster-whisper 和其他依赖库使用 NumPy 1.x 编译
- NumPy 2.x 与这些库不兼容

---

### 问题 2：OpenMP 库重复初始化

```
OMP: Error #15: Initializing libiomp5.dylib, but found libiomp5.dylib already initialized.
```

**原因**：
- Intel MKL 库和 PyTorch 都链接了 OpenMP
- 多个 OpenMP 运行时实例冲突
- macOS 上常见问题

---

## 快速修复方案

### 方案 1：一键修复脚本（推荐）

```bash
cd /Users/sunmuchao/Downloads/Her
./scripts/fix-whisper-dependencies.sh
```

**自动完成**：
- ✅ 检查 NumPy 版本
- ✅ 降级到 NumPy 1.x（如果需要）
- ✅ 验证 faster-whisper 安装
- ✅ 设置环境变量

---

### 方案 2：手动修复 NumPy

```bash
# 激活虚拟环境
source .venv/bin/activate

# 卸载 NumPy 2.x
pip uninstall numpy -y

# 安装 NumPy 1.x
pip install "numpy<2"

# 验证版本
python -c "import numpy; print(numpy.__version__)"
# 应输出: 1.x.x
```

---

### 方案 3：环境变量临时修复

在运行脚本前设置环境变量：

```bash
# 修复 OpenMP 冲突
export KMP_DUPLICATE_LIB_OK=TRUE

# 运行预热脚本
python scripts/preload_whisper_model.py
```

**已自动配置**：
- ✅ [preload_whisper_model.py](../scripts/preload_whisper_model.py#L14) 已添加
- ✅ [voice_routes.py](../external-systems/partner-http-gateway/gateway/voice_routes.py#L10) 已添加

---

## 长期解决方案

### 1. 更新 requirements.txt

已在 [requirements.txt](../requirements.txt#L18) 中添加：
```txt
numpy<2  # NumPy version constraint (faster-whisper requires NumPy 1.x)
```

**效果**：
- ✅ 确保新安装使用兼容版本
- ✅ 防止 pip 自动升级到 NumPy 2.x

---

### 2. 更新依赖库

等待上游库更新以支持 NumPy 2.x：
- faster-whisper
- ctranslate2
- torch

**当前状态**：
- faster-whisper 1.2.1 不支持 NumPy 2.x
- ctranslate2 正在更新
- PyTorch 2.x 已支持 NumPy 2.x（部分）

---

## 重新安装依赖

### 完全重新安装（推荐）

```bash
# 激活虚拟环境
source .venv/bin/activate

# 清理旧依赖
pip uninstall numpy faster-whisper ctranslate2 -y

# 重新安装（使用 requirements.txt）
pip install -r requirements.txt

# 验证安装
python -c "import numpy; print('NumPy:', numpy.__version__)"
python -c "import faster_whisper; print('faster-whisper: OK')"
```

---

## 验证修复

### 1. 运行预热脚本

```bash
python scripts/preload_whisper_model.py
```

**预期输出**：
```
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
  - 语言检测: zh (概率: 0.98)
```

---

### 2. 测试语音识别

启动 Gateway 后，刷新浏览器测试语音识别：
- 按住麦克风说话
- 松开后应该立即开始识别（模型已缓存）

---

## 常见问题排查

### Q1: 仍然报 NumPy 错误

**检查版本**：
```bash
python -c "import numpy; print(numpy.__version__)"
```

**如果仍显示 2.x**：
```bash
pip uninstall numpy -y --force
pip install "numpy<2,>=1.24"
```

---

### Q2: OpenMP 错误仍然出现

**检查环境变量**：
```bash
echo $KMP_DUPLICATE_LIB_OK
```

**如果未设置**：
```bash
export KMP_DUPLICATE_LIB_OK=TRUE
```

**或修改 Python 脚本**（已在 preload_whisper_model.py 和 voice_routes.py 中添加）

---

### Q3: 模型下载成功但识别失败

**清理缓存重新下载**：
```bash
rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-*
python scripts/preload_whisper_model.py
```

---

## macOS 特定问题

macOS 上 OpenMP 冲突更常见，因为：
- Intel MKL 库在 macOS 上默认使用 OpenMP
- PyTorch 也链接了 OpenMP
- 系统可能有多个 OpenMP 实现

**macOS 推荐方案**：
1. 使用 Conda 管理 OpenMP：
   ```bash
   conda install -c conda-forge numpy=1.24
   ```

2. 或使用 Apple Silicon 版本的 PyTorch：
   ```bash
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   ```

---

## 依赖版本参考

| 依赖 | 推荐版本 | 状态 |
|------|---------|------|
| numpy | < 2, >= 1.24 | ✅ 兼容 |
| faster-whisper | 1.2.1 | ✅ 稳定 |
| ctranslate2 | >= 4.0 | ⚠️ 需要检查 |
| torch | >= 2.0 | ✅ 兼容（部分） |

---

生成时间：2026-06-26
作者：Claude Code