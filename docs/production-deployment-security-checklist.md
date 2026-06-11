# 生产环境部署安全检查清单

**用途**: 生产环境部署前的安全配置验证  
**使用时机**: 每次生产部署前必须逐项检查  
**负责人**: 运维团队 + 安全团队

---

## ✅ 必需配置（部署前验证）

### 1. 生产模式启用
- [ ] `HER_PRODUCTION_MODE=1` 已设置
- [ ] 确认应用启动时调用 `assert_production_all()` 检查

### 2. 凭证配置（强密码）

#### MinIO 媒体存储
- [ ] `MINIO_ACCESS_KEY` >= 20 chars，使用强密码
- [ ] `MINIO_SECRET_KEY` >= 40 chars，使用强密码
- [ ] `MINIO_SECURE=true`（生产环境必须 HTTPS）
- [ ] 凭证不包含占位符（如 "replace-with", "test"）

#### API 密钥
- [ ] `OPENAI_API_KEY` >= 32 chars，有效且无占位符
- [ ] `HER_DISCOVERY_AGENT_API_KEY` >= 32 chars，有效且无占位符
- [ ] `HER_VERIFICATION_CHALLENGE_SECRET` >= 20 chars，独立 HMAC 密钥

### 3. 数据库安全

#### 连接字符串
- [ ] 所有数据库使用生产服务器地址（禁止 localhost/127.0.0.1）
- [ ] 所有数据库使用强密码（>= 12 chars）
- [ ] 数据库用户权限最小化（非 root 用户）

#### 检查的环境变量
- [ ] `PARTNER_RECOMMENDATION_DB`
- [ ] `PARTNER_MATCHMAKING_DB`
- [ ] `PARTNER_CHAT_DB`
- [ ] `PARTNER_DISCOVERY_DB`
- [ ] `HER_RELATION_LEDGER_DB`

### 4. 认证配置（禁止 Stub）

#### SMS 认证
- [ ] `HER_SMS_PROVIDER=aliyun`（禁止 stub/mac_messages/shell）
- [ ] `HER_SMS_ALIYUN_ACCESS_KEY_ID` 已配置
- [ ] `HER_SMS_ALIYUN_ACCESS_KEY_SECRET` 已配置
- [ ] `HER_SMS_ALIYUN_SIGN_NAME` 已配置
- [ ] `HER_SMS_ALIYUN_TEMPLATE_CODE` 已配置

#### 微信登录
- [ ] `HER_AUTH_WECHAT_PROVIDER=open_platform`（禁止 stub）
- [ ] `HER_WECHAT_APP_ID` 已配置
- [ ] `HER_WECHAT_APP_SECRET` 已配置

#### 一键登录
- [ ] `HER_AUTH_ONE_TAP_PROVIDER` 已配置（禁止 stub）
- [ ] 相关运营商配置已完成

#### 固定验证码
- [ ] `HER_AUTH_FIXED_CODE` **未设置**（或已移除）

### 5. HTTPS/TLS 配置

- [ ] `MINIO_SECURE=true`（MinIO 使用 HTTPS）
- [ ] 所有外部 API 使用 HTTPS（如 OpenAI、阿里云）
- [ ] 数据库连接使用 SSL（如 MySQL SSL）

### 6. 限流配置

- [ ] `PARTNER_GATEWAY_RATE_LIMIT_PER_MINUTE` 已设置合理值（如 600）
- [ ] Gateway 限流检查已启用

### 7. 审计与监控

- [ ] 所有安全关键操作有审计日志
- [ ] 审计日志存储配置完成
- [ ] 异常告警机制已配置

---

## ❌ 禁止配置（部署前验证）

### 禁止硬编码凭证
- [ ] `.env` 文件中无硬编码密码/API Key
- [ ] 所有凭证来自密钥管理服务或安全环境变量

### 禁止开发/测试配置
- [ ] 无 Stub 认证提供者（WeChat、One-Tap）
- [ ] 无固定验证码（`HER_AUTH_FIXED_CODE`）
- [ ] 无弱凭证黑名单匹配（如 `minioadmin/minioadmin`）

### 禁止不安全地址
- [ ] 无 localhost 数据库地址（如 `mysql://root@127.0.0.1`）
- [ ] 无无密码数据库连接（如 `mysql://root@db-server`）

### 禁止占位符
- [ ] 无 "replace-with" 占位符
- [ ] 无 "test"、"demo"、"example" 测试值

