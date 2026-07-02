"""Input validation utilities for verification API endpoints.

This module provides validation functions for verification-related input fields,
including:
- submission_id format validation
- file size validation
- content type validation
"""

from __future__ import annotations

import re
from typing import Any


class InputValidationError(Exception):
    """Input validation error"""

    def __init__(self, field: str, reason: str):
        self.field = field
        self.reason = reason
        super().__init__(f"Validation error for {field}: {reason}")


# submission_id format pattern: vfy-{16 hex characters}
SUBMISSION_ID_PATTERN = r'^vfy-[a-f0-9]{16}$'

# Maximum file size for video uploads (50MB)
MAX_VIDEO_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Allowed content types for video uploads
ALLOWED_VIDEO_CONTENT_TYPES = {
    'video/webm',
    'video/mp4',
    'video/quicktime',
    'video/x-msvideo',
}


def validate_submission_id(submission_id: str | None) -> str:
    """
    Validate submission_id format

    Args:
        submission_id: The submission ID to validate

    Returns:
        The validated submission ID

    Raises:
        InputValidationError: If submission_id format is invalid
    """
    if submission_id is None:
        raise InputValidationError("submission_id", "submission_id is required")

    if not isinstance(submission_id, str):
        raise InputValidationError("submission_id", "submission_id must be a string")

    if len(submission_id) > 64:
        raise InputValidationError("submission_id", "submission_id must be <= 64 characters")

    if not re.match(SUBMISSION_ID_PATTERN, submission_id):
        raise InputValidationError(
            "submission_id",
            f"submission_id must match pattern: {SUBMISSION_ID_PATTERN}"
        )

    return submission_id


def validate_file_size(file_size_bytes: int) -> int:
    """
    Validate file size for video uploads

    Args:
        file_size_bytes: The file size in bytes

    Returns:
        The validated file size

    Raises:
        InputValidationError: If file size exceeds limit
    """
    if file_size_bytes <= 0:
        raise InputValidationError("file_size", "file size must be positive")

    if file_size_bytes > MAX_VIDEO_FILE_SIZE:
        max_size_mb = MAX_VIDEO_FILE_SIZE / (1024 * 1024)
        raise InputValidationError(
            "file_size",
            f"file size must be <= {max_size_mb}MB"
        )

    return file_size_bytes


def validate_content_type(content_type: str | None) -> str:
    """
    Validate content type for video uploads

    Args:
        content_type: The content type to validate

    Returns:
        The validated content type

    Raises:
        InputValidationError: If content type is not allowed
    """
    if content_type is None:
        raise InputValidationError("content_type", "content_type is required")

    if not isinstance(content_type, str):
        raise InputValidationError("content_type", "content_type must be a string")

    # Normalize content type (remove parameters)
    normalized = content_type.split(';')[0].strip().lower()

    if normalized not in ALLOWED_VIDEO_CONTENT_TYPES:
        allowed = ', '.join(sorted(ALLOWED_VIDEO_CONTENT_TYPES))
        raise InputValidationError(
            "content_type",
            f"content_type must be one of: {allowed}"
        )

    return normalized


def validate_video_upload(
    submission_id: str | None,
    file_size_bytes: int | None,
    content_type: str | None,
) -> dict[str, Any]:
    """
    Validate all fields for video upload

    Args:
        submission_id: The submission ID
        file_size_bytes: The file size in bytes
        content_type: The content type

    Returns:
        Dict with validated fields

    Raises:
        InputValidationError: If any field is invalid
    """
    validated = {}

    if submission_id is not None:
        validated["submission_id"] = validate_submission_id(submission_id)

    if file_size_bytes is not None:
        validated["file_size_bytes"] = validate_file_size(file_size_bytes)

    if content_type is not None:
        validated["content_type"] = validate_content_type(content_type)

    return validated


def parse_multipart_file(environ: dict[str, Any]) -> dict[str, Any]:
    """
    Parse multipart/form-data file upload from WSGI environ

    Args:
        environ: WSGI environ dict

    Returns:
        Dict with file data:
        - filename: str
        - content_type: str
        - file_size_bytes: int
        - file_data: bytes

    Raises:
        InputValidationError: If parsing fails or file is too large
    """
    content_type = environ.get("CONTENT_TYPE", "")
    if not content_type.startswith("multipart/form-data"):
        raise InputValidationError(
            "content_type",
            "Expected multipart/form-data"
        )

    content_length = int(environ.get("CONTENT_LENGTH", 0))

    # Validate file size before reading
    validate_file_size(content_length)

    # Parse multipart data (simplified implementation)
    # In production, use a proper multipart parser library
    try:
        from cgi import FieldStorage
        fs = FieldStorage(
            fp=environ["wsgi.input"],
            environ=environ,
            keep_blank_values=True
        )

        # Find the file field
        file_field = None
        for key in fs.keys():
            if fs[key].filename:
                file_field = fs[key]
                break

        if file_field is None:
            raise InputValidationError("file", "No file uploaded")

        filename = file_field.filename
        file_content_type = file_field.type
        file_data = file_field.file.read()

        return {
            "filename": filename,
            "content_type": file_content_type,
            "file_size_bytes": len(file_data),
            "file_data": file_data,
        }

    except Exception as e:
        raise InputValidationError("file", f"Failed to parse multipart data: {e}")


if __name__ == "__main__":
    # Test validation functions
    print("Testing input validation...")

    # Test submission_id validation
    valid_id = "vfy-a1b2c3d4e5f67890"
    validated_id = validate_submission_id(valid_id)
    print(f"Valid submission_id: {validated_id}")

    try:
        validate_submission_id("invalid-id")
    except InputValidationError as e:
        print(f"Invalid submission_id rejected: {e}")

    # Test file size validation
    try:
        validate_file_size(60 * 1024 * 1024)  # 60MB
    except InputValidationError as e:
        print(f"Large file rejected: {e}")

    # Test content type validation
    validated_ct = validate_content_type("video/webm")
    print(f"Valid content_type: {validated_ct}")

    try:
        validate_content_type("application/pdf")
    except InputValidationError as e:
        print(f"Invalid content_type rejected: {e}")

    print("✓ Input validation test passed")