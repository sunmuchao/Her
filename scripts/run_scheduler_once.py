#!/usr/bin/env python3
"""单次检查无活动会话（用于外部调度器）

使用方式：
python scripts/run_scheduler_once.py

外部调度示例（cron）：
*/5 * * * * cd /path/to/project && python scripts/run_scheduler_once.py >> .run/logs/scheduler.log 2>&1

功能说明：
- 检查超过30分钟无活动的会话
- 触发摘要处理（异步后台处理）
- 输出检查结果到日志
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_logger = logging.getLogger(__name__)


async def main() -> None:
    """主函数：单次检查无活动会话"""

    # 检查环境变量
    discovery_dsn = os.environ.get("PARTNER_DISCOVERY_DB", "")
    if not discovery_dsn:
        _logger.error("错误：缺少 PARTNER_DISCOVERY_DB 环境变量")
        sys.exit(1)

    persona_dsn = os.environ.get("PERSONA_MEMORY_MYSQL_SOURCE", "")
    if not persona_dsn:
        _logger.warning("警告：缺少 PERSONA_MEMORY_MYSQL_SOURCE 环境变量，无法写入摘要")

    llm_base_url = os.environ.get("HER_DISCOVERY_AGENT_BASE_URL")
    llm_api_key = os.environ.get("HER_DISCOVERY_AGENT_API_KEY")
    llm_model = os.environ.get("HER_DISCOVERY_AGENT_MODEL")

    _logger.info(
        f"开始检查无活动会话: "
        f"time={datetime.now().isoformat()}, "
        f"threshold=30分钟"
    )

    try:
        # 导入必要的模块
        from external_systems.partner_discovery_system.discovery_system.storage import MySQLDiscoveryStorage
        from match_domain.session_end_scheduler import run_once_inactive_session_check

        # 创建 storage 对象
        storage = MySQLDiscoveryStorage(discovery_dsn)

        # 执行单次检查
        tasks = await run_once_inactive_session_check(
            storage=storage,
            inactive_threshold_minutes=30,
            dsn=persona_dsn,
            llm_base_url=llm_base_url,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
        )

        # 输出结果
        _logger.info(
            f"检查完成: "
            f"发现无活动会话={len(tasks)}个, "
            f"触发处理任务={len([t for t in tasks if t])}个"
        )

        # 等待所有任务完成（可选）
        if tasks:
            _logger.info("等待后台任务完成...")
            # 不等待，因为任务会在后台异步执行

        _logger.info("单次检查完成")

    except Exception as exc:
        _logger.error(f"检查失败: error={exc}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())