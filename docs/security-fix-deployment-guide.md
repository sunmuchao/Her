# API 安全修复完整方案 - 部署指南

## 一、修复概览

本次安全修复从底层架构角度重构了系统的安全机制，而非零散的单点修复。

### 核心架构改进

```
┌─────────────────────────────────────────────────────────────┐
│                   安全架构重构                                │
│                                                              │
│  1. 资源访问控制框架 (resource_access_guard.py)              │
│     - 统一的 IDOR 防护                                       │
│     - 资源所有权验证                                         │
│     - 审计所有访问决策                                       │
│                                                              │
│  2. 多维频率限制 (multi_rate_limiter.py)                     │
│     - IP 级别限流                                            │
│     - 手机号级别限流 (防 SMS 炸弹)                           │
│     - 验证失败累计限流                                       │
│     - 资源枚举检测                                           │
│     - 分布式攻击检测                                         │
│                                                              │
│  3. 输入验证框架 (input_validator.py)                        │
│     - 统一验证规则                                           │
│     - 注入检测                                               │
│     - 类型安全转换                                           │
│                                                              │
│  4. 文件上传安全 (media_routes.py 增强)                      │
│     - Magic Number 验证                                      │
│     - 文件名清洗                                             │
│     - EXIF 数据清理                                          │
│                                                              │
│  5. 运维接口安全 (support_routes.py 增强)                    │
│     - 操作范围验证                                           │
│     - 实时审计告警                                           │
│                                                              │
│  6. 安全响应头 (security_headers.py)                         │
│     - XSS 防护                                               │
│     - Clickjacking 防护                                      │
│     - HSTS                                                   │
│                                                              │
│  7. 日志脱敏 (log_masking.py)                                │
│     - 手机号掩码                                             │
│     - 身份证掩码                                             │
│     - 敏感字段检测                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、新增文件清单

| 文件路径 | 功能 | 依赖 |
|---------|------|------|
| `gateway/resource_access_guard.py` | 统一资源访问控制 | identity.py, observability |
| `gateway/multi_rate_limiter.py` | 多维频率限制 | observability |
| `gateway/input_validator.py` | 输入验证框架 | auth_common (可选) |
| `gateway/security_headers.py` | 安全响应头 | 无 |
| `gateway/log_masking.py` | 日志脱敏 | 无 |

---

## 三、修改文件清单

| 文件路径 | 修改内容 |
|---------|---------|
| `gateway/bff/candidate_detail.py` | 添加访问控制验证 |
| `gateway/collected_routes.py` | 严格绑定 profile_id |
| `gateway/verification_routes.py` | 添加提交所有权验证 |
| `gateway/media_routes.py` | Magic Number + 文件名清洗 + EXIF 清理 |
| `gateway/support_routes.py` | 运维操作范围验证 + 审计告警 |

---

## 四、部署步骤

### Step 1: 环境变量配置

```bash
# 频率限制配置
export PARTNER_GATEWAY_RATE_LIMIT_PER_MINUTE=600
export PARTNER_RATE_LIMIT_SMS_IP_PER_MINUTE=5
export PARTNER_RATE_LIMIT_SMS_PHONE_PER_MINUTE=1
export PARTNER_RATE_LIMIT_VERIFY_MAX_ATTEMPTS=5
export PARTNER_RATE_LIMIT_VERIFY_LOCKOUT_MINUTES=30
export PARTNER_RATE_LIMIT_404_THRESHOLD=20
export PARTNER_RATE_LIMIT_403_THRESHOLD=15
export PARTNER_RATE_LIMIT_ENUM_LOCKOUT_MINUTES=10

# 生产模式（禁用 Stub 和固定验证码）
export HER_PRODUCTION_MODE=1

# 安全头配置
export PARTNER_GATEWAY_TRUST_X_FORWARDED_FOR=1  # 如有负载均衡
```

### Step 2: 代码部署

```bash
# 1. 备份现有代码
git checkout -b security-fix-backup

# 2. 应用修复
git checkout main
git merge security-fix-branch

# 3. 安装依赖（如有新增）
pip install -r requirements.txt
```

### Step 3: 数据库更新（如需要）

```sql
-- 添加审计日志索引（如有大量审计记录）
CREATE INDEX idx_audit_event_action ON audit_events(action);
CREATE INDEX idx_audit_event_resource ON audit_events(resource_type, resource_id);
CREATE INDEX idx_audit_event_timestamp ON audit_events(timestamp);
```

### Step 4: 配置集成

在 `app.py` 中集成新模块：

```python
from .multi_rate_limiter import MultiRateLimiter, multi_rate_limiter_from_environ
from .security_headers import add_security_headers
from .log_masking import mask_for_log

class PartnerGateway:
    def __init__(self, ...):
        # 替换原有的 MinuteRateLimiter
        self._rate_limiter = multi_rate_limiter_from_environ()
        
    def __call__(self, environ, start_response):
        # 在返回响应时添加安全头
        def secured_start_response(status, headers, exc_info=None):
            secured_headers = add_security_headers(headers, environ)
            return start_response(status, secured_headers, exc_info)
        
        # 使用 secured_start_response 替代原始 start_response
