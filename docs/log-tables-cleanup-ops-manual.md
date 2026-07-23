# 日志表清理与监控运维手册

## 背景

2026-07-23 发生 "The table 'auth_login_events' is full" 错误，根本原因是：
1. MySQL容器磁盘空间100%满（Docker镜像缓存占用过多）
2. 缺少日志表数据生命周期管理机制
3. 缺少容量监控告警体系

## 解决方案

已实施以下措施：

### 1. 紧急止血
- 清理Docker未使用资源，释放 **10.25GB** 空间
- 磁盘使用率从 **100%** 降至 **83%**

### 2. 建立归档表
为所有日志表创建了归档表：
- `her_auth.auth_login_events_archive`
- `her_relationship_ledger.match_relation_events_archive`
- `her_recommendation.recommendation_actions_archive`

### 3. 自动化清理机制
- **SQL脚本**: `scripts/cleanup_log_tables.sql`
- **Shell脚本**: `scripts/cleanup_logs.sh`
- **保留策略**: 90天
- **执行频率**: 每天凌晨3点
- **执行方式**: Kubernetes CronJob 或 crontab

### 4. 监控告警体系
- **监控脚本**: `scripts/monitor_log_tables.sh`
- **Prometheus告警规则**: `monitoring/log_tables_alerts.yaml`
- **监控指标**:
  - `log_table_rows`: 日志表行数
  - `log_table_size_mb`: 日志表大小（MB）
  - `log_table_oldest_age_days`: 最老记录年龄（天）
  - `mysql_disk_usage_percent`: MySQL磁盘使用率

- **告警阈值**:
  - 行数：100万警告，500万严重
  - 大小：1GB警告，5GB严重
  - 年龄：180天警告，365天严重
  - 磁盘：80%警告，90%严重

## 日常运维

### 手动清理

```bash
# 查看统计信息（dry-run）
MYSQL_ROOT_PASSWORD='YOUR_PASSWORD' ./scripts/cleanup_logs.sh --dry-run

# 执行清理
MYSQL_ROOT_PASSWORD='YOUR_PASSWORD' ./scripts/cleanup_logs.sh
```

### 查看监控指标

```bash
# 执行监控脚本
MYSQL_ROOT_PASSWORD='YOUR_PASSWORD' ./scripts/monitor_log_tables.sh

# 查看指标
cat logs/log_tables.prom
```

### 查看日志

```bash
# 清理日志
tail -f logs/log_cleanup.log

# Cron日志
tail -f logs/cron_cleanup.log
```

### 部署定时任务

**方式一：Kubernetes CronJob**
```bash
kubectl apply -f kubernetes/log-tables-cleanup-cronjob.yaml
```

**方式二：crontab**
```bash
crontab -e
# 添加以下行：
0 3 * * * cd /app && MYSQL_ROOT_PASSWORD='YOUR_PASSWORD' ./scripts/cleanup_logs.sh >> logs/cron_cleanup.log 2>&1
```

## 监控告警

### Prometheus 配置

将告警规则添加到 Prometheus 配置：

```yaml
# prometheus.yml
rule_files:
  - /etc/prometheus/log_tables_alerts.yaml
```

### 告警处理流程

1. **收到告警** → 查看具体指标
2. **行数/大小告警** → 检查清理任务是否正常执行
3. **年龄告警** → 手动执行清理脚本
4. **磁盘告警** → 清理Docker资源或扩展磁盘

## 故障排查

### 清理任务失败

1. 检查MySQL容器是否运行：`docker ps | grep mysql`
2. 检查密码是否正确：`docker exec her-mysql-1 mysql -uroot -p'PASSWORD' -e "SELECT 1"`
3. 检查归档表是否存在：`SHOW TABLES LIKE '%archive%'`
4. 检查日志：`tail -f logs/log_cleanup.log`

### 磁盘空间不足

1. 清理Docker资源：`docker system prune -f --volumes`
2. 查看大表：执行 `scripts/monitor_log_tables.sh` 查看表大小
3. 手动清理旧数据：执行清理脚本

### 监控指标异常

1. 检查监控脚本：`./scripts/monitor_log_tables.sh`
2. 检查MySQL连接：`docker exec her-mysql-1 mysql -uroot -p'PASSWORD' -e "SHOW DATABASES"`
3. 检查磁盘空间：`docker exec her-mysql-1 df -h`

## 相关文件

- `scripts/cleanup_log_tables.sql` - SQL清理脚本
- `scripts/cleanup_logs.sh` - Shell清理脚本
- `scripts/cleanup_all_log_tables.py` - Python清理脚本
- `scripts/monitor_log_tables.sh` - 监控脚本
- `monitoring/log_tables_alerts.yaml` - Prometheus告警规则
- `kubernetes/log-tables-cleanup-cronjob.yaml` - Kubernetes CronJob配置

## 检查清单

定期检查（每周）：
- [ ] 清理任务是否正常执行（查看日志）
- [ ] 磁盘使用率是否超过80%
- [ ] 日志表数据量是否正常增长
- [ ] 归档表数据是否正常累积

定期维护（每月）：
- [ ] 检查告警规则是否有效
- [ ] 检查监控指标是否正常采集
- [ ] 评估保留策略是否合理（当前90天）
- [ ] 清理Docker未使用资源

## 联系方式

如有问题，请联系：
- 开发团队：[开发团队联系方式]
- 运维团队：[运维团队联系方式]