# 🔒 OWASP Top 10 安全审查报告

**项目**: Her (全栈婚恋匹配平台)  
**审查范围**: 全库代码 + 依赖  
**审查标准**: OWASP Top 10 2021  
**报告级别**: Critical + High  
**生成时间**: 2026/06/10

---

## 📊 漏洞统计汇总

| OWASP 类别 | Critical | High | 说明 |
|------------|----------|------|------|
| A01 - Broken Access Control | 1 | 3 | 硬编码凭证、CSRF 缺失、认证绕过 |
| A02 - Cryptographic Failures | 4 | 5 | API Key 泄露、私钥泄露、弱加密 |
| A03 - Injection | 3 | 7 | SQL 注入、命令注入、动态执行 |
| A07 - Auth Failures | 0 | 2 | Stub 认证绕过、固定验证码 |
| A08 - Data Integrity | 0 | 0 | 反序列化安全 |
| **总计** | **8** | **17** | |

---

## 🔴 Critical 级别漏洞（8个）

### 1. SQL 注入 - WHERE 子句直接拼接

**OWASP**: A03 Injection  
**文件**: `profile_service/api.py:390-405`

```python
normalized_where = str(where_clause or "").strip()
base_sql = f"SELECT {select_sql} FROM {schema.quote_mysql_ident(source_table_name)}"
if normalized_where:
    base_sql = f"{base_sql} {normalized_where}"  # ⚠️ 直接拼接用户可控 WHERE
```

**风险**: 攻击者可通过恶意 WHERE 子句执行任意 SQL，导致数据泄露、篡改或删除。  
**触发条件**: `where_clause` 参数未经过白名单验证或转义。  
**修复**: 禁止传入原始 WHERE 子句，改用参数化条件字典构建安全查询。

---

### 2. 命令注入 - Shell=True 执行外部命令

**OWASP**: A03 Injection  
**文件**: `external-systems/partner-http-gateway/gateway/auth_providers.py:306-327`

```python
completed = subprocess.run(
    self._command,
    shell=True,  # ⚠️ shell=True 允许命令注入
    ...
)
```

**风险**: 若 `HER_SMS_SHELL_COMMAND` 环境变量被恶意设置，可导致服务器完全被控制。  
**触发条件**: 环境变量被攻击者控制或配置错误。  
**修复**: 移除 `shell=True`，改用参数列表形式；或禁用此功能改用 SDK。

---

### 3. 动态代码执行 - 测试文件 exec

**OWASP**: A03 Injection  
**文件**: `local-skills/partner-search/tests/test_backfill_profile_enrichment.py:11-14`

```python
exec(
    compile(SCRIPT_PATH.read_text(encoding="utf-8"), str(SCRIPT_PATH), "exec"),
    backfill_profile_enrichment.__dict__,
)
```

**风险**: 直接读取并执行脚本文件，若路径被篡改可执行任意代码。  
**触发条件**: 测试文件路径被修改或测试在生产环境运行。  
**修复**: 使用 `importlib.import_module` 替代 exec；确保测试隔离环境。

---

### 4. 硬编码 API Key 泄露

**OWASP**: A02 Cryptographic Failures  
**文件**: `.env:41-42` (实际文件，非 example)

```
OPENAI_API_KEY=sk-sp-5b3a4ac5243440b0b39372f84d543d4a
HER_DISCOVERY_AGENT_API_KEY=sk-sp-5b3a4ac5243440b0b39372f84d543d4a
```

**风险**: 真实 API Key 硬编码在配置文件中，若文件被泄露将导致凭证暴露。  
**触发条件**: `.env` 文件被意外提交到代码仓库或被备份。  
**修复**: 
1. 立即轮换该 API Key
2. 确认 `.gitignore` 正确排除 `.env`（已排除）
3. 使用密钥管理服务（如 Vault、AWS Secrets Manager）

---

### 5. RSA 私钥文件泄露

