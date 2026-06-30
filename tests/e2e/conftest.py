"""
Playwright E2E Test Configuration

This module provides fixtures and utilities for end-to-end testing
with Playwright against a running Django development server.
"""

import os
import pytest
import time
import socket
from contextlib import closing
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext

# =============================================================================
# CONFIGURATION
# =============================================================================

BASE_URL = os.environ.get("E2E_BASE_URL", "http://localhost:8000")
HEADLESS = os.environ.get("E2E_HEADLESS", "true").lower() == "true"
SLOW_MO = int(os.environ.get("E2E_SLOW_MO", "0"))  # Milliseconds between actions

# Test user credentials
TEST_USER_EMAIL = "e2e_test@example.com"
TEST_USER_PASSWORD = "E2ETestPassword123!"
TEST_PREMIUM_EMAIL = "e2e_premium@example.com"
TEST_PREMIUM_PASSWORD = "E2EPremiumPassword123!"


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        return sock.connect_ex(("localhost", port)) == 0


def wait_for_server(url: str, timeout: int = 30) -> bool:
    """Wait for the server to be ready."""
    import urllib.request
    import urllib.error

    start = time.time()
    while time.time() - start < timeout:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except (urllib.error.URLError, ConnectionRefusedError):
            time.sleep(0.5)
    return False


# =============================================================================
# FIXTURES - BROWSER
# =============================================================================


@pytest.fixture(scope="session")
def playwright_instance():
    """Create a Playwright instance for the session."""
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="session")
def browser(playwright_instance) -> Browser:
    """Create a browser instance."""
    browser = playwright_instance.chromium.launch(
        headless=HEADLESS,
        slow_mo=SLOW_MO,
    )
    yield browser
    browser.close()


@pytest.fixture
def context(browser) -> BrowserContext:
    """Create a new browser context for each test."""
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        base_url=BASE_URL,
    )
    yield context
    context.close()


@pytest.fixture
def page(context) -> Page:
    """Create a new page for each test."""
    page = context.new_page()
    yield page
    page.close()


# =============================================================================
# FIXTURES - AUTHENTICATION
# =============================================================================


def _login_with_retry(context, email, password, max_attempts=3):
    """Login with retry logic for flaky single-threaded dev server."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeout

    last_error = None
    for attempt in range(max_attempts):
        page = context.new_page()
        try:
            page.goto("/accounts/login/", timeout=30000)
            page.fill('input[name="login"]', email)
            page.fill('input[name="password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_url("**/dashboard/**", timeout=30000)
            return page
        except PlaywrightTimeout as exc:
            last_error = exc
            page.close()
    raise last_error


@pytest.fixture
def authenticated_page(context) -> Page:
    """Create a page with an authenticated user session."""
    page = _login_with_retry(context, TEST_USER_EMAIL, TEST_USER_PASSWORD)
    yield page
    page.close()


@pytest.fixture
def premium_page(context) -> Page:
    """Create a page with a premium user session."""
    page = _login_with_retry(context, TEST_PREMIUM_EMAIL, TEST_PREMIUM_PASSWORD)
    yield page
    page.close()


# =============================================================================
# FIXTURES - TEST DATA SETUP
# =============================================================================


@pytest.fixture(scope="session", autouse=True)
def setup_e2e_test_users(django_db_blocker):
    """Ensure test users exist in the database before running E2E tests."""
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "benefits_navigator.settings")
    django.setup()

    from django.contrib.auth import get_user_model
    from accounts.models import Subscription
    from datetime import datetime, timedelta

    User = get_user_model()

    with django_db_blocker.unblock():
        # Create standard test user
        if not User.objects.filter(email=TEST_USER_EMAIL).exists():
            User.objects.create_user(
                email=TEST_USER_EMAIL,
                password=TEST_USER_PASSWORD,
                first_name="E2E",
                last_name="Tester",
            )

        # Create premium test user
        if not User.objects.filter(email=TEST_PREMIUM_EMAIL).exists():
            premium_user = User.objects.create_user(
                email=TEST_PREMIUM_EMAIL,
                password=TEST_PREMIUM_PASSWORD,
                first_name="Premium",
                last_name="Tester",
            )
            Subscription.objects.create(
                user=premium_user,
                plan_type="premium",
                status="active",
                current_period_end=datetime.now() + timedelta(days=365),
            )

    yield

    # Cleanup after all tests (optional)
    # with django_db_blocker.unblock():
    #     User.objects.filter(email__in=[TEST_USER_EMAIL, TEST_PREMIUM_EMAIL]).delete()


# =============================================================================
# HELPER FIXTURES
# =============================================================================


@pytest.fixture
def screenshot_on_failure(page, request):
    """Take a screenshot when a test fails."""
    yield
    if request.node.rep_call.failed:
        screenshot_dir = "tests/e2e/screenshots"
        os.makedirs(screenshot_dir, exist_ok=True)
        page.screenshot(path=f"{screenshot_dir}/{request.node.name}.png")


# =============================================================================
# PAGE OBJECT HELPERS
# =============================================================================


class BasePage:
    """Base class for page objects."""

    def __init__(self, page: Page):
        self.page = page

    def goto(self, path: str):
        self.page.goto(path)

    def click(self, selector: str):
        self.page.click(selector)

    def fill(self, selector: str, value: str):
        self.page.fill(selector, value)

    def get_text(self, selector: str) -> str:
        return self.page.text_content(selector)

    def is_visible(self, selector: str) -> bool:
        return self.page.is_visible(selector)

    def wait_for_selector(self, selector: str, timeout: int = 5000):
        self.page.wait_for_selector(selector, timeout=timeout)


class LoginPage(BasePage):
    """Login page object."""

    def login(self, email: str, password: str):
        self.goto("/accounts/login/")
        self.fill('input[name="login"]', email)
        self.fill('input[name="password"]', password)
        self.click('button[type="submit"]')


class DashboardPage(BasePage):
    """Dashboard page object."""

    def goto(self, path: str = "/dashboard/"):
        super().goto(path)

    def get_welcome_message(self) -> str:
        return self.get_text("h1")

    def click_upload_document(self):
        self.click('a[href*="upload"]')


class RatingCalculatorPage(BasePage):
    """Rating calculator page object."""

    def goto(self, path: str = "/examprep/rating-calculator/"):
        super().goto(path)

    def add_rating(self, percentage: int, description: str):
        self.fill('input[name="percentage"]', str(percentage))
        self.fill('input[name="description"]', description)
        self.click('button[type="submit"]')

    def get_combined_rating(self) -> str:
        return self.get_text('[data-testid="combined-rating"]')


@pytest.fixture
def login_page(page) -> LoginPage:
    return LoginPage(page)


@pytest.fixture
def dashboard_page(page) -> DashboardPage:
    return DashboardPage(page)


@pytest.fixture
def rating_calculator_page(page) -> RatingCalculatorPage:
    return RatingCalculatorPage(page)
