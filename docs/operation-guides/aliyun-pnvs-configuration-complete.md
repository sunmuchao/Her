# 阿里云 PNVS 短信认证服务配置完成总结

## ✅ 配置成功！

阿里云 PNVS（短信认证服务）已成功接入并测试通过。

---

## 📋 完成的全部工作

### 1. 代码实现

**新增 AliyunPnvsProvider 类**（支持 PNVS API）：
- ✅ 使用专用 API：`SendSmsVerifyCode`（不是普通短信的 SendSms）
- ✅ 使用专用 Endpoint：`https://dypnsapi.aliyuncs.com/`
- ✅ 实现正确的签名算法（双重 URL 编码）
- ✅ 正确的参数名：`PhoneNumber`（不是 PhoneNumbers）
- ✅ 模板参数：`{"code": "验证码", "min": "有效期分钟数"}`

**文件位置**：
- [external-systems/partner-http-gateway/gateway/auth_providers.py](external-systems/partner-http-gateway/gateway/auth_providers.py)

### 2. 配置修改

**`.env` 文件修改**：

```bash
# ✅ PNVS 短信认证服务配置（已启用）
HER_SMS_PROVIDER=aliyun_pnvs
HER_SMS_ALIYUN_ACCESS_KEY_ID=LTAI5t5mKE1YFnmHoL4Da4D9
HER_SMS_ALIYUN_ACCESS_KEY_SECRET=HYbj1056bzG6hqsIVYSRujcSf3N2GX
HER_SMS_ALIYUN_PNVS_SIGN_NAME=云渚科技验证平台
HER_SMS_ALIYUN_PNVS_TEMPLATE_CODE=100001
HER_SMS_ALIYUN_REGION_ID=cn-hangzhou
HER_SMS_ALIYUN_ENDPOINT=https://dypnsapi.aliyuncs.com/

# ❌ 固定验证码配置（已移除）
# HER_AUTH_FIXED_CODE=123456  ← 移除后使用真实验证码
```

### 3. SSL 证书修复

**macOS Python SSL 证书问题**：
- ✅ 安装 certifi 包
- ✅ 在代码中使用 certifi 的证书路径
- ✅ 所有 HTTPS 请求都使用正确的 SSL context

### 4. 测试验证

**测试结果**：
- ✅ 签名验证成功
- ✅ API 调用成功
- ✅ 短信发送成功（验证码：275619）
- ✅ 返回正确的响应数据

**测试 API**：
```bash
curl -s http://127.0.0.1:8080/v1/auth/sms/send-code \
  -H "Content-Type: application/json" \
  -d '{"phone":"18846811193"}'
```

**响应示例**：
```json
{
    "challenge_id": "otp-35e61a65a0cc4c24",
    "delivery": {
        "channel": "sms",
        "masked_phone": "188****1193",
        "expires_in_seconds": 300,
        "resend_in_seconds": 60,
        "provider": "aliyun_pnvs"  ← 使用 PNVS
    },
    "flow": {
        "scenario": "new",
        "next_path": "/onboarding"
    }
}
```

---

## 🔍 关键发现与解决

### 问题 1：字形相似的字符混淆

**问题**：
- `渚` (E6B89A) vs `渝` (E6B89D) - 字形相近但 UTF-8 编码不同
- 手动输入容易出错

**解决方案**：
- ✅ 直接从阿里云控制台复制粘贴签名名称
- ✅ 不要手动输入，避免字形混淆

### 问题 2：PNVS 也需要模板参数

**问题**：
- 初期认为 PNVS 不需要模板参数
- 实际 API 报错：`TemplateParam is mandatory for this action`

**解决方案**：
- ✅ PNVS 模板参数格式：`{"code": "验证码", "min": "有效期分钟数"}`
- ✅ 变量名是 `min`（不是 `expireTime`）

### 问题 3：固定验证码配置干扰

