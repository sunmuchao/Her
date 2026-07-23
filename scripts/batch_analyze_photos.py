#!/usr/bin/env python3
"""
批量照片分析脚本 - 分析无锡女性用户（20-40岁）的照片

执行方式：
1. 查询符合条件的用户（无锡女性，20-40岁）
2. 查询这些用户的照片数据
3. 触发照片分析任务（异步后台执行）
4. 生成颜值评分、风格描述、人脸向量等数据

作者：Claude Code
日期：2026-07-08
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Any

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from profile_service import get_profile, list_profile_photos
from match_domain.appearance_features import refresh_profile_photo_features
from async_jobs.queue import enqueue_async_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
_logger = logging.getLogger(__name__)

REQUIRE_OPT_IN_ENV = "ALLOW_BULK_PHOTO_ANALYSIS_REENQUEUE"


def get_mysql_connection(db_name: str = "her"):
    """获取MySQL数据库连接"""
    import pymysql

    # 从环境变量读取数据库配置（根据.env文件）
    db_host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    db_port = int(os.environ.get("MYSQL_PORT", "3307"))  # 注意：端口是3307
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


def require_explicit_opt_in() -> None:
    raw = str(os.environ.get(REQUIRE_OPT_IN_ENV) or "").strip().lower()
    if raw in {"1", "true", "yes"}:
        return
    raise SystemExit(
        f"Refusing to bulk photo-analyze users without {REQUIRE_OPT_IN_ENV}=1"
    )


def query_target_users() -> list[dict[str, Any]]:
    """
    查询目标用户：无锡女性，20-40岁

    Returns:
        list: 符合条件的用户列表
    """
    connection = get_mysql_connection("her")  # her数据库

    try:
        with connection.cursor() as cursor:
            # 查询无锡女性用户，年龄20-40岁
            # profiles表有gender, city, age, avatar_url字段
            sql = """
            SELECT
                id as profile_id,
                gender,
                city,
                age,
                avatar_url,
                photo_count,
                verified_level,
                photo_verification_level
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

            _logger.info(f"✅ 查询到 {len(results)} 个符合条件的用户（有照片）")

            return results

    finally:
        connection.close()


def query_photo_features_status(profile_ids: list[int]) -> dict[int, dict[str, Any]]:
    """
    查询照片分析状态

    Args:
        profile_ids: 用户ID列表

    Returns:
        dict: 照片分析状态字典 {profile_id: feature_row}
    """
    if not profile_ids:
        return {}

    connection = get_mysql_connection("her")  # her数据库

    try:
        with connection.cursor() as cursor:
            # 查询照片分析状态
            sql = """
            SELECT
                profile_id,
                analysis_status,
                last_error,
                beauty_score,
                appearance_summary,
                created_at,
                updated_at
            FROM profile_photo_features
            WHERE profile_id IN (%s)
            """ % ",".join(str(pid) for pid in profile_ids)

            cursor.execute(sql)
            results = cursor.fetchall()

            # 转换为字典
            status_map = {row["profile_id"]: row for row in results}

            _logger.info(f"✅ 查询到 {len(status_map)} 个已有照片分析记录")

            return status_map

    finally:
        connection.close()


def enqueue_photo_analysis_job(profile_id: int, source_dsn: str) -> dict[str, Any]:
    """
    入队照片分析任务（异步后台执行）

    使用MySQL直接插入async_jobs表

    Args:
        profile_id: 用户ID
        source_dsn: 数据源连接字符串

    Returns:
        dict: 任务入队结果
    """
    import json
    import uuid

    # 连接her_infrastructure数据库（async_jobs表）
    infra_conn = get_mysql_connection("her_infrastructure")

    try:
        with infra_conn.cursor() as cursor:
            # 生成job_id
            job_id = f"job-{uuid.uuid4().hex[:16]}"

            # 构建payload
            job_payload = {
                "profile_id": profile_id,
                "source_dsn": source_dsn,
                "trigger_reason": "batch_analysis_script",
                "triggered_at": datetime.now().isoformat(),
            }

            # 当前时间
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 直接插入async_jobs表（MySQL格式）
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

            cursor.execute(sql, (
                job_id,
                "photo_feature_refresh",
                json.dumps(job_payload),
                ts,
                "batch_photo_analysis_script",
                f"batch-photo:{profile_id}",
                ts,
            ))

            infra_conn.commit()

            _logger.info(f"   ✅ 用户 {profile_id} 任务已入队（job_id: {job_id})")

            return {
                "job_id": job_id,
                "saved": True,
            }

    except Exception as e:
        _logger.error(f"   ⚠️ 用户 {profile_id} 任务入队失败: {str(e)}")
        return {
            "job_id": None,
            "saved": False,
            "error": str(e),
        }
    finally:
        infra_conn.close()


