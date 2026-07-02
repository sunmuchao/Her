"""Simplified test suite for verification security improvements.

This script tests the core components that can be tested without complex imports.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

# Add project paths
sys.path.insert(0, '/Users/sunmuchao/Downloads/Her')
sys.path.insert(0, '/Users/sunmuchao/Downloads/Her/external-systems/partner-chat-system')
sys.path.insert(0, '/Users/sunmuchao/Downloads/Her/external-systems/partner-http-gateway')

import pymysql

# Database configuration
DB_HOST = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("MYSQL_PORT", "3307"))
DB_USER = os.environ.get("MYSQL_USER", "root")
DB_PASSWORD = os.environ.get("MYSQL_ROOT_PASSWORD", "SLhJJ0BfjguKNGpGb5jUJlajt2+5QP7IW3B8aXycnrw=")
DB_NAME = "her_chat"


def test_database_schema():
    """Test database schema changes"""
    print("\n[TEST 1] Database Schema Validation")

    conn = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER,
        password=DB_PASSWORD, database=DB_NAME, charset='utf8mb4'
    )
    cursor = conn.cursor()

    passed = True

    # Check new tables
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
            print(f"  ✓ Table {table_name} exists")
        else:
            print(f"  ✗ Table {table_name} not found")
            passed = False

    # Check new fields in verification_submissions
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
            print(f"  ✓ Field verification_submissions.{field} exists")
        else:
            print(f"  ✗ Field verification_submissions.{field} not found")
            passed = False

    # Check initial data
    cursor.execute("SELECT COUNT(*) FROM verification_level_weights")
    count = cursor.fetchone()[0]
    if count == 4:
        print(f"  ✓ verification_level_weights has {count} records")
    else:
        print(f"  ✗ verification_level_weights has {count} records (expected: 4)")
        passed = False

    cursor.execute("SELECT COUNT(*) FROM verification_data_governance_policies")
    count = cursor.fetchone()[0]
    if count == 4:
        print(f"  ✓ verification_data_governance_policies has {count} records")
    else:
        print(f"  ✗ verification_data_governance_policies has {count} records (expected: 4)")
        passed = False

    cursor.close()
    conn.close()

    return passed


def test_threshold_configuration():
    """Test threshold configuration"""
    print("\n[TEST 2] Threshold Configuration")

    try:
        from match_domain.rule_config_schema import (
            SLICE_VERIFICATION_THRESHOLDS,
            code_defaults_for_slice,
        )

        thresholds = code_defaults_for_slice(SLICE_VERIFICATION_THRESHOLDS)

        passed = True

        if thresholds:
            print(f"  ✓ Thresholds loaded: {len(thresholds)} parameters")
        else:
            print(f"  ✗ Thresholds not loaded")
            return False

        # Verify key thresholds
        expected = {
            'liveness_score_min': 85,
            'face_match_score_min': 85,
            'challenge_score_min': 80,
            'auto_approve_enabled': True,
        }

        for key, value in expected.items():
            if thresholds.get(key) == value:
                print(f"  ✓ {key} = {value}")
            else:
                print(f"  ✗ {key} mismatch: expected {value}, got {thresholds.get(key)}")
                passed = False

        return passed

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def test_encryption():
    """Test encryption functionality"""
    print("\n[TEST 3] Encryption/Decryption")

    try:
        from chat_system.verification_sensitive_data_encryption import (
            encrypt_sensitive_field,
            decrypt_sensitive_field,
        )

        passed = True

        # Test string encryption
        test_string = "This is sensitive data"
        encrypted = encrypt_sensitive_field(test_string)

        if encrypted and encrypted != test_string:
            print(f"  ✓ String encryption successful")
        else:
            print(f"  ✗ String encryption failed")
            passed = False

        decrypted = decrypt_sensitive_field(encrypted)
        if decrypted == test_string:
            print(f"  ✓ String decryption successful")
        else:
            print(f"  ✗ String decryption failed")
            passed = False

        # Test dict encryption
        test_dict = {"school": "北京大学", "degree": "本科"}
        encrypted_dict = encrypt_sensitive_field(test_dict)

        if encrypted_dict and isinstance(encrypted_dict, str):
            print(f"  ✓ Dict encryption successful")
        else:
            print(f"  ✗ Dict encryption failed")
            passed = False

        decrypted_dict = decrypt_sensitive_field(encrypted_dict)
        if decrypted_dict == test_dict:
            print(f"  ✓ Dict decryption successful")
        else:
            print(f"  ✗ Dict decryption failed")
            passed = False

        return passed

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def test_rate_limiting():
    """Test rate limiting"""
    print("\n[TEST 4] Rate Limiting")

    try:
        from gateway.verification_rate_limiter import (
            check_verification_rate_limit,
            get_remaining_verification_requests,
            RATE_LIMITS,
        )

        passed = True

        # Verify rate limit configs
        if 'create_challenge' in RATE_LIMITS:
            config = RATE_LIMITS['create_challenge']
            if config['max_requests'] == 10 and config['window_seconds'] == 60:
                print(f"  ✓ create_challenge: 10 requests per 60 seconds")
            else:
                print(f"  ✗ create_challenge config incorrect")
                passed = False
        else:
            print(f"  ✗ create_challenge not defined")
            passed = False

        if 'submit_video' in RATE_LIMITS:
            config = RATE_LIMITS['submit_video']
            if config['max_requests'] == 5 and config['window_seconds'] == 60:
                print(f"  ✓ submit_video: 5 requests per 60 seconds")
            else:
                print(f"  ✗ submit_video config incorrect")
                passed = False
        else:
            print(f"  ✗ submit_video not defined")
            passed = False

        # Test rate limit check
        try:
            check_verification_rate_limit("create_challenge", "test-user-001")
            print(f"  ✓ First request passed rate limit")
        except Exception as e:
            print(f"  ✗ Rate limit check failed: {e}")
            passed = False

        return passed

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def test_input_validation():
    """Test input validation"""
    print("\n[TEST 5] Input Validation")

    try:
        from gateway.verification_input_validator import (
            validate_submission_id,
            validate_file_size,
            validate_content_type,
            InputValidationError,
        )

        passed = True

        # Test valid submission_id
        valid_id = "vfy-a1b2c3d4e5f67890"
        try:
            validated = validate_submission_id(valid_id)
            print(f"  ✓ Valid submission_id accepted")
        except InputValidationError:
            print(f"  ✗ Valid submission_id should be accepted")
            passed = False

        # Test invalid submission_id
        invalid_ids = ["invalid-id", "vfy-short", "VFY-UPPERCASE"]
        for invalid_id in invalid_ids:
            try:
                validate_submission_id(invalid_id)
                print(f"  ✗ Invalid submission_id '{invalid_id}' should be rejected")
                passed = False
            except InputValidationError:
                print(f"  ✓ Invalid submission_id '{invalid_id}' rejected")

        # Test file size
        try:
            validate_file_size(10 * 1024 * 1024)  # 10MB
            print(f"  ✓ Valid file size accepted")
        except InputValidationError:
            print(f"  ✗ Valid file size should be accepted")
            passed = False

        try:
            validate_file_size(60 * 1024 * 1024)  # 60MB
            print(f"  ✗ File size > 50MB should be rejected")
            passed = False
        except InputValidationError:
            print(f"  ✓ File size > 50MB rejected")

        # Test content type
        try:
            validate_content_type('video/webm')
            print(f"  ✓ Valid content_type accepted")
        except InputValidationError:
            print(f"  ✗ Valid content_type should be accepted")
            passed = False

        try:
            validate_content_type('application/pdf')
            print(f"  ✗ Invalid content_type should be rejected")
            passed = False
        except InputValidationError:
            print(f"  ✓ Invalid content_type rejected")

        return passed

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def test_ocr_service():
    """Test OCR service"""
    print("\n[TEST 6] OCR Service")

    try:
        from chat_system.verification_ocr_service import (
            OCRServiceFactory,
            MockOCRProvider,
            ocr_verify_document,
        )

        passed = True

        # Get mock provider
        provider = OCRServiceFactory.get_provider('mock')
        if provider:
            print(f"  ✓ OCR provider created")
        else:
            print(f"  ✗ OCR provider creation failed")
            return False

        # Test OCR recognition
        test_image = b"mock_image_data"
        ocr_result = provider.recognize_text(test_image)

        if ocr_result.success:
            print(f"  ✓ OCR recognition successful")
        else:
            print(f"  ✗ OCR recognition failed")
            passed = False

        if ocr_result.full_text:
            print(f"  ✓ OCR extracted text: '{ocr_result.full_text}'")
        else:
            print(f"  ✗ OCR should extract text")
            passed = False

        # Test document verification
        profile_data = {"name": "张三", "school": "北京大学"}
        verification_result = ocr_verify_document(test_image, 'education', profile_data)

        if verification_result['ocr_success']:
            print(f"  ✓ OCR verification successful")
        else:
            print(f"  ✗ OCR verification failed")
            passed = False

        return passed

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def test_expiry_revocation():
    """Test expiry and revocation"""
    print("\n[TEST 7] Expiry and Revocation")

    try:
        from chat_system.verification_expiry_revocation import (
            check_verification_expiry,
            get_level_expiry,
        )

        passed = True

        # Test level expiry
        live_video_expiry = get_level_expiry('live_video_verified')
        if live_video_expiry == 365:
            print(f"  ✓ live_video_verified expiry: {live_video_expiry} days")
        else:
            print(f"  ✗ live_video_verified expiry should be 365")
            passed = False

        # Test expired verification
        expired_profile = {
            "photo_verification_at": "2020-01-01T00:00:00",
            "photo_verification_level": "live_video_verified",
        }

        expiry_result = check_verification_expiry(expired_profile)

        if expiry_result['expired']:
            print(f"  ✓ Expired verification detected")
        else:
            print(f"  ✗ Should detect expired verification")
            passed = False

        # Test fresh verification
        fresh_profile = {
            "photo_verification_at": datetime.now().isoformat(),
            "photo_verification_level": "live_video_verified",
        }

        expiry_result = check_verification_expiry(fresh_profile)

        if not expiry_result['expired']:
            print(f"  ✓ Fresh verification not expired")
        else:
            print(f"  ✗ Fresh verification should not be expired")
            passed = False

        return passed

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def test_cleanup_task():
    """Test cleanup task"""
    print("\n[TEST 8] Automatic Cleanup Task")

    try:
        from chat_system.verification_cleanup_task import (
            SensitiveDataCleanupTask,
        )

        passed = True

        task = SensitiveDataCleanupTask()

        # Get retention policies
        policies = task._get_retention_policies()

        if policies:
            print(f"  ✓ Retention policies loaded: {len(policies)} policies")
        else:
            print(f"  ✗ Retention policies not loaded")
            return False

        # Verify policy values
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
                    print(f"  ✓ Policy {policy_key}: {actual_days} days")
                else:
                    print(f"  ✗ Policy {policy_key} mismatch")
                    passed = False
            else:
                print(f"  ✗ Policy {policy_key} missing")
                passed = False

        task.close()

        return passed

    except Exception as e:
        print(f"  ✗ Test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("=" * 80)
    print("VERIFICATION SECURITY IMPROVEMENT TEST SUITE")
    print("=" * 80)

    tests = [
        ("Database Schema", test_database_schema),
        ("Threshold Configuration", test_threshold_configuration),
        ("Encryption", test_encryption),
        ("Rate Limiting", test_rate_limiting),
        ("Input Validation", test_input_validation),
        ("OCR Service", test_ocr_service),
        ("Expiry/Revocation", test_expiry_revocation),
        ("Cleanup Task", test_cleanup_task),
    ]

    results = []
    total_passed = 0

    for test_name, test_func in tests:
        passed = test_func()
        results.append((test_name, passed))
        if passed:
            total_passed += 1

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name}: {status}")

    print(f"\nTotal: {len(results)} tests")
    print(f"Passed: {total_passed}")
    print(f"Failed: {len(results) - total_passed}")
    print(f"Success rate: {total_passed / len(results) * 100:.1f}%")

    print("=" * 80)

    if total_passed == len(results):
        print("\n✅ All tests passed! Verification security improvements validated.")
        return 0
    else:
        print(f"\n⚠️  {len(results) - total_passed} tests failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)