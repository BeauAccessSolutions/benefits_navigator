"""
Base Testing Agent

Provides foundation for AI-powered testing agents that can autonomously
explore and test the application.
"""

import os
import json
import random
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from playwright.sync_api import Page, Browser, BrowserContext, sync_playwright

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TestResult:
    """Result of a single test action."""

    action: str
    url: str
    success: bool
    error: Optional[str] = None
    screenshot: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "url": self.url,
            "success": self.success,
            "error": self.error,
            "screenshot": self.screenshot,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }


@dataclass
class TestSession:
    """A testing session containing multiple test results."""

    agent_name: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    results: list = field(default_factory=list)
    pages_visited: set = field(default_factory=set)
    errors_found: list = field(default_factory=list)

    def add_result(self, result: TestResult):
        self.results.append(result)
        self.pages_visited.add(result.url)
        if not result.success:
            self.errors_found.append(result)

    def finish(self):
        self.end_time = datetime.now()

    @property
    def success_rate(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.success) / len(self.results)

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "total_actions": len(self.results),
            "success_rate": self.success_rate,
            "pages_visited": list(self.pages_visited),
            "errors_count": len(self.errors_found),
            "results": [r.to_dict() for r in self.results],
        }

    def save_report(self, filepath: str):
        """Save session report to JSON file."""
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)


class BaseTestAgent(ABC):
    """
    Base class for AI-powered testing agents.

    Provides common functionality for browser automation,
    navigation, and result tracking.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        headless: bool = True,
        screenshot_dir: str = "tests/agents/screenshots",
    ):
        self.base_url = base_url
        self.headless = headless
        self.screenshot_dir = screenshot_dir
        self.session: Optional[TestSession] = None
        self.page: Optional[Page] = None
        self.context: Optional[BrowserContext] = None
        self.browser: Optional[Browser] = None

        os.makedirs(screenshot_dir, exist_ok=True)

    @property
    @abstractmethod
    def name(self) -> str:
        """Agent name for identification."""
        pass

    @abstractmethod
    def run(self) -> TestSession:
        """Execute the agent's testing logic."""
        pass

    def start_browser(self):
        """Start the browser instance."""
        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 720},
            base_url=self.base_url,
        )
        self.page = self.context.new_page()
        self.session = TestSession(agent_name=self.name)

    def stop_browser(self):
        """Stop the browser instance."""
        if self.session:
            self.session.finish()
        if self.page:
            self.page.close()
        if self.context:
            self.context.close()
        if self.browser:
            self.browser.close()
        if hasattr(self, "_playwright"):
            self._playwright.stop()

    def take_screenshot(self, name: str) -> str:
        """Take a screenshot and return the path."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{name}_{timestamp}.png"
        filepath = os.path.join(self.screenshot_dir, filename)
        self.page.screenshot(path=filepath)
        return filepath

    def navigate(self, url: str) -> TestResult:
        """Navigate to a URL and record the result."""
        try:
            response = self.page.goto(url)
            success = response.status < 400 if response else False

            result = TestResult(
                action="navigate",
                url=self.page.url,
                success=success,
                details={"status_code": response.status if response else None},
            )

            if not success:
                result.screenshot = self.take_screenshot("nav_error")
                result.error = f'HTTP {response.status if response else "unknown"}'

        except Exception as e:
            result = TestResult(
                action="navigate",
                url=url,
                success=False,
                error=str(e),
                screenshot=self.take_screenshot("nav_exception"),
            )

        if self.session:
            self.session.add_result(result)
        return result

    def click(self, selector: str) -> TestResult:
        """Click an element and record the result."""
        try:
            self.page.click(selector, timeout=5000)
            result = TestResult(
                action=f"click: {selector}",
                url=self.page.url,
                success=True,
            )
        except Exception as e:
            result = TestResult(
                action=f"click: {selector}",
                url=self.page.url,
                success=False,
                error=str(e),
                screenshot=self.take_screenshot("click_error"),
            )

        if self.session:
            self.session.add_result(result)
        return result

    def fill(self, selector: str, value: str) -> TestResult:
        """Fill an input and record the result."""
        try:
            self.page.fill(selector, value, timeout=5000)
            result = TestResult(
                action=f"fill: {selector}",
                url=self.page.url,
                success=True,
            )
        except Exception as e:
            result = TestResult(
                action=f"fill: {selector}",
                url=self.page.url,
                success=False,
                error=str(e),
            )

        if self.session:
            self.session.add_result(result)
        return result

    def check_for_errors(self) -> list:
        """Check current page for common error indicators."""
        errors = []

        # Check for error status
        error_selectors = [
            ".error",
            ".alert-danger",
            ".alert-error",
            '[role="alert"]',
            ".errorlist",
            ".form-error",
            'h1:has-text("Error")',
            'h1:has-text("500")',
            'h1:has-text("404")',
            'h1:has-text("403")',
        ]

        for selector in error_selectors:
            elements = self.page.locator(selector)
            if elements.count() > 0:
                for i in range(elements.count()):
                    text = elements.nth(i).text_content()
                    if text and text.strip():
                        errors.append(
                            {
                                "selector": selector,
                                "text": text.strip()[:200],
                                "url": self.page.url,
                            }
                        )

        return errors

    def get_all_links(self) -> list:
        """Get all internal links on the current page."""
        links = []
        elements = self.page.locator("a[href]")

        for i in range(elements.count()):
            href = elements.nth(i).get_attribute("href")
            if href and not href.startswith(
                ("http://", "https://", "mailto:", "tel:", "#", "javascript:")
            ):
                links.append(href)
            elif href and (href.startswith(self.base_url) or href.startswith("/")):
                links.append(href)

        return list(set(links))

    def get_all_forms(self) -> list:
        """Get all forms on the current page."""
        forms = []
        elements = self.page.locator("form")

        for i in range(elements.count()):
            form = elements.nth(i)
            action = form.get_attribute("action") or ""
            method = form.get_attribute("method") or "get"
            forms.append({"action": action, "method": method})

        return forms

    def get_interactive_elements(self) -> dict:
        """Get all interactive elements on the page."""
        return {
            "links": self.get_all_links(),
            "forms": self.get_all_forms(),
            "buttons": self.page.locator("button").count(),
            "inputs": self.page.locator("input").count(),
            "selects": self.page.locator("select").count(),
        }


class RandomExplorerMixin:
    """Mixin for agents that explore randomly."""

    def random_link(self) -> Optional[str]:
        """Get a random internal link."""
        links = self.get_all_links()
        return random.choice(links) if links else None

    def random_click(self) -> TestResult:
        """Click a random interactive element."""
        clickable = self.page.locator("a, button").all()
        if clickable:
            element = random.choice(clickable)
            try:
                element.click(timeout=3000)
                return TestResult(
                    action="random_click",
                    url=self.page.url,
                    success=True,
                )
            except Exception as e:
                return TestResult(
                    action="random_click",
                    url=self.page.url,
                    success=False,
                    error=str(e),
                )
        return TestResult(
            action="random_click",
            url=self.page.url,
            success=False,
            error="No clickable elements found",
        )
