"""
Tests for GraphQL schema security features.

Covers:
- PII redaction in document_analysis
- Text truncation limits
"""

from django.test import TestCase

from benefits_navigator.schema import (
    redact_pii,
    truncate_text,
    sanitize_graphql_text,
    MAX_OCR_TEXT_LENGTH,
    MAX_AI_SUMMARY_LENGTH,
)

# =============================================================================
# PII REDACTION TESTS
# =============================================================================


class TestPIIRedaction(TestCase):
    """Tests for PII redaction utilities."""

    def test_redact_ssn_with_dashes(self):
        """SSN with dashes is redacted."""
        text = "Veteran SSN: 123-45-6789"
        result = redact_pii(text)
        self.assertIn("[REDACTED:SSN]", result)
        self.assertNotIn("123-45-6789", result)

    def test_redact_ssn_with_spaces(self):
        """SSN with spaces is redacted."""
        text = "SSN 123 45 6789 on file"
        result = redact_pii(text)
        self.assertIn("[REDACTED:SSN]", result)
        self.assertNotIn("123 45 6789", result)

    def test_redact_ssn_no_separators(self):
        """SSN without separators is redacted."""
        text = "Number: 123456789"
        result = redact_pii(text)
        self.assertIn("[REDACTED:SSN]", result)
        self.assertNotIn("123456789", result)

    def test_redact_va_file_number_8_digits(self):
        """8-digit VA file number is redacted."""
        text = "VA File Number: 12345678"
        result = redact_pii(text)
        self.assertIn("[REDACTED:VA_FILE]", result)
        self.assertNotIn("12345678", result)

    def test_redact_va_file_number_9_digits(self):
        """9-digit VA file number is redacted."""
        text = "File: 123456789"
        result = redact_pii(text)
        # Note: 9 digits matches both SSN and VA_FILE patterns
        self.assertTrue("[REDACTED:SSN]" in result or "[REDACTED:VA_FILE]" in result)

    def test_redact_va_file_with_c_prefix(self):
        """VA file number with C prefix is redacted."""
        text = "VA File: C12345678"
        result = redact_pii(text)
        self.assertIn("[REDACTED:VA_FILE]", result)
        self.assertNotIn("C12345678", result)

    def test_redact_phone_number_with_parens(self):
        """Phone number with parentheses is redacted."""
        text = "Call (555) 123-4567 for info"
        result = redact_pii(text)
        self.assertIn("[REDACTED:PHONE]", result)
        self.assertNotIn("(555) 123-4567", result)

    def test_redact_phone_number_with_dashes(self):
        """Phone number with dashes is redacted."""
        text = "Phone: 555-123-4567"
        result = redact_pii(text)
        self.assertIn("[REDACTED:PHONE]", result)
        self.assertNotIn("555-123-4567", result)

    def test_redact_phone_number_with_dots(self):
        """Phone number with dots is redacted."""
        text = "Contact: 555.123.4567"
        result = redact_pii(text)
        self.assertIn("[REDACTED:PHONE]", result)
        self.assertNotIn("555.123.4567", result)

    def test_redact_credit_card(self):
        """Credit card number is redacted."""
        text = "Card: 1234-5678-9012-3456"
        result = redact_pii(text)
        self.assertIn("[REDACTED:CC]", result)
        self.assertNotIn("1234-5678-9012-3456", result)

    def test_redact_labeled_dob(self):
        """Labeled date of birth is redacted."""
        text = "Date of Birth: 01/15/1985"
        result = redact_pii(text)
        self.assertIn("[REDACTED:DOB]", result)
        self.assertNotIn("01/15/1985", result)

    def test_redact_dob_shorthand(self):
        """DOB shorthand is redacted."""
        text = "DOB: 1/15/85"
        result = redact_pii(text)
        self.assertIn("[REDACTED:DOB]", result)
        self.assertNotIn("1/15/85", result)

    def test_preserves_normal_text(self):
        """Normal text without PII is preserved."""
        text = "The veteran was granted 30% for PTSD."
        result = redact_pii(text)
        self.assertEqual(text, result)

    def test_preserves_dates_without_label(self):
        """Dates without DOB label are preserved (e.g., decision dates)."""
        text = "Decision date: 01/15/2024"
        result = redact_pii(text)
        self.assertIn("01/15/2024", result)

    def test_multiple_pii_items(self):
        """Multiple PII items are all redacted."""
        text = "SSN: 123-45-6789, Phone: 555-123-4567, VA File: C12345678"
        result = redact_pii(text)
        self.assertIn("[REDACTED:SSN]", result)
        self.assertIn("[REDACTED:PHONE]", result)
        self.assertIn("[REDACTED:VA_FILE]", result)
        self.assertNotIn("123-45-6789", result)
        self.assertNotIn("555-123-4567", result)
        self.assertNotIn("C12345678", result)

    def test_empty_string(self):
        """Empty string returns empty."""
        self.assertEqual(redact_pii(""), "")

    def test_none_returns_none(self):
        """None input returns None."""
        self.assertIsNone(redact_pii(None))


