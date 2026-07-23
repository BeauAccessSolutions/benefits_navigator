"""
Field-level encryption for sensitive PII data.
Uses Fernet (AES-256) encryption.

Security Notes:
- FIELD_ENCRYPTION_KEY should be set in environment for all deployments
- Key must be a 32-byte base64-encoded string (Fernet format)
- Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
- Key rotation requires data migration - see encrypt_existing_data() utility
"""

import base64
import hashlib
import logging
import warnings

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)


def _get_encryption_key() -> bytes:
    """
    Get the encryption key from settings.

    Priority:
    1. FIELD_ENCRYPTION_KEY environment variable (recommended)
    2. Derived from SECRET_KEY (legacy fallback, warns in non-DEBUG)

    Returns:
        32-byte base64-encoded key suitable for Fernet
    """
    # Check for dedicated encryption key (preferred)
    encryption_key = getattr(settings, "FIELD_ENCRYPTION_KEY", None)

    if encryption_key:
        # Validate it's a proper Fernet key
        try:
            # Fernet keys are 32 bytes, base64-encoded (44 chars with padding)
            decoded = base64.urlsafe_b64decode(encryption_key)
            if len(decoded) != 32:
                raise ValueError("FIELD_ENCRYPTION_KEY must be 32 bytes when decoded")
            return (
                encryption_key.encode()
                if isinstance(encryption_key, str)
                else encryption_key
            )
        except Exception as e:
            raise ValueError(
                f"Invalid FIELD_ENCRYPTION_KEY: {e}. "
                'Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
            )

    # Fallback to SECRET_KEY derivation (legacy)
    if not getattr(settings, "DEBUG", False):
        warnings.warn(
            "FIELD_ENCRYPTION_KEY not set - deriving from SECRET_KEY. "
            "Set FIELD_ENCRYPTION_KEY for better security and key rotation support.",
            UserWarning,
        )

    # Derive a 32-byte key from SECRET_KEY
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return base64.urlsafe_b64encode(key)


class FieldEncryption:
    """
    Handles encryption/decryption of field values using Fernet.

    Uses FIELD_ENCRYPTION_KEY if set, otherwise derives from SECRET_KEY.
    """

    _fernet = None
    _key_hash = None  # Track key changes for cache invalidation

    @classmethod
    def _get_fernet(cls) -> Fernet:
        """Get or create Fernet instance."""
        key = _get_encryption_key()
        key_hash = hashlib.md5(key, usedforsecurity=False).hexdigest()

        # Invalidate cache if key changed (useful for testing)
        if cls._fernet is None or cls._key_hash != key_hash:
            cls._fernet = Fernet(key)
            cls._key_hash = key_hash

        return cls._fernet

    @classmethod
    def reset(cls):
        """Reset the cached Fernet instance. Useful for testing."""
        cls._fernet = None
        cls._key_hash = None

    @classmethod
    def encrypt(cls, value: str) -> str:
        """
        Encrypt a string value.

        Args:
            value: Plain text string to encrypt

        Returns:
            Base64-encoded encrypted string
        """
        if not value:
            return ""

        fernet = cls._get_fernet()
        encrypted = fernet.encrypt(value.encode("utf-8"))
        return base64.urlsafe_b64encode(encrypted).decode("utf-8")

    @classmethod
    def decrypt(cls, encrypted_value: str) -> str:
        """
        Decrypt an encrypted string value.

        Args:
            encrypted_value: Base64-encoded encrypted string

        Returns:
            Decrypted plain text string
        """
        if not encrypted_value:
            return ""

        try:
            fernet = cls._get_fernet()
            decoded = base64.urlsafe_b64decode(encrypted_value.encode("utf-8"))
            decrypted = fernet.decrypt(decoded)
            return decrypted.decode("utf-8")
        except (InvalidToken, ValueError) as e:
            logger.warning(f"Decryption failed: {e}")
            # Return empty string on decryption failure
            # This handles cases where data was stored unencrypted
            return ""


class EncryptedCharField(models.CharField):
    """
    CharField that transparently encrypts/decrypts values.

    Usage:
        va_file_number = EncryptedCharField(max_length=255, blank=True)

    The max_length should be larger than the plain text max length
    since encrypted values are longer (roughly 2x + overhead).
    """

    description = "An encrypted CharField"

    def __init__(self, *args, **kwargs):
        # Encrypted values are longer, so increase max_length
        # Rule of thumb: original_length * 2 + 100 for overhead
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value):
        """Encrypt value before saving to database."""
        if value is None or value == "":
            return value
        return FieldEncryption.encrypt(str(value))

    def from_db_value(self, value, expression, connection):
        """Decrypt value when reading from database."""
        if value is None or value == "":
            return value
        return FieldEncryption.decrypt(value)

    def to_python(self, value):
        """Handle value conversion from form input."""
        if isinstance(value, str) and value:
            # Try to decrypt - if it fails, it's probably plain text from a form
            # This is safer than heuristic detection (checking for Z0FB prefix)
            decrypted = FieldEncryption.decrypt(value)
            if decrypted:
                return decrypted
            # If decryption returned empty string, treat as plain text input
        return value


