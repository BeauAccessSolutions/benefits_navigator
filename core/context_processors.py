"""
Custom context processors for making variables available to all templates
"""

from django.conf import settings


def site_settings(request):
    """
    Add site-wide settings to template context
    """
    return {
        "SITE_NAME": settings.SITE_NAME,
        "SITE_DESCRIPTION": settings.SITE_DESCRIPTION,
        "SUPPORT_EMAIL": settings.SUPPORT_EMAIL,
        "DEBUG": settings.DEBUG,
    }


def user_usage(request):
    """
    Add user's usage information to template context for freemium display.

    Available in templates as:
    - {{ user_usage.is_premium }}
    - {{ user_usage.documents_used }} / {{ user_usage.documents_limit }}
    - {{ user_usage.documents_remaining }}
    - {{ user_usage.storage_used_mb }} / {{ user_usage.storage_limit_mb }}
    - {{ user_usage.storage_percentage }}
    - {{ user_usage.denial_decodes_remaining }}
    - {{ user_usage.ai_analyses_remaining }}
    """
    if not request.user.is_authenticated:
        return {"user_usage": None}

    from accounts.models import UsageTracking

    try:
        usage, _ = UsageTracking.objects.get_or_create(user=request.user)
        return {"user_usage": usage.get_usage_summary()}
    except Exception:
        return {"user_usage": None}


def tier_limits(request):
    """
    Add tier limit settings to template context for display.

    Available as:
    - {{ tier_limits.free_documents }}
    - {{ tier_limits.free_storage_mb }}
    - {{ tier_limits.free_denial_decodes }}
    - {{ tier_limits.free_ai_analyses }}
    """
    return {
        "tier_limits": {
            "free_documents": getattr(settings, "FREE_TIER_DOCUMENTS_PER_MONTH", 3),
            "free_storage_mb": getattr(settings, "FREE_TIER_MAX_STORAGE_MB", 100),
            "free_denial_decodes": getattr(
                settings, "FREE_TIER_DENIAL_DECODES_PER_MONTH", 2
            ),
            "free_ai_analyses": getattr(settings, "FREE_TIER_AI_ANALYSES_PER_MONTH", 5),
        }
    }


def feature_flags(request):
    """
    Add feature flags to template context.

    Available as:
    - {% if features.organizations %}...{% endif %}
    - {% if features.org_billing %}...{% endif %}

    Usage in templates:
        {% if features.organizations %}
            <a href="{% url 'accounts:org_dashboard' %}">My Organization</a>
        {% endif %}
    """
    from core.features import get_enabled_features

    return {
        "features": get_enabled_features(),
    }


def vso_access(request):
    """
    Add VSO access information to template context.

    Available as:
    - {{ is_vso_staff }} - True if user is VSO admin or caseworker
    - {{ user_organization }} - The user's primary organization (if VSO staff)

    Usage in templates:
        {% if is_vso_staff %}
            <a href="{% url 'vso:dashboard' %}">VSO Portal</a>
        {% endif %}
    """
    if not request.user.is_authenticated:
        return {
            "is_vso_staff": False,
            "user_organization": None,
        }

    try:
        membership = (
            request.user.memberships.filter(
                role__in=["admin", "caseworker"],
                is_active=True,
                organization__is_active=True,
            )
            .select_related("organization")
            .first()
        )

        return {
            "is_vso_staff": membership is not None,
            "user_organization": membership.organization if membership else None,
        }
    except Exception:
        return {
            "is_vso_staff": False,
            "user_organization": None,
        }


def pilot_mode(request):
    """
    Add pilot mode settings to template context.

    Available as:
    - {{ pilot_mode }} - True if PILOT_MODE is enabled
    - {{ pilot_billing_disabled }} - True if billing is disabled
    - {{ is_pilot_user }} - True if current user has pilot premium access

    Usage in templates:
        {% if pilot_mode %}
            <span class="badge">Pilot</span>
        {% endif %}

        {% if is_pilot_user %}
            <span>Premium (Pilot)</span>
        {% endif %}
    """
    context = {
        "pilot_mode": getattr(settings, "PILOT_MODE", False),
        "pilot_billing_disabled": getattr(settings, "PILOT_BILLING_DISABLED", False),
        "is_pilot_user": False,
    }

    if request.user.is_authenticated:
        context["is_pilot_user"] = getattr(request.user, "is_pilot_user", False)

    return context
