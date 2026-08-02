"""
Storage-agnostic helpers for reading uploaded files.

``FieldFile.path`` raises ``NotImplementedError`` on remote backends (S3 /
Spaces), so any code that assumes a real filesystem path breaks the moment
``USE_S3`` is turned on. Two patterns live here:

* Serving code should stream through the storage backend
  (``field_file.open("rb")`` + ``field_file.storage.exists(...)``) and never
  touch ``.path``.
* Tools that genuinely require a filesystem path — Tesseract/poppler OCR — use
  :func:`as_local_path`, which hands back the real path on local storage and
  otherwise downloads a temporary copy.
"""

import os
import shutil
import tempfile
from contextlib import contextmanager


def local_path_or_none(field_file):
    """
    Return a real filesystem path for ``field_file``, or ``None``.

    ``None`` means the storage backend has no local path (e.g. S3), which is
    the signal for callers to take a storage-backed code path instead of an
    filesystem one (nginx X-Accel-Redirect, for example, can only serve a file
    the web server can see on disk).
    """
    try:
        return field_file.path
    except (NotImplementedError, AttributeError, ValueError):
        return None


@contextmanager
def as_local_path(field_file):
    """
    Yield a filesystem path for ``field_file``, valid for the block's duration.

    On local storage this is the file's real path and nothing is copied. On a
    remote backend the contents are streamed to a ``NamedTemporaryFile`` so
    path-only tools keep working; the temporary copy is always removed on exit,
    including on exception.
    """
    existing = local_path_or_none(field_file)
    if existing:
        yield existing
        return

    suffix = os.path.splitext(field_file.name or "")[1]
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        field_file.open("rb")
        try:
            shutil.copyfileobj(field_file, tmp)
        finally:
            field_file.close()
        tmp.close()
        yield tmp.name
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
