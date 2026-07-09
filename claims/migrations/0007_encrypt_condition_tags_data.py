"""
Data migration to encrypt existing Document.condition_tags values.

Follows the 0005_encrypt_ai_summary pattern: raw cursor reads to bypass
model-level decryption, skip values that are already Fernet tokens.
"""

import json

from django.db import migrations


def _is_encrypted(value):
    return isinstance(value, str) and len(value) > 100 and value.startswith("Z0FB")


def encrypt_condition_tags(apps, schema_editor):
    from core.encryption import FieldEncryption
    from django.db import connections

    connection = connections[schema_editor.connection.alias]

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, condition_tags FROM claims_document "
            "WHERE condition_tags IS NOT NULL"
        )
        rows = cursor.fetchall()

    for pk, value in rows:
        if value is None or value == "" or _is_encrypted(value):
            continue
        json_str = value if isinstance(value, str) else json.dumps(value)
        encrypted = FieldEncryption.encrypt(json_str)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE claims_document SET condition_tags = %s WHERE id = %s",
                [encrypted, pk],
            )


def decrypt_condition_tags(apps, schema_editor):
    from core.encryption import FieldEncryption
    from django.db import connections

    connection = connections[schema_editor.connection.alias]

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, condition_tags FROM claims_document "
            "WHERE condition_tags IS NOT NULL"
        )
        rows = cursor.fetchall()

    for pk, value in rows:
        if not _is_encrypted(value):
            continue
        decrypted = FieldEncryption.decrypt(value)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE claims_document SET condition_tags = %s WHERE id = %s",
                [decrypted or "[]", pk],
            )


class Migration(migrations.Migration):

    dependencies = [
        ("claims", "0006_alter_document_ai_summary_and_more"),
    ]

    operations = [
        migrations.RunPython(encrypt_condition_tags, decrypt_condition_tags),
    ]
