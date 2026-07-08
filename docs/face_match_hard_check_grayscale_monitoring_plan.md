# 活体视频认证前置人脸比对硬性检查 - 灰度发布和监控方案

## 完成时间：2026-07-07

---

## 一、监控指标设计

### 1.1 核心监控指标

| 指标名称 | 指标类型 | 监控维度 | 告警阈值 | 说明 |
|---------|---------|---------|---------|------|
| `video_face_anchor_save_rate` | 成功率 | profile_id, verification_status | < 95% 触发告警 | 视频人脸向量保存成功率 |
| `verification_rejection_rate` | 比率 | profile_id, rejection_reason | > 15% 触发告警 | 认证拒绝率（阈值提高后） |
| `photo_update_success_rate` | 成功率 | profile_id, face_match_status | < 90% 触发告警 | 照片更新成功率 |
| `face_similarity_score_avg` | 平均值 | profile_id, verification_status | < 0.5 关注 | 人脸相似度平均分数 |
| `auto_verification_approve_count` | 计数 | profile_id, verification_status | 无阈值，仅统计 | 自动认证通过次数 |
| `photo_face_mismatch_count` | 计数 | profile_id, error_reason | 无阈值，仅统计 | 照片人脸不匹配次数 |

### 1.2 监控数据来源

**数据表：**
- `verification_records` - 认证记录
- `profile_face_embeddings` - 人脸向量表
- `profile_photos` - 照片表
- `profiles` - 用户档案表

**日志埋点：**
- `verification.py:2559-2630` - 审核通过后保存视频人脸向量（INFO级别）
- `verification.py:1353-1364` - 审核决策逻辑（INFO级别）
- `profile_service/api.py:1585-1830` - 照片更新双重检查（INFO级别）
- `gateway/collected_routes.py:395-491` - 照片更新API路由（INFO级别）

### 1.3 监控仪表板设计

**仪表板名称：** `Face Match Hard Check Dashboard`

**展示内容：**
1. **概览卡片**：
   - 视频人脸向量保存成功率（最近1小时/24小时/7天）
   - 认证拒绝率（最近1小时/24小时/7天）
   - 照片更新成功率（最近1小时/24小时/7天）
   - 自动认证通过次数（最近1小时/24小时/7天）

2. **趋势图表**：
   - 人脸相似度分数分布（直方图）
   - 认证拒绝率趋势（时间序列图）
   - 照片更新成功率趋势（时间序列图）

3. **实时监控**：
   - 最近10条照片更新记录（实时列表）
   - 最近10条认证拒绝记录（实时列表）
   - 最近10条自动认证通过记录（实时列表）

---

## 二、灰度发布流程

### 2.1 灰度发布阶段

| 阶段 | 时间 | 用户比例 | 目标 | 观察指标 |
|------|------|---------|------|---------|
| **阶段1：内部测试** | 1天 | 0%（内部用户） | 验证功能可用性 | 所有测试通过 |
| **阶段2：小范围灰度** | 2天 | 10% | 验证真实用户反应 | 指标无明显异常 |
| **阶段3：中等范围灰度** | 3天 | 30% | 扩大观察范围 | 指标稳定 |
| **阶段4：大范围灰度** | 5天 | 50% | 验证稳定性 | 指标稳定 |
| **阶段5：全量发布** | 无限期 | 100% | 正常运行 | 持续监控 |

### 2.2 灰度发布控制方案

**控制方式：** 通过配置文件控制阈值和灰度比例

**配置文件：** `config/face_match_hard_check.yaml`

```yaml
# 人脸比对硬性检查配置
face_match_hard_check:
  # 是否启用硬性检查
  enabled: true

  # 灰度发布比例（0-100）
  grayscale_percentage: 10

  # 硬性阈值（相似度分数）
  hard_threshold: 0.363

  # 审核阈值（从40提高到70）
  verification_threshold: 70

  # 灰度用户筛选策略
  grayscale_strategy: "user_id_mod"  # 按用户ID取模

  # 灰度用户白名单（优先级高于灰度比例）
  whitelist: [
    "internal_test_user_001",
    "internal_test_user_002",
  ]
```

**灰度策略实现：**

