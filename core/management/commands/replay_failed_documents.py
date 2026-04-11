"""
Management command to replay failed document processing tasks.

Finds documents in 'failed' status (optionally filtered by age or document ID)
and re-queues them for processing. Dry-run by default.

Usage:
    # Preview what would be replayed (no writes):
    python manage.py replay_failed_documents

    # Replay all failed documents from the last 24 hours:
    python manage.py replay_failed_documents --execute

    # Replay a specific document by ID:
    python manage.py replay_failed_documents --document-id 42 --execute

    # Replay documents failed within the last N hours:
    python manage.py replay_failed_documents --hours 48 --execute

    # Also replay stuck documents (processing > 2 hours):
    python manage.py replay_failed_documents --include-stuck --execute
"""

from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Replay failed (or stuck) document processing tasks."

    def add_arguments(self, parser):
        parser.add_argument(
            "--execute",
            action="store_true",
            default=False,
            help="Actually re-queue tasks. Without this flag, only a preview is shown.",
        )
        parser.add_argument(
            "--document-id",
            type=int,
            metavar="ID",
            help="Replay a single document by primary key.",
        )
        parser.add_argument(
            "--hours",
            type=int,
            default=24,
            metavar="N",
            help="Only replay documents that failed within the last N hours (default: 24).",
        )
        parser.add_argument(
            "--include-stuck",
            action="store_true",
            default=False,
            help="Also replay documents stuck in 'processing'/'analyzing' for more than 2 hours.",
        )

    def handle(self, *args, **options):
        from claims.models import Document
        from claims.tasks import process_document

        execute = options["execute"]
        doc_id = options["document_id"]
        hours = options["hours"]
        include_stuck = options["include_stuck"]

        if doc_id:
            try:
                documents = [Document.objects.get(pk=doc_id)]
            except Document.DoesNotExist:
                raise CommandError(f"Document {doc_id} does not exist.")
        else:
            cutoff = timezone.now() - timedelta(hours=hours)
            qs = Document.objects.filter(status="failed", updated_at__gte=cutoff)

            if include_stuck:
                stuck_cutoff = timezone.now() - timedelta(hours=2)
                stuck_qs = Document.objects.filter(
                    status__in=["processing", "analyzing"],
                    updated_at__lt=stuck_cutoff,
                )
                # Union via Python (both querysets are small)
                doc_pks = set(qs.values_list("pk", flat=True)) | set(
                    stuck_qs.values_list("pk", flat=True)
                )
                documents = list(Document.objects.filter(pk__in=doc_pks).order_by("updated_at"))
            else:
                documents = list(qs.order_by("updated_at"))

        if not documents:
            self.stdout.write(self.style.SUCCESS("No documents match the criteria — nothing to replay."))
            return

        verb = "Replaying" if execute else "Would replay (dry run)"
        self.stdout.write(f"\n{verb} {len(documents)} document(s):\n")

        replayed = 0
        for doc in documents:
            age = timezone.now() - doc.updated_at
            age_str = f"{int(age.total_seconds() / 3600)}h {int((age.total_seconds() % 3600) / 60)}m ago"
            self.stdout.write(
                f"  [{doc.pk}] {doc.file_name or 'unnamed'} — status={doc.status}, last updated {age_str}"
            )

            if execute:
                # Reset to pending so the task re-runs cleanly
                doc.status = "pending"
                doc.error_message = ""
                doc.save(update_fields=["status", "error_message", "updated_at"])
                process_document.delay(doc.pk)
                replayed += 1

        if execute:
            self.stdout.write(self.style.SUCCESS(f"\n✓ Queued {replayed} document(s) for reprocessing."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"\nDry run complete. Run with --execute to actually replay {len(documents)} document(s)."
                )
            )
