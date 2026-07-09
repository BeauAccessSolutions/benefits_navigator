"""
Celery tasks for AI agents and M21 scraping.

Tasks:
- M21 scraping (scheduled and on-demand)
- Topic index building
- Agent content processing
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone
from django.db import transaction

from agents.models import M21ManualSection, M21ScrapeJob, M21TopicIndex
from agents.knowva_scraper import KnowVAScraper, KNOWN_ARTICLE_IDS

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def scrape_m21_section(self, article_id: str, force_update: bool = False):
    """
    Scrape a single M21-1 section.

    Args:
        article_id: KnowVA article ID
        force_update: Whether to update if already exists

    Returns:
        Dict with status and section_id if successful
    """
    logger.info(f"Starting M21 scrape task for article {article_id}")

    try:
        # Check if exists and skip if not forcing
        if not force_update:
            existing = M21ManualSection.objects.filter(article_id=article_id).first()
            if existing:
                logger.info(
                    f"Article {article_id} already exists (ref: {existing.reference}), skipping"
                )
                return {
                    "status": "skipped",
                    "reason": "already_exists",
                    "section_id": existing.id,
                }

        # Scrape
        scraper = KnowVAScraper(headless=True, rate_limit=3.0)
        data = scraper.scrape_section(article_id)

        if not data:
            logger.error(f"Failed to scrape article {article_id}")
            return {"status": "failed", "reason": "no_data_returned"}

        # Save to database
        section = _save_section_data(data, force_update)

        if section:
            logger.info(
                f"Successfully scraped and saved article {article_id}: {section.reference}"
            )
            return {
                "status": "success",
                "section_id": section.id,
                "reference": section.reference,
                "title": section.title,
            }
        else:
            logger.error(f"Failed to save section for article {article_id}")
            return {"status": "failed", "reason": "save_failed"}

    except Exception as e:
        logger.error(
            f"Error in scrape_m21_section for article {article_id}: {e}", exc_info=True
        )

        # Retry with exponential backoff
        retry_delay = 60 * (2**self.request.retries)  # 1min, 2min, 4min
        raise self.retry(exc=e, countdown=retry_delay)


@shared_task
def scrape_m21_bulk(article_ids: list, force_update: bool = False):
    """
    Scrape multiple M21-1 sections in bulk.

    Args:
        article_ids: List of KnowVA article IDs
        force_update: Whether to update existing sections

    Returns:
        Dict with summary of results
    """
    logger.info(f"Starting bulk M21 scrape for {len(article_ids)} articles")

    # Create scrape job
    scrape_job = M21ScrapeJob.objects.create(
        status="running",
        force_update=force_update,
        total_sections=len(article_ids),
        started_at=timezone.now(),
    )

    successful = 0
    failed = 0
    skipped = 0
    errors = []

    scraper = KnowVAScraper(headless=True, rate_limit=3.0)

    for article_id in article_ids:
        try:
            # Check if exists
            if not force_update:
                existing = M21ManualSection.objects.filter(
                    article_id=article_id
                ).first()
                if existing:
                    skipped += 1
                    scrape_job.sections_completed += 1
                    scrape_job.save()
                    continue

            # Scrape
            data = scraper.scrape_section(article_id)

            if not data:
                failed += 1
                scrape_job.sections_failed += 1
                errors.append(f"Article {article_id}: No data returned")
                continue

            # Save
            section = _save_section_data(data, force_update)

            if section:
                successful += 1
                scrape_job.sections_completed += 1
            else:
                failed += 1
                scrape_job.sections_failed += 1
                errors.append(f"Article {article_id}: Save failed")

        except Exception as e:
            logger.error(f"Error scraping article {article_id}: {e}", exc_info=True)
            failed += 1
            scrape_job.sections_failed += 1
            errors.append(f"Article {article_id}: {str(e)}")

        scrape_job.save()

    # Finalize job
    scrape_job.completed_at = timezone.now()
    duration = (scrape_job.completed_at - scrape_job.started_at).total_seconds()
    scrape_job.duration_seconds = int(duration)

    if failed == 0:
        scrape_job.status = "completed"
    elif successful > 0:
        scrape_job.status = "partial"
    else:
        scrape_job.status = "failed"

    scrape_job.summary = {
        "total": len(article_ids),
        "successful": successful,
        "failed": failed,
        "skipped": skipped,
    }
    scrape_job.error_log = "\n".join(errors)
    scrape_job.save()

    logger.info(
        f"Bulk scrape complete: {successful} success, {failed} failed, {skipped} skipped"
    )

    return {
        "job_id": scrape_job.id,
        "successful": successful,
        "failed": failed,
        "skipped": skipped,
        "duration": duration,
    }


@shared_task
def scrape_m21_all_known():
    """
    Scrape all known M21-1 articles.

    Scheduled task that runs periodically to keep content updated.
    """
    article_ids = list(KNOWN_ARTICLE_IDS.values())
    return scrape_m21_bulk(article_ids, force_update=False)


@shared_task
def update_stale_m21_sections(days_old: int = 30):
    """
    Update M21 sections that haven't been updated in X days.

    Args:
        days_old: Number of days after which a section is considered stale
    """
    cutoff_date = timezone.now() - timedelta(days=days_old)

    stale_sections = M21ManualSection.objects.filter(
        last_scraped__lt=cutoff_date, article_id__isnull=False
    ).values_list("article_id", flat=True)

    stale_ids = list(stale_sections)

    if stale_ids:
        logger.info(f"Updating {len(stale_ids)} stale M21 sections")
        return scrape_m21_bulk(stale_ids, force_update=True)
    else:
        logger.info("No stale M21 sections to update")
        return {"status": "no_updates_needed"}


@shared_task
def build_m21_topic_indices():
    """
    Build/rebuild topic-based indices for M21 sections.

    Scans all M21 sections and associates them with topics based on keywords.
    """
    logger.info("Building M21 topic indices")

    # Get or create topic indices
    topic_configs = [
        {
            "topic": "service_connection",
            "title": "Service Connection",
            "description": "How VA establishes service connection for disabilities",
            "keywords": [
                "service connection",
                "service-connection",
                "nexus",
                "in-service",
                "direct service",
                "secondary service",
                "presumptive",
                "aggravation",
            ],
            "priority": 100,
        },
        {
            "topic": "rating_process",
            "title": "Rating Process",
            "description": "How VA rates disabilities and assigns percentages",
            "keywords": [
                "rating",
                "evaluation",
                "diagnostic code",
                "schedule for rating",
                "percentage",
                "combined rating",
            ],
            "priority": 90,
        },
        {
            "topic": "evidence",
            "title": "Evidence Requirements",
            "description": "What evidence VA needs and how it weighs evidence",
            "keywords": [
                "evidence",
                "medical records",
                "lay evidence",
                "buddy statement",
                "nexus letter",
                "weighing evidence",
                "credibility",
            ],
            "priority": 85,
        },
        {
            "topic": "examinations",
            "title": "C&P Examinations",
            "description": "Compensation & Pension exam procedures",
            "keywords": [
                "examination",
                "C&P",
                "DBQ",
                "medical opinion",
                "examiner",
                "exam request",
            ],
            "priority": 80,
        },
        {
            "topic": "effective_dates",
            "title": "Effective Dates",
            "description": "How VA determines effective dates for benefits",
            "keywords": [
                "effective date",
                "date of claim",
                "date entitlement",
                "earlier effective date",
            ],
            "priority": 75,
        },
        {
            "topic": "tdiu",
            "title": "TDIU - Individual Unemployability",
            "description": "Unemployability due to service-connected disabilities",
            "keywords": [
                "TDIU",
                "unemployability",
                "individual unemployability",
                "unable to work",
                "substantially gainful",
            ],
            "priority": 70,
        },
        {
            "topic": "special_monthly_compensation",
            "title": "Special Monthly Compensation (SMC)",
            "description": "Additional compensation for severe disabilities",
            "keywords": [
                "special monthly compensation",
                "SMC",
                "aid and attendance",
                "housebound",
            ],
            "priority": 65,
        },
    ]

    updated_count = 0

    for config in topic_configs:
        topic_index, created = M21TopicIndex.objects.get_or_create(
            topic=config["topic"],
            defaults={
                "title": config["title"],
                "description": config["description"],
                "keywords": config["keywords"],
                "priority": config["priority"],
            },
        )

        if not created:
            # Update if changed
            topic_index.title = config["title"]
            topic_index.description = config["description"]
            topic_index.keywords = config["keywords"]
            topic_index.priority = config["priority"]
            topic_index.save()

        # Clear existing associations
        topic_index.sections.clear()

        # Find matching sections
        keywords_lower = [k.lower() for k in config["keywords"]]

        for section in M21ManualSection.objects.all():
            # Build searchable text
            search_text = " ".join(
                [section.title, section.overview, section.content]
            ).lower()

            # Check for keyword matches
            for keyword in keywords_lower:
                if keyword in search_text:
                    topic_index.sections.add(section)
                    break

        section_count = topic_index.sections.count()
        logger.info(f"Topic '{config['title']}': {section_count} sections")
        updated_count += 1

    logger.info(f"Built {updated_count} topic indices")

    return {"status": "success", "topics_updated": updated_count}


@transaction.atomic
def _save_section_data(data: dict, force_update: bool = False):
    """
    Helper function to save scraped section data.

    Args:
        data: Scraped section data
        force_update: Whether to update existing records

    Returns:
        M21ManualSection instance or None
    """
    section_data = {
        "article_id": data.get("article_id"),
        "knowva_url": data.get("url"),
        "title": data.get("section_title") or data.get("title", "Unknown"),
        "content": data.get("content", ""),
        "overview": data.get("overview", ""),
        "topics": data.get("topics", []),
        "references": data.get("references", []),
        "scrape_status": "success",
        "scrape_error": "",
    }

    if data.get("reference"):
        section_data.update(
            {
                "part": data.get("part", ""),
                "part_number": data.get("part_number", 0),
                "part_title": data.get("part_title", ""),
                "subpart": data.get("subpart", ""),
                "chapter": data.get("chapter", ""),
                "section": data.get("section", ""),
                "reference": data.get("reference"),
                "full_reference": data.get("full_reference", ""),
            }
        )

    if data.get("article_id"):
        section, created = M21ManualSection.objects.update_or_create(
            article_id=data["article_id"], defaults=section_data
        )
    elif data.get("reference"):
        section, created = M21ManualSection.objects.update_or_create(
            reference=data["reference"], defaults=section_data
        )
    else:
        section = M21ManualSection.objects.create(**section_data)

    return section
