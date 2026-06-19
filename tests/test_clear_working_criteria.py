"""测试 search_part 清空逻辑：会话结束后清空 working_criteria

验证 process_session_end 中是否正确清空 working_criteria。
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import asyncio


def test_clear_working_criteria_function_exists():
    """测试 clear_working_criteria 函数是否存在"""
    from match_domain.session_end_processor import clear_working_criteria

    assert callable(clear_working_criteria), "clear_working_criteria 函数不可调用"


def test_clear_working_criteria_in_process_session_end():
    """测试 process_session_end 是否调用 clear_working_criteria"""
    from match_domain.session_end_processor import process_session_end

    # 检查函数定义中是否包含 clear_working_criteria 调用
    import inspect
    source = inspect.getsource(process_session_end)

    assert "clear_working_criteria" in source, "process_session_end 中没有调用 clear_working_criteria"


def test_clear_working_criteria_in_all_exports():
    """测试 clear_working_criteria 是否在 __all__ 中导出"""
    from match_domain import session_end_processor

    assert "clear_working_criteria" in session_end_processor.__all__, "clear_working_criteria 未在 __all__ 中导出"


@pytest.mark.asyncio
async def test_clear_working_criteria_mock():
    """测试 clear_working_criteria 函数逻辑（Mock 版本）"""
    from match_domain.session_end_processor import clear_working_criteria

    # Mock 数据库连接
    mock_conn = MagicMock()
    mock_conn.execute = MagicMock()
    mock_conn.commit = MagicMock()
    mock_conn.rollback = MagicMock()
    mock_conn.close = MagicMock()

    # Mock 查询结果（包含 working_criteria）
    mock_row = {"session_state": '{"working_criteria": {"cities": ["北京"], "age_min": 26}}'}
    mock_conn.execute.return_value.fetchone.return_value = mock_row

    # Mock connect_db
    with patch("external_systems.partner_discovery_system.discovery_system.storage.connect_db", return_value=mock_conn):
        with patch.dict("os.environ", {"PARTNER_DISCOVERY_DB": "mysql://test"}):
            result = await clear_working_criteria("test_session_id")

            # 验证返回值
            assert result is True, "清空失败"

            # 验证数据库操作
            assert mock_conn.execute.call_count >= 2, "数据库操作次数不足"
            assert mock_conn.commit.called, "没有提交事务"


@pytest.mark.asyncio
async def test_clear_working_criteria_no_dsn():
    """测试 clear_working_criteria 在没有 DSN 时的行为"""
    from match_domain.session_end_processor import clear_working_criteria

    # 没有配置 DSN
    with patch.dict("os.environ", {}, clear=True):
        result = await clear_working_criteria("test_session_id")

        # 应该返回 False（失败）
        assert result is False, "没有 DSN 时应该返回 False"


@pytest.mark.asyncio
async def test_clear_working_criteria_session_not_found():
    """测试 clear_working_criteria 在 session 不存在时的行为"""
    from match_domain.session_end_processor import clear_working_criteria

    # Mock 数据库连接
    mock_conn = MagicMock()
    mock_conn.execute = MagicMock()
    mock_conn.rollback = MagicMock()
    mock_conn.close = MagicMock()

    # Mock 查询结果（session 不存在）
    mock_conn.execute.return_value.fetchone.return_value = None

    # Mock connect_db
    with patch("external_systems.partner_discovery_system.discovery_system.storage.connect_db", return_value=mock_conn):
        with patch.dict("os.environ", {"PARTNER_DISCOVERY_DB": "mysql://test"}):
            result = await clear_working_criteria("test_session_id")

            # 应该返回 False（失败）
            assert result is False, "session 不存在时应该返回 False"


@pytest.mark.asyncio
async def test_clear_working_criteria_no_working_criteria():
    """测试 clear_working_criteria 在没有 working_criteria 时的行为"""
    from match_domain.session_end_processor import clear_working_criteria

    # Mock 数据库连接
    mock_conn = MagicMock()
    mock_conn.execute = MagicMock()
    mock_conn.commit = MagicMock()
    mock_conn.close = MagicMock()

    # Mock 查询结果（没有 working_criteria）
    mock_row = {"session_state": '{"other_state": "value"}'}
    mock_conn.execute.return_value.fetchone.return_value = mock_row

    # Mock connect_db
    with patch("external_systems.partner_discovery_system.discovery_system.storage.connect_db", return_value=mock_conn):
        with patch.dict("os.environ", {"PARTNER_DISCOVERY_DB": "mysql://test"}):
            result = await clear_working_criteria("test_session_id")

            # 应该返回 True（无需清空）
            assert result is True, "没有 working_criteria 时应该返回 True"


if __name__ == "__main__":
    # 运行基本测试
    test_clear_working_criteria_function_exists()
    test_clear_working_criteria_in_process_session_end()
    test_clear_working_criteria_in_all_exports()

    print("✅ search_part 清空逻辑测试全部通过（基本测试）")

    # 运行异步测试（需要 pytest）
    print("\n提示：异步测试需要 pytest，请运行：pytest tests/test_clear_working_criteria.py -v")