"""
Regression Tripwires — Fast, deterministic tests for critical invariants.

These tests run under pytest without Playwright, BDD, or external services.
They ensure architectural decisions (OCR field removal, route integrity) are not reverted.

Run with: pytest tests/test_regression_tripwires.py -v
"""

import pytest
from django.urls import reverse, resolve, NoReverseMatch
from django.urls.exceptions import Resolver404

# =============================================================================
# Route Configuration Constants
# =============================================================================
#
# MAINTENANCE: Update these lists when adding/removing routes.
# - Add new public routes to CORE_PUBLIC_PATHS or MONETIZABLE_PUBLIC_PATHS
# - Add new protected routes to PROTECTED_PATHS
# - Add new named URLs to NAMED_URLS
# - Add new critical paths to CRITICAL_PATHS
#
# These lists are tested for non-emptiness to prevent accidental deletion.

# Named URL patterns that must resolve (no DB required)
NAMED_URLS = [
    # Core routes
    ("home", {}),
    ("health_check", {}),
    # Claims routes
    ("claims:document_list", {}),
    ("claims:document_upload", {}),
    ("claims:denial_decoder", {}),
    # Agent routes
    ("agents:home", {}),
    ("agents:decision_analyzer", {}),
    ("agents:evidence_gap", {}),
    ("agents:statement_generator", {}),
    ("agents:assistant", {}),
    ("agents:assistant_stream", {}),
    ("agents:assistant_stop", {}),
    # Exam prep routes
    ("examprep:guide_list", {}),
    ("examprep:rating_calculator", {}),
    ("examprep:smc_calculator", {}),
    ("examprep:tdiu_calculator", {}),
    ("examprep:glossary_list", {}),
    ("examprep:secondary_conditions_hub", {}),
    # Appeals routes
    ("appeals:home", {}),
    ("appeals:decision_tree", {}),
    # VSO routes
    ("vso:dashboard", {}),
    # Auth routes
    ("account_login", {}),
    ("account_signup", {}),
]

# Critical paths that must resolve to views (no DB required)
CRITICAL_PATHS = [
    "/",
    "/health/",
    "/claims/",
    "/claims/upload/",
    "/claims/decode/",
    "/agents/",
    "/agents/decision-analyzer/",
    "/agents/evidence-gap/",
    "/agents/statement-generator/",
    "/exam-prep/",
    "/exam-prep/rating-calculator/",
    "/appeals/",
    "/vso/",
    "/accounts/login/",
    "/accounts/signup/",
]

# Core public routes that MUST return 200 (never gated)
CORE_PUBLIC_PATHS = [
    "/",
    "/health/",
    "/accounts/login/",
    "/accounts/signup/",
]

# Public routes that may be monetized later (assert not 404, not necessarily 200)
# These use "not 404" assertions to allow future auth/paywall redirects
MONETIZABLE_PUBLIC_PATHS = [
    "/exam-prep/",
    "/exam-prep/rating-calculator/",
    "/exam-prep/smc-calculator/",
    "/exam-prep/tdiu-calculator/",
    "/exam-prep/secondary-conditions/",
    "/exam-prep/glossary/",
    "/appeals/",
    "/appeals/find-your-path/",
]

# Protected routes that must redirect anonymous users to login with next= param
PROTECTED_PATHS = [
    "/dashboard/",
    "/journey/",
    "/claims/",
    "/claims/upload/",
    "/claims/decode/",
    "/agents/decision-analyzer/",
    "/agents/evidence-gap/",
    "/agents/statement-generator/",
    "/exam-prep/my-checklists/",
    "/appeals/my-appeals/",
    "/vso/",
]


# =============================================================================
# Sanity Tests: Ensure route lists are not accidentally emptied
# =============================================================================


