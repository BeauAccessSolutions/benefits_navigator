"""
Management command to rotate the FIELD_ENCRYPTION_KEY.

Decrypts all PII fields with the old key, then re-encrypts with the new key.
Must be run BEFORE updating FIELD_ENCRYPTION_KEY in your environment.

Usage:
    # Dry run (see what would change, no writes):
    python manage.py rotate_encryption_key --old-key <OLD> --new-key <NEW>

    # Actually rotate:
    python manage.py rotate_encryption_key --old-key <OLD> --new-key <NEW> --execute

    # Generate a new Fernet key:
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

# Every encrypted field in the codebase.
# Format: (table, pk_column, field_column, is_json)
ENCRYPTED_FIELDS = [
    ("accounts_userprofile", "id", "va_file_number", False),
    ("accounts_userprofile", "id", "date_of_birth", False),
    ("agents_ratinganalysis", "id", "file_number", False),
    ("claims_document", "id", "ai_summary", True),
]


def _validate_fernet_key(key_str: str, label: str) -> Fernet:
    """Validate and return a Fernet instance for the given key string."""
    try:
        decoded = base64.urlsafe_b64decode(key_str.encode())
        if len(decoded) != 32:
            raise CommandError(
                f"{label} must be 32 bytes when base64-decoded (got {len(decoded)})"
            )
        return Fernet(key_str.encode())
    except Exception as e:
        raise CommandError(f"Invalid {label}: {e}")


class Command(BaseCommand):
    help = "Rotate FIELD_ENCRYPTION_KEY: decrypt with old key, re-encrypt with new key."

    def add_arguments(self, parser):
        parser.add_argument(
            "--old-key",
            required=True,
            help="Current FIELD_ENCRYPTION_KEY (the one data is encrypted with now)",
        )
        parser.add_argument(
            "--new-key",
            required=True,
            help="New FIELD_ENCRYPTION_KEY to re-encrypt data with",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually perform the rotation. Without this flag, dry-run only.",
        )

    def handle(self, **options):
        old_key_str = options["old_key"]
        new_key_str = options["new_key"]
        execute = options["execute"]

        if old_key_str == new_key_str:
            raise CommandError("Old and new keys are identical. Nothing to do.")

        old_fernet = _validate_fernet_key(old_key_str, "old-key")
        new_fernet = _validate_fernet_key(new_key_str, "new-key")

        mode = "EXECUTING" if execute else "DRY RUN"
        self.stdout.write(self.style.WARNING(f"\n=== Key Rotation ({mode}) ===\n"))

        total_rotated = 0
        total_failed = 0
        total_skipped = 0

        for table, pk_col, field_col, is_json in ENCRYPTED_FIELDS:
            rotated, failed, skipped = self._rotate_field(
                table,
                pk_col,
                field_col,
                is_json,
                old_fernet,
                new_fernet,
                execute,
            )
            total_rotated += rotated
            total_failed += failed
            total_skipped += skipped

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Summary: {total_rotated} rotated, {total_skipped} skipped (null/empty), "
                f"{total_failed} failed"
            )
        )

        if total_failed > 0:
            self.stdout.write(
                self.style.ERROR(
                    "Some rows failed decryption. They may be plaintext, already rotated, "
                    "or encrypted with a different key. Review the output above."
                )
            )

        if not execute:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis was a dry run. Add --execute to perform the rotation."
                )
            )

    def _rotate_field(
        self, table, pk_col, field_col, is_json, old_fernet, new_fernet, execute
    ):
        """Rotate one encrypted field. Returns (rotated, failed, skipped)."""
        self.stdout.write(f"  {table}.{field_col}:")

        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT "{pk_col}", "{field_col}" FROM "{table}" '
                f'WHERE "{field_col}" IS NOT NULL AND "{field_col}" != %s',
                [""],
            )
            rows = cursor.fetchall()

        if not rows:
            self.stdout.write("    0 rows (empty)")
            return 0, 0, 0

        rotated = 0
        failed = 0
        skipped = 0

        for pk, raw_value in rows:
            if not raw_value or not raw_value.strip():
                skipped += 1
                continue

            # Decrypt with old key
            try:
                decoded = base64.urlsafe_b64decode(raw_value.encode("utf-8"))
                plaintext_bytes = old_fernet.decrypt(decoded)
                plaintext = plaintext_bytes.decode("utf-8")
            except (InvalidToken, ValueError, Exception) as e:
                failed += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"    pk={pk}: decrypt failed ({e.__class__.__name__})"
                    )
                )
                continue

            # Re-encrypt with new key
            new_encrypted = new_fernet.encrypt(plaintext.encode("utf-8"))
            new_value = base64.urlsafe_b64encode(new_encrypted).decode("utf-8")

            if execute:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f'UPDATE "{table}" SET "{field_col}" = %s WHERE "{pk_col}" = %s',
                        [new_value, pk],
                    )
            rotated += 1

        action = "rotated" if execute else "would rotate"
        self.stdout.write(
            f"    {len(rows)} rows: {rotated} {action}, {skipped} skipped, {failed} failed"
        )
        return rotated, failed, skipped
