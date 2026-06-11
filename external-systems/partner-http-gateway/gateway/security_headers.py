"""Security response headers middleware for the gateway.

This module adds security headers to all HTTP responses to protect against:
1. XSS attacks
2. Clickjacking
3. MIME type sniffing
4. Information disclosure

Headers added:
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- X-XSS-Protection: 1; mode=block
- Content-Security-Policy: default-src 'self'
- Strict-Transport-Security: max-age=31536000 (if HTTPS)
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy: restrict dangerous APIs
"""

from __future__ import annotations

import os
from typing import Any


# Security headers configuration
SECURITY_HEADERS = {
    # Prevent MIME type sniffing
    "X-Content-Type-Options": "nosniff",

    # Prevent clickjacking
    "X-Frame-Options": "DENY",

    # XSS protection (legacy but still useful for older browsers)
    "X-XSS-Protection": "1; mode=block",

    # Referrer policy
    "Referrer-Policy": "strict-origin-when-cross-origin",

    # Permission policy (restrict dangerous browser APIs)
    "Permissions-Policy": (
        "geolocation=(), "
        "microphone=(), "
        "camera=(), "
        "payment=(), "
        "usb=()"
    ),
}

# Content Security Policy (adjust based on your needs)
CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "  # unsafe-inline for inline styles if needed
    "img-src 'self' data: https:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "base-uri 'self'"
)

# HSTS configuration
HSTS_MAX_AGE = 31536000  # 1 year
HSTS_INCLUDE_SUBDOMAINS = True


def add_security_headers(
    response_headers: list[tuple[str, str]],
    environ: dict[str, Any],
    *,
    include_csp: bool = True,
    include_hsts: bool = True,
) -> list[tuple[str, str]]:
    """Add security headers to response headers.

    Args:
        response_headers: Existing response headers
        environ: WSGI environ dict
        include_csp: Whether to include Content-Security-Policy
        include_hsts: Whether to include Strict-Transport-Security

    Returns:
        Response headers with security headers added
    """
    headers = list(response_headers)

    # Add standard security headers
    for name, value in SECURITY_HEADERS.items():
        # Don't override if already set
        if not any(h[0].lower() == name.lower() for h in headers):
            headers.append((name, value))

    # Add Content-Security-Policy
    if include_csp:
        if not any(h[0].lower() == "content-security-policy" for h in headers):
            headers.append(("Content-Security-Policy", CSP_POLICY))

    # Add HSTS if HTTPS
    if include_hsts:
        # Check if request is HTTPS
        is_https = (
            environ.get("wsgi.url_scheme") == "https"
            or environ.get("HTTP_X_FORWARDED_PROTO", "").lower() == "https"
        )
        if is_https:
            hsts_value = f"max-age={HSTS_MAX_AGE}"
            if HSTS_INCLUDE_SUBDOMAINS:
                hsts_value += "; includeSubDomains"
            if not any(h[0].lower() == "strict-transport-security" for h in headers):
                headers.append(("Strict-Transport-Security", hsts_value))

    # Remove potentially dangerous headers
    # Some servers might add these, we want to remove them
    dangerous_headers = {"server", "x-powered-by", "x-aspnet-version"}
    headers = [(name, value) for name, value in headers if name.lower() not in dangerous_headers]

    return headers


def get_health_endpoint_headers() -> list[tuple[str, str]]:
    """Get minimal headers for health endpoint (no sensitive info)."""
    return [
        ("Content-Type", "application/json; charset=utf-8"),
        ("X-Content-Type-Options", "nosniff"),
        ("Cache-Control", "no-cache, no-store, must-revalidate"),
    ]


def get_error_response_headers(trace_id: str) -> list[tuple[str, str]]:
    """Get headers for error responses."""
    return [
        ("Content-Type", "application/json; charset=utf-8"),
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("X-Trace-ID", trace_id),
        ("Cache-Control", "no-cache, no-store, must-revalidate"),
    ]


def sanitize_server_header(environ: dict[str, Any]) -> str:
    """Return a generic server header to avoid information disclosure."""
    # Don't reveal actual server software
    return "PartnerGateway"


__all__ = [
    "SECURITY_HEADERS",
    "CSP_POLICY",
    "HSTS_MAX_AGE",
    "add_security_headers",
    "get_health_endpoint_headers",
    "get_error_response_headers",
    "sanitize_server_header",
]