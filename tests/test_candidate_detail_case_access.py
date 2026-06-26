"""测试 caseId 访问候选人详情的修复

测试场景：
1. 从关系页访问候选人详情（通过 caseId）- 应该成功
2. 从发现页访问候选人详情（通过 sessionId）- 应该继续工作
3. 无任何凭证访问候选人详情 - 应该返回 403

运行方法：
python tests/test_candidate_detail_case_access.py
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch
from gateway.bff.candidate_detail import rest_candidate_detail, _check_candidate_access_via_case
from gateway.input_validator import ValidationError


def test_case_access_check():
    """测试 caseId 访问检查逻辑"""
    print("\n=== 测试 caseId 访问检查 ===")

    # Mock gateway
    gateway = MagicMock()

    # Mock environ
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/v1/candidates/123",
    }

    # Mock actor
    actor = MagicMock()
    actor.actor_id = "user_001"
    actor.has_any_role.return_value = False

    gateway._current_actor.return_value = actor
    gateway._is_auth_session_end_user.return_value = True

    # Test case 1: 用户是 case 的参与者
    print("\n场景 1: 用户是 case 的参与者")
    case_data = {
        "candidate_id": 123,
        "requester_id": 456,
    }
    gateway._get_case_for_actor.return_value = case_data

    result = _check_candidate_access_via_case(gateway, environ, 123, "case_001")
    print(f"  访问候选人 123: {result} (预期: True)")
    assert result == True, "应该允许访问"

    # Test case 2: 用户不是 case 的参与者
    print("\n场景 2: 用户不是 case 的参与者")
    case_data = {
        "candidate_id": 789,  # 不同的候选人
        "requester_id": 456,
    }
    gateway._get_case_for_actor.return_value = case_data

    result = _check_candidate_access_via_case(gateway, environ, 123, "case_002")
    print(f"  访问候选人 123: {result} (预期: False)")
    assert result == False, "应该拒绝访问"

    # Test case 3: 异常情况（如 case 不存在）
    print("\n场景 3: case 不存在或无权限访问")
    gateway._get_case_for_actor.side_effect = Exception("Case not found")

    result = _check_candidate_access_via_case(gateway, environ, 123, "case_003")
    print(f"  访问候选人 123: {result} (预期: False)")
    assert result == False, "异常时应该返回 False"

    print("\n✓ caseId 访问检查逻辑测试通过")


def test_rest_candidate_detail_with_case_id():
    """测试 rest_candidate_detail 函数接受 caseId 参数"""
    print("\n=== 测试 rest_candidate_detail 接受 caseId ===")

    # Mock gateway
    gateway = MagicMock()

    # Mock environ with case_id query parameter
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/v1/candidates/123",
        "QUERY_STRING": "case_id=case_001",
    }

    # Mock actor
    actor = MagicMock()
    actor.actor_id = "user_001"
    actor.has_any_role.return_value = False

    gateway._current_actor.return_value = actor
    gateway._is_auth_session_end_user.return_value = True

    # Mock case data
    case_data = {
        "candidate_id": 123,
        "requester_id": 456,
    }
    gateway._get_case_for_actor.return_value = case_data

    # Mock profile data
    profile_row = {
        "profile_id": 123,
        "display_name": "Test User",
        "age": 30,
        "city": "上海",
    }

    # Mock dependencies
    with patch('gateway.bff.candidate_detail.default_profile_source') as mock_source, \
         patch('gateway.bff.candidate_detail.get_profile') as mock_get_profile, \
         patch('gateway.bff.candidate_detail.build_trust_summary') as mock_trust, \
         patch('gateway.bff.candidate_detail.extract_profile_facts') as mock_facts:

        mock_source.return_value = ("dsn", "table")
        mock_get_profile.return_value = profile_row
        mock_trust.return_value = MagicMock(to_dict=lambda: {})
        mock_facts.return_value = {}

        status, response = rest_candidate_detail(gateway, environ, "123")

        print(f"  状态码: {status} (预期: 200)")
        print(f"  响应: {response}")

        assert status == 200, "应该成功返回 200"
        assert response.get("candidate_id") == 123, "应该返回正确的 candidate_id"
        assert response.get("access_method") == "case", "应该标记访问方式为 case"

    print("\n✓ rest_candidate_detail caseId 参数测试通过")


def test_rest_candidate_detail_without_credentials():
    """测试无凭证访问候选人详情应该返回 403"""
    print("\n=== 测试无凭证访问候选人详情 ===")

    # Mock gateway
    gateway = MagicMock()

    # Mock environ without any credentials
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/v1/candidates/123",
        "QUERY_STRING": "",  # 无 session_id, recommendation_id, case_id
    }

    # Mock actor
    actor = MagicMock()
    actor.actor_id = "user_001"
    actor.has_any_role.return_value = False

    gateway._current_actor.return_value = actor

    status, response = rest_candidate_detail(gateway, environ, "123")

    print(f"  状态码: {status} (预期: 403)")
    print(f"  错误信息: {response.get('error', {}).get('message')}")

    assert status == 403, "应该返回 403 Forbidden"
    assert response.get("error", {}).get("code") == "forbidden", "错误代码应该是 forbidden"

    print("\n✓ 无凭证访问测试通过")


def test_rest_candidate_detail_with_session_id():
    """测试通过 sessionId 访问候选人详情应该继续工作"""
    print("\n=== 测试通过 sessionId 访问 ===")

    # Mock gateway
    gateway = MagicMock()

    # Mock environ with session_id
    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": "/v1/candidates/123",
        "QUERY_STRING": "session_id=session_001",
    }

    # Mock actor
    actor = MagicMock()
    actor.actor_id = "user_001"
    actor.has_any_role.return_value = False

    gateway._current_actor.return_value = actor
    gateway._is_auth_session_end_user.return_value = True

    # Mock discovery system
    gateway._discovery = MagicMock()
    gateway._discovery.get_session_owner_id.return_value = 456  # user's profile_id
    gateway._discovery.get_session_view.return_value = {
        "view": {
            "candidates": [{"profile_id": 123}],
            "timeline": [],
        }
    }

    # Mock resolved principal
    resolved_principal = MagicMock()
    resolved_principal.profile_id = 456
    gateway._resolve_end_user_principal.return_value = resolved_principal

    # Mock profile data
    profile_row = {
        "profile_id": 123,
        "display_name": "Test User",
        "age": 30,
        "city": "上海",
    }

    with patch('gateway.bff.candidate_detail.default_profile_source') as mock_source, \
         patch('gateway.bff.candidate_detail.get_profile') as mock_get_profile, \
         patch('gateway.bff.candidate_detail.build_trust_summary') as mock_trust, \
         patch('gateway.bff.candidate_detail.extract_profile_facts') as mock_facts:

        mock_source.return_value = ("dsn", "table")
        mock_get_profile.return_value = profile_row
        mock_trust.return_value = MagicMock(to_dict=lambda: {})
        mock_facts.return_value = {}

        status, response = rest_candidate_detail(gateway, environ, "123")

        print(f"  状态码: {status} (预期: 200)")
        print(f"  访问方式: {response.get('access_method')} (预期: session)")

        assert status == 200, "应该成功返回 200"
        assert response.get("access_method") == "session", "应该标记访问方式为 session"

    print("\n✓ sessionId 访问测试通过")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("候选人详情 caseId 访问修复验证测试")
    print("=" * 60)

    try:
        test_case_access_check()
        test_rest_candidate_detail_with_case_id()
        test_rest_candidate_detail_without_credentials()
        test_rest_candidate_detail_with_session_id()

        print("\n" + "=" * 60)
        print("✓ 所有测试通过！修复验证成功")
        print("=" * 60)

    except AssertionError as e:
        print("\n" + "=" * 60)
        print(f"✗ 测试失败: {e}")
        print("=" * 60)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())