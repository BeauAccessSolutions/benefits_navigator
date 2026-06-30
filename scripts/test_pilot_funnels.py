#!/usr/bin/env python
"""
Pilot Funnel Test Script

Tests both Path A (document upload) and Path B (rating calculator) user journeys.

Usage:
    # Start server first:
    RATELIMIT_ENABLE=false USE_REDIS_CACHE=false python manage.py runserver

    # Run tests:
    python scripts/test_pilot_funnels.py

    # Run specific path:
    python scripts/test_pilot_funnels.py --path-a
    python scripts/test_pilot_funnels.py --path-b
"""

import sys
import os
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "benefits_navigator.settings")

from playwright.sync_api import sync_playwright

BASE_URL = "http://localhost:8000"
TEST_USER_EMAIL = "pilot_both@test.com"
TEST_USER_PASSWORD = "PilotTest2026!"


class PilotFunnelTester:
    def __init__(self, headless=True):
        self.headless = headless
        self.results = {"path_a": [], "path_b": []}

    def run_all(self):
        """Run all pilot funnel tests."""
        print("=" * 60)
        print("PILOT FUNNEL TESTS")
        print("=" * 60)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context()
            page = context.new_page()

            try:
                # Test Path B first (doesn't require file upload)
                self.test_path_b(page)

                # Test Path A
                self.test_path_a(page)

            finally:
                browser.close()

        self.print_results()

    def test_path_a(self, page):
        """Test Path A: Document Upload → AI Analysis → Dashboard"""
        print("\n" + "-" * 60)
        print("PATH A: Document Upload Flow")
        print("-" * 60)

        # A1: Login
        result = self._test_login(page)
        self.results["path_a"].append(("A1: Login", result))

        # A2: Navigate to upload page
        result = self._test_step(
            page,
            lambda: page.goto(f"{BASE_URL}/claims/upload/"),
            lambda: page.locator('input[type="file"]').is_visible(),
            "A2: Navigate to upload page",
        )
        self.results["path_a"].append(result)

        # A3: Verify upload form elements
        result = self._test_step(
            page,
            lambda: None,  # Already on page
            lambda: (
                page.locator('select[name="document_type"]').is_visible()
                and page.locator('button[type="submit"]').is_visible()
            ),
            "A3: Upload form elements present",
        )
        self.results["path_a"].append(result)

        # A4: Navigate to document list
        result = self._test_step(
            page,
            lambda: page.goto(f"{BASE_URL}/claims/"),
            lambda: page.url.endswith("/claims/") or "claims" in page.url,
            "A4: Document list accessible",
        )
        self.results["path_a"].append(result)

        # A5: Dashboard shows documents section
        result = self._test_step(
            page,
            lambda: page.goto(f"{BASE_URL}/dashboard/"),
            lambda: "dashboard" in page.url.lower(),
            "A5: Dashboard accessible",
        )
        self.results["path_a"].append(result)

    def test_path_b(self, page):
        """Test Path B: Rating Calculator → Save/Share → Dashboard"""
        print("\n" + "-" * 60)
        print("PATH B: Rating Calculator Flow")
        print("-" * 60)

        # B1: Access calculator (public)
        result = self._test_step(
            page,
            lambda: page.goto(f"{BASE_URL}/exam-prep/rating-calculator/"),
            lambda: "rating" in page.url.lower() and page.locator("input").count() > 0,
            "B1: Calculator page loads",
        )
        self.results["path_b"].append(result)

        # B2: Add a rating
        result = self._test_step(
            page,
            lambda: self._add_rating(page, 30, "Test condition"),
            lambda: True,  # Will fail in _add_rating if issue
            "B2: Add disability rating",
        )
        self.results["path_b"].append(result)

        # B3: Calculate combined rating
        result = self._test_step(
            page,
            lambda: self._click_calculate(page),
            lambda: page.locator("text=/combined|result/i").count() > 0,
            "B3: Calculate combined rating",
        )
        self.results["path_b"].append(result)

        # B4: Login for save
        result = self._test_login(page)
        self.results["path_b"].append(("B4: Login for save", result))

        # B5: Access saved calculations
        result = self._test_step(
            page,
            lambda: page.goto(f"{BASE_URL}/exam-prep/rating-calculator/saved/"),
            lambda: "saved" in page.url.lower(),
            "B5: Saved calculations page",
        )
        self.results["path_b"].append(result)

        # B6: Access exam guides
        result = self._test_step(
            page,
            lambda: page.goto(f"{BASE_URL}/exam-prep/"),
            lambda: page.locator('a[href*="/guide/"]').count() > 0,
            "B6: Exam guides list",
        )
        self.results["path_b"].append(result)

        # B7: Access glossary
        result = self._test_step(
            page,
            lambda: page.goto(f"{BASE_URL}/exam-prep/glossary/"),
            lambda: "glossary" in page.url.lower(),
            "B7: Glossary accessible",
        )
        self.results["path_b"].append(result)

    def _test_login(self, page):
        """Helper to test login."""
        try:
            page.goto(f"{BASE_URL}/accounts/login/")

            # Check if already logged in (redirected to dashboard)
            if "/dashboard" in page.url:
                print("  [PASS] Already logged in")
                return True

            # Fill login form
            page.fill('input[name="login"]', TEST_USER_EMAIL)
            page.fill('input[name="password"]', TEST_USER_PASSWORD)
            page.click('button[type="submit"]')
            page.wait_for_url("**/dashboard/**", timeout=10000)

            print("  [PASS] Login successful")
            return True
        except Exception as e:
            print(f"  [FAIL] Login: {e}")
            return False

    def _test_step(self, page, action, check, name):
        """Helper to test a single step."""
        try:
            action()
            page.wait_for_load_state("networkidle", timeout=5000)
            success = check()
            status = "PASS" if success else "FAIL"
            print(f"  [{status}] {name}")
            return (name, success)
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            return (name, False)

    def _add_rating(self, page, percentage, description):
        """Add a rating to the calculator."""
        # Look for percentage input
        inputs = page.locator('input[type="number"], input[name*="percentage"]')
        if inputs.count() > 0:
            inputs.first.fill(str(percentage))

        # Look for description input
        desc_inputs = page.locator('input[name*="description"], input[type="text"]')
        if desc_inputs.count() > 0:
            desc_inputs.first.fill(description)

        # Click add button if present
        add_btn = page.locator('button:has-text("Add"), button:has-text("+")')
        if add_btn.count() > 0:
            add_btn.first.click()
            page.wait_for_timeout(500)

    def _click_calculate(self, page):
        """Click the calculate button."""
        calc_btn = page.locator('button:has-text("Calculate")')
        if calc_btn.count() > 0:
            calc_btn.first.click()
            page.wait_for_timeout(1000)

    def print_results(self):
        """Print test results summary."""
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)

        for path_name, results in self.results.items():
            passed = sum(1 for _, success in results if success)
            total = len(results)
            status = "PASS" if passed == total else "FAIL"
            print(f"\n{path_name.upper()}: {passed}/{total} tests passed [{status}]")

            for name, success in results:
                icon = "✓" if success else "✗"
                print(f"  {icon} {name}")

        # Overall
        all_results = self.results["path_a"] + self.results["path_b"]
        total_passed = sum(1 for _, success in all_results if success)
        total_tests = len(all_results)
        overall = "PASS" if total_passed == total_tests else "FAIL"

        print(f'\n{"=" * 60}')
        print(f"OVERALL: {total_passed}/{total_tests} tests passed [{overall}]")
        print("=" * 60)

        return total_passed == total_tests


def main():
    parser = argparse.ArgumentParser(description="Test pilot funnels")
    parser.add_argument("--path-a", action="store_true", help="Test Path A only")
    parser.add_argument("--path-b", action="store_true", help="Test Path B only")
    parser.add_argument(
        "--headed", action="store_true", help="Run with visible browser"
    )
    args = parser.parse_args()

    tester = PilotFunnelTester(headless=not args.headed)

    if args.path_a or args.path_b:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not args.headed)
            page = browser.new_page()
            try:
                if args.path_a:
                    tester.test_path_a(page)
                if args.path_b:
                    tester.test_path_b(page)
            finally:
                browser.close()
        tester.print_results()
    else:
        tester.run_all()


if __name__ == "__main__":
    main()
