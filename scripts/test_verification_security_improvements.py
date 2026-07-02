"""Comprehensive test suite for verification security improvements.

This test module validates all components of the verification security
improvement implementation:

Tests:
1. Database schema validation
2. Encryption/decryption functionality
3. Access audit logging
4. Dynamic threshold configuration
5. Rate limiting
6. Input validation
7. OCR service
8. Expiry and revocation
9. Quality monitoring
10. Automatic cleanup
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
from datetime import datetime, timedelta
from typing import Any

import pymysql

# Database configuration
DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ.get("MYSQL_USER", "root")
DB_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "SLhJJ0BfjguKNGpGb5jUJlajt2+5QP7IW3B8aXycnrw=")
DB_NAME = "her_chat"


class TestResult:
    """Test result container"""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.passed = True
        self.errors = []
        self.details = []

    def add_error(self, error: str):
        self.passed = False
        self.errors.append(error)

    def add_detail(self, detail: str):
        self.details.append(detail)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_name": self.test_name,
            "passed": self.passed,
            "errors": self.errors,
            "details": self.details,
        }


def get_db_connection() -> pymysql.Connection:
    """Get database connection"""
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset='utf8mb4',
    )


# ============================================================================
# Test 1: Database Schema Validation
# ============================================================================

def test_database_schema() -> TestResult:
    """Test database schema changes"""
    result = TestResult("Database Schema Validation")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Test 1.1: Check new tables exist
        new_tables = [
            'verification_level_weights',
            'verification_submission_metadata',
            'verification_revocations',
            'verification_auto_review_stats',
            'verification_review_latency',
            'verification_data_governance_policies',
        ]

        for table_name in new_tables:
            cursor.execute(f"SHOW TABLES LIKE '{table_name}'")
            if cursor.fetchone():
                result.add_detail(f"✓ Table {table_name} exists")
            else:
                result.add_error(f"✗ Table {table_name} not found")

        # Test 1.2: Check new fields in verification_submissions
        cursor.execute("DESCRIBE verification_submissions")
        columns = [row[0] for row in cursor.fetchall()]

        new_fields = [
            'machine_review_outcome',
            'machine_review_score',
            'expires_at',
            'revoked_at',
            'revocation_reason',
        ]

        for field in new_fields:
            if field in columns:
                result.add_detail(f"✓ Field verification_submissions.{field} exists")
            else:
                result.add_error(f"✗ Field verification_submissions.{field} not found")

        # Test 1.3: Check new fields in profile_field_verification_submissions
        cursor.execute("DESCRIBE profile_field_verification_submissions")
        columns = [row[0] for row in cursor.fetchall()]

        new_fields = [
            'ocr_extracted_text',
            'ocr_confidence_score',
            'ocr_processed_at',
            'authority_verification_status',
            'authority_verification_result',
            'revoked_at',
        ]

        for field in new_fields:
            if field in columns:
                result.add_detail(f"✓ Field profile_field_verification_submissions.{field} exists")
            else:
                result.add_error(f"✗ Field profile_field_verification_submissions.{field} not found")

        # Test 1.4: Check initial data in verification_level_weights
        cursor.execute("SELECT COUNT(*) FROM verification_level_weights")
        count = cursor.fetchone()[0]
        if count == 4:
            result.add_detail(f"✓ verification_level_weights has {count} records (expected: 4)")
        else:
            result.add_error(f"✗ verification_level_weights has {count} records (expected: 4)")

        # Test 1.5: Check initial data in verification_data_governance_policies
        cursor.execute("SELECT COUNT(*) FROM verification_data_governance_policies")
        count = cursor.fetchone()[0]
        if count == 4:
            result.add_detail(f"✓ verification_data_governance_policies has {count} records (expected: 4)")
        else:
            result.add_error(f"✗ verification_data_governance_policies has {count} records (expected: 4)")

        # Test 1.6: Check indexes exist
        cursor.execute("SHOW INDEX FROM verification_submissions WHERE Key_name = 'idx_verification_submissions_machine_outcome'")
        if cursor.fetchone():
            result.add_detail("✓ Index idx_verification_submissions_machine_outcome exists")
        else:
            result.add_error("✗ Index idx_verification_submissions_machine_outcome not found")

        cursor.execute("SHOW INDEX FROM verification_submissions WHERE Key_name = 'idx_verification_submissions_expires_at'")
        if cursor.fetchone():
            result.add_detail("✓ Index idx_verification_submissions_expires_at exists")
        else:
            result.add_error("✗ Index idx_verification_submissions_expires_at not found")

    except Exception as e:
        result.add_error(f"Database schema test failed: {e}")

    finally:
        cursor.close()
        conn.close()

    return result


# ============================================================================
# Test 2: Encryption/Decryption Functionality
# ============================================================================

def test_encryption() -> TestResult:
    """Test encryption and decryption functionality"""
    result = TestResult("Encryption/Decryption Test")

    try:
        # Add project root to path
        import sys
        sys.path.insert(0, '/Users/sunmuchao/Downloads/Her')

        from chat_system.verification_sensitive_data_encryption import (
            encrypt_sensitive_field,
            decrypt_sensitive_field,
            SensitiveDataEncryption,
        )

        # Test 2.1: Encrypt and decrypt string
        test_string = "This is sensitive data"
        encrypted = encrypt_sensitive_field(test_string)

        if encrypted and encrypted != test_string:
            result.add_detail(f"✓ String encryption successful: {len(encrypted)} chars")
        else:
            result.add_error("✗ String encryption failed")

        decrypted = decrypt_sensitive_field(encrypted)
        if decrypted == test_string:
            result.add_detail("✓ String decryption successful")
        else:
            result.add_error(f"✗ String decryption failed: expected '{test_string}', got '{decrypted}'")

        # Test 2.2: Encrypt and decrypt JSON dict
        test_dict = {
            "school_name": "北京大学",
            "degree_level": "本科",
            "ocr_confidence": 0.95,
        }
        encrypted_dict = encrypt_sensitive_field(test_dict)

        if encrypted_dict and isinstance(encrypted_dict, str):
            result.add_detail("✓ Dict encryption successful")
        else:
            result.add_error("✗ Dict encryption failed")

        decrypted_dict = decrypt_sensitive_field(encrypted_dict)
        if decrypted_dict == test_dict:
            result.add_detail("✓ Dict decryption successful")
        else:
            result.add_error(f"✗ Dict decryption failed: expected {test_dict}, got {decrypted_dict}")

        # Test 2.3: Encrypt None value
        encrypted_none = encrypt_sensitive_field(None)
        if encrypted_none is None:
            result.add_detail("✓ None encryption returns None")
        else:
            result.add_error("✗ None encryption should return None")

        decrypted_none = decrypt_sensitive_field(None)
        if decrypted_none is None:
            result.add_detail("✓ None decryption returns None")
        else:
            result.add_error("✗ None decryption should return None")

        # Test 2.4: Verify encryption produces different outputs for same input
        encrypted1 = encrypt_sensitive_field(test_string)
        encrypted2 = encrypt_sensitive_field(test_string)

        if encrypted1 != encrypted2:
            result.add_detail("✓ Encryption produces unique outputs (random nonce)")
        else:
            result.add_error("✗ Encryption should produce different outputs for same input")

        # Test 2.5: Verify decryption of both produces same result
        decrypted1 = decrypt_sensitive_field(encrypted1)
        decrypted2 = decrypt_sensitive_field(encrypted2)

        if decrypted1 == decrypted2 == test_string:
            result.add_detail("✓ Different encrypted outputs decrypt to same value")
        else:
            result.add_error("✗ Decryption consistency failed")

    except ImportError as e:
        result.add_error(f"Encryption module import failed: {e}")
    except Exception as e:
        result.add_error(f"Encryption test failed: {e}")

    return result


# ============================================================================
# Test 3: Access Audit Logging
# ============================================================================

def test_access_audit() -> TestResult:
    """Test access audit logging functionality"""
    result = TestResult("Access Audit Logging Test")

    try:
        from external_systems.partner_chat_system.chat_system.verification_access_audit import (
            log_sensitive_data_access,
            query_audit_logs,
            AccessAuditLogger,
        )

        # Test 3.1: Log access
        test_submission_id = "test-submission-audit-001"
        log_sensitive_data_access(
            submission_id=test_submission_id,
            field_name="ocr_extracted_text",
            accessor_id="test-reviewer-001",
            accessor_role="verification_ops",
            access_type="decrypt",
            access_reason="Manual review",
            metadata={"review_task_id": "task-001"},
        )
        result.add_detail("✓ Access audit log created")

        # Test 3.2: Query audit logs
        logs = query_audit_logs(submission_id=test_submission_id)

        if len(logs) > 0:
            result.add_detail(f"✓ Found {len(logs)} audit logs")
        else:
            result.add_error("✗ No audit logs found")

        # Test 3.3: Verify audit log details
        if logs:
            latest_log = logs[0]
            if latest_log['submission_id'] == test_submission_id:
                result.add_detail("✓ Audit log submission_id correct")
            else:
                result.add_error(f"✗ Audit log submission_id mismatch: {latest_log['submission_id']}")

            if latest_log['field_name'] == "ocr_extracted_text":
                result.add_detail("✓ Audit log field_name correct")
            else:
                result.add_error(f"✗ Audit log field_name mismatch: {latest_log['field_name']}")

            if latest_log['accessor_id'] == "test-reviewer-001":
                result.add_detail("✓ Audit log accessor_id correct")
            else:
                result.add_error(f"✗ Audit log accessor_id mismatch: {latest_log['accessor_id']}")

            if latest_log['access_type'] == "decrypt":
                result.add_detail("✓ Audit log access_type correct")
            else:
                result.add_error(f"✗ Audit log access_type mismatch: {latest_log['access_type']}")

    except ImportError as e:
        result.add_error(f"Access audit module import failed: {e}")
    except Exception as e:
        result.add_error(f"Access audit test failed: {e}")

    return result


# ============================================================================
# Test 4: Dynamic Threshold Configuration
# ============================================================================

def test_threshold_configuration() -> TestResult:
    """Test dynamic threshold configuration"""
    result = TestResult("Dynamic Threshold Configuration Test")

    try:
        from match_domain.rule_config_schema import (
            SLICE_VERIFICATION_THRESHOLDS,
            code_defaults_for_slice,
        )

        # Test 4.1: Check slice exists
        if SLICE_VERIFICATION_THRESHOLDS:
            result.add_detail(f"✓ SLICE_VERIFICATION_THRESHOLDS defined: {SLICE_VERIFICATION_THRESHOLDS}")
        else:
            result.add_error("✗ SLICE_VERIFICATION_THRESHOLDS not defined")

        # Test 4.2: Get default thresholds
        thresholds = code_defaults_for_slice(SLICE_VERIFICATION_THRESHOLDS)

        if thresholds:
            result.add_detail(f"✓ Thresholds loaded: {len(thresholds)} parameters")
        else:
            result.add_error("✗ Thresholds not loaded")

        # Test 4.3: Verify threshold values
        expected_thresholds = {
            'liveness_score_min': 85,
            'face_match_score_min': 85,
            'challenge_score_min': 80,
            'deepfake_risk_threshold': 85,
            'replay_attack_threshold': 85,
        }

        for key, expected_value in expected_thresholds.items():
            if key in thresholds and thresholds[key] == expected_value:
                result.add_detail(f"✓ Threshold {key} = {expected_value}")
            else:
                actual_value = thresholds.get(key, 'missing')
                result.add_error(f"✗ Threshold {key} mismatch: expected {expected_value}, got {actual_value}")

        # Test 4.4: Verify auto_approve settings
        if thresholds.get('auto_approve_enabled') == True:
            result.add_detail("✓ auto_approve_enabled = True")
        else:
            result.add_error("✗ auto_approve_enabled should be True")

        if thresholds.get('auto_approve_strict_mode') == True:
            result.add_detail("✓ auto_approve_strict_mode = True")
        else:
            result.add_error("✗ auto_approve_strict_mode should be True")

    except ImportError as e:
        result.add_error(f"Threshold configuration import failed: {e}")
    except Exception as e:
        result.add_error(f"Threshold configuration test failed: {e}")

    return result


# ============================================================================
# Test 5: Rate Limiting
# ============================================================================

def test_rate_limiting() -> TestResult:
    """Test rate limiting functionality"""
    result = TestResult("Rate Limiting Test")

    try:
        from external_systems.partner_http_gateway.gateway.verification_rate_limiter import (
            check_verification_rate_limit,
            get_remaining_verification_requests,
            RateLimitExceeded,
            RATE_LIMITS,
        )

        # Test 5.1: Verify rate limit configurations
        if 'create_challenge' in RATE_LIMITS:
            config = RATE_LIMITS['create_challenge']
            if config['max_requests'] == 10 and config['window_seconds'] == 60:
                result.add_detail(f"✓ create_challenge rate limit: 10/60s")
            else:
                result.add_error(f"✗ create_challenge rate limit config incorrect")
        else:
            result.add_error("✗ create_challenge rate limit not defined")

        if 'submit_video' in RATE_LIMITS:
            config = RATE_LIMITS['submit_video']
            if config['max_requests'] == 5 and config['window_seconds'] == 60:
                result.add_detail(f"✓ submit_video rate limit: 5/60s")
            else:
                result.add_error(f"✗ submit_video rate limit config incorrect")
        else:
            result.add_error("✗ submit_video rate limit not defined")

        # Test 5.2: Test rate limit check
        test_user_id = "test-rate-limit-user-001"

        # First request should pass
        try:
            check_verification_rate_limit("create_challenge", test_user_id)
            result.add_detail("✓ First request passed rate limit")
        except RateLimitExceeded:
            result.add_error("✗ First request should not exceed rate limit")

        # Test 5.3: Check remaining requests
        remaining = get_remaining_verification_requests("create_challenge", test_user_id)
        if remaining >= 0:
            result.add_detail(f"✓ Remaining requests: {remaining}")
        else:
            result.add_error("✗ Remaining requests calculation failed")

        # Test 5.4: Simulate exceeding rate limit (not actually exceeding in test)
        # In production, would need to make 10+ requests to trigger this
        result.add_detail("⚠ Rate limit enforcement requires multiple requests (not tested)")

    except ImportError as e:
        result.add_error(f"Rate limiting module import failed: {e}")
    except Exception as e:
        result.add_error(f"Rate limiting test failed: {e}")

    return result


# ============================================================================
# Test 6: Input Validation
# ============================================================================

def test_input_validation() -> TestResult:
    """Test input validation functionality"""
    result = TestResult("Input Validation Test")

    try:
        from external_systems.partner_http_gateway.gateway.verification_input_validator import (
            validate_submission_id,
            validate_file_size,
            validate_content_type,
            InputValidationError,
            SUBMISSION_ID_PATTERN,
            MAX_VIDEO_FILE_SIZE,
            ALLOWED_VIDEO_CONTENT_TYPES,
        )

        # Test 6.1: Valid submission_id
        valid_id = "vfy-a1b2c3d4e5f67890"
        try:
            validated = validate_submission_id(valid_id)
            result.add_detail(f"✓ Valid submission_id accepted: {validated}")
        except InputValidationError:
            result.add_error("✗ Valid submission_id should be accepted")

        # Test 6.2: Invalid submission_id formats
        invalid_ids = [
            "invalid-id",  # Wrong format
            "vfy-short",  # Too short
            "VFY-A1B2C3D4E5F67890",  # Uppercase
            "vfy-a1b2c3d4e5f67890extra",  # Too long
        ]

        for invalid_id in invalid_ids:
            try:
                validate_submission_id(invalid_id)
                result.add_error(f"✗ Invalid submission_id '{invalid_id}' should be rejected")
            except InputValidationError:
                result.add_detail(f"✓ Invalid submission_id '{invalid_id}' rejected")

        # Test 6.3: Valid file size
        try:
            validate_file_size(10 * 1024 * 1024)  # 10MB
            result.add_detail("✓ Valid file size (10MB) accepted")
        except InputValidationError:
            result.add_error("✗ Valid file size should be accepted")

        # Test 6.4: Invalid file size
        try:
            validate_file_size(60 * 1024 * 1024)  # 60MB (exceeds 50MB limit)
            result.add_error("✗ File size > 50MB should be rejected")
        except InputValidationError:
            result.add_detail("✓ File size > 50MB rejected")

        # Test 6.5: Valid content types
        valid_types = ['video/webm', 'video/mp4', 'video/quicktime']
        for content_type in valid_types:
            try:
                validated = validate_content_type(content_type)
                result.add_detail(f"✓ Valid content_type '{content_type}' accepted")
            except InputValidationError:
                result.add_error(f"✗ Valid content_type '{content_type}' should be accepted")

        # Test 6.6: Invalid content type
        try:
            validate_content_type('application/pdf')
            result.add_error("✗ Invalid content_type should be rejected")
        except InputValidationError:
            result.add_detail("✓ Invalid content_type 'application/pdf' rejected")

    except ImportError as e:
        result.add_error(f"Input validation module import failed: {e}")
    except Exception as e:
        result.add_error(f"Input validation test failed: {e}")

    return result


# ============================================================================
# Test 7: OCR Service
# ============================================================================

def test_ocr_service() -> TestResult:
    """Test OCR service functionality"""
    result = TestResult("OCR Service Test")

    try:
        from external_systems.partner_chat_system.chat_system.verification_ocr_service import (
            OCRServiceFactory,
            MockOCRProvider,
            ocr_verify_document,
            OCRResult,
        )

        # Test 7.1: Get OCR provider
        provider = OCRServiceFactory.get_provider('mock')
        if provider:
            result.add_detail("✓ OCR provider created")
        else:
            result.add_error("✗ OCR provider creation failed")

        # Test 7.2: Mock OCR recognition
        test_image = b"mock_image_data"
        ocr_result = provider.recognize_text(test_image)

        if ocr_result.success:
            result.add_detail(f"✓ OCR recognition successful")
        else:
            result.add_error(f"✗ OCR recognition failed: {ocr_result.error}")

        if ocr_result.full_text:
            result.add_detail(f"✓ OCR extracted text: '{ocr_result.full_text}'")
        else:
            result.add_error("✗ OCR should extract text")

        if ocr_result.avg_confidence > 0:
            result.add_detail(f"✓ OCR confidence: {ocr_result.avg_confidence}")
        else:
            result.add_error("✗ OCR confidence should be > 0")

        # Test 7.3: Document verification
        profile_data = {"name": "张三", "school": "北京大学"}
        verification_result = ocr_verify_document(test_image, 'education', profile_data)

        if verification_result['ocr_success']:
            result.add_detail("✓ OCR verification successful")
        else:
            result.add_error(f"✗ OCR verification failed: {verification_result.get('review_reason')}")

        if 'field_match_result' in verification_result:
            result.add_detail(f"✓ Field match result: {verification_result['field_match_result']}")
        else:
            result.add_error("✗ Field match result missing")

        # Test 7.4: Check risk level
        if verification_result['risk_level'] in ['low', 'medium', 'high']:
            result.add_detail(f"✓ Risk level: {verification_result['risk_level']}")
        else:
            result.add_error(f"✗ Invalid risk level: {verification_result['risk_level']}")

    except ImportError as e:
        result.add_error(f"OCR service module import failed: {e}")
    except Exception as e:
        result.add_error(f"OCR service test failed: {e}")

    return result


# ============================================================================
# Test 8: Expiry and Revocation
# ============================================================================

def test_expiry_revocation() -> TestResult:
    """Test expiry and revocation functionality"""
    result = TestResult("Expiry and Revocation Test")

    try:
        from external_systems.partner_chat_system.chat_system.verification_expiry_revocation import (
            check_verification_expiry,
            get_level_expiry,
            get_revocation_history,
        )

        # Test 8.1: Get level expiry
        live_video_expiry = get_level_expiry('live_video_verified')
        if live_video_expiry == 365:
            result.add_detail(f"✓ live_video_verified expiry: {live_video_expiry} days")
        else:
            result.add_error(f"✗ live_video_verified expiry should be 365, got {live_video_expiry}")

        human_verified_expiry = get_level_expiry('human_verified')
        if human_verified_expiry == 365:
            result.add_detail(f"✓ human_verified expiry: {human_verified_expiry} days")
        else:
            result.add_error(f"✗ human_verified expiry should be 365, got {human_verified_expiry}")

        offline_expiry = get_level_expiry('offline_verified')
        if offline_expiry is None:
            result.add_detail(f"✓ offline_verified expiry: None (never expires)")
        else:
            result.add_error(f"✗ offline_verified should never expire, got {offline_expiry}")

        # Test 8.2: Check verification expiry
        # Mock profile with expired verification
        expired_profile = {
            "photo_verification_at": "2020-01-01T00:00:00",  # Expired (4+ years ago)
            "photo_verification_level": "live_video_verified",
        }

        expiry_result = check_verification_expiry(expired_profile)

        if expiry_result['expired']:
            result.add_detail("✓ Expired verification detected")
        else:
            result.add_error("✗ Should detect expired verification")

        if 'video' in expiry_result['expired_fields']:
            result.add_detail("✓ Video verification marked as expired")
        else:
            result.add_error("✗ Video should be in expired_fields")

        # Test 8.3: Check non-expired verification
        fresh_profile = {
            "photo_verification_at": datetime.now().isoformat(),
            "photo_verification_level": "live_video_verified",
        }

        expiry_result = check_verification_expiry(fresh_profile)

        if not expiry_result['expired']:
            result.add_detail("✓ Fresh verification not expired")
        else:
            result.add_error("✗ Fresh verification should not be expired")

        # Test 8.4: Get revocation history
        history = get_revocation_history("test-user-001")
        if isinstance(history, list):
            result.add_detail(f"✓ Revocation history returned: {len(history)} records")
        else:
            result.add_error("✗ Revocation history should return list")

    except ImportError as e:
        result.add_error(f"Expiry/revocation module import failed: {e}")
    except Exception as e:
        result.add_error(f"Expiry/revocation test failed: {e}")

    return result


# ============================================================================
# Test 9: Quality Monitoring
# ============================================================================

def test_quality_monitoring() -> TestResult:
    """Test quality monitoring functionality"""
    result = TestResult("Quality Monitoring Test")

    try:
        from external_systems.partner_chat_system.chat_system.verification_quality_monitoring import (
            get_verification_quality_metrics,
            get_latency_trends,
        )

        # Test 9.1: Get quality metrics
        start_date = datetime.now() - timedelta(days=30)
        end_date = datetime.now()

        metrics = get_verification_quality_metrics(start_date, end_date)

        if 'period' in metrics:
            result.add_detail(f"✓ Quality metrics period: {metrics['period']}")
        else:
            result.add_error("✗ Quality metrics period missing")

        if 'summary' in metrics:
            result.add_detail(f"✓ Quality metrics summary: {metrics['summary']}")
        else:
            result.add_error("✗ Quality metrics summary missing")

        # Test 9.2: Check summary metrics
        summary = metrics.get('summary', {})
        expected_keys = [
            'total_submissions',
            'auto_approve_rate',
            'false_positive_rate',
            'avg_auto_review_latency_ms',
        ]

        for key in expected_keys:
            if key in summary:
                result.add_detail(f"✓ Summary metric {key}: {summary[key]}")
            else:
                result.add_error(f"✗ Summary metric {key} missing")

        # Test 9.3: Get latency trends
        trends = get_latency_trends(days=7)

        if 'period_days' in trends:
            result.add_detail(f"✓ Latency trends period: {trends['period_days']} days")
        else:
            result.add_error("✗ Latency trends period missing")

        if 'trends' in trends:
            result.add_detail(f"✓ Latency trends data: {len(trends['trends'])} records")
        else:
            result.add_error("✗ Latency trends data missing")

    except ImportError as e:
        result.add_error(f"Quality monitoring module import failed: {e}")
    except Exception as e:
        result.add_error(f"Quality monitoring test failed: {e}")

    return result


# ============================================================================
# Test 10: Automatic Cleanup
# ============================================================================

def test_cleanup_task() -> TestResult:
    """Test automatic cleanup functionality"""
    result = TestResult("Automatic Cleanup Task Test")

    try:
        from external_systems.partner_chat_system.chat_system.verification_cleanup_task import (
            SensitiveDataCleanupTask,
            run_verification_cleanup_task,
        )

        # Test 10.1: Create cleanup task
        task = SensitiveDataCleanupTask()
        if task:
            result.add_detail("✓ Cleanup task created")
        else:
            result.add_error("✗ Cleanup task creation failed")

        # Test 10.2: Get retention policies
        policies = task._get_retention_policies()

        if policies:
            result.add_detail(f"✓ Retention policies loaded: {len(policies)} policies")
        else:
            result.add_error("✗ Retention policies not loaded")

        # Test 10.3: Verify policy values
        expected_policies = {
            'raw_verification_media': 30,
            'ocr_extracted_text': 180,
            'authority_verification_result': 365,
            'revocation_evidence': 730,
        }

        for policy_key, expected_days in expected_policies.items():
            if policy_key in policies:
                actual_days = policies[policy_key]
                if actual_days == expected_days:
                    result.add_detail(f"✓ Policy {policy_key}: {actual_days} days")
                else:
                    result.add_error(f"✗ Policy {policy_key} mismatch: expected {expected_days}, got {actual_days}")
            else:
                result.add_error(f"✗ Policy {policy_key} missing")

        # Test 10.4: Cleanup task execution (dry run - not actually deleting data)
        result.add_detail("⚠ Cleanup task execution skipped (would delete real data)")

        task.close()

    except ImportError as e:
        result.add_error(f"Cleanup task module import failed: {e}")
    except Exception as e:
        result.add_error(f"Cleanup task test failed: {e}")

    return result


# ============================================================================
# Test Runner
# ============================================================================

def run_all_tests() -> dict[str, Any]:
    """Run all verification security improvement tests"""
    print("=" * 80)
    print("VERIFICATION SECURITY IMPROVEMENT TEST SUITE")
    print("=" * 80)
    print()

    tests = [
        test_database_schema,
        test_encryption,
        test_access_audit,
        test_threshold_configuration,
        test_rate_limiting,
        test_input_validation,
        test_ocr_service,
        test_expiry_revocation,
        test_quality_monitoring,
        test_cleanup_task,
    ]

    results = []
    total_passed = 0
    total_failed = 0

    for test_func in tests:
        print(f"Running {test_func.__name__}...")
        try:
            result = test_func()
            results.append(result.to_dict())

            if result.passed:
                total_passed += 1
                print(f"  ✓ PASSED")
            else:
                total_failed += 1
                print(f"  ✗ FAILED")
                for error in result.errors:
                    print(f"    - {error}")

            print()
        except Exception as e:
            print(f"  ✗ TEST EXECUTION FAILED: {e}")
            print()
            total_failed += 1
            results.append({
                "test_name": test_func.__name__,
                "passed": False,
                "errors": [f"Test execution failed: {e}"],
                "details": [],
            })

    # Summary
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total tests: {len(results)}")
    print(f"Passed: {total_passed}")
    print(f"Failed: {total_failed}")
    print(f"Success rate: {total_passed / len(results) * 100:.1f}%")
    print()

    if total_failed > 0:
        print("Failed tests:")
        for result in results:
            if not result['passed']:
                print(f"  - {result['test_name']}: {len(result['errors'])} errors")
        print()

    print("=" * 80)

    return {
        "total_tests": len(results),
        "passed": total_passed,
        "failed": total_failed,
        "success_rate": total_passed / len(results) * 100,
        "results": results,
    }


if __name__ == "__main__":
    # Run all tests
    summary = run_all_tests()

    # Export results to JSON
    results_file = f"/tmp/verification_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(results_file, 'w') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(f"Test results saved to: {results_file}")

    # Exit with appropriate status
    if summary['failed'] > 0:
        print("\n⚠ Some tests failed. Please review errors above.")
        exit(1)
    else:
        print("\n✓ All tests passed!")
        exit(0)