# =============================================================================
# TEXT TRUNCATION TESTS
# =============================================================================


class TestTextTruncation(TestCase):
    """Tests for text truncation utility."""

    def test_short_text_not_truncated(self):
        """Text under limit is not truncated."""
        text = "Short text"
        result = truncate_text(text, 100)
        self.assertEqual(text, result)

    def test_text_at_limit_not_truncated(self):
        """Text exactly at limit is not truncated."""
        text = "X" * 100
        result = truncate_text(text, 100)
        self.assertEqual(text, result)

    def test_text_over_limit_truncated(self):
        """Text over limit is truncated."""
        text = "X" * 200
        result = truncate_text(text, 100)
        self.assertIn("[TRUNCATED:", result)
        self.assertIn("100 characters omitted", result)
        self.assertTrue(len(result) < 200)

    def test_empty_string(self):
        """Empty string returns empty."""
        self.assertEqual(truncate_text("", 100), "")

    def test_none_returns_none(self):
        """None input returns None."""
        self.assertIsNone(truncate_text(None, 100))


# =============================================================================
# SANITIZE GRAPHQL TEXT TESTS
# =============================================================================


class TestSanitizeGraphQLText(TestCase):
    """Tests for combined sanitization function."""

    def test_redacts_and_truncates(self):
        """Both redaction and truncation are applied."""
        # Create text with PII that exceeds limit
        text = "SSN: 123-45-6789 " + "X" * 200
        result = sanitize_graphql_text(text, 100)

        # Should redact PII
        self.assertIn("[REDACTED:SSN]", result)
        self.assertNotIn("123-45-6789", result)

        # Should truncate
        self.assertIn("[TRUNCATED:", result)

    def test_redaction_happens_before_truncation(self):
        """PII is redacted before truncation (important for security)."""
        # PII at the end that might be cut off if truncation happened first
        text = "X" * 50 + " SSN: 123-45-6789"
        result = sanitize_graphql_text(text, 60)

        # PII should be redacted even if text is truncated
        self.assertNotIn("123-45-6789", result)

    def test_empty_string(self):
        """Empty string returns empty."""
        self.assertEqual(sanitize_graphql_text("", 100), "")

    def test_none_returns_none(self):
        """None input returns None."""
        self.assertIsNone(sanitize_graphql_text(None, 100))


# =============================================================================
# CONSTANTS TESTS
# =============================================================================


class TestConstants(TestCase):
    """Tests for GraphQL security constants."""

    def test_max_ocr_text_length_reasonable(self):
        """MAX_OCR_TEXT_LENGTH is set to reasonable value."""
        # Should be > 10KB for usability, < 1MB for security
        self.assertGreater(MAX_OCR_TEXT_LENGTH, 10000)
        self.assertLess(MAX_OCR_TEXT_LENGTH, 1000000)

    def test_max_ai_summary_length_reasonable(self):
        """MAX_AI_SUMMARY_LENGTH is set to reasonable value."""
        # Should be > 1KB for usability, < 100KB for security
        self.assertGreater(MAX_AI_SUMMARY_LENGTH, 1000)
        self.assertLess(MAX_AI_SUMMARY_LENGTH, 100000)
