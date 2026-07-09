#!/usr/bin/env python
"""
Quick status check for M21 scraper.

Usage:
    python check_m21_status.py
"""

import os
import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "benefits_navigator.settings")
django.setup()

from agents.models import M21ManualSection, M21ScrapeJob, M21TopicIndex


def main():
    print("\n" + "=" * 60)
    print("M21 SCRAPER STATUS")
    print("=" * 60)

    # Check sections
    section_count = M21ManualSection.objects.count()
    print(f"\n📄 Scraped Sections: {section_count}")

    if section_count > 0:
        print("\n   Latest sections:")
        for section in M21ManualSection.objects.order_by("-last_scraped")[:5]:
            print(f"   • {section.reference} - {section.title[:50]}...")

    # Check scrape jobs
    job_count = M21ScrapeJob.objects.count()
    print(f"\n🔄 Scrape Jobs: {job_count}")

    if job_count > 0:
        latest_job = M21ScrapeJob.objects.order_by("-created_at").first()
        print(f"\n   Latest job (ID {latest_job.id}):")
        print(f"   • Status: {latest_job.status}")
        print(
            f"   • Completed: {latest_job.sections_completed}/{latest_job.total_sections}"
        )
        print(f"   • Failed: {latest_job.sections_failed}")
        if latest_job.duration_seconds:
            print(f"   • Duration: {latest_job.duration_seconds}s")

    # Check topic indices
    topic_count = M21TopicIndex.objects.count()
    print(f"\n🏷️  Topic Indices: {topic_count}")

    if topic_count > 0:
        print("\n   Topics:")
        for topic in M21TopicIndex.objects.order_by("-priority")[:5]:
            count = topic.sections.count()
            print(f"   • {topic.title}: {count} sections")

    # Database info
    print(f"\n💾 Database: {django.conf.settings.DATABASES['default']['NAME']}")

    print("\n" + "=" * 60)

    # Recommendations
    if section_count == 0:
        print("\n📝 Next step: Scrape some content!")
        print(
            "   python manage.py scrape_m21 --import-from-file agents/data/starter_article_ids.json"
        )
    elif section_count < 10:
        print("\n📝 Next step: Scrape more content!")
        print("   python manage.py scrape_m21 --all")
    else:
        print("\n✅ You have scraped content! View it in Django admin:")
        print("   python manage.py runserver")
        print("   Visit: http://localhost:8000/admin")

    if topic_count == 0 and section_count > 0:
        print("\n💡 Tip: Build topic indices for better AI integration")
        print("   python manage.py shell")
        print("   >>> from agents.tasks import build_m21_topic_indices")
        print("   >>> build_m21_topic_indices()")

    print("")


if __name__ == "__main__":
    main()
