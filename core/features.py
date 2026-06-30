"""
Feature flag utilities for dual-path development.

Path A = Direct-to-Veteran (B2C)
Path B = VSO Platform (B2B)

Usage:
    from core.features import feature_enabled, require_feature

    # In views
    if feature_enabled('organizations'):
        # Show org UI

    # As decorator
    @require_feature('organizations')
    def org_dashboard(request):
        ...

    # In templates (via context processor)
    {% if features.organizations %}
        <a href="{% url 'org:dashboard' %}">Organization</a>
    {% endif %}
"""

from functools import wraps
from django.conf import settings
from django.http import Http404
from django.shortcuts import redirect
from django.contrib import messages


def feature_enabled(feature_name: str) -> bool:
    """
    Check if a feature flag is enabled.

    Args:
        feature_name: Name of the feature flag

    Returns:
        True if enabled, False otherwise
    """
    return settings.FEATURES.get(feature_name, False)


def require_feature(feature_name: str, redirect_url: str = None):
    """
    Decorator that requires a feature to be enabled.

    If feature is disabled:
    - If redirect_url provided, redirects there with message
    - Otherwise raises Http404

    Usage:
        @require_feature('organizations')
        def org_view(request):
            ...

        @require_feature('organizations', redirect_url='home')
        def org_view(request):
            ...
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not feature_enabled(feature_name):
                if redirect_url:
                    messages.info(request, "This feature is not yet available.")
                    return redirect(redirect_url)
                raise Http404("Feature not available")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def get_enabled_features() -> dict:
    """
    Get all feature flags and their status.
    Used by context processor for templates.

    Returns:
        Dict of feature_name -> bool
    """
    return settings.FEATURES.copy()


def get_path_features() -> dict:
    """
    Get features organized by path.

    Returns:
        Dict with 'path_a', 'path_b', 'shared' keys
    """
    features = settings.FEATURES

    return {
        "path_a": {
            "freemium_limits": features.get("freemium_limits", False),
            "stripe_individual": features.get("stripe_individual", False),
            "usage_tracking": features.get("usage_tracking", False),
        },
        "path_b": {
            "organizations": features.get("organizations", False),
            "org_roles": features.get("org_roles", False),
            "org_invitations": features.get("org_invitations", False),
            "caseworker_assignment": features.get("caseworker_assignment", False),
            "org_billing": features.get("org_billing", False),
            "org_admin_dashboard": features.get("org_admin_dashboard", False),
            "audit_export": features.get("audit_export", False),
        },
        "future": {
            "sso_saml": features.get("sso_saml", False),
            "mfa": features.get("mfa", False),
        },
    }


class FeatureFlag:
    """
    Class-based feature flag checker for more complex scenarios.

    Usage:
        org_feature = FeatureFlag('organizations')

        if org_feature.is_enabled:
            ...

        if org_feature.is_enabled_for_user(user):
            ...
    """

    def __init__(self, feature_name: str):
        self.feature_name = feature_name

    @property
    def is_enabled(self) -> bool:
        """Check if globally enabled."""
        return feature_enabled(self.feature_name)

    def is_enabled_for_user(self, user) -> bool:
        """
        Check if enabled for specific user.
        Allows for user-specific rollout in the future.
        """
        # For now, just check global flag
        # Future: could check user.feature_flags or org settings
        if not self.is_enabled:
            return False

        # Could add user-specific logic here:
        # - Beta users
        # - Specific orgs
        # - Percentage rollout
        return True

    def is_enabled_for_org(self, organization) -> bool:
        """
        Check if enabled for specific organization.
        Allows for org-specific rollout.
        """
        if not self.is_enabled:
            return False

        # Future: check organization.enabled_features
        return True
