"""
Management command to import appeals guidance content from JSON files.

Usage:
    python manage.py import_appeals_guidance
    python manage.py import_appeals_guidance --dry-run
    python manage.py import_appeals_guidance --clear
"""

import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from appeals.models import AppealGuidance


class Command(BaseCommand):
    help = "Import appeals guidance from JSON files"

    # Base path for research docs
    RESEARCH_DOCS_PATH = (
        Path(__file__).resolve().parent.parent.parent.parent
        / "Research Docs"
        / "appeals_guides"
    )

    # JSON file locations
    GUIDE_FILES = {
        "supplemental": "supplemental_claim_guide.json",
        "hlr": "higher_level_review_guide.json",
        "board": "board_appeal_guide.json",
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing guidance before importing",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        clear = options["clear"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        if clear and not dry_run:
            count = AppealGuidance.objects.count()
            AppealGuidance.objects.all().delete()
            self.stdout.write(f"Cleared {count} existing guidance records")

        self.stdout.write(self.style.HTTP_INFO("\n=== Importing Appeals Guidance ==="))

        for appeal_type, filepath in self.GUIDE_FILES.items():
            full_path = self.RESEARCH_DOCS_PATH / filepath
            if not full_path.exists():
                self.stdout.write(self.style.WARNING(f"File not found: {full_path}"))
                continue

            self.stdout.write(f"\nProcessing: {filepath}")
            with open(full_path, "r") as f:
                data = json.load(f)

            guidance = self.parse_guidance(data, appeal_type)

            if dry_run:
                self.stdout.write(f'  Would create: {guidance["title"]}')
                self.stdout.write(f'    - Appeal Type: {guidance["appeal_type"]}')
                self.stdout.write(f'    - VA Form: {guidance["va_form_number"]}')
                self.stdout.write(
                    f'    - Checklist items: {len(guidance["checklist_items"])}'
                )
            else:
                obj, created = AppealGuidance.objects.update_or_create(
                    appeal_type=guidance["appeal_type"], defaults=guidance
                )
                status = "Created" if created else "Updated"
                self.stdout.write(self.style.SUCCESS(f"  {status}: {obj.title}"))

        self.stdout.write(self.style.SUCCESS("\nImport complete!"))

    def parse_guidance(self, data, appeal_type):
        """Parse a guidance JSON into model fields."""
        return {
            "title": data.get("title", ""),
            "slug": slugify(data.get("title", appeal_type)),
            "appeal_type": data.get("appeal_type", appeal_type),
            "va_form_number": data.get("va_form_number", ""),
            "average_processing_days": data.get("average_processing_days", 0),
            "when_to_use": data.get("when_to_use", ""),
            "when_not_to_use": data.get("when_not_to_use", ""),
            "overview": data.get("overview", ""),
            "requirements": data.get("requirements", ""),
            "step_by_step": data.get("step_by_step", ""),
            "evidence_guidance": data.get("evidence_guidance", ""),
            "common_mistakes": data.get("common_mistakes", ""),
            "after_submission": data.get("after_submission", ""),
            "tips": data.get("tips", ""),
            "checklist_items": data.get("checklist_items", []),
            "is_published": True,
        }