```

---

## 五、测试清单

### 5.1 IDOR 测试

```bash
# 测试 candidate_detail IDOR
# 用户 A 尝试访问用户 B 的候选人资料（应返回 403）
curl -H "Authorization: Bearer $TOKEN_A" \
  "http://localhost/v1/candidates/$PROFILE_B_ID?session_id=$SESSION_A"

# 预期: 403 Forbidden
```

```bash
# 测试 profile/me IDOR
# 静态 token 用户尝试通过 query 参数访问他人资料
curl -H "X-API-Key: $STATIC_TOKEN" \
  "http://localhost/v1/profile/me?profile_id=$OTHER_PROFILE_ID"

# 预期: 403 Forbidden (非 staff 角色)
```

```bash
# 测试 verification submission IDOR
curl -H "Authorization: Bearer $TOKEN_A" \
  "http://localhost/v1/verifications/live-video-submissions/$SUBMISSION_B_ID"

# 预期: 403 Forbidden
```

### 5.2 频率限制测试

```bash
# SMS 手机号限流测试
for i in {1..10}; do
  curl -X POST -H "Content-Type: application/json" \
    -d '{"phone": "13812345678"}' \
    "http://localhost/v1/auth/sms/send-code"
done

# 预期: 第 2 次开始返回 429 Too Many Requests
```

```bash
# 资源枚举测试
for i in {1..30}; do
  curl -H "Authorization: Bearer $TOKEN" \
    "http://localhost/v1/candidates/$i"
done

# 预期: 大量 404 后触发临时封禁
```

### 5.3 文件上传测试

```bash
# Magic Number 验证测试
# 上传伪装成图片的 PDF
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@malicious.pdf;filename=test.jpg" \
  "http://localhost/v2/media/upload"

# 预期: 400 Invalid file type
```

```bash
# 文件名清洗测试
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -F "file=@test.jpg;filename=../../../etc/passwd" \
  "http://localhost/v2/media/upload"

# 预期: 文件名被清洗或拒绝
```

### 5.4 运维接口测试

```bash
# 操作范围测试
# Ops operator 尝试 override 非 recommendation 资源
curl -X POST -H "Authorization: Bearer $OPS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"target_owner": "profile", "target_id": "123", "action": "delete"}' \
  "http://localhost/v1/ops/overrides"

# 预期: 403 Scope forbidden
```

### 5.5 安全头测试

```bash
curl -I "http://localhost/v1/profile/me"

# 预期响应头:
# X-Content-Type-Options: nosniff
# X-Frame-Options: DENY
# X-XSS-Protection: 1; mode=block
# Content-Security-Policy: default-src 'self'
# Referrer-Policy: strict-origin-when-cross-origin
```

---

## 六、监控配置

### 6.1 新增监控指标

```yaml
# Prometheus 指标建议
metrics:
  - gateway.rate_limit.denied_total{type="ip|phone|enum"}
  - gateway.resource_access.denied_total{resource_type="profile|candidate|..."}
  - gateway.ops_override.total{outcome="success|denied|error"}
  - gateway.security_alert.total{type="idor_attempt|enum_attack|distributed"}
```

### 6.2 告警规则

```yaml
# 告警配置
alerts:
  - name: HighIDORAttemptRate
    condition: rate(gateway.resource_access.denied_total[5m]) > 10
    severity: high
    
  - name: SMSSBombingDetected
    condition: rate(gateway.rate_limit.denied_total{type="phone"}[1m]) > 5
    severity: critical
    
  - name: EnumerationAttack
    condition: rate(gateway.rate_limit.denied_total{type="enum"}[5m]) > 20
    severity: high
    
  - name: OpsOverrideAnomaly
    condition: rate(gateway.ops_override.total{outcome="error"}[10m]) > 3
    severity: medium
```

---

## 七、回滚方案

如果修复引入问题，可按以下步骤回滚：

```bash
# 1. 回滚代码
git checkout security-fix-backup
git checkout -b rollback-security
git push origin rollback-security

# 2. 恢复环境变量
unset HER_PRODUCTION_MODE
unset PARTNER_RATE_LIMIT_SMS_IP_PER_MINUTE

# 3. 重启服务
systemctl restart partner-gateway
```

---

## 八、后续建议

### 8.1 短期（1周内）

1. 完成所有安全测试验证
2. 配置监控告警
3. 通知安全团队进行渗透测试

### 8.2 中期（1个月内）

1. 集成病毒扫描服务（ClamAV 或商业方案）
2. 完善 EXIF 数据清理实现（使用 PIL）
3. 增加二次审批机制（关键运维操作）

### 8.3 长期（季度规划）

1. 实现分布式限流（Redis/Redis Cluster）
2. 增加机器学习异常检测
3. 定期安全审计自动化

---

## 九、风险评估

### 修复后残余风险

| 风险项 | 残余风险 | 原因 | 后续处理 |
|-------|---------|------|---------|
| 命令注入 | 低 | Shell SMS 已强制 shell=False + 黑名单 | 建议移除 Shell SMS |
| 分布式攻击 | 中 | 单机限流不防分布式 | 需 Redis 集中式限流 |
| Staff 越权 | 低 | 有审计但无二次审批 | 增加审批机制 |
| 未知类型资源 | 低 | 新资源类型需注册 resolver | 文档化注册流程 |

---

**文档版本**: v1.0  
**生成日期**: 2026-06-10  
**负责人**: Security Team