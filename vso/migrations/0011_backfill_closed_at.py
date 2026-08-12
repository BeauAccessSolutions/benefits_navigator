"""
Backfill VeteranCase.closed_at for cases bulk-closed before #103 was fixed.

The bulk case action used queryset.update(status=...), which bypasses the
closure stamping done by the single-case path, leaving rows with a
'closed_*' status but closed_at NULL. Those rows are invisible to every
closure metric (dashboard win rate, closed-this-month, reports
time-to-close).

closed_at is backfilled from updated_at. This is an approximation — it is
the timestamp of the row's last save, not necessarily the closing update —
but it is the best signal available, since for most affected rows the bulk
close was the final write. closed_by stays NULL because the acting user was
never recorded.
"""

from django.db import migrations
from django.db.models import F


def backfill_closed_at(apps, schema_editor):
    VeteranCase = apps.get_model("vso", "VeteranCase")
    db_alias = schema_editor.connection.alias
    VeteranCase.objects.using(db_alias).filter(
        status__startswith="closed", closed_at__isnull=True
    ).update(closed_at=F("updated_at"))


class Migration(migrations.Migration):

    dependencies = [
        ("vso", "0010_alter_casenote_content"),
    ]

    operations = [
        migrations.RunPython(backfill_closed_at, migrations.RunPython.noop),
    ]
