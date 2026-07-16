"""
BAS shared-identity (Keycloak OIDC) settings for Benefits Navigator.

Inert by default (mirrors KindredAccess's ``mysite/oidc_config.py``): with
``KEYCLOAK_ISSUER`` / ``OIDC_RP_CLIENT_ID`` unset, ``OIDC_ENABLED`` is False, the
``openid_connect`` provider is never added to ``INSTALLED_APPS`` or
``SOCIALACCOUNT_PROVIDERS``, and BN keeps its existing django-allauth
email/password login completely untouched.

Why allauth's built-in ``openid_connect`` provider (NOT mozilla-django-oidc):
BN is already an allauth app (``django-allauth`` 65.x + ``allauth-2fa``), and
``allauth.socialaccount`` is already installed, so SSO is *config, not a new
dependency*. It plugs into allauth's existing login / signup / 2FA /
email-verification flows. Bolting on ``mozilla-django-oidc`` (which CIT and
KindredAccess use — they are not allauth apps) would create a parallel auth path
that bypasses ``allauth-2fa`` (``ACCOUNT_ADAPTER = allauth_2fa.adapter.OTPAdapter``)
— an MFA-bypass risk.

Platform contract (see ~/projects/bas-platform):
  - Realm ``bas``; issuer https://id.beauaccesssolutions.com/realms/bas (prod).
  - ``benefits-navigator-web`` is a CONFIDENTIAL client + PKCE (S256). The Django
    backend can hold a secret, so confidential + PKCE is the correct,
    strictly-stronger choice (the ADRs mandate PKCE, pairwise sub, and audience
    isolation — not "public" specifically).
  - Pairwise ``sub`` (ADR-003) is enforced Keycloak-side; allauth receives an
    already-pairwise ``sub`` as ``SocialAccount.uid`` — no app change needed.
  - Provider id is ``keycloak``, so allauth's callback path is
    ``/accounts/oidc/keycloak/login/callback/`` — this MUST match the redirect
    URI registered on the realm client.

Full scope: docs/deploy/benefits-navigator-oidc-integration.md in bas-platform.
"""

# The allauth provider_id. Drives the RP callback URL path
# (/accounts/oidc/<PROVIDER_ID>/login/callback/), which MUST match the redirect
# URI registered on the Keycloak `benefits-navigator-web` client.
OIDC_PROVIDER_ID = "keycloak"

# Human-facing label on the "Sign in with ..." button and the Keycloak app name.
OIDC_PROVIDER_NAME = "Beau Access Solutions"

# Session keys used to defer MFA to Keycloak for SSO users (decision #1):
# accounts.adapters records whether the id_token asserted a second factor, and
# vso.middleware treats an SSO session as MFA-satisfied without a local
# allauth-2fa device (which SSO users don't enroll).
SSO_SESSION_KEY = "bas_sso"          # this login came in via Keycloak SSO
SSO_MFA_SESSION_KEY = "bas_sso_mfa"  # Keycloak asserted a second factor (acr/amr)


def build_oidc_config(env):
    """Return a dict of Django/allauth settings to merge into settings globals.

    ``env`` is the project's ``environ.Env`` instance (already ``read_env``'d in
    settings.py). Always returns ``OIDC_ENABLED``; when enabled, also returns the
    ``openid_connect`` provider registration and ``KEYCLOAK_ISSUER`` (used for
    RP-initiated logout / audience checks).
    """
    issuer = env("KEYCLOAK_ISSUER", default="").rstrip("/")
    client_id = env("OIDC_RP_CLIENT_ID", default="")
    enabled = bool(issuer and client_id)

    cfg = {"OIDC_ENABLED": enabled}
    if not enabled:
        return cfg

    cfg.update(
        {
            "KEYCLOAK_ISSUER": issuer,
            "OIDC_RP_CLIENT_ID": client_id,
            "SOCIALACCOUNT_PROVIDERS": {
                "openid_connect": {
                    # PKCE (S256) on a confidential client is strictly stronger;
                    # the realm client sets pkce.code.challenge.method=S256.
                    "OAUTH_PKCE_ENABLED": True,
                    "APPS": [
                        {
                            "provider_id": OIDC_PROVIDER_ID,
                            "name": OIDC_PROVIDER_NAME,
                            "client_id": client_id,
                            "secret": env("OIDC_RP_CLIENT_SECRET", default=""),
                            "settings": {
                                # The provider appends /.well-known/... if absent,
                                # but be explicit so it's obvious what's fetched.
                                "server_url": f"{issuer}/.well-known/openid-configuration",
                                # Keycloak confidential clients accept
                                # client_secret_basic; declare it so allauth
                                # doesn't have to sniff it from the metadata.
                                "token_auth_method": "client_secret_basic",
                            },
                        }
                    ],
                }
            },
        }
    )
    return cfg
