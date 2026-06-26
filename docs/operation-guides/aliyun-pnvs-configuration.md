# 阿里云 PNVS（短信认证服务）配置指南

## 重要发现

通过官方文档，我发现：

### PNVS 不是完全免签名模板！

虽然 PNVS 号称"免资质、签名、模板申请"，但实际上：

1. **使用专用的 API**：`SendSmsVerifyCode`（不是普通短信的 SendSms）
2. **需要签名和模板参数**：但使用阿里云**系统赠送**的签名和模板
3. **系统赠送资源**：阿里云提供了默认的签名和模板供你使用

---

## 配置步骤

### 步骤 1：获取系统赠送的签名和模板

访问阿里云控制台：https://dypns.console.aliyun.com/smsCertParamsConfig

在控制台中，你可以看到系统赠送的：
- **签名名称**（如"阿里云"、"短信验证"等）
- **模板 CODE**（如 SMS_XXXXXX）

### 步骤 2：配置环境变量

现在需要配置 4 个环境变量（AccessKey + 系统赠送的签名和模板）：

```bash
# AccessKey
export HER_SMS_ALIYUN_ACCESS_KEY_ID=LTAI5t5mKE1YFnmHoL4Da4D9
export HER_SMS_ALIYUN_ACCESS_KEY_SECRET=你的新密码

# PNVS 系统赠送的签名和模板（从控制台获取）
export HER_SMS_ALIYUN_PNVS_SIGN_NAME=系统赠送的签名名称
export HER_SMS_ALIYUN_PNVS_TEMPLATE_CODE=系统赠送的模板CODE

# 可选：强制使用 PNVS
export HER_SMS_PROVIDER=aliyun_pnvs
```

### 步骤 3：验证配置

```bash
python tests/integration/test_aliyun_sms_config.py
```

应该看到：
```
✅ PNVS 短信认证服务配置完整
   使用系统赠送的签名和模板
```

### 步骤 4：发送测试短信

```bash
python tests/integration/test_aliyun_sms_config.py --send-test 18846811193
```

---

## PNVS vs 普通短信对比

| 对比项 | 普通短信服务 | PNVS 短信认证服务 |
|--------|------------|------------------|
| **API 名称** | `SendSms` | `SendSmsVerifyCode` |
| **API Endpoint** | dysmsapi.aliyuncs.com | dypnsapi.aliyuncs.com |
| **手机号参数** | `PhoneNumbers` | `PhoneNumber` |
| **签名来源** | 自己申请（需审核） | 系统赠送（免审核） |
| **模板来源** | 自己申请（需审核） | 系统赠送（免审核） |
| **审核时间** | 1-2 天 | **无需审核** |
| **适用场景** | 营销、通知短信 | 验证码短信 |

---

## 系统赠送的签名和模板

根据官方文档：

1. **系统赠送签名必须搭配系统赠送模板使用**
2. **模板包含两个变量**："验证码"和"有效期"
3. **可以从控制台查看**：https://dypns.console.aliyun.com/smsCertParamsConfig

---

## 快速体验

阿里云提供了一个快速测试功能：

1. 访问：https://dypns.console.aliyun.com/smsServiceOverview
2. 在"快速测试"页面绑定测试手机号（每个账号可绑定 5 个）
3. 点击"调用 API 测试短信认证服务"发送测试短信

---

## 环境变量说明

### 必需环境变量

| 环境变量名 | 说明 | 获取方式 |
|-----------|------|---------|
| `HER_SMS_ALIYUN_ACCESS_KEY_ID` | AccessKey ID | https://ram.console.aliyun.com/manage/ak |
| `HER_SMS_ALIYUN_ACCESS_KEY_SECRET` | AccessKey Secret | https://ram.console.aliyun.com/manage/ak |
| `HER_SMS_ALIYUN_PNVS_SIGN_NAME` | 系统赠送的签名名称 | https://dypns.console.aliyun.com/smsCertParamsConfig |
| `HER_SMS_ALIYUN_PNVS_TEMPLATE_CODE` | 系统赠送的模板 CODE | https://dypns.console.aliyun.com/smsCertParamsConfig |

### 可选环境变量

| 环境变量名 | 默认值 | 说明 |
|-----------|--------|------|
| `HER_SMS_PROVIDER` | 自动检测 | 设置为 `aliyun_pnvs` 强制使用 PNVS |
| `HER_SMS_ALIYUN_REGION_ID` | `cn-hangzhou` | 区域 ID |
| `HER_SMS_ALIYUN_ENDPOINT` | `https://dypnsapi.aliyuncs.com/` | API 端点 |

---

## 代码修改说明

我已经修改了代码以支持 PNVS：

1. **使用正确的 API**：`SendSmsVerifyCode`（不是 SendSms）
2. **使用正确的 Endpoint**：`dypnsapi.aliyuncs.com`（不是 dysmsapi）
3. **使用正确的参数名**：`PhoneNumber`（不是 PhoneNumbers）
4. **支持系统赠送的签名和模板**：通过环境变量配置

---

## 相关链接

- PNVS 产品介绍：https://www.aliyun.com/product/pnvs
- PNVS 控制台：https://dypns.console.aliyun.com/
- 参数配置页面：https://dypns.console.aliyun.com/smsCertParamsConfig
- API 文档：https://help.aliyun.com/zh/pnvs/developer-reference/api-dypnsapi-2017-05-25-sendsmsverifycode

---

## 下一步

请按照以下步骤操作：

1. 访问 https://dypns.console.aliyun.com/smsCertParamsConfig
2. 查看系统赠送的签名名称和模板 CODE
3. 设置环境变量：
   ```bash
   export HER_SMS_ALIYUN_PNVS_SIGN_NAME=你的系统赠送签名
   export HER_SMS_ALIYUN_PNVS_TEMPLATE_CODE=你的系统赠送模板CODE
   ```
4. 运行测试：
   ```bash
   python tests/integration/test_aliyun_sms_config.py --send-test 18846811193
   ```

完成！