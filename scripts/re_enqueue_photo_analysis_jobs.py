#!/usr/bin/env python3
"""
重新入队照片分析任务到正确的数据库（her）

调度器Worker读取的是her数据库的async_jobs表，
所以我需要在her数据库中入队任务，而不是her_infrastructure。

作者：Claude Code
日期：2026-07-08
"""

import logging
import os
import sys
import json
import uuid
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pymysql

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
_logger = logging.getLogger(__name__)


def get_mysql_connection(db_name: str = "her"):
    """获取MySQL数据库连接"""
    db_host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    db_port = int(os.environ.get("MYSQL_PORT", "3307"))
    db_user = os.environ.get("MYSQL_USER", "root")
    db_pass = os.environ.get("MYSQL_ROOT_PASSWORD", "SLhJJ0BfjguKNGpGb5jUJlajt2+5QP7IW3B8aXycnrw=")

    connection = pymysql.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_pass,
        database=db_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )

    return connection


def query_target_users() -> list[int]:
    """查询目标用户profile_id列表"""
    connection = get_mysql_connection("her")

    try:
        with connection.cursor() as cursor:
            sql = """
            SELECT id as profile_id
            FROM profiles
            WHERE gender = '女'
              AND city = '无锡'
              AND age >= 20
              AND age <= 40
              AND avatar_url IS NOT NULL
              AND avatar_url != ''
              AND photo_count > 0
            ORDER BY id DESC
            """

            cursor.execute(sql)
            results = cursor.fetchall()

            profile_ids = [int(row["profile_id"]) for row in results]

            _logger.info(f"✅ 查询到 {len(profile_ids)} 个符合条件的用户")

            return profile_ids

    finally:
        connection.close()


def clear_old_jobs_in_her():
    """清空her数据库中的旧任务（如果有）"""
    connection = get_mysql_connection("her")

    try:
        with connection.cursor() as cursor:
            sql = """
            DELETE FROM async_jobs
            WHERE job_type = 'photo_feature_refresh'
              AND created_by = 'batch_photo_analysis_script'
            """

            cursor.execute(sql)
            deleted_count = cursor.rowcount
            connection.commit()

            _logger.info(f"🗑️ 清空her数据库中的旧任务：{deleted_count}个")

    finally:
        connection.close()


def enqueue_jobs_to_her_db(profile_ids: list[int]):
    """批量入队任务到her数据库的async_jobs表"""
    connection = get_mysql_connection("her")

    try:
        with connection.cursor() as cursor:
            # 构建批量插入SQL
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            source_dsn = "mysql://root@mysql:3306/her?table=profiles"  # 容器内的连接字符串

            batch_size = 50
            total = len(profile_ids)
            inserted = 0

            _logger.info(f"🚀 开始入队任务到her数据库，共 {total} 个")

            for i in range(0, total, batch_size):
                batch = profile_ids[i : i + batch_size]

                for profile_id in batch:
                    job_id = f"job-{uuid.uuid4().hex[:16]}"
                    payload = {
                        "profile_id": profile_id,
                        "source_dsn": source_dsn,
                        "trigger_reason": "batch_analysis_script",
                    }

                    sql = """
                    INSERT INTO async_jobs (
                        job_id,
                        job_type,
                        status,
                        payload_json,
                        max_attempts,
                        next_attempt_at,
                        created_by,
                        trace_id,
                        created_at
                    ) VALUES (%s, %s, 'pending', %s, 3, %s, %s, %s, %s)
                    """

                    cursor.execute(
                        sql,
                        (
                            job_id,
                            "photo_feature_refresh",
                            json.dumps(payload),
                            ts,
                            "batch_photo_analysis_script",
                            f"batch-photo:{profile_id}",
                            ts,
                        ),
                    )

                    inserted += 1

                connection.commit()

                if (i + batch_size) % 500 == 0 or (i + batch_size) >= total:
                    _logger.info(f"   ✅ 已入队 {inserted}/{total} 个任务")

            _logger.info(f"✅ 成功入队 {inserted} 个任务到her数据库")

    finally:
        connection.close()


def main():
    """主函数"""
    _logger.info("=" * 80)
    _logger.info("重新入队照片分析任务到正确的数据库（her）")
    _logger.info("=" * 80)

    # 1. 查询目标用户
    _logger.info("🔍 步骤1：查询目标用户")
    profile_ids = query_target_users()

    if not profile_ids:
        _logger.warning("⚠️ 未找到符合条件的用户")
        return

    # 2. 清空her数据库中的旧任务
    _logger.info("🗑️ 步骤2：清空旧任务")
    clear_old_jobs_in_her()

    # 3. 批量入队任务到her数据库
    _logger.info("🚀 步骤3：批量入队任务")
    enqueue_jobs_to_her_db(profile_ids)

    _logger.info("=" * 80)
    _logger.info("✅ 完成！调度器Worker现在可以处理这些任务了")
    _logger.info("=" * 80)

    _logger.info("📝 查看任务执行进度：")
    _logger.info("   docker compose logs scheduler --tail=100 | grep photo_feature_refresh")


if __name__ == "__main__":
    main()