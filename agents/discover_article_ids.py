"""
Utility script to discover M21-1 article IDs from KnowVA.

This script helps build a comprehensive list of article IDs by:
1. Scraping the M21-1 table of contents from KnowVA
2. Extracting article IDs from URLs
3. Saving them to a JSON file for later import

Usage:
    python manage.py shell
    >>> from agents.discover_article_ids import discover_m21_articles
    >>> articles = discover_m21_articles()
    >>> # Or run directly:
    python -c "from agents.discover_article_ids import main; main()"

Or as a standalone script:
    cd /path/to/benefits-navigator
    python agents/discover_article_ids.py
"""

import json
import re
import time
import logging
from pathlib import Path
from typing import Dict

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class M21ArticleDiscoverer:
    """
    Discovers M21-1 article IDs from KnowVA.

    The M21-1 manual has a table of contents/index page that lists all sections.
    This script navigates that structure to extract article IDs.
    """

    # KnowVA M21-1 index/TOC URL patterns to try
    TOC_URLS = [
        "https://www.knowva.ebenefits.va.gov/system/templates/selfservice/va_ssnew/help/customer/locale/en-US/portal/554400000001018/topic/554400000001141",  # Main M21-1 page
        "https://www.knowva.ebenefits.va.gov/system/templates/selfservice/va_ssnew/help/customer/locale/en-US/portal/554400000001018/category/M21-1_Adjudication_Procedures_Manual",
    ]

    def __init__(self, headless: bool = True, output_file: str = None):
        self.headless = headless
        self.output_file = output_file or "agents/data/discovered_m21_articles.json"

    def discover_all(self) -> Dict[str, Dict]:
        """
        Discover all M21-1 articles.

        Returns:
            Dict mapping references to article data
        """
        all_articles = {}

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()

            # Try each TOC URL
            for toc_url in self.TOC_URLS:
                logger.info(f"Trying TOC URL: {toc_url}")

                try:
                    articles = self._scrape_toc_page(page, toc_url)
                    if articles:
                        logger.info(f"Found {len(articles)} articles from {toc_url}")
                        all_articles.update(articles)
                        break  # Success, no need to try other URLs
                except Exception as e:
                    logger.warning(f"Failed to scrape {toc_url}: {e}")
                    continue

            browser.close()

        if not all_articles:
            logger.warning(
                "No articles discovered. You may need to manually find article IDs."
            )
            logger.info("To manually discover article IDs:")
            logger.info("1. Visit https://www.knowva.ebenefits.va.gov")
            logger.info("2. Search for 'M21-1'")
            logger.info("3. Browse the sections and inspect URLs")
            logger.info("4. Article IDs are in URLs like /content/554400000181474/")

        return all_articles

    def _scrape_toc_page(self, page, url: str) -> Dict[str, Dict]:
        """
        Scrape table of contents page for article links.
        """
        articles = {}

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(3)  # Let JavaScript render

            # Get all links on the page
            links = page.query_selector_all("a")

            for link in links:
                try:
                    href = link.get_attribute("href")
                    text = link.inner_text().strip()

                    if not href or not text:
                        continue

                    # Look for M21-1 article links
                    # Pattern: /content/{article_id}/...
                    article_id_match = re.search(r"/content/(\d+)/", href)

                    if article_id_match and "M21-1" in text:
                        article_id = article_id_match.group(1)

                        # Parse reference from text
                        ref_data = self._parse_reference_from_text(text)

                        if ref_data:
                            articles[ref_data["reference"]] = {
                                "article_id": article_id,
                                "url": (
                                    f"https://www.knowva.ebenefits.va.gov{href}"
                                    if href.startswith("/")
                                    else href
                                ),
                                "title": text,
                                **ref_data,
                            }

                except Exception as e:
                    logger.debug(f"Error processing link: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error scraping TOC page: {e}")

        return articles

    def _parse_reference_from_text(self, text: str) -> Dict:
        """
        Parse M21-1 reference from link text.

        Example: "M21-1, Part I, Subpart i, Chapter 1, Section A - Title"
        """
        pattern = r"M21-1.*?Part\s+([IVX]+).*?Subpart\s+([ivx]+).*?Chapter\s+(\d+).*?Section\s+([A-Z])"
        match = re.search(pattern, text, re.IGNORECASE)

        if match:
            part = match.group(1).upper()
            subpart = match.group(2).lower()
            chapter = match.group(3)
            section = match.group(4).upper()

            return {
                "part": part,
                "subpart": subpart,
                "chapter": chapter,
                "section": section,
                "reference": f"{part}.{subpart}.{chapter}.{section}",
            }

        return None

    def save_to_file(self, articles: Dict, filename: str = None):
        """Save discovered articles to JSON file."""
        filename = filename or self.output_file
        filepath = Path(filename)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w") as f:
            json.dump(articles, f, indent=2)

        logger.info(f"Saved {len(articles)} articles to {filepath}")

    def manual_discovery_guide(self):
        """
        Print a guide for manually discovering article IDs.
        """
        print("\n" + "=" * 70)
        print("MANUAL M21-1 ARTICLE ID DISCOVERY GUIDE")
        print("=" * 70)
        print("\nIf automated discovery fails, follow these steps:\n")
        print("1. Open browser and go to:")
        print("   https://www.knowva.ebenefits.va.gov\n")
        print("2. Search for: M21-1 Adjudication Procedures Manual\n")
        print("3. Browse to a specific section you want\n")
        print("4. Look at the URL, which will have this format:")
        print("   .../content/554400000181474/M21-1-Part-I-Subpart-i-...\n")
        print("5. The number after /content/ is the article ID: 554400000181474\n")
        print("6. The reference is in the URL after the ID: Part I, Subpart i, etc.\n")
        print("7. Add to agents/knowva_scraper.py in KNOWN_ARTICLE_IDS dict:")
        print("   'I.i.1.A': '554400000181474',\n")
        print("8. Or create a JSON file with this format:")
        print("""
{
  "I.i.1.A": {
    "article_id": "554400000181474",
    "title": "Duty to Notify and Duty to Assist"
  },
  "I.i.1.B": {
    "article_id": "554400000181476",
    "title": "Due Process"
  }
}
        """)
        print("\n9. Import using:")
        print("   python manage.py scrape_m21 --import-from-file your_file.json")
        print("\n" + "=" * 70 + "\n")


