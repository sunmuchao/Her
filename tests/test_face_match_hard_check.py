"""
活体视频认证前置人脸比对硬性检查 - 自动化测试

测试场景：
1. 第一次认证失败，照片更新成功自动认证通过
2. 照片更新失败（人脸不匹配）
3. 认证通过后，用户更新照片（一致）
4. 认证通过后，用户更新照片（不一致）

运行方法：
pytest tests/test_face_match_hard_check.py -v

注意：
- 这些测试需要真实的数据库连接和人脸识别服务
- 建议在测试环境中运行，避免影响生产数据
- 测试前需要准备测试数据和测试用户
"""

import pytest
from typing import Any, Dict
from unittest.mock import Mock, patch, MagicMock
import json

# 导入需要测试的函数
from profile_service.api import (
    update_profile_photos_with_face_check,
    get_verified_face_anchor,
)
from chat_system.verification import review_live_video_verification


# ============================================================
# 测试数据准备
# ============================================================

class TestDataContext:
    """测试数据上下文管理"""

    def __init__(self):
        self.test_profile_id = 99999
        self.test_source_dsn = "mysql://test:test@localhost/test_db"
        self.test_photos = [
            "http://minio.example.com/photo1.jpg",
            "http://minio.example.com/photo2.jpg",
        ]
        self.test_video_face_embedding = {
            "embedding_json": json.dumps([0.1, 0.2, 0.3, 0.4]),  # 模拟人脸向量
            "quality_score": 0.95,
        }

    def setup_test_user(self):
        """创建测试用户"""
        # TODO: 在测试数据库中创建测试用户
        pass

    def cleanup_test_user(self):
        """清理测试用户"""
        # TODO: 从测试数据库中删除测试用户
        pass


# ============================================================
# 场景1：第一次认证失败，照片更新成功自动认证通过
# ============================================================

class TestScenario1:
    """场景1：第一次认证拒绝 + 照片更新成功自动认证通过

    测试步骤：
    1. 用户上传照片A（别人的照片）
    2. 用户录活体视频（真人）
    3. 系统审核：人脸比对失败 → 认证拒绝（状态：rejected）
    4. 用户在个人资料页上传照片B（真实照片）
    5. 系统检查：照片B人脸 ≈ 视频真人 → 一致
    6. 照片B保存成功 + 自动认证通过（状态：approved）
    """

    @pytest.fixture
    def test_context(self):
        """测试上下文"""
        context = TestDataContext()
        context.setup_test_user()
        yield context
        context.cleanup_test_user()

    def test_step1_3_first_certification_reject(
        self,
        test_context: TestDataContext,
    ):
        """步骤1-3：第一次认证拒绝"""
        # Mock 人脸比对失败
        with patch('match_domain.face_embedding_extractor.compute_face_similarity') as mock_similarity:
            mock_similarity.return_value = 0.2  # 相似度 < 0.363，不匹配

            # 调用审核函数
            result = review_live_video_verification(
                verification_id="test_verification_001",
                reviewer_id="test_reviewer",
                decision="approve",  # 审核员尝试通过
            )

            # 验证：认证状态应为"rejected"
            assert result.get("verification_status") == "rejected"

            # 验证：返回错误信息
            assert "人脸比对失败" in result.get("error_message", "")

            # 验证：视频人脸向量已保存
            video_anchor = get_verified_face_anchor(
                source_dsn=test_context.test_source_dsn,
                profile_id=test_context.test_profile_id,
            )
            assert video_anchor is not None
            assert video_anchor.get("embedding_json") is not None

    def test_step4_6_photo_update_success_auto_approve(
        self,
        test_context: TestDataContext,
    ):
        """步骤4-6：照片更新成功自动认证通过"""
        # Mock 人脸比对成功
        with patch('match_domain.face_embedding_extractor.compute_face_similarity') as mock_similarity:
            mock_similarity.return_value = 0.85  # 相似度 > 0.363，匹配

            # Mock 视频人脸向量
            with patch('profile_service.api.get_verified_face_anchor') as mock_anchor:
                mock_anchor.return_value = test_context.test_video_face_embedding

                # 调用照片更新函数
                result = update_profile_photos_with_face_check(
                    source_dsn=test_context.test_source_dsn,
                    profile_id=test_context.test_profile_id,
                    new_photos=test_context.test_photos,
                    verification_status="rejected",  # 当前认证状态为rejected
                )

                # 验证：照片保存成功
                assert result.get("success") is True

                # 验证：自动认证通过
                assert result.get("verification_auto_approved") is True

                # 验证：相似度分数
                assert result.get("similarity_score") >= 0.363


