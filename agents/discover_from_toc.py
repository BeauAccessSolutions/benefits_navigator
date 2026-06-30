"""
Discover all M21-1 article IDs by crawling from the Table of Contents page.

Based on GPT analysis:
- TOC page article ID: 554400000073398
- Article IDs are in URLs matching /content/<digits>/
- Topic IDs are in URLs matching /topic/<digits>/

Usage:
    python agents/discover_from_toc.py

Or with Django:
    python manage.py shell
    >>> from agents.discover_from_toc import discover_all_from_toc
    >>> articles = discover_all_from_toc()
"""

import json
import re
import time
import logging
from pathlib import Path
from typing import Dict, Set
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Regex patterns for extracting IDs from URLs
RE_CONTENT = re.compile(r"/content/(\d{12,18})/")
RE_TOPIC = re.compile(r"/topic/(\d{12,18})/")
RE_URL = re.compile(r"https://www\.knowva\.ebenefits\.va\.gov/\S+")

# Known starting points
TOC_ARTICLE_ID = "554400000073398"
PORTAL_ID = "554400000001018"
BASE_URL = "https://www.knowva.ebenefits.va.gov/system/templates/selfservice/va_ssnew/help/customer/locale/en-US/portal"


def extract_knowva_ids(url: str) -> dict:
    """Extract article_id and topic_id from a KnowVA URL."""
    path = urlsplit(url).path

    out = {"article_id": None, "topic_id": None}

    m = RE_CONTENT.search(path)
    if m:
        out["article_id"] = m.group(1)

    m = RE_TOPIC.search(path)
    if m:
        out["topic_id"] = m.group(1)

    return out


def build_content_url(article_id: str) -> str:
    """Build a KnowVA content URL from an article ID."""
    return f"{BASE_URL}/{PORTAL_ID}/content/{article_id}/"


def build_topic_url(topic_id: str) -> str:
    """Build a KnowVA topic URL from a topic ID."""
    return f"{BASE_URL}/{PORTAL_ID}/topic/{topic_id}/"


