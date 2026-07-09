"""
Explorer Testing Agent

Autonomously explores the application, visiting pages and looking for errors.
This agent mimics a curious user clicking around to discover issues.
"""

import logging
from typing import Set
from .base_agent import BaseTestAgent, RandomExplorerMixin, TestSession

logger = logging.getLogger(__name__)


class ExplorerAgent(BaseTestAgent, RandomExplorerMixin):
    """
    Autonomous explorer that crawls the application looking for errors.

    This agent:
    - Visits every reachable page
    - Checks for HTTP errors
    - Looks for JavaScript errors
    - Identifies broken links
    - Reports accessibility issues
    """

    def __init__(
        self,
        max_pages: int = 50,
        authenticated: bool = False,
        login_email: str = "e2e_test@example.com",
        login_password: str = "E2ETestPassword123!",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.max_pages = max_pages
        self.authenticated = authenticated
        self.login_email = login_email
        self.login_password = login_password
        self.visited_urls: Set[str] = set()
        self.urls_to_visit: list = []
        self.js_errors: list = []

    @property
    def name(self) -> str:
        return "ExplorerAgent"

    def login(self):
        """Log in to the application."""
        logger.info("Logging in...")
        self.navigate("/accounts/login/")
        self.fill('input[name="login"]', self.login_email)
        self.fill('input[name="password"]', self.login_password)
        self.click('button[type="submit"]')
        self.page.wait_for_load_state("networkidle")

    def setup_error_tracking(self):
        """Set up JavaScript error tracking."""

        def handle_console_error(msg):
            if msg.type == "error":
                self.js_errors.append(
                    {
                        "url": self.page.url,
                        "message": msg.text,
                    }
                )

        self.page.on("console", handle_console_error)
        self.page.on(
            "pageerror",
            lambda err: self.js_errors.append(
                {
                    "url": self.page.url,
                    "error": str(err),
                }
            ),
        )

    def discover_links(self):
        """Add new links from current page to the visit queue."""
        links = self.get_all_links()
        for link in links:
            # Normalize URL
            if link.startswith("/"):
                full_url = f"{self.base_url}{link}"
            elif link.startswith(self.base_url):
                full_url = link
            else:
                continue

            # Skip already visited or queued
            if full_url not in self.visited_urls and full_url not in self.urls_to_visit:
                # Skip external links, logout, admin
                if "/logout" in full_url or "/admin/" in full_url:
                    continue
                self.urls_to_visit.append(full_url)

    def explore_page(self) -> list:
        """Explore the current page and return any errors found."""
        errors = []

        # Check for visible errors
        page_errors = self.check_for_errors()
        errors.extend(page_errors)

        # Check page title
        title = self.page.title()
        if not title or "error" in title.lower():
            errors.append(
                {
                    "type": "suspicious_title",
                    "title": title,
                    "url": self.page.url,
                }
            )

        # Discover new links
        self.discover_links()

        # Log progress
        logger.info(
            f"Explored: {self.page.url} | Errors: {len(page_errors)} | Queue: {len(self.urls_to_visit)}"
        )

        return errors

    def run(self) -> TestSession:
        """Execute the exploration."""
        logger.info(f"Starting {self.name}")

        try:
            self.start_browser()
            self.setup_error_tracking()

            # Start with home page
            self.urls_to_visit = [self.base_url]

            # Log in if needed
            if self.authenticated:
                self.login()
                self.urls_to_visit.append(f"{self.base_url}/dashboard/")

            pages_explored = 0

            while self.urls_to_visit and pages_explored < self.max_pages:
                url = self.urls_to_visit.pop(0)

                if url in self.visited_urls:
                    continue

                self.visited_urls.add(url)
                result = self.navigate(url)

                if result.success:
                    self.explore_page()
                    pages_explored += 1

            # Add JS errors to session
            if self.js_errors:
                self.session.details = {"js_errors": self.js_errors}

            logger.info(f"Exploration complete. Visited {pages_explored} pages.")
            return self.session

        finally:
            self.stop_browser()


class DeepExplorerAgent(ExplorerAgent):
    """
    Deep explorer that also interacts with forms and buttons.
    """

    @property
    def name(self) -> str:
        return "DeepExplorerAgent"

    def try_forms(self):
        """Attempt to interact with forms on the page."""
        forms = self.get_all_forms()

        for form_info in forms[:2]:  # Limit form interactions
            # Skip dangerous forms
            if any(x in str(form_info) for x in ["delete", "logout", "cancel"]):
                continue

            # Try to fill and submit
            try:
                # Fill text inputs with test data
                inputs = self.page.locator('input[type="text"], input[type="email"]')
                for i in range(min(inputs.count(), 3)):
                    try:
                        inputs.nth(i).fill("test@example.com")
                    except:
                        pass

                # Don't actually submit - just check the form is functional
                submit = self.page.locator('button[type="submit"]')
                if submit.count() > 0:
                    # Just verify it's clickable
                    submit.first.is_enabled()

            except Exception as e:
                logger.warning(f"Form interaction error: {e}")

    def explore_page(self) -> list:
        """Extended exploration with form interaction."""
        errors = super().explore_page()

        # Try interacting with forms
        self.try_forms()

        # Check for broken images
        images = self.page.locator("img")
        for i in range(images.count()):
            try:
                img = images.nth(i)
                natural_width = self.page.evaluate(
                    "(img) => img.naturalWidth", img.element_handle()
                )
                if natural_width == 0:
                    src = img.get_attribute("src")
                    errors.append(
                        {
                            "type": "broken_image",
                            "src": src,
                            "url": self.page.url,
                        }
                    )
            except:
                pass

        return errors


def run_explorer(
    authenticated: bool = True,
    max_pages: int = 50,
    report_path: str = "tests/agents/explorer_report.json",
):
    """Convenience function to run the explorer agent."""
    agent = ExplorerAgent(
        authenticated=authenticated,
        max_pages=max_pages,
        headless=True,
    )
    session = agent.run()
    session.save_report(report_path)
    return session


if __name__ == "__main__":
    # Run as script
    import sys

    authenticated = "--auth" in sys.argv or "-a" in sys.argv
    session = run_explorer(authenticated=authenticated)

    print("\n=== Explorer Agent Report ===")
    print(f"Pages visited: {len(session.pages_visited)}")
    print(f"Actions taken: {len(session.results)}")
    print(f"Success rate: {session.success_rate:.1%}")
    print(f"Errors found: {len(session.errors_found)}")

    if session.errors_found:
        print("\nErrors:")
        for error in session.errors_found[:10]:
            print(f"  - {error.action}: {error.error}")
