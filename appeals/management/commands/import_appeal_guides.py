"""
Management command to import appeal guides from JSON files into the database.
"""

import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from appeals.models import AppealGuidance


class Command(BaseCommand):
    help = "Import appeal guides from JSON files into the AppealGuidance model"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=str,
            default="agents/data",
            help="Source directory for JSON guide files (default: agents/data)",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Update existing guides instead of skipping them",
        )

    def handle(self, *args, **options):
        source_dir = Path(options["source"])
        if not source_dir.is_absolute():
            source_dir = Path(__file__).parent.parent.parent.parent.parent / source_dir

        update_existing = options["update"]

        # Map JSON files to appeal types
        guide_files = {
            "hlr": source_dir / "higher_level_review_guide.json",
            "supplemental": source_dir / "supplemental_claim_guide.json",
            "board": source_dir / "board_appeal_guide.json",
        }

        imported = 0
        updated = 0
        skipped = 0
        errors = 0

        for appeal_type, file_path in guide_files.items():
            if not file_path.exists():
                self.stdout.write(self.style.WARNING(f"File not found: {file_path}"))
                errors += 1
                continue

            try:
                with open(file_path, "r") as f:
                    data = json.load(f)

                # Check if guide already exists
                existing = AppealGuidance.objects.filter(
                    appeal_type=appeal_type
                ).first()

                if existing and not update_existing:
                    self.stdout.write(
                        self.style.NOTICE(
                            f"Skipping {appeal_type} - already exists (use --update to overwrite)"
                        )
                    )
                    skipped += 1
                    continue

                # Prepare the guide data
                guide_data = {
                    "title": data.get("title", f"{appeal_type.upper()} Guide"),
                    "slug": slugify(data.get("title", appeal_type)),
                    "appeal_type": appeal_type,
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

                # Set order based on appeal type
                order_map = {"hlr": 1, "supplemental": 2, "board": 3}
                guide_data["order"] = order_map.get(appeal_type, 10)

                if existing:
                    # Update existing guide
                    for key, value in guide_data.items():
                        setattr(existing, key, value)
                    existing.save()
                    self.stdout.write(
                        self.style.SUCCESS(f'Updated: {data.get("title", appeal_type)}')
                    )
                    updated += 1
                else:
                    # Create new guide
                    AppealGuidance.objects.create(**guide_data)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Imported: {data.get("title", appeal_type)}'
                        )
                    )
                    imported += 1

            except json.JSONDecodeError as e:
                self.stdout.write(self.style.ERROR(f"Invalid JSON in {file_path}: {e}"))
                errors += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Error importing {file_path}: {e}"))
                errors += 1

        # Summary
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Import complete:"))
        self.stdout.write(f"  Imported: {imported}")
        self.stdout.write(f"  Updated: {updated}")
        self.stdout.write(f"  Skipped: {skipped}")
        if errors:
            self.stdout.write(self.style.WARNING(f"  Errors: {errors}"))