```python
def is_grayscale_user(profile_id: int, config: dict) -> bool:
    """
    判断用户是否在灰度范围内

    Args:
        profile_id: 用户ID
        config: 配置字典

    Returns:
        bool: True表示在灰度范围内，False表示不在
    """
    # 1. 检查白名单
    whitelist = config.get("whitelist", [])
    if str(profile_id) in whitelist:
        return True

    # 2. 检查灰度比例
    grayscale_percentage = config.get("grayscale_percentage", 0)
    if grayscale_percentage == 0:
        return False

    # 3. 按用户ID取模判断
    grayscale_strategy = config.get("grayscale_strategy", "user_id_mod")
    if grayscale_strategy == "user_id_mod":
        return (profile_id % 100) < grayscale_percentage

    return False
```

### 2.3 灰度发布实施步骤

**步骤1：准备配置文件**
```bash
# 创建配置文件
mkdir -p config
touch config/face_match_hard_check.yaml

# 初始化配置（灰度比例设置为10%）
cat > config/face_match_hard_check.yaml <<EOF
face_match_hard_check:
  enabled: true
  grayscale_percentage: 10
  hard_threshold: 0.363
  verification_threshold: 70
  grayscale_strategy: "user_id_mod"
  whitelist: []
EOF
```

**步骤2：部署配置中心**
```bash
# 配置中心需要支持动态更新配置
# 使用Redis或数据库存储配置

# Redis示例
redis-cli SET "face_match_hard_check:grayscale_percentage" "10"
redis-cli SET "face_match_hard_check:verification_threshold" "70"
```

**步骤3：启动灰度发布**
```bash
# 部署代码
git pull origin feature/persona-memory-session-end-improvements-clean
git checkout feature/persona-memory-session-end-improvements-clean

# 启动服务
make restart

# 检查服务状态
curl http://localhost:8080/health
```

**步骤4：监控观察**
```bash
# 查看监控仪表板
open http://grafana.example.com/d/face-match-hard-check

# 查看日志
tail -f /var/log/her/verification.log | grep "face_match"

# 查看关键指标
curl http://localhost:8080/api/metrics | grep "face_match"
```

---

## 三、回滚方案

### 3.1 回滚触发条件

| 触发条件 | 回滚级别 | 回滚方式 | 说明 |
|---------|---------|---------|------|
| 视频人脸向量保存成功率 < 95% | 部分回滚 | 降低阈值或灰度比例 | 可能是人脸识别服务问题 |
| 认证拒绝率 > 20% | 全量回滚 | 关闭硬性检查 | 阈值过高导致大量用户无法认证 |
| 照片更新成功率 < 80% | 部分回滚 | 降低阈值或灰度比例 | 可能是人脸识别服务问题 |
| 用户投诉超过阈值 | 全量回滚 | 关闭硬性检查 | 用户反馈体验不佳 |
| 系统异常错误率 > 5% | 全量回滚 | 关闭硬性检查 | 系统稳定性问题 |

### 3.2 回滚操作步骤

**快速回滚（关闭硬性检查）：**

```bash
# 方式1：修改配置文件
cat > config/face_match_hard_check.yaml <<EOF
face_match_hard_check:
  enabled: false
  grayscale_percentage: 0
  hard_threshold: 0.363
  verification_threshold: 40  # 回滚到原阈值
EOF

# 方式2：使用Redis动态更新
redis-cli SET "face_match_hard_check:enabled" "false"
redis-cli SET "face_match_hard_check:grayscale_percentage" "0"
redis-cli SET "face_match_hard_check:verification_threshold" "40"

# 重启服务（如果配置不支持动态更新）
make restart

# 检查服务状态
curl http://localhost:8080/health

# 验证回滚成功
curl http://localhost:8080/api/config | grep "face_match_hard_check"
```

**部分回滚（降低阈值）：**

```bash
# 降低审核阈值
redis-cli SET "face_match_hard_check:verification_threshold" "50"

# 降低灰度比例
redis-cli SET "face_match_hard_check:grayscale_percentage" "5"

# 检查服务状态
curl http://localhost:8080/health
```

### 3.3 回滚验证清单

- [ ] 配置已更新（enabled=false 或 grayscale_percentage=0）
- [ ] 服务已重启（如果需要）
- [ ] 监控指标恢复正常
- [ ] 用户认证成功率恢复正常
- [ ] 照片更新成功率恢复正常
- [ ] 用户投诉减少
- [ ] 系统错误率降低

---

## 四、AB测试方案（可选）

### 4.1 AB测试设计

**测试目标：** 验证硬性检查对用户行为的影响

**测试分组：**
- **A组（对照组）：** 使用原阈值（40分），不检查照片人脸
- **B组（实验组）：** 使用新阈值（70分），检查照片人脸

**测试指标：**
- 认证成功率
- 认证拒绝率
- 照片更新成功率
- 用户投诉率
- 用户留存率
- 用户满意度

