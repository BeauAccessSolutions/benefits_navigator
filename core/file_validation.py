"""Server-side validation shared by every document upload path.

Both veterans' claim documents and appeal evidence arrive through forms, and
both need the same four checks before a byte is stored: size cap, extension,
declared content type, and — the one that actually matters — the file's magic
bytes. Extension and ``Content-Type`` are attacker-controlled; only the leading
bytes say what a file really is.

This lives in ``core`` rather than in either app because it drifted once
already: ``claims`` had the full set while ``appeals`` had nothing but an
``accept=`` attribute on the widget, which is a client-side hint any HTTP client
ignores. One implementation, one place to harden.

``python-magic`` is a hard requirement. If it is missing, uploads are rejected
rather than waved through — failing open on content inspection would silently
turn the strongest check into no check at all.
"""

import logging

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

try:
    import magic

    MAGIC_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on host packages
    MAGIC_AVAILABLE = False
    logger.error(
        "SECURITY WARNING: python-magic is not installed. "
        "File uploads will be rejected until it is installed. "
        "Install with: pip install python-magic (or python-magic-bin on Windows)"
    )

ALLOWED_DOCUMENT_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif"]

# How many leading bytes to hand to libmagic. Enough for every container we
# accept to be identified, small enough not to pull a 50 MB upload into memory.
MAGIC_SNIFF_BYTES = 2048


def validate_document_upload(file, *, max_size=None, allowed_types=None):
    """
    Run the shared upload checks, raising ``ValidationError`` on the first miss.

    Returns the file with its pointer rewound, so callers can keep reading it
    (page counting, storage) without tripping over libmagic's read.
    """
    if not file:
        raise ValidationError(_("Please select a file to upload."))

    max_size = max_size if max_size is not None else settings.MAX_DOCUMENT_SIZE
    allowed_types = (
        allowed_types if allowed_types is not None else settings.ALLOWED_DOCUMENT_TYPES
    )

    if file.size > max_size:
        max_size_mb = max_size / (1024 * 1024)
        raise ValidationError(
            _(
                f"File size exceeds maximum allowed size of {max_size_mb} MB. "
                f"Your file is {round(file.size / (1024 * 1024), 2)} MB."
            )
        )

    # First layer: extension. Cheap, and catches honest mistakes.
    ext = file.name.lower().split(".")[-1] if "." in file.name else ""
    if f".{ext}" not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise ValidationError(
            _("Invalid file extension. Allowed extensions: PDF, JPG, JPEG, PNG, TIFF.")
        )

    # Second layer: what the client claims the file is.
    if file.content_type not in allowed_types:
        raise ValidationError(
            _(
                "File type not supported. Please upload PDF, JPG, PNG, or TIFF "
                "files only."
            )
        )

    # Third layer: what the file actually is. Fail closed if we cannot look.
    if not MAGIC_AVAILABLE:
        raise ValidationError(
            _(
                "File upload is temporarily unavailable due to a server "
                "configuration issue. Please contact support."
            )
        )

    file.seek(0)
    file_magic = magic.from_buffer(file.read(MAGIC_SNIFF_BYTES), mime=True)
    file.seek(0)

    if file_magic not in allowed_types:
        raise ValidationError(
            _(
                "File content does not match expected type. "
                "Please ensure you are uploading a valid PDF or image file."
            )
        )

    return file
