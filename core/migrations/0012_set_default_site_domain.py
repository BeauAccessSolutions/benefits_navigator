"""Brand the django.contrib.sites Site row used by allauth emails.

The stock Site row ships as "example.com", which leaked into production
signup verification emails ("Hello from example.com!") because allauth
renders site_name/site_domain from this row. Observed live 2026-08-02.
"""

from django.conf import settings
from django.db import migrations

SITE_DOMAIN = "vabenefitsnavigator.org"
SITE_NAME = "VA Benefits Navigator"


def set_default_site(apps, schema_editor):
    Site = apps.get_model("sites", "Site")
    Site.objects.update_or_create(
        pk=getattr(settings, "SITE_ID", 1),
        defaults={"domain": SITE_DOMAIN, "name": SITE_NAME},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_alter_auditlog_action"),
        ("sites", "0002_alter_domain_unique"),
    ]

    operations = [
        migrations.RunPython(set_default_site, migrations.RunPython.noop),
    ]
