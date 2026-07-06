"""创建 verification_submissions 表的脚本"""

import pymysql
import outer_system_mysql_schema as schema

# 连接 her_chat 数据库
config = schema.parse_mysql_dsn('mysql://root:SLhJJ0BfjguKNGpGb5jUJlajt2+5QP7IW3B8aXycnrw=@127.0.0.1:3307/her_chat')
conn = schema.mysql_database_connect(config)

cursor = conn.cursor()

# 创建 verification_submissions 表
create_table_sql = """
CREATE TABLE IF NOT EXISTS verification_submissions (
  submission_id VARCHAR(64) PRIMARY KEY,
  verification_type VARCHAR(32) NOT NULL,
  user_id VARCHAR(191) NOT NULL,
  profile_id BIGINT,
  source_dsn VARCHAR(512),
  source_table_name VARCHAR(191),
  status VARCHAR(32) NOT NULL,
  resubmission_count INT NOT NULL DEFAULT 0,
  challenge_phrase VARCHAR(191),
  review_decision VARCHAR(32),
  review_note LONGTEXT,
  reviewer_id VARCHAR(191),
  latest_asset_id BIGINT,
  latest_sync_status VARCHAR(32),
  latest_sync_error LONGTEXT,
  submitted_at DATETIME NOT NULL,
  reviewed_at DATETIME,
  approved_at DATETIME,
  rejected_at DATETIME,
  machine_review_outcome VARCHAR(32),
  machine_review_score INT,
  expires_at DATETIME,
  revoked_at DATETIME,
  revocation_reason VARCHAR(191),
  metadata_json LONGTEXT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  INDEX idx_verification_submissions_user_status (user_id, status, updated_at),
  INDEX idx_verification_submissions_status_time (status, updated_at),
  INDEX idx_verification_submissions_profile_time (profile_id, updated_at),
  INDEX idx_verification_submissions_machine_outcome (machine_review_outcome, updated_at),
  INDEX idx_verification_submissions_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
"""

cursor.execute(create_table_sql)
conn.commit()
print('✓ verification_submissions 表已在 her_chat 数据库中创建')

conn.close()