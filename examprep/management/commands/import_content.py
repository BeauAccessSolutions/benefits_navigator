"""
Management command to import C&P exam guides and glossary content from JSON files.

Usage:
    python manage.py import_content
    python manage.py import_content --fixtures  (imports from examprep/fixtures/)
    python manage.py import_content --guides-only
    python manage.py import_content --glossary-only
    python manage.py import_content --dry-run
"""

import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from examprep.models import ExamGuidance, GlossaryTerm


class Command(BaseCommand):
    help = "Import C&P exam guides and glossary terms from JSON files"

    # Base path for research docs
    RESEARCH_DOCS_PATH = (
        Path(__file__).resolve().parent.parent.parent.parent / "Research Docs"
    )

    # Base path for fixtures
    FIXTURES_PATH = Path(__file__).resolve().parent.parent.parent / "fixtures"

    # JSON file locations (Research Docs format)
    GUIDE_FILES = {
        "general": "files/cp_exam_general_guide.json",
        "ptsd": "files2/cp_exam_ptsd_guide.json",
        "musculoskeletal": "files3/cp_exam_musculoskeletal_guide.json",
        "hearing": "files4/cp_exam_hearing_tinnitus_guide.json",
    }
    GLOSSARY_FILE = "files0/va_terminology_glossary.json"

    # Fixture file locations
    FIXTURE_GUIDE_FILES = [
        "exam_guides.json",
        "exam_guides_msk_hearing.json",
        "exam_guides_tbi.json",
        "exam_guides_sleep_apnea.json",
        "exam_guides_mental_health.json",
    ]
    FIXTURE_GLOSSARY_FILES = [
        "glossary_terms.json",
        "additional_glossary_terms.json",
    ]

    # Category mapping from JSON to model choices
    CATEGORY_MAP = {
        "general": "general",
        "ptsd": "ptsd",
        "musculoskeletal": "musculoskeletal",
        "hearing": "hearing",
        "hearing_tinnitus": "hearing",
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixtures",
            action="store_true",
            help="Import from examprep/fixtures/ directory (pre-formatted JSON)",
        )
        parser.add_argument(
            "--guides-only",
            action="store_true",
            help="Only import exam guides, skip glossary",
        )
        parser.add_argument(
            "--glossary-only",
            action="store_true",
            help="Only import glossary terms, skip guides",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be imported without making changes",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing data before importing (use with caution)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        guides_only = options["guides_only"]
        glossary_only = options["glossary_only"]
        clear = options["clear"]
        use_fixtures = options["fixtures"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No changes will be made"))

        if clear and not dry_run:
            self.clear_existing_data(glossary_only, guides_only)

        if use_fixtures:
            # Import from fixtures directory (pre-formatted JSON)
            if not glossary_only:
                self.import_guides_from_fixtures(dry_run)
            if not guides_only:
                self.import_glossary_from_fixtures(dry_run)
        else:
            # Import from Research Docs (legacy format)
            if not glossary_only:
                self.import_guides(dry_run)
            if not guides_only:
                self.import_glossary(dry_run)

        self.stdout.write(self.style.SUCCESS("Import complete!"))

    def clear_existing_data(self, glossary_only, guides_only):
        """Clear existing data before import."""
        if not guides_only:
            count = GlossaryTerm.objects.count()
            GlossaryTerm.objects.all().delete()
            self.stdout.write(f"Cleared {count} glossary terms")

        if not glossary_only:
            count = ExamGuidance.objects.count()
            ExamGuidance.objects.all().delete()
            self.stdout.write(f"Cleared {count} exam guides")

    def import_guides(self, dry_run):
        """Import all exam guidance JSON files."""
        self.stdout.write(self.style.HTTP_INFO("\n=== Importing Exam Guides ==="))

        for category, filepath in self.GUIDE_FILES.items():
            full_path = self.RESEARCH_DOCS_PATH / filepath
            if not full_path.exists():
                self.stdout.write(self.style.WARNING(f"File not found: {full_path}"))
                continue

            self.stdout.write(f"\nProcessing: {filepath}")
            with open(full_path, "r") as f:
                data = json.load(f)

            guide = self.parse_guide(data, category)

            if dry_run:
                self.stdout.write(f'  Would create: {guide["title"]}')
                self.stdout.write(f'    - Category: {guide["category"]}')
                self.stdout.write(f'    - Slug: {guide["slug"]}')
                self.stdout.write(
                    f'    - Checklist items: {len(guide["checklist_items"])}'
                )
            else:
                obj, created = ExamGuidance.objects.update_or_create(
                    slug=guide["slug"], defaults=guide
                )
                status = "Created" if created else "Updated"
                self.stdout.write(self.style.SUCCESS(f"  {status}: {obj.title}"))

    def parse_guide(self, data, category_key):
        """Parse a guide JSON into model fields."""
        sections = {s["section_number"]: s for s in data.get("sections", [])}

        # Map category
        condition_code = data.get("condition_code", category_key)
        category = self.CATEGORY_MAP.get(
            condition_code, self.CATEGORY_MAP.get(category_key, "other")
        )

        # Generate slug
        slug = slugify(data.get("condition_code", category_key) + "-exam-prep")

        return {
            "title": data.get("title", ""),
            "slug": slug,
            "category": category,
            "introduction": self.section_to_markdown(
                sections.get(1, {}).get("content", {})
            ),
            "what_exam_measures": self.section_to_markdown(
                sections.get(2, {}).get("content", {})
            ),
            "physical_tests": self.section_to_markdown(
                sections.get(3, {}).get("content", {})
            ),
            "questions_to_expect": self.section_to_markdown(
                sections.get(4, {}).get("content", {})
            ),
            "preparation_tips": self.section_to_markdown(
                sections.get(5, {}).get("content", {})
            ),
            "day_of_guidance": self.section_to_markdown(
                sections.get(6, {}).get("content", {})
            ),
            "common_mistakes": self.section_to_markdown(
                sections.get(7, {}).get("content", {})
            ),
            "after_exam": self.section_to_markdown(
                sections.get(8, {}).get("content", {})
            ),
            "checklist_items": data.get("preparation_checklist", []),
            "is_published": True,
            "meta_description": f"Prepare for your {data.get('condition', category_key)} C&P exam with this veteran-friendly guide.",
        }

    def section_to_markdown(self, content):
        """Convert nested JSON content to readable markdown text."""
        if not content:
            return ""

        if isinstance(content, str):
            return content

        lines = []

        for key, value in content.items():
            if isinstance(value, str):
                # Simple string value
                if key in (
                    "overview",
                    "explanation",
                    "text",
                    "description",
                    "instruction",
                ):
                    lines.append(value)
                    lines.append("")
                elif key not in ("title", "slug"):
                    lines.append(f"**{self.format_key(key)}:** {value}")
                    lines.append("")

            elif isinstance(value, list):
                # List of items
                if value and isinstance(value[0], str):
                    # Simple string list
                    lines.append(f"**{self.format_key(key)}:**")
                    for item in value:
                        lines.append(f"- {item}")
                    lines.append("")
                elif value and isinstance(value[0], dict):
                    # List of objects
                    lines.append(f"**{self.format_key(key)}:**")
                    lines.append("")
                    for item in value:
                        self.format_dict_item(item, lines)
                    lines.append("")

            elif isinstance(value, dict):
                # Nested object
                title = value.get("title", self.format_key(key))
                lines.append(f"### {title}")
                lines.append("")

                # Recursively format nested content
                nested = self.section_to_markdown(value)
                if nested:
                    lines.append(nested)

        return "\n".join(lines).strip()

    def format_dict_item(self, item, lines):
        """Format a dictionary item as markdown."""
        # Handle different common patterns
        if "question" in item and "answer" in item:
            lines.append(f'**{item["question"]}**')
            lines.append(f'{item["answer"]}')
            lines.append("")
        elif "mistake" in item:
            severity = item.get("severity", "")
            severity_marker = " (Critical)" if severity == "critical" else ""
            lines.append(f'**{item["mistake"]}{severity_marker}**')
            if "description" in item:
                lines.append(item["description"])
            if "fix" in item:
                lines.append(f'*Fix:* {item["fix"]}')
            lines.append("")
        elif "item" in item:
            lines.append(f'- **{item["item"]}**')
            if "reason" in item:
                lines.append(f'  {item["reason"]}')
            if "example" in item:
                lines.append(f'  *Example:* {item["example"]}')
        elif "category" in item and "questions" in item:
            lines.append(f'**{item["category"]}:**')
            for q in item["questions"]:
                lines.append(f"- {q}")
            lines.append("")
        elif "name" in item and "description" in item:
            lines.append(f'- **{item["name"]}:** {item["description"]}')
        elif "factor" in item and "description" in item:
            lines.append(f'- **{item["factor"]}:** {item["description"]}')
        elif "step" in item:
            lines.append(f'{item["step"]}. **{item.get("name", "")}**')
            if "description" in item:
                lines.append(f'   {item["description"]}')
            lines.append("")
        elif "percentage" in item:
            lines.append(f'- **{item["percentage"]}%:** {item.get("description", "")}')
        elif "instead_of" in item and "say" in item:
            lines.append(f'- Instead of: *"{item["instead_of"]}"*')
            lines.append(f'  Say: **"{item["say"]}"**')
            lines.append("")
        else:
            # Generic dict formatting
            for k, v in item.items():
                if isinstance(v, str) and k not in ("id", "slug"):
                    lines.append(f"- **{self.format_key(k)}:** {v}")

    def format_key(self, key):
        """Format a snake_case key as Title Case."""
        return key.replace("_", " ").title()

    def import_glossary(self, dry_run):
        """Import glossary terms from JSON file."""
        self.stdout.write(self.style.HTTP_INFO("\n=== Importing Glossary Terms ==="))

        full_path = self.RESEARCH_DOCS_PATH / self.GLOSSARY_FILE
        if not full_path.exists():
            self.stdout.write(
                self.style.WARNING(f"Glossary file not found: {full_path}")
            )
            return

        with open(full_path, "r") as f:
            data = json.load(f)

        terms = data.get("terms", [])
        self.stdout.write(f"Found {len(terms)} terms to import")

        created_count = 0
        updated_count = 0

        for term_data in terms:
            term_obj = {
                "term": term_data.get("term", ""),
                "plain_language": term_data.get("plain_language", ""),
                "context": term_data.get("context", ""),
                "example": term_data.get("example", ""),
                "show_in_tooltips": True,
            }

            if dry_run:
                self.stdout.write(f'  Would create: {term_obj["term"]}')
            else:
                obj, created = GlossaryTerm.objects.update_or_create(
                    term=term_obj["term"], defaults=term_obj
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Glossary import complete: {created_count} created, {updated_count} updated"
                )
            )

    def import_guides_from_fixtures(self, dry_run):
        """Import exam guides from fixtures directory (pre-formatted JSON)."""
        self.stdout.write(
            self.style.HTTP_INFO("\n=== Importing Exam Guides from Fixtures ===")
        )

        created_count = 0
        updated_count = 0

        for filename in self.FIXTURE_GUIDE_FILES:
            full_path = self.FIXTURES_PATH / filename
            if not full_path.exists():
                self.stdout.write(self.style.WARNING(f"File not found: {full_path}"))
                continue

            self.stdout.write(f"\nProcessing: {filename}")
            with open(full_path, "r") as f:
                guides = json.load(f)

            for guide_data in guides:
                if dry_run:
                    self.stdout.write(
                        f'  Would create: {guide_data.get("title", "Unknown")}'
                    )
                    self.stdout.write(
                        f'    - Category: {guide_data.get("category", "other")}'
                    )
                    self.stdout.write(f'    - Slug: {guide_data.get("slug", "")}')
                    checklist = guide_data.get("checklist_items", [])
                    self.stdout.write(f"    - Checklist items: {len(checklist)}")
                else:
                    slug = guide_data.get("slug", "")
                    obj, created = ExamGuidance.objects.update_or_create(
                        slug=slug, defaults=guide_data
                    )
                    status = "Created" if created else "Updated"
                    self.stdout.write(self.style.SUCCESS(f"  {status}: {obj.title}"))
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nGuides import complete: {created_count} created, {updated_count} updated"
                )
            )

    def import_glossary_from_fixtures(self, dry_run):
        """Import glossary terms from fixtures directory (pre-formatted JSON)."""
        self.stdout.write(
            self.style.HTTP_INFO("\n=== Importing Glossary Terms from Fixtures ===")
        )

        created_count = 0
        updated_count = 0

        for filename in self.FIXTURE_GLOSSARY_FILES:
            full_path = self.FIXTURES_PATH / filename
            if not full_path.exists():
                self.stdout.write(self.style.WARNING(f"File not found: {full_path}"))
                continue

            self.stdout.write(f"\nProcessing: {filename}")
            with open(full_path, "r") as f:
                terms = json.load(f)

            self.stdout.write(f"Found {len(terms)} terms")

            for term_data in terms:
                # Handle Django fixture format (with model/pk/fields)
                if "fields" in term_data:
                    fields = term_data["fields"]
                    term_obj = {
                        "term": fields.get("term", ""),
                        "plain_language": fields.get("plain_language", ""),
                        "context": fields.get("context", ""),
                        "example": fields.get("example", ""),
                        "show_in_tooltips": fields.get("show_in_tooltips", True),
                        "order": fields.get("order", 0),
                    }
                else:
                    # Handle flat format
                    term_obj = {
                        "term": term_data.get("term", ""),
                        "plain_language": term_data.get("plain_language", ""),
                        "context": term_data.get("context", ""),
                        "example": term_data.get("example", ""),
                        "show_in_tooltips": term_data.get("show_in_tooltips", True),
                        "order": term_data.get("order", 0),
                    }

                if not term_obj["term"]:
                    continue  # Skip empty terms

                if dry_run:
                    self.stdout.write(f'  Would create: {term_obj["term"]}')
                else:
                    obj, created = GlossaryTerm.objects.update_or_create(
                        term=term_obj["term"], defaults=term_obj
                    )
                    if created:
                        created_count += 1
                    else:
                        updated_count += 1

        if not dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"\nGlossary import complete: {created_count} created, {updated_count} updated"
                )
            )
