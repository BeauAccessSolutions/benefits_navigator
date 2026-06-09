"""
Security regression tests for the controls behind privacy/marketing claims:

- Signed URL tokens: expiry, tampering, signature binding (core/signed_urls.py)
- Field encryption: round-trip + ciphertext at rest (core/encryption.py)
- GraphQL PII redaction patterns (benefits_navigator/schema.py)

Added per audits/2026-06-09 (P1-9) and docs/PRIVACY_HARDENING_PLAN.md Phase 0.
"""

import time
from unittest import mock

import pytest
from django.db import connection

from benefits_navigator.schema import redact_pii, sanitize_graphql_text
from core.encryption import FieldEncryption
from core.signed_urls import (
    InvalidTokenError,
    SignedURLGenerator,
    TokenExpiredError,
)


pytestmark = pytest.mark.unit


class TestSignedURLSecurity:
    """The HMAC token is the only credential on signed media URLs."""

    def setup_method(self):
        self.generator = SignedURLGenerator(secret_key="test-secret-key-for-signing")

    def _token(self, **overrides):
        kwargs = dict(
            resource_type="document",
            resource_id=42,
            user_id=7,
            action="download",
            expires_minutes=30,
        )
        kwargs.update(overrides)
        return self.generator.generate_token(**kwargs)

    def test_valid_token_round_trip(self):
        data = self.generator.validate_token(self._token())
        assert data["resource_id"] == 42
        assert data["user_id"] == 7
        assert data["action"] == "download"

    def test_expired_token_rejected(self):
        token = self._token(expires_minutes=1)
        with mock.patch("core.signed_urls.time.time", return_value=time.time() + 120):
            with pytest.raises(TokenExpiredError):
                self.generator.validate_token(token)

    def test_expiry_capped_at_maximum(self):
        token = self._token(expires_minutes=10_000_000)
        data = self.generator.validate_token(token)
        max_seconds = SignedURLGenerator.MAX_EXPIRES_MINUTES * 60
        assert data["expires_at"] <= time.time() + max_seconds + 5

    def test_tampered_payload_rejected(self):
        payload_b64, signature = self._token().split(".")
        # Flip a payload character: signature no longer matches
        tampered = ("A" if payload_b64[0] != "A" else "B") + payload_b64[1:]
        with pytest.raises(InvalidTokenError):
            self.generator.validate_token(f"{tampered}.{signature}")

    def test_tampered_signature_rejected(self):
        payload_b64, signature = self._token().split(".")
        tampered = ("a" if signature[-1] != "a" else "b") + signature[1:]
        with pytest.raises(InvalidTokenError):
            self.generator.validate_token(f"{payload_b64}.{tampered}")

    def test_token_bound_to_signing_key(self):
        token = self._token()
        other = SignedURLGenerator(secret_key="a-completely-different-key")
        with pytest.raises(InvalidTokenError):
            other.validate_token(token)

    def test_garbage_token_rejected(self):
        for garbage in ["", "no-dot-here", "a.b.c", "...."]:
            with pytest.raises(InvalidTokenError):
                self.generator.validate_token(garbage)


class TestEncryptionRoundTrip:
    """PII fields must survive encrypt/decrypt and be ciphertext at rest."""

    def test_field_encryption_round_trip(self):
        plaintext = "C-12345678 / SSN 123-45-6789"
        encrypted = FieldEncryption.encrypt(plaintext)
        assert encrypted != plaintext
        assert FieldEncryption.decrypt(encrypted) == plaintext

    def test_decrypt_garbage_returns_empty(self):
        assert FieldEncryption.decrypt("not-a-fernet-token") == ""

    @pytest.mark.django_db
    def test_phone_number_encrypted_at_rest(self, user):
        user.phone_number = "555-867-5309"
        user.save()

        user.refresh_from_db()
        assert user.phone_number == "555-867-5309"

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT phone_number FROM accounts_user WHERE id = %s", [user.pk]
            )
            raw = cursor.fetchone()[0]
        assert "555-867-5309" not in raw
        assert raw.startswith("Z0FB")  # double-base64 Fernet token

    @pytest.mark.django_db
    def test_condition_tags_encrypted_at_rest(self, user):
        from claims.models import Document

        doc = Document.objects.create(
            user=user,
            file_name="test.pdf",
            file_size=1024,
            mime_type="application/pdf",
            document_type="medical_records",
            condition_tags=["PTSD", "tinnitus"],
        )

        doc.refresh_from_db()
        assert doc.condition_tags == ["PTSD", "tinnitus"]

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT condition_tags FROM claims_document WHERE id = %s", [doc.pk]
            )
            raw = cursor.fetchone()[0]
        assert "PTSD" not in raw

    @pytest.mark.django_db
    def test_veteran_case_pii_encrypted_at_rest(self, user):
        from accounts.models import Organization
        from vso.models import VeteranCase

        org = Organization.objects.create(
            name="Test VSO", slug="test-vso", org_type="vso"
        )
        case = VeteranCase.objects.create(
            organization=org,
            veteran=user,
            title="Test Case",
            description="Veteran reports severe PTSD symptoms",
            conditions=[{"condition": "PTSD", "status": "pending"}],
        )

        case.refresh_from_db()
        assert case.description == "Veteran reports severe PTSD symptoms"
        assert case.conditions == [{"condition": "PTSD", "status": "pending"}]

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT description, conditions FROM vso_veterancase WHERE id = %s",
                [case.pk],
            )
            raw_description, raw_conditions = cursor.fetchone()
        assert "PTSD" not in raw_description
        assert "PTSD" not in raw_conditions


class TestGraphQLPIIRedaction:
    """redact_pii must catch every documented PII pattern."""

    @pytest.mark.parametrize(
        "text",
        [
            "SSN: 123-45-6789",
            "SSN: 123 45 6789",
            "my ssn is 123456789",
        ],
    )
    def test_ssn_formats_redacted(self, text):
        assert "123" not in redact_pii(text) or "6789" not in redact_pii(text)

    def test_va_file_number_redacted(self):
        redacted = redact_pii("VA file number C12345678 on record")
        assert "C12345678" not in redacted

    def test_clean_text_unchanged(self):
        text = "Rating decision dated January 5, 2026 grants 70 percent."
        assert redact_pii(text) == text

    def test_truncation_enforced(self):
        long_text = "x" * 60_000
        result = sanitize_graphql_text(long_text, max_length=50_000)
        assert len(result) <= 50_100  # allow for truncation marker
