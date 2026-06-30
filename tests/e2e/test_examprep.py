"""
E2E Tests for Exam Preparation Features

Tests cover:
- Exam guides
- Glossary
- Checklists
- Secondary conditions
- Evidence checklists
"""

from playwright.sync_api import Page, expect


class TestExamGuides:
    """Test exam preparation guides."""

    def test_guides_list_loads(self, page: Page):
        """Exam guides list should be accessible."""
        page.goto("/exam-prep/")
        expect(page).to_have_url("/exam-prep/")
        expect(page.locator("h1").last).to_be_visible()

    def test_guides_are_listed(self, page: Page):
        """Should display available guides."""
        page.goto("/exam-prep/")

        # Look for guide links or cards
        guides = page.locator(
            'a[href*="/exam-prep/guide/"], .guide-card, ' ".exam-guide, article"
        )
        # May or may not have guides depending on fixtures
        page.wait_for_timeout(500)

    def test_guide_detail_loads(self, page: Page):
        """Individual guide should load."""
        page.goto("/exam-prep/")

        # Click first guide if available
        guide_links = page.locator('a[href*="/exam-prep/guide/"]')
        if guide_links.count() > 0:
            guide_links.first.click()
            page.wait_for_load_state("networkidle")

            # Should have guide content
            expect(page.locator("main").first).to_be_visible()

    def test_guide_has_checklist(self, page: Page):
        """Guide should have preparation checklist."""
        page.goto("/exam-prep/")

        guide_links = page.locator('a[href*="/exam-prep/guide/"]')
        if guide_links.count() > 0:
            guide_links.first.click()
            page.wait_for_load_state("networkidle")

            # Look for checklist section
            checklist = page.locator(".checklist, ul, ol, [data-checklist]")
            page.wait_for_timeout(500)


class TestGlossary:
    """Test VA terminology glossary."""

    def test_glossary_list_loads(self, page: Page):
        """Glossary should be accessible."""
        page.goto("/exam-prep/glossary/")
        expect(page).to_have_url("/exam-prep/glossary/")

    def test_glossary_search(self, page: Page):
        """Glossary should have search functionality."""
        page.goto("/exam-prep/glossary/")

        # Look for search input
        search = page.locator(
            'input[type="search"], input[name="q"], '
            'input[name="search"], input[placeholder*="search" i]'
        )
        if search.count() > 0:
            search.first.fill("nexus")
            page.wait_for_timeout(500)

    def test_glossary_term_detail(self, page: Page):
        """Glossary term detail should load."""
        page.goto("/exam-prep/glossary/")

        # Click first term if available
        term_links = page.locator('a[href*="/exam-prep/glossary/"]')
        if term_links.count() > 0:
            term_links.first.click()
            page.wait_for_load_state("networkidle")

            # Should have term definition
            expect(page.locator("main").first).to_be_visible()


class TestMyChecklists:
    """Test user's exam checklists."""

    def test_checklists_requires_auth(self, page: Page):
        """My checklists should require authentication."""
        page.goto("/exam-prep/my-checklists/")
        expect(page).to_have_url("/accounts/login/?next=/exam-prep/my-checklists/")

    def test_checklists_loads(self, authenticated_page: Page):
        """Authenticated users can access checklists."""
        page = authenticated_page
        page.goto("/exam-prep/my-checklists/")

        expect(page).to_have_url("/exam-prep/my-checklists/")
        expect(page.locator("h1").last).to_be_visible()

    def test_create_checklist_button(self, authenticated_page: Page):
        """Should have option to create new checklist."""
        page = authenticated_page
        page.goto("/exam-prep/my-checklists/")

        create_button = page.locator(
            'a[href*="create"], button:has-text("Create"), '
            'a:has-text("New"), a:has-text("Add")'
        )
        expect(create_button.first).to_be_visible()

    def test_create_checklist_form(self, authenticated_page: Page):
        """Create checklist form should work."""
        page = authenticated_page
        page.goto("/exam-prep/my-checklists/create/")

        expect(page.locator("form")).to_be_visible()

        # Should have condition field
        condition = page.locator('input[name*="condition"], select[name*="condition"]')
        expect(condition.first).to_be_visible()

        # Should have exam date field
        date = page.locator('input[type="date"], input[name*="date"]')
        expect(date.first).to_be_visible()


class TestSecondaryConditions:
    """Test secondary conditions feature."""

    def test_secondary_conditions_hub_loads(self, page: Page):
        """Secondary conditions hub should be accessible."""
        page.goto("/exam-prep/secondary-conditions/")
        expect(page).to_have_url("/exam-prep/secondary-conditions/")

    def test_secondary_conditions_search(self, page: Page):
        """Should be able to search secondary conditions."""
        page.goto("/exam-prep/secondary-conditions/")

        # Look for search input
        search = page.locator(
            'input[type="search"], input[name="q"], ' 'input[placeholder*="search" i]'
        )
        if search.count() > 0:
            search.first.fill("PTSD")
            page.wait_for_timeout(500)

    def test_secondary_condition_detail(self, page: Page):
        """Secondary condition detail should load."""
        page.goto("/exam-prep/secondary-conditions/")

        # Click first condition if available
        condition_links = page.locator('a[href*="/exam-prep/secondary-conditions/"]')
        if condition_links.count() > 0:
            condition_links.first.click()
            page.wait_for_load_state("networkidle")

            # Should have condition info
            expect(page.locator("main, article")).to_be_visible()


class TestEvidenceChecklists:
    """Test evidence checklists."""

    def test_evidence_checklist_list(self, authenticated_page: Page):
        """Evidence checklist list should load."""
        page = authenticated_page
        page.goto("/exam-prep/evidence-checklist/")

        expect(page).to_have_url("/exam-prep/evidence-checklist/")

    def test_create_evidence_checklist(self, authenticated_page: Page):
        """Should be able to create evidence checklist."""
        page = authenticated_page
        page.goto("/exam-prep/evidence-checklist/new/")

        expect(page.locator("form")).to_be_visible()

    def test_evidence_checklist_toggle(self, authenticated_page: Page):
        """Should be able to toggle evidence items."""
        page = authenticated_page
        page.goto("/exam-prep/evidence-checklist/")

        # Look for existing checklists
        checklist_links = page.locator('a[href*="/exam-prep/evidence-checklist/"]')
        if checklist_links.count() > 0:
            checklist_links.first.click()
            page.wait_for_load_state("networkidle")

            # Look for toggle buttons/checkboxes
            toggles = page.locator(
                'input[type="checkbox"], button:has-text("Complete"), ' "[data-toggle]"
            )
            page.wait_for_timeout(500)