class TestRouteListIntegrity:
    """Verify route configuration lists are not empty (prevents accidental deletion)."""

    def test_named_urls_not_empty(self):
        """NAMED_URLS must contain at least one entry."""
        assert (
            len(NAMED_URLS) > 0
        ), "NAMED_URLS is empty - this would skip all URL resolution tests"

    def test_critical_paths_not_empty(self):
        """CRITICAL_PATHS must contain at least one entry."""
        assert (
            len(CRITICAL_PATHS) > 0
        ), "CRITICAL_PATHS is empty - this would skip all path resolution tests"

    def test_core_public_paths_not_empty(self):
        """CORE_PUBLIC_PATHS must contain at least one entry."""
        assert (
            len(CORE_PUBLIC_PATHS) > 0
        ), "CORE_PUBLIC_PATHS is empty - this would skip core public route tests"

    def test_protected_paths_not_empty(self):
        """PROTECTED_PATHS must contain at least one entry."""
        assert (
            len(PROTECTED_PATHS) > 0
        ), "PROTECTED_PATHS is empty - this would skip protected route tests"


# =============================================================================
# Goal A: Ensure removed OCR/PHI fields cannot reappear in database
# =============================================================================


class TestPHIFieldRemovalInvariants:
    """
    Validates that PHI-containing fields remain removed from database models.

    The Ephemeral OCR Refactor removed these fields to protect PHI:
    - Document.ocr_text (claims app)
    - DecisionLetterAnalysis.raw_text (agents app)
    - RatingAnalysis.raw_text (agents app)

    These tests use Django model _meta to check DATABASE field definitions only.
    We check for fields with a 'column' attribute (actual DB columns), not
    arbitrary Python attributes which could be properties or cached values.

    NOTE: No @pytest.mark.django_db - these tests inspect model metadata only.
    """

    def _get_db_field_names(self, model_class):
        """Extract database column field names from Django model _meta."""
        return {f.name for f in model_class._meta.get_fields() if hasattr(f, "column")}

    # -------------------------------------------------------------------------
    # Document.ocr_text removal
    # -------------------------------------------------------------------------

    def test_document_model_has_no_ocr_text_db_field(self):
        """Document must not have ocr_text as a database field."""
        from claims.models import Document

        db_fields = self._get_db_field_names(Document)

        assert "ocr_text" not in db_fields, (
            "REGRESSION: Document.ocr_text database field has reappeared. "
            "This field was removed in the Ephemeral OCR Refactor to protect PHI. "
            "Raw OCR text must not be persisted to the database."
        )

    def test_document_has_required_ocr_metadata_fields(self):
        """Document must have ocr_length and ocr_status for observability."""
        from claims.models import Document

        db_fields = self._get_db_field_names(Document)

        assert "ocr_length" in db_fields, (
            "Document.ocr_length field is missing. "
            "This metadata field replaced ocr_text for observability without PHI."
        )
        assert "ocr_status" in db_fields, (
            "Document.ocr_status field is missing. "
            "This metadata field replaced ocr_text for observability without PHI."
        )

    # -------------------------------------------------------------------------
    # DecisionLetterAnalysis.raw_text removal
    # -------------------------------------------------------------------------

    def test_decision_letter_analysis_has_no_raw_text_db_field(self):
        """DecisionLetterAnalysis must not have raw_text as a database field."""
        from agents.models import DecisionLetterAnalysis

        db_fields = self._get_db_field_names(DecisionLetterAnalysis)

        assert "raw_text" not in db_fields, (
            "REGRESSION: DecisionLetterAnalysis.raw_text database field has reappeared. "
            "This field was removed in the Ephemeral OCR Refactor to protect PHI."
        )

    # -------------------------------------------------------------------------
    # RatingAnalysis.raw_text removal
    # -------------------------------------------------------------------------

    def test_rating_analysis_has_no_raw_text_db_field(self):
        """RatingAnalysis must not have raw_text as a database field."""
        from agents.models import RatingAnalysis

        db_fields = self._get_db_field_names(RatingAnalysis)

        assert "raw_text" not in db_fields, (
            "REGRESSION: RatingAnalysis.raw_text database field has reappeared. "
            "This field was removed in the Ephemeral OCR Refactor to protect PHI."
        )


# =============================================================================
# Goal B: URL Resolution Integrity (no DB required)
# =============================================================================