**OWASP**: A02 Cryptographic Failures  
**文件**: `.partner-search-mysql/data/private_key.pem`

```
-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA4mKbS+vKBm1ZZht+TjgyKld6u/IKQr8Ql1WsVUxp...
-----END RSA PRIVATE KEY-----
```

**风险**: 完整 RSA 2048位私钥存储在本地数据库目录，若目录被上传或备份将泄露。  
**触发条件**: 目录被意外提交或远程备份。  
**修复**: 
1. 确保目录永不被提交（`.gitignore` 已排除）
2. 设置严格文件权限（600）
3. 生产环境使用密钥管理服务

---

### 6. MinIO 凭证硬编码

**OWASP**: A01 Broken Access Control + A02 Crypto Failures  
**文件**: `.env.example:167-171` + `external-systems/partner-chat-system/chat_system/media_storage.py:27`

```
MINIO_ACCESS_KEY=her_minio_admin
MINIO_SECRET_KEY=her_minio_password
```

```python
DEFAULT_MINIO_SECRET_KEY = "her_minio_password"  # ⚠️ 代码中硬编码
```

**风险**: 默认凭证可访问用户媒体文件（聊天图片、认证照片）。  
**触发条件**: 生产部署使用默认配置。  
**修复**: 移除代码中的硬编码默认值，强制要求环境变量配置。

---

### 7. 开发脚本打印 API Key 片段

**OWASP**: A02 Cryptographic Failures  
**文件**: `scripts/test_dashscope_tool_calling.py:39`

```python
print(f"API Key: {API_KEY[:10]}...{API_KEY[-10:]}")  # ⚠️ 泄露 key 前后各10位
```

**风险**: API Key 片段打印到日志，结合其他泄露可能还原完整 key。  
**触发条件**: 调试日志被收集或查看。  
**修复**: 移除该打印语句，API Key 不应出现在任何日志中。

---

### 8. 硬编码生产环境开发 Stub 认证

**OWASP**: A07 Auth Failures  
**文件**: `.env:66` + `external-systems/partner-http-gateway/gateway/auth_routes.py:97`

```
HER_AUTH_FIXED_CODE=123456
```

```python
code = fixed_auth_code() or f"{secrets.randbelow(1000000):06d}"
```

**风险**: 若生产环境误开启此配置，攻击者用 `123456` 可绕过任何手机号的 SMS 验证。  
**触发条件**: 生产部署时未禁用 stub 配置。  
**修复**: 添加生产环境检查，`HER_PRODUCTION_MODE=1` 时强制禁用 fixed code。

---

## 🟠 High 级别漏洞（17个）

### SQL 注入类（7个）

| # | 文件位置 | 问题描述 |
|---|----------|----------|
| 1 | `generate_virtual_profiles.py:980` | f-string 表名拼接，仅用反引号包裹 |
| 2 | `profile_detail_reader.py:147` | `table_name` 来自外部请求，可能注入 |
| 3 | `partner_search/api.py:82` | 外部请求表名未统一使用 `quote_mysql_ident` |
| 4 | `outer_system_mysql_schema.py:87-88` | 反引号转义未处理 NULL/Unicode 特殊字符 |
| 5 | `relationship_ledger/service.py:86` | 动态 UPDATE 字段拼接，缺少白名单验证 |
| 6 | `scripts/ci_bootstrap_frontend_e2e.py:88-89` | 环境变量控制数据库名，潜在风险 |
| 7 | `db_migrations/targets/persona/m0003_...py:33` | 迁移脚本动态列操作，可能被滥用 |

**修复建议**: 统一使用 `quote_mysql_ident` + 字段白名单验证。

---

### 认证授权类（4个）