# ============================================================
# 场景2：照片更新失败（人脸不匹配）
# ============================================================

class TestScenario2:
    """场景2：照片更新失败（人脸不匹配）

    测试步骤：
    1. 用户认证失败（状态：rejected）
    2. 用户上传照片B（别人的照片）
    3. 系统检查：照片B人脸 ≠ 视频真人 → 不一致
    4. 照片B保存失败
    """

    @pytest.fixture
    def test_context(self):
        """测试上下文"""
        context = TestDataContext()
        context.setup_test_user()
        yield context
        context.cleanup_test_user()

    def test_photo_update_reject_face_mismatch(
        self,
        test_context: TestDataContext,
    ):
        """照片更新失败（人脸不匹配）"""
        # Mock 人脸比对失败
        with patch('match_domain.face_embedding_extractor.compute_face_similarity') as mock_similarity:
            mock_similarity.return_value = 0.2  # 相似度 < 0.363，不匹配

            # Mock 视频人脸向量
            with patch('profile_service.api.get_verified_face_anchor') as mock_anchor:
                mock_anchor.return_value = test_context.test_video_face_embedding

                # 调用照片更新函数
                result = update_profile_photos_with_face_check(
                    source_dsn=test_context.test_source_dsn,
                    profile_id=test_context.test_profile_id,
                    new_photos=test_context.test_photos,
                    verification_status="rejected",
                )

                # 验证：照片保存失败
                assert result.get("success") is False

                # 验证：返回错误信息
                assert "不匹配" in result.get("error", "")

                # 验证：相似度分数
                assert result.get("similarity_score") < 0.363


# ============================================================
# 场景3：认证通过后，用户更新照片（一致）
# ============================================================

class TestScenario3:
    """场景3：认证通过后，用户更新照片（一致）

    测试步骤：
    1. 用户认证通过（状态：approved）
    2. 用户上传照片C（真实照片）
    3. 系统检查：照片C人脸 ≈ 视频真人 → 一致
    4. 照片C保存成功
    """

    @pytest.fixture
    def test_context(self):
        """测试上下文"""
        context = TestDataContext()
        context.setup_test_user()
        yield context
        context.cleanup_test_user()

    def test_certified_user_update_photo_match(
        self,
        test_context: TestDataContext,
    ):
        """认证通过后更新照片（一致）"""
        # Mock 人脸比对成功
        with patch('match_domain.face_embedding_extractor.compute_face_similarity') as mock_similarity:
            mock_similarity.return_value = 0.9  # 相似度 > 0.363，匹配

            # Mock 视频人脸向量
            with patch('profile_service.api.get_verified_face_anchor') as mock_anchor:
                mock_anchor.return_value = test_context.test_video_face_embedding

                # 调用照片更新函数
                result = update_profile_photos_with_face_check(
                    source_dsn=test_context.test_source_dsn,
                    profile_id=test_context.test_profile_id,
                    new_photos=test_context.test_photos,
                    verification_status="approved",  # 当前认证状态为approved
                )

                # 验证：照片保存成功
                assert result.get("success") is True

                # 验证：不会自动认证通过（因为已经通过）
                assert result.get("verification_auto_approved") is False

                # 验证：相似度分数
                assert result.get("similarity_score") >= 0.363


# ============================================================
# 场景4：认证通过后，用户更新照片（不一致）
# ============================================================

