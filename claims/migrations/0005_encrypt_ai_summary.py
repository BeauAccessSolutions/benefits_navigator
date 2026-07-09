"""
Data migration to encrypt existing ai_summary values.

Step 1: AlterField from JSONField to EncryptedJSONField (TextField in DB).
Step 2: RunPython to encrypt existing plaintext JSON data.
"""

import json

from django.db import migrations, models


def encrypt_existing_ai_summaries(apps, schema_editor):
    """Encrypt existing plaintext ai_summary values."""
    from core.encryption import FieldEncryption

    Document = apps.get_model("claims", "Document")
    db_alias = schema_editor.connection.alias

    # Read raw values directly to avoid model-level decryption
    from django.db import connections

    connection = connections[db_alias]

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, ai_summary FROM claims_document "
            "WHERE ai_summary IS NOT NULL AND ai_summary != ''"
        )
        rows = cursor.fetchall()

    for pk, value in rows:
        if not value:
            continue

        # Skip if already encrypted (encrypted values are long base64 strings)
        if isinstance(value, str) and len(value) > 100 and value.startswith("Z0FB"):
            continue

        # Value could be a JSON string or a Python-repr string from JSONField
        if isinstance(value, str):
            json_str = value
        else:
            json_str = json.dumps(value)

        encrypted = FieldEncryption.encrypt(json_str)

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE claims_document SET ai_summary = %s WHERE id = %s",
                [encrypted, pk],
            )


def decrypt_ai_summaries(apps, schema_editor):
    """Reverse: decrypt ai_summary values back to plaintext JSON."""
    from core.encryption import FieldEncryption

    from django.db import connections

    db_alias = schema_editor.connection.alias
    connection = connections[db_alias]

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, ai_summary FROM claims_document "
            "WHERE ai_summary IS NOT NULL AND ai_summary != ''"
        )
        rows = cursor.fetchall()

    for pk, value in rows:
        if not value:
            continue

        decrypted = FieldEncryption.decrypt(value)
        if decrypted:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE claims_document SET ai_summary = %s WHERE id = %s",
                    [decrypted, pk],
                )


class Migration(migrations.Migration):

    dependencies = [
        ("claims", "0004_add_condition_tags"),
    ]

    operations = [
        # Step 1: Change column type from JSON to Text
        # (EncryptedJSONField extends TextField, not JSONField)
        migrations.AlterField(
            model_name="document",
            name="ai_summary",
            field=models.TextField(
                blank=True,
                help_text="Structured analysis results from OpenAI (encrypted)",
                null=True,
                verbose_name="AI analysis summary",
            ),
        ),
        # Step 2: Encrypt existing plaintext data
        migrations.RunPython(
            encrypt_existing_ai_summaries,
            reverse_code=decrypt_ai_summaries,
        ),
    ]
