"""
Views for claims app - Document upload and management
"""

import os
import mimetypes
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, FileResponse, Http404, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django.conf import settings
from django_ratelimit.decorators import ratelimit

from core.models import AuditLog
from agents.views import require_ai_consent_view
from .models import Document
from .forms import DocumentUploadForm, DenialLetterUploadForm
from .tasks import (
    process_document_task,
    decode_denial_letter_task,
    analyze_rating_decision_task,
)


@login_required
def document_list(request):
    """
    Display list of user's uploaded documents
    Accessible table with sortable columns
    """
    documents = Document.objects.filter(user=request.user, is_deleted=False).order_by(
        "-created_at"
    )

    # Get current month's document count from UsageTracking (more accurate)
    from accounts.models import UsageTracking

    usage, _ = UsageTracking.objects.get_or_create(user=request.user)
    usage.check_and_reset_monthly()  # Ensure counters are current

    context = {
        "documents": documents,
        "documents_this_month": usage.documents_uploaded_this_month,
        "free_tier_limit": settings.FREE_TIER_DOCUMENTS_PER_MONTH,
        "is_premium": (
            request.user.is_premium if hasattr(request.user, "is_premium") else False
        ),
    }

    return render(request, "claims/document_list.html", context)


@login_required
@require_ai_consent_view
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def document_upload(request):
    """
    Handle document upload with accessible form.
    Includes inline validation and clear error messages.

    Rate limited to 10/min per user to prevent upload spam and storage exhaustion.
    Requires AI consent as uploads trigger automatic AI analysis.
    """
    # Get usage info for display
    from accounts.models import UsageTracking

    usage, _ = UsageTracking.objects.get_or_create(user=request.user)
    usage_summary = usage.get_usage_summary()

    if request.method == "POST":
        form = DocumentUploadForm(request.POST, request.FILES, user=request.user)

        if form.is_valid():
            # Save AI processing consent
            form.save_consent()

            # Create document instance
            document = form.save(commit=False)
            document.user = request.user

            # Set file metadata
            uploaded_file = request.FILES["file"]
            document.file_name = uploaded_file.name
            document.file_size = uploaded_file.size
            document.mime_type = uploaded_file.content_type

            document.save()

            # Record usage (count and storage)
            usage.record_document_upload(document.file_size)

            # Trigger async processing
            process_document_task.delay(document.id)

            # Success message for screen readers
            messages.success(
                request,
                f'Document "{document.file_name}" uploaded successfully. '
                "Processing has started and you will be notified when complete.",
            )

            return redirect("claims:document_detail", pk=document.id)
        else:
            # Form has errors - they will be displayed in template
            # Add a general error message for screen readers
            messages.error(
                request,
                "There were errors in your upload. Please review the form below.",
            )
    else:
        form = DocumentUploadForm(user=request.user)

    context = {
        "form": form,
        "usage": usage_summary,
    }

    return render(request, "claims/document_upload.html", context)


