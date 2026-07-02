"""Apply verification enhancement tables migration.

This script directly executes the SQL statements to create the new tables
and add new fields to existing tables.
"""

import pymysql
import os

# 数据库连接配置
DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ.get("MYSQL_USER", "root")
DB_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "SLhJJ0BfjguKNGpGb5jUJlajt2+5QP7IW3B8aXycnrw=")
DB_NAME = "her_chat"

def get_connection():
    """获取数据库连接"""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset='utf8mb4',
        autocommit=False
    )

def apply_migration():
    """应用迁移"""
    conn = get_connection()
    cursor = conn.cursor()

    try:
        print("Starting verification enhancement migration...")

        # 1. 创建认证等级权重表
        print("Creating verification_level_weights table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_level_weights (
                level_name VARCHAR(32) PRIMARY KEY,
                weight INT NOT NULL COMMENT '权重值（越高越好）',
                label VARCHAR(64) NOT NULL COMMENT '展示标签',
                expires_after_days INT COMMENT '过期天数（NULL表示永不过期）',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='认证等级权重配置表'
        """)

        # 插入初始数据
        cursor.execute("""
            INSERT INTO verification_level_weights
            (level_name, weight, label, expires_after_days, created_at)
            VALUES
            ('offline_verified', 4, '线下核验照片', NULL, NOW()),
            ('live_video_verified', 3, '活体自拍视频认证', 365, NOW()),
            ('human_verified', 2, '真人照片认证', 365, NOW()),
            ('uploaded', 1, '普通上传照片', NULL, NOW())
            ON DUPLICATE KEY UPDATE weight=VALUES(weight), label=VALUES(label)
        """)
        print("✓ verification_level_weights table created and initialized")

        # 2. 创建认证提交元数据表
        print("Creating verification_submission_metadata table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_submission_metadata (
                submission_id VARCHAR(64) COLLATE utf8mb4_unicode_ci PRIMARY KEY,
                machine_review_json LONGTEXT COMMENT '机器审核详细结果',
                workflow_history_json LONGTEXT COMMENT '工作流历史',
                photo_review_task_json LONGTEXT COMMENT '照片审核任务详情',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (submission_id) REFERENCES verification_submissions(submission_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='认证提交元数据表'
        """)
        print("✓ verification_submission_metadata table created")

        # 3. 创建认证撤销记录表
        print("Creating verification_revocations table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_revocations (
                revocation_id BIGINT PRIMARY KEY AUTO_INCREMENT,
                submission_id VARCHAR(64) COLLATE utf8mb4_unicode_ci NOT NULL,
                user_id VARCHAR(191) NOT NULL,
                profile_id BIGINT,
                revocation_reason VARCHAR(191) NOT NULL COMMENT '撤销原因（争议成立/风控发现造假/用户申请）',
                revoked_by VARCHAR(191) NOT NULL COMMENT '撤销操作人',
                revoked_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                metadata_json LONGTEXT COMMENT '撤销详情（证据、举报ID等）',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (submission_id) REFERENCES verification_submissions(submission_id),
                INDEX idx_revocations_user_time (user_id, revoked_at),
                INDEX idx_revocations_submission (submission_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='认证撤销记录表'
        """)
        print("✓ verification_revocations table created")

        # 4. 创建自动审核质量统计表
        print("Creating verification_auto_review_stats table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_auto_review_stats (
                stat_id BIGINT PRIMARY KEY AUTO_INCREMENT,
                stat_date DATE NOT NULL COMMENT '统计日期',
                verification_type VARCHAR(32) NOT NULL COMMENT '认证类型',
                total_auto_reviews INT NOT NULL DEFAULT 0 COMMENT '自动审核总数',
                auto_approved INT NOT NULL DEFAULT 0 COMMENT '自动通过数',
                auto_resubmission INT NOT NULL DEFAULT 0 COMMENT '自动要求重录数',
                manual_review INT NOT NULL DEFAULT 0 COMMENT '转人工审核数',
                manual_approved_after_auto INT NOT NULL DEFAULT 0 COMMENT '人工复核后通过数',
                manual_rejected_after_auto INT NOT NULL DEFAULT 0 COMMENT '人工复核后拒绝数',
                false_positive_rate DECIMAL(5,2) COMMENT '误拦率（转人工后本可通过的比例）',
                false_negative_recall_count INT NOT NULL DEFAULT 0 COMMENT '漏放后被追撤数量',
                post_approval_revocation_rate DECIMAL(5,2) COMMENT '自动通过后追撤率',
                avg_auto_review_latency_ms INT COMMENT '平均自动审核耗时（毫秒）',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uk_date_type (stat_date, verification_type),
                INDEX idx_stats_date (stat_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='自动审核质量统计表'
        """)
        print("✓ verification_auto_review_stats table created")

        # 5. 创建审核延迟明细表
        print("Creating verification_review_latency table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_review_latency (
                latency_id BIGINT PRIMARY KEY AUTO_INCREMENT,
                submission_id VARCHAR(64) COLLATE utf8mb4_unicode_ci NOT NULL,
                review_type VARCHAR(32) NOT NULL COMMENT 'auto/manual',
                decision VARCHAR(32) NOT NULL,
                latency_ms INT NOT NULL,
                recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_review_latency_time (recorded_at),
                INDEX idx_review_latency_submission (submission_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审核延迟明细表'
        """)
        print("✓ verification_review_latency table created")

        # 6. 创建敏感数据治理策略表
        print("Creating verification_data_governance_policies table...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS verification_data_governance_policies (
                policy_key VARCHAR(64) PRIMARY KEY,
                retention_days INT NOT NULL COMMENT '保留天数',
                encryption_required TINYINT NOT NULL DEFAULT 1 COMMENT '是否强制加密',
                access_scope VARCHAR(64) NOT NULL COMMENT '可访问角色范围',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='认证敏感数据治理策略表'
        """)

        # 插入初始数据
        cursor.execute("""
            INSERT INTO verification_data_governance_policies
            (policy_key, retention_days, encryption_required, access_scope, created_at, updated_at)
            VALUES
            ('raw_verification_media', 30, 1, 'risk_ops,verification_ops', NOW(), NOW()),
            ('ocr_extracted_text', 180, 1, 'verification_ops', NOW(), NOW()),
            ('authority_verification_result', 365, 1, 'verification_ops,risk_ops', NOW(), NOW()),
            ('revocation_evidence', 730, 1, 'risk_ops,compliance_ops', NOW(), NOW())
            ON DUPLICATE KEY UPDATE retention_days=VALUES(retention_days), access_scope=VALUES(access_scope)
        """)
        print("✓ verification_data_governance_policies table created and initialized")

        # 7. 在 verification_submissions 表添加新字段
        print("Adding new fields to verification_submissions table...")
        try:
            cursor.execute("""
                ALTER TABLE verification_submissions
                ADD COLUMN machine_review_outcome VARCHAR(32) COMMENT '机器审核决策'
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" in str(e):
                print("  - machine_review_outcome already exists, skipping...")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE verification_submissions
                ADD COLUMN machine_review_score INT COMMENT '机器审核综合分数'
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" in str(e):
                print("  - machine_review_score already exists, skipping...")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE verification_submissions
                ADD COLUMN expires_at DATETIME COMMENT '认证过期时间'
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" in str(e):
                print("  - expires_at already exists, skipping...")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE verification_submissions
                ADD COLUMN revoked_at DATETIME COMMENT '认证撤销时间'
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" in str(e):
                print("  - revoked_at already exists, skipping...")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE verification_submissions
                ADD COLUMN revocation_reason VARCHAR(191) COMMENT '撤销原因'
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" in str(e):
                print("  - revocation_reason already exists, skipping...")
            else:
                raise

        # 添加索引
        try:
            cursor.execute("""
                CREATE INDEX idx_verification_submissions_machine_outcome
                ON verification_submissions (machine_review_outcome, updated_at)
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate key name" in str(e):
                print("  - idx_verification_submissions_machine_outcome already exists, skipping...")
            else:
                raise

        try:
            cursor.execute("""
                CREATE INDEX idx_verification_submissions_expires_at
                ON verification_submissions (expires_at)
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate key name" in str(e):
                print("  - idx_verification_submissions_expires_at already exists, skipping...")
            else:
                raise

        print("✓ verification_submissions table updated")

        # 8. 在 profile_field_verification_submissions 表添加新字段
        print("Adding new fields to profile_field_verification_submissions table...")
        try:
            cursor.execute("""
                ALTER TABLE profile_field_verification_submissions
                ADD COLUMN ocr_extracted_text LONGTEXT COMMENT 'OCR识别提取的文本'
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" in str(e):
                print("  - ocr_extracted_text already exists, skipping...")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE profile_field_verification_submissions
                ADD COLUMN ocr_confidence_score INT COMMENT 'OCR识别置信度（0-100）'
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" in str(e):
                print("  - ocr_confidence_score already exists, skipping...")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE profile_field_verification_submissions
                ADD COLUMN ocr_processed_at DATETIME COMMENT 'OCR处理时间'
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" in str(e):
                print("  - ocr_processed_at already exists, skipping...")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE profile_field_verification_submissions
                ADD COLUMN authority_verification_status VARCHAR(32) COMMENT '权威机构验证状态'
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" in str(e):
                print("  - authority_verification_status already exists, skipping...")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE profile_field_verification_submissions
                ADD COLUMN authority_verification_result LONGTEXT COMMENT '权威机构验证结果'
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" in str(e):
                print("  - authority_verification_result already exists, skipping...")
            else:
                raise

        try:
            cursor.execute("""
                ALTER TABLE profile_field_verification_submissions
                ADD COLUMN revoked_at DATETIME COMMENT '认证撤销时间'
            """)
        except pymysql.err.OperationalError as e:
            if "Duplicate column name" in str(e):
                print("  - revoked_at already exists, skipping...")
            else:
                raise

        print("✓ profile_field_verification_submissions table updated")

        # 提交事务
        conn.commit()
        print("\n✅ Migration completed successfully!")

        # 验证表结构
        print("\nValidating migration...")
        cursor.execute("SELECT COUNT(*) FROM verification_level_weights")
        level_count = cursor.fetchone()[0]
        print(f"  - verification_level_weights: {level_count} records (expected: 4)")

        cursor.execute("SELECT COUNT(*) FROM verification_data_governance_policies")
        policy_count = cursor.fetchone()[0]
        print(f"  - verification_data_governance_policies: {policy_count} records (expected: 4)")

        if level_count == 4 and policy_count == 4:
            print("✅ Migration validation passed!")
        else:
            print("⚠️  Migration validation failed: initial data count mismatch")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ Migration failed: {e}")
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    apply_migration()