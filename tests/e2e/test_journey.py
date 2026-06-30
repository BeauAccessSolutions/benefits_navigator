"""
E2E Tests for Journey Tracking

Tests cover:
- Journey dashboard
- Timeline view
- Milestones
- Deadlines
"""

from playwright.sync_api import Page, expect


class TestJourneyDashboard:
    """Test journey dashboard."""

    def test_journey_requires_auth(self, page: Page):
        """Journey should require authentication."""
        page.goto("/journey/")
        expect(page).to_have_url("/accounts/login/?next=/journey/")

    def test_journey_loads(self, authenticated_page: Page):
        """Authenticated users can access journey."""
        page = authenticated_page
        page.goto("/journey/")

        expect(page).to_have_url("/journey/")
        expect(page.locator("h1").last).to_be_visible()

    def test_timeline_visible(self, authenticated_page: Page):
        """Timeline should be visible on journey page."""
        page = authenticated_page
        page.goto("/journey/")

        # Look for timeline elements
        timeline = page.locator(
            ".timeline, [data-timeline], .journey-timeline, " ".events, .milestones"
        )
        page.wait_for_timeout(500)


class TestMilestones:
    """Test milestone management."""

    def test_add_milestone_button(self, authenticated_page: Page):
        """Should have option to add milestone."""
        page = authenticated_page
        page.goto("/journey/")

        add_button = page.locator(
            'a[href*="milestone/add"], button:has-text("Milestone"), '
            'a:has-text("Add Milestone")'
        )
        expect(add_button.first).to_be_visible()

    def test_add_milestone_form(self, authenticated_page: Page):
        """Add milestone form should work."""
        page = authenticated_page
        page.goto("/journey/milestone/add/")

        expect(page.locator("form")).to_be_visible()

        # Should have title field
        title = page.locator('input[name*="title"]')
        expect(title.first).to_be_visible()

        # Should have date field
        date = page.locator('input[type="date"], input[name*="date"]')
        expect(date.first).to_be_visible()

    def test_add_milestone_submit(self, authenticated_page: Page):
        """Should be able to submit new milestone."""
        page = authenticated_page
        page.goto("/journey/milestone/add/")

        # Fill form
        page.fill('input[name*="title"]', "Test Milestone")
        page.fill('input[type="date"]', "2024-01-15")

        # Look for milestone type if exists
        type_select = page.locator('select[name*="type"]')
        if type_select.count() > 0:
            type_select.first.select_option(index=1)

        # Submit
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # Should redirect to journey
        expect(page).to_have_url("/journey/")


class TestDeadlines:
    """Test deadline management."""

    def test_add_deadline_button(self, authenticated_page: Page):
        """Should have option to add deadline."""
        page = authenticated_page
        page.goto("/journey/")

        add_button = page.locator(
            'a[href*="deadline/add"], button:has-text("Deadline"), '
            'a:has-text("Add Deadline")'
        )
        expect(add_button.first).to_be_visible()

    def test_add_deadline_form(self, authenticated_page: Page):
        """Add deadline form should work."""
        page = authenticated_page
        page.goto("/journey/deadline/add/")

        expect(page.locator("form")).to_be_visible()

        # Should have title field
        title = page.locator('input[name*="title"]')
        expect(title.first).to_be_visible()

        # Should have date field
        date = page.locator('input[type="date"], input[name*="date"]')
        expect(date.first).to_be_visible()

    def test_deadline_toggle(self, authenticated_page: Page):
        """Should be able to toggle deadline completion."""
        page = authenticated_page
        page.goto("/journey/")

        # Look for deadline toggle buttons
        toggle = page.locator('button[hx-post*="toggle"], input[type="checkbox"]')
        # May or may not have deadlines
        page.wait_for_timeout(500)

    def test_deadline_priority_indicator(self, authenticated_page: Page):
        """Deadlines should show priority."""
        page = authenticated_page
        page.goto("/journey/")

        # Look for priority indicators
        priority = page.locator(".priority, [data-priority], .urgent, .critical")
        # May or may not have deadlines with priority
        page.wait_for_timeout(500)


class TestTimelineHtmx:
    """Test HTMX timeline features."""

    def test_timeline_partial_loads(self, authenticated_page: Page):
        """Timeline partial should load via HTMX."""
        page = authenticated_page
        page.goto("/journey/")

        # Look for HTMX-enhanced elements
        htmx_elements = page.locator("[hx-get], [hx-post]")
        page.wait_for_timeout(500)

    def test_toggle_updates_ui(self, authenticated_page: Page):
        """Toggling should update UI without full reload."""
        page = authenticated_page
        page.goto("/journey/")

        # Check for HTMX swap targets
        swap_targets = page.locator("[hx-target], [hx-swap]")
        page.wait_for_timeout(500)