class TestScenario4:
    """场景4：认证通过后，用户更新照片（不一致）

    测试步骤：
    1. 用户认证通过（状态：approved）
    2. 用户上传照片D（别人的照片）
    3. 系统检查：照片D人脸 ≠ 视频真人 → 不一致
    4. 照片D保存失败
    """

    @pytest.fixture
    def test_context(self):
        """测试上下文"""
        context = TestDataContext()
        context.setup_test_user()
        yield context
        context.cleanup_test_user()

    def test_certified_user_update_photo_mismatch(
        self,
        test_context: TestDataContext,
    ):
        """认证通过后更新照片（不一致）"""
        # Mock 人脸比对失败
        with patch('match_domain.face_embedding_extractor.compute_face_similarity') as mock_similarity:
            mock_similarity.return_value = 0.15  # 相似度 < 0.363，不匹配

            # Mock 视频人脸向量
            with patch('profile_service.api.get_verified_face_anchor') as mock_anchor:
                mock_anchor.return_value = test_context.test_video_face_embedding

                # 调用照片更新函数
                result = update_profile_photos_with_face_check(
                    source_dsn=test_context.test_source_dsn,
                    profile_id=test_context.test_profile_id,
                    new_photos=test_context.test_photos,
                    verification_status="approved",
                )

                # 验证：照片保存失败
                assert result.get("success") is False

                # 验证：返回错误信息
                assert "不匹配" in result.get("error", "")

                # 验证：相似度分数
                assert result.get("similarity_score") < 0.363


# ============================================================
# 边缘场景测试
# ============================================================

class TestEdgeCases:
    """边缘场景测试"""

    def test_no_video_anchor_skip_check(self):
        """没有视频人脸向量时跳过检查"""
        # Mock 没有视频人脸向量
        with patch('profile_service.api.get_verified_face_anchor') as mock_anchor:
            mock_anchor.return_value = None  # 没有视频人脸向量

            # 调用照片更新函数
            result = update_profile_photos_with_face_check(
                source_dsn="mysql://test:test@localhost/test_db",
                profile_id=99999,
                new_photos=["http://minio.example.com/photo1.jpg"],
            )

            # 验证：照片保存成功（跳过检查）
            assert result.get("success") is True

            # 验证：相似度分数为0
            assert result.get("similarity_score") == 0.0

    def test_max_photos_limit(self):
        """照片数量超过限制"""
        # 尝试上传7张照片
        photos = [f"http://minio.example.com/photo{i}.jpg" for i in range(7)]

        # Mock 视频人脸向量
        with patch('profile_service.api.get_verified_face_anchor') as mock_anchor:
            mock_anchor.return_value = {"embedding_json": json.dumps([0.1, 0.2, 0.3])}

            # 调用照片更新函数
            result = update_profile_photos_with_face_check(
                source_dsn="mysql://test:test@localhost/test_db",
                profile_id=99999,
                new_photos=photos,
            )

            # 验证：应该截断到6张照片
            assert result.get("photos_count") <= 6

    def test_invalid_profile_id(self):
        """无效的profile_id"""
        # 尝试使用无效的profile_id
        with pytest.raises(ValueError):
            update_profile_photos_with_face_check(
                source_dsn="mysql://test:test@localhost/test_db",
                profile_id=0,  # 无效profile_id
                new_photos=["http://minio.example.com/photo1.jpg"],
            )

    def test_empty_photos_list(self):
        """空照片列表"""
        # 尝试上传空照片列表
        with pytest.raises(ValueError):
            update_profile_photos_with_face_check(
                source_dsn="mysql://test:test@localhost/test_db",
                profile_id=99999,
                new_photos=[],  # 空照片列表
            )


# ============================================================
# 运行说明
# ============================================================

if __name__ == "__main__":
    """
    运行测试：

    1. 运行所有测试：
       pytest tests/test_face_match_hard_check.py -v

    2. 运行特定场景：
       pytest tests/test_face_match_hard_check.py::TestScenario1 -v

    3. 运行特定测试：
       pytest tests/test_face_match_hard_check.py::TestScenario1::test_step1_3_first_certification_reject -v

    注意：
    - 这些测试使用了Mock，不会真实调用数据库和人脸识别服务
    - 如果需要真实测试，需要准备测试数据库和测试数据
    - 建议在CI/CD流程中运行这些测试
    """
    pytest.main([__file__, "-v"])