"""
User Journey Testing Agent

Simulates complete user journeys through the application,
testing critical paths that real users would follow.
"""

import logging
from .base_agent import BaseTestAgent, TestResult, TestSession

logger = logging.getLogger(__name__)


class UserJourneyAgent(BaseTestAgent):
    """
    Tests complete user journeys through the application.

    Journeys tested:
    1. New user signup and onboarding
    2. Document upload and analysis
    3. Rating calculation workflow
    4. Appeal decision and tracking
    5. Exam preparation checklist
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.journey_results = {}

    @property
    def name(self) -> str:
        return "UserJourneyAgent"

    def test_signup_journey(self) -> dict:
        """Test the new user signup journey."""
        logger.info("Testing signup journey...")
        results = {"steps": [], "success": True}

        # Step 1: Visit home page
        result = self.navigate("/")
        results["steps"].append(("visit_home", result.success))

        # Step 2: Click signup
        try:
            self.page.click('a[href*="signup"], a:has-text("Sign Up")', timeout=3000)
            self.page.wait_for_load_state("networkidle")
            results["steps"].append(("click_signup", True))
        except Exception:
            results["steps"].append(("click_signup", False))
            results["success"] = False
            return results

        # Step 3: Fill signup form (don't actually submit)
        try:
            self.page.fill('input[name="email"]', "journey_test@example.com")
            self.page.fill('input[name="password1"]', "SecurePassword123!")
            self.page.fill('input[name="password2"]', "SecurePassword123!")
            results["steps"].append(("fill_signup_form", True))
        except Exception:
            results["steps"].append(("fill_signup_form", False))
            results["success"] = False

        return results

    def test_login_dashboard_journey(self) -> dict:
        """Test login and dashboard access journey."""
        logger.info("Testing login/dashboard journey...")
        results = {"steps": [], "success": True}

        # Step 1: Navigate to login
        result = self.navigate("/accounts/login/")
        results["steps"].append(("navigate_login", result.success))

        # Check if already logged in (redirected to dashboard)
        if "/dashboard" in self.page.url:
            results["steps"].append(("already_logged_in", True))
            results["steps"].append(("dashboard_loaded", True))
            return results

        # Step 2: Fill credentials
        try:
            self.page.fill('input[name="login"]', "e2e_test@example.com")
            self.page.fill('input[name="password"]', "E2ETestPassword123!")
            results["steps"].append(("fill_credentials", True))
        except Exception:
            results["steps"].append(("fill_credentials", False))
            results["success"] = False
            return results

        # Step 3: Submit login
        try:
            self.page.click('button[type="submit"]')
            self.page.wait_for_url("**/dashboard/**", timeout=10000)
            results["steps"].append(("submit_login", True))
        except Exception:
            results["steps"].append(("submit_login", False))
            results["success"] = False
            return results

        # Step 4: Verify dashboard loaded
        try:
            self.page.wait_for_selector("h1", timeout=5000)
            results["steps"].append(("dashboard_loaded", True))
        except:
            results["steps"].append(("dashboard_loaded", False))
            results["success"] = False

        return results

    def test_rating_calculator_journey(self) -> dict:
        """Test the rating calculator workflow."""
        logger.info("Testing rating calculator journey...")
        results = {"steps": [], "success": True}

        # Login first
        login_result = self.test_login_dashboard_journey()
        if not login_result["success"]:
            results["success"] = False
            results["steps"].append(("login_prerequisite", False))
            return results

        # Step 1: Navigate to calculator
        result = self.navigate("/exam-prep/rating-calculator/")
        results["steps"].append(("navigate_calculator", result.success))

        if not result.success:
            results["success"] = False
            return results

        # Step 2: Verify calculator elements (page uses HTMX, no traditional form)
        try:
            self.page.wait_for_selector("input, button", timeout=5000)
            results["steps"].append(("calculator_loaded", True))
        except:
            results["steps"].append(("calculator_loaded", False))
            results["success"] = False
            return results

        # Step 3: Try to add a rating
        try:
            # Look for percentage input
            percentage = self.page.locator(
                'input[name="percentage"], input[type="number"]'
            ).first
            if percentage.is_visible():
                percentage.fill("50")
                results["steps"].append(("add_rating", True))
            else:
                results["steps"].append(("add_rating", "skipped"))
        except Exception:
            results["steps"].append(("add_rating", False))

        return results

    def test_appeal_journey(self) -> dict:
        """Test the appeal workflow journey."""
        logger.info("Testing appeal journey...")
        results = {"steps": [], "success": True}

        # Step 1: Visit appeals page (public)
        result = self.navigate("/appeals/")
        results["steps"].append(("visit_appeals", result.success))
        if not result.success:
            results["success"] = False

        # Step 2: Check decision tree
        result = self.navigate("/appeals/find-your-path/")
        results["steps"].append(("decision_tree", result.success))
        if not result.success:
            results["success"] = False

        # Step 3: Verify interactive elements
        try:
            form = self.page.locator("form, .decision-tree")
            if form.count() > 0:
                results["steps"].append(("tree_interactive", True))
            else:
                results["steps"].append(("tree_interactive", False))
                results["success"] = False
        except:
            results["steps"].append(("tree_interactive", False))
            results["success"] = False

        # Step 4: Check guidance pages
        guidance_links = self.page.locator('a[href*="/appeals/guide/"]')
        if guidance_links.count() > 0:
            try:
                guidance_links.first.click()
                self.page.wait_for_load_state("networkidle")
                results["steps"].append(("view_guidance", True))
            except:
                results["steps"].append(("view_guidance", False))
                results["success"] = False
        else:
            results["steps"].append(("view_guidance", "skipped"))

        return results

    def test_exam_prep_journey(self) -> dict:
        """Test the exam prep workflow."""
        logger.info("Testing exam prep journey...")
        results = {"steps": [], "success": True}

        # Step 1: Visit exam prep
        result = self.navigate("/exam-prep/")
        results["steps"].append(("visit_examprep", result.success))
        if not result.success:
            results["success"] = False

        # Step 2: Check guides
        guide_links = self.page.locator('a[href*="/exam-prep/guide/"]')
        if guide_links.count() > 0:
            try:
                guide_links.first.click()
                self.page.wait_for_load_state("networkidle")
                results["steps"].append(("view_guide", True))
            except:
                results["steps"].append(("view_guide", False))
                results["success"] = False
        else:
            results["steps"].append(("view_guide", "skipped"))

        # Step 3: Check glossary
        result = self.navigate("/exam-prep/glossary/")
        results["steps"].append(("visit_glossary", result.success))
        if not result.success:
            results["success"] = False

        # Step 4: Check secondary conditions
        result = self.navigate("/exam-prep/secondary-conditions/")
        results["steps"].append(("visit_secondary", result.success))
        if not result.success:
            results["success"] = False

        return results

    def test_document_journey(self) -> dict:
        """Test document upload journey."""
        logger.info("Testing document journey...")
        results = {"steps": [], "success": True}

        # Login first
        login_result = self.test_login_dashboard_journey()
        if not login_result["success"]:
            results["success"] = False
            results["steps"].append(("login_prerequisite", False))
            return results

        # Step 1: Navigate to documents
        result = self.navigate("/claims/")
        results["steps"].append(("navigate_documents", result.success))
        if not result.success:
            results["success"] = False

        # Step 2: Go to upload page
        result = self.navigate("/claims/upload/")
        results["steps"].append(("navigate_upload", result.success))
        if not result.success:
            results["success"] = False

        # Step 3: Verify upload form
        try:
            file_input = self.page.locator('input[type="file"]')
            if file_input.count() > 0:
                results["steps"].append(("upload_form", True))
            else:
                results["steps"].append(("upload_form", False))
                results["success"] = False
        except:
            results["steps"].append(("upload_form", False))
            results["success"] = False

        return results

    def run(self) -> TestSession:
        """Execute all user journeys."""
        logger.info(f"Starting {self.name}")

        try:
            self.start_browser()

            # Run each journey
            self.journey_results["signup"] = self.test_signup_journey()
            self.journey_results["login_dashboard"] = (
                self.test_login_dashboard_journey()
            )
            self.journey_results["rating_calculator"] = (
                self.test_rating_calculator_journey()
            )
            self.journey_results["appeal"] = self.test_appeal_journey()
            self.journey_results["exam_prep"] = self.test_exam_prep_journey()
            self.journey_results["document"] = self.test_document_journey()

            # Summarize results
            for journey_name, journey_result in self.journey_results.items():
                result = TestResult(
                    action=f"journey_{journey_name}",
                    url=self.page.url if self.page else "",
                    success=journey_result["success"],
                    details={"steps": journey_result["steps"]},
                )
                self.session.add_result(result)

            logger.info("User journeys complete.")
            return self.session

        finally:
            self.stop_browser()


def run_user_journeys(report_path: str = "tests/agents/journey_report.json"):
    """Convenience function to run user journey tests."""
    agent = UserJourneyAgent(headless=True)
    session = agent.run()
    session.save_report(report_path)
    return session


if __name__ == "__main__":
    session = run_user_journeys()

    print("\n=== User Journey Agent Report ===")
    print(f"Journeys tested: {len(session.results)}")
    print(f"Success rate: {session.success_rate:.1%}")

    for result in session.results:
        status = "✓" if result.success else "✗"
        print(f"  {status} {result.action}")
        if result.details.get("steps"):
            for step, success in result.details["steps"]:
                step_status = (
                    "✓" if success is True else ("○" if success == "skipped" else "✗")
                )
                print(f"      {step_status} {step}")
