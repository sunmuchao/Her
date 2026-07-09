#!/usr/bin/env python3
"""
照片分析Worker - 处理async_jobs表中的photo_feature_refresh任务

执行方式：
python scripts/run_photo_analysis_worker.py

后台运行：
nohup python scripts/run_photo_analysis_worker.py > logs/photo_analysis.log 2>&1 &

作者：Claude Code
日期：2026-07-08
"""

import logging
import os
import sys
import time
from datetime import datetime

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from match_domain.appearance_features import refresh_profile_photo_features
from profile_service import get_profile, list_profile_photos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
_logger = logging.getLogger(__name__)


def get_mysql_connection(db_name: str = "her_infrastructure"):
    """获取MySQL数据库连接"""
    import pymysql

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


def claim_next_job():
    """从async_jobs表中认领下一个待处理任务"""
    infra_conn = get_mysql_connection("her_infrastructure")

    try:
        with infra_conn.cursor() as cursor:
            # 查询下一个待处理任务
            sql = """
            SELECT *
            FROM async_jobs
            WHERE job_type = 'photo_feature_refresh'
              AND status = 'pending'
              AND next_attempt_at <= NOW()
            ORDER BY created_at ASC
            LIMIT 1
            """

            cursor.execute(sql)
            job = cursor.fetchone()

            if not job:
                return None

            # 认领任务（更新状态为processing）
            claim_token = f"claim-{os.getpid()}-{int(time.time())}"
            sql = """
            UPDATE async_jobs
            SET status = 'processing',
                claim_token = %s,
                claim_started_at = NOW(),
                claim_worker = %s,
                attempt_count = attempt_count + 1,
                started_at = NOW()
            WHERE job_id = %s
              AND status = 'pending'
            """

            cursor.execute(sql, (claim_token, f"worker-{os.getpid()}", job["job_id"]))
            infra_conn.commit()

            # 返回认领的任务
            job["claim_token"] = claim_token
            return job

    finally:
        infra_conn.close()


def execute_job(job):
    """执行照片分析任务"""
    import json

    job_id = job["job_id"]
    payload = json.loads(job.get("payload_json") or "{}")
    profile_id = payload.get("profile_id")
    source_dsn = payload.get("source_dsn", "mysql://root@127.0.0.1:3307/her")

    _logger.info(f"🔍 开始处理任务 {job_id}，用户 {profile_id}")

    try:
        # 执行照片分析
        result = refresh_profile_photo_features(
            source_dsn=source_dsn,
            profile_id=profile_id,
        )

        if result.get("saved") and result.get("analysis_status") == "done":
            # 成功
            mark_job_success(job_id, result)
            _logger.info(f"✅ 任务 {job_id} 执行成功")
            _logger.info(f"   - 颜值评分: {result.get('beauty_score', 0):.2f}")
            _logger.info(f"   - 外貌描述: {result.get('appearance_summary', '')[:50]}...")
            return True
        else:
            # 失败
            error_msg = result.get("last_error", "unknown_error")
            mark_job_failed(job_id, error_msg)
            _logger.warning(f"⚠️ 任务 {job_id} 执行失败: {error_msg}")
            return False

    except Exception as e:
        # 异常
        error_msg = f"execution_error: {str(e)}"
        mark_job_failed(job_id, error_msg)
        _logger.error(f"❌ 任务 {job_id} 执行异常: {str(e)}")
        return False


def mark_job_success(job_id, result):
    """标记任务成功"""
    import json

    infra_conn = get_mysql_connection("her_infrastructure")

    try:
        with infra_conn.cursor() as cursor:
            sql = """
            UPDATE async_jobs
            SET status = 'succeeded',
                result_json = %s,
                finished_at = NOW(),
                claim_token = NULL,
                claim_started_at = NULL
            WHERE job_id = %s
            """

            cursor.execute(sql, (json.dumps(result), job_id))
            infra_conn.commit()

    finally:
        infra_conn.close()


def mark_job_failed(job_id, error_msg):
    """标记任务失败"""
    infra_conn = get_mysql_connection("her_infrastructure")

    try:
        with infra_conn.cursor() as cursor:
            # 检查是否需要重试
            cursor.execute("SELECT attempt_count, max_attempts FROM async_jobs WHERE job_id = %s", (job_id,))
            job = cursor.fetchone()

            attempt_count = int(job.get("attempt_count") or 0)
            max_attempts = int(job.get("max_attempts") or 3)

            if attempt_count < max_attempts:
                # 还可以重试，设置为retry_pending
                next_delay = 15 * (2 ** (attempt_count - 1))  # 15s, 30s, 60s
                sql = """
                UPDATE async_jobs
                SET status = 'retry_pending',
                    error_text = %s,
                    next_attempt_at = NOW() + INTERVAL %s SECOND,
                    claim_token = NULL,
                    claim_started_at = NULL
                WHERE job_id = %s
                """
                cursor.execute(sql, (error_msg, next_delay, job_id))
            else:
                # 已达到最大重试次数，标记为failed
                sql = """
                UPDATE async_jobs
                SET status = 'failed',
                    error_text = %s,
                    finished_at = NOW(),
                    claim_token = NULL,
                    claim_started_at = NULL
                WHERE job_id = %s
                """
                cursor.execute(sql, (error_msg, job_id))

            infra_conn.commit()

    finally:
        infra_conn.close()


def run_worker(limit=10, sleep_interval=5):
    """
    运行Worker，处理async_jobs表中的照片分析任务

    Args:
        limit: 每轮处理任务数上限
        sleep_interval: 无任务时的休眠间隔（秒）
    """
    _logger.info("=" * 80)
    _logger.info("照片分析Worker启动")
    _logger.info(f"配置：limit={limit}, sleep_interval={sleep_interval}s")
    _logger.info("=" * 80)

    processed_count = 0
    success_count = 0
    failed_count = 0

    while True:
        # 认领下一个任务
        job = claim_next_job()

        if not job:
            # 无待处理任务
            _logger.info(f"💤 无待处理任务，休眠 {sleep_interval}s...")
            time.sleep(sleep_interval)
            continue

        # 执行任务
        success = execute_job(job)

        processed_count += 1
        if success:
            success_count += 1
        else:
            failed_count += 1

        # 每处理10个任务输出统计信息
        if processed_count % 10 == 0:
            _logger.info("=" * 80)
            _logger.info(f"📊 处理统计：已处理 {processed_count} 个任务")
            _logger.info(f"   - 成功：{success_count} 个")
            _logger.info(f"   - 失败：{failed_count} 个")
            _logger.info("=" * 80)

        # 每处理limit个任务后休眠一会儿，避免过载
        if processed_count % limit == 0:
            _logger.info(f"⏸️ 已处理 {limit} 个任务，休眠10s...")
            time.sleep(10)


def main():
    """主函数"""
    try:
        run_worker(limit=10, sleep_interval=5)
    except KeyboardInterrupt:
        _logger.info("⌨️ 接收到Ctrl+C信号，Worker停止")
        sys.exit(0)
    except Exception as e:
        _logger.error(f"❌ Worker异常退出: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()