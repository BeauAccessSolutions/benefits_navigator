"""
Data migration to encrypt existing phone_number values.

Follows the claims/0005_encrypt_ai_summary pattern: raw cursor reads to
bypass model-level decryption, skip values that are already Fernet tokens.
"""

from django.db import migrations


def _is_encrypted(value):
    # Fernet tokens are base64 strings starting with 'gAAA' ('Z0FB' when
    # double-encoded); plaintext phone numbers are short.
    return isinstance(value, str) and len(value) > 100 and value.startswith("Z0FB")


def encrypt_phone_numbers(apps, schema_editor):
    from core.encryption import FieldEncryption
    from django.db import connections

    connection = connections[schema_editor.connection.alias]

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, phone_number FROM accounts_user "
            "WHERE phone_number IS NOT NULL AND phone_number != ''"
        )
        rows = cursor.fetchall()

    for pk, value in rows:
        if not value or _is_encrypted(value):
            continue
        encrypted = FieldEncryption.encrypt(value)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE accounts_user SET phone_number = %s WHERE id = %s",
                [encrypted, pk],
            )


def decrypt_phone_numbers(apps, schema_editor):
    from core.encryption import FieldEncryption
    from django.db import connections

    connection = connections[schema_editor.connection.alias]

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, phone_number FROM accounts_user "
            "WHERE phone_number IS NOT NULL AND phone_number != ''"
        )
        rows = cursor.fetchall()

    for pk, value in rows:
        if not _is_encrypted(value):
            continue
        decrypted = FieldEncryption.decrypt(value)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE accounts_user SET phone_number = %s WHERE id = %s",
                [decrypted or "", pk],
            )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_alter_user_phone_number"),
    ]

    operations = [
        migrations.RunPython(encrypt_phone_numbers, decrypt_phone_numbers),
    ]
