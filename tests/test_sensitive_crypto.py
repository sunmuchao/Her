"""Tests for sensitive data encryption/decryption.

Test coverage:
- Normal encryption/decryption flow
- Key missing scenarios
- Key rotation
- Invalid data handling
- Empty/null handling
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

# Bootstrap project path - add external-systems to path
external_systems_root = Path(__file__).resolve().parent.parent / "external-systems"
external_systems_root_str = str(external_systems_root)
if external_systems_root_str not in sys.path:
    sys.path.insert(0, external_systems_root_str)


class TestSensitiveDataCrypto(unittest.TestCase):
    """Unit tests for SensitiveDataCrypto class."""

    TEST_KEY = Fernet.generate_key().decode()
    TEST_KEY_ALT = Fernet.generate_key().decode()

    def setUp(self):
        """Set up test environment with encryption key."""
        # Save original env
        self._original_key = os.environ.get("HER_SENSITIVE_DATA_KEY")
        self._original_prev_key = os.environ.get("HER_SENSITIVE_DATA_KEY_PREVIOUS")
        self._original_prod_mode = os.environ.get("HER_PRODUCTION_MODE")

        # Set test key
        os.environ["HER_SENSITIVE_DATA_KEY"] = self.TEST_KEY
        os.environ.pop("HER_SENSITIVE_DATA_KEY_PREVIOUS", None)
        os.environ.pop("HER_PRODUCTION_MODE", None)

        # Force re-initialization
        from chat_system.sensitive_crypto import (
            _CryptoBackend,
            SensitiveDataCrypto,
        )
        _CryptoBackend._initialized = False
        _CryptoBackend._fernet = None
        _CryptoBackend._fernet_previous = None

    def tearDown(self):
        """Restore original environment."""
        if self._original_key:
            os.environ["HER_SENSITIVE_DATA_KEY"] = self._original_key
        else:
            os.environ.pop("HER_SENSITIVE_DATA_KEY", None)

        if self._original_prev_key:
            os.environ["HER_SENSITIVE_DATA_KEY_PREVIOUS"] = self._original_prev_key
        else:
            os.environ.pop("HER_SENSITIVE_DATA_KEY_PREVIOUS", None)

        if self._original_prod_mode:
            os.environ["HER_PRODUCTION_MODE"] = self._original_prod_mode
        else:
            os.environ.pop("HER_PRODUCTION_MODE", None)

        # Force re-initialization for next test
        from chat_system.sensitive_crypto import _CryptoBackend
        _CryptoBackend._initialized = False
        _CryptoBackend._fernet = None
        _CryptoBackend._fernet_previous = None

    def test_encrypt_decrypt_phone(self):
        """Test normal phone encryption/decryption."""
        from chat_system.sensitive_crypto import (
            SensitiveDataCrypto,
        )

        phone = "13812345678"
        encrypted = SensitiveDataCrypto.encrypt_phone(phone)

        # Should have prefix
        self.assertTrue(encrypted.startswith("enc:"))

        # Should be different from original
        self.assertNotEqual(encrypted, phone)

        # Should decrypt correctly
        decrypted = SensitiveDataCrypto.decrypt_phone(encrypted)
        self.assertEqual(decrypted, phone)

    def test_encrypt_decrypt_wechat_id(self):
        """Test WeChat ID encryption/decryption."""
        from chat_system.sensitive_crypto import (
            SensitiveDataCrypto,
        )

        openid = "wx-openid-test-12345678"
        encrypted = SensitiveDataCrypto.encrypt_wechat_id(openid)

        # Should have prefix
        self.assertTrue(encrypted.startswith("enc:"))

        # Should decrypt correctly
        decrypted = SensitiveDataCrypto.decrypt_wechat_id(encrypted)
        self.assertEqual(decrypted, openid)

    def test_encrypt_identity_value(self):
        """Test identity value encryption based on type."""
        from chat_system.sensitive_crypto import (
            SensitiveDataCrypto,
        )

        phone = "13812345678"
        openid = "wx-openid-test-12345"

        # Phone type
        encrypted_phone = SensitiveDataCrypto.encrypt_identity_value("phone", phone)
        decrypted_phone = SensitiveDataCrypto.decrypt_identity_value("phone", encrypted_phone)
        self.assertEqual(decrypted_phone, phone)

        # WeChat type
        encrypted_openid = SensitiveDataCrypto.encrypt_identity_value("wechat_openid", openid)
        decrypted_openid = SensitiveDataCrypto.decrypt_identity_value("wechat_openid", encrypted_openid)
        self.assertEqual(decrypted_openid, openid)

    def test_null_handling(self):
        """Test null/empty handling."""
        from chat_system.sensitive_crypto import (
            SensitiveDataCrypto,
        )

        # Null input
        self.assertIsNone(SensitiveDataCrypto.encrypt_phone(None))
        self.assertIsNone(SensitiveDataCrypto.decrypt_phone(None))
        self.assertIsNone(SensitiveDataCrypto.encrypt_wechat_id(None))
        self.assertIsNone(SensitiveDataCrypto.decrypt_wechat_id(None))

        # Empty string
        self.assertIsNone(SensitiveDataCrypto.encrypt_phone(""))
        self.assertIsNone(SensitiveDataCrypto.decrypt_phone(""))

    def test_is_encrypted(self):
        """Test encryption detection."""
        from chat_system.sensitive_crypto import (
            SensitiveDataCrypto,
        )

        # Encrypted value
        encrypted = SensitiveDataCrypto.encrypt_phone("13812345678")
        self.assertTrue(SensitiveDataCrypto.is_encrypted(encrypted))

        # Plain value
        self.assertFalse(SensitiveDataCrypto.is_encrypted("13812345678"))
        self.assertFalse(SensitiveDataCrypto.is_encrypted(None))
        self.assertFalse(SensitiveDataCrypto.is_encrypted(""))

    def test_mask_phone_for_display(self):
        """Test phone masking for display."""
        from chat_system.sensitive_crypto import (
            SensitiveDataCrypto,
        )

        # Standard phone
        masked = SensitiveDataCrypto.mask_phone_for_display("13812345678")
        self.assertEqual(masked, "138****5678")

        # Non-standard phone
        masked = SensitiveDataCrypto.mask_phone_for_display("1234567")
        self.assertEqual(masked, "12****67")

        # Short value
        masked = SensitiveDataCrypto.mask_phone_for_display("123")
        self.assertEqual(masked, "***")

        # Null
        self.assertEqual(SensitiveDataCrypto.mask_phone_for_display(None), "")

    def test_key_rotation(self):
        """Test decryption with previous key (rotation scenario)."""
        from chat_system.sensitive_crypto import (
            SensitiveDataCrypto,
            _CryptoBackend,
        )

        # Encrypt with current key
        phone = "13812345678"
        encrypted = SensitiveDataCrypto.encrypt_phone(phone)

        # Set up rotation scenario: current key becomes previous
        os.environ["HER_SENSITIVE_DATA_KEY"] = self.TEST_KEY_ALT
        os.environ["HER_SENSITIVE_DATA_KEY_PREVIOUS"] = self.TEST_KEY

        # Force re-initialization
        _CryptoBackend._initialized = False
        _CryptoBackend._fernet = None
        _CryptoBackend._fernet_previous = None

        # Should still decrypt with previous key
        decrypted = SensitiveDataCrypto.decrypt_phone(encrypted)
        self.assertEqual(decrypted, phone)

    def test_production_mode_missing_key(self):
        """Test production mode raises error without key."""
        os.environ.pop("HER_SENSITIVE_DATA_KEY", None)
        os.environ["HER_PRODUCTION_MODE"] = "1"

        # Force re-initialization
        from chat_system.sensitive_crypto import (
            _CryptoBackend,
            MissingEncryptionKeyError,
        )
        _CryptoBackend._initialized = False
        _CryptoBackend._fernet = None
        _CryptoBackend._fernet_previous = None

        with self.assertRaises(MissingEncryptionKeyError):
            _CryptoBackend._ensure_initialized()

    def test_dev_mode_without_key(self):
        """Test development mode works without key (pseudo-encryption)."""
        os.environ.pop("HER_SENSITIVE_DATA_KEY", None)
        os.environ.pop("HER_PRODUCTION_MODE", None)

        # Force re-initialization
        from chat_system.sensitive_crypto import (
            _CryptoBackend,
            SensitiveDataCrypto,
        )
        _CryptoBackend._initialized = False
        _CryptoBackend._fernet = None
        _CryptoBackend._fernet_previous = None

        # Should pseudo-encrypt (add prefix but not truly encrypt)
        phone = "13812345678"
        encrypted = SensitiveDataCrypto.encrypt_phone(phone)

        # Should have DEV prefix
        self.assertTrue(encrypted.startswith("enc:DEV:"))

        # Should decrypt correctly
        decrypted = SensitiveDataCrypto.decrypt_phone(encrypted)
        self.assertEqual(decrypted, phone)

    def test_decryption_failure_with_wrong_key(self):
        """Test decryption fails with wrong key."""
        from chat_system.sensitive_crypto import (
            SensitiveDataCrypto,
            _CryptoBackend,
            DecryptionError,
        )

        # Encrypt with current key
        phone = "13812345678"
        encrypted = SensitiveDataCrypto.encrypt_phone(phone)

        # Change to different key (no previous key set)
        os.environ["HER_SENSITIVE_DATA_KEY"] = self.TEST_KEY_ALT
        os.environ.pop("HER_SENSITIVE_DATA_KEY_PREVIOUS", None)

        # Force re-initialization
        _CryptoBackend._initialized = False
        _CryptoBackend._fernet = None
        _CryptoBackend._fernet_previous = None

        # Should raise DecryptionError
        with self.assertRaises(DecryptionError):
            SensitiveDataCrypto.decrypt_phone(encrypted)

    def test_decrypt_plain_value(self):
        """Test decrypting plain value (migration scenario)."""
        from chat_system.sensitive_crypto import (
            SensitiveDataCrypto,
        )

        # Plain value should return as-is
        plain_phone = "13812345678"
        decrypted = SensitiveDataCrypto.decrypt_phone(plain_phone)
        self.assertEqual(decrypted, plain_phone)


if __name__ == "__main__":
    unittest.main()