class M21TOCCrawler:
    """
    Crawl the M21-1 Table of Contents to discover all article IDs.
    """

    def __init__(self, headless: bool = True, rate_limit: float = 1.5):
        self.headless = headless
        self.rate_limit = rate_limit
        self.discovered_articles: Dict[str, dict] = {}
        self.discovered_topics: Set[str] = set()
        self.visited_urls: Set[str] = set()
        self.failed_urls: Set[str] = set()

    def crawl_page(
        self, page, url: str, depth: int = 0, max_depth: int = 3
    ) -> Dict[str, dict]:
        """
        Crawl a single page and extract article IDs from links.

        Args:
            page: Playwright page object
            url: URL to crawl
            depth: Current crawl depth
            max_depth: Maximum depth to crawl

        Returns:
            Dict of discovered articles
        """
        if url in self.visited_urls:
            return {}

        if depth > max_depth:
            logger.debug(f"Max depth reached for {url}")
            return {}

        self.visited_urls.add(url)
        new_articles = {}

        try:
            logger.info(f"[Depth {depth}] Crawling: {url[:80]}...")
            page.goto(url, wait_until="networkidle", timeout=30000)
            time.sleep(self.rate_limit)

            # Get page title for context
            page_title = page.title()

            # Find all links on the page
            links = page.query_selector_all("a[href]")

            urls_to_crawl = []

            for link in links:
                try:
                    href = link.get_attribute("href")
                    text = link.inner_text().strip()

                    if not href:
                        continue

                    # Make absolute URL if needed
                    if href.startswith("/"):
                        href = f"https://www.knowva.ebenefits.va.gov{href}"

                    # Only process KnowVA URLs
                    if "knowva.ebenefits.va.gov" not in href:
                        continue

                    ids = extract_knowva_ids(href)

                    # If it's a content page (article)
                    if (
                        ids["article_id"]
                        and ids["article_id"] not in self.discovered_articles
                    ):
                        article_data = {
                            "article_id": ids["article_id"],
                            "url": href,
                            "title": text,
                            "found_on": url,
                            "depth": depth,
                        }

                        # Try to parse M21-1 reference from title
                        ref_data = self._parse_reference(text)
                        if ref_data:
                            article_data.update(ref_data)

                        new_articles[ids["article_id"]] = article_data
                        self.discovered_articles[ids["article_id"]] = article_data
                        logger.info(
                            f"  Found article: {ids['article_id']} - {text[:50]}..."
                        )

                    # If it's a topic page, queue for crawling
                    if (
                        ids["topic_id"]
                        and ids["topic_id"] not in self.discovered_topics
                    ):
                        self.discovered_topics.add(ids["topic_id"])
                        if href not in self.visited_urls:
                            urls_to_crawl.append(href)

                    # Also crawl content pages that might have sub-links
                    if (
                        ids["article_id"]
                        and "M21-1" in text
                        and href not in self.visited_urls
                    ):
                        urls_to_crawl.append(href)

                except Exception as e:
                    logger.debug(f"Error processing link: {e}")
                    continue

            # Recursively crawl discovered URLs
            for crawl_url in urls_to_crawl[:50]:  # Limit to prevent infinite crawl
                if crawl_url not in self.visited_urls:
                    time.sleep(self.rate_limit)
                    sub_articles = self.crawl_page(
                        page, crawl_url, depth + 1, max_depth
                    )
                    new_articles.update(sub_articles)

        except Exception as e:
            logger.error(f"Error crawling {url}: {e}")
            self.failed_urls.add(url)

        return new_articles

    def _parse_reference(self, text: str) -> dict:
        """Parse M21-1 reference from link text."""
        # Pattern: M21-1, Part I, Subpart i, Chapter 1, Section A - Title
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

        # Try chapter-only pattern (no section)
        chapter_pattern = (
            r"M21-1.*?Part\s+([IVX]+).*?Subpart\s+([ivx]+).*?Chapter\s+(\d+)"
        )
        match = re.search(chapter_pattern, text, re.IGNORECASE)

        if match:
            part = match.group(1).upper()
            subpart = match.group(2).lower()
            chapter = match.group(3)

            return {
                "part": part,
                "subpart": subpart,
                "chapter": chapter,
                "section": "",
                "reference": f"{part}.{subpart}.{chapter}",
            }

        return None

    def discover_all(self) -> Dict[str, dict]:
        """
        Discover all M21-1 articles starting from the TOC page.

        Returns:
            Dict mapping article_id to article data
        """
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self.headless)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = context.new_page()

            # Start from the TOC page
            toc_url = build_content_url(TOC_ARTICLE_ID)
            logger.info(f"Starting discovery from TOC: {toc_url}")

            self.crawl_page(page, toc_url, depth=0, max_depth=4)

            # Also try topic pages for M21-1
            topic_urls = [
                f"{BASE_URL}/{PORTAL_ID}/topic/554400000001141",  # M21-1 topic
                f"{BASE_URL}/{PORTAL_ID}/topic/554400000004049",  # Another M21-1 topic
            ]

            for topic_url in topic_urls:
                if topic_url not in self.visited_urls:
                    logger.info(f"Crawling topic page: {topic_url}")
                    self.crawl_page(page, topic_url, depth=0, max_depth=3)

            browser.close()

        return self.discovered_articles

    def save_results(self, filename: str = "agents/data/toc_discovered_articles.json"):
        """Save discovered articles to JSON file."""
        filepath = Path(filename)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # Convert to scraper-compatible format
        output = {
            "article_ids": list(self.discovered_articles.keys()),
            "articles": self.discovered_articles,
            "_metadata": {
                "total_articles": len(self.discovered_articles),
                "total_topics": len(self.discovered_topics),
                "pages_visited": len(self.visited_urls),
                "failed_urls": len(self.failed_urls),
                "discovery_method": "TOC crawling",
            },
        }

        with open(filepath, "w") as f:
            json.dump(output, f, indent=2)

        logger.info(f"Saved {len(self.discovered_articles)} articles to {filepath}")
        return filepath


def discover_all_from_toc(headless: bool = True, save: bool = True) -> Dict[str, dict]:
    """
    Main function to discover all M21-1 articles from TOC.

    Args:
        headless: Run browser in headless mode
        save: Save results to file

    Returns:
        Dict of discovered articles
    """
    crawler = M21TOCCrawler(headless=headless, rate_limit=1.5)

    logger.info("Starting M21-1 TOC discovery...")
    articles = crawler.discover_all()

    logger.info("\n=== Discovery Complete ===")
    logger.info(f"Total articles discovered: {len(articles)}")
    logger.info(f"Total topics found: {len(crawler.discovered_topics)}")
    logger.info(f"Pages visited: {len(crawler.visited_urls)}")

    if save:
        filepath = crawler.save_results()
        logger.info("\nTo scrape all discovered articles:")
        logger.info(f"  python manage.py scrape_m21 --import-from-file {filepath}")

    return articles


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Discover M21-1 articles from TOC")
    parser.add_argument(
        "--no-headless", action="store_true", help="Show browser window"
    )
    parser.add_argument(
        "--output",
        "-o",
        default="agents/data/toc_discovered_articles.json",
        help="Output JSON file",
    )

    args = parser.parse_args()

    articles = discover_all_from_toc(headless=not args.no_headless, save=True)

    if articles:
        print(f"\n✓ Discovered {len(articles)} articles")
        print("✓ Saved to agents/data/toc_discovered_articles.json")
        print("\nTo scrape all discovered articles:")
        print(
            "  python manage.py scrape_m21 --import-from-file agents/data/toc_discovered_articles.json"
        )
    else:
        print("\n✗ No articles discovered")


if __name__ == "__main__":
    main()
