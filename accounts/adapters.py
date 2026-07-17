"""
Custom allauth SocialAccount adapter for BAS Keycloak SSO.

Two responsibilities, both driven by the integration decisions recorded in
docs/deploy/benefits-navigator-oidc-integration.md (bas-platform):

1. Verified-email account linking (ADR-004 / decision #2). When a returning SSO
   user's Keycloak email is verified AND matches an existing local BN account,
   connect the social login to that account instead of creating a duplicate. We
   link ONLY on a verified email — silently linking an *unverified* email is an
   account-takeover vector (an attacker who controls a Keycloak account with a
   victim's unverified email would otherwise inherit the victim's BN account).

2. Keycloak step-up MFA (decision #1). BN defers MFA to Keycloak for SSO users
   rather than double-prompting them with a second, local allauth-2fa factor. We
   read the id_token's ``acr``/``amr`` and record on the session whether the IdP
   asserted a second factor, so ``vso.middleware.VSOStaffMFAMiddleware`` can
   treat an SSO session as MFA-satisfied without a local TOTP device (which SSO
   users don't enroll). Without this, VSO_MFA_REQUIRED would lock every SSO user
   out of /vso/.

This is the SOCIALACCOUNT_ADAPTER only; ACCOUNT_ADAPTER stays
``allauth_2fa.adapter.OTPAdapter`` so the local-login 2FA path is unchanged.
"""

from __future__ import annotations

import logging

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model

from benefits_navigator.oidc_config import SSO_MFA_SESSION_KEY, SSO_SESSION_KEY

logger = logging.getLogger(__name__)

# ``amr`` values that indicate a second factor ran at Keycloak. Keycloak emits
# amr entries such as ["pwd", "otp"] and may use "mfa" for a step-up flow.
_MFA_AMR_VALUES = {"otp", "totp", "mfa", "hwk", "sms", "swk"}


def _sso_did_mfa(id_token: dict) -> bool:
    """True when the id_token asserts a second authentication factor.

    Prefers ``amr`` (authentication methods), falling back to ``acr`` (an LoA:
    the string "mfa" or a numeric level > 1). Conservative: an absent/ambiguous
    claim reads as "no MFA", so the VSO gate never *weakens* on a malformed token.
    """
    amr = id_token.get("amr") or []
    if isinstance(amr, str):
        amr = [amr]
    if any(str(v).lower() in _MFA_AMR_VALUES for v in amr):
        return True

    acr = id_token.get("acr")
    if acr is not None:
        acr_s = str(acr).strip().lower()
        if acr_s == "mfa":
            return True
        try:
            return int(acr_s) > 1
        except ValueError:
            return False
    return False


class BASSocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """Runs after the OIDC round-trip, before the user is logged in.

        ``sociallogin.account.extra_data`` already holds the decoded id_token
        (allauth's openid_connect adapter stores it as ``{"id_token": {...}}``),
        and ``sociallogin.email_addresses`` carries per-address ``verified`` flags
        derived from Keycloak's ``email_verified`` claim.
        """
        # --- Record the Keycloak MFA assertion for this session (decision #1) ---
        extra = getattr(sociallogin.account, "extra_data", None) or {}
        id_token = extra.get("id_token")
        if not isinstance(id_token, dict):
            id_token = {}
        request.session[SSO_SESSION_KEY] = True
        request.session[SSO_MFA_SESSION_KEY] = _sso_did_mfa(id_token)

        # --- Verified-email linking (decision #2 / ADR-004) ---
        if sociallogin.is_existing:
            # This Keycloak identity is already linked to a local user — nothing
            # to reconcile; allauth will log that user in.
            return

        email = ((sociallogin.user.email if sociallogin.user else "") or "").strip()
        if not email:
            return

        # Only trust an email Keycloak marked verified for THIS address.
        verified = any(
            (addr.email or "").lower() == email.lower() and addr.verified
            for addr in sociallogin.email_addresses
        )
        if not verified:
            # Unverified email → do NOT auto-link. allauth continues as a fresh
            # signup (auto-signup) or its normal email-conflict handling.
            logger.info(
                "SSO login for %s has an unverified email; not auto-linking to a local account.",
                email,
            )
            return

        User = get_user_model()
        try:
            existing = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return  # genuinely new user; let allauth provision the account
        except User.MultipleObjectsReturned:
            # Ambiguous — refuse to auto-link rather than guess. Needs manual
            # reconciliation (a data-integrity issue predating SSO).
            logger.warning(
                "SSO email %s matches multiple local accounts; not auto-linking.", email
            )
            return

        # Verified email + exactly one local match → connect this SSO identity to
        # the existing account (no duplicate user is created).
        sociallogin.connect(request, existing)
