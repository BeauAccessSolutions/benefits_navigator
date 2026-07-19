"""
Appeals app views - Appeal workflow, guidance, and management.
"""

import mimetypes
import os

from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.http import require_http_methods

from core.models import AuditLog

from .models import Appeal, AppealGuidance, AppealDocument, AppealNote
from .forms import (
    AppealStartForm,
    DecisionTreeForm,
    AppealTypeForm,
    AppealUpdateForm,
    AppealDecisionForm,
    AppealDocumentForm,
    AppealNoteForm,
)

# =============================================================================
# APPEAL GUIDANCE VIEWS (Public)
# =============================================================================


def appeals_home(request):
    """
    Appeals landing page - overview of appeal options and decision tree entry.
    """
    guidance_list = AppealGuidance.objects.filter(is_published=True)

    # Stats for the page
    appeal_types = [
        {
            "type": "supplemental",
            "name": "Supplemental Claim",
            "form": "VA Form 20-0995",
            "time": "~93 days",
            "best_for": "When you have NEW evidence",
            "icon": "document-plus",
        },
        {
            "type": "hlr",
            "name": "Higher-Level Review",
            "form": "VA Form 20-0996",
            "time": "~141 days",
            "best_for": "When VA made an ERROR",
            "icon": "magnifying-glass",
        },
        {
            "type": "board",
            "name": "Board Appeal",
            "form": "VA Form 10182",
            "time": "1-2+ years",
            "best_for": "Complex cases or when you want a hearing",
            "icon": "scale",
        },
    ]

    context = {
        "guidance_list": guidance_list,
        "appeal_types": appeal_types,
        "page_title": "VA Appeals Guide",
    }
    return render(request, "appeals/appeals_home.html", context)


def guidance_detail(request, slug):
    """
    Detailed guidance for a specific appeal type.
    """
    guidance = get_object_or_404(AppealGuidance, slug=slug, is_published=True)

    context = {
        "guidance": guidance,
        "page_title": guidance.title,
    }
    return render(request, "appeals/guidance_detail.html", context)


def decision_tree(request):
    """
    Interactive decision tree to recommend appeal type.
    Can be used without login for education; saves if logged in.
    """
    if request.method == "POST":
        form = DecisionTreeForm(request.POST)
        if form.is_valid():
            recommendation = form.get_recommendation()

            # If user is logged in and wants to start an appeal
            if request.user.is_authenticated and request.POST.get("start_appeal"):
                # Store recommendation AND answers in session for next step
                # This avoids asking the same questions again in appeal_decide
                request.session["appeal_recommendation"] = recommendation
                request.session["appeal_decision_tree_answers"] = {
                    "has_new_evidence": form.cleaned_data.get("has_new_evidence"),
                    "believes_va_error": form.cleaned_data.get("believes_va_error"),
                    "wants_hearing": form.cleaned_data.get("wants_hearing"),
                }
                return redirect("appeals:appeal_start")

            context = {
                "form": form,
                "recommendation": recommendation,
                "show_result": True,
                "page_title": "Appeal Path Finder - Result",
            }
            return render(request, "appeals/decision_tree.html", context)
    else:
        form = DecisionTreeForm()

    context = {
        "form": form,
        "show_result": False,
        "page_title": "Find Your Appeal Path",
    }
    return render(request, "appeals/decision_tree.html", context)


# =============================================================================
# APPEAL MANAGEMENT VIEWS (Login Required)
# =============================================================================


@login_required
def appeal_list(request):
    """
    List user's appeals with status overview.
    """
    appeals = Appeal.objects.filter(user=request.user)

    # Separate by status
    active_appeals = appeals.exclude(status__in=["decided", "closed"])
    completed_appeals = appeals.filter(status__in=["decided", "closed"])

    # Check for urgent deadlines
    urgent_appeals = [a for a in active_appeals if a.is_deadline_urgent]

    context = {
        "active_appeals": active_appeals,
        "completed_appeals": completed_appeals,
        "urgent_appeals": urgent_appeals,
        "page_title": "My Appeals",
    }
    return render(request, "appeals/appeal_list.html", context)


