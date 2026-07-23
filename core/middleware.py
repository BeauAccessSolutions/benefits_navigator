"""
Custom middleware for the VA Benefits Navigator.
"""

import logging
import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class HealthCheckMiddleware:
    """
    Middleware to handle health check requests before ALLOWED_HOSTS validation.

    This must be placed BEFORE django.middleware.common.CommonMiddleware
    in MIDDLEWARE settings to bypass the Host header check for health endpoints.

    DigitalOcean App Platform uses internal IPs (e.g., 10.244.x.x) for health checks,
    which would fail ALLOWED_HOSTS validation.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Respond to health check without checking ALLOWED_HOSTS
        if request.path == "/health/" or request.path == "/health":
            return JsonResponse({"status": "ok", "message": "Service is running"})

        return self.get_response(request)


class AuditMiddleware(MiddlewareMixin):
    """
    Middleware to automatically log security-sensitive operations.

    Logs:
    - Document uploads, views, downloads, deletions
    - AI analysis operations
    - Authentication events (handled separately by signals)
    - Profile/account changes
    """

    # Paths that trigger document-related audit logs
    DOCUMENT_PATHS = [
        "/claims/document/",
        "/claims/decode/",
    ]

    # Paths that trigger AI analysis logs
    AI_ANALYSIS_PATHS = [
        "/agents/",
        "/claims/decode/",
    ]

    # Paths to skip (high-frequency, low-security)
    SKIP_PATHS = [
        "/static/",
        "/media/",
        "/favicon.ico",
        "/__debug__/",
        "/health/",
    ]

    def process_request(self, request):
        """Store request info for use in process_response."""
        # Skip static/media requests
        for skip_path in self.SKIP_PATHS:
            if request.path.startswith(skip_path):
                request._skip_audit = True
                return None

        request._skip_audit = False
        return None

    def process_response(self, request, response):
        """Log completed requests based on path and response."""
        # Skip if marked
        if getattr(request, "_skip_audit", True):
            return response

        # Skip non-authenticated requests for most logging
        if not hasattr(request, "user") or not request.user.is_authenticated:
            return response

        # Skip non-successful responses for most operations
        if response.status_code >= 400:
            return response

        try:
            self._audit_request(request, response)
        except Exception as e:
            # Never let audit logging break the request
            logger.error(f"Audit logging error: {e}")

        return response

    def _audit_request(self, request, response):
        """Determine and create appropriate audit log entries."""
        from .models import AuditLog

        path = request.path
        method = request.method

        # Document upload (POST to upload endpoint)
        if (
            "/document/upload/" in path
            and method == "POST"
            and response.status_code in [200, 201, 302]
        ):
            AuditLog.log(
                action="document_upload",
                request=request,
                details={"upload_path": path},
            )
            return

        # Document view (GET on document detail)
        if "/document/" in path and method == "GET" and "/download/" not in path:
            # Try to extract document ID from path
            doc_id = self._extract_id_from_path(path, "document")
            if doc_id:
                AuditLog.log(
                    action="document_view",
                    request=request,
                    resource_type="Document",
                    resource_id=doc_id,
                )
            return

        # Document download
        if "/document/" in path and "/download/" in path and method == "GET":
            doc_id = self._extract_id_from_path(path, "document")
            if doc_id:
                AuditLog.log(
                    action="document_download",
                    request=request,
                    resource_type="Document",
                    resource_id=doc_id,
                )
            return

        # Document delete
        if "/document/" in path and "/delete/" in path and method == "POST":
            doc_id = self._extract_id_from_path(path, "document")
            if doc_id:
                AuditLog.log(
                    action="document_delete",
                    request=request,
                    resource_type="Document",
                    resource_id=doc_id,
                )
            return

        # Denial decoder (AI analysis)
        if (
            "/decode/" in path
            and method == "POST"
            and response.status_code in [200, 201, 302]
        ):
            AuditLog.log(
                action="denial_decode",
                request=request,
                details={"decode_path": path},
            )
            return

        # AI analysis endpoints
        if "/agents/" in path and "/analyze" in path and method == "POST":
            AuditLog.log(
                action="ai_analysis",
                request=request,
                details={"analysis_path": path},
            )
            return

        # Profile update
        if "/accounts/profile/" in path and method == "POST":
            AuditLog.log(
                action="profile_update",
                request=request,
            )
            return

    def _extract_id_from_path(self, path: str, resource_name: str) -> int | None:
        """Extract numeric ID from URL path after resource name."""
        try:
            parts = path.split("/")
            for i, part in enumerate(parts):
                if part == resource_name and i + 1 < len(parts):
                    next_part = parts[i + 1]
                    if next_part.isdigit():
                        return int(next_part)
        except (ValueError, IndexError):
            pass
        return None


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add additional security headers to all responses.

    NOTE: CSP is handled by django-csp middleware (csp.middleware.CSPMiddleware)
    configured in settings.py. Do NOT set CSP here to avoid conflicts.

    NOTE: The following headers are already set via Django settings:
    - X-Content-Type-Options (SECURE_CONTENT_TYPE_NOSNIFF)
    - X-Frame-Options (X_FRAME_OPTIONS)
    - Referrer-Policy (SECURE_REFERRER_POLICY)

    This middleware only adds headers not covered by Django settings.
    """

    def process_response(self, request, response):
        # Only add Permissions-Policy as it's not covered by Django settings
        # This restricts access to browser features for security
        if "Permissions-Policy" not in response:
            response["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response


# Session key holding the unix timestamp of the last request on the session.
IDLE_ACTIVITY_KEY = "_last_activity"


class IdleSessionTimeoutMiddleware:
    """
    Automatic logoff after inactivity — HIPAA Security Rule §164.312(a)(2)(iii).

    For authenticated users, tracks the timestamp of the last request in the
    session. If the gap since the last request exceeds ``SESSION_IDLE_TIMEOUT``
    seconds, the session is logged out (flushed) before the view runs and the
    user is redirected to the login page. Protects an unattended workstation
    that has veteran PHI on screen.

    Must run after AuthenticationMiddleware (needs ``request.user``) and after
    SessionMiddleware (reads/writes ``request.session``). A timeout of 0
    disables the behavior.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Read per request so runtime config / override_settings takes effect.
        timeout = getattr(settings, "SESSION_IDLE_TIMEOUT", 0) or 0

        if timeout and self._is_authenticated(request):
            now = int(time.time())
            last = request.session.get(IDLE_ACTIVITY_KEY)

            if last is not None and (now - last) > timeout:
                return self._expire(request)

            # Record activity. Assigning to the session marks it modified so it
            # is saved even without SESSION_SAVE_EVERY_REQUEST.
            request.session[IDLE_ACTIVITY_KEY] = now

        return self.get_response(request)

    @staticmethod
    def _is_authenticated(request):
        return hasattr(request, "user") and request.user.is_authenticated

    @staticmethod
    def _expire(request):
        logout(request)  # flushes the session, clearing the activity marker
        messages.info(
            request, "You were signed out due to inactivity. Please sign in again."
        )
        login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")

        # HTMX requests can't follow a normal redirect body — use HX-Redirect.
        if request.headers.get("HX-Request"):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = login_url
            return response

        return redirect(login_url)