@login_required
def document_detail(request, pk):
    """
    Display document details and analysis results
    Accessible layout with clear headings and sections
    """
    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    active_shares = document.case_shares.select_related("case__organization").order_by(
        "-shared_at"
    )

    context = {
        "document": document,
        "active_shares": active_shares,
    }

    return render(request, "claims/document_detail.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def document_status(request, pk):
    """
    HTMX endpoint to check document processing status.
    Returns HTML partial for HTMX polling or JSON fallback.
    Sends HX-Refresh header when complete to reload page and stop polling.

    Rate limited to 60/min per user to prevent scraping while allowing
    normal 5-second polling (12 requests/min) with room for multiple tabs.
    """
    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    # Return HTML fragment for HTMX
    if request.headers.get("HX-Request"):
        response = render(
            request, "claims/partials/document_status.html", {"document": document}
        )
        # When processing completes, trigger page refresh to show results and stop polling
        if not document.is_processing:
            response["HX-Refresh"] = "true"
        return response

    # Fallback JSON response
    return JsonResponse(
        {
            "status": document.status,
            "is_processing": document.is_processing,
            "is_complete": document.is_complete,
            "has_failed": document.has_failed,
            "error_message": document.error_message if document.has_failed else None,
        }
    )


@login_required
@require_http_methods(["POST"])
def document_delete(request, pk):
    """
    Soft delete document
    Includes confirmation and accessible feedback
    """
    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    document_name = document.file_name
    file_size = document.file_size  # Store size before deletion

    document.delete()  # Soft delete from SoftDeleteModel

    # Release storage from usage tracking
    if file_size > 0:
        from accounts.models import UsageTracking

        usage, _ = UsageTracking.objects.get_or_create(user=request.user)
        usage.record_storage_freed(file_size)

    messages.success(request, f'Document "{document_name}" has been deleted.')

    return redirect("claims:document_list")


@login_required
@require_http_methods(["POST"])
@ratelimit(key="user", rate="30/m", method="POST", block=True)
def document_update_tags(request, pk):
    """
    Update condition tags for a document.
    Allows linking documents to specific conditions for organization.

    Rate limited to 30/min per user to prevent spam.
    """
    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    # Get tags from POST data
    tags_input = request.POST.get("condition_tags", "")

    # Parse tags (comma-separated or JSON array)
    import json

    try:
        # Try JSON array first
        tags = json.loads(tags_input)
        if not isinstance(tags, list):
            tags = [str(tags)]
    except (json.JSONDecodeError, TypeError):
        # Fall back to comma-separated
        tags = [t.strip() for t in tags_input.split(",") if t.strip()]

    # Clean and dedupe tags
    tags = list(set(tag.strip()[:100] for tag in tags if tag.strip()))

    document.condition_tags = tags
    document.save(update_fields=["condition_tags"])

    # HTMX response
    if request.headers.get("HX-Request"):
        return render(
            request,
            "claims/partials/document_tags.html",
            {
                "document": document,
                "tags_updated": True,
            },
        )

    messages.success(request, "Document tags updated.")
    return redirect("claims:document_detail", pk=document.pk)


# =============================================================================
# Denial Decoder Views
# =============================================================================


@login_required
@require_ai_consent_view
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def denial_decoder_upload(request):
    """
    Upload VA denial letter for decoding.
    Extracts denial reasons, matches to M21 sections, and generates evidence guidance.

    Rate limited to 10/min per user to prevent upload spam.
    Requires AI consent as this triggers AI-powered denial analysis.
    """
    # Get usage info for display
    from accounts.models import UsageTracking

    usage, _ = UsageTracking.objects.get_or_create(user=request.user)
    usage_summary = usage.get_usage_summary()

    if request.method == "POST":
        form = DenialLetterUploadForm(request.POST, request.FILES, user=request.user)

        if form.is_valid():
            # Save AI processing consent
            form.save_consent()

            # Create document instance
            document = form.save(commit=False)
            document.user = request.user
            document.document_type = "decision_letter"

            # Set file metadata
            uploaded_file = request.FILES["file"]
            document.file_name = uploaded_file.name
            document.file_size = uploaded_file.size
            document.mime_type = uploaded_file.content_type

            document.save()

            # Record usage (document upload + denial decode)
            usage.record_document_upload(document.file_size)
            usage.record_denial_decode()

            # Trigger denial decoding task
            decode_denial_letter_task.delay(document.id)

            messages.success(
                request,
                f'Denial letter "{document.file_name}" uploaded successfully. '
                "Analysis in progress - this may take 1-2 minutes.",
            )

            return redirect("claims:denial_decoder_result", pk=document.id)
        else:
            messages.error(
                request,
                "There were errors in your upload. Please review the form below.",
            )
    else:
        form = DenialLetterUploadForm(user=request.user)

    context = {
        "form": form,
        "usage": usage_summary,
    }

    return render(request, "claims/denial_decoder_upload.html", context)


@login_required
def denial_decoder_result(request, pk):
    """
    Display denial decoding results.
    Shows extracted denials, M21 matches, and evidence guidance.
    """
    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    # Get associated analysis and decoding
    analysis = None
    decoding = None

    # Check if document has been analyzed
    if hasattr(document, "decision_analyses"):
        analysis = document.decision_analyses.first()
        if analysis and hasattr(analysis, "denial_decoding"):
            decoding = analysis.denial_decoding

    context = {
        "document": document,
        "analysis": analysis,
        "decoding": decoding,
    }

    return render(request, "claims/denial_decoder_result.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def denial_decoder_status(request, pk):
    """
    HTMX endpoint to check denial decoding status.
    Returns status fragment for polling during processing.
    Sends HX-Refresh header when complete to reload page and stop polling.

    Rate limited to 60/min per user to prevent scraping.
    """
    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    # Check for analysis
    analysis = None
    decoding = None
    if hasattr(document, "decision_analyses"):
        analysis = document.decision_analyses.first()
        if analysis and hasattr(analysis, "denial_decoding"):
            decoding = analysis.denial_decoding

    context = {
        "document": document,
        "analysis": analysis,
        "decoding": decoding,
    }

    if request.headers.get("HX-Request"):
        response = render(
            request, "claims/partials/denial_decoder_status.html", context
        )
        # When processing completes, trigger page refresh to show results and stop polling
        if not document.is_processing:
            response["HX-Refresh"] = "true"
        return response

    return JsonResponse(
        {
            "status": document.status,
            "is_processing": document.is_processing,
            "is_complete": document.is_complete,
            "has_analysis": analysis is not None,
            "has_decoding": decoding is not None,
        }
    )


# =============================================================================
# Protected Media Access
# =============================================================================


@login_required
@ratelimit(key="user", rate="60/m", method="GET", block=True)
@require_http_methods(["GET"])
def document_download(request, pk):
    """
    Secure document download view.

    Protects media files by:
    1. Requiring authentication
    2. Verifying document ownership
    3. Audit logging the access
    4. Serving file through Django (not direct MEDIA_URL access)

    In production with nginx/apache, use X-Sendfile/X-Accel-Redirect
    for better performance.
    """
    # Get document and verify ownership
    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    # Get the file path
    if not document.file:
        raise Http404("Document file not found")

    file_path = document.file.path

    # Verify file exists on disk
    if not os.path.exists(file_path):
        raise Http404("Document file not found on disk")

    # Audit log the download
    AuditLog.log(
        action="document_download",
        request=request,
        resource_type="Document",
        resource_id=document.id,
        details={
            "file_name": document.file_name,
            "file_size": document.file_size,
        },
    )

    # Determine content type
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = "application/octet-stream"

    # Check for production sendfile support
    # In production, configure nginx with X-Accel-Redirect or apache with X-Sendfile
    use_sendfile = getattr(settings, "USE_X_SENDFILE", False)
    sendfile_root = getattr(settings, "SENDFILE_ROOT", "")

    if use_sendfile and sendfile_root:
        # Production: Use X-Sendfile/X-Accel-Redirect for nginx/apache
        # This is more efficient as the web server handles the file transfer
        from django.http import HttpResponse

        response = HttpResponse(content_type=content_type)

        # Calculate the internal redirect path for nginx
        # The file path relative to SENDFILE_ROOT
        internal_path = file_path.replace(str(settings.MEDIA_ROOT), "/protected-media")
        response["X-Accel-Redirect"] = internal_path
        response["Content-Disposition"] = f'attachment; filename="{document.file_name}"'
        return response
    else:
        # Development: Serve file directly through Django
        # This is slower but works without web server configuration
        response = FileResponse(
            open(file_path, "rb"),
            content_type=content_type,
            as_attachment=True,
            filename=document.file_name,
        )
        return response


@login_required
@ratelimit(key="user", rate="60/m", method="GET", block=True)
@require_http_methods(["GET"])
def document_view_inline(request, pk):
    """
    View document inline (in browser) rather than download.

    Same security as document_download but sets Content-Disposition
    to inline for PDFs/images to display in browser.
    """
    # Get document and verify ownership
    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    if not document.file:
        raise Http404("Document file not found")

    file_path = document.file.path

    if not os.path.exists(file_path):
        raise Http404("Document file not found on disk")

    # Audit log the view
    AuditLog.log(
        action="document_view",
        request=request,
        resource_type="Document",
        resource_id=document.id,
        details={
            "file_name": document.file_name,
            "view_type": "inline",
        },
    )

    # Determine content type
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = "application/octet-stream"

    # Serve file inline (for viewing in browser)
    response = FileResponse(
        open(file_path, "rb"),
        content_type=content_type,
    )
    response["Content-Disposition"] = f'inline; filename="{document.file_name}"'
    return response


# =============================================================================
# Signed URL Access (Token-based, no session required)
# =============================================================================


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
@require_http_methods(["GET"])
def document_download_signed(request, token):
    """
    Download document using signed URL token.

    Allows time-limited access without requiring active session.
    Token includes user ID, resource ID, action, and expiration.
    Used for sharing links that work across browser tabs/sessions.
    """
    from core.signed_urls import (
        get_signed_url_generator,
        TokenExpiredError,
        InvalidTokenError,
    )

    generator = get_signed_url_generator()

    try:
        token_data = generator.validate_token(token)
    except TokenExpiredError:
        return HttpResponseForbidden(
            "This download link has expired. Please request a new link."
        )
    except InvalidTokenError:
        return HttpResponseForbidden("Invalid download link.")

    # Verify action type
    if token_data.get("action") != "download":
        return HttpResponseForbidden("Invalid link type.")

    # Verify resource type
    if token_data.get("resource_type") != "document":
        return HttpResponseForbidden("Invalid resource type.")

    # Get the document
    resource_id = token_data.get("resource_id")
    user_id = token_data.get("user_id")

    try:
        document = Document.objects.get(
            pk=resource_id, user_id=user_id, is_deleted=False
        )
    except Document.DoesNotExist:
        raise Http404("Document not found")

    if not document.file:
        raise Http404("Document file not found")

    file_path = document.file.path

    if not os.path.exists(file_path):
        raise Http404("Document file not found on disk")

    # Audit log the download (use document owner since token-based access)
    AuditLog.log(
        action="document_download",
        request=request,
        user=document.user,
        resource_type="Document",
        resource_id=document.id,
        details={
            "file_name": document.file_name,
            "file_size": document.file_size,
            "access_type": "signed_url",
        },
    )

    # Determine content type
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = "application/octet-stream"

    # Serve file
    response = FileResponse(
        open(file_path, "rb"),
        content_type=content_type,
        as_attachment=True,
        filename=document.file_name,
    )
    return response


@ratelimit(key="ip", rate="30/m", method="GET", block=True)
@require_http_methods(["GET"])
def document_view_signed(request, token):
    """
    View document inline using signed URL token.

    Allows time-limited inline viewing without requiring active session.
    Same as document_download_signed but serves inline instead of attachment.
    """
    from core.signed_urls import (
        get_signed_url_generator,
        TokenExpiredError,
        InvalidTokenError,
    )

    generator = get_signed_url_generator()

    try:
        token_data = generator.validate_token(token)
    except TokenExpiredError:
        return HttpResponseForbidden(
            "This view link has expired. Please request a new link."
        )
    except InvalidTokenError:
        return HttpResponseForbidden("Invalid view link.")

    # Verify action type
    if token_data.get("action") != "view":
        return HttpResponseForbidden("Invalid link type.")

    # Verify resource type
    if token_data.get("resource_type") != "document":
        return HttpResponseForbidden("Invalid resource type.")

    # Get the document
    resource_id = token_data.get("resource_id")
    user_id = token_data.get("user_id")

    try:
        document = Document.objects.get(
            pk=resource_id, user_id=user_id, is_deleted=False
        )
    except Document.DoesNotExist:
        raise Http404("Document not found")

    if not document.file:
        raise Http404("Document file not found")

    file_path = document.file.path

    if not os.path.exists(file_path):
        raise Http404("Document file not found on disk")

    # Audit log the view (use document owner since token-based access)
    AuditLog.log(
        action="document_view",
        request=request,
        user=document.user,
        resource_type="Document",
        resource_id=document.id,
        details={
            "file_name": document.file_name,
            "view_type": "inline",
            "access_type": "signed_url",
        },
    )

    # Determine content type
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = "application/octet-stream"

    # Serve file inline
    response = FileResponse(
        open(file_path, "rb"),
        content_type=content_type,
    )
    response["Content-Disposition"] = f'inline; filename="{document.file_name}"'
    return response


# =============================================================================
# Rating Analyzer Views
# =============================================================================


@login_required
@require_ai_consent_view
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def rating_analyzer_upload(request):
    """
    Upload VA rating decision for enhanced analysis.
    Identifies increase opportunities, secondary conditions, errors, and deadlines.

    Rate limited to 10/min per user to prevent upload spam.
    Requires AI consent as this triggers AI-powered rating analysis.
    """
    from accounts.models import UsageTracking

    usage, _ = UsageTracking.objects.get_or_create(user=request.user)
    usage_summary = usage.get_usage_summary()

    if request.method == "POST":
        # Reuse the DenialLetterUploadForm since it's the same file validation
        form = DenialLetterUploadForm(request.POST, request.FILES, user=request.user)

        if form.is_valid():
            # Save AI processing consent
            form.save_consent()

            # Create document instance
            document = form.save(commit=False)
            document.user = request.user
            document.document_type = "decision_letter"

            # Set file metadata
            uploaded_file = request.FILES["file"]
            document.file_name = uploaded_file.name
            document.file_size = uploaded_file.size
            document.mime_type = uploaded_file.content_type

            document.save()

            # Record usage
            usage.record_document_upload(document.file_size)

            # Trigger rating analysis task (structured JSON format)
            analyze_rating_decision_task.delay(document.id, use_simple_format=False)

            messages.success(
                request,
                f'Rating decision "{document.file_name}" uploaded successfully. '
                "Analysis in progress - this may take 1-2 minutes.",
            )

            return redirect("claims:rating_analyzer_result", pk=document.id)
        else:
            messages.error(
                request,
                "There were errors in your upload. Please review the form below.",
            )
    else:
        form = DenialLetterUploadForm(user=request.user)

    context = {
        "form": form,
        "usage": usage_summary,
    }

    return render(request, "claims/rating_analyzer_upload.html", context)


@login_required
def rating_analyzer_result(request, pk):
    """
    Display rating analysis results.
    Shows increase opportunities, secondary conditions, deadlines, and priority actions.
    """
    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    # Get associated rating analysis
    rating_analysis = None
    from agents.models import RatingAnalysis

    rating_analysis = RatingAnalysis.objects.filter(
        document=document, user=request.user
    ).first()

    context = {
        "document": document,
        "analysis": rating_analysis,
    }

    return render(request, "claims/rating_analyzer_result.html", context)


@login_required
@require_http_methods(["GET"])
@ratelimit(key="user", rate="60/m", method="GET", block=True)
def rating_analyzer_status(request, pk):
    """
    HTMX endpoint to check rating analysis status.
    Returns status fragment for polling during processing.
    Sends HX-Refresh header when complete to reload page and stop polling.

    Rate limited to 60/min per user to prevent scraping.
    """
    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    # Check for rating analysis
    rating_analysis = None
    from agents.models import RatingAnalysis

    rating_analysis = RatingAnalysis.objects.filter(
        document=document, user=request.user
    ).first()

    context = {
        "document": document,
        "analysis": rating_analysis,
    }

    if request.headers.get("HX-Request"):
        response = render(
            request, "claims/partials/rating_analyzer_status.html", context
        )
        # When processing completes, trigger page refresh to show results and stop polling
        if not document.is_processing:
            response["HX-Refresh"] = "true"
        return response

    return JsonResponse(
        {
            "status": document.status,
            "is_processing": document.is_processing,
            "is_complete": document.is_complete,
            "has_analysis": rating_analysis is not None,
            "combined_rating": (
                rating_analysis.combined_rating if rating_analysis else None
            ),
            "condition_count": (
                rating_analysis.condition_count if rating_analysis else 0
            ),
        }
    )


@login_required
def document_share(request, pk):
    """
    Share a document with the veteran's assigned VSO.
    Veterans can share their documents with their active VSO case.
    """
    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    # Get active cases where this user is the veteran
    from vso.models import VeteranCase, SharedDocument

    active_cases = (
        VeteranCase.objects.filter(veteran=request.user)
        .exclude(status__startswith="closed")
        .select_related("organization", "assigned_to")
    )

    if request.method == "POST":
        case_id = request.POST.get("case_id")
        include_ai_analysis = request.POST.get("include_ai_analysis") == "on"

        if not case_id:
            messages.error(request, "Please select a case to share with.")
            return redirect("claims:document_share", pk=pk)

        case = get_object_or_404(VeteranCase, pk=case_id, veteran=request.user)

        # Check if already shared
        if SharedDocument.objects.filter(case=case, document=document).exists():
            messages.warning(request, "This document is already shared with this case.")
            return redirect("claims:document_detail", pk=pk)

        # Create the share
        shared_doc = SharedDocument.objects.create(
            case=case,
            document=document,
            shared_by=request.user,
            include_ai_analysis=include_ai_analysis,
            status="pending",
        )

        # Audit log: Document shared with VSO
        AuditLog.log(
            action="vso_document_share",
            request=request,
            resource_type="SharedDocument",
            resource_id=shared_doc.pk,
            details={
                "document_id": document.pk,
                "case_id": case.pk,
                "organization_id": case.organization.pk,
                "include_ai_analysis": include_ai_analysis,
            },
            success=True,
        )

        messages.success(
            request,
            f"Document shared with {case.organization.name}. "
            f"Your caseworker will be notified.",
        )

        return redirect("claims:document_detail", pk=pk)

    context = {
        "document": document,
        "active_cases": active_cases,
    }

    return render(request, "claims/document_share.html", context)


@login_required
@require_http_methods(["POST"])
def document_unshare(request, pk, share_pk):
    """
    Revoke a document share with a VSO.

    Veterans control sharing in both directions: the SharedDocument row is
    deleted (the VSO loses access immediately) and the revocation is
    audit-logged. VSO-authored case notes are unaffected.
    """
    from vso.models import SharedDocument

    document = get_object_or_404(Document, pk=pk, user=request.user, is_deleted=False)

    shared_doc = get_object_or_404(
        SharedDocument,
        pk=share_pk,
        document=document,
        document__user=request.user,
    )

    case = shared_doc.case
    details = {
        "document_id": document.pk,
        "case_id": case.pk,
        "organization_id": case.organization.pk,
        "was_shared_at": shared_doc.shared_at.isoformat(),
    }

    shared_doc.delete()

    AuditLog.log(
        action="vso_document_unshare",
        request=request,
        resource_type="SharedDocument",
        resource_id=share_pk,
        details=details,
        success=True,
    )

    messages.success(
        request,
        f"Sharing revoked. {case.organization.name} no longer has access "
        f"to this document.",
    )

    return redirect("claims:document_detail", pk=pk)
