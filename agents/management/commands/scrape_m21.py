"""
Django management command to scrape M21-1 manual from KnowVA.

Usage:
    python manage.py scrape_m21 --all
    python manage.py scrape_m21 --article-id 554400000181474
    python manage.py scrape_m21 --reference I.i.1.A
    python manage.py scrape_m21 --parts I II III --force
    python manage.py scrape_m21 --dry-run
"""

import json
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError
from django.utils import timezone

from agents.models import M21ManualSection, M21ScrapeJob
from agents.knowva_scraper import KnowVAScraper, KNOWN_ARTICLE_IDS

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scrape M21-1 Adjudication Procedures Manual from VA KnowVA"

    def add_arguments(self, parser):
        parser.add_argument(
            "--article-id", type=str, help="Scrape a specific KnowVA article ID"
        )
        parser.add_argument(
            "--reference", type=str, help="Scrape by M21-1 reference (e.g., I.i.1.A)"
        )
        parser.add_argument(
            "--all", action="store_true", help="Scrape all known articles"
        )
        parser.add_argument(
            "--parts", nargs="+", help="Scrape specific parts (e.g., I II III)"
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force re-scrape even if content exists",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be scraped without actually scraping",
        )
        parser.add_argument(
            "--headless",
            action="store_true",
            default=True,
            help="Run browser in headless mode (default: True)",
        )
        parser.add_argument(
            "--no-headless",
            action="store_false",
            dest="headless",
            help="Run browser with visible window",
        )
        parser.add_argument(
            "--rate-limit",
            type=float,
            default=3.0,
            help="Seconds between requests (default: 3.0)",
        )
        parser.add_argument(
            "--import-from-file", type=str, help="Import article IDs from JSON file"
        )

    def handle(self, *args, **options):
        # Determine what to scrape
        article_ids_to_scrape = self._determine_articles(options)

        if not article_ids_to_scrape:
            self.stdout.write(
                self.style.ERROR(
                    "No articles to scrape. Use --all, --article-id, or --reference"
                )
            )
            return

        self.stdout.write(self.style.HTTP_INFO("\n=== M21-1 Scraping Job ==="))
        self.stdout.write(f"Articles to scrape: {len(article_ids_to_scrape)}")
        self.stdout.write(f'Force update: {options["force"]}')
        self.stdout.write(f'Dry run: {options["dry_run"]}')
        self.stdout.write(f'Rate limit: {options["rate_limit"]}s')
        self.stdout.write("")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made\n"))
            for article_id in article_ids_to_scrape[:10]:  # Show first 10
                self.stdout.write(f"  Would scrape: {article_id}")
            if len(article_ids_to_scrape) > 10:
                self.stdout.write(f"  ... and {len(article_ids_to_scrape) - 10} more")
            return

        # Create scrape job record
        scrape_job = M21ScrapeJob.objects.create(
            status="running",
            target_parts=options.get("parts") or [],
            force_update=options["force"],
            total_sections=len(article_ids_to_scrape),
            started_at=timezone.now(),
        )

        # Initialize scraper
        scraper = KnowVAScraper(
            headless=options["headless"], rate_limit=options["rate_limit"]
        )

        # Track results
        successful = 0
        failed = 0
        skipped = 0
        errors = []

        try:
            for idx, article_id in enumerate(article_ids_to_scrape, 1):
                self.stdout.write(
                    f"\n[{idx}/{len(article_ids_to_scrape)}] Scraping article {article_id}..."
                )

                # Check if exists and skip if not forcing
                if not options["force"]:
                    existing = M21ManualSection.objects.filter(
                        article_id=article_id
                    ).first()
                    if existing:
                        self.stdout.write(
                            self.style.WARNING(
                                f"  Skipped (already exists): {existing.reference}"
                            )
                        )
                        skipped += 1
                        scrape_job.sections_completed += 1
                        scrape_job.save()
                        continue

                # Scrape
                try:
                    data = scraper.scrape_section(article_id)

                    if not data:
                        self.stdout.write(
                            self.style.ERROR(f"  Failed to scrape article {article_id}")
                        )
                        failed += 1
                        scrape_job.sections_failed += 1
                        errors.append(f"Article {article_id}: No data returned")
                        continue

                    # Save to database
                    section = self._save_section(data, options["force"])

                    if section:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"  Saved: {section.reference} - {section.title[:60]}"
                            )
                        )
                        successful += 1
                        scrape_job.sections_completed += 1
                    else:
                        self.stdout.write(self.style.ERROR("  Failed to save section"))
                        failed += 1
                        scrape_job.sections_failed += 1
                        errors.append(f"Article {article_id}: Failed to save")

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  Error: {str(e)}"))
                    failed += 1
                    scrape_job.sections_failed += 1
                    errors.append(f"Article {article_id}: {str(e)}")
                    logger.error(f"Error scraping article {article_id}", exc_info=True)

                scrape_job.save()

        finally:
            # Update job status
            scrape_job.completed_at = timezone.now()
            duration = (scrape_job.completed_at - scrape_job.started_at).total_seconds()
            scrape_job.duration_seconds = int(duration)

            if failed == 0:
                scrape_job.status = "completed"
            elif successful > 0:
                scrape_job.status = "partial"
            else:
                scrape_job.status = "failed"

            scrape_job.summary = {
                "total": len(article_ids_to_scrape),
                "successful": successful,
                "failed": failed,
                "skipped": skipped,
            }
            scrape_job.error_log = "\n".join(errors)
            scrape_job.save()

        # Print summary
        self.stdout.write(self.style.HTTP_INFO("\n=== Scraping Complete ==="))
        self.stdout.write(f"Total articles: {len(article_ids_to_scrape)}")
        self.stdout.write(self.style.SUCCESS(f"Successful: {successful}"))
        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped (existing): {skipped}"))
        if failed:
            self.stdout.write(self.style.ERROR(f"Failed: {failed}"))
        self.stdout.write(f"Duration: {duration:.1f}s")
        self.stdout.write(f"Job ID: {scrape_job.id}")

        if errors:
            self.stdout.write(self.style.ERROR("\nErrors:"))
            for error in errors[:10]:  # Show first 10
                self.stdout.write(f"  - {error}")
            if len(errors) > 10:
                self.stdout.write(f"  ... and {len(errors) - 10} more")

    def _determine_articles(self, options) -> list:
        """Determine which article IDs to scrape based on options."""
        article_ids = []

        # Specific article ID
        if options.get("article_id"):
            article_ids.append(options["article_id"])

        # By reference
        elif options.get("reference"):
            reference = options["reference"]
            # Look up in known IDs
            for ref, article_id in KNOWN_ARTICLE_IDS.items():
                if ref == reference or ref.replace(".", "") == reference.replace(
                    ".", ""
                ):
                    article_ids.append(article_id)
                    break
            if not article_ids:
                raise CommandError(f"Unknown reference: {reference}")

        # All known articles
        elif options.get("all"):
            article_ids = list(KNOWN_ARTICLE_IDS.values())

        # By parts
        elif options.get("parts"):
            target_parts = [p.upper() for p in options["parts"]]
            for ref, article_id in KNOWN_ARTICLE_IDS.items():
                # Extract part from reference (first component)
                part = ref.split(".")[0] if "." in ref else ref.split("_")[0]
                if part.upper() in target_parts:
                    article_ids.append(article_id)

        # From file
        elif options.get("import_from_file"):
            file_path = Path(options["import_from_file"])
            if not file_path.exists():
                raise CommandError(f"File not found: {file_path}")

            with open(file_path, "r") as f:
                data = json.load(f)

            # Support different file formats
            if isinstance(data, list):
                article_ids = data
            elif isinstance(data, dict):
                if "article_ids" in data:
                    article_ids = data["article_ids"]
                elif "articles" in data:
                    article_ids = [
                        a["id"] if isinstance(a, dict) else a for a in data["articles"]
                    ]
                else:
                    # Extract article_id from dict values
                    # Format: {"I.i.1.A": {"article_id": "123", ...}, ...}
                    article_ids = []
                    for key, value in data.items():
                        if key.startswith("_"):  # Skip comments like "_comment"
                            continue
                        if isinstance(value, dict) and "article_id" in value:
                            article_ids.append(value["article_id"])
                        elif isinstance(value, str):
                            article_ids.append(value)

        return article_ids

    def _save_section(self, data: dict, force_update: bool = False) -> M21ManualSection:
        """
        Save scraped section data to database.

        Args:
            data: Scraped section data
            force_update: Whether to update existing records

        Returns:
            M21ManualSection instance
        """
        # Map Roman numerals to integers for part_number
        part_to_number = {
            "I": 1,
            "II": 2,
            "III": 3,
            "IV": 4,
            "V": 5,
            "VI": 6,
            "VII": 7,
            "VIII": 8,
            "IX": 9,
            "X": 10,
            "XI": 11,
            "XII": 12,
            "XIII": 13,
            "XIV": 14,
        }

        # Extract part from title if not in data (for chapter-only articles)
        part = data.get("part", "")
        if not part:
            title = data.get("title", "") or data.get("section_title", "")
            import re

            match = re.search(
                r"Part\s+(I{1,3}|IV|V|VI{0,3}|IX|X{1,3}|XI{1,3}|XIV?)", title
            )
            if match:
                part = match.group(1)

        part_number = data.get("part_number", 0)
        if not part_number and part:
            part_number = part_to_number.get(part, 0)

        # Prepare data for model
        section_data = {
            "article_id": data.get("article_id"),
            "knowva_url": data.get("url"),
            "title": data.get("section_title") or data.get("title", "Unknown"),
            "content": data.get("content", ""),
            "overview": data.get("overview", ""),
            "topics": data.get("topics", []),
            "references": data.get("references", []),
            "scrape_status": "success",
            "scrape_error": "",
            "part": part,
            "part_number": part_number,
            "part_title": data.get("part_title", ""),
            "subpart": data.get("subpart", ""),
            "chapter": data.get("chapter", ""),
            "section": data.get("section", ""),
            "reference": data.get("reference", ""),
            "full_reference": data.get("full_reference", ""),
        }

        # Add reference data if available (override defaults)
        if data.get("reference"):
            section_data.update(
                {
                    "part": data.get("part", part),
                    "part_number": data.get("part_number", part_number),
                    "part_title": data.get("part_title", ""),
                    "subpart": data.get("subpart", ""),
                    "chapter": data.get("chapter", ""),
                    "section": data.get("section", ""),
                    "reference": data.get("reference"),
                    "full_reference": data.get("full_reference", ""),
                }
            )

        # Handle date
        if data.get("last_updated"):
            # For now, store as string in scrape_error field
            # Could enhance to parse into DateTimeField
            section_data["last_updated_va"] = None

        # Update or create with IntegrityError handling for duplicate references
        try:
            if data.get("article_id"):
                section, created = M21ManualSection.objects.update_or_create(
                    article_id=data["article_id"], defaults=section_data
                )
            elif data.get("reference"):
                section, created = M21ManualSection.objects.update_or_create(
                    reference=data["reference"], defaults=section_data
                )
            else:
                # Create new without unique constraint
                section = M21ManualSection.objects.create(**section_data)
                created = True
        except IntegrityError as e:
            # Handle duplicate reference - update existing record by reference
            error_str = str(e).lower()
            if "reference" in error_str or "unique constraint" in error_str:
                ref = section_data.get("reference") or data.get("reference", "")
                if ref:
                    logger.info(
                        f"Duplicate reference {ref}, updating existing record by reference"
                    )
                    section, created = M21ManualSection.objects.update_or_create(
                        reference=ref, defaults=section_data
                    )
                else:
                    # No reference, try by article_id
                    article_id = section_data.get("article_id") or data.get(
                        "article_id", ""
                    )
                    if article_id:
                        logger.info(
                            f"Duplicate detected for article {article_id}, updating by article_id"
                        )
                        # Remove reference from defaults to avoid conflict
                        update_data = {
                            k: v for k, v in section_data.items() if k != "reference"
                        }
                        section, created = M21ManualSection.objects.update_or_create(
                            article_id=article_id, defaults=update_data
                        )
                    else:
                        raise
            else:
                raise

        return section
