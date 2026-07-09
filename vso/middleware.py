"""
VSO Middleware - Security middleware for VSO staff access control.

Provides:
- MFA enforcement/encouragement for VSO staff accounts
- Organization scope validation
"""

from datetime import timedelta

from django.conf import settings
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone

from .views import get_user_staff_memberships


class VSOStaffMFAMiddleware:
    """
    Middleware that encourages/enforces MFA for VSO staff accounts.

    VSO staff (caseworkers and admins) handle sensitive veteran data.
    This middleware checks if they have MFA enabled and prompts them
    to set it up if not.

    Configuration:
        VSO_MFA_REQUIRED: If True, blocks VSO access without MFA (default: False)
        VSO_MFA_GRACE_PERIOD_DAYS: Days to allow access without MFA (default: 7)
    """

    # URLs that should be accessible without MFA check (to allow setup)
    EXEMPT_URLS = [
        "/accounts/2fa/",
        "/accounts/login/",
        "/accounts/logout/",
        "/accounts/signup/",
        "/admin/",
        "/health/",
    ]

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip for unauthenticated users
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Skip for exempt URLs
        path = request.path
        if any(path.startswith(exempt) for exempt in self.EXEMPT_URLS):
            return self.get_response(request)

        # Check if user is VSO staff
        memberships = get_user_staff_memberships(request.user)
        if not memberships.exists():
            return self.get_response(request)

        # User is VSO staff - check MFA status
        # django-otp adds is_verified() method to user via OTPMiddleware
        if hasattr(request.user, "is_verified"):
            # User has OTP middleware - check if verified or has devices
            from django_otp import devices_for_user

            user_devices = list(devices_for_user(request.user, confirmed=True))

            if not user_devices and path.startswith('/vso/'):
                # User has no MFA devices set up
                mfa_required = getattr(settings, 'VSO_MFA_REQUIRED', False)

                if mfa_required:
                    grace_days = getattr(settings, 'VSO_MFA_GRACE_PERIOD_DAYS', 7)
                    joined_at = (
                        memberships.order_by('created_at')
                        .values_list('created_at', flat=True)
                        .first()
                    )
                    grace_ends = (
                        joined_at + timedelta(days=grace_days)
                        if joined_at else timezone.now()
                    )

                    if timezone.now() >= grace_ends:
                        # Grace period over: block VSO access until 2FA exists
                        messages.error(
                            request,
                            'Two-factor authentication is required for VSO '
                            'staff accounts. Please set up 2FA to continue.'
                        )
                        return redirect('two-factor-setup')

                    # Still in grace period: warn with the deadline
                    days_left = max(0, (grace_ends - timezone.now()).days)
                    if not request.session.get('mfa_warning_shown'):
                        messages.warning(
                            request,
                            f'Two-factor authentication will be required for '
                            f'VSO access in {days_left} day(s). '
                            '<a href="/accounts/2fa/setup/" class="underline font-medium">'
                            'Set up 2FA now</a>',
                            extra_tags='safe'
                        )
                        request.session['mfa_warning_shown'] = True
                else:
                    # Encouragement mode: warn once per session, don't block
                    if not request.session.get('mfa_warning_shown'):
                        messages.warning(
                            request,
                            "For enhanced security, please enable two-factor authentication. "
                            '<a href="/accounts/2fa/setup/" class="underline font-medium">'
                            "Set up 2FA now</a>",
                            extra_tags="safe",
                        )
                        request.session["mfa_warning_shown"] = True

        return self.get_response(request)


def require_mfa_for_vso(view_func):
    """
    Decorator that requires MFA to be enabled for VSO staff views.

    Use this on sensitive VSO views that should require MFA.

    Usage:
        @require_mfa_for_vso
        def sensitive_vso_view(request):
            ...
    """
    from functools import wraps
    from django_otp import devices_for_user

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("account_login")

        # Check if user is VSO staff
        memberships = get_user_staff_memberships(request.user)
        if memberships.exists():
            # VSO staff must have MFA
            user_devices = list(devices_for_user(request.user, confirmed=True))
            if not user_devices:
                messages.error(
                    request,
                    "This action requires two-factor authentication. "
                    "Please set up 2FA to continue.",
                )
                return redirect("two-factor-setup")

        return view_func(request, *args, **kwargs)

    return wrapper
