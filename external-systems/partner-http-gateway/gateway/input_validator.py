"""Centralized input validation helpers for the gateway.

This module provides reusable validation functions that can be applied
consistently across all routes, preventing common input-based attacks:

1. Type coercion with bounds checking
2. Format validation (IDs, phone numbers, etc.)
3. String sanitization (path traversal, injection)
4. List/dict validation

Design Principles:
- Fail early: Validate before processing
- Fail safe: Reject invalid input, don't try to fix it
- Single source of truth: Same validation rules everywhere
- Audit validation failures: Track attack patterns

Architecture:
┌─────────────────────────────────────────────────────────────┐
│                    InputValidator                            │
│                                                              │
│  Validators:                                                 │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ validate_id() - 资源 ID 验证                         │    │
│  │ - 格式: 只允许字母、数字、下划线、连字符             │    │
│  │ - 长度: 最大 128 字符                                │    │
│  │ - 禁止: 路径遍历字符 (../, /)                       │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ validate_int_id() - 整数 ID 验证                     │    │
│  │ - 类型: 必须为整数                                   │    │
│  │ - 范围: 1 ~ 10^9                                     │    │
│  │ - 禁止: 零、负数                                     │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ validate_string() - 字符串验证                       │    │
│  │ - 长度限制                                           │    │
│  │ - 字符白名单/黑名单                                  │    │
│  │ - XSS/SQL注入检测                                    │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ validate_list() - 列表验证                           │    │
│  │ - 类型检查                                           │    │
│  │ - 元素数量限制                                       │    │
│  │ - 元素内容验证                                       │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import re
from typing import Any


class ValidationError(ValueError):
    """Raised when input validation fails.

    Attributes:
        field: The field that failed validation
        value: The invalid value (may be None for security)
        reason: Why validation failed
    """

    def __init__(self, field: str, reason: str, value: Any = None) -> None:
        self.field = field
        self.reason = reason
        # Don't store sensitive values in exception for security
        self._value = value if not self._is_sensitive(field) else None
        super().__init__(f"{field}: {reason}")

    def _is_sensitive(self, field: str) -> bool:
        """Check if field might contain sensitive data."""
        sensitive_fields = {"password", "token", "secret", "key", "code", "otp"}
        return any(s in field.lower() for s in sensitive_fields)


# Common patterns
_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")
_INT_ID_PATTERN = re.compile(r"^[1-9][0-9]{0,9}$")
_SAFE_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{1,255}$")
_NO_PATH_TRAVERSAL = re.compile(r"^(?!.*(\.\.\/|\/\.\.|\.\.|%2e%2e|%252e))")
_ALNUM_ONLY = re.compile(r"^[a-zA-Z0-9]+$")

# Dangerous characters for injection detection
_DANGEROUS_CHARS = {
    "sql": ("'", '"', ";", "--", "/*", "*/", "\\", "\x00"),
    "xss": ("<", ">", "&", "javascript:", "onerror=", "onload=", "onclick="),
    "path": ("../", "..\\", "/", "\\", "%2e", "%252e"),
    "shell": ("|", "&", ";", "$", "`", "\n", "\r", "<", ">"),
}

# Maximum lengths for common fields
_MAX_ID_LENGTH = 128
_MAX_STRING_LENGTH = 10000
_MAX_TAG_LENGTH = 100
_MAX_TAGS_COUNT = 50
_MAX_LIST_LENGTH = 1000


def validate_id(raw: Any, field: str = "id") -> str:
    """Validate a resource ID.

    Rules:
    - Must be non-empty string
    - Only alphanumeric, underscore, hyphen
    - Max 128 characters
    - No path traversal characters

    Args:
        raw: The value to validate
        field: Field name for error messages

    Returns:
        Validated and normalized ID string

    Raises:
        ValidationError if invalid
    """
    if raw is None:
        raise ValidationError(field, "is required")

    text = str(raw).strip()
    if not text:
        raise ValidationError(field, "is required (empty after trimming)")

    if len(text) > _MAX_ID_LENGTH:
        raise ValidationError(field, f"too long (max {_MAX_ID_LENGTH} characters)")

    if not _ID_PATTERN.fullmatch(text):
        raise ValidationError(
            field,
            "invalid format: only letters, numbers, underscore, and hyphen allowed",
        )

    # Check for path traversal
    if ".." in text or "/" in text or "\\" in text:
        raise ValidationError(field, "contains forbidden path traversal characters")

    return text


def validate_int_id(raw: Any, field: str = "id") -> int:
    """Validate an integer resource ID.

    Rules:
    - Must be positive integer
    - Range: 1 to 10^9

    Args:
        raw: The value to validate
        field: Field name for error messages

    Returns:
        Validated integer ID

    Raises:
        ValidationError if invalid
    """
    if raw is None:
        raise ValidationError(field, "is required")

    # Handle string input
    text = str(raw).strip()
    if not text:
        raise ValidationError(field, "is required")

    # Check format before conversion
    if not _INT_ID_PATTERN.fullmatch(text):
        raise ValidationError(
            field,
            "must be a positive integer between 1 and 10^9",
        )

    try:
        value = int(text)
    except ValueError:
        raise ValidationError(field, "must be an integer")

    if value <= 0:
        raise ValidationError(field, "must be positive")

    if value > 10**9:
        raise ValidationError(field, "too large (max 10^9)")

    return value


def validate_optional_int_id(raw: Any, field: str = "id") -> int | None:
    """Validate an optional integer ID."""
    if raw is None or str(raw).strip() == "":
        return None
    return validate_int_id(raw, field)


def validate_string(
    raw: Any,
    field: str,
    *,
    max_length: int = _MAX_STRING_LENGTH,
    min_length: int = 0,
    allowed_chars: str | None = None,
    forbidden_chars: set[str] | None = None,
    pattern: str | None = None,
    check_injection: bool = True,
) -> str:
    """Validate a string field.

    Args:
        raw: The value to validate
        field: Field name for error messages
        max_length: Maximum allowed length
        min_length: Minimum required length
        allowed_chars: Regex pattern for allowed characters
        forbidden_chars: Set of forbidden characters
        pattern: Full regex pattern to match
        check_injection: Whether to check for injection attacks

    Returns:
        Validated and trimmed string

    Raises:
        ValidationError if invalid
    """
    if raw is None:
        raise ValidationError(field, "is required")

    text = str(raw).strip()
    if len(text) < min_length:
        raise ValidationError(field, f"too short (min {min_length} characters)")
    if len(text) > max_length:
        raise ValidationError(field, f"too long (max {max_length} characters)")

    # Check allowed characters
    if allowed_chars is not None:
        if not re.fullmatch(allowed_chars, text):
            raise ValidationError(field, "contains invalid characters")

    # Check forbidden characters
    if forbidden_chars is not None:
        found = [c for c in forbidden_chars if c in text]
        if found:
            raise ValidationError(field, f"contains forbidden characters: {found}")

    # Check pattern
    if pattern is not None:
        if not re.fullmatch(pattern, text):
            raise ValidationError(field, "does not match required pattern")

    # Check for injection attacks
    if check_injection:
        # SQL injection
        sql_chars = [c for c in _DANGEROUS_CHARS["sql"] if c in text]
        if sql_chars and not _is_sql_safe(text):
            raise ValidationError(
                field,
                "potentially contains SQL injection patterns",
            )

        # XSS
        xss_chars = [c for c in _DANGEROUS_CHARS["xss"] if c.lower() in text.lower()]
        if xss_chars:
            raise ValidationError(
                field,
                "potentially contains XSS patterns",
            )

        # Path traversal
        if any(c in text for c in _DANGEROUS_CHARS["path"]):
            raise ValidationError(
                field,
                "contains path traversal characters",
            )

    return text


def _is_sql_safe(text: str) -> bool:
    """Check if text is SQL-safe despite having some SQL characters.

    For example, "user's profile" is safe, but "'; DROP TABLE --" is not.
    """
    # Simple heuristic: if text has balanced quotes and no SQL keywords
    sql_keywords = {
        "select", "insert", "update", "delete", "drop", "create",
        "alter", "exec", "execute", "union", "where", "from",
    }
    lower_text = text.lower()
    return not any(kw in lower_text for kw in sql_keywords)


def validate_filename(raw: Any, field: str = "filename") -> str:
    """Validate a filename for safe storage.

    Rules:
    - No path traversal
    - Safe characters only
    - Max 255 characters
    """
    text = validate_string(
        raw,
        field,
        max_length=255,
        check_injection=False,  # Filename handled separately
    )

    # Check path traversal
    if not _NO_PATH_TRAVERSAL.match(text):
        raise ValidationError(field, "contains path traversal characters")

    # Check safe filename pattern
    if not _SAFE_FILENAME_PATTERN.fullmatch(text):
        # Try to sanitize
        sanitized = re.sub(r"[^a-zA-Z0-9_.-]", "_", text)
        if not sanitized:
            raise ValidationError(field, "invalid filename")
        return sanitized

    return text


def validate_tag(raw: Any, field: str = "tag") -> str:
    """Validate a user-provided tag/label.

    Rules:
    - Max 100 characters
    - No injection patterns
    - Alphanumeric with spaces and Chinese characters
    """
    # Allow Chinese characters, alphanumeric, and spaces
    chinese_alnum_pattern = r"^[a-zA-Z0-9一-鿿\s\-_]+$"

    return validate_string(
        raw,
        field,
        max_length=_MAX_TAG_LENGTH,
        min_length=1,
        pattern=chinese_alnum_pattern,
        check_injection=True,
    )


def validate_tags_list(raw: Any, field: str = "tags") -> list[str]:
    """Validate a list of tags.

    Rules:
    - Must be a list
    - Max 50 tags
    - Each tag must be valid
    """
    if raw is None:
        raise ValidationError(field, "is required")

    if not isinstance(raw, list):
        raise ValidationError(field, "must be a list")

    if len(raw) > _MAX_TAGS_COUNT:
        raise ValidationError(field, f"too many tags (max {_MAX_TAGS_COUNT})")

    validated = []
    for i, tag in enumerate(raw):
        validated.append(validate_tag(tag, f"{field}[{i}]"))

    return validated


def validate_list(
    raw: Any,
    field: str,
    *,
    max_length: int = _MAX_LIST_LENGTH,
    min_length: int = 0,
    item_validator: callable | None = None,
    item_type: type | None = None,
) -> list[Any]:
    """Validate a list field.

    Args:
        raw: The value to validate
        field: Field name for error messages
        max_length: Maximum number of items
        min_length: Minimum number of items
        item_validator: Function to validate each item
        item_type: Type to check for each item

    Returns:
        Validated list

    Raises:
        ValidationError if invalid
    """
    if raw is None:
        raise ValidationError(field, "is required")

    if not isinstance(raw, list):
        raise ValidationError(field, "must be a list")

    if len(raw) < min_length:
        raise ValidationError(field, f"too few items (min {min_length})")
    if len(raw) > max_length:
        raise ValidationError(field, f"too many items (max {max_length})")

    if item_type is not None:
        for i, item in enumerate(raw):
            if not isinstance(item, item_type):
                raise ValidationError(
                    f"{field}[{i}]",
                    f"must be of type {item_type.__name__}",
                )

    if item_validator is not None:
        validated = []
        for i, item in enumerate(raw):
            validated.append(item_validator(item, f"{field}[{i}]"))
        return validated

    return raw


def validate_dict(
    raw: Any,
    field: str,
    *,
    max_keys: int = 100,
    required_keys: set[str] | None = None,
    allowed_keys: set[str] | None = None,
    key_pattern: str | None = None,
) -> dict[str, Any]:
    """Validate a dictionary field.

    Args:
        raw: The value to validate
        field: Field name for error messages
        max_keys: Maximum number of keys
        required_keys: Set of required keys
        allowed_keys: Set of allowed keys (others rejected)
        key_pattern: Regex pattern for key names

    Returns:
        Validated dict

    Raises:
        ValidationError if invalid
    """
    if raw is None:
        raise ValidationError(field, "is required")

    if not isinstance(raw, dict):
        raise ValidationError(field, "must be a dictionary")

    if len(raw) > max_keys:
        raise ValidationError(field, f"too many keys (max {max_keys})")

    # Validate keys
    for key in raw.keys():
        if not isinstance(key, str):
            raise ValidationError(field, "keys must be strings")

        if key_pattern is not None and not re.fullmatch(key_pattern, key):
            raise ValidationError(f"{field}.{key}", "invalid key format")

        # Check for key injection
        if any(c in key for c in {"'", '"', ".", "/", "\\", "\x00"}):
            raise ValidationError(f"{field}.{key}", "key contains forbidden characters")

    # Check required keys
    if required_keys is not None:
        missing = required_keys - set(raw.keys())
        if missing:
            raise ValidationError(field, f"missing required keys: {missing}")

    # Check allowed keys
    if allowed_keys is not None:
        extra = set(raw.keys()) - allowed_keys
        if extra:
            raise ValidationError(field, f"unknown keys: {extra}")

    return raw


def validate_phone(raw: Any, field: str = "phone") -> str:
    """Validate a phone number (Chinese mainland format).

    Already implemented in auth_common.py, this is a wrapper for consistency.
    """
    from .auth_common import require_cn_phone, AuthRouteError

    try:
        return require_cn_phone(raw)
    except AuthRouteError as e:
        raise ValidationError(field, e.message)


def validate_code(raw: Any, field: str = "code") -> str:
    """Validate a verification code (6 digits).

    Already implemented in auth_common.py, this is a wrapper for consistency.
    """
    from .auth_common import require_code, AuthRouteError

    try:
        return require_code(raw)
    except AuthRouteError as e:
        raise ValidationError(field, e.message)


def validate_assessment_id(raw: Any, field: str = "assessment_id") -> str:
    """Validate an assessment ID with type prefix.

    Allowed prefixes: mbti_, attachment_, big_five_, sternberg_
    """
    text = validate_id(raw, field)

    # Valid prefixes
    valid_prefixes = ("mbti_", "attachment_", "big_five_", "sternberg_")
    if not any(text.startswith(prefix) for prefix in valid_prefixes):
        raise ValidationError(
            field,
            f"invalid assessment type prefix: must start with {valid_prefixes}",
        )

    # No path traversal in the suffix
    suffix = text.split("_", 1)[-1] if "_" in text else ""
    if ".." in suffix or "/" in suffix:
        raise ValidationError(field, "contains forbidden characters in ID suffix")

    return text


def validate_url_path_segment(raw: Any, field: str = "segment") -> str:
    """Validate a URL path segment (for route parameters).

    Rules:
    - No path traversal
    - No special URL characters
    - Safe for URL encoding
    """
    text = str(raw).strip()
    if not text:
        raise ValidationError(field, "is required")

    # URL path safe characters
    url_safe_pattern = r"^[a-zA-Z0-9_.~-]+$"
    if not re.fullmatch(url_safe_pattern, text):
        raise ValidationError(field, "contains invalid URL characters")

    return text


# Convenience function for route handlers
def validate_request_body(
    body: dict[str, Any],
    schema: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Validate request body against a schema.

    Args:
        body: The request body dict
        schema: Schema definition:
            {
                "field_name": {
                    "validator": validate_int_id,
                    "required": True,
                    "default": None,  # optional default
                },
            }

    Returns:
        Validated body with defaults applied

    Raises:
        ValidationError if any field invalid
    """
    validated = {}

    for field_name, field_spec in schema.items():
        required = field_spec.get("required", False)
        default = field_spec.get("default")
        validator = field_spec.get("validator")

        raw_value = body.get(field_name)

        if raw_value is None:
            if default is not None:
                validated[field_name] = default
            elif required:
                raise ValidationError(field_name, "is required")
            else:
                validated[field_name] = None
        elif validator is not None:
            validated[field_name] = validator(raw_value, field_name)
        else:
            validated[field_name] = raw_value

    # Check for unknown fields if schema is strict
    if field_spec.get("_strict", False):
        unknown = set(body.keys()) - set(schema.keys())
        if unknown:
            raise ValidationError("body", f"unknown fields: {unknown}")

    return validated


__all__ = [
    "ValidationError",
    "validate_id",
    "validate_int_id",
    "validate_optional_int_id",
    "validate_string",
    "validate_filename",
    "validate_tag",
    "validate_tags_list",
    "validate_list",
    "validate_dict",
    "validate_phone",
    "validate_code",
    "validate_assessment_id",
    "validate_url_path_segment",
    "validate_request_body",
    "_MAX_ID_LENGTH",
    "_MAX_STRING_LENGTH",
    "_MAX_TAG_LENGTH",
    "_MAX_TAGS_COUNT",
    "_MAX_LIST_LENGTH",
]