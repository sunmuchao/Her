-- Phase 1：用户外貌偏好学习系统 - 数据表创建
-- 创建时间：2026-07-13
-- 设计原则：颜值评分只做基础分，个性化加分包括风格偏好匹配 + 五官偏好匹配

-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 1. 用户外貌行为日志表
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CREATE TABLE IF NOT EXISTS user_appearance_behavior_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
    user_key VARCHAR(128) NOT NULL COMMENT '用户标识',
    candidate_profile_id INT NOT NULL COMMENT '候选人ID',
    action_type VARCHAR(32) NOT NULL COMMENT '行为类型：like/skip/dislike/view',
    action_timestamp DATETIME NOT NULL COMMENT '行为时间',
    session_id VARCHAR(128) COMMENT '会话ID（可选）',

    -- 候选人风格特征快照（用于学习风格偏好）
    candidate_appearance_keywords_json JSON COMMENT '风格标签数组',
    candidate_appearance_summary TEXT COMMENT '外貌描述文本',

    -- 候选人五官特征快照（用于学习五官偏好）
    candidate_eye_size_score FLOAT COMMENT '眼睛大小评分',
    candidate_face_roundness_score FLOAT COMMENT '脸型圆润度评分',
    candidate_jaw_definition_score FLOAT COMMENT '下颌线清晰度评分',
    candidate_youthfulness_score FLOAT COMMENT '幼态感评分',

    -- ❌ 不记录颜值评分（beauty_score）
    -- 颜值评分只做基础分，不参与个性化学习

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    INDEX idx_user_key (user_key),
    INDEX idx_candidate_profile_id (candidate_profile_id),
    INDEX idx_action_type (action_type),
    INDEX idx_action_timestamp (action_timestamp),
    INDEX idx_user_action (user_key, action_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户外貌行为日志表';


-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 2. 用户外貌偏好表（扩展字段）
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

-- 创建表（如果不存在）
CREATE TABLE IF NOT EXISTS user_appearance_preferences (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_key VARCHAR(128) NOT NULL UNIQUE COMMENT '用户标识',
    last_updated DATETIME NOT NULL COMMENT '最后更新时间',

    -- 风格偏好（基于点赞候选人学习）
    preferred_style_tags_json JSON COMMENT '偏好风格标签列表',
    preferred_style_weights_json JSON COMMENT '偏好风格权重字典',
    disliked_style_tags_json JSON COMMENT '不喜欢风格标签列表',

    -- 五官偏好（基于点赞候选人学习）
    preferred_eye_size_score_avg FLOAT COMMENT '偏好眼睛大小平均分',
    preferred_eye_size_score_std FLOAT COMMENT '偏好眼睛大小标准差',
    preferred_face_roundness_score_avg FLOAT COMMENT '偏好脸型圆润度平均分',
    preferred_face_roundness_score_std FLOAT COMMENT '偏好脸型圆润度标准差',
    preferred_jaw_definition_score_avg FLOAT COMMENT '偏好下颌线清晰度平均分',
    preferred_youthfulness_score_avg FLOAT COMMENT '偏好幼态感平均分',

    -- 统计信息
    total_like_count INT DEFAULT 0 COMMENT '点赞总数',
    total_skip_count INT DEFAULT 0 COMMENT '跳过总数',

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',

    INDEX idx_user_key (user_key),
    INDEX idx_last_updated (last_updated)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户外貌偏好表';


-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 3. 初始化示例数据（用于测试）
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

-- 注意：以下为测试数据，生产环境请勿执行

-- 示例：用户小明点赞候选人A（温柔、清秀、眼睛大）
-- INSERT INTO user_appearance_behavior_log (
--     user_key, candidate_profile_id, action_type, action_timestamp,
--     candidate_appearance_keywords_json, candidate_appearance_summary,
--     candidate_eye_size_score, candidate_face_roundness_score
-- ) VALUES (
--     'xiaoming', 1001, 'like', NOW(),
--     '["温柔", "清秀"]', '清秀型，眼睛大，温柔气质',
--     75.0, 40.0
-- );

-- 示例：用户小明点赞候选人B（可爱、甜美）
-- INSERT INTO user_appearance_behavior_log (
--     user_key, candidate_profile_id, action_type, action_timestamp,
--     candidate_appearance_keywords_json, candidate_appearance_summary,
--     candidate_eye_size_score, candidate_face_roundness_score
-- ) VALUES (
--     'xiaoming', 1002, 'like', NOW(),
--     '["可爱", "甜美"]', '可爱型，脸圆，甜美气质',
--     68.0, 60.0
-- );

-- 示例：用户小明跳过候选人C（成熟、眼睛小）
-- INSERT INTO user_appearance_behavior_log (
--     user_key, candidate_profile_id, action_type, action_timestamp,
--     candidate_appearance_keywords_json, candidate_appearance_summary,
--     candidate_eye_size_score, candidate_face_roundness_score
-- ) VALUES (
--     'xiaoming', 1003, 'skip', NOW(),
--     '["成熟", "利落精致"]', '成熟型，利落精致，知性美',
--     45.0, 30.0
-- );


-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
-- 4. 验证表创建成功
-- ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

-- 查看表结构
-- SHOW CREATE TABLE user_appearance_behavior_log;
-- SHOW CREATE TABLE user_appearance_preferences;

-- 查看表字段
-- DESCRIBE user_appearance_behavior_log;
-- DESCRIBE user_appearance_preferences;