def analyze_photos_sync(profile_id: int, source_dsn: str) -> dict[str, Any]:
    """
    同步执行照片分析（阻塞等待）

    Args:
        profile_id: 用户ID
        source_dsn: 数据源连接字符串

    Returns:
        dict: 分析结果
    """
    try:
        _logger.info(f"🔍 开始分析用户 {profile_id} 的照片...")

        result = refresh_profile_photo_features(
            source_dsn=source_dsn,
            profile_id=profile_id,
        )

        if result.get("saved") and result.get("analysis_status") == "done":
            _logger.info(f"✅ 用户 {profile_id} 照片分析成功")
            _logger.info(f"   - 颜值评分: {result.get('beauty_score', 0):.2f}")
            _logger.info(f"   - 外貌描述: {result.get('appearance_summary', '')}")
        else:
            _logger.warning(f"⚠️ 用户 {profile_id} 照片分析失败: {result.get('last_error', '')}")

        return result

    except Exception as e:
        _logger.error(f"❌ 用户 {profile_id} 照片分析异常: {str(e)}")
        return {"saved": False, "error": str(e)}


async def analyze_photos_batch_async(
    profile_ids: list[int],
    source_dsn: str,
    batch_size: int = 10,
) -> dict[str, Any]:
    """
    批量异步执行照片分析（后台并发）

    Args:
        profile_ids: 用户ID列表
        source_dsn: 数据源连接字符串
        batch_size: 每批处理数量

    Returns:
        dict: 批量分析结果统计
    """
    total = len(profile_ids)
    success_count = 0
    failed_count = 0
    pending_count = 0

    _logger.info(f"🚀 开始批量照片分析，共 {total} 个用户，每批 {batch_size} 个")

    for i in range(0, total, batch_size):
        batch = profile_ids[i : i + batch_size]

        _logger.info(f"📦 处理第 {i // batch_size + 1} 批：{len(batch)} 个用户")

        for profile_id in batch:
            # 入队异步任务
            result = enqueue_photo_analysis_job(profile_id, source_dsn)

            if result.get("job_id"):
                pending_count += 1
                _logger.info(f"   ✅ 用户 {profile_id} 任务已入队（job_id: {result['job_id']})")
            else:
                failed_count += 1
                _logger.warning(f"   ⚠️ 用户 {profile_id} 任务入队失败")

        # 每批之间暂停一会儿，避免过载
        if i + batch_size < total:
            await asyncio.sleep(2)

    return {
        "total": total,
        "success": success_count,
        "failed": failed_count,
        "pending": pending_count,
        "message": f"已完成 {pending_count} 个任务的入队，等待后台Worker执行",
    }