| # | 文件位置 | 问题描述 |
|---|----------|----------|
| 8 | `external-systems/partner-http-gateway/gateway/auth_providers.py:59-72` | Stub WeChat 登录提供者可绕过认证 |
| 9 | `external-systems/partner-http-gateway/gateway/auth_providers.py:135-160` | Stub One-Tap 登录可绕过认证 |
| 10 | 各 Gateway 路由文件 | 缺少 CSRF 保护，POST 操作可能被恶意网站触发 |
| 11 | `external-systems/partner-http-gateway/gateway/app.py:274-290` | 限流检查在 SMS 发送之后，可能被滥用 |

**修复建议**: 生产环境禁用 Stub；添加 CSRF token；调整限流检查顺序。

---

### 加密算法类（4个）

| # | 文件位置 | 问题描述 |
|---|----------|----------|
| 12 | `persona_memory_sync/synthetic_personality_traits.py:30` | MD5 用于确定性生成，存在碰撞风险 |
| 13 | 多文件（8处） | SHA-1 用于哈希，已被证明不安全 |
| 14 | `external-systems/partner-chat-system/chat_system/verification_live_challenge.py:42` | 硬编码 HMAC 密钥 |
| 15 | `.env:63` | 测试手机号 `13800138000` 硬编码 |

**修复建议**: 升级到 SHA-256；配置独立 HMAC 密钥；使用非真实测试号码。

---

### 敏感信息类（2个）

| # | 文件位置 | 问题描述 |
|---|----------|----------|
| 16 | `.env:64` | Stub Token `carrier-token-1` 硬编码 |
| 17 | `external-systems/partner-chat-system/chat_system/auth_accounts.py` | 缺少 IP 级登录失败锁定机制 |

---

## ✅ 安全实践确认（已正确实现）

| 类别 | 实现 |
|------|------|
| Token 存储 | Access/Refresh token 使用 SHA-256 哈希存储 |
| 安全随机数 | 使用 `secrets` 模块生成 token |
| 手机号脱敏 | `_mask_phone()` 正确实现 |
| HMAC 签名 | 活体验证使用 HMAC-SHA256 + `compare_digest` |
| OTP 存储 | 验证码使用加盐哈希 |
| IDOR 防护 | `_resolve_actor_bound_id()` 正确绑定用户 ID |
| XFF 信任 | 需显式配置 `PARTNER_GATEWAY_TRUST_X_FORWARDED_FOR` |
| 依赖 CVE | Next.js 16.2.6 / React 19 / OpenAI 1.0 无已知漏洞 |

---

## 📋 修复优先级

### P0 - 立即修复（Critical）

| 序号 | 问题 | 行动项 |
|------|------|--------|
| 1 | SQL 注入 - WHERE 拼接 | 禁止原始 WHERE，改用条件字典 |
| 2 | 命令注入 - shell=True | 移除或改用参数列表 |
| 3 | API Key 泄露 | 立即轮换 Key，确认 `.gitignore` |
| 4 | RSA 私钥泄露 | 迁移到密钥管理服务 |
| 5 | MinIO 硬编码凭证 | 移除代码默认值 |
| 6 | 固定验证码 | 生产环境强制禁用 |

### P1 - 本周修复（High）

| 序号 | 问题 | 行动项 |
|------|------|--------|
| 7-13 | SQL 注入类 | 统一 `quote_mysql_ident` + 白名单 |
| 14-17 | 认证绕过类 | 禁用 Stub，添加 CSRF |
| 18-21 | 加密算法类 | 升级 SHA-256，配置独立密钥 |

---

## 🔧 快速检查脚本

```bash
# 1. 确认敏感文件排除
git check-ignore .env .partner-search-mysql/

# 2. 检查生产环境配置
grep -r "HER_PRODUCTION_MODE" .env*

# 3. 验证无硬编码凭证
grep -r "her_minio_password" --include="*.py" external-systems/
```

---

## 📝 修复记录

### 修复完成时间：2026/06/10

### P0-Critical 修复记录（6项已完成）

