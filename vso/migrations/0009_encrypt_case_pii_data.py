"""
Data migration to encrypt existing VeteranCase PII/PHI values:
description, closure_notes, c_and_p_exam_notes (text) and conditions (JSON).

Follows the claims/0005_encrypt_ai_summary pattern: raw cursor reads to
bypass model-level decryption, skip values that are already Fernet tokens.
"""

import json

from django.db import migrations

TEXT_FIELDS = ['description', 'closure_notes', 'c_and_p_exam_notes']
JSON_FIELDS = ['conditions']


def _is_encrypted(value):
    return isinstance(value, str) and len(value) > 100 and value.startswith('Z0FB')


def encrypt_case_fields(apps, schema_editor):
    from core.encryption import FieldEncryption
    from django.db import connections

    connection = connections[schema_editor.connection.alias]
    columns = TEXT_FIELDS + JSON_FIELDS

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT id, {", ".join(columns)} FROM vso_veterancase'
        )
        rows = cursor.fetchall()

    for row in rows:
        pk, values = row[0], row[1:]
        updates = {}
        for column, value in zip(columns, values):
            if value is None or value == '' or _is_encrypted(value):
                continue
            if column in JSON_FIELDS:
                # Value may arrive as a JSON string or a parsed object
                # depending on backend; normalize to a JSON string.
                json_str = value if isinstance(value, str) else json.dumps(value)
                updates[column] = FieldEncryption.encrypt(json_str)
            else:
                updates[column] = FieldEncryption.encrypt(str(value))

        if updates:
            set_clause = ', '.join(f'{col} = %s' for col in updates)
            with connection.cursor() as cursor:
                cursor.execute(
                    f'UPDATE vso_veterancase SET {set_clause} WHERE id = %s',
                    [*updates.values(), pk],
                )


def decrypt_case_fields(apps, schema_editor):
    from core.encryption import FieldEncryption
    from django.db import connections

    connection = connections[schema_editor.connection.alias]
    columns = TEXT_FIELDS + JSON_FIELDS

    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT id, {", ".join(columns)} FROM vso_veterancase'
        )
        rows = cursor.fetchall()

    for row in rows:
        pk, values = row[0], row[1:]
        updates = {}
        for column, value in zip(columns, values):
            if not _is_encrypted(value):
                continue
            updates[column] = FieldEncryption.decrypt(value) or ''

        if updates:
            set_clause = ', '.join(f'{col} = %s' for col in updates)
            with connection.cursor() as cursor:
                cursor.execute(
                    f'UPDATE vso_veterancase SET {set_clause} WHERE id = %s',
                    [*updates.values(), pk],
                )


class Migration(migrations.Migration):

    dependencies = [
        ('vso', '0008_alter_veterancase_c_and_p_exam_notes_and_more'),
    ]

    operations = [
        migrations.RunPython(encrypt_case_fields, decrypt_case_fields),
    ]