def analyze_photos_batch_sync(
    profile_ids: list[int],
    source_dsn: str,
    batch_size: int = 5,
) -> dict[str, Any]:
    """
    批量同步执行照片分析（阻塞等待）

    Args:
        profile_ids: 用户ID列表
        source_dsn: 数据源连接字符串
        batch_size: 每批处理数量

    Returns:
        dict: 批量分析结果统计
    """
    total = len(profile_ids)
    success_count = 0
    failed_count = 0

    _logger.info(f"🚀 开始批量照片分析（同步模式），共 {total} 个用户，每批 {batch_size} 个")

    for i in range(0, total, batch_size):
        batch = profile_ids[i : i + batch_size]

        _logger.info(f"📦 处理第 {i // batch_size + 1} 批：{len(batch)} 个用户")

        for profile_id in batch:
            result = analyze_photos_sync(profile_id, source_dsn)

            if result.get("saved") and result.get("analysis_status") == "done":
                success_count += 1
            else:
                failed_count += 1

        # 每批之间暂停一会儿，避免API调用过载
        if i + batch_size < total:
            _logger.info("   ⏸️ 暂停30秒，避免API调用过载...")
            import time

            time.sleep(30)

    return {
        "total": total,
        "success": success_count,
        "failed": failed_count,
        "message": f"分析完成：成功 {success_count} 个，失败 {failed_count} 个",
    }


def main():
    """主函数"""
    require_explicit_opt_in()
    _logger.info("=" * 80)
    _logger.info("批量照片分析脚本 - 分析无锡女性用户（20-40岁）的照片")
    _logger.info("=" * 80)

    # 1. 查询目标用户
    _logger.info("🔍 步骤1：查询目标用户（无锡女性，20-40岁）")
    target_users = query_target_users()

    if not target_users:
        _logger.warning("⚠️ 未找到符合条件的用户，脚本结束")
        return

    # 2. 查询照片分析状态
    _logger.info("🔍 步骤2：查询照片分析状态")
    profile_ids = [user["profile_id"] for user in target_users]
    features_status = query_photo_features_status(profile_ids)

    # 3. 分析统计
    _logger.info("📊 步骤3：分析统计")
    need_analysis = []
    already_done = []
    failed_before = []

    for user in target_users:
        profile_id = user["profile_id"]
        status = features_status.get(profile_id)

        if not status:
            # 未分析过的
            need_analysis.append(profile_id)
        elif status.get("analysis_status") == "done":
            # 已分析成功的
            already_done.append(profile_id)
        elif status.get("analysis_status") in ("pending", "processing", "failed"):
            # 未完成或失败的
            need_analysis.append(profile_id)
            if status.get("analysis_status") == "failed":
                failed_before.append(profile_id)

    _logger.info(f"   - 总用户数：{len(target_users)}")
    _logger.info(f"   - 已分析成功：{len(already_done)}")
    _logger.info(f"   - 之前失败：{len(failed_before)}")
    _logger.info(f"   - 需要分析：{len(need_analysis)}")

    # 4. 用户选择执行模式
    _logger.info("⚡ 步骤4：选择执行模式")
    _logger.info("   - 模式1：异步后台执行（推荐，大量照片）")
    _logger.info("   - 模式2：同步阻塞执行（适合少量照片）")

    # 默认使用异步模式
    mode = "async"

    # 5. 获取数据库连接字符串
    source_dsn = os.environ.get("SOURCE_DSN", "mysql://root@localhost:3306/her")

    # 6. 执行分析
    _logger.info("🚀 步骤5：执行照片分析")

    if mode == "async":
        # 异步模式：入队任务
        result = asyncio.run(analyze_photos_batch_async(need_analysis, source_dsn))
    else:
        # 同步模式：直接执行
        result = analyze_photos_batch_sync(need_analysis, source_dsn)

    _logger.info("=" * 80)
    _logger.info(f"✅ 执行完成：{result['message']}")
    _logger.info("=" * 80)

    # 7. 输出详细结果
    if mode == "async":
        _logger.info("📝 后续操作：")
        _logger.info("   1. 查看任务状态：SELECT * FROM async_jobs WHERE job_type='photo_feature_refresh'")
        _logger.info("   2. 查看分析结果：SELECT * FROM profile_photo_features WHERE analysis_status='done'")
        _logger.info("   3. 查看向量数据：SELECT * FROM profile_face_embeddings WHERE profile_id IN (...)")
        _logger.info("   4. 等待Worker执行完成（约30秒-5分钟）")


if __name__ == "__main__":
    main()
