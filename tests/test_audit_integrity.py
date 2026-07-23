"""
Audit-trail integrity.

Two findings from the 2026-07-23 pass of the platform multi-role test matrix
(bas-platform docs/testing/multi-role-test-matrix.yaml, tests AUDIT-01/AUDIT-02):

- AUDIT-02: AuditLogAdmin allowed superusers to delete audit rows, so an admin
  could erase the record of their own access.
- AUDIT-01: the three bulk-export call sites built rows via objects.create() and
  stored REMOTE_ADDR directly. Behind the App Platform load balancer that is the
  proxy address, so the source IP was a constant on exactly the events an incident
  responder needs it for.

Both are the kind of fix that regresses silently — nothing user-visible changes
when they break.
"""

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import Client, RequestFactory
from django.urls import reverse

from accounts.models import Organization, OrganizationMembership
from core.admin import AuditLogAdmin
from core.models import AuditLog
from vso.models import VeteranCase

pytestmark = [pytest.mark.django_db, pytest.mark.integration]

PROXY_ADDR = "10.0.0.9"  # what REMOTE_ADDR looks like behind the load balancer
CLIENT_ADDR = "203.0.113.7"  # the real caller, only present in X-Forwarded-For


@pytest.fixture
def org(db):
    return Organization.objects.create(
        name="Audit VSO", slug="audit-vso", org_type="vso"
    )


class TestAuditLogIsAppendOnly:
    """AUDIT-02: nobody deletes audit history through the admin."""

    def _admin(self):
        return AuditLogAdmin(AuditLog, AdminSite())

    def test_superuser_cannot_delete(self, django_user_model, user_password):
        superuser = django_user_model.objects.create_superuser(
            email="root@example.com", password=user_password
        )
        request = RequestFactory().get("/admin/")
        request.user = superuser

        assert self._admin().has_delete_permission(request) is False
        assert self._admin().has_delete_permission(request, obj=AuditLog()) is False

    def test_add_and_change_also_blocked(self, django_user_model, user_password):
        superuser = django_user_model.objects.create_superuser(
            email="root2@example.com", password=user_password
        )
        request = RequestFactory().get("/admin/")
        request.user = superuser

        assert self._admin().has_add_permission(request) is False
        assert self._admin().has_change_permission(request) is False


class TestExportAuditRecordsClientIP:
    """AUDIT-01: bulk pulls record the caller, not the load balancer."""

    def _org_admin_client(self, org, django_user_model, user_password):
        admin = django_user_model.objects.create_user(
            email="orgadmin@vso.org", password=user_password
        )
        OrganizationMembership.objects.create(
            organization=org, user=admin, role="admin"
        )
        client = Client()
        client.login(email="orgadmin@vso.org", password=user_password)
        return client

    def test_case_export_records_forwarded_for(
        self, org, django_user_model, user_password
    ):
        veteran = django_user_model.objects.create_user(
            email="vet-export@example.com", password=user_password
        )
        VeteranCase.objects.create(
            organization=org, veteran=veteran, title="Exported", status="intake"
        )
        client = self._org_admin_client(org, django_user_model, user_password)

        client.get(
            reverse("vso:case_list"),
            {"export": "csv"},
            REMOTE_ADDR=PROXY_ADDR,
            HTTP_X_FORWARDED_FOR=f"{CLIENT_ADDR}, {PROXY_ADDR}",
        )

        entry = AuditLog.objects.filter(action="vso_case_export").latest("timestamp")
        assert entry.ip_address == CLIENT_ADDR, (
            "bulk export logged the proxy address — the call site is bypassing "
            "AuditLog.log()/_get_client_ip again"
        )
        assert entry.user_email == "orgadmin@vso.org"
        assert entry.request_path

    def test_report_export_records_forwarded_for(
        self, org, django_user_model, user_password
    ):
        client = self._org_admin_client(org, django_user_model, user_password)

        client.get(
            reverse("vso:reports"),
            {"export": "csv"},
            REMOTE_ADDR=PROXY_ADDR,
            HTTP_X_FORWARDED_FOR=f"{CLIENT_ADDR}, {PROXY_ADDR}",
        )

        entry = AuditLog.objects.filter(action="vso_report_export").latest("timestamp")
        assert entry.ip_address == CLIENT_ADDR
        assert entry.details.get("format") == "csv"
