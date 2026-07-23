# Encrypt veteran-narrative PHI at rest (HIPAA §164.312(a)(2)(iv)):
# AssistantTurn.content (chat transcripts) and the PersonalStatement narrative
# fields. AlterField switches each to EncryptedTextField; RunPython encrypts
# existing plaintext rows in place.

import core.encryption
from django.db import migrations

PERSONAL_STATEMENT_COLUMNS = [
    "in_service_event",
    "current_symptoms",
    "daily_impact",
    "work_impact",
    "treatment_history",
    "worst_days",
    "generated_statement",
    "final_statement",
]


def _encrypt_columns(connection, table, columns):
    """Encrypt existing plaintext values in the given text columns, in place."""
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
    """Reverse: decrypt values back to plaintext."""
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
    _encrypt_columns(conn, "agents_assistantturn", ["content"])
    _encrypt_columns(conn, "agents_personalstatement", PERSONAL_STATEMENT_COLUMNS)


def decrypt_reverse(apps, schema_editor):
    conn = schema_editor.connection
    _decrypt_columns(conn, "agents_assistantturn", ["content"])
    _decrypt_columns(conn, "agents_personalstatement", PERSONAL_STATEMENT_COLUMNS)


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0010_assistantthread_assistantturn_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="assistantturn",
            name="content",
            field=core.encryption.EncryptedTextField(blank=True),
        ),
        migrations.AlterField(
            model_name="personalstatement",
            name="current_symptoms",
            field=core.encryption.EncryptedTextField(
                help_text="Current symptoms and limitations"
            ),
        ),
        migrations.AlterField(
            model_name="personalstatement",
            name="daily_impact",
            field=core.encryption.EncryptedTextField(
                help_text="How condition affects daily life"
            ),
        ),
        migrations.AlterField(
            model_name="personalstatement",
            name="final_statement",
            field=core.encryption.EncryptedTextField(
                blank=True, help_text="User-edited final version"
            ),
        ),
        migrations.AlterField(
            model_name="personalstatement",
            name="generated_statement",
            field=core.encryption.EncryptedTextField(
                blank=True, help_text="AI-generated statement"
            ),
        ),
        migrations.AlterField(
            model_name="personalstatement",
            name="in_service_event",
            field=core.encryption.EncryptedTextField(
                help_text="What happened during service"
            ),
        ),
        migrations.AlterField(
            model_name="personalstatement",
            name="treatment_history",
            field=core.encryption.EncryptedTextField(
                blank=True, help_text="Treatment received"
            ),
        ),
        migrations.AlterField(
            model_name="personalstatement",
            name="work_impact",
            field=core.encryption.EncryptedTextField(
                blank=True, help_text="How condition affects work"
            ),
        ),
        migrations.AlterField(
            model_name="personalstatement",
            name="worst_days",
            field=core.encryption.EncryptedTextField(
                blank=True, help_text="Description of worst days/flare-ups"
            ),
        ),
        migrations.RunPython(encrypt_forward, reverse_code=decrypt_reverse),
    ]
