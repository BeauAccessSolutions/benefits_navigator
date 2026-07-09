"""
URL configuration for benefits_navigator project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.sitemaps.views import sitemap
from django.views.generic import TemplateView
from django.http import JsonResponse
from api.graphql import JWTAuthGraphQLView

from core import views


def health_check(request):
    """Health check endpoint for load balancers and monitoring."""
    # Simple liveness check - just confirm app is running
    # Use ?full=1 for detailed status
    if request.GET.get("full") != "1":
        return JsonResponse({"status": "ok"}, status=200)

    # Full health check (for monitoring dashboards)
    from core.health import get_full_health_status

    health = get_full_health_status()
    status_code = 200 if health["status"] == "healthy" else 503
    return JsonResponse(health, status=status_code)


from accounts.views import (
    RateLimitedLoginView,
    RateLimitedSignupView,
    RateLimitedPasswordResetView,
)
from .schema import schema
from .sitemaps import sitemaps

# Require a verified TOTP device for /admin when enabled (privacy plan Phase 4)
if settings.ADMIN_OTP_REQUIRED:
    from django_otp.admin import OTPAdminSite
    admin.site.__class__ = OTPAdminSite

urlpatterns = [
    # Health check for load balancers/monitoring
    path("health/", health_check, name="health_check"),
    # SEO files
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
        name="robots_txt",
    ),
    path(
        "sitemap.xml",
        sitemap,
        {"sitemaps": sitemaps},
        name="django.contrib.sitemaps.views.sitemap",
    ),
    # Home page
    path("", views.home, name="home"),
    # User dashboard
    path("dashboard/", views.dashboard, name="dashboard"),
    # GraphQL API (supports both session and JWT auth)
    path("graphql/", JWTAuthGraphQLView.as_view(schema=schema), name="graphql"),
    # Mobile API (JWT auth)
    path("api/v1/", include("api.urls", namespace="api")),
    # Admin
    path("admin/", admin.site.urls),
    # Rate-limited auth views (override allauth defaults)
    path("accounts/login/", RateLimitedLoginView.as_view(), name="account_login"),
    path("accounts/signup/", RateLimitedSignupView.as_view(), name="account_signup"),
    path(
        "accounts/password/reset/",
        RateLimitedPasswordResetView.as_view(),
        name="account_reset_password",
    ),
    # Accounts app URLs (privacy, export, deletion)
    path("accounts/", include("accounts.urls", namespace="accounts")),
    # Two-Factor Authentication (MFA) URLs
    path("accounts/2fa/", include("allauth_2fa.urls")),
    # Authentication (django-allauth) - remaining URLs
    path("accounts/", include("allauth.urls")),
    # App URLs
    path("", include("core.urls")),
    path("claims/", include("claims.urls")),
    path("exam-prep/", include("examprep.urls")),
    path("appeals/", include("appeals.urls")),
    path("agents/", include("agents.urls")),
    path("docs/", include("documentation.urls", namespace="documentation")),
    path("vso/", include("vso.urls", namespace="vso")),
]

# Serve static files in development
# NOTE: Media files are NOT served directly for security reasons.
# All document access must go through protected views at /claims/document/<pk>/download/
# which verify authentication and ownership before serving files.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # DO NOT add: urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
