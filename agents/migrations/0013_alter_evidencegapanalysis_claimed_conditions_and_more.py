# Encrypt the remaining agent analysis PHI at rest (HIPAA §164.312(a)(2)(iv)):
# EvidenceGapAnalysis + RatingAnalysis conditions/evidence/strategy JSON, the
# rating markdown, and the extracted veteran name. AlterField switches each to
# an Encrypted* field; RunPython encrypts existing rows in place. Follows the
# proven claims.0005 (ai_summary) jsonb->text + encrypt pattern.

import core.encryption
from django.db import migrations

EVIDENCE_GAP_COLUMNS = [
    "claimed_conditions",
    "existing_evidence",
    "evidence_gaps",
    "strength_assessment",
    "recommendations",
    "templates_suggested",
]

RATING_COLUMNS = [
    "veteran_name",
    "markdown_analysis",
    "conditions",
    "evidence_list",
    "increase_opportunities",
    "secondary_conditions",
    "rating_errors",
    "effective_date_issues",
    "deadline_tracker",
    "benefits_unlocked",
    "exam_prep_tips",
    "priority_actions",
    "confidence_breakdown",
    "confidence_factors",
]


def _encrypt_columns(connection, table, columns):
    """Encrypt existing plaintext values in the given columns, in place.

    Works for text, char, and (post-AlterField) former-JSON columns alike: the
    value is read as its text form and encrypted as an opaque string.
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
    _encrypt_columns(conn, "agents_evidencegapanalysis", EVIDENCE_GAP_COLUMNS)
    _encrypt_columns(conn, "agents_ratinganalysis", RATING_COLUMNS)


def decrypt_reverse(apps, schema_editor):
    conn = schema_editor.connection
    _decrypt_columns(conn, "agents_evidencegapanalysis", EVIDENCE_GAP_COLUMNS)
    _decrypt_columns(conn, "agents_ratinganalysis", RATING_COLUMNS)


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0012_alter_decisionletteranalysis_action_items_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="evidencegapanalysis",
            name="claimed_conditions",
            field=core.encryption.EncryptedJSONField(
                default=list, help_text="Conditions being claimed"
            ),
        ),
        migrations.AlterField(
            model_name="evidencegapanalysis",
            name="evidence_gaps",
            field=core.encryption.EncryptedJSONField(
                default=list, help_text="Missing evidence items"
            ),
        ),
        migrations.AlterField(
            model_name="evidencegapanalysis",
            name="existing_evidence",
            field=core.encryption.EncryptedJSONField(
                default=list, help_text="Evidence already gathered"
            ),
        ),
        migrations.AlterField(
            model_name="evidencegapanalysis",
            name="recommendations",
            field=core.encryption.EncryptedJSONField(
                default=list, help_text="Prioritized recommendations"
            ),
        ),
        migrations.AlterField(
            model_name="evidencegapanalysis",
            name="strength_assessment",
            field=core.encryption.EncryptedJSONField(
                default=dict, help_text="Current evidence strength by condition"
            ),
        ),
        migrations.AlterField(
            model_name="evidencegapanalysis",
            name="templates_suggested",
            field=core.encryption.EncryptedJSONField(
                default=list, help_text="Relevant templates/forms"
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="benefits_unlocked",
            field=core.encryption.EncryptedJSONField(
                default=list,
                help_text="Benefits veteran is eligible for at current rating",
                verbose_name="Benefits Unlocked",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="conditions",
            field=core.encryption.EncryptedJSONField(
                default=list,
                help_text="List of conditions with ratings and diagnostic codes",
                verbose_name="Rated Conditions",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="confidence_breakdown",
            field=core.encryption.EncryptedJSONField(
                default=dict,
                help_text="Detailed confidence scores for different aspects",
                verbose_name="Confidence Breakdown",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="confidence_factors",
            field=core.encryption.EncryptedJSONField(
                default=list,
                help_text="Factors that influenced confidence scoring",
                verbose_name="Confidence Factors",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="deadline_tracker",
            field=core.encryption.EncryptedJSONField(
                default=dict,
                help_text="Appeal deadlines and availability",
                verbose_name="Deadline Tracker",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="effective_date_issues",
            field=core.encryption.EncryptedJSONField(
                default=list,
                help_text="Potential issues with effective dates",
                verbose_name="Effective Date Issues",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="evidence_list",
            field=core.encryption.EncryptedJSONField(
                default=list,
                help_text="List of evidence VA reviewed",
                verbose_name="Evidence Reviewed",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="exam_prep_tips",
            field=core.encryption.EncryptedJSONField(
                default=list,
                help_text="C&P exam preparation guidance",
                verbose_name="Exam Prep Tips",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="increase_opportunities",
            field=core.encryption.EncryptedJSONField(
                default=list,
                help_text="Opportunities to increase ratings for each condition",
                verbose_name="Increase Opportunities",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="markdown_analysis",
            field=core.encryption.EncryptedTextField(
                blank=True,
                help_text="Human-readable markdown-formatted analysis",
                verbose_name="Markdown Analysis",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="priority_actions",
            field=core.encryption.EncryptedJSONField(
                default=list,
                help_text="Prioritized list of recommended actions",
                verbose_name="Priority Actions",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="rating_errors",
            field=core.encryption.EncryptedJSONField(
                default=list,
                help_text="Potential errors in the rating decision",
                verbose_name="Potential Rating Errors",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="secondary_conditions",
            field=core.encryption.EncryptedJSONField(
                default=list,
                help_text="Potential secondary conditions to claim",
                verbose_name="Secondary Conditions",
            ),
        ),
        migrations.AlterField(
            model_name="ratinganalysis",
            name="veteran_name",
            field=core.encryption.EncryptedCharField(blank=True, max_length=1000),
        ),
        migrations.RunPython(encrypt_forward, reverse_code=decrypt_reverse),
    ]
