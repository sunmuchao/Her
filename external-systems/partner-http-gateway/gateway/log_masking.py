"""Sensitive data masking for logs and audit records.

This module provides utilities to mask sensitive information in logs,
preventing accidental exposure of:
1. Phone numbers
2. ID numbers (身份证, 银行卡)
3. Passwords/tokens
4. IP addresses (partial masking)
5. User IDs (in certain contexts)

Design Principles:
1. Mask in logs, but keep full data for legitimate business processing
2. Different masking rules for different data types
3. Audit what was masked for debugging
"""

from __future__ import annotations

import re
from typing import Any


# Sensitive field patterns
_SENSITIVE_FIELD_NAMES = frozenset({
    # Authentication
    "password", "pwd", "pass", "secret", "token", "api_key", "apikey",
    "access_token", "refresh_token", "auth_code", "otp", "code",
    "private_key", "secret_key", "encryption_key",

    # Personal info
    "phone", "mobile", "tel", "telephone", "cellphone",
    "id_number", "id_card", "身份证", "identity_card",
    "bank_card", "card_number", "account_number",
    "email", "mail", "address", "addr",
    "real_name", "name", "姓名",

    # Financial
    "salary", "income", "balance", "amount", "money",

    # Health
    "medical", "health", "disease", "病历",

    # Other sensitive
    "ssn", "social_security", "passport",
})

# Field name patterns for partial masking (reveal some info)
_PARTIAL_MASK_FIELDS = frozenset({
    "phone", "mobile", "tel", "telephone",
    "email", "mail",
    "ip", "ip_address", "client_ip",
    "user_id", "actor_id", "profile_id",
})

# Regex patterns for sensitive data detection
_PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")
_EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_ID_CARD_PATTERN = re.compile(r"\d{17}[\dXx]")
_BANK_CARD_PATTERN = re.compile(r"\d{16,19}")


def mask_phone(phone: str | None) -> str:
    """Mask phone number: show first 3 and last 4 digits.

    Example: 13812345678 -> 138****5678
    """
    if phone is None:
        return ""
    text = str(phone).strip()
    if not text:
        return ""
    # Validate format first
    if _PHONE_PATTERN.fullmatch(text):
        return f"{text[:3]}****{text[-4:]}"
    # For invalid/non-standard phones, mask more aggressively
    if len(text) > 6:
        return f"{text[:2]}****{text[-2:]}"
    return "***"


def mask_email(email: str | None) -> str:
    """Mask email: show first letter and domain.

    Example: user@example.com -> u***@example.com
    """
    if email is None:
        return ""
    text = str(email).strip()
    if not text:
        return ""
    if "@" not in text:
        return "***"
    local, domain = text.rsplit("@", 1)
    if len(local) > 1:
        masked_local = f"{local[0]}***"
    else:
        masked_local = "***"
    return f"{masked_local}@{domain}"


def mask_id_card(id_number: str | None) -> str:
    """Mask ID card number: show first 6 and last 4.

    Example: 123456789012345678 -> 123456****5678
    """
    if id_number is None:
        return ""
    text = str(id_number).strip()
    if not text:
        return ""
    if len(text) >= 15:
        return f"{text[:6]}****{text[-4:]}"
    return "***"


def mask_bank_card(card_number: str | None) -> str:
    """Mask bank card: show first 4 and last 4.

    Example: 1234567890123456 -> 1234****3456
    """
    if card_number is None:
        return ""
    text = str(card_number).strip()
    if not text:
        return ""
    # Remove spaces/dashes
    text = re.sub(r"[\s\-]", "", text)
    if len(text) >= 12:
        return f"{text[:4]}****{text[-4:]}"
    return "***"


def mask_ip(ip: str | None) -> str:
    """Mask IP address: show first octet.

    Example: 192.168.1.100 -> 192.*.*.*
    """
    if ip is None:
        return ""
    text = str(ip).strip()
    if not text or text == "0.0.0.0":
        return text
    parts = text.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.***.***.***"
    return "***"


def mask_token(token: str | None) -> str:
    """Mask token: show first 8 characters only.

    Example: abc123def456ghi789... -> abc123de***
    """
    if token is None:
        return ""
    text = str(token).strip()
    if not text:
        return ""
    if len(text) > 8:
        return f"{text[:8]}***"
    return "***"