class EncryptedTextField(models.TextField):
    """
    TextField that transparently encrypts/decrypts values.

    Usage:
        notes = EncryptedTextField(blank=True)
    """

    description = "An encrypted TextField"

    def get_prep_value(self, value):
        """Encrypt value before saving to database."""
        if value is None or value == "":
            return value
        return FieldEncryption.encrypt(str(value))

    def from_db_value(self, value, expression, connection):
        """Decrypt value when reading from database."""
        if value is None or value == "":
            return value
        return FieldEncryption.decrypt(value)

    def to_python(self, value):
        """Handle value conversion from form input."""
        if isinstance(value, str) and value:
            # Try to decrypt - if it fails, it's probably plain text from a form
            decrypted = FieldEncryption.decrypt(value)
            if decrypted:
                return decrypted
        return value


class EncryptedJSONField(models.TextField):
    """
    TextField that transparently encrypts/decrypts JSON values.

    Stores JSON data as encrypted text. On read, decrypts and deserializes
    back to Python dict/list. Preserves the Python dict/list interface
    while encrypting at rest.

    Usage:
        ai_summary = EncryptedJSONField('AI summary', null=True, blank=True)

    Trade-off: Loses database-level JSON querying (PostgreSQL -> operator).
    Only use when you read ai_summary after fetching the object — no
    JSON path queries in WHERE clauses.
    """

    description = "An encrypted JSON field"

    def get_prep_value(self, value):
        """Serialize to JSON string, then encrypt before saving."""
        import json

        if value is None:
            return None
        try:
            json_str = json.dumps(value)
        except (TypeError, ValueError):
            json_str = str(value)
        return FieldEncryption.encrypt(json_str)

    def from_db_value(self, value, expression, connection):
        """Decrypt, then deserialize JSON when reading from database."""
        import json

        if value is None or value == "":
            return None
        decrypted = FieldEncryption.decrypt(value)
        if not decrypted:
            return None
        try:
            return json.loads(decrypted)
        except (json.JSONDecodeError, ValueError):
            return None

    def to_python(self, value):
        """Handle value conversion from form input or already-parsed values."""
        import json

        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str) and value:
            # Try JSON parse first (form input)
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                pass
            # Try decrypt then parse (encrypted value)
            decrypted = FieldEncryption.decrypt(value)
            if decrypted:
                try:
                    return json.loads(decrypted)
                except (json.JSONDecodeError, ValueError):
                    pass
        return value


class EncryptedDateField(models.CharField):
    """
    A date field that stores encrypted date strings.

    Stores dates as encrypted ISO format strings (YYYY-MM-DD).
    Returns Python date objects when accessed.

    Usage:
        date_of_birth = EncryptedDateField(blank=True, null=True)
    """

    description = "An encrypted date field for sensitive dates like DOB"

    def __init__(self, *args, **kwargs):
        # Store as varchar(255) to accommodate encrypted data
        kwargs["max_length"] = 255
        kwargs.pop("auto_now", None)
        kwargs.pop("auto_now_add", None)
        super().__init__(*args, **kwargs)

    def get_prep_value(self, value):
        """Encrypt date value before saving to database."""
        from datetime import date

        if value is None:
            return None

        if isinstance(value, date):
            date_str = value.isoformat()
        elif isinstance(value, str) and value:
            date_str = value
        else:
            return None

        return FieldEncryption.encrypt(date_str)

    def from_db_value(self, value, expression, connection):
        """Decrypt value and convert to date when reading from database."""
        from datetime import date

        if value is None or value == "":
            return None

        decrypted = FieldEncryption.decrypt(value)
        if not decrypted:
            return None

        try:
            return date.fromisoformat(decrypted)
        except ValueError:
            return None

    def to_python(self, value):
        """Handle value conversion for forms."""
        from datetime import date

        if value is None or value == "":
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            # First try parsing as ISO date (form input)
            try:
                return date.fromisoformat(value)
            except ValueError:
                pass

            # Try to decrypt (may be encrypted value from DB or form)
            decrypted = FieldEncryption.decrypt(value)
            if decrypted:
                try:
                    return date.fromisoformat(decrypted)
                except ValueError:
                    return None
        return None


def mask_pii(value: str, show_last: int = 4, mask_char: str = "*") -> str:
    """
    Mask a PII value for display, showing only the last N characters.

    Args:
        value: The value to mask
        show_last: Number of characters to show at the end
        mask_char: Character to use for masking

    Returns:
        Masked string like "****1234"
    """
    if not value or len(value) <= show_last:
        return mask_char * 4

    masked_length = len(value) - show_last
    return mask_char * masked_length + value[-show_last:]


def encrypt_existing_data(model_class, field_name: str, dry_run: bool = True):
    """
    Utility function to encrypt existing unencrypted data.

    Use this in a data migration or management command.

    Args:
        model_class: Django model class
        field_name: Name of the field to encrypt
        dry_run: If True, only report what would be done
    """
    from django.db import connection

    # Get raw values directly from database to avoid model decryption
    table_name = model_class._meta.db_table
    pk_name = model_class._meta.pk.name

    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {pk_name}, {field_name} FROM {table_name} WHERE {field_name} IS NOT NULL AND {field_name} != ''"
        )
        rows = cursor.fetchall()

    count = 0
    for pk, value in rows:
        # Skip already encrypted values (they start with base64 pattern)
        if value and len(value) > 100 and value.startswith("Z0FB"):
            continue

        encrypted = FieldEncryption.encrypt(value)

        if dry_run:
            logger.info(f"Would encrypt {model_class.__name__} pk={pk} {field_name}")
        else:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"UPDATE {table_name} SET {field_name} = %s WHERE {pk_name} = %s",
                    [encrypted, pk],
                )
        count += 1

    action = "Would encrypt" if dry_run else "Encrypted"
    logger.info(f"{action} {count} {model_class.__name__} records")
    return count