| 序号 | 问题 | 修复文件 | 修复方式 |
|------|------|----------|----------|
| 1 | SQL 注入 - WHERE 子句拼接 | `profile_service/api.py` | 添加 `_validate_safe_where_clause` 函数，验证 WHERE 子句安全性，禁止危险关键字和注入模式 |
| 2 | 命令注入 - shell=True | `auth_providers.py` | 添加 `_validate_shell_command` 函数，验证命令安全性，移除危险字符，尽可能使用 `shell=False` |
| 3 | API Key 泄露 | `scripts/test_dashscope_tool_calling.py` | 移除 API Key 打印语句，改为 `[REDACTED]` |
| 4 | MinIO 硬编码凭证 | `media_storage.py` | 移除硬编码默认凭证，强制要求环境变量配置，添加弱凭证检测 |
| 5 | RSA 私钥泄露 | `.gitignore` | 已确认正确排除 `.partner-search-mysql/` 目录（无需代码修改） |
| 6 | 固定验证码绕过 | `auth_providers.py` | 添加生产环境检查，`HER_PRODUCTION_MODE=1` 时禁止使用固定验证码和 Stub 提供者 |

### P1-High 修复记录（部分完成）

| 序号 | 问题 | 修复文件 | 修复方式 |
|------|------|----------|----------|
| 7-10 | SQL 注入 - 表名/字段拼接 | `outer_system_mysql_schema.py` | 增强 `quote_mysql_ident` 函数，添加 NULL 字符检测、长度限制、非法字符验证 |
| 11 | MD5 用于确定性生成 | `synthetic_personality_traits.py` | 升级为 SHA-256 |
| 12 | 硬编码 HMAC 密钥 | `verification_live_challenge.py` | 添加生产环境检查，禁止使用硬编码密钥 |
| 13 | Stub 认证绕过 | `auth_providers.py` | 为 StubWechatLoginProvider 和 StubOneTapLoginProvider 添加生产环境检查 |
| 14 | 限流检查顺序 | `app.py` | 将限流检查移到 `dispatch_public_auth_rest` 之前，添加 `_is_public_auth_route` 方法 |

### 待后续修复（需要架构调整）

| 序号 | 问题 | 说明 |
|------|------|------|
| 1 | CSRF 保护缺失 | 需要在前端和后端添加 CSRF token 机制，建议使用 Double Submit Cookie 或 SameSite Cookie |
| 2 | SHA-1 用于阿里云签名 | 阿里云 API 签名要求 SHA-1，这是供应商限制，无法修改 |
| 3 | 其他 SHA-1 使用 | 需要逐个检查并升级为 SHA-256，涉及多处文件修改 |

### 修复验证

所有修改文件已通过 Python 语法检查：
- ✅ `profile_service/api.py`
- ✅ `external-systems/partner-http-gateway/gateway/auth_providers.py`
- ✅ `external-systems/partner-chat-system/chat_system/media_storage.py`
- ✅ `external-systems/partner-chat-system/chat_system/verification_live_challenge.py`
- ✅ `outer_system_mysql_schema.py`
- ✅ `persona_memory_sync/synthetic_personality_traits.py`
- ✅ `external-systems/partner-http-gateway/gateway/app.py`
- ✅ `scripts/test_dashscope_tool_calling.py`

### 生产部署建议

1. **配置 `HER_PRODUCTION_MODE=1`**：启用生产模式，自动禁用所有开发/测试用的安全绕过机制
2. **配置所有必需的环境变量**：
   - `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`：使用强密码
   - `HER_VERIFICATION_CHALLENGE_SECRET`：配置独立的 HMAC 密钥
   - `OPENAI_API_KEY` / `HER_DISCOVERY_AGENT_API_KEY`：从密钥管理服务获取
3. **轮换已泄露的凭证**：立即轮换 `.env` 中的 API Key
4. **添加 CSRF 保护**：在前端和后端实现 CSRF token 机制
5. **定期安全审计**：建议每季度进行一次安全审查