@login_required
def appeal_start(request):
    """
    Start a new appeal - Step 1: Basic info about the decision.
    """
    # Get recommendation and answers from decision tree (don't pop yet - need them for POST)
    recommendation = request.session.get("appeal_recommendation")
    decision_tree_answers = request.session.get("appeal_decision_tree_answers")

    if request.method == "POST":
        form = AppealStartForm(request.POST)
        if form.is_valid():
            appeal = form.save(commit=False)
            appeal.user = request.user

            # Apply recommendation and decision tree answers if available
            # This prevents asking the same questions again in appeal_decide
            if recommendation:
                appeal.appeal_type = recommendation.get("type", "")
                appeal.status = "gathering"  # Skip deciding phase, go to gathering

            if decision_tree_answers:
                appeal.has_new_evidence = (
                    decision_tree_answers.get("has_new_evidence") == "yes"
                )
                appeal.believes_va_error = (
                    decision_tree_answers.get("believes_va_error") == "yes"
                )
                appeal.wants_hearing = (
                    decision_tree_answers.get("wants_hearing") == "yes"
                )

            appeal.save()

            # Now that the appeal is saved, clear the session data
            request.session.pop("appeal_recommendation", None)
            request.session.pop("appeal_decision_tree_answers", None)

            # If we already have a type from recommendation, skip to detail page
            if appeal.appeal_type:
                # Add status note
                AppealNote.objects.create(
                    appeal=appeal,
                    note_type="status",
                    content=f"Appeal started: {appeal.get_appeal_type_display()}",
                )
                messages.success(
                    request,
                    f"Appeal started! You're filing a {appeal.get_appeal_type_display()}. "
                    f"Review the checklist below to prepare.",
                )
                return redirect("appeals:appeal_detail", pk=appeal.pk)

            # Otherwise, go to decision tree to choose appeal type
            messages.success(
                request, "Appeal started! Now let's figure out the best appeal path."
            )
            return redirect("appeals:appeal_decide", pk=appeal.pk)
    else:
        form = AppealStartForm()

    context = {
        "form": form,
        "recommendation": recommendation,
        "page_title": "Start New Appeal",
    }
    return render(request, "appeals/appeal_start.html", context)


@login_required
def appeal_decide(request, pk):
    """
    Decision tree step for an existing appeal to choose appeal type.
    """
    appeal = get_object_or_404(Appeal, pk=pk, user=request.user)

    if request.method == "POST":
        form = DecisionTreeForm(request.POST)
        if form.is_valid():
            # Update appeal with answers
            has_evidence = form.cleaned_data.get("has_new_evidence")
            believes_error = form.cleaned_data.get("believes_va_error")
            wants_hearing = form.cleaned_data.get("wants_hearing")

            appeal.has_new_evidence = has_evidence == "yes"
            appeal.believes_va_error = believes_error == "yes"
            appeal.wants_hearing = wants_hearing == "yes"

            # Get recommendation
            recommendation = form.get_recommendation()
            recommended_type = recommendation.get("type")

            # Show type selection with recommendation
            type_form = AppealTypeForm(recommended_type=recommended_type)

            context = {
                "appeal": appeal,
                "form": form,
                "type_form": type_form,
                "recommendation": recommendation,
                "show_type_selection": True,
                "page_title": "Choose Appeal Type",
            }
            return render(request, "appeals/appeal_decide.html", context)
    else:
        form = DecisionTreeForm()

    context = {
        "appeal": appeal,
        "form": form,
        "show_type_selection": False,
        "page_title": "Choose Your Appeal Path",
    }
    return render(request, "appeals/appeal_decide.html", context)


@login_required
@require_http_methods(["POST"])
def appeal_set_type(request, pk):
    """
    Set the appeal type after decision tree.
    """
    appeal = get_object_or_404(Appeal, pk=pk, user=request.user)

    form = AppealTypeForm(request.POST, instance=appeal)
    if form.is_valid():
        appeal = form.save(commit=False)
        appeal.status = "gathering"  # Move to next phase
        appeal.save()

        # Add status note
        AppealNote.objects.create(
            appeal=appeal,
            note_type="status",
            content=f"Appeal type selected: {appeal.get_appeal_type_display()}",
        )

        messages.success(
            request,
            f"Great choice! You're filing a {appeal.get_appeal_type_display()}. "
            f"Let's gather what you need.",
        )
        return redirect("appeals:appeal_detail", pk=appeal.pk)

    messages.error(request, "Please select an appeal type.")
    return redirect("appeals:appeal_decide", pk=pk)


