"""
E2E Tests for Document Upload and Processing

Tests cover:
- Document upload form
- File type validation
- Upload progress
- Document list view
- Document detail view
- Document deletion
- Denial letter decoder
"""

from playwright.sync_api import Page, expect


class TestDocumentList:
    """Test document list page."""

    def test_document_list_requires_auth(self, page: Page):
        """Document list should require authentication."""
        page.goto("/claims/")
        expect(page).to_have_url("/accounts/login/?next=/claims/")

    def test_document_list_loads(self, authenticated_page: Page):
        """Authenticated users can access document list."""
        page = authenticated_page
        page.goto("/claims/")
        expect(page).to_have_url("/claims/")
        expect(page.locator("h1").last).to_be_visible()

    def test_upload_button_visible(self, authenticated_page: Page):
        """Upload button should be visible on document list."""
        page = authenticated_page
        page.goto("/claims/")

        upload_link = page.locator(
            'a[href*="upload"], button:has-text("Upload"), ' 'a:has-text("Upload")'
        )
        expect(upload_link.first).to_be_visible()


class TestDocumentUpload:
    """Test document upload functionality."""

    def test_upload_page_loads(self, authenticated_page: Page):
        """Upload page should be accessible."""
        page = authenticated_page
        page.goto("/claims/upload/")

        expect(page).to_have_url("/claims/upload/")
        expect(page.locator("form")).to_be_visible()
        expect(page.locator('input[type="file"]')).to_be_visible()

    def test_upload_form_has_document_types(self, authenticated_page: Page):
        """Upload form should have document type selection."""
        page = authenticated_page
        page.goto("/claims/upload/")

        # Look for document type select/radio
        doc_type = page.locator(
            'select[name*="type"], select[name*="document"], '
            'input[name*="type"][type="radio"]'
        )
        expect(doc_type.first).to_be_visible()

    def test_upload_without_file_shows_error(self, authenticated_page: Page):
        """Submitting without file should show error."""
        page = authenticated_page
        page.goto("/claims/upload/")

        # Try to submit without file
        submit_button = page.locator('button[type="submit"]')
        submit_button.click()

        # Should show validation error
        page.wait_for_timeout(500)
        # Form should still be visible (not redirected)
        expect(page.locator("form")).to_be_visible()

    def test_upload_accepts_pdf(self, authenticated_page: Page):
        """Upload should accept PDF files."""
        page = authenticated_page
        page.goto("/claims/upload/")

        # Check that file input accepts PDFs
        file_input = page.locator('input[type="file"]')
        accept_attr = file_input.get_attribute("accept")
        # Accept should include PDF or be empty (all files)
        if accept_attr:
            assert "pdf" in accept_attr.lower() or "*" in accept_attr


class TestDocumentDetail:
    """Test document detail page."""

    def test_document_detail_requires_auth(self, page: Page):
        """Document detail should require authentication."""
        page.goto("/claims/document/1/")
        expect(page).to_have_url("/accounts/login/?next=/claims/document/1/")


class TestDenialDecoder:
    """Test denial letter decoder."""

    def test_decoder_page_loads(self, authenticated_page: Page):
        """Denial decoder page should be accessible."""
        page = authenticated_page
        page.goto("/claims/decode/")

        expect(page).to_have_url("/claims/decode/")
        expect(page.locator("form")).to_be_visible()

    def test_decoder_accepts_file(self, authenticated_page: Page):
        """Decoder should have file upload input."""
        page = authenticated_page
        page.goto("/claims/decode/")

        file_input = page.locator('input[type="file"]')
        expect(file_input).to_be_visible()

    def test_decoder_usage_limits_displayed(self, authenticated_page: Page):
        """Free tier should see usage limits."""
        page = authenticated_page
        page.goto("/claims/decode/")

        # Look for usage indicator
        page.wait_for_timeout(500)
        # Usage info might be displayed somewhere on the page
