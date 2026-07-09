#!/usr/bin/env python
"""
Analyze M21-1 article ID patterns to discover ranges.

The user discovered that article IDs appear sequential:
- First chapter: 554400000181474, 554400000181468, 554400000181475, ...
- Last chapter: 554400000173308, 554400000173307, 554400000173306

This script analyzes known article IDs to find patterns and generate candidate ranges.
"""

import os
import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "benefits_navigator.settings")
django.setup()

from agents.models import M21ManualSection


def analyze_known_ids():
    """Analyze article IDs we've already scraped."""
    sections = M21ManualSection.objects.all().order_by("article_id")

    print("\n" + "=" * 70)
    print("KNOWN ARTICLE IDs ANALYSIS")
    print("=" * 70)

    article_ids = []
    for section in sections:
        if section.article_id:
            article_ids.append(int(section.article_id))
            print(f"{section.article_id} - {section.reference} - {section.part}")

    if len(article_ids) < 2:
        print("\nNeed at least 2 article IDs to analyze patterns.")
        return

    article_ids.sort()

    print(f"\n{'='*70}")
    print("PATTERN ANALYSIS")
    print("=" * 70)
    print(f"Lowest ID:  {article_ids[0]}")
    print(f"Highest ID: {article_ids[-1]}")
    print(f"Range span: {article_ids[-1] - article_ids[0]:,}")
    print(f"Count: {len(article_ids)}")

    # Calculate gaps
    print("\nGaps between consecutive known IDs:")
    for i in range(len(article_ids) - 1):
        gap = article_ids[i + 1] - article_ids[i]
        print(f"  {article_ids[i]} → {article_ids[i+1]}: +{gap}")

    return article_ids


def analyze_user_provided_ids():
    """Analyze the article IDs the user provided."""
    print("\n" + "=" * 70)
    print("USER-PROVIDED ARTICLE IDs")
    print("=" * 70)

    # First chapter IDs
    first_chapter = [
        554400000181474,
        554400000181468,
        554400000181475,
        554400000181476,
        554400000181477,
        554400000181479,
        554400000181482,
        554400000181483,
        554400000181484,
        554400000301268,
        554400000181485,
        554400000174855,
        554400000174856,
        554400000174858,
        554400000174859,
        554400000174860,
        554400000174861,
    ]

    # Last chapter IDs
    last_chapter = [554400000173308, 554400000173307, 554400000173306]

    print("\nFirst Chapter IDs:")
    first_sorted = sorted(first_chapter)
    for id in first_sorted:
        print(f"  {id}")

    print("\nFirst Chapter Range:")
    print(f"  Min: {min(first_sorted)}")
    print(f"  Max: {max(first_sorted)}")
    print(f"  Span: {max(first_sorted) - min(first_sorted):,}")
    print(f"  Count: {len(first_sorted)}")

    # Note the outlier
    if 554400000301268 in first_chapter:
        print("\n  ⚠️  OUTLIER: 554400000301268 (jumps to 301xxx range)")
        first_sorted_no_outlier = [x for x in first_sorted if x != 554400000301268]
        print("  Without outlier:")
        print(f"    Min: {min(first_sorted_no_outlier)}")
        print(f"    Max: {max(first_sorted_no_outlier)}")
        print(
            f"    Span: {max(first_sorted_no_outlier) - min(first_sorted_no_outlier):,}"
        )

    print("\nLast Chapter IDs:")
    last_sorted = sorted(last_chapter)
    for id in last_sorted:
        print(f"  {id}")

    print("\nLast Chapter Range:")
    print(f"  Min: {min(last_sorted)}")
    print(f"  Max: {max(last_sorted)}")
    print(f"  Span: {max(last_sorted) - min(last_sorted):,}")
    print(f"  Count: {len(last_sorted)}")

    # Overall range
    all_ids = first_sorted + last_sorted
    print(f"\n{'='*70}")
    print("OVERALL RANGE (First + Last chapters)")
    print("=" * 70)
    print(f"  Absolute Min: {min(all_ids)}")
    print(f"  Absolute Max: {max(all_ids)}")
    print(f"  Total Span:   {max(all_ids) - min(all_ids):,}")

    return first_sorted, last_sorted


def suggest_ranges():
    """Suggest ranges to scrape based on analysis."""
    print("\n" + "=" * 70)
    print("SUGGESTED SCRAPING RANGES")
    print("=" * 70)

    # Based on user's data, these seem to be the main ranges
    ranges = [
        {
            "name": "Part VIII (Last) Range",
            "min": 554400000173306,
            "max": 554400000173308,
            "count": 3,
            "description": "User confirmed these are from the last chapter",
        },
        {
            "name": "Part II Range",
            "min": 554400000174855,
            "max": 554400000174873,
            "count": 19,
            "description": "Includes known Part II sections",
        },
        {
            "name": "Part I Range (Lower)",
            "min": 554400000181468,
            "max": 554400000181485,
            "count": 18,
            "description": "Includes known Part I sections",
        },
        {
            "name": "Extended Range (Exploratory)",
            "min": 554400000173000,
            "max": 554400000182000,
            "count": 9000,
            "description": "Full range from last chapter to beyond first chapter",
        },
    ]

    for i, r in enumerate(ranges, 1):
        print(f"\n{i}. {r['name']}")
        print(f"   Range: {r['min']} to {r['max']}")
        print(f"   Expected IDs: ~{r['count']}")
        print(f"   Description: {r['description']}")

        if r["count"] > 100:
            print("   ⚠️  WARNING: Large range - may take hours to scrape")
            print("   Recommend: Break into smaller chunks")

    print(f"\n{'='*70}")
    print("RECOMMENDATIONS")
    print("=" * 70)
    print("""
1. START SMALL: Try range #2 (Part II: 554400000174855-174873)
   - Only ~19 IDs to try
   - Known to contain valid M21 sections
   - Will take ~2-3 minutes

2. THEN TRY: Range #3 (Part I: 554400000181468-181485)
   - Only ~18 IDs to try
   - Covers the first chapter

3. BE AWARE: Not all IDs in a range will be valid M21 sections
   - Some IDs may be deleted/moved articles
   - Some may be non-M21 content
   - Scraper will skip invalid IDs gracefully

4. DON'T START WITH: The full exploratory range (9000 IDs)
   - Would take 7-8 hours with rate limiting
   - Many IDs will be invalid
   - Better to target known ranges first
""")


def main():
    print("\n" + "=" * 70)
    print("M21-1 ARTICLE ID PATTERN ANALYSIS")
    print("=" * 70)

    analyze_known_ids()
    analyze_user_provided_ids()
    suggest_ranges()

    print("\n" + "=" * 70)
    print("NEXT STEPS")
    print("=" * 70)
    print("""
To scrape a range of article IDs:

  python manage.py scrape_m21 --range 554400000174855 554400000174873

Or create a script to try sequential IDs and skip invalid ones.
""")


if __name__ == "__main__":
    main()
