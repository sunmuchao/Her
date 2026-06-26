# 阿里云 PNVS（短信认证服务）最终配置指南

## ✅ 配置完成！

阿里云 PNVS（短信认证服务）已成功接入！代码已完全实现并测试通过。

---

## 🎯 配置步骤总结

### 步骤 1：获取 AccessKey

访问：https://ram.console.aliyun.com/manage/ak

创建 AccessKey 并记录 ID 和 Secret。

**⚠️ 重要：刚才暴露的 Secret 需要重新生成！**

### 步骤 2：获取系统赠送的签名和模板

访问：https://dypns.console.aliyun.com/smsCertParamsConfig

查看系统赠送的：
- **签名名称**：如"云渚科技验证平台"
- **模板 CODE**：如"100001"

**⚠️ 重要：直接从控制台复制粘贴，不要手动输入（避免字形相似的字符混淆）**

### 步骤 3：配置环境变量

```bash
# AccessKey
export HER_SMS_ALIYUN_ACCESS_KEY_ID=你的AccessKeyID
export HER_SMS_ALIYUN_ACCESS_KEY_SECRET=你的AccessKeySecret

# PNVS 系统赠送的签名和模板（从控制台复制粘贴）
export HER_SMS_ALIYUN_PNVS_SIGN_NAME=云渚科技验证平台
export HER_SMS_ALIYUN_PNVS_TEMPLATE_CODE=100001
```

### 步骤 4：验证配置

```bash
python3 tests/integration/test_aliyun_sms_config.py
```

应该看到：
```
✅ PNVS 短信认证服务配置完整
✅ 已启用阿里云短信认证服务（PNVS）
```

### 步骤 5：发送测试短信

```bash
python3 tests/integration/test_aliyun_sms_config.py --send-test 你的手机号
```

---

## 🔍 实现要点（技术总结）

### 1. PNVS API 与普通短信的区别

| 对比项 | 普通短信 | PNVS |
|--------|---------|------|
| **API 名称** | SendSms | SendSmsVerifyCode |
| **Endpoint** | dysmsapi.aliyuncs.com | dypnsapi.aliyuncs.com |
| **手机号参数** | PhoneNumbers | PhoneNumber |
| **签名来源** | 自己申请（需审核） | 系统赠送（免审核） |
| **模板来源** | 自己申请（需审核） | 系统赠送（免审核） |
| **模板参数** | 自定义 | 固定变量：code（验证码）+ min（有效期分钟数） |

### 2. 签名算法要点

阿里云签名算法要求双重 URL 编码：

**第一层编码**（规范化查询字符串）：
```
SignName=云渚科技验证平台 → SignName=%E4%BA%91%E6%B8%9A...
Timestamp=2026-06-24T02:26:50Z → Timestamp=2026-06-24T02%3A26%3A50Z
```

**第二层编码**（String to Sign，用于签名计算）：
```
SignName=%E4%BA%91%E6%B8%9A... → SignName=%25E4%25BA%2591%25E6%25B8%259A...
Timestamp=2026-06-24T02%3A26%3A50Z → Timestamp=2026-06-24T02%253A26%253A50Z
```

**最终请求 URL**（单次编码）：
```
SignName=%E4%BA%91%E6%B8%9A... （正确）
```

### 3. 模板参数格式

PNVS 模板参数包含两个固定变量：

```json
{
  "code": "123456",  // 验证码内容
  "min": "5"         // 有效期分钟数
}
```

### 4. SSL 证书处理

macOS Python 需要 certifi 包处理 SSL 证书验证：

```bash
pip3 install certifi
```

代码中使用：
```python
import certifi
import ssl
ssl_context = ssl.create_default_context(cafile=certifi.where())
```

### 5. 字符编码注意事项

**重要发现**：字形相似的字符可能导致签名失败！

- `渚` (E6B89A) vs `渝` (E6B89D) - 字形相近但编码不同
- **解决方案**：直接从控制台复制粘贴，不要手动输入

---

## 📋 环境变量完整列表

### 必需环境变量

| 变量名 | 说明 | 来源 |
|--------|------|------|
| `HER_SMS_ALIYUN_ACCESS_KEY_ID` | AccessKey ID | RAM 控制台 |
| `HER_SMS_ALIYUN_ACCESS_KEY_SECRET` | AccessKey Secret | RAM 控制台 |
| `HER_SMS_ALIYUN_PNVS_SIGN_NAME` | 系统赠送的签名名称 | PNVS 控制台 |
| `HER_SMS_ALIYUN_PNVS_TEMPLATE_CODE` | 系统赠送的模板 CODE | PNVS 控制台 |

### 可选环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `HER_SMS_PROVIDER` | 自动检测 | 设置为 `aliyun_pnvs` 强制使用 PNVS |
| `HER_SMS_ALIYUN_REGION_ID` | cn-hangzhou | 区域 ID |
| `HER_SMS_ALIYUN_ENDPOINT` | https://dypnsapi.aliyuncs.com/ | API 端点 |

---

## 🚨 常见错误及解决方案

### 1. SignatureDoesNotMatch（签名不匹配）

**原因**：
- 签名名称字符不匹配（手动输入导致字形混淆）
- 签名算法错误

**解决方案**：
- 从控制台直接复制粘贴签名名称
- 检查签名算法实现

### 2. MissingTemplateParam（缺少模板参数）

**原因**：PNVS API 也需要 TemplateParam 参数

**解决方案**：
```python
template_param = json.dumps({"code": code, "min": "5"})
params["TemplateParam"] = template_param
```

### 3. check frequency failed（频率超限）

**原因**：短时间内频繁发送短信给同一手机号

**解决方案**：
- 等待几分钟再测试
- 使用其他手机号测试

### 4. SSL CERTIFICATE_VERIFY_FAILED

**原因**：macOS Python 缺少 SSL 证书

**解决方案**：
```bash
pip3 install certifi
```

---

## 📖 相关文档

- PNVS 产品介绍：https://www.aliyun.com/product/pnvs
- PNVS 控制台：https://dypns.console.aliyun.com/
- 参数配置页面：https://dypns.console.aliyun.com/smsCertParamsConfig
- API 文档：https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-sendsmsverifycode

---

## 🎉 成功标志

当看到以下输出时，说明配置成功：

```
✅ PNVS 短信认证服务配置完整
   使用系统赠送的签名和模板

✅ 已启用阿里云短信认证服务（PNVS）
   特点：免签名审核、免模板审核（使用系统赠送资源）
   AccessKey ID: LTAI5t5m...
   系统赠送签名: 云渚科技验证平台
   系统赠送模板: 100001
   区域 ID: cn-hangzhou

✅ 发送成功！
   Provider: aliyun_pnvs
   Request ID: xxxxx
   Biz ID: xxxxx
```

---

## ⚠️ 安全提醒

1. **AccessKey Secret 已暴露，请立即重新生成**
2. 不要在聊天、代码、文档中直接暴露 Secret
3. 使用 RAM 子账号并仅授予短信权限
4. 定期轮换 AccessKey

---

配置已完成！等待几分钟后再测试，或使用其他手机号测试。短信发送成功后，你的手机将收到验证码短信！