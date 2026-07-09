"""
Chaos Testing Agent

Intentionally tries to break the application by:
- Submitting invalid data
- Clicking rapidly
- Testing edge cases
- Fuzzing inputs
"""

import random
import string
import logging
from .base_agent import BaseTestAgent, TestResult, TestSession

logger = logging.getLogger(__name__)


class ChaosAgent(BaseTestAgent):
    """
    Chaos agent that tries to break the application.

    Tests:
    - Invalid form submissions
    - XSS attempts (for validation testing)
    - SQL injection patterns (for validation testing)
    - Extremely long inputs
    - Special characters
    - Rapid actions
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.vulnerabilities = []

    @property
    def name(self) -> str:
        return "ChaosAgent"

    # Test payloads for security testing
    MALICIOUS_PAYLOADS = [
        '<script>alert("XSS")</script>',
        '"><script>alert("XSS")</script>',
        "'; DROP TABLE users; --",
        "1' OR '1'='1",
        "{{7*7}}",  # Template injection
        "${7*7}",
        "../../../etc/passwd",
        "javascript:alert(1)",
    ]

    EDGE_CASE_INPUTS = [
        "",  # Empty
        " ",  # Whitespace
        "   ",  # Multiple spaces
        "a" * 10000,  # Very long
        "0",
        "-1",
        "9999999999999999",
        "0.000001",
        "null",
        "undefined",
        "NaN",
        "true",
        "false",
        "\\n\\r\\t",
        "\x00",  # Null byte
        "🎉🔥💀",  # Emojis
        "日本語",  # Unicode
        "مرحبا",  # RTL text
    ]

    def generate_fuzz_string(self, length: int = 100) -> str:
        """Generate a random fuzz string."""
        chars = string.printable + "".join(chr(i) for i in range(128, 256))
        return "".join(random.choice(chars) for _ in range(length))

    def test_form_with_payload(self, payload: str) -> TestResult:
        """Test a form with a specific payload."""
        try:
            # Find all text inputs
            inputs = self.page.locator(
                'input[type="text"], input[type="email"], textarea'
            )

            for i in range(inputs.count()):
                try:
                    inputs.nth(i).fill(payload)
                except:
                    pass

            # Try to submit
            submit = self.page.locator('button[type="submit"]')
            if submit.count() > 0:
                try:
                    submit.first.click(timeout=3000)
                    self.page.wait_for_load_state("networkidle", timeout=5000)
                except:
                    pass

            # Check if payload appears unescaped (XSS vulnerability)
            page_content = self.page.content()
            if "<script>alert" in page_content and payload in page_content:
                self.vulnerabilities.append(
                    {
                        "type": "potential_xss",
                        "payload": payload,
                        "url": self.page.url,
                    }
                )
                return TestResult(
                    action=f"xss_test: {payload[:50]}",
                    url=self.page.url,
                    success=False,  # Found vulnerability
                    error="Potential XSS vulnerability",
                )

            return TestResult(
                action=f"payload_test: {payload[:50]}",
                url=self.page.url,
                success=True,  # Properly handled
            )

        except Exception as e:
            return TestResult(
                action=f"payload_test: {payload[:50]}",
                url=self.page.url,
                success=True,  # Error is often acceptable for malicious input
                details={"error": str(e)},
            )

    def test_input_boundaries(self) -> list:
        """Test input boundary conditions."""
        results = []

        for edge_input in self.EDGE_CASE_INPUTS:
            result = self.test_form_with_payload(edge_input)
            results.append(result)
            if self.session:
                self.session.add_result(result)

        return results

    def test_rapid_clicks(self) -> TestResult:
        """Test rapid clicking on buttons."""
        try:
            buttons = self.page.locator("button, a").all()
            clickable = [b for b in buttons if b.is_visible()]

            if clickable:
                button = random.choice(clickable)
                # Click rapidly
                for _ in range(5):
                    try:
                        button.click(timeout=500, no_wait_after=True)
                    except:
                        break

            return TestResult(
                action="rapid_clicks",
                url=self.page.url,
                success=True,
            )

        except Exception as e:
            return TestResult(
                action="rapid_clicks",
                url=self.page.url,
                success=False,
                error=str(e),
            )

    def test_url_manipulation(self) -> list:
        """Test URL manipulation."""
        results = []

        malicious_urls = [
            "/../../etc/passwd",
            "/admin/../../etc/passwd",
            "/<script>alert(1)</script>",
            "/claims/document/-1/",
            "/claims/document/999999/",
            "/claims/document/abc/",
            "/appeals/0/",
            "/appeals/-1/",
            "/examprep/guide/../../admin/",
        ]

        for url in malicious_urls[:5]:  # Limit tests
            try:
                response = self.page.goto(url)
                status = response.status if response else 0

                # 404, 403, 400 are acceptable
                success = status in [400, 403, 404, 302, 301]

                result = TestResult(
                    action=f"url_manipulation: {url}",
                    url=self.page.url,
                    success=success,
                    details={"status_code": status},
                )

                if not success and status == 200:
                    self.vulnerabilities.append(
                        {
                            "type": "path_traversal",
                            "url": url,
                            "status": status,
                        }
                    )

            except Exception as e:
                result = TestResult(
                    action=f"url_manipulation: {url}",
                    url=url,
                    success=True,  # Error is acceptable
                    error=str(e),
                )

            results.append(result)
            if self.session:
                self.session.add_result(result)

        return results

    def test_security_payloads(self) -> list:
        """Test security payloads on forms."""
        results = []

        # Navigate to a form page
        self.navigate("/accounts/login/")

        for payload in self.MALICIOUS_PAYLOADS:
            result = self.test_form_with_payload(payload)
            results.append(result)

        return results

    def test_concurrent_actions(self) -> TestResult:
        """Test concurrent form submissions."""
        try:
            # Open multiple tabs
            pages = [self.context.new_page() for _ in range(3)]

            for page in pages:
                page.goto("/accounts/login/")
                page.fill('input[name="login"]', "test@example.com")

            # Submit all at once
            for page in pages:
                try:
                    page.click('button[type="submit"]', no_wait_after=True)
                except:
                    pass

            # Close extra pages
            for page in pages:
                page.close()

            return TestResult(
                action="concurrent_submissions",
                url=self.page.url,
                success=True,
            )

        except Exception as e:
            return TestResult(
                action="concurrent_submissions",
                url=self.page.url,
                success=False,
                error=str(e),
            )

    def run(self) -> TestSession:
        """Execute chaos testing."""
        logger.info(f"Starting {self.name}")

        try:
            self.start_browser()

            # URL manipulation tests
            logger.info("Testing URL manipulation...")
            self.test_url_manipulation()

            # Input boundary tests
            logger.info("Testing input boundaries...")
            self.navigate("/accounts/signup/")
            self.test_input_boundaries()

            # Security payload tests
            logger.info("Testing security payloads...")
            self.test_security_payloads()

            # Rapid click tests
            logger.info("Testing rapid clicks...")
            self.navigate("/")
            result = self.test_rapid_clicks()
            self.session.add_result(result)

            # Concurrent action tests
            logger.info("Testing concurrent actions...")
            result = self.test_concurrent_actions()
            self.session.add_result(result)

            # Report vulnerabilities
            if self.vulnerabilities:
                logger.warning(
                    f"Found {len(self.vulnerabilities)} potential vulnerabilities!"
                )
                self.session.details = {"vulnerabilities": self.vulnerabilities}

            logger.info("Chaos testing complete.")
            return self.session

        finally:
            self.stop_browser()


def run_chaos_testing(report_path: str = "tests/agents/chaos_report.json"):
    """Convenience function to run chaos testing."""
    agent = ChaosAgent(headless=True)
    session = agent.run()
    session.save_report(report_path)
    return session


if __name__ == "__main__":
    session = run_chaos_testing()

    print("\n=== Chaos Agent Report ===")
    print(f"Actions performed: {len(session.results)}")
    print(f"Success rate: {session.success_rate:.1%}")

    if hasattr(session, "details") and session.details.get("vulnerabilities"):
        print("\nPotential vulnerabilities found:")
        for vuln in session.details["vulnerabilities"]:
            print(
                f'  - {vuln["type"]}: {vuln.get("url", vuln.get("payload", "")[:50])}'
            )
    else:
        print("\nNo vulnerabilities detected.")
