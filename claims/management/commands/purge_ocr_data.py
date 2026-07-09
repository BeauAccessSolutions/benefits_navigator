"""
Management command to purge raw OCR text from the database.

This command was part of the Ephemeral OCR Refactor (PR 5) to eliminate PHI storage.

NOTE: As of PR 6, the ocr_text, raw_text fields have been REMOVED from the database
schema entirely. This command is now deprecated and exists only for historical reference.

The PHI text fields were:
- Document.ocr_text (removed in migration 0003)
- DecisionLetterAnalysis.raw_text (removed in migration 0008)
- RatingAnalysis.raw_text (removed in migration 0008)

These fields no longer exist in the models. All OCR text is now ephemeral - extracted
from documents only during processing and never persisted to the database.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "[DEPRECATED] OCR text fields have been removed from the database schema."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("\n⚠️  This command is DEPRECATED.\n"))
        self.stdout.write(
            "The following PHI text fields have been REMOVED from the database schema:\n"
            "  - Document.ocr_text (removed in migration claims/0003)\n"
            "  - DecisionLetterAnalysis.raw_text (removed in migration agents/0008)\n"
            "  - RatingAnalysis.raw_text (removed in migration agents/0008)\n"
        )
        self.stdout.write(
            self.style.SUCCESS(
                "\n✅ No action needed - PHI text fields no longer exist in the database.\n"
                "   OCR text is now ephemeral: extracted during processing, never stored.\n"
            )
        )
