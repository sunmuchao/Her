"""Sensitive data encryption/decryption for phone numbers and WeChat IDs.

This module provides secure encryption for sensitive user data:
1. Phone numbers (primary_phone, identity_value)
2. WeChat identifiers (openid, unionid)

Security Design:
- Uses Fernet (AES-128-CBC + HMAC-SHA256) from cryptography library
- Key managed via environment variable HER_SENSITIVE_DATA_KEY
- Encrypted values prefixed with 'enc:' for migration identification
- Supports key rotation via HER_SENSITIVE_DATA_KEY_PREVIOUS

Usage:
    from chat_system.sensitive_crypto import SensitiveDataCrypto

    # Encrypt phone before storing
    encrypted = SensitiveDataCrypto.encrypt_phone("13812345678")

    # Decrypt phone when reading
    phone = SensitiveDataCrypto.decrypt_phone(encrypted)

    # Check if value is already encrypted (for migration)
    if SensitiveDataCrypto.is_encrypted(value):
        phone = SensitiveDataCrypto.decrypt_phone(value)
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# Encrypted value prefix for migration identification
_ENCRYPTED_PREFIX = "enc:"

# Phone number pattern (Chinese mobile)
_PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")

# WeChat ID pattern (alphanumeric + underscore/dash, length 16-64)
_WECHAT_ID_PATTERN = re.compile(r"[a-zA-Z0-9_-]{16,64}")


class SensitiveDataCryptoError(RuntimeError):
    """Base exception for sensitive data crypto errors."""
    pass


class MissingEncryptionKeyError(SensitiveDataCryptoError):
    """Raised when encryption key is not configured."""
    pass


class DecryptionError(SensitiveDataCryptoError):
    """Raised when decryption fails (invalid key or corrupted data)."""
    pass


class _CryptoBackend:
    """
    Internal crypto backend using Fernet.

    Fernet provides:
    - AES-128-CBC encryption
    - HMAC-SHA256 authentication
    - Timestamp-based token expiration (optional)
    - URL-safe base64 encoding
    """

    _fernet: Fernet | None = None
    _fernet_previous: Fernet | None = None
    _initialized: bool = False

    @classmethod
    def _ensure_initialized(cls) -> None:
        """Initialize Fernet instances from environment variables."""
        if cls._initialized:
            return

        key = os.environ.get("HER_SENSITIVE_DATA_KEY", "").strip()
        if not key:
            # In development mode, allow operation without encryption
            # but log a warning. Production MUST have key configured.
            if os.environ.get("HER_PRODUCTION_MODE"):
                raise MissingEncryptionKeyError(
                    "HER_SENSITIVE_DATA_KEY is required in production mode. "
                    "Generate a key with: "
                    "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
            logger.warning(
                "HER_SENSITIVE_DATA_KEY not configured. "
                "Sensitive data will NOT be encrypted. "
                "This is acceptable for development but MUST be configured for production."
            )
            cls._initialized = True
            return

        try:
            cls._fernet = Fernet(key.encode())
        except Exception as exc:
            raise MissingEncryptionKeyError(
                f"Invalid HER_SENSITIVE_DATA_KEY format. "
                f"Key must be 32-byte base64-encoded string. "
                f"Error: {exc}"
            ) from exc

        # Optional: previous key for rotation
        key_previous = os.environ.get("HER_SENSITIVE_DATA_KEY_PREVIOUS", "").strip()
        if key_previous:
            try:
                cls._fernet_previous = Fernet(key_previous.encode())
            except Exception as exc:
                logger.warning(
                    f"Invalid HER_SENSITIVE_DATA_KEY_PREVIOUS format, ignoring: {exc}"
                )

        cls._initialized = True

    @classmethod
    def encrypt(cls, value: str) -> str:
        """Encrypt a value using Fernet."""
        cls._ensure_initialized()

        # If no key configured (development mode), return value with prefix
        # to indicate it should have been encrypted but wasn't
        if cls._fernet is None:
            return f"{_ENCRYPTED_PREFIX}DEV:{value}"

        encrypted_bytes = cls._fernet.encrypt(value.encode("utf-8"))
        encrypted_str = encrypted_bytes.decode("utf-8")
        return f"{_ENCRYPTED_PREFIX}{encrypted_str}"

    @classmethod
    def decrypt(cls, encrypted: str) -> str:
        """Decrypt a value using Fernet, with fallback to previous key."""
        cls._ensure_initialized()

        # Check prefix
        if not encrypted.startswith(_ENCRYPTED_PREFIX):
            # Not encrypted, return as-is (migration scenario)
            return encrypted

        # Remove prefix
        payload = encrypted[len(_ENCRYPTED_PREFIX):]

        # Development mode fallback
        if payload.startswith("DEV:") and cls._fernet is None:
            return payload[4:]

        # No key configured but value is encrypted - this is an error
        if cls._fernet is None:
            raise DecryptionError(
                "Cannot decrypt encrypted value without HER_SENSITIVE_DATA_KEY. "
                "Please configure the encryption key."
            )

        # Try current key first
        try:
            decrypted_bytes = cls._fernet.decrypt(payload.encode("utf-8"))
            return decrypted_bytes.decode("utf-8")
        except InvalidToken:
            pass

        # Try previous key (for rotation)
        if cls._fernet_previous is not None:
            try:
                decrypted_bytes = cls._fernet_previous.decrypt(payload.encode("utf-8"))
                logger.info("Decrypted using previous key (rotation scenario)")
                return decrypted_bytes.decode("utf-8")
            except InvalidToken:
                pass

        raise DecryptionError(
            "Decryption failed: invalid key or corrupted data. "
            "Ensure HER_SENSITIVE_DATA_KEY matches the key used for encryption."
        )

    @classmethod
    def is_encrypted(cls, value: str | None) -> bool:
        """Check if a value is encrypted (has the prefix)."""
        if value is None:
            return False
        return str(value).startswith(_ENCRYPTED_PREFIX)

    @classmethod
    def has_key(cls) -> bool:
        """Check if encryption key is configured."""
        cls._ensure_initialized()
        return cls._fernet is not None


class SensitiveDataCrypto:
    """
    Public API for sensitive data encryption/decryption.

    Provides type-specific methods for:
    - Phone numbers (encrypt_phone, decrypt_phone)
    - WeChat IDs (encrypt_wechat_id, decrypt_wechat_id)
    - Generic values (encrypt, decrypt)
    """

    @staticmethod
    def encrypt_phone(phone: str | None) -> str | None:
        """
        Encrypt a phone number.

        Args:
            phone: Phone number to encrypt (e.g., "13812345678")

        Returns:
            Encrypted string with 'enc:' prefix, or None if input is None

        Raises:
            MissingEncryptionKeyError: In production mode without key
        """
        if phone is None or not str(phone).strip():
            return None

        normalized = str(phone).strip()

        # Validate phone format (optional but recommended)
        if not _PHONE_PATTERN.fullmatch(normalized):
            logger.warning(f"Encrypting non-standard phone format: {normalized[:6]}***")

        return _CryptoBackend.encrypt(normalized)

    @staticmethod
    def decrypt_phone(encrypted: str | None) -> str | None:
        """
        Decrypt an encrypted phone number.

        Args:
            encrypted: Encrypted phone string (with 'enc:' prefix) or plain phone

        Returns:
            Decrypted phone number, or None if input is None

        Raises:
            DecryptionError: If decryption fails
        """
        if encrypted is None or not str(encrypted).strip():
            return None

        return _CryptoBackend.decrypt(str(encrypted))

    @staticmethod
    def encrypt_wechat_id(wechat_id: str | None) -> str | None:
        """
        Encrypt a WeChat identifier (openid or unionid).

        Args:
            wechat_id: WeChat ID to encrypt

        Returns:
            Encrypted string with 'enc:' prefix, or None if input is None
        """
        if wechat_id is None or not str(wechat_id).strip():
            return None

        normalized = str(wechat_id).strip()
        return _CryptoBackend.encrypt(normalized)

    @staticmethod
    def decrypt_wechat_id(encrypted: str | None) -> str | None:
        """
        Decrypt an encrypted WeChat identifier.

        Args:
            encrypted: Encrypted WeChat ID or plain ID

        Returns:
            Decrypted WeChat ID, or None if input is None
        """
        if encrypted is None or not str(encrypted).strip():
            return None

        return _CryptoBackend.decrypt(str(encrypted))

    @staticmethod
    def encrypt_identity_value(identity_type: str, value: str | None) -> str | None:
        """
        Encrypt an identity value based on type.

        Args:
            identity_type: Type of identity ('phone', 'wechat_openid', 'wechat_unionid')
            value: Identity value to encrypt

        Returns:
            Encrypted value appropriate for the type
        """
        if value is None:
            return None

        identity_type_lower = identity_type.lower()

        if identity_type_lower == "phone":
            return SensitiveDataCrypto.encrypt_phone(value)
        elif identity_type_lower in ("wechat_openid", "wechat_unionid"):
            return SensitiveDataCrypto.encrypt_wechat_id(value)
        else:
            # Unknown type - encrypt anyway for safety
            return _CryptoBackend.encrypt(str(value))

    @staticmethod
    def decrypt_identity_value(identity_type: str, encrypted: str | None) -> str | None:
        """
        Decrypt an identity value based on type.

        Args:
            identity_type: Type of identity
            encrypted: Encrypted or plain value

        Returns:
            Decrypted value appropriate for the type
        """
        if encrypted is None:
            return None

        identity_type_lower = identity_type.lower()

        if identity_type_lower == "phone":
            return SensitiveDataCrypto.decrypt_phone(encrypted)
        elif identity_type_lower in ("wechat_openid", "wechat_unionid"):
            return SensitiveDataCrypto.decrypt_wechat_id(encrypted)
        else:
            return _CryptoBackend.decrypt(str(encrypted))

    @staticmethod
    def is_encrypted(value: str | None) -> bool:
        """Check if a value appears to be encrypted."""
        return _CryptoBackend.is_encrypted(value)

    @staticmethod
    def has_encryption_key() -> bool:
        """Check if encryption key is configured."""
        return _CryptoBackend.has_key()

    @staticmethod
    def mask_phone_for_display(phone: str | None) -> str:
        """
        Mask phone number for display (logs, UI).

        Args:
            phone: Plain phone number (not encrypted)

        Returns:
            Masked phone: "138****5678"
        """
        if phone is None:
            return ""
        text = str(phone).strip()
        if not text:
            return ""
        if _PHONE_PATTERN.fullmatch(text):
            return f"{text[:3]}****{text[-4:]}"
        if len(text) > 6:
            return f"{text[:2]}****{text[-2:]}"
        return "***"


__all__ = [
    "SensitiveDataCrypto",
    "SensitiveDataCryptoError",
    "MissingEncryptionKeyError",
    "DecryptionError",
]