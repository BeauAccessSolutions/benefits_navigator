"""
KnowVA M21-1 Web Scraper

Scrapes M21-1 Adjudication Procedures Manual from VA's KnowVA system.

Usage:
    from agents.knowva_scraper import KnowVAScraper

    scraper = KnowVAScraper()
    section_data = scraper.scrape_section(article_id='554400000181474')
"""

import time
import re
import logging
from typing import Dict, List, Optional, Tuple

from bs4 import BeautifulSoup
from playwright.sync_api import (
    sync_playwright,
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

logger = logging.getLogger(__name__)


class KnowVAScraper:
    """
    Scraper for VA KnowVA M21-1 manual sections.

    Features:
    - JavaScript rendering with Playwright
    - Rate limiting to be respectful of VA servers
    - Retry logic for failed requests
    - Content parsing and structuring
    """

    # KnowVA URL pattern
    BASE_URL = "https://www.knowva.ebenefits.va.gov/system/templates/selfservice/va_ssnew/help/customer/locale/en-US/portal/554400000001018/content/{article_id}/"

    # Rate limiting (seconds between requests)
    RATE_LIMIT = 3.0
    RETRY_ATTEMPTS = 3
    RETRY_DELAY = 5.0
    PAGE_LOAD_TIMEOUT = 30000  # 30 seconds

    def __init__(self, headless: bool = True, rate_limit: float = None):
        """
        Initialize scraper.

        Args:
            headless: Run browser in headless mode
            rate_limit: Override default rate limit (seconds)
        """
        self.headless = headless
        self.rate_limit = rate_limit or self.RATE_LIMIT
        self.last_request_time = 0

    def _wait_for_rate_limit(self):
        """Ensure we don't exceed rate limit."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            sleep_time = self.rate_limit - elapsed
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_request_time = time.time()

    def scrape_section(
        self, article_id: str, max_retries: int = None
    ) -> Optional[Dict]:
        """
        Scrape a single M21-1 section from KnowVA.

        Args:
            article_id: KnowVA article ID
            max_retries: Number of retry attempts

        Returns:
            Dict with section data or None if failed
        """
        max_retries = max_retries or self.RETRY_ATTEMPTS

        for attempt in range(max_retries):
            try:
                self._wait_for_rate_limit()

                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=self.headless)
                    context = browser.new_context(
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        viewport={"width": 1920, "height": 1080},
                    )
                    page = context.new_page()

                    # Construct URL
                    url = self.BASE_URL.format(article_id=article_id)
                    logger.info(f"Fetching {url} (attempt {attempt + 1}/{max_retries})")

                    # Navigate to page
                    response = page.goto(
                        url, wait_until="networkidle", timeout=self.PAGE_LOAD_TIMEOUT
                    )

                    if response and response.status >= 400:
                        logger.error(f"HTTP {response.status} for article {article_id}")
                        browser.close()
                        if attempt < max_retries - 1:
                            time.sleep(self.RETRY_DELAY)
                            continue
                        return None

                    # Wait for content to render
                    time.sleep(2)

                    # Extract content
                    data = self._parse_page(page, article_id, url)

                    browser.close()

                    if data:
                        logger.info(
                            f"Successfully scraped article {article_id}: {data.get('title', 'Unknown')}"
                        )
                        return data
                    else:
                        logger.warning(f"No data extracted from article {article_id}")
                        if attempt < max_retries - 1:
                            time.sleep(self.RETRY_DELAY)
                            continue
                        return None

            except PlaywrightTimeoutError as e:
                logger.error(f"Timeout scraping article {article_id}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(self.RETRY_DELAY)
                    continue
                return None

            except Exception as e:
                logger.error(f"Error scraping article {article_id}: {e}", exc_info=True)
                if attempt < max_retries - 1:
                    time.sleep(self.RETRY_DELAY)
                    continue
                return None

        logger.error(
            f"Failed to scrape article {article_id} after {max_retries} attempts"
        )
        return None

    def _parse_page(self, page: Page, article_id: str, url: str) -> Optional[Dict]:
        """
        Parse M21-1 content from KnowVA page.

        Args:
            page: Playwright page object
            article_id: Article ID
            url: Full URL

        Returns:
            Dict with parsed content
        """
        try:
            # Get page title - try multiple selectors
            title = None
            for selector in ["h1", ".article-title", ".page-title", "title"]:
                try:
                    title_elem = page.query_selector(selector)
                    if title_elem:
                        title = title_elem.inner_text().strip()
                        if title and not title.startswith("KnowVA"):
                            break
                except:
                    continue

            # Parse title to extract M21 reference
            reference_data = self._parse_m21_reference(title) if title else {}

            # Get main content - try multiple selectors
            content_html = None
            content_text = None
            for selector in [
                ".article-content",
                ".article-body",
                ".content-body",
                "article",
                "#content",
                "main",
            ]:
                try:
                    content_elem = page.query_selector(selector)
                    if content_elem:
                        content_html = content_elem.inner_html()
                        content_text = content_elem.inner_text()
                        if content_text and len(content_text.strip()) > 100:
                            break
                except:
                    continue

            if not content_text or len(content_text.strip()) < 50:
                logger.warning(f"Insufficient content for article {article_id}")
                return None

            # Parse structured content
            soup = BeautifulSoup(content_html, "html.parser") if content_html else None
            topics = (
                self._extract_topics(soup, content_text, reference_data) if soup else []
            )
            references = self._extract_references(content_text)

            # Try to find last updated date
            last_updated = None
            for selector in [".last-updated", ".update-date", ".modified-date"]:
                try:
                    date_elem = page.query_selector(selector)
                    if date_elem:
                        date_text = date_elem.inner_text()
                        last_updated = self._parse_date(date_text)
                        if last_updated:
                            break
                except:
                    continue

            # Extract overview (typically first paragraph or section before topics)
            overview = self._extract_overview(content_text, topics)

            return {
                "article_id": article_id,
                "url": url,
                "title": title or "Unknown",
                "content": content_text,
                "content_html": content_html,
                "overview": overview,
                "topics": topics,
                "references": references,
                "last_updated": last_updated,
                **reference_data,
            }

        except Exception as e:
            logger.error(
                f"Error parsing page for article {article_id}: {e}", exc_info=True
            )
            return None

    def _parse_m21_reference(self, title: str) -> Dict:
        """
        Parse M21-1 reference from title.

        Example: "M21-1, Part I, Subpart i, Chapter 1, Section A - Title"

        Returns:
            Dict with parsed reference components
        """
        # Pattern: M21-1, Part ROMAN, Subpart roman, Chapter NUM, Section LETTER - Title
        pattern = r"M21-1,?\s*Part\s+([IVX]+),?\s*Subpart\s+([ivx]+),?\s*Chapter\s+(\d+),?\s*Section\s+([A-Z])\s*[-–—]\s*(.+?)$"
        match = re.search(pattern, title, re.IGNORECASE)

        if match:
            part = match.group(1).upper()
            subpart = match.group(2).lower()
            chapter = match.group(3)
            section = match.group(4).upper()
            section_title = match.group(5).strip()

            return {
                "part": part,
                "part_number": self._roman_to_int(part),
                "subpart": subpart,
                "chapter": chapter,
                "section": section,
                "section_title": section_title,
                "reference": f"M21-1.{part}.{subpart}.{chapter}.{section}",
                "full_reference": f"M21-1, Part {part}, Subpart {subpart}, Chapter {chapter}, Section {section}",
                "part_title": self._get_part_title(part),
            }
        else:
            logger.warning(f"Could not parse M21 reference from title: {title}")
            return {"section_title": title, "reference": "", "full_reference": ""}

    def _extract_topics(
        self, soup: BeautifulSoup, content_text: str, reference_data: Dict
    ) -> List[Dict]:
        """
        Extract structured topics from section content.

        Topics typically have format like: I.i.1.A.1.a. Topic Title
        """
        topics = []

        if not reference_data.get("part"):
            return topics

        # Build topic code pattern
        # Example: I.i.1.A.1.a.
        part = reference_data.get("part", "")
        subpart = reference_data.get("subpart", "")
        chapter = reference_data.get("chapter", "")
        section = reference_data.get("section", "")

        topic_pattern = rf"{re.escape(part)}\.{re.escape(subpart)}\.{re.escape(chapter)}\.{re.escape(section)}\.(\d+)\.([a-z])\.\s*(.+?)(?:\n|$)"

        matches = re.finditer(topic_pattern, content_text, re.MULTILINE)

        for match in matches:
            topic_num = match.group(1)
            subtopic = match.group(2)
            topic_title = match.group(3).strip()

            topic_code = f"{part}.{subpart}.{chapter}.{section}.{topic_num}.{subtopic}"

            # Try to extract content for this topic
            # (content between this topic and next topic/end)
            topic_content = ""
            # This is simplified - could be enhanced to extract actual content

            topics.append(
                {
                    "code": topic_code,
                    "topic_num": topic_num,
                    "subtopic": subtopic,
                    "title": topic_title,
                    "content": topic_content,
                }
            )

        return topics

    def _extract_overview(self, content_text: str, topics: List[Dict]) -> str:
        """
        Extract overview/introduction text.

        Typically the content before the first topic starts.
        """
        if not content_text:
            return ""

        # If we have topics, extract text before first topic
        if topics and topics[0].get("title"):
            first_topic_title = topics[0]["title"]
            idx = content_text.find(first_topic_title)
            if idx > 0:
                overview = content_text[:idx].strip()
                # Clean up common headers
                overview = re.sub(
                    r"^(Overview|Introduction|In This Section)[\s:]*",
                    "",
                    overview,
                    flags=re.IGNORECASE,
                )
                return overview[:1000]  # Limit length

        # Otherwise, take first few paragraphs (up to 1000 chars)
        paragraphs = content_text.split("\n\n")
        overview = "\n\n".join(paragraphs[:3])
        return overview[:1000]

    def _extract_references(self, content: str) -> List[str]:
        """
        Extract M21-1 and CFR references from content.
        """
        references = []

        # M21-1 references: "M21-1, Part I, Subpart ii, ..."
        m21_pattern = r"M21-1,?\s*Part\s+[IVX]+,?\s*Subpart\s+[ivx]+,?[\s\w,]+"
        m21_matches = re.finditer(m21_pattern, content)
        for match in m21_matches:
            ref = match.group().strip()
            if ref and ref not in references:
                references.append(ref)

        # CFR references: "38 CFR 3.102"
        cfr_pattern = r"38\s+CFR\s+[\d\.]+"
        cfr_matches = re.finditer(cfr_pattern, content)
        for match in cfr_matches:
            ref = match.group().strip()
            if ref and ref not in references:
                references.append(ref)

        return references[:20]  # Limit to first 20

    def _parse_date(self, date_text: str) -> Optional[str]:
        """Parse date from various formats."""
        # This is simplified - could use python-dateutil for better parsing
        # For now, just extract something that looks like a date
        date_pattern = r"(\d{1,2}/\d{1,2}/\d{2,4})|(\w+ \d{1,2},? \d{4})"
        match = re.search(date_pattern, date_text)
        if match:
            return match.group()
        return None

    def _roman_to_int(self, roman: str) -> int:
        """Convert Roman numeral to integer."""
        values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}
        result = 0
        prev = 0
        for char in reversed(roman.upper()):
            curr = values.get(char, 0)
            if curr < prev:
                result -= curr
            else:
                result += curr
            prev = curr
        return result

    def _get_part_title(self, part_num: str) -> str:
        """Get the title for a part number."""
        titles = {
            "I": "Claimants' Rights and Claims Processing Centers and Programs",
            "II": "Intake, Claims Establishment, Jurisdiction, and File Maintenance",
            "III": "The Development Process",
            "IV": "Examinations",
            "V": "The Rating Process",
            "VI": "The Authorization Process",
            "VII": "Dependency",
            "VIII": "Special Compensation Issues",
            "IX": "Pension, Survivors' Pension, and Parent's DIC",
            "X": "Benefits Administration and Oversight",
            "XI": "Notice of Death, Benefits Payable at Death, and Burial Benefits",
            "XII": "DIC and Other Survivor's Benefits",
            "XIII": "Eligibility Determinations and Information Sharing",
            "XIV": "Matching Programs",
        }
        return titles.get(part_num.upper(), f"Part {part_num}")

    def scrape_multiple(
        self, article_ids: List[str], progress_callback: Optional[callable] = None
    ) -> Tuple[List[Dict], List[str]]:
        """
        Scrape multiple sections.

        Args:
            article_ids: List of article IDs to scrape
            progress_callback: Optional callback(current, total, article_id)

        Returns:
            Tuple of (successful_data_list, failed_article_ids)
        """
        successful = []
        failed = []

        total = len(article_ids)
        for idx, article_id in enumerate(article_ids, 1):
            if progress_callback:
                progress_callback(idx, total, article_id)

            data = self.scrape_section(article_id)

            if data:
                successful.append(data)
            else:
                failed.append(article_id)

            logger.info(
                f"Progress: {idx}/{total} - Success: {len(successful)}, Failed: {len(failed)}"
            )

        return successful, failed


# Predefined article IDs from KnowVA
# These can be discovered by browsing KnowVA and inspecting URLs
# Source: M21-1 Adjudication Procedures Manual Table of Contents
KNOWN_ARTICLE_IDS = {
    # Part I - Claimants' Rights and Claims Processing Centers
    "I.i.1.A": "554400000181474",  # Duty to Notify and Duty to Assist
    "I.i.1.B": "554400000181476",  # Due Process
    "I.i.2.A": "554400000181477",  # Power of Attorney (POA)
    "I.i.2.B": "554400000181479",  # Representative's Right to Notification
    "I.i.2.C": "554400000181482",  # System Updates for POA Appointments
    "I.ii.1.A": "554400000181483",  # Structure of the VSC
    "I.ii.1.B": "554400000181484",  # Organization of PMCs
    "I.ii.1.C": "554400000181485",  # PMC Procedures
    # Part II - Intake, Claims Establishment, Jurisdiction
    "II.i.1.A": "554400000174855",  # Centralized Mail (CM) Intake
    "II.i.1.B": "554400000174856",  # VCIP Shipping
    "II.i.2.A": "554400000174858",  # Process Overview for Screening Mail
    "II.i.2.B": "554400000174859",  # Recording Date of Receipt
    "II.i.2.C": "554400000174860",  # Mail Management
    "II.i.2.D": "554400000174861",  # Handling Specific Types of Mail
    "II.iii.1.A": "554400000174869",  # Applications for Benefits
    "II.iii.1.B": "554400000174870",  # Screening Applications
    "II.iii.1.C": "554400000174871",  # Substantial Completeness
    "II.iii.2.A": "554400000174872",  # Intent to File
    "II.iii.2.B": "554400000174873",  # Supplemental Claims
    # Part III - The Development Process
    "III.ii.2.B": "554400000014119",  # Procedures for Obtaining STRs
    # Part IV - Examinations
    "IV.i.1.A": "554400000180494",  # Duty to Assist With Examination
    # Part V - The Rating Process
    "V.ii.4.A": "554400000180492",  # Effective Dates
    # Part VIII - Special Compensation Issues
    "VIII.i.1.A": "554400000177422",  # Herbicide Exposure Claims
}


def get_article_id_for_reference(reference: str) -> Optional[str]:
    """
    Get KnowVA article ID for an M21-1 reference.

    Args:
        reference: M21-1 reference like "I.i.1.A"

    Returns:
        Article ID if known, else None
    """
    return KNOWN_ARTICLE_IDS.get(reference)
