"""Deployment-configuration system checks.

The staging app ran with DEBUG=False and: no ANTHROPIC_API_KEY (every AI
feature dead), no SENTRY_DSN (Sentry never initialized, so nobody saw the
errors), the console email backend (ACCOUNT_EMAIL_VERIFICATION is "mandatory"
when DEBUG is off, so no signup could ever complete), and SITE_URL left at
http://localhost:8000 (veteran invitation emails linked to localhost).
Nothing crashed at boot; every one of those defaults is individually
reasonable for development, which is exactly why the combination shipped.

These checks turn that configuration state into a failed deploy instead of a
silently broken app. They are registered with deploy=True, so they run only
under ``manage.py check --deploy`` — the PRE_DEPLOY job in
``app-spec.yaml.template`` runs it before migrations, and a failure halts the
rollout while the previous container keeps serving. They never run during
tests or ``runserver``, and they no-op entirely when DEBUG is true so a
developer running ``check --deploy`` locally isn't blocked.

Audit reference: benefits-navigator-experience-audit-2026-08-02, P0-1..P0-4.
"""

from django.conf import settings
from django.core.checks import Error, Tags, register

# Backends that swallow or divert mail instead of delivering it. Fine in
# development; in a deployment they make signup verification, password
# resets, and VSO invitations silently undeliverable.
DEV_ONLY_EMAIL_BACKENDS = frozenset(
    {
        "django.core.mail.backends.console.EmailBackend",
        "django.core.mail.backends.filebased.EmailBackend",
        "django.core.mail.backends.locmem.EmailBackend",
        "django.core.mail.backends.dummy.EmailBackend",
    }
)


@register(Tags.security, deploy=True)
def check_deployed_configuration(app_configs, **kwargs):
    """Fail the deploy when a DEBUG=False process still has dev defaults."""
    if settings.DEBUG:
        return []

    errors = []

    if settings.EMAIL_BACKEND in DEV_ONLY_EMAIL_BACKENDS:
        errors.append(
            Error(
                f"EMAIL_BACKEND is {settings.EMAIL_BACKEND!r} with DEBUG=False.",
                hint=(
                    "Email verification is mandatory in production, so no new "
                    "signup can ever complete, and password resets and VSO "
                    "invitations go nowhere. Set the EMAIL_BACKEND, EMAIL_HOST, "
                    "EMAIL_HOST_USER, EMAIL_HOST_PASSWORD, and "
                    "DEFAULT_FROM_EMAIL environment variables."
                ),
                id="core.E001",
            )
        )

    if not settings.ANTHROPIC_API_KEY:
        errors.append(
            Error(
                "ANTHROPIC_API_KEY is empty with DEBUG=False.",
                hint=(
                    "Every AI feature (document analysis, decision decoding, "
                    "statement generation) fails without it. Set it as an "
                    "encrypted environment variable."
                ),
                id="core.E002",
            )
        )

    if not settings.SENTRY_DSN:
        errors.append(
            Error(
                "SENTRY_DSN is empty with DEBUG=False.",
                hint=(
                    "Sentry never initializes, so production errors are "
                    "invisible. Set it as an encrypted environment variable."
                ),
                id="core.E003",
            )
        )

    site_url = settings.SITE_URL
    if "localhost" in site_url or "127.0.0.1" in site_url:
        errors.append(
            Error(
                f"SITE_URL is {site_url!r} with DEBUG=False.",
                hint=(
                    "Veteran invitation links are built from SITE_URL "
                    "(vso/views.py), so invitation emails would point at "
                    "localhost. Set SITE_URL to the public origin, e.g. "
                    "https://vabenefitsnavigator.org."
                ),
                id="core.E004",
            )
        )

    return errors