---

## 📋 验证脚本

### 快速检查脚本

```bash
# 1. 确认敏感文件排除
git check-ignore .env .partner-search-mysql/ && echo "✅ .env 已排除"

# 2. 检查生产环境配置
grep -r "HER_PRODUCTION_MODE=1" .env* && echo "✅ 生产模式已启用"

# 3. 验证无硬编码弱凭证
grep -r "her_minio_password" --include="*.py" . && echo "❌ 发现硬编码弱凭证！"
grep -r "minioadmin" --include="*.py" . && echo "❌ 发现硬编码弱凭证！"

# 4. 验证数据库地址
grep -r "127.0.0.1" .env* | grep -i "db" && echo "❌ 发现 localhost 数据库地址！"
grep -r "localhost" .env* | grep -i "db" && echo "❌ 发现 localhost 数据库地址！"

# 5. 验证 API 密钥长度
python -c "import os; key=os.environ.get('OPENAI_API_KEY',''); print(f'OpenAI Key length: {len(key)}')"
```

### Python 安全检查脚本

```python
#!/usr/bin/env python3
"""生产环境安全配置验证脚本"""

import os
import sys

def check_production_config():
    """验证生产环境配置"""
    errors = []
    
    # 1. 检查生产模式
    if os.environ.get("HER_PRODUCTION_MODE") != "1":
        errors.append("❌ HER_PRODUCTION_MODE 未设置为 1")
    
    # 2. 检查 MinIO 凭证长度
    access_key = os.environ.get("MINIO_ACCESS_KEY", "")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "")
    
    if len(access_key) < 20:
        errors.append(f"❌ MINIO_ACCESS_KEY 长度过短: {len(access_key)} chars (需要 >= 20)")
    if len(secret_key) < 40:
        errors.append(f"❌ MINIO_SECRET_KEY 长度过短: {len(secret_key)} chars (需要 >= 40)")
    
    # 3. 检查 API 密钥
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    discovery_key = os.environ.get("HER_DISCOVERY_AGENT_API_KEY", "")
    
    if len(openai_key) < 32:
        errors.append(f"❌ OPENAI_API_KEY 长度过短: {len(openai_key)} chars (需要 >= 32)")
    if len(discovery_key) < 32:
        errors.append(f"❌ HER_DISCOVERY_AGENT_API_KEY 长度过短: {len(discovery_key)} chars (需要 >= 32)")
    
    # 4. 检查占位符
    placeholders = ["replace-with", "test", "demo", "example"]
    for key_name in ["OPENAI_API_KEY", "HER_DISCOVERY_AGENT_API_KEY", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"]:
        value = os.environ.get(key_name, "")
        for placeholder in placeholders:
            if placeholder in value.lower():
                errors.append(f"❌ {key_name} 包含占位符 '{placeholder}'")
    
    # 5. 检查数据库地址
    db_envs = ["PARTNER_RECOMMENDATION_DB", "PARTNER_MATCHMAKING_DB", "PARTNER_CHAT_DB", "PARTNER_DISCOVERY_DB"]
    for env_name in db_envs:
        dsn = os.environ.get(env_name, "")
        if "127.0.0.1" in dsn or "localhost" in dsn:
            errors.append(f"❌ {env_name} 使用 localhost 地址")
    
    # 输出结果
    if errors:
        print("\n".join(errors))
        return False
    
    print("✅ 所有生产环境配置检查通过")
    return True

if __name__ == "__main__":
    if not check_production_config():
        sys.exit(1)
```

---

## 📝 使用说明

### 部署前流程

1. **运维团队**：
   - 从密钥管理服务获取所有凭证
   - 配置 `.env` 文件（使用强密码）
   - 运行验证脚本检查配置

2. **安全团队**：
   - 逐项检查上述清单
   - 验证无禁止配置
   - 签署安全检查确认

3. **开发团队**：
   - 确认 `assert_production_all()` 在应用启动时调用
   - 确认审计日志配置完成
   - 确认异常告警机制已配置

### 部署后验证

1. 应用启动成功（无 RuntimeError）
2. 审计日志正常记录
3. 安全告警机制正常工作

---

## 🔗 相关文档

- [安全审查补充报告](security-review-supplement-report.md)
- [安全审查完整报告](security-review-report.md)
- [her_production.py 安全检查函数](../her_production.py)

---

**最后更新**: 2026-06-10  
**负责人**: 安全团队
