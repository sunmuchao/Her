-- 紧急清理脚本：auth_login_events 表数据归档
-- 执行前请先备份数据！
-- 执行步骤：
-- 1. 创建归档表
-- 2. 迁移90天前的数据
-- 3. 删除已归档数据
-- 4. 优化表空间

-- Step 1: 创建归档表（如果不存在）
CREATE TABLE IF NOT EXISTS auth_login_events_archive (
    event_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64),
    phone VARCHAR(255),
    event_type VARCHAR(64) NOT NULL,
    result VARCHAR(32) NOT NULL,
    reason_code VARCHAR(64),
    client_ip VARCHAR(64),
    device_id VARCHAR(128),
    metadata_json LONGTEXT NOT NULL,
    created_at DATETIME NOT NULL,
    archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (event_id),
    INDEX idx_archived_at (archived_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Step 2: 迁移90天前的数据到归档表（分批执行，避免锁表）
-- 注意：建议每次迁移10万条，分多次执行
INSERT INTO auth_login_events_archive
SELECT *, NOW() as archived_at
FROM auth_login_events
WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY)
LIMIT 100000;

-- Step 3: 删除已归档的数据（分批执行）
DELETE FROM auth_login_events
WHERE created_at < DATE_SUB(NOW(), INTERVAL 90 DAY)
LIMIT 100000;

-- Step 4: 优化表空间（释放磁盘空间）
OPTIMIZE TABLE auth_login_events;

-- Step 5: 查看表状态
SHOW TABLE STATUS LIKE 'auth_login_events';
SELECT COUNT(*) as total_rows, MIN(created_at) as oldest_record, MAX(created_at) as newest_record
FROM auth_login_events;