@login_required
def appeal_detail(request, pk):
    """
    Main appeal dashboard - shows progress, guidance, documents, and next steps.
    """
    appeal = get_object_or_404(Appeal, pk=pk, user=request.user)
    guidance = appeal.get_guidance()
    documents = appeal.documents.all()
    notes = appeal.timeline_notes.all()[:10]

    # Get checklist progress
    checklist_items = []
    if guidance and guidance.checklist_items:
        for item in guidance.checklist_items:
            item["completed"] = item.get("id") in appeal.steps_completed
            checklist_items.append(item)

    context = {
        "appeal": appeal,
        "guidance": guidance,
        "documents": documents,
        "notes": notes,
        "checklist_items": checklist_items,
        "page_title": f'Appeal: {appeal.get_appeal_type_display() if appeal.appeal_type else "In Progress"}',
    }
    return render(request, "appeals/appeal_detail.html", context)


@login_required
def appeal_update(request, pk):
    """
    Update appeal status and info.
    """
    appeal = get_object_or_404(Appeal, pk=pk, user=request.user)

    if request.method == "POST":
        form = AppealUpdateForm(request.POST, instance=appeal)
        if form.is_valid():
            old_status = appeal.status
            appeal = form.save()

            # Log status change
            if old_status != appeal.status:
                AppealNote.objects.create(
                    appeal=appeal,
                    note_type="status",
                    content=f"Status changed from {old_status} to {appeal.status}",
                )

            messages.success(request, "Appeal updated.")
            return redirect("appeals:appeal_detail", pk=appeal.pk)
    else:
        form = AppealUpdateForm(instance=appeal)

    context = {
        "appeal": appeal,
        "form": form,
        "page_title": "Update Appeal",
    }
    return render(request, "appeals/appeal_update.html", context)


@login_required
def appeal_record_decision(request, pk):
    """
    Record the outcome of an appeal.
    """
    appeal = get_object_or_404(Appeal, pk=pk, user=request.user)

    if request.method == "POST":
        form = AppealDecisionForm(request.POST, instance=appeal)
        if form.is_valid():
            appeal = form.save(commit=False)
            appeal.status = "decided"
            appeal.save()

            # Log decision
            AppealNote.objects.create(
                appeal=appeal,
                note_type="status",
                content=f"Decision received: {appeal.get_decision_outcome_display()}",
                is_important=True,
            )

            outcome_messages = {
                "granted": "Congratulations! Your appeal was granted.",
                "partial": "Your appeal was partially granted. Review what was approved and consider next steps for remaining issues.",
                "denied": "Your appeal was denied. Don't give up - you may have other options.",
                "remanded": "Your case was remanded. The VA will do more work and issue a new decision.",
            }

            messages.info(
                request,
                outcome_messages.get(appeal.decision_outcome, "Decision recorded."),
            )
            return redirect("appeals:appeal_detail", pk=appeal.pk)
    else:
        form = AppealDecisionForm(instance=appeal)

    context = {
        "appeal": appeal,
        "form": form,
        "page_title": "Record Decision",
    }
    return render(request, "appeals/appeal_record_decision.html", context)


@login_required
@require_http_methods(["POST"])
def appeal_toggle_step(request, pk):
    """
    Toggle a checklist step as completed/incomplete (HTMX endpoint).
    """
    appeal = get_object_or_404(Appeal, pk=pk, user=request.user)
    step_id = request.POST.get("step_id")

    if step_id:
        steps = list(appeal.steps_completed)
        if step_id in steps:
            steps.remove(step_id)
        else:
            steps.append(step_id)
        appeal.steps_completed = steps
        appeal.save()

    # Return updated checklist item for HTMX
    if request.headers.get("HX-Request"):
        guidance = appeal.get_guidance()
        checklist_items = []
        if guidance and guidance.checklist_items:
            for item in guidance.checklist_items:
                item["completed"] = item.get("id") in appeal.steps_completed
                checklist_items.append(item)

        return render(
            request,
            "appeals/partials/checklist.html",
            {
                "appeal": appeal,
                "checklist_items": checklist_items,
            },
        )

    return redirect("appeals:appeal_detail", pk=pk)


# =============================================================================
# DOCUMENT VIEWS
# =============================================================================


@login_required
def appeal_add_document(request, pk):
    """
    Add a document to an appeal.
    """
    appeal = get_object_or_404(Appeal, pk=pk, user=request.user)

    if request.method == "POST":
        form = AppealDocumentForm(request.POST, request.FILES)
        if form.is_valid():
            document = form.save(commit=False)
            document.appeal = appeal
            document.save()

            messages.success(request, f'Document "{document.title}" added.')

            if request.headers.get("HX-Request"):
                documents = appeal.documents.all()
                return render(
                    request,
                    "appeals/partials/document_list.html",
                    {
                        "appeal": appeal,
                        "documents": documents,
                    },
                )

            return redirect("appeals:appeal_detail", pk=appeal.pk)
    else:
        form = AppealDocumentForm()

    context = {
        "appeal": appeal,
        "form": form,
        "page_title": "Add Document",
    }
    return render(request, "appeals/appeal_add_document.html", context)


