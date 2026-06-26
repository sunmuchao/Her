---
name: aliyun-sms-configuration
description: 阿里云短信服务配置指南
metadata:
  type: reference
---

# 阿里云短信服务配置指南

## 问题现象

调用发送验证码接口时返回错误：
```
短信通道未配置，请接入正式短信供应商后再发送验证码
```

## 根因分析

```
问题现象：短信发送失败，提示"短信通道未配置"
├─ 为什么 1: build_sms_provider() 返回 DisabledSmsProvider
├─ 为什么 2: 环境变量未配置或配置不完整
├─ 为什么 3: AliyunSmsProvider.is_configured_from_env() 检查失败
├─ 为什么 4: 缺少必需的阿里云凭证环境变量
└─ 为什么 5: 【根本原因】项目已实现阿里云短信，但未配置环境变量

根本对策：配置阿里云短信服务的必需环境变量
```

## 解决方案

### 步骤 1：获取阿里云短信凭证

登录[阿里云控制台](https://ram.console.aliyun.com/manage/ak)获取：

1. **AccessKey ID** 和 **AccessKey Secret**
   - 创建 AccessKey 或使用已有的
   - 推荐使用 RAM 子账号的 AccessKey（仅授予短信权限）

2. **短信签名（SignName）**
   - 在[短信控制台](https://dysms.console.aliyun.com/domestic/text/sign)申请
   - 需要审核通过后才能使用

3. **短信模板（TemplateCode）**
   - 在[短信控制台](https://dysms.console.aliyun.com/domestic/text/template)申请
   - 模板内容示例：`您的验证码为：${code}，该验证码5分钟内有效，请勿泄漏于他人！`
   - 模板参数名默认为 `code`

### 步骤 2：配置环境变量

根据你的部署方式选择对应的配置方式：

#### 方式一：Docker Compose 部署

编辑 `.env` 文件：

```bash
# 短信服务提供商（可选，不设置会自动检测）
HER_SMS_PROVIDER=aliyun

# 必需：阿里云 AccessKey（三选一环境变量名）
HER_SMS_ALIYUN_ACCESS_KEY_ID=your_access_key_id
HER_SMS_ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret

# 或使用阿里云官方标准环境变量名（推荐）
ALIBABA_CLOUD_ACCESS_KEY_ID=your_access_key_id
ALIBABA_CLOUD_ACCESS_KEY_SECRET=your_access_key_secret

# 必需：短信签名
HER_SMS_ALIYUN_SIGN_NAME=你的签名名称

# 必需：短信模板 CODE
HER_SMS_ALIYUN_TEMPLATE_CODE=SMS_123456789

# 可选：区域 ID（默认 cn-hangzhou）
HER_SMS_ALIYUN_REGION_ID=cn-hangzhou

# 可选：模板参数键名（默认 code）
HER_SMS_ALIYUN_TEMPLATE_PARAM_KEY=code
```

#### 方式二：Kubernetes 部署

创建 Secret：

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: aliyun-sms-secret
type: Opaque
stringData:
  access-key-id: your_access_key_id
  access-key-secret: your_access_key_secret
  sign-name: 你的签名名称
  template-code: SMS_123456789
```

在 Deployment 中引用：

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: her-app
spec:
  template:
    spec:
      containers:
        - name: app
          env:
            - name: HER_SMS_PROVIDER
              value: "aliyun"
            - name: HER_SMS_ALIYUN_ACCESS_KEY_ID
              valueFrom:
                secretKeyRef:
                  name: aliyun-sms-secret
                  key: access-key-id
            - name: HER_SMS_ALIYUN_ACCESS_KEY_SECRET
              valueFrom:
                secretKeyRef:
                  name: aliyun-sms-secret
                  key: access-key-secret
            - name: HER_SMS_ALIYUN_SIGN_NAME
              valueFrom:
                secretKeyRef:
                  name: aliyun-sms-secret
                  key: sign-name
            - name: HER_SMS_ALIYUN_TEMPLATE_CODE
              valueFrom:
                secretKeyRef:
                  name: aliyun-sms-secret
                  key: template-code
```

#### 方式三：直接设置环境变量

```bash
export HER_SMS_PROVIDER=aliyun
export HER_SMS_ALIYUN_ACCESS_KEY_ID=your_access_key_id
export HER_SMS_ALIYUN_ACCESS_KEY_SECRET=your_access_key_secret
export HER_SMS_ALIYUN_SIGN_NAME=你的签名名称
export HER_SMS_ALIYUN_TEMPLATE_CODE=SMS_123456789
```

### 步骤 3：验证配置

#### 方法一：代码验证

创建测试脚本 `test_sms_config.py`：

```python
#!/usr/bin/env python3
import os
import sys

# 模拟设置环境变量（实际使用时应该在系统环境中配置）
# os.environ["HER_SMS_PROVIDER"] = "aliyun"
# os.environ["HER_SMS_ALIYUN_ACCESS_KEY_ID"] = "your_key"
# os.environ["HER_SMS_ALIYUN_ACCESS_KEY_SECRET"] = "your_secret"
# os.environ["HER_SMS_ALIYUN_SIGN_NAME"] = "你的签名"
# os.environ["HER_SMS_ALIYUN_TEMPLATE_CODE"] = "SMS_123456789"

# 添加项目路径
sys.path.insert(0, "/Users/sunmuchao/Downloads/Her")

from external_systems.partner_http_gateway.gateway.auth_providers import (
    AliyunSmsProvider,
    build_sms_provider,
)

# 检查配置是否完整
if AliyunSmsProvider.is_configured_from_env():
    print("✅ 阿里云短信配置完整")
    provider = AliyunSmsProvider.from_env()
    print(f"✅ AccessKey ID: {provider._access_key_id[:8]}...")
    print(f"✅ 签名名称: {provider._sign_name}")
    print(f"✅ 模板 CODE: {provider._template_code}")
else:
    print("❌ 阿里云短信配置不完整，请检查以下环境变量：")
    print("  - HER_SMS_ALIYUN_ACCESS_KEY_ID (或 ALIBABA_CLOUD_ACCESS_KEY_ID)")
    print("  - HER_SMS_ALIYUN_ACCESS_KEY_SECRET (或 ALIBABA_CLOUD_ACCESS_KEY_SECRET)")
    print("  - HER_SMS_ALIYUN_SIGN_NAME (或 HER_SMS_SIGN_NAME)")
    print("  - HER_SMS_ALIYUN_TEMPLATE_CODE (或 HER_SMS_TEMPLATE_CODE)")
    sys.exit(1)

# 检查实际使用的 Provider
print("\n实际使用的短信 Provider:")
actual_provider = build_sms_provider()
print(f"  类型: {type(actual_provider).__name__}")
if isinstance(actual_provider, AliyunSmsProvider):
    print("  ✅ 已启用阿里云短信服务")
else:
    print(f"  ⚠️  使用的是 {type(actual_provider).__name__}，请检查 HER_SMS_PROVIDER 环境变量")
```

运行验证：

```bash
python test_sms_config.py
```

#### 方法二：发送测试短信

```bash
# 设置环境变量后，重启服务
# 调用验证码发送接口测试
curl -X POST http://localhost:8000/auth/send-code \
  -H "Content-Type: application/json" \
  -d '{"phone": "13800138000"}'
```

## 环境变量说明

### 必需环境变量

| 环境变量名 | 别名（优先级从高到低） | 说明 |
|-----------|---------------------|------|
| `HER_SMS_ALIYUN_ACCESS_KEY_ID` | `ALIBABA_CLOUD_ACCESS_KEY_ID`, `ALICLOUD_ACCESS_KEY_ID` | 阿里云 AccessKey ID |
| `HER_SMS_ALIYUN_ACCESS_KEY_SECRET` | `ALIBABA_CLOUD_ACCESS_KEY_SECRET`, `ALICLOUD_ACCESS_KEY_SECRET` | 阿里云 AccessKey Secret |
| `HER_SMS_ALIYUN_SIGN_NAME` | `HER_SMS_SIGN_NAME` | 短信签名（需在阿里云审核通过） |
| `HER_SMS_ALIYUN_TEMPLATE_CODE` | `HER_SMS_TEMPLATE_CODE` | 短信模板 CODE（需在阿里云审核通过） |

### 可选环境变量

| 环境变量名 | 默认值 | 说明 |
|-----------|--------|------|
| `HER_SMS_PROVIDER` | 自动检测 | 设置为 `aliyun` 强制使用阿里云短信 |
| `HER_SMS_ALIYUN_REGION_ID` | `cn-hangzhou` | 阿里云区域 ID |
| `HER_SMS_ALIYUN_ENDPOINT` | `https://dysmsapi.aliyuncs.com/` | 阿里云短信 API 端点 |
| `HER_SMS_ALIYUN_TEMPLATE_PARAM_KEY` | `code` | 模板参数键名 |

## 常见错误排查

### 1. 签名/模板未审核通过

**错误信息**：
```
阿里云短信发送失败：isv.SIGN_NAME_ILLEGAL
阿里云短信发送失败：isv.TEMPLATE_CODE_ILLEGAL
```

**解决方案**：
- 检查签名和模板是否已审核通过
- 确保环境变量中的签名名称和模板 CODE 与阿里云控制台一致

### 2. AccessKey 错误

**错误信息**：
```
阿里云短信发送失败：InvalidAccessKeyId.NotFound
阿里云短信发送失败：SignatureDoesNotMatch
```

**解决方案**：
- 检查 AccessKey ID 和 Secret 是否正确
- 确保 AccessKey 未被禁用

### 3. 短信发送频率限制

**错误信息**：
```
短信发送过于频繁，请稍后再试
```

**解决方案**：
- 阿里云对同一手机号的发送频率有限制
- 等待一段时间后重试
- 在阿里云控制台调整频率限制策略

### 4. 权限不足

**错误信息**：
```
阿里云短信发送失败：isv.NO_PERMISSION
```

**解决方案**：
- 确保使用的 AccessKey 有短信发送权限
- 推荐使用 RAM 子账号并仅授予 `AliyunDysmsFullAccess` 权限

## 安全建议

1. **使用 RAM 子账号**
   - 创建专用的 RAM 子账号
   - 仅授予 `AliyunDysmsFullAccess` 或更细粒度的权限
   - 定期轮换 AccessKey

2. **环境变量管理**
   - 不要将 AccessKey Secret 提交到代码仓库
   - 使用密钥管理服务（如 Kubernetes Secret、Vault）
   - 在 `.gitignore` 中添加 `.env` 文件

3. **生产环境检查**
   - 生产环境禁止使用 `HER_AUTH_FIXED_CODE`（固定验证码）
   - 生产环境禁止使用 `StubSmsProvider`
   - 代码中已内置安全检查，会自动拒绝危险配置

## 相关文档

- [阿里云短信服务文档](https://help.aliyun.com/product/44282.html)
- [阿里云 AccessKey 管理](https://ram.console.aliyun.com/manage/ak)
- [短信签名申请](https://dysms.console.aliyun.com/domestic/text/sign)
- [短信模板申请](https://dysms.console.aliyun.com/domestic/text/template)

## 相关代码

- 短信服务实现：[auth_providers.py](external-systems/partner-http-gateway/gateway/auth_providers.py)
- 配置构建函数：`build_sms_provider()` (第 555 行)
- 阿里云实现：`AliyunSmsProvider` (第 285 行)
- 配置检测：`AliyunSmsProvider.is_configured_from_env()` (第 319 行)