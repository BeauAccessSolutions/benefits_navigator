"""The Site row and allauth emails must carry real branding, not example.com.

allauth renders site_name/site_domain from django.contrib.sites' Site row.
The stock row ("example.com") leaked into production signup verification
emails — "Hello from example.com!" — observed live 2026-08-02.
Fixed by core/migrations/0012_set_default_site_domain.py plus branded
overrides of the confirmation email templates.
"""

from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.conf import settings as django_settings
from django.contrib.sites.models import Site
from django.core import mail
from django.urls import reverse

pytestmark = pytest.mark.django_db

SITE_DOMAIN = "vabenefitsnavigator.org"
SITE_NAME = "VA Benefits Navigator"

migration = import_module("core.migrations.0012_set_default_site_domain")


class TestSiteRow:
    def test_default_site_is_branded(self):
        site = Site.objects.get(pk=django_settings.SITE_ID)
        assert site.domain == SITE_DOMAIN
        assert site.name == SITE_NAME

    def test_migration_repairs_a_stock_row(self):
        Site.objects.filter(pk=django_settings.SITE_ID).update(
            domain="example.com", name="example.com"
        )
        migration.set_default_site(global_apps, None)
        site = Site.objects.get(pk=django_settings.SITE_ID)
        assert site.domain == SITE_DOMAIN
        assert site.name == SITE_NAME

    def test_migration_is_idempotent_and_creates_when_missing(self):
        Site.objects.all().delete()
        migration.set_default_site(global_apps, None)
        migration.set_default_site(global_apps, None)
        site = Site.objects.get(pk=django_settings.SITE_ID)
        assert site.domain == SITE_DOMAIN
        assert site.name == SITE_NAME


class TestConfirmationEmail:
    def test_signup_confirmation_email_is_branded(self, client, settings):
        settings.ACCOUNT_EMAIL_VERIFICATION = "mandatory"
        response = client.post(
            reverse("account_signup"),
            {
                "email": "vet@veteransmail.org",
                "password1": "correct-horse-battery-staple-77",
                "password2": "correct-horse-battery-staple-77",
            },
        )
        assert response.status_code == 302
        assert len(mail.outbox) == 1

        message = mail.outbox[0]
        assert SITE_NAME in message.subject
        assert "example.com" not in message.subject
        assert SITE_NAME in message.body
        assert "example.com" not in message.body
