"""The detailed health check has to actually be reachable — and only by operators.

``HealthCheckMiddleware`` sits in front of everything so DigitalOcean's
internal-IP liveness probe can answer without tripping ALLOWED_HOSTS. It
matched on ``request.path`` alone, which meant it also swallowed
``/health/?full=1`` and returned a flat ``{"status": "ok"}``. The endpoint
documented for monitoring dashboards reported healthy no matter how sick the
system was, and nothing failed loudly enough to notice — the liveness probe
kept passing, which is exactly what it was doing wrong.

Making it reachable is only half the fix. The full status reports database,
Redis, Celery worker and queue state: a map of the infrastructure and a live
signal of when it is weak. So these tests pin both halves — the detailed check
runs, and it does not run for anonymous callers.
"""

import pytest
from django.urls import reverse

LIVENESS = "/health/"
FULL = "/health/?full=1"


@pytest.mark.django_db
class TestLivenessProbe:
    """The DO health check must keep working exactly as before."""

    def test_plain_health_is_ok_and_needs_no_auth(self, client):
        response = client.get(LIVENESS)

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_liveness_still_bypasses_allowed_hosts(self, client, settings):
        """
        The reason the middleware exists: DO probes from 10.244.x.x, which is
        not in ALLOWED_HOSTS. Narrowing the match must not break that.
        """
        settings.ALLOWED_HOSTS = ["example.com"]

        response = client.get(LIVENESS, headers={"host": "10.244.1.7"})

        assert response.status_code == 200

    def test_url_name_still_resolves(self):
        assert reverse("health_check") == LIVENESS


@pytest.mark.django_db
class TestFullStatusReachability:
    def test_full_check_is_no_longer_swallowed_by_the_middleware(
        self, admin_client, settings
    ):
        """The regression: this used to return the flat liveness payload."""
        response = admin_client.get(FULL)

        body = response.json()
        assert "checks" in body, "middleware short-circuited the detailed view"
        assert "database" in body["checks"]

    def test_full_check_reports_an_unhealthy_system_with_503(
        self, admin_client, monkeypatch
    ):
        """A health endpoint that cannot say 'unhealthy' is decoration."""
        import core.health

        monkeypatch.setattr(
            core.health,
            "get_full_health_status",
            lambda: {"status": "unhealthy", "checks": {"database": {}}},
        )

        assert admin_client.get(FULL).status_code == 503


@pytest.mark.django_db
class TestFullStatusAccess:
    def test_anonymous_callers_are_refused(self, client):
        response = client.get(FULL)

        assert response.status_code == 403
        assert "checks" not in response.json()

    def test_ordinary_users_are_refused(self, authenticated_client):
        assert authenticated_client.get(FULL).status_code == 403

    def test_staff_may_read_it(self, admin_client):
        assert admin_client.get(FULL).status_code in (200, 503)

    def test_monitoring_may_read_it_with_the_token_header(self, client, settings):
        settings.HEALTH_CHECK_TOKEN = "s3cret-token"

        response = client.get(FULL, headers={"x-health-token": "s3cret-token"})

        assert response.status_code in (200, 503)
        assert "checks" in response.json()

    def test_a_wrong_token_is_refused(self, client, settings):
        settings.HEALTH_CHECK_TOKEN = "s3cret-token"

        response = client.get(FULL, headers={"x-health-token": "wrong"})

        assert response.status_code == 403

    def test_an_unset_token_does_not_admit_an_empty_header(self, client, settings):
        """The obvious way to get this wrong: "" == "" opens the endpoint."""
        settings.HEALTH_CHECK_TOKEN = ""

        response = client.get(FULL, headers={"x-health-token": ""})

        assert response.status_code == 403