def mask_user_id(user_id: str | None) -> str:
    """Mask user ID: show first 4 and last 4 characters.

    Example: usr_abc123xyz -> usr_***xyz
    """
    if user_id is None:
        return ""
    text = str(user_id).strip()
    if not text:
        return ""
    if len(text) > 8:
        return f"{text[:4]}***{text[-4:]}"
    return "***"


def mask_field_value(field_name: str, value: Any) -> Any:
    """Mask a field value based on field name.

    Args:
        field_name: The field/parameter name
        value: The value to potentially mask

    Returns:
        Masked value or original if not sensitive
    """
    if value is None:
        return None

    # Check if field name indicates sensitive data
    field_lower = field_name.lower()

    # Full masking for highly sensitive fields
    if field_lower in _SENSITIVE_FIELD_NAMES:
        if field_lower in {"phone", "mobile", "tel", "telephone"}:
            return mask_phone(str(value))
        if field_lower in {"email", "mail"}:
            return mask_email(str(value))
        if field_lower in {"id_number", "id_card", "身份证", "identity_card"}:
            return mask_id_card(str(value))
        if field_lower in {"bank_card", "card_number", "account_number"}:
            return mask_bank_card(str(value))
        if field_lower in {"ip", "ip_address", "client_ip"}:
            return mask_ip(str(value))
        # Other sensitive fields: full mask
        return "***"

    # Partial masking for semi-sensitive fields
    if field_lower in _PARTIAL_MASK_FIELDS:
        if field_lower in {"phone", "mobile", "tel", "telephone"}:
            return mask_phone(str(value))
        if field_lower in {"email", "mail"}:
            return mask_email(str(value))
        if field_lower in {"ip", "ip_address", "client_ip"}:
            return mask_ip(str(value))
        if field_lower in {"user_id", "actor_id", "profile_id"}:
            return mask_user_id(str(value))

    # Pattern-based masking for values that look sensitive
    text = str(value)
    if _PHONE_PATTERN.fullmatch(text):
        return mask_phone(text)
    if _EMAIL_PATTERN.fullmatch(text):
        return mask_email(text)
    if _ID_CARD_PATTERN.fullmatch(text):
        return mask_id_card(text)
    if _BANK_CARD_PATTERN.fullmatch(text):
        return mask_bank_card(text)

    return value


def mask_dict_values(data: dict[str, Any]) -> dict[str, Any]:
    """Mask sensitive values in a dictionary.

    Args:
        data: Dictionary with potentially sensitive values

    Returns:
        Dictionary with masked sensitive values
    """
    if not isinstance(data, dict):
        return data

    masked = {}
    for key, value in data.items():
        if isinstance(value, dict):
            masked[key] = mask_dict_values(value)
        elif isinstance(value, list):
            masked[key] = [mask_dict_values(item) if isinstance(item, dict) else mask_field_value(key, item) for item in value]
        else:
            masked[key] = mask_field_value(key, value)

    return masked


def mask_for_log(data: Any, context: str = "") -> str:
    """Convert data to string with sensitive values masked for logging.

    Args:
        data: Any data structure
        context: Additional context for the log

    Returns:
        Safe string representation for logging
    """
    if isinstance(data, dict):
        masked_data = mask_dict_values(data)
        import json
        try:
            return json.dumps(masked_data, ensure_ascii=False, default=str)
        except Exception:
            return str(masked_data)
    if isinstance(data, list):
        masked_list = [mask_dict_values(item) if isinstance(item, dict) else item for item in data]
        import json
        try:
            return json.dumps(masked_list, ensure_ascii=False, default=str)
        except Exception:
            return str(masked_list)
    return str(mask_field_value("value", data))


def is_sensitive_field(field_name: str) -> bool:
    """Check if a field name indicates sensitive data."""
    return field_name.lower() in _SENSITIVE_FIELD_NAMES


__all__ = [
    "mask_phone",
    "mask_email",
    "mask_id_card",
    "mask_bank_card",
    "mask_ip",
    "mask_token",
    "mask_user_id",
    "mask_field_value",
    "mask_dict_values",
    "mask_for_log",
    "is_sensitive_field",
    "_SENSITIVE_FIELD_NAMES",
    "_PARTIAL_MASK_FIELDS",
]