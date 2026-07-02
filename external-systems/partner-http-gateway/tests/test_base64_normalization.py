"""Tests for Base64 normalization in verification_routes.

CRITICAL: This test validates the fix for "Failed to decode Base64: Incorrect padding"
           (issue where video verification submission fails due to non-standard Base64 formats)
"""

import base64
import pytest

from gateway.verification_routes import _normalize_base64


class TestNormalizeBase64:
    """Test Base64 normalization for various input formats."""

    def test_wrong_padding_corrected(self):
        """Base64 with wrong padding should be corrected.

        Example: 'AAAAAA=' (remainder 2 + wrong 1 '=')
        Should become: 'AAAAAA==' (remainder 2 + correct 2 '=')
        """
        import base64

        # Case 1: remainder 2 with 1 wrong padding
        wrong_padding_1 = "AAAAAA="  # Length 7, should have 2 '='
        normalized = _normalize_base64(wrong_padding_1)
        assert normalized == "AAAAAA=="
        assert base64.b64decode(normalized) == base64.b64decode("AAAAAA==")

        # Case 2: remainder 2 with 3 wrong padding
        wrong_padding_2 = "AAAAAA==="  # Length 9, should have 2 '='
        normalized = _normalize_base64(wrong_padding_2)
        assert normalized == "AAAAAA=="

        # Case 3: remainder 0 with wrong padding
        wrong_padding_3 = "AAAA="  # Length 5, should have 0 '='
        normalized = _normalize_base64(wrong_padding_3)
        assert normalized == "AAAA"

    def test_existing_valid_padding_preserved(self):
        """Base64 with correct padding should work correctly."""
        import base64

        # Correct padding should be preserved after normalization
        correct_padding_1 = "SGVsbG8gV29ybGQ="  # "Hello World"
        normalized = _normalize_base64(correct_padding_1)
        # Note: normalization strips and recalculates, but result should decode correctly
        decoded = base64.b64decode(normalized)
        assert decoded == b"Hello World"

        correct_padding_2 = "SGVsbG8gV29ybGQ=="  # Might be over-padded
        normalized = _normalize_base64(correct_padding_2)
        decoded = base64.b64decode(normalized)
        # Should still decode to same content
        assert decoded == b"Hello World"

    def test_invalid_length_remainder_1(self):
        """Base64 with length % 4 == 1 (invalid, indicates corruption) should be truncated.

        CRITICAL: This tests the fix for the real-world error:
        "number of data characters (1597689) cannot be 1 more than a multiple of 4"
        """
        import base64
        # Create a valid Base64 string first
        original_data = b"This is a test video recording content for validation"
        valid_b64 = base64.b64encode(original_data).decode()

        # Simulate corruption: add 1 extra character (making length % 4 == 1)
        corrupted_b64 = valid_b64 + "A"  # Extra character
        assert len(corrupted_b64) % 4 == 1

        # Normalize should truncate the last character
        normalized = _normalize_base64(corrupted_b64)

        # Should be valid now (length % 4 == 0)
        assert len(normalized) % 4 == 0

        # Should decode successfully (may lose last byte due to truncation)
        decoded = base64.b64decode(normalized)
        # The decoded data should be close to original (may lose up to 2 bytes)
        assert decoded[:len(original_data) - 2] == original_data[:len(original_data) - 2]

    def test_large_invalid_base64_real_world_case(self):
        """Test the actual error case from production: 1597689 characters.

        This simulates the exact error the user encountered.
        """
        import base64
        # Simulate the production case: 1597689 characters (remainder 1)
        large_b64 = "A" * 1597689

        # Should normalize without crash
        normalized = _normalize_base64(large_b64)

        # Should be valid length now
        assert len(normalized) % 4 == 0
        assert len(normalized) == 1597688  # Truncated by 1 character

        # Should decode successfully
        decoded = base64.b64decode(normalized)
        assert len(decoded) > 0

    def test_standard_base64_with_padding(self):
        """Standard Base64 with correct padding should pass unchanged."""
        # Standard Base64 (length is multiple of 4, has padding)
        original = "SGVsbG8gV29ybGQ="  # "Hello World"
        normalized = _normalize_base64(original)
        assert normalized == original
        assert base64.b64decode(normalized) == b"Hello World"

    def test_standard_base64_without_padding(self):
        """Base64 without padding should get padding added."""
        # Base64 without padding (length 11, needs 1 '=' to reach 12)
        original = "SGVsbG8gV29ybGQ"  # "Hello World" without padding
        normalized = _normalize_base64(original)
        assert normalized == "SGVsbG8gV29ybGQ="
        assert base64.b64decode(normalized) == b"Hello World"

    def test_base64_needing_double_padding(self):
        """Base64 needing 2 '=' characters should work.

        Note: Length % 4 == 2 → needs 2 '=' padding
        Example: 'Hello W' (7 bytes) → 'SGVsbG8gVw==' (12 chars, 2 padding)
        """
        # Create a Base64 without padding that needs 2 '='
        import base64
        original_encoded = base64.b64encode(b'Hello W').decode()
        # original_encoded = 'SGVsbG8gVw==' (has padding)
        # Remove padding to simulate problematic input
        original = original_encoded.rstrip('=')
        # original = 'SGVsbG8gVw' (length 10, 10 % 4 = 2)

        normalized = _normalize_base64(original)
        # Should add 2 '=' back
        assert normalized == original_encoded
        assert base64.b64decode(normalized) == b'Hello W'

    def test_base64_needing_single_padding(self):
        """Base64 needing 1 '=' character should work.

        Note: Length % 4 == 3 → needs 1 '=' padding
        Example: 'Hello Wo' (8 bytes) → 'SGVsbG8gV28=' (12 chars, 1 padding)
        """
        # Create a Base64 without padding that needs 1 '='
        import base64
        original_encoded = base64.b64encode(b'Hello Wo').decode()
        # original_encoded = 'SGVsbG8gV28=' (has padding)
        # Remove padding to simulate problematic input
        original = original_encoded.rstrip('=')
        # original = 'SGVsbG8gV28' (length 11, 11 % 4 = 3)

        normalized = _normalize_base64(original)
        # Should add 1 '=' back
        assert normalized == original_encoded
        assert base64.b64decode(normalized) == b'Hello Wo'

    def test_url_safe_base64(self):
        """URL-safe Base64 (with - and _) should be converted to standard."""
        # URL-safe Base64: uses '-' instead of '+', '_' instead of '/'
        url_safe = "SGVsbG8gV29ybGQ_"  # Simulated URL-safe variant
        normalized = _normalize_base64(url_safe)
        assert "_" in url_safe
        assert "/" in normalized  # Should convert _ to /
        assert "-" not in normalized
        assert "+" not in normalized

    def test_base64_with_whitespace(self):
        """Base64 with whitespace/newlines should be cleaned."""
        # Base64 with spaces and newlines
        original = "SGVs\n bG8g V29ybGQ="
        normalized = _normalize_base64(original)
        assert "\n" not in normalized
        assert " " not in normalized
        assert normalized == "SGVsbG8gV29ybGQ="
        assert base64.b64decode(normalized) == b"Hello World"

    def test_data_url_prefix(self):
        """Base64 with data URL prefix should have prefix removed."""
        # Data URL format: data:video/webm;base64,<actual_base64>
        data_url = "data:video/webm;base64,SGVsbG8gV29ybGQ="
        normalized = _normalize_base64(data_url)
        assert not normalized.startswith("data:")
        assert normalized == "SGVsbG8gV29ybGQ="
        assert base64.b64decode(normalized) == b"Hello World"

    def test_data_url_prefix_with_jpeg(self):
        """Data URL with different MIME type should also work."""
        data_url = "data:image/jpeg;base64,SGVsbG8gV29ybGQ="
        normalized = _normalize_base64(data_url)
        assert normalized == "SGVsbG8gV29ybGQ="
        assert base64.b64decode(normalized) == b"Hello World"

    def test_combined_issues(self):
        """Base64 with multiple issues (URL-safe + no padding + whitespace) should work."""
        # Combined: URL-safe, no padding, has whitespace
        problematic = "SGVs bG8g V29y bGQ"  # No padding, has spaces
        normalized = _normalize_base64(problematic)
        assert " " not in normalized
        assert normalized.endswith("=")  # Should have padding added
        # Should decode successfully
        decoded = base64.b64decode(normalized)
        assert decoded == b"Hello World"

    def test_empty_string(self):
        """Empty string should return empty (no crash)."""
        normalized = _normalize_base64("")
        assert normalized == ""

    def test_actual_video_base64_sample(self):
        """Test with actual video Base64 sample (WebM header)."""
        # Real WebM header Base64 (from test stub in verification.ts)
        # Note: This is truncated/minimal, just for testing format handling
        webm_header = "GkXfo59ChoEBQveBAULygQRC84EIQoKEd2VibUKHgQRChYECGFOAZwEAAAAAAAHTEU2bdLpNu4tAA5"
        normalized = _normalize_base64(webm_header)

        # Length 76, which is divisible by 4, so no padding needed
        # But we'll add if needed
        assert len(normalized) % 4 == 0

        # Should decode without error
        decoded = base64.b64decode(normalized)
        assert len(decoded) > 0

    def test_long_base64_needing_padding(self):
        """Test long Base64 string that needs padding.

        Note: Base64 length that's already multiple of 4 doesn't need padding.
        """
        # Create a Base64 string that's already multiple of 4
        # Original data: "This is a test video recording" (31 bytes)
        # Base64 encoded: "VGhpcyBpcyBhIHRlc3QgdmlkZW8gcmVjb3JkaW5n" (44 chars, already multiple of 4)
        long_b64 = "VGhpcyBpcyBhIHRlc3QgdmlkZW8gcmVjb3JkaW5n"
        normalized = _normalize_base64(long_b64)

        # Should NOT add padding (44 is already multiple of 4)
        assert len(normalized) % 4 == 0
        assert normalized == long_b64  # Should be unchanged

        # Should decode successfully
        decoded = base64.b64decode(normalized)
        assert decoded == b"This is a test video recording"


class TestBase64DecodingInSubmitLiveVideo:
    """Integration test for Base64 decoding in submit_live_video endpoint.

    Note: This requires mocking the gateway and full request context.
          For now, we test the normalization function directly.
    """

    def test_base64_decode_success_after_normalization(self):
        """Verify that problematic Base64 can be decoded after normalization."""
        # Simulate a Base64 string that would fail without normalization
        problematic = "SGVsbG8gV29ybGQ"  # Missing padding

        # Without normalization, this would raise "Incorrect padding"
        with pytest.raises(Exception):  # base64.binascii.Error
            base64.b64decode(problematic)

        # With normalization, it should work
        normalized = _normalize_base64(problematic)
        decoded = base64.b64decode(normalized)
        assert decoded == b"Hello World"

    def test_url_safe_decode_success(self):
        """Verify URL-safe Base64 can be decoded after normalization."""
        # URL-safe Base64 (would fail with standard b64decode)
        url_safe = "SGVsbG8gV29ybGQ-"  # '-' instead of '+'

        # Normalize and decode
        normalized = _normalize_base64(url_safe)
        decoded = base64.b64decode(normalized)
        # Note: '-' → '+' conversion, but actual decoding depends on content
        assert len(decoded) > 0