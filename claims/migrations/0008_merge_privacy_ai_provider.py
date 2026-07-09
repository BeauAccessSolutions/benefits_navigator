import core.encryption
from django.db import migrations


class Migration(migrations.Migration):
    """
    Merge the two leaf migrations created independently on `main`
    (0006_alter_document_ai_summary — Claude provider) and on the
    privacy-hardening branch (0006_alter_document_ai_summary_and_more →
    0007_encrypt_condition_tags_data).

    Both leaves altered `ai_summary` to the same EncryptedJSONField, differing
    only in help_text (Claude vs OpenAI). The AlterField below pins the field to
    the current model definition so the migration state and the model agree and
    `makemigrations --check` stays clean regardless of leaf apply order.
    """

    dependencies = [
        ("claims", "0006_alter_document_ai_summary"),
        ("claims", "0007_encrypt_condition_tags_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="document",
            name="ai_summary",
            field=core.encryption.EncryptedJSONField(
                blank=True,
                help_text="Structured analysis results from Claude (encrypted)",
                null=True,
                verbose_name="AI analysis summary",
            ),
        ),
    ]
