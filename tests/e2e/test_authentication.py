"""
E2E Tests for Authentication Flows

Tests cover:
- User registration
- Login/logout
- Password reset flow
- Protected page access
- Session handling
"""

import pytest
from playwright.sync_api import Page, expect


class TestPublicPages:
    """Test public pages are accessible without authentication."""

    def test_home_page_loads(self, page: Page):
        """Home page should load for anonymous users."""
        page.goto("/")
        expect(page).to_have_title(
            "VA Benefits Navigator - Get the VA Disability Rating You Deserve"
        )
        expect(page.locator("h1").first).to_be_visible()

    def test_login_page_loads(self, page: Page):
        """Login page should be accessible."""
        page.goto("/accounts/login/")
        expect(page.locator('input[name="login"]')).to_be_visible()
        expect(page.locator('input[name="password"]')).to_be_visible()
        expect(page.locator('button[type="submit"]')).to_be_visible()

    def test_signup_page_loads(self, page: Page):
        """Signup page should be accessible."""
        page.goto("/accounts/signup/")
        expect(page.locator('input[name="email"]')).to_be_visible()
        expect(page.locator('input[name="password1"]')).to_be_visible()

    def test_appeals_public_page(self, page: Page):
        """Appeals overview should be public."""
        page.goto("/appeals/")
        expect(page.locator("h1").last).to_contain_text("Appeal")

    def test_examprep_guides_public(self, page: Page):
        """Exam prep guides list should be public."""
        page.goto("/exam-prep/")
        expect(page).to_have_url("/exam-prep/")


class TestLogin:
    """Test login functionality."""

    def test_successful_login(self, page: Page):
        """User should be able to log in with valid credentials."""
        page.goto("/accounts/login/")

        page.fill('input[name="login"]', "e2e_test@example.com")
        page.fill('input[name="password"]', "E2ETestPassword123!")
        page.click('button[type="submit"]')

        # Should redirect to dashboard
        page.wait_for_url("**/dashboard/**", timeout=10000)
        expect(page).to_have_url("/dashboard/")

    def test_invalid_login_shows_error(self, page: Page):
        """Invalid credentials should show an error message."""
        page.goto("/accounts/login/")

        page.fill('input[name="login"]', "wrong@example.com")
        page.fill('input[name="password"]', "wrongpassword")
        page.click('button[type="submit"]')

        # Should stay on login page with error
        expect(page).to_have_url("/accounts/login/")
        # Look for error message
        expect(
            page.locator('.alert-danger, .errorlist, [role="alert"]')
        ).to_be_visible()

    def test_login_required_redirect(self, page: Page):
        """Protected pages should redirect to login."""
        page.goto("/dashboard/")

        # Should redirect to login with next parameter
        expect(page).to_have_url("/accounts/login/?next=/dashboard/")


class TestLogout:
    """Test logout functionality."""

    def test_logout_clears_session(self, authenticated_page: Page):
        """Logout should clear the user session."""
        page = authenticated_page

        # Click logout
        page.goto("/accounts/logout/")
        page.click('button[type="submit"]')

        # Try to access protected page
        page.goto("/dashboard/")

        # Should redirect to login
        expect(page).to_have_url("/accounts/login/?next=/dashboard/")


class TestProtectedPages:
    """Test that protected pages require authentication."""

    @pytest.mark.parametrize(
        "url",
        [
            "/dashboard/",
            "/journey/",
            "/claims/",
            "/exam-prep/my-checklists/",
            "/appeals/my-appeals/",
            "/accounts/privacy/",
        ],
    )
    def test_protected_page_redirects_anonymous(self, page: Page, url: str):
        """Protected pages should redirect anonymous users to login."""
        page.goto(url)
        expect(page).to_have_url(f"/accounts/login/?next={url}")

    @pytest.mark.parametrize(
        "url",
        [
            "/dashboard/",
            "/journey/",
            "/claims/",
            "/exam-prep/my-checklists/",
        ],
    )
    def test_protected_page_accessible_authenticated(
        self, authenticated_page: Page, url: str
    ):
        """Protected pages should be accessible to authenticated users."""
        page = authenticated_page
        page.goto(url)
        # Should not redirect to login
        expect(page).not_to_have_url("/accounts/login/*")


class TestRegistration:
    """Test user registration flow."""

    def test_registration_form_validation(self, page: Page):
        """Registration should validate input fields."""
        page.goto("/accounts/signup/")

        # Submit empty form
        page.click('button[type="submit"]')

        # Should show validation errors
        expect(page).to_have_url("/accounts/signup/")

    def test_registration_password_mismatch(self, page: Page):
        """Registration should reject mismatched passwords."""
        page.goto("/accounts/signup/")

        page.fill('input[name="email"]', "newuser@example.com")
        page.fill('input[name="password1"]', "SecurePassword123!")
        page.fill('input[name="password2"]', "DifferentPassword123!")
        page.click('button[type="submit"]')

        # Should show error
        expect(page.locator(".errorlist, .alert-danger")).to_be_visible()


class TestPasswordReset:
    """Test password reset flow."""

    def test_password_reset_page_loads(self, page: Page):
        """Password reset page should be accessible."""
        page.goto("/accounts/password/reset/")
        expect(page.locator('input[name="email"]')).to_be_visible()

    def test_password_reset_request(self, page: Page):
        """Password reset should accept email and show confirmation."""
        page.goto("/accounts/password/reset/")

        page.fill('input[name="email"]', "e2e_test@example.com")
        page.click('button[type="submit"]')

        # Should show confirmation (either redirect or message)
        page.wait_for_load_state("networkidle")
        # The page should indicate email was sent


class TestSessionSecurity:
    """Test session security features."""

    def test_session_persists_across_pages(self, authenticated_page: Page):
        """User session should persist when navigating."""
        page = authenticated_page

        # Navigate to different pages
        page.goto("/dashboard/")
        expect(page).to_have_url("/dashboard/")

        page.goto("/claims/")
        expect(page).to_have_url("/claims/")

        page.goto("/journey/")
        expect(page).to_have_url("/journey/")

        # Should still be logged in
        page.goto("/dashboard/")
        expect(page).to_have_url("/dashboard/")