@login_required
@require_http_methods(["POST"])
def appeal_delete_document(request, pk, doc_pk):
    """
    Delete a document from an appeal.
    """
    appeal = get_object_or_404(Appeal, pk=pk, user=request.user)
    document = get_object_or_404(AppealDocument, pk=doc_pk, appeal=appeal)

    document.delete()
    messages.success(request, "Document deleted.")

    if request.headers.get("HX-Request"):
        documents = appeal.documents.all()
        return render(
            request,
            "appeals/partials/document_list.html",
            {
                "appeal": appeal,
                "documents": documents,
            },
        )

    return redirect("appeals:appeal_detail", pk=pk)


def _serve_appeal_document(request, pk, doc_pk, *, disposition, audit_action):
    """
    Shared body for the protected appeal-document media views.

    Media files are never served from MEDIA_URL (see benefits_navigator/urls.py),
    so access goes through here, which:
    1. Requires authentication (via @login_required on the callers)
    2. Verifies the document belongs to an appeal owned by request.user
    3. Audit logs the access
    4. Streams the file through Django

    Mirrors claims.views.document_download / document_view_inline, with file
    access done through the storage backend rather than a filesystem path so it
    keeps working under USE_S3.
    """
    appeal = get_object_or_404(Appeal, pk=pk, user=request.user)
    document = get_object_or_404(AppealDocument, pk=doc_pk, appeal=appeal)

    if not document.file:
        raise Http404("Document file not found")

    storage = document.file.storage
    file_name = os.path.basename(document.file.name)

    if not storage.exists(document.file.name):
        raise Http404("Document file not found in storage")

    AuditLog.log(
        action=audit_action,
        request=request,
        resource_type="AppealDocument",
        resource_id=document.id,
        details={
            "appeal_id": appeal.id,
            "file_name": file_name,
            "disposition": disposition,
        },
    )

    content_type, _ = mimetypes.guess_type(file_name)
    if not content_type:
        content_type = "application/octet-stream"

    # Production: let nginx/apache do the transfer via X-Accel-Redirect.
    # Only reachable with local filesystem storage, which is what SENDFILE_ROOT implies.
    use_sendfile = getattr(settings, "USE_X_SENDFILE", False)
    sendfile_root = getattr(settings, "SENDFILE_ROOT", "")

    if use_sendfile and sendfile_root:
        response = HttpResponse(content_type=content_type)
        internal_path = document.file.path.replace(
            str(settings.MEDIA_ROOT), "/protected-media"
        )
        response["X-Accel-Redirect"] = internal_path
        response["Content-Disposition"] = f'{disposition}; filename="{file_name}"'
        return response

    response = FileResponse(document.file.open("rb"), content_type=content_type)
    response["Content-Disposition"] = f'{disposition}; filename="{file_name}"'
    return response


@login_required
@require_http_methods(["GET"])
def appeal_document_view(request, pk, doc_pk):
    """
    View an appeal document inline (in the browser).
    """
    return _serve_appeal_document(
        request,
        pk,
        doc_pk,
        disposition="inline",
        audit_action="document_view",
    )


@login_required
@require_http_methods(["GET"])
def appeal_document_download(request, pk, doc_pk):
    """
    Download an appeal document as an attachment.
    """
    return _serve_appeal_document(
        request,
        pk,
        doc_pk,
        disposition="attachment",
        audit_action="document_download",
    )


# =============================================================================
# NOTE VIEWS
# =============================================================================


@login_required
def appeal_add_note(request, pk):
    """
    Add a note to an appeal timeline.
    """
    appeal = get_object_or_404(Appeal, pk=pk, user=request.user)

    if request.method == "POST":
        form = AppealNoteForm(request.POST)
        if form.is_valid():
            note = form.save(commit=False)
            note.appeal = appeal
            note.save()

            messages.success(request, "Note added.")

            if request.headers.get("HX-Request"):
                notes = appeal.timeline_notes.all()[:10]
                return render(
                    request,
                    "appeals/partials/notes_list.html",
                    {
                        "appeal": appeal,
                        "notes": notes,
                    },
                )

            return redirect("appeals:appeal_detail", pk=appeal.pk)
    else:
        form = AppealNoteForm()

    context = {
        "appeal": appeal,
        "form": form,
        "page_title": "Add Note",
    }
    return render(request, "appeals/appeal_add_note.html", context)