def discover_m21_articles(headless: bool = True, save: bool = True) -> Dict:
    """
    Main function to discover M21-1 articles.

    Args:
        headless: Run browser in headless mode
        save: Save results to file

    Returns:
        Dict of discovered articles
    """
    discoverer = M21ArticleDiscoverer(headless=headless)

    logger.info("Starting M21-1 article discovery...")
    articles = discoverer.discover_all()

    logger.info(f"\nDiscovered {len(articles)} unique M21-1 articles")

    if articles and save:
        discoverer.save_to_file(articles)

    if not articles:
        discoverer.manual_discovery_guide()

    return articles


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Discover M21-1 article IDs from KnowVA"
    )
    parser.add_argument(
        "--no-headless", action="store_true", help="Show browser window"
    )
    parser.add_argument("--output", "-o", help="Output JSON file")
    parser.add_argument(
        "--manual-guide", action="store_true", help="Show manual discovery guide"
    )

    args = parser.parse_args()

    if args.manual_guide:
        discoverer = M21ArticleDiscoverer()
        discoverer.manual_discovery_guide()
        return

    articles = discover_m21_articles(headless=not args.no_headless, save=True)

    if articles:
        print(f"\n✓ Discovered {len(articles)} articles")
        print("✓ Saved to agents/data/discovered_m21_articles.json")
        print("\nUse them with:")
        print(
            "  python manage.py scrape_m21 --import-from-file agents/data/discovered_m21_articles.json"
        )
    else:
        print("\n✗ No articles discovered automatically")
        print("  Run with --manual-guide for instructions on manual discovery")


if __name__ == "__main__":
    main()
