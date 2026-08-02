"""Remove stored files when the row that owns them is deleted.

Deleting an ``AppealDocument`` removed the database row and left the uploaded
file sitting in storage. For an app whose deletion promise is "permanently
deleted", an orphaned PDF of a veteran's medical evidence is the gap between
what the UI says and what is true — and nothing else would ever come back for
it, because the only pointer to the path was the row just deleted.

``post_delete`` is the right hook rather than an explicit call in each view:
files must go on *cascade* deletes too (an appeal deleted with its documents, an
account purge walking every related row), and those never touch a view.

Claims documents are soft-deleted by default (``SoftDeleteModel.delete()`` only
flips a flag), so this receiver does not fire for the everyday "delete my
document" path — by design, that is a reversible action. It fires on
``hard_delete()`` and on cascades, which is exactly where the file must go.
"""

import logging

from django.db.models.signals import post_delete

logger = logging.getLogger(__name__)


def _delete_stored_file(instance, field_name="file"):
    """Best-effort removal; a missing file must not break the delete."""
    file_field = getattr(instance, field_name, None)
    if not file_field or not file_field.name:
        return

    try:
        file_field.delete(save=False)
    except Exception:
        # Storage may be unreachable, or the file already gone. The row is
        # already deleted and the transaction must not be undone over this;
        # log the path so an operator can sweep it.
        logger.warning(
            "Could not delete stored file for %s id=%s",
            type(instance).__name__,
            instance.pk,
            exc_info=True,
        )


# Receivers are module-level on purpose. Django's signal registry holds
# receivers by *weak* reference by default, so a handler defined inside
# register() would be referenced by nothing else once that call returned — and
# would stop firing whenever the garbage collector next ran. That is not
# hypothetical: written that way, this passed locally and failed in CI, where
# a longer run collected the closures partway through and files stopped being
# deleted. A module-level function is kept alive by the module itself.
def appeal_document_deleted(sender, instance, **kwargs):
    _delete_stored_file(instance)


def document_deleted(sender, instance, **kwargs):
    _delete_stored_file(instance)


def register():
    """Connect the receivers. Called from ``CoreConfig.ready()``."""
    from appeals.models import AppealDocument
    from claims.models import Document

    # weak=False as well as module-level functions. Either alone would do; both
    # together mean the connection cannot be lost to garbage collection however
    # this module is later refactored. These receivers live for the life of the
    # process, so there is nothing to auto-disconnect.
    post_delete.connect(
        appeal_document_deleted,
        sender=AppealDocument,
        dispatch_uid="appealdoc_file_cleanup",
        weak=False,
    )
    post_delete.connect(
        document_deleted,
        sender=Document,
        dispatch_uid="document_file_cleanup",
        weak=False,
    )
