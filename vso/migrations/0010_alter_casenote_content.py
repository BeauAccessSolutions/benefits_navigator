# Encrypt CaseNote.content at rest (HIPAA §164.312(a)(2)(iv)).
#
# Step 1: AlterField TextField -> EncryptedTextField (still a text column in DB).
# Step 2: RunPython encrypts existing plaintext rows in place.

import core.encryption
from django.db import migrations


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
    _encrypt_columns(schema_editor.connection, "vso_casenote", ["content"])


def decrypt_reverse(apps, schema_editor):
    _decrypt_columns(schema_editor.connection, "vso_casenote", ["content"])


class Migration(migrations.Migration):

    dependencies = [
        ("vso", "0009_encrypt_case_pii_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="casenote",
            name="content",
            field=core.encryption.EncryptedTextField(verbose_name="Content"),
        ),
        migrations.RunPython(encrypt_forward, reverse_code=decrypt_reverse),
    ]