class TestURLResolutionIntegrity:
    """
    Validates that named URLs resolve and paths map to views.

    These tests use Django's URL resolver only - no HTTP requests, no DB access.
    They prevent silent route loss from URL configuration changes.

    NOTE: No @pytest.mark.django_db - these tests use URL resolver only.
    """

    # -------------------------------------------------------------------------
    # Named URL patterns must resolve
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("url_name,kwargs", NAMED_URLS)
    def test_named_url_resolves(self, url_name, kwargs):
        """Named URLs must resolve without NoReverseMatch error."""
        try:
            url = reverse(url_name, kwargs=kwargs)
            assert url is not None and url != ""
        except NoReverseMatch as e:
            pytest.fail(
                f"Named URL '{url_name}' failed to resolve: {e}. "
                f"This URL pattern may have been removed or renamed."
            )

    # -------------------------------------------------------------------------
    # Critical paths must resolve to views
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("path", CRITICAL_PATHS)
    def test_path_resolves_to_view(self, path):
        """URL paths must resolve to a view function (not raise Resolver404)."""
        try:
            match = resolve(path)
            assert (
                match.func is not None
            ), f"Path '{path}' resolved but has no view function."
        except Resolver404:
            pytest.fail(
                f"Path '{path}' raised Resolver404. "
                f"This route does not exist in URL configuration."
            )


# =============================================================================
# Goal C: Route HTTP Behavior (requires DB for auth checks)
# =============================================================================


@pytest.mark.django_db
class TestRouteHTTPBehavior:
    """
    Validates HTTP response behavior for critical routes.

    Rules:
    - Core public routes (/, /health/) must return 200
    - Auth-required routes must return 302 redirect to login with next= parameter
    - Monetizable public routes should "not 404" (may be gated later)

    NOTE: @pytest.mark.django_db required - auth middleware needs database.
    """

    @pytest.fixture
    def client(self):
        """Django test client for anonymous requests."""
        from django.test import Client

        return Client()

    # -------------------------------------------------------------------------
    # Core public routes (must remain 200)
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("path", CORE_PUBLIC_PATHS)
    def test_core_public_route_returns_200(self, client, path):
        """Core public routes must return 200 for anonymous users."""
        response = client.get(path)

        assert response.status_code == 200, (
            f"Route '{path}' returned {response.status_code}, expected 200. "
            f"This core route must remain publicly accessible."
        )

    # -------------------------------------------------------------------------
    # Public routes (should not 404, but may be gated in future)
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("path", MONETIZABLE_PUBLIC_PATHS)
    def test_public_route_exists(self, client, path):
        """
        Monetizable public routes must exist (not 404).

        NOTE: Uses "!= 404" instead of "== 200" intentionally.
        These routes may return 200 now but could be gated behind auth/paywall later.
        If intentionally removed, update MONETIZABLE_PUBLIC_PATHS.
        """
        response = client.get(path)

        assert response.status_code != 404, (
            f"Route '{path}' returned 404. "
            f"This route should exist. If intentionally removed, update MONETIZABLE_PUBLIC_PATHS."
        )

    # -------------------------------------------------------------------------
    # Auth-required routes (must redirect to login with next=)
    # -------------------------------------------------------------------------

    @pytest.mark.parametrize("path", PROTECTED_PATHS)
    def test_protected_route_redirects_to_login(self, client, path):
        """
        Protected routes must redirect anonymous users to login.

        Assertions:
        1. Response is 302 redirect (not 404 or 200)
        2. Redirect URL contains /login/ or /accounts/login/
        3. Redirect URL includes next= parameter pointing back to original path
        """
        response = client.get(path)

        # (1) Must be a redirect
        assert response.status_code in (301, 302), (
            f"Route '{path}' returned {response.status_code}, expected 302 redirect. "
            f"Protected routes must redirect anonymous users to login."
        )

        # Get redirect location
        redirect_url = response.get("Location", "")

        # (2) Must redirect to login page
        assert (
            "/accounts/login/" in redirect_url or "/login/" in redirect_url
        ), f"Route '{path}' redirected to '{redirect_url}', expected login page."

        # (3) Must include next= parameter to preserve original destination
        assert "next=" in redirect_url, (
            f"Route '{path}' redirect missing next= parameter. "
            f"Got: '{redirect_url}'. Login redirect should preserve original destination."
        )
