#!/usr/bin/env python3
"""诊断搜索结果为0的原因

通过查询数据库，逐步分析每个筛选条件的影响
"""

import os
import sys
import json
import logging
from typing import Any

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
_logger = logging.getLogger(__name__)

# 添加项目路径
sys.path.insert(0, '/Users/sunmuchao/Downloads/Her')

try:
    from her_repo_path_bootstrap import ensure_partner_system_roots_on_sys_path
    ensure_partner_system_roots_on_sys_path('/Users/sunmuchao/Downloads/Her')
except ImportError:
    pass

try:
    from partner_search.mysql_source import MySQLSource
    from profile_source_refs import build_source_file_ref
except ImportError as e:
    _logger.error(f"导入失败: {e}")
    sys.exit(1)


def get_mysql_source() -> MySQLSource | None:
    """获取MySQL数据源"""
    # 尝试从环境变量获取数据库连接字符串
    dsn = os.environ.get('PARTNER_SEARCH_MYSQL_SOURCE') or \
          os.environ.get('HER_DISCOVERY_PROFILE_SOURCE') or \
          os.environ.get('PERSONA_MEMORY_MYSQL_SOURCE')

    if not dsn:
        _logger.error("未找到数据库连接字符串环境变量")
        return None

    try:
        source = MySQLSource(dsn=dsn)
        return source
    except Exception as e:
        _logger.error(f"创建MySQLSource失败: {e}")
        return None


def query_candidate_count(source: MySQLSource, conditions: dict[str, Any], description: str) -> int:
    """查询满足条件的候选人数量"""
    try:
        # 构建SQL查询
        where_clauses = []
        params = []

        for key, value in conditions.items():
            if value is None:
                continue
            if isinstance(value, list):
                if len(value) == 0:
                    continue
                placeholders = ", ".join(["%s"] * len(value))
                where_clauses.append(f"{key} IN ({placeholders})")
                params.extend(value)
            else:
                where_clauses.append(f"{key} = %s")
                params.append(value)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        sql = f"SELECT COUNT(*) as count FROM profiles WHERE {where_sql}"

        _logger.info(f"【{description}】执行SQL: {sql}")
        _logger.info(f"【{description}】参数: {params}")

        # 执行查询
        result = source.execute_query(sql, params)
        count = result[0]['count'] if result else 0

        _logger.info(f"【{description}】结果: {count}人")
        return count

    except Exception as e:
        _logger.error(f"【{description}】查询失败: {e}")
        return -1


def diagnose_search_zero_results():
    """诊断搜索结果为0的原因"""

    _logger.info("=" * 80)
    _logger.info("开始诊断搜索结果为0的原因")
    _logger.info("=" * 80)

    # 获取数据源
    source = get_mysql_source()
    if not source:
        _logger.error("无法获取数据源，诊断终止")
        return

    # 用户信息
    user_profile_id = 10006
    user_age = 28
    user_city = "无锡"
    user_gender = "male"
    user_sexual_orientation = "like_female"

    _logger.info(f"用户信息: profile_id={user_profile_id}, age={user_age}, city={user_city}, gender={user_gender}, sexual_orientation={user_sexual_orientation}")

    # 推导的搜索条件
    target_gender = "female"  # 从like_female推导
    target_cities = [user_city]  # 无锡
    target_relationship_goals = ["结婚导向"]  # 假设（需要从用户资料中确认）
    profile_statuses = ["active", "matched", "paused", "inactive", "archived"]  # 可以搜索所有状态

    _logger.info(f"推导的搜索条件:")
    _logger.info(f"  - gender={target_gender}")
    _logger.info(f"  - cities={target_cities}")
    _logger.info(f"  - relationship_goals={target_relationship_goals}")
    _logger.info(f"  - profile_statuses={profile_statuses}")

    # 逐步分析每个筛选条件的影响

    # Step 1: 查询所有候选人
    count_all = query_candidate_count(source, {}, "所有候选人")
    _logger.info(f"数据库总候选人数量: {count_all}")

    # Step 2: 查询女性候选人
    count_female = query_candidate_count(source, {"gender": target_gender}, "女性候选人")
    _logger.info(f"女性候选人占比: {count_female}/{count_all} ({count_female/count_all*100 if count_all > 0 else 0:.1f}%)")

    # Step 3: 查询无锡地区的候选人
    count_wuxi = query_candidate_count(source, {"city": target_cities}, "无锡地区候选人")
    _logger.info(f"无锡地区候选人占比: {count_wuxi}/{count_all} ({count_wuxi/count_all*100 if count_all > 0 else 0:.1f}%)")

    # Step 4: 查询无锡地区的女性候选人
    count_wuxi_female = query_candidate_count(
        source,
        {"gender": target_gender, "city": target_cities},
        "无锡地区女性候选人"
    )
    _logger.info(f"无锡地区女性候选人: {count_wuxi_female}")

    # Step 5: 查询关系目标为结婚导向的候选人
    count_marriage_goal = query_candidate_count(
        source,
        {"relationship_goal": target_relationship_goals},
        "结婚导向候选人"
    )
    _logger.info(f"结婚导向候选人占比: {count_marriage_goal}/{count_all} ({count_marriage_goal/count_all*100 if count_all > 0 else 0:.1f}%)")

    # Step 6: 查询满足所有硬约束条件的候选人（实际搜索结果）
    count_final = query_candidate_count(
        source,
        {
            "gender": target_gender,
            "city": target_cities,
            "relationship_goal": target_relationship_goals,
            "profile_status": profile_statuses,
        },
        "最终搜索结果（满足所有硬约束）"
    )
    _logger.info(f"最终搜索结果: {count_final}")

    # 排除用户自己
    if count_final > 0:
        count_final_exclude_self = query_candidate_count(
            source,
            {
                "gender": target_gender,
                "city": target_cities,
                "relationship_goal": target_relationship_goals,
                "profile_status": profile_statuses,
                "id": [10006],  # 排除用户自己（这里用NOT IN逻辑）
            },
            "排除用户自己后的结果"
        )
        # 注意：这里需要手动调整，因为id条件是排除，不是包含

    _logger.info("=" * 80)
    _logger.info("诊断总结")
    _logger.info("=" * 80)

    # 分析结果
    if count_all == 0:
        _logger.error("根本原因：数据库中没有任何候选人数据")
    elif count_female == 0:
        _logger.error("根本原因：数据库中没有女性候选人")
    elif count_wuxi == 0:
        _logger.error("根本原因：数据库中没有无锡地区的候选人")
    elif count_wuxi_female == 0:
        _logger.error("根本原因：无锡地区没有女性候选人")
    elif count_marriage_goal == 0:
        _logger.error("根本原因：数据库中没有关系目标为结婚导向的候选人")
    elif count_final == 0:
        _logger.error(f"根本原因：无锡地区女性且结婚导向的候选人数量为0")
        _logger.error(f"建议：放宽条件（例如：接受其他城市、接受认真恋爱等）")
    else:
        _logger.info(f"搜索应该有结果，但实际返回0，需要检查其他筛选条件")

    # 关闭数据源
    source.close()

    _logger.info("诊断完成")


if __name__ == "__main__":
    diagnose_search_zero_results()