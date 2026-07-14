"""
Celery tasks for document processing
"""

import time
import logging
from celery import shared_task
from django.utils import timezone

from .models import Document
from .services.ocr_service import OCRService
from .services.ai_service import AIService

logger = logging.getLogger(__name__)


class AIConsentError(Exception):
    """Raised when user has not consented to AI processing."""

    pass


def verify_ai_consent(user) -> bool:
    """
    Verify that a user has consented to AI processing.

    This is a defense-in-depth check. Consent should also be verified
    at the view/form level before tasks are queued.

    Args:
        user: User instance to check

    Returns:
        True if user has consented, False otherwise

    Raises:
        AIConsentError: If user has not consented (for use in tasks)
    """
    if not user:
        return False

    try:
        profile = user.profile
        return bool(profile.ai_processing_consent)
    except Exception:
        # No profile or profile access error
        return False


def require_ai_consent(user):
    """
    Require AI consent or raise an error.

    Use this in tasks to enforce consent before processing.

    Args:
        user: User instance to check

    Raises:
        AIConsentError: If user has not consented
    """
    if not verify_ai_consent(user):
        raise AIConsentError(
            f"User {user.id if user else 'unknown'} has not consented to AI processing. "
            "AI analysis cannot proceed without consent."
        )


@shared_task(bind=True, max_retries=3, acks_late=True)
def process_document_task(self, document_id):
    """
    Async task to process uploaded document:
    1. Extract text via OCR
    2. Analyze with AI
    3. Save results

    This task is accessible-aware: it updates status fields that
    are announced to screen readers via ARIA live regions

    SECURITY: Requires user to have consented to AI processing.
    """
    start_time = time.time()

    try:
        # Get document
        document = Document.objects.get(id=document_id)

        # SECURITY: Verify AI consent before processing
        require_ai_consent(document.user)

        document.mark_processing()

        logger.info(f"Starting OCR processing for document {document_id}")

        # Step 1: OCR Processing
        ocr_service = OCRService()
        ocr_result = ocr_service.extract_text(document.file.path)

        # Keep OCR text in memory for passing to AI service
        ocr_text = ocr_result["text"]
        ocr_length = len(ocr_text)

        # Update document with OCR metadata (no raw text stored for PHI protection)
        document.ocr_confidence = ocr_result.get("confidence", None)
        document.page_count = ocr_result.get("page_count", 0)
        document.ocr_status = "completed"
        document.ocr_length = ocr_length
        document.save(
            update_fields=["ocr_confidence", "page_count", "ocr_status", "ocr_length"]
        )

        logger.info(
            f"OCR complete for document {document_id}. Extracted {ocr_length} characters"
        )

        # Step 2: AI Analysis
        document.mark_analyzing()
        logger.info(f"Starting AI analysis for document {document_id}")

        ai_service = AIService()
        # Pass OCR text directly from memory (not from document.ocr_text)
        ai_result = ai_service.analyze_document(
            text=ocr_text, document_type=document.document_type
        )

        document.ai_summary = ai_result["analysis"]
        document.ai_model_used = ai_result["model"]
        document.ai_tokens_used = ai_result["tokens_used"]
        document.save(update_fields=["ai_summary", "ai_model_used", "ai_tokens_used"])

        # Calculate processing duration
        duration = time.time() - start_time
        document.mark_completed(duration=duration)

        logger.info(
            f"Document {document_id} processed successfully in {duration:.2f} seconds"
        )

        # Send email notification (async)
        try:
            from core.tasks import send_document_analysis_complete_email

            send_document_analysis_complete_email.delay(document_id)
        except Exception as e:
            logger.warning(
                f"Failed to queue email notification for document {document_id}: {e}"
            )

        return {
            "document_id": document_id,
            "status": "completed",
            "duration": duration,
            "ocr_length": ocr_length,
            "tokens_used": document.ai_tokens_used,
        }

    except Document.DoesNotExist:
        logger.error(f"Document {document_id} not found")
        raise

    except AIConsentError as exc:
        # Don't retry on consent errors - this is a permanent failure
        logger.error(f"AI consent not granted for document {document_id}: {str(exc)}")
        try:
            document = Document.objects.get(id=document_id)
            document.mark_failed(
                "AI processing consent required. Please enable AI processing in your privacy settings."
            )
        except Exception as e:
            logger.error(f"Failed to update document status: {str(e)}")
        # Don't retry - consent must be granted first
        raise

    except Exception as exc:
        logger.error(
            f"Error processing document {document_id}: {str(exc)}", exc_info=True
        )

        # Determine if this was an OCR failure (for ocr_status tracking)
        is_ocr_failure = "ocr" in str(exc).lower() or "extract" in str(exc).lower()

        # Try to update document status
        try:
            document = Document.objects.get(id=document_id)
            error_message = f"Processing failed: {str(exc)}"
            document.mark_failed(error_message, ocr_failed=is_ocr_failure)
        except Exception as e:
            logger.error(f"Failed to update document status: {str(e)}")

        # Record failure for health monitoring
        try:
            import traceback
            from core.models import ProcessingFailure

            ProcessingFailure.record_failure(
                failure_type="ocr" if is_ocr_failure else "document_processing",
                error_message=str(exc),
                stack_trace=traceback.format_exc(),
                document_id=str(document_id),
                task_id=self.request.id,
            )
        except Exception as e:
            logger.error(f"Failed to record processing failure: {str(e)}")

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@shared_task(bind=True, max_retries=3, acks_late=True)
def decode_denial_letter_task(self, document_id, user_id=None):
    """
    Complete denial decoding pipeline:
    1. OCR extraction (if not already done)
    2. Decision letter analysis (extract denied conditions)
    3. M21 matching (find relevant manual sections)
    4. Evidence guidance generation

    Creates DecisionLetterAnalysis and DenialDecoding records.

    SECURITY: Requires user to have consented to AI processing.
    """
    from agents.models import AgentInteraction, DecisionLetterAnalysis, DenialDecoding
    from agents.services import DecisionLetterAnalyzer, DenialDecoderService

    start_time = time.time()

    try:
        # Get document
        document = Document.objects.get(id=document_id)
        user = document.user

        # SECURITY: Verify AI consent before processing
        require_ai_consent(user)

        # Step 1: OCR extraction (ephemeral - always extract fresh from file)
        document.mark_processing()
        logger.info(f"Starting OCR for denial letter {document_id}")

        ocr_service = OCRService()
        ocr_result = ocr_service.extract_text(document.file.path)

        # Keep OCR text in memory only (not persisted for PHI protection)
        ocr_text = ocr_result["text"]
        ocr_length = len(ocr_text)

        # Update document with OCR metadata (no raw text stored)
        document.ocr_confidence = ocr_result.get("confidence", None)
        document.page_count = ocr_result.get("page_count", 0)
        document.ocr_status = "completed"
        document.ocr_length = ocr_length
        document.save(
            update_fields=["ocr_confidence", "page_count", "ocr_status", "ocr_length"]
        )

        logger.info(f"OCR complete: {ocr_length} characters")

        # Step 2: Decision Letter Analysis
        document.mark_analyzing()
        logger.info(f"Analyzing decision letter {document_id}")

        analyzer = DecisionLetterAnalyzer()
        # Pass OCR text from memory variable
        analysis_result = analyzer.analyze(ocr_text)

        # Create interaction record
        interaction = AgentInteraction.objects.create(
            user=user,
            agent_type="decision_analyzer",
            status="completed",
            tokens_used=analysis_result.get("_tokens_used", 0),
            cost_estimate=analysis_result.get("_cost_estimate", 0),
        )

        # Create analysis record (raw_text removed for PHI protection)
        analysis = DecisionLetterAnalysis.objects.create(
            interaction=interaction,
            user=user,
            document=document,
            decision_date=_parse_date(analysis_result.get("decision_date")),
            conditions_granted=analysis_result.get("conditions_granted", []),
            conditions_denied=analysis_result.get("conditions_denied", []),
            conditions_deferred=analysis_result.get("conditions_deferred", []),
            summary=analysis_result.get("summary", ""),
            appeal_options=analysis_result.get("appeal_options", []),
            evidence_issues=analysis_result.get("evidence_issues", []),
            action_items=analysis_result.get("action_items", []),
            appeal_deadline=_parse_date(analysis_result.get("appeal_deadline")),
        )

        logger.info(
            f"Analysis complete: {len(analysis_result.get('conditions_denied', []))} denied conditions"
        )

        # Step 3: Denial Decoding (M21 matching + evidence guidance)
        denied_conditions = analysis_result.get("conditions_denied", [])

        if denied_conditions:
            logger.info(f"Decoding {len(denied_conditions)} denials with M21 matching")

            decoder = DenialDecoderService()
            denial_mappings, evidence_strategy, m21_sections_searched = (
                decoder.decode_all_denials(denied_conditions)
            )

            # Create priority order based on critical evidence count
            priority_order = sorted(
                range(len(denial_mappings)),
                key=lambda i: sum(
                    1
                    for e in denial_mappings[i].get("required_evidence", [])
                    if e.get("priority") == "critical"
                ),
                reverse=True,
            )

            # Create decoding record
            decoding = DenialDecoding.objects.create(
                analysis=analysis,
                denial_mappings=denial_mappings,
                evidence_strategy=evidence_strategy,
                priority_order=priority_order,
                m21_sections_searched=m21_sections_searched,
                processing_time_seconds=time.time() - start_time,
            )

            logger.info(
                f"Denial decoding complete: {m21_sections_searched} M21 sections searched"
            )
        else:
            logger.info("No denied conditions to decode")
            decoding = None

        # Mark document complete
        duration = time.time() - start_time
        document.mark_completed(duration=duration)

        # Send email notification (async)
        try:
            from core.tasks import send_document_analysis_complete_email

            send_document_analysis_complete_email.delay(document_id)
        except Exception as e:
            logger.warning(
                f"Failed to queue email notification for document {document_id}: {e}"
            )

        return {
            "document_id": document_id,
            "analysis_id": analysis.id,
            "decoding_id": decoding.id if decoding else None,
            "denied_count": len(denied_conditions),
            "status": "completed",
            "duration": duration,
        }

    except Document.DoesNotExist:
        logger.error(f"Document {document_id} not found")
        raise

    except AIConsentError as exc:
        # Don't retry on consent errors - this is a permanent failure
        logger.error(f"AI consent not granted for document {document_id}: {str(exc)}")
        try:
            document = Document.objects.get(id=document_id)
            document.mark_failed(
                "AI processing consent required. Please enable AI processing in your privacy settings."
            )
        except Exception as e:
            logger.error(f"Failed to update document status: {str(e)}")
        # Don't retry - consent must be granted first
        raise

    except Exception as exc:
        logger.error(
            f"Error decoding denial letter {document_id}: {str(exc)}", exc_info=True
        )

        # Determine if this was an OCR failure
        is_ocr_failure = "ocr" in str(exc).lower() or "extract" in str(exc).lower()

        try:
            document = Document.objects.get(id=document_id)
            document.mark_failed(
                f"Decoding failed: {str(exc)}", ocr_failed=is_ocr_failure
            )
        except Exception as e:
            logger.error(f"Failed to update document status: {str(e)}")

        # Record failure for health monitoring
        try:
            import traceback
            from core.models import ProcessingFailure

            ProcessingFailure.record_failure(
                failure_type="ocr" if is_ocr_failure else "ai_analysis",
                error_message=str(exc),
                stack_trace=traceback.format_exc(),
                document_id=str(document_id),
                task_id=self.request.id,
            )
        except Exception as e:
            logger.error(f"Failed to record processing failure: {str(e)}")

        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


