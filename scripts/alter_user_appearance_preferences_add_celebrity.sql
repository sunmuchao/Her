-- Phase 1：扩展用户外貌偏好表 - 新增明星类型偏好字段
-- 创建时间：2026-07-15
-- 设计原则：记录用户搜索明星脸时的偏好，用于个性化推荐

-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 1. 添加明星类型偏好字段
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALTER TABLE user_appearance_preferences
ADD COLUMN preferred_celebrity_types_json JSON COMMENT '明星类型偏好列表（如["田曦薇类型", "刘亦菲类型"]）',
ADD COLUMN preferred_celebrity_weights_json JSON COMMENT '明星类型偏好权重字典（如{"田曦薇类型": 0.8}）';

-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 2. 添加positive_sample_count和negative_sample_count字段（如果不存在）
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

-- 检查字段是否存在，如果不存在则添加
-- 注意：MySQL不支持IF NOT EXISTS，需要手动检查

-- 如果字段已存在会报错，可以忽略
ALTER TABLE user_appearance_preferences
ADD COLUMN positive_sample_count INT DEFAULT 0 COMMENT '正向样本数量（搜明星脸次数）';

ALTER TABLE user_appearance_preferences
ADD COLUMN negative_sample_count INT DEFAULT 0 COMMENT '负向样本数量（跳过次数）';

-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 3. 验证字段添加成功
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

-- 查看表结构
DESCRIBE user_appearance_preferences;

-- 查看新增字段
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    COLUMN_COMMENT
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'user_appearance_preferences'
    AND COLUMN_NAME IN (
        'preferred_celebrity_types_json',
        'preferred_celebrity_weights_json',
        'positive_sample_count',
        'negative_sample_count'
    );