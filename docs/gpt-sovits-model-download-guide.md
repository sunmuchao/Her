# GPT-SoVITS 模型手动下载指南

## ⚠️ 重要提示

由于 Hugging Face CDN 网络访问限制，模型下载链接可能会失效或超时。请尝试以下多种方案：

---

## 方案 A：直接下载链接（推荐尝试）

### 尝试 1：直接文件链接

**s2bert48cn 模型**（约 178MB）
```
https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/s2bert48cn.pt
```

**s2dim488 模型**（约 500MB）
```
https://huggingface.co/lj1995/GPT-SoVITS/resolve/main/s2dim488.pt
```

### 尝试 2：使用国内镜像

**s2bert48cn 模型**
```
https://hf-mirror.com/lj1995/GPT-SoVITS/resolve/main/s2bert48cn.pt
```

**s2dim488 模型**
```
https://hf-mirror.com/lj1995/GPT-SoVITS/resolve/main/s2dim488.pt
```

---

## 方案 B：浏览仓库手动下载

### 步骤 1：访问仓库页面

**Hugging Face 仓库**：
```
https://huggingface.co/lj1995/GPT-SoVITS/tree/main
```

**国内镜像**：
```
https://hf-mirror.com/lj1995/GPT-SoVITS/tree/main
```

### 步骤 2：查找模型文件

在仓库页面中找到 `pretrained_models` 目录，下载以下文件：
- `s2bert48cn.pt` 或 `s2bert48cn/model.pth`
- `s2dim488.pt` 或 `s2dim488/model.pth`

---

## 方案 C：使用 Git LFS 克隆（最可靠）

如果直接下载都失效，可以使用 Git LFS 克隆整个仓库：

```bash
# 安装 Git LFS（如果未安装）
brew install git-lfs

# 初始化 Git LFS
git lfs install

# 进入项目目录
cd /Users/sunmuchao/Downloads/Her/external-systems

# 克隆整个仓库（约 2-3GB，包含所有模型）
git clone https://huggingface.co/lj1995/GPT-SoVITS GPT-SoVITS-models

# 或使用国内镜像
git clone https://hf-mirror.com/lj1995/GPT-SoVITS GPT-SoVITS-models

# 克隆完成后，找到模型文件
ls GPT-SoVITS-models/pretrained_models/
```

---

## 方案 D：使用 ModelScope（国内平台）

ModelScope 是阿里云的模型平台，国内访问速度更快：

### 步骤 1：访问 ModelScope
```
https://modelscope.cn/models
```

### 步骤 2：搜索 GPT-SoVITS
在搜索框中输入：`GPT-SoVITS`

### 步骤 3：下载模型
找到对应的模型仓库，下载预训练模型文件。

---

## 方案 E：从其他渠道获取

如果以上方案都不可行，可以尝试：

1. **百度网盘/阿里云盘**
   - 搜索关键词：`GPT-SoVITS 模型`
   - 社区分享的资源

2. **GitHub Release**
   ```
   https://github.com/RVC-Boss/GPT-SoVITS/releases
   ```
   查看是否有打包好的模型文件

3. **官方文档**
   查看 GPT-SoVITS 官方文档中的模型下载说明：
   ```
   https://github.com/RVC-Boss/GPT-SoVITS/blob/main/docs/cn/README.md
   ```

---

## 下载后的放置位置

无论使用哪种方案下载，最终需要将模型文件放到以下位置：

```bash
# 目标目录
/Users/sunmuchao/Downloads/Her/external-systems/GPT-SoVITS/GPT_SoVITS/pretrained_models/

# 如果下载的是 model.pth 文件，需要重命名
mv model.pth s2bert48cn.pt  # 第一个模型
mv model.pth s2dim488.pt    # 第二个模型

# 验证文件大小
ls -lh /Users/sunmuchao/Downloads/Her/external-systems/GPT-SoVITS/GPT_SoVITS/pretrained_models/

# 正确的文件大小应该是：
# s2bert48cn.pt: 约 178MB
# s2dim488.pt:  约 500MB
```

---

## 完成后的验证

下载完成后，运行以下命令验证：

```bash
cd /Users/sunmuchao/Downloads/Her/external-systems/GPT-SoVITS

# 检查模型文件
ls -lh GPT_SoVITS/pretrained_models/

# 启动 API 服务
./start-api-ultra-minimal.sh

# 测试语音合成
curl -X POST http://localhost:9880/tts \
  -H "Content-Type: application/json" \
  -d '{
    "text": "你好，我是小雅",
    "text_lang": "zh",
    "ref_audio_path": "reference_audio/xiaoya-sample.wav",
    "prompt_text": "你好，我是小雅",
    "prompt_lang": "zh"
  }' \
  --output test.wav

# 播放测试音频
afplay test.wav
```

---

## 常见问题

### Q: 为什么链接失效？
A: Hugging Face CDN 对某些地区有访问限制，导致链接超时或返回 404。

### Q: Git LFS 克隆很慢怎么办？
A: 使用国内镜像源：`https://hf-mirror.com/lj1995/GPT-SoVITS`

### Q: 下载的文件很小（几KB）怎么办？
A: 说明下载失败，只下载了错误页面。请尝试其他方案。

### Q: 模型文件应该是什么格式？
A: 应该是 `.pt` 或 `.pth` 文件，大小分别是 178MB 和 500MB左右。

---

## 推荐方案

基于网络环境，我推荐以下顺序：

1. **首选：方案 C（Git LFS 克隆）** - 最可靠，会下载完整仓库
2. **次选：方案 B（浏览仓库手动下载）** - 可视化，可以确认文件存在
3. **备选：方案 D（ModelScope）** - 国内平台，速度快
4. **最后：方案 E（其他渠道）** - 社区资源

---

**注意**：如果所有方案都失败，可以考虑：
- 使用 VPN 或代理访问 Hugging Face
- 请朋友帮忙下载后传输
- 或者暂时跳过语音功能，后续再补充