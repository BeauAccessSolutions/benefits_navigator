"""Upload validation and stored-file lifecycle.

Two gaps in the appeal-document path, from the remediation plan's Phase 1.2:

* ``AppealDocumentForm`` had no server-side validation at all — just an
  ``accept=`` attribute on the widget, which is a file-picker hint. Anything
  that speaks HTTP could post a 200 MB executable named ``evidence.pdf``.
* Deleting an appeal document removed the row and left the file in storage,
  so "deleted" was not true of the bytes.

The validation tests drive the shared ``core.file_validation`` helper through
the appeals form, because that is the path that was unprotected; the claims
forms route through the same helper, so a regression there fails here too.
"""

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

from appeals.forms import AppealDocumentForm
from appeals.models import Appeal, AppealDocument
from core.file_validation import validate_document_upload

# Smallest byte sequences libmagic identifies as the real thing.
PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDAT"
    b"x\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _upload(name, content, content_type):
    return SimpleUploadedFile(name, content, content_type=content_type)


def _form(file):
    return AppealDocumentForm(
        data={"document_type": "medical_record", "title": "MRI report"},
        files={"file": file},
    )


class TestSharedUploadValidator:
    """Unit-level checks on the helper both apps now share."""

    def test_accepts_a_real_pdf(self):
        validated = validate_document_upload(
            _upload("evidence.pdf", PDF_BYTES, "application/pdf")
        )
        assert validated.name == "evidence.pdf"

    def test_accepts_a_real_png(self):
        assert validate_document_upload(_upload("scan.png", PNG_BYTES, "image/png"))

    def test_rejects_a_file_over_the_size_cap(self):
        big = _upload("evidence.pdf", PDF_BYTES, "application/pdf")
        with pytest.raises(ValidationError, match="exceeds maximum"):
            validate_document_upload(big, max_size=4)

    def test_rejects_a_disallowed_extension(self):
        with pytest.raises(ValidationError, match="Invalid file extension"):
            validate_document_upload(
                _upload("payload.exe", PDF_BYTES, "application/pdf")
            )

    def test_rejects_a_disallowed_content_type(self):
        with pytest.raises(ValidationError, match="File type not supported"):
            validate_document_upload(_upload("notes.pdf", PDF_BYTES, "text/html"))

    def test_rejects_content_that_lies_about_itself(self):
        """The check that matters: extension and header both say PDF, bytes don't."""
        disguised = _upload("evidence.pdf", b"#!/bin/sh\nrm -rf /\n", "application/pdf")
        with pytest.raises(ValidationError, match="does not match expected type"):
            validate_document_upload(disguised)

    def test_leaves_the_file_readable_for_the_caller(self):
        """libmagic reads the head; callers still need the whole file."""
        validated = validate_document_upload(
            _upload("evidence.pdf", PDF_BYTES, "application/pdf")
        )
        assert validated.read() == PDF_BYTES


@pytest.mark.django_db
class TestAppealDocumentFormValidation:
    """The appeals form must reject what the claims form has always rejected."""

    def test_accepts_a_valid_document(self):
        assert _form(_upload("evidence.pdf", PDF_BYTES, "application/pdf")).is_valid()

    def test_rejects_a_disguised_executable(self):
        form = _form(_upload("evidence.pdf", b"MZ\x90\x00\x03", "application/pdf"))
        assert not form.is_valid()
        assert "file" in form.errors

    def test_rejects_a_bad_extension(self):
        form = _form(_upload("evidence.svg", PNG_BYTES, "image/png"))
        assert not form.is_valid()
        assert "file" in form.errors

    def test_allows_a_document_row_with_no_file(self):
        """The model permits a file-less row; validation must not break that."""
        form = AppealDocumentForm(
            data={"document_type": "medical_record", "title": "Requested from VA"},
            files={},
        )
        assert form.is_valid(), form.errors


@pytest.mark.django_db
class TestStoredFileIsRemovedOnDelete:
    """A deleted row must take its bytes with it."""

    def _appeal_document(self, user):
        appeal = Appeal.objects.create(
            user=user, appeal_type="hlr", conditions_appealed="Knee"
        )
        document = AppealDocument.objects.create(
            appeal=appeal,
            document_type="medical_record",
            title="MRI report",
            file=_upload("evidence.pdf", PDF_BYTES, "application/pdf"),
        )
        return appeal, document

    def test_deleting_the_row_deletes_the_file(self, user):
        _, document = self._appeal_document(user)
        path = document.file.name
        assert default_storage.exists(path)

        document.delete()

        assert not default_storage.exists(path)

    def test_cascade_from_the_appeal_deletes_the_file(self, user):
        """Deleting the appeal must not orphan its evidence."""
        appeal, document = self._appeal_document(user)
        path = document.file.name

        appeal.delete()

        assert not default_storage.exists(path)

    def test_delete_survives_a_missing_file(self, user):
        """A file already gone from storage must not block the row delete."""
        _, document = self._appeal_document(user)
        default_storage.delete(document.file.name)

        document.delete()

        assert not AppealDocument.objects.filter(pk=document.pk).exists()

    def test_the_receivers_are_held_by_strong_reference(self):
        """
        Django stores signal receivers by *weak* reference by default. Written
        as closures inside ``register()``, these handlers were referenced by
        nothing else once that call returned, so the collector could reclaim
        them mid-process and file deletion would silently stop — no error, no
        failed request, just files quietly accumulating.

        It behaved locally and failed in CI, where a longer run collected them
        partway through.

        Asserting on the registry rather than forcing a ``gc.collect()``: when
        collection actually happens depends on reference cycles and timing, so
        a collect-then-delete test passes against the broken version too (it
        does — I checked). The registry is the thing that is deterministically
        either right or wrong.
        """
        import weakref

        from django.db.models.signals import post_delete

        uids = {"appealdoc_file_cleanup", "document_file_cleanup"}
        found = {
            key[0]: ref
            for key, ref, _sender, _is_async in post_delete.receivers
            if isinstance(key, tuple) and key[0] in uids
        }

        assert set(found) == uids, f"receivers not connected: {uids - set(found)}"
        for uid, ref in found.items():
            assert not isinstance(ref, weakref.ReferenceType), (
                f"{uid} is stored as a weakref — the collector can disconnect "
                f"it and file deletion stops silently. Connect with weak=False "
                f"and keep the handler at module level."
            )
