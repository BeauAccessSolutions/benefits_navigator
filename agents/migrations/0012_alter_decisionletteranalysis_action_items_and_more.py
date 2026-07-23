# Encrypt agent analysis PHI at rest (HIPAA §164.312(a)(2)(iv)):
# DecisionLetterAnalysis (conditions/appeal/action JSON + summary) and
# DenialDecoding (denial mappings/priority JSON + evidence strategy). AlterField
# switches JSON columns to EncryptedJSONField (jsonb -> text) and the text
# columns to EncryptedTextField; RunPython encrypts existing rows in place.
#
# Follows the proven claims.0005 (ai_summary) jsonb->text + encrypt pattern.

import core.encryption
from django.db import migrations

DECISION_COLUMNS = [
    "conditions_granted",
    "conditions_denied",
    "conditions_deferred",
    "summary",
    "appeal_options",
    "evidence_issues",
    "action_items",
]

DENIAL_COLUMNS = ["denial_mappings", "evidence_strategy", "priority_order"]


def _encrypt_columns(connection, table, columns):
    """Encrypt existing plaintext values in the given columns, in place.

    Works for both text and (post-AlterField) former-JSON columns: the value is
    read as its text form and encrypted as an opaque string; EncryptedJSONField
    re-parses the JSON on read.
    """
    from core.encryption import FieldEncryption

    col_list = ", ".join(columns)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id, {col_list} FROM {table}")
        rows = cursor.fetchall()

    for row in rows:
        pk = row[0]
        updates = {}
        for col, value in zip(columns, row[1:]):
            if not value:
                continue
            # Idempotent: a value that already decrypts is already encrypted.
            if FieldEncryption.decrypt(value):
                continue
            updates[col] = FieldEncryption.encrypt(str(value))

        if updates:
            set_clause = ", ".join(f"{col} = %s" for col in updates)
            params = list(updates.values()) + [pk]
            with connection.cursor() as cursor:
                cursor.execute(f"UPDATE {table} SET {set_clause} WHERE id = %s", params)


def _decrypt_columns(connection, table, columns):
    """Reverse: decrypt values back to their plaintext text form."""
    from core.encryption import FieldEncryption

    col_list = ", ".join(columns)
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id, {col_list} FROM {table}")
        rows = cursor.fetchall()

    for row in rows:
        pk = row[0]
        updates = {}
        for col, value in zip(columns, row[1:]):
            if not value:
                continue
            decrypted = FieldEncryption.decrypt(value)
            if decrypted:
                updates[col] = decrypted

        if updates:
            set_clause = ", ".join(f"{col} = %s" for col in updates)
            params = list(updates.values()) + [pk]
            with connection.cursor() as cursor:
                cursor.execute(f"UPDATE {table} SET {set_clause} WHERE id = %s", params)


def encrypt_forward(apps, schema_editor):
    conn = schema_editor.connection
    _encrypt_columns(conn, "agents_decisionletteranalysis", DECISION_COLUMNS)
    _encrypt_columns(conn, "agents_denialdecoding", DENIAL_COLUMNS)


def decrypt_reverse(apps, schema_editor):
    conn = schema_editor.connection
    _decrypt_columns(conn, "agents_decisionletteranalysis", DECISION_COLUMNS)
    _decrypt_columns(conn, "agents_denialdecoding", DENIAL_COLUMNS)


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0011_alter_assistantturn_content_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="decisionletteranalysis",
            name="action_items",
            field=core.encryption.EncryptedJSONField(
                default=list, help_text="Recommended next steps"
            ),
        ),
        migrations.AlterField(
            model_name="decisionletteranalysis",
            name="appeal_options",
            field=core.encryption.EncryptedJSONField(
                default=list, help_text="Available appeal paths with deadlines"
            ),
        ),
        migrations.AlterField(
            model_name="decisionletteranalysis",
            name="conditions_deferred",
            field=core.encryption.EncryptedJSONField(
                default=list, help_text="List of deferred conditions"
            ),
        ),
        migrations.AlterField(
            model_name="decisionletteranalysis",
            name="conditions_denied",
            field=core.encryption.EncryptedJSONField(
                default=list, help_text="List of denied conditions with reasons"
            ),
        ),
        migrations.AlterField(
            model_name="decisionletteranalysis",
            name="conditions_granted",
            field=core.encryption.EncryptedJSONField(
                default=list, help_text="List of granted conditions with ratings"
            ),
        ),
        migrations.AlterField(
            model_name="decisionletteranalysis",
            name="evidence_issues",
            field=core.encryption.EncryptedJSONField(
                default=list, help_text="Evidence problems identified"
            ),
        ),
        migrations.AlterField(
            model_name="decisionletteranalysis",
            name="summary",
            field=core.encryption.EncryptedTextField(
                blank=True, help_text="Plain-English summary"
            ),
        ),
        migrations.AlterField(
            model_name="denialdecoding",
            name="denial_mappings",
            field=core.encryption.EncryptedJSONField(
                default=list,
                help_text="Denials with M21 matches and evidence requirements",
                verbose_name="Denial Mappings",
            ),
        ),
        migrations.AlterField(
            model_name="denialdecoding",
            name="evidence_strategy",
            field=core.encryption.EncryptedTextField(
                blank=True,
                help_text="AI-generated overall strategy for addressing denials",
                verbose_name="Evidence Strategy",
            ),
        ),
        migrations.AlterField(
            model_name="denialdecoding",
            name="priority_order",
            field=core.encryption.EncryptedJSONField(
                blank=True,
                default=list,
                help_text="Recommended order to address denials",
                verbose_name="Priority Order",
            ),
        ),
        migrations.RunPython(encrypt_forward, reverse_code=decrypt_reverse),
    ]
