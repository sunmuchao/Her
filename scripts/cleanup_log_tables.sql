-- 日志表清理脚本
-- 执行频率：每天凌晨3点
-- 保留策略：90天

-- 设置变量
SET @retention_days = 90;
SET @batch_size = 100000;
SET @cutoff_date = DATE_SUB(NOW(), INTERVAL @retention_days DAY);

-- 显示统计信息
SELECT '========== Before Cleanup ==========' as status;
SELECT 'auth_login_events' as table_name, COUNT(*) as total_rows FROM her_auth.auth_login_events;
SELECT 'match_relation_events' as table_name, COUNT(*) as total_rows FROM her_relationship_ledger.match_relation_events;
SELECT 'recommendation_actions' as table_name, COUNT(*) as total_rows FROM her_recommendation.recommendation_actions;

-- 1. 清理 auth_login_events
USE her_auth;
-- 归档旧数据
INSERT INTO auth_login_events_archive
SELECT *, NOW() as archived_at
FROM auth_login_events
WHERE created_at < @cutoff_date
LIMIT @batch_size;
-- 删除已归档数据
DELETE FROM auth_login_events
WHERE created_at < @cutoff_date
LIMIT @batch_size;
-- 优化表空间
OPTIMIZE TABLE auth_login_events;

-- 2. 清理 match_relation_events
USE her_relationship_ledger;
-- 归档旧数据
INSERT INTO match_relation_events_archive
SELECT *, NOW() as archived_at
FROM match_relation_events
WHERE occurred_at < @cutoff_date
LIMIT @batch_size;
-- 删除已归档数据
DELETE FROM match_relation_events
WHERE occurred_at < @cutoff_date
LIMIT @batch_size;
-- 优化表空间
OPTIMIZE TABLE match_relation_events;

-- 3. 清理 recommendation_actions
USE her_recommendation;
-- 归档旧数据
INSERT INTO recommendation_actions_archive
SELECT *, NOW() as archived_at
FROM recommendation_actions
WHERE occurred_at < @cutoff_date
LIMIT @batch_size;
-- 删除已归档数据
DELETE FROM recommendation_actions
WHERE occurred_at < @cutoff_date
LIMIT @batch_size;
-- 优化表空间
OPTIMIZE TABLE recommendation_actions;

-- 显示清理后统计信息
SELECT '========== After Cleanup ==========' as status;
SELECT 'auth_login_events' as table_name, COUNT(*) as total_rows FROM her_auth.auth_login_events;
SELECT 'match_relation_events' as table_name, COUNT(*) as total_rows FROM her_relationship_ledger.match_relation_events;
SELECT 'recommendation_actions' as table_name, COUNT(*) as total_rows FROM her_recommendation.recommendation_actions;

SELECT 'Cleanup completed successfully' as status;