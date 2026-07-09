"""
Feature gating decorators for premium features.

These decorators check user subscription status and usage limits
before allowing access to premium features.
"""

from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse


def premium_required(view_func):
    """
    Decorator that requires premium subscription.
    Redirects free users to upgrade page.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("account_login")

        if not request.user.is_premium:
            messages.warning(
                request,
                "This feature requires a Premium subscription. "
                "Upgrade to unlock unlimited access to all features.",
            )
            return redirect("accounts:upgrade")

        return view_func(request, *args, **kwargs)

    return wrapper


def check_document_limit(view_func):
    """
    Decorator that checks document upload limits.
    Used on upload views to enforce free tier limits.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("account_login")

        from .models import UsageTracking

        usage, _ = UsageTracking.objects.get_or_create(user=request.user)

        # For GET requests, just check if they can upload (for UI display)
        # For POST requests, the form validation will do the detailed check
        if request.method == "GET":
            can_upload, reason = usage.can_upload_document(0)
            if not can_upload:
                messages.warning(
                    request, reason + " Upgrade to Premium for unlimited uploads."
                )
                # Still allow them to see the page, but show the warning

        return view_func(request, *args, **kwargs)

    return wrapper


def check_denial_decoder_limit(view_func):
    """
    Decorator that checks denial decoder usage limits.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("account_login")

        from .models import UsageTracking

        usage, _ = UsageTracking.objects.get_or_create(user=request.user)

        can_use, reason = usage.can_use_denial_decoder()
        if not can_use:
            messages.warning(
                request, reason + " Upgrade to Premium for unlimited denial decodes."
            )
            return redirect("accounts:upgrade")

        return view_func(request, *args, **kwargs)

    return wrapper


def check_ai_analysis_limit(view_func):
    """
    Decorator that checks AI analysis usage limits.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("account_login")

        from .models import UsageTracking

        usage, _ = UsageTracking.objects.get_or_create(user=request.user)

        can_use, reason = usage.can_use_ai_analysis()
        if not can_use:
            messages.warning(
                request, reason + " Upgrade to Premium for unlimited AI analyses."
            )
            return redirect("accounts:upgrade")

        return view_func(request, *args, **kwargs)

    return wrapper


def api_check_limit(limit_type):
    """
    Decorator for API endpoints that returns JSON errors.

    Args:
        limit_type: One of 'document', 'denial_decoder', 'ai_analysis'
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({"error": "Authentication required"}, status=401)

            from .models import UsageTracking

            usage, _ = UsageTracking.objects.get_or_create(user=request.user)

            if limit_type == "document":
                can_use, reason = usage.can_upload_document(0)
            elif limit_type == "denial_decoder":
                can_use, reason = usage.can_use_denial_decoder()
            elif limit_type == "ai_analysis":
                can_use, reason = usage.can_use_ai_analysis()
            else:
                can_use, reason = True, ""

            if not can_use:
                return JsonResponse(
                    {
                        "error": "limit_exceeded",
                        "message": reason,
                        "upgrade_url": "/accounts/upgrade/",
                    },
                    status=403,
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def record_usage(usage_type):
    """
    Decorator that records usage after successful operations.

    Args:
        usage_type: One of 'document_upload', 'denial_decode', 'ai_analysis'

    Note: For document uploads, you should call record_document_upload
    directly in the view with the file size. This decorator is for
    simpler operations.
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            response = view_func(request, *args, **kwargs)

            # Only record on successful POST requests
            if request.method == "POST" and hasattr(response, "status_code"):
                if response.status_code in [200, 201, 302]:
                    if request.user.is_authenticated:
                        from .models import UsageTracking

                        usage, _ = UsageTracking.objects.get_or_create(
                            user=request.user
                        )

                        if usage_type == "denial_decode":
                            usage.record_denial_decode()
                        elif usage_type == "ai_analysis":
                            usage.record_ai_analysis()

            return response

        return wrapper

    return decorator