### 4.2 AB测试实施

**配置AB测试：**

```yaml
ab_test:
  enabled: true
  test_name: "face_match_hard_check"
  groups:
    A:
      percentage: 50
      config:
        verification_threshold: 40
        face_check_enabled: false
    B:
      percentage: 50
      config:
        verification_threshold: 70
        face_check_enabled: true
```

**AB测试用户分配：**

```python
def assign_ab_group(profile_id: int) -> str:
    """
    分配AB测试分组

    Args:
        profile_id: 用户ID

    Returns:
        str: "A" 或 "B"
    """
    return "A" if (profile_id % 100) < 50 else "B"
```

### 4.3 AB测试结果分析

**分析周期：** 14天

**分析维度：**
- 认证成功率对比（A组 vs B组）
- 认证拒绝率对比（A组 vs B组）
- 用户投诉率对比（A组 vs B组）
- 用户留存率对比（A组 vs B组）
- 用户满意度对比（A组 vs B组）

**决策依据：**
- 如果B组用户投诉率显著高于A组（>20%），考虑回滚
- 如果B组用户留存率显著低于A组（>10%），考虑回滚
- 如果B组认证拒绝率过高（>20%），考虑调整阈值

---

## 五、监控告警配置

### 5.1 Prometheus监控配置

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'her-face-match'
    static_configs:
      - targets: ['localhost:8080']
    metrics_path: '/api/metrics'

rule_files:
  - 'face_match_alerts.yml'
```

### 5.2 告警规则配置

```yaml
# face_match_alerts.yml
groups:
  - name: face_match_alerts
    rules:
      - alert: VideoFaceAnchorSaveRateLow
        expr: video_face_anchor_save_rate < 0.95
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "视频人脸向量保存成功率过低"
          description: "成功率 {{ $value }}，低于95%阈值"

      - alert: VerificationRejectionRateHigh
        expr: verification_rejection_rate > 0.15
        for: 10m
        labels:
          severity: critical
        annotations:
          summary: "认证拒绝率过高"
          description: "拒绝率 {{ $value }}，超过15%阈值"

      - alert: PhotoUpdateSuccessRateLow
        expr: photo_update_success_rate < 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "照片更新成功率过低"
          description: "成功率 {{ $value }}，低于90%阈值"
```

### 5.3 Grafana仪表板配置

**仪表板JSON：** 见附录 `grafana_dashboard.json`

---

## 六、运维手册

### 6.1 日常运维检查清单

- [ ] 检查监控仪表板（每日）
- [ ] 检查告警日志（每日）
- [ ] 检查用户投诉（每日）
- [ ] 检查系统日志（每日）
- [ ] 检查配置文件（每周）
- [ ] 检查数据库表（每周）
- [ ] 检查人脸识别服务（每周）

### 6.2 故障排查手册

**故障1：视频人脸向量保存失败**

**排查步骤：**
1. 检查人脸识别服务状态
2. 检查数据库连接状态
3. 检查日志错误信息
4. 检查配置文件

**故障2：认证拒绝率过高**

**排查步骤：**
1. 检查阈值配置
2. 检查人脸识别服务准确率
3. 检查用户照片质量
4. 检查日志中的相似度分数

**故障3：照片更新失败**

**排查步骤：**
1. 检查人脸识别服务状态
2. 检查视频人脸向量是否存在
3. 检查照片质量
4. 检查日志错误信息

---

## 七、附录

### 7.1 Grafana仪表板JSON

```json
{
  "dashboard": {
    "title": "Face Match Hard Check Dashboard",
    "panels": [
      {
        "title": "视频人脸向量保存成功率",
        "type": "stat",
        "targets": [
          {
            "expr": "video_face_anchor_save_rate",
            "legendFormat": "成功率"
          }
        ],
        "thresholds": [
          {
            "value": 0.95,
            "color": "green"
          },
          {
            "value": 0.9,
            "color": "yellow"
          },
          {
            "value": 0,
            "color": "red"
          }
        ]
      },
      {
        "title": "认证拒绝率",
        "type": "stat",
        "targets": [
          {
            "expr": "verification_rejection_rate",
            "legendFormat": "拒绝率"
          }
        ],
        "thresholds": [
          {
            "value": 0,
            "color": "green"
          },
          {
            "value": 0.15,
            "color": "yellow"
          },
          {
            "value": 0.2,
            "color": "red"
          }
        ]
      }
    ]
  }
}
```

---

**文档完成时间：** 2026-07-07
**文档作者：** Claude Code
**文档状态：** 已完成