"""Sensitive data encryption utilities for verification system.

This module provides encryption and decryption functions for sensitive fields
in the verification system, including:
- OCR extracted text
- ID numbers
- Income verification results
- Revocation evidence

Encryption uses AES-256-GCM for authenticated encryption.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from datetime import datetime
from typing import Any

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Encryption key from environment or generate a new one
ENCRYPTION_KEY_ENV = "HER_VERIFICATION_ENCRYPTION_KEY"
ENCRYPTION_SALT_ENV = "HER_VERIFICATION_ENCRYPTION_SALT"

# Default key and salt for development (should be changed in production)
DEFAULT_KEY = "her-verification-secret-key-change-in-production"
DEFAULT_SALT = b"her-verification-salt-change-in-production"


class EncryptionError(Exception):
    """Encryption or decryption error"""
    pass


class SensitiveDataEncryption:
    """Sensitive data encryption manager"""

    def __init__(self):
        self._backend = default_backend()
        self._key = self._derive_key()

    def _derive_key(self) -> bytes:
        """Derive encryption key from password and salt"""
        password = os.environ.get(ENCRYPTION_KEY_ENV, DEFAULT_KEY).encode()
        salt = base64.b64decode(os.environ.get(ENCRYPTION_SALT_ENV, base64.b64encode(DEFAULT_SALT).decode()))

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,  # AES-256 key length
            salt=salt,
            iterations=100000,
            backend=self._backend
        )

        return kdf.derive(password)

    def encrypt(self, plaintext: str | dict | None) -> str | None:
        """
        Encrypt sensitive data using AES-256-GCM

        Args:
            plaintext: The data to encrypt (string, dict, or None)

        Returns:
            Base64 encoded encrypted data with nonce, or None if input is None

        Raises:
            EncryptionError: If encryption fails
        """
        if plaintext is None:
            return None

        try:
            # Convert dict to JSON string if needed
            if isinstance(plaintext, dict):
                plaintext = json.dumps(plaintext, ensure_ascii=False)

            plaintext_bytes = plaintext.encode('utf-8')

            # Generate random nonce (96 bits for GCM)
            nonce = secrets.token_bytes(12)

            # Create AES-GCM cipher
            cipher = Cipher(
                algorithms.AES(self._key),
                modes.GCM(nonce),
                backend=self._backend
            )
            encryptor = cipher.encryptor()

            # Encrypt and get authentication tag
            ciphertext = encryptor.update(plaintext_bytes) + encryptor.finalize()
            tag = encryptor.tag

            # Combine nonce + tag + ciphertext and encode as base64
            combined = nonce + tag + ciphertext
            return base64.b64encode(combined).decode('ascii')

        except Exception as e:
            raise EncryptionError(f"Encryption failed: {e}") from e

    def decrypt(self, ciphertext: str | None) -> str | dict | None:
        """
        Decrypt sensitive data using AES-256-GCM

        Args:
            ciphertext: Base64 encoded encrypted data

        Returns:
            Decrypted data (string, dict if JSON, or None)

        Raises:
            EncryptionError: If decryption fails or authentication fails
        """
        if ciphertext is None:
            return None

        try:
            # Decode base64
            combined = base64.b64decode(ciphertext)

            # Extract nonce (12 bytes), tag (16 bytes), and ciphertext
            nonce = combined[:12]
            tag = combined[12:28]
            actual_ciphertext = combined[28:]

            # Create AES-GCM cipher for decryption
            cipher = Cipher(
                algorithms.AES(self._key),
                modes.GCM(nonce, tag),
                backend=self._backend
            )
            decryptor = cipher.decryptor()

            # Decrypt and verify authentication
            plaintext_bytes = decryptor.update(actual_ciphertext) + decryptor.finalize()
            plaintext = plaintext_bytes.decode('utf-8')

            # Try to parse as JSON if it looks like JSON
            try:
                return json.loads(plaintext)
            except json.JSONDecodeError:
                return plaintext

        except Exception as e:
            raise EncryptionError(f"Decryption failed: {e}") from e


# Global encryption instance
_encryption = SensitiveDataEncryption()


def encrypt_sensitive_field(value: str | dict | None) -> str | None:
    """Encrypt a sensitive field value"""
    return _encryption.encrypt(value)


def decrypt_sensitive_field(value: str | None) -> str | dict | None:
    """Decrypt a sensitive field value"""
    return _encryption.decrypt(value)


# Sensitive field types that need encryption
SENSITIVE_FIELD_TYPES = {
    'ocr_extracted_text': 'OCR全文',
    'authority_verification_result': '权威验证结果',
    'revocation_evidence': '撤销证据',
    'id_number': '身份证号',
    'income_result': '收入结果',
}


def is_sensitive_field(field_name: str) -> bool:
    """Check if a field is sensitive and needs encryption"""
    return field_name in SENSITIVE_FIELD_TYPES


def encrypt_field_if_sensitive(field_name: str, value: Any) -> Any:
    """
    Encrypt a field value if it's sensitive

    Args:
        field_name: The field name
        value: The field value

    Returns:
        Encrypted value if field is sensitive, original value otherwise
    """
    if is_sensitive_field(field_name) and value is not None:
        return encrypt_sensitive_field(value)
    return value


def decrypt_field_if_sensitive(field_name: str, value: Any) -> Any:
    """
    Decrypt a field value if it's sensitive

    Args:
        field_name: The field name
        value: The field value

    Returns:
        Decrypted value if field is sensitive and encrypted, original value otherwise
    """
    if is_sensitive_field(field_name) and value is not None and isinstance(value, str):
        try:
            return decrypt_sensitive_field(value)
        except EncryptionError:
            # If decryption fails, return original value (might not be encrypted yet)
            return value
    return value


if __name__ == "__main__":
    # Test encryption
    test_data = {
        "school_name": "北京大学",
        "degree_level": "本科",
        "ocr_confidence": 0.95
    }

    print("Testing encryption...")
    encrypted = encrypt_sensitive_field(test_data)
    print(f"Encrypted: {encrypted[:50]}...")

    decrypted = decrypt_sensitive_field(encrypted)
    print(f"Decrypted: {decrypted}")

    assert decrypted == test_data, "Decryption failed"
    print("✓ Encryption test passed")