@shared_task(bind=True, max_retries=3, acks_late=True)
def analyze_rating_decision_task(
    self, document_id, user_id=None, use_simple_format=False
):
    """
    Analyze a VA rating decision document for actionable insights.

    This task provides enhanced analysis beyond basic extraction:
    1. OCR extraction (if not already done)
    2. Structured data extraction (conditions, ratings, dates)
    3. Strategic analysis (increase opportunities, secondary conditions, errors)
    4. Priority action recommendations

    Creates RatingAnalysis record with comprehensive insights.

    Args:
        document_id: ID of the uploaded Document
        user_id: Optional user ID (defaults to document owner)
        use_simple_format: If True, generate markdown instead of structured JSON

    SECURITY: Requires user to have consented to AI processing.
    """
    from agents.models import AgentInteraction, RatingAnalysis
    from claims.services.rating_analysis_service import (
        RatingDecisionAnalyzer,
        SimpleRatingAnalyzer,
    )

    start_time = time.time()

    try:
        # Get document
        document = Document.objects.get(id=document_id)
        user = document.user

        # SECURITY: Verify AI consent before processing
        require_ai_consent(user)

        # Step 1: OCR extraction (ephemeral - always extract fresh from file)
        document.mark_processing()
        logger.info(f"Starting OCR for rating decision {document_id}")

        ocr_service = OCRService()
        ocr_result = ocr_service.extract_text(document.file.path)

        # Keep OCR text in memory only (not persisted for PHI protection)
        ocr_text = ocr_result["text"]
        ocr_length = len(ocr_text)

        # Update document with OCR metadata (no raw text stored)
        document.ocr_confidence = ocr_result.get("confidence", None)
        document.page_count = ocr_result.get("page_count", 0)
        document.ocr_status = "completed"
        document.ocr_length = ocr_length
        document.save(
            update_fields=["ocr_confidence", "page_count", "ocr_status", "ocr_length"]
        )

        logger.info(f"OCR complete: {ocr_length} characters")

        # Step 2: Analyze the rating decision
        document.mark_analyzing()
        logger.info(f"Analyzing rating decision {document_id}")

        if use_simple_format:
            # Simple markdown format
            analyzer = SimpleRatingAnalyzer()
            # Pass OCR text from memory variable
            markdown_analysis, tokens_used = analyzer.analyze(ocr_text)

            # Create interaction record
            interaction = AgentInteraction.objects.create(
                user=user,
                agent_type="rating_analyzer",
                status="completed",
                tokens_used=tokens_used,
                cost_estimate=analyzer.estimate_cost(tokens_used),
            )

            # Create analysis record with markdown (raw_text removed for PHI protection)
            analysis = RatingAnalysis.objects.create(
                interaction=interaction,
                user=user,
                document=document,
                markdown_analysis=markdown_analysis,
                tokens_used=tokens_used,
                cost_estimate=analyzer.estimate_cost(tokens_used),
                processing_time_seconds=time.time() - start_time,
            )

        else:
            # Full structured analysis
            analyzer = RatingDecisionAnalyzer()
            # Pass OCR text from memory variable
            result = analyzer.analyze(ocr_text)

            # Create interaction record
            interaction = AgentInteraction.objects.create(
                user=user,
                agent_type="rating_analyzer",
                status="completed",
                tokens_used=result.tokens_used,
                cost_estimate=result.cost_estimate,
            )

            # Parse decision date from extracted data
            decision_date = _parse_date(result.extracted_data.get("decision_date"))

            # Create analysis record with full structured data (raw_text removed for PHI protection)
            analysis = RatingAnalysis.objects.create(
                interaction=interaction,
                user=user,
                document=document,
                decision_date=decision_date,
                veteran_name=result.extracted_data.get("veteran_name", ""),
                file_number=result.extracted_data.get("file_number", ""),
                combined_rating=result.extracted_data.get("combined_rating"),
                monthly_compensation=result.extracted_data.get("monthly_compensation"),
                conditions=result.extracted_data.get("conditions", []),
                evidence_list=result.extracted_data.get("evidence_list", []),
                increase_opportunities=result.analysis.get(
                    "increase_opportunities", []
                ),
                secondary_conditions=result.analysis.get("secondary_conditions", []),
                rating_errors=result.analysis.get("rating_errors", []),
                effective_date_issues=result.analysis.get("effective_date_issues", []),
                deadline_tracker=result.analysis.get("deadline_tracker", {}),
                benefits_unlocked=result.analysis.get("benefits_unlocked", []),
                exam_prep_tips=result.analysis.get("exam_prep_tips", []),
                priority_actions=result.analysis.get("priority_actions", []),
                tokens_used=result.tokens_used,
                cost_estimate=result.cost_estimate,
                processing_time_seconds=time.time() - start_time,
            )

        logger.info(f"Rating analysis complete for document {document_id}")

        # Mark document complete
        duration = time.time() - start_time
        document.mark_completed(duration=duration)

        # Send email notification (async)
        try:
            from core.tasks import send_document_analysis_complete_email

            send_document_analysis_complete_email.delay(document_id)
        except Exception as e:
            logger.warning(
                f"Failed to queue email notification for document {document_id}: {e}"
            )

        return {
            "document_id": document_id,
            "analysis_id": analysis.id,
            "combined_rating": analysis.combined_rating,
            "condition_count": analysis.condition_count,
            "increase_opportunities": analysis.increase_opportunity_count,
            "secondary_conditions": analysis.secondary_condition_count,
            "status": "completed",
            "duration": duration,
        }

    except Document.DoesNotExist:
        logger.error(f"Document {document_id} not found")
        raise

    except AIConsentError as exc:
        # Don't retry on consent errors - this is a permanent failure
        logger.error(f"AI consent not granted for document {document_id}: {str(exc)}")
        try:
            document = Document.objects.get(id=document_id)
            document.mark_failed(
                "AI processing consent required. Please enable AI processing in your privacy settings."
            )
        except Exception as e:
            logger.error(f"Failed to update document status: {str(e)}")
        # Don't retry - consent must be granted first
        raise

    except Exception as exc:
        logger.error(
            f"Error analyzing rating decision {document_id}: {str(exc)}", exc_info=True
        )

        # Determine if this was an OCR failure
        is_ocr_failure = "ocr" in str(exc).lower() or "extract" in str(exc).lower()

        try:
            document = Document.objects.get(id=document_id)
            document.mark_failed(
                f"Rating analysis failed: {str(exc)}", ocr_failed=is_ocr_failure
            )
        except Exception as e:
            logger.error(f"Failed to update document status: {str(e)}")

        # Record failure for health monitoring
        try:
            import traceback
            from core.models import ProcessingFailure

            ProcessingFailure.record_failure(
                failure_type="ocr" if is_ocr_failure else "ai_analysis",
                error_message=str(exc),
                stack_trace=traceback.format_exc(),
                document_id=str(document_id),
                task_id=self.request.id,
            )
        except Exception as e:
            logger.error(f"Failed to record processing failure: {str(e)}")

        raise self.retry(exc=exc, countdown=60 * (2**self.request.retries))


def _parse_date(date_str):
    """Parse date string to date object."""
    if not date_str:
        return None
    try:
        from datetime import datetime

        if isinstance(date_str, str):
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        return date_str
    except (ValueError, TypeError):
        return None


@shared_task(acks_late=True)
def cleanup_old_documents():
    """
    Periodic task to clean up old soft-deleted documents
    Can be scheduled via Celery Beat

    Uses acks_late so a worker crash mid-purge redelivers the task rather
    than acking it early and leaving user data retained until the next run
    (project rule: user-data tasks must use late acknowledgement). The body
    is idempotent under redelivery: it re-queries soft-deleted docs past the
    threshold and tolerates already-missing files.
    """
    from datetime import timedelta

    threshold_date = timezone.now() - timedelta(days=90)

    # Use all_objects to find soft-deleted documents (objects manager excludes them)
    deleted_docs = Document.all_objects.filter(
        is_deleted=True, deleted_at__lt=threshold_date
    )

    count = deleted_docs.count()

    # Permanently delete each document (hard_delete is an instance method)
    for doc in deleted_docs:
        try:
            # Delete the file from storage if it exists
            if doc.file:
                doc.file.delete(save=False)
            doc.hard_delete()
        except Exception as e:
            logger.error(f"Failed to hard delete document {doc.id}: {e}")

    logger.info(f"Cleaned up {count} old documents")
    return f"Cleaned up {count} documents"