**问题**：
- `.env` 中保留的 `HER_AUTH_FIXED_CODE=123456` 导致：
  - 系统使用固定验证码
  - 用户只能输入 123456 才能验证
  - 无法测试真实短信功能

**解决方案**：
- ✅ 移除 `HER_AUTH_FIXED_CODE=123456` 配置
- ✅ 使用真实短信验证码

### 问题 4：环境变量未生效

**问题**：
- 临时环境变量（export）只在当前 shell 有效
- 已运行的应用不会自动读取新的环境变量

**解决方案**：
- ✅ 修改 `.env` 文件（持久化配置）
- ✅ 重启应用以加载新配置

---

## 📖 配置要点总结

### PNVS vs 普通短信的区别

| 对比项 | 普通短信 | PNVS |
|--------|---------|------|
| **API 名称** | SendSms | SendSmsVerifyCode |
| **Endpoint** | dysmsapi.aliyuncs.com | dypnsapi.aliyuncs.com |
| **手机号参数** | PhoneNumbers | PhoneNumber |
| **签名来源** | 自己申请（需审核） | 系统赠送（免审核） |
| **模板来源** | 自己申请（需审核） | 系统赠送（免审核） |
| **模板参数** | 自定义变量 | 固定变量：code + min |
| **审核时间** | 1-2 天 | **无需审核** |

### 签名算法要点

**双重 URL 编码流程**：

1. **第一层编码**（规范化查询字符串）：
   ```
   SignName=云渚科技验证平台 → SignName=%E4%BA%91%E6%B8%9A...
   Timestamp=2026-06-24T02:26:50Z → Timestamp=2026-06-24T02%3A26%3A50Z
   ```

2. **第二层编码**（String to Sign，用于签名计算）：
   ```
   SignName=%E4%BA%91%E6%B8%9A... → SignName=%25E4%25BA%2591%25E6%25B8%259A...
   ```

3. **最终请求 URL**（单次编码）：
   ```
   SignName=%E4%BA%91%E6%B8%9A... （正确）
   ```

---

## 🚨 安全提醒

### ⚠️ AccessKey Secret 已泄露

**当前使用的 Secret**：`HYbj1056bzG6hqsIVYSRujcSf3N2GX`

**必须立即重新生成**：

1. 登录阿里云控制台：https://ram.console.aliyun.com/manage/ak
2. 删除旧的 AccessKey（LTAI5t5mKE1YFnmHoL4Da4D9）
3. 创建新的 AccessKey
4. 更新 `.env` 文件中的配置：
   ```bash
   HER_SMS_ALIYUN_ACCESS_KEY_ID=新的ID
   HER_SMS_ALIYUN_ACCESS_KEY_SECRET=新的Secret
   ```
5. 重启应用

---

## 📚 相关文档

- **PNVS 产品介绍**：https://www.aliyun.com/product/pnvs
- **PNVS 控制台**：https://dypns.console.aliyun.com/
- **参数配置页面**：https://dypns.console.aliyun.com/smsCertParamsConfig
- **API 文档**：https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-sendsmsverifycode

---

## 🎯 下一步操作

1. ✅ **立即重新生成 AccessKey Secret**（安全第一）
2. ✅ **更新 `.env` 文件配置**
3. ✅ **重启应用**
4. ✅ **验证功能是否正常**

---

## 💡 快速参考

### API 测试命令

```bash
# 发送验证码
curl -X POST http://127.0.0.1:8080/v1/auth/sms/send-code \
  -H "Content-Type: application/json" \
  -d '{"phone":"18846811193"}'

# 验证验证码（假设验证码是 275619）
curl -X POST http://127.0.0.1:8080/v1/auth/sms/verify-code \
  -H "Content-Type: application/json" \
  -d '{"phone":"18846811193","code":"275619","challenge_id":"otp-xxx"}'
```

### 应用重启命令

```bash
# 停止应用
pkill -f "python.*gateway"

# 启动应用
cd /Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway
docker compose up -d gateway-public
```

---

配置完成！系统已成功接入阿里云 PNVS 短信认证服务。🎉
