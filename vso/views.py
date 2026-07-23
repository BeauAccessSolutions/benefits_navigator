"""
Views for VSO app - Case management and dashboard for Veterans Service Organizations
"""

import csv
from datetime import timedelta

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Count
from django.utils import timezone
from django_ratelimit.decorators import ratelimit

from accounts.models import OrganizationMembership, OrganizationInvitation
from core.models import AuditLog
from .models import VeteranCase, CaseNote, SharedDocument, SharedAnalysis, CaseCondition
from .permissions import (
    get_user_organization_membership,
    vso_staff_required,
    member_is_org_admin,
    scope_cases_for_member,
    get_scoped_case_or_404,
)
from .services import GapCheckerService
from appeals.models import Appeal


def is_case_read_only(case):
    """
    Check if a case is read-only (archived).

    Archived cases should not allow any modifications - no new notes,
    no status changes, no document reviews, etc.

    Returns:
        True if the case is archived and should be treated as read-only.
    """
    return case.is_archived


def is_vso_member(user, org_slug=None):
    """Check if user is a VSO staff member (admin or caseworker)."""
    if not user.is_authenticated:
        return False

    memberships = user.memberships.filter(
        role__in=["admin", "caseworker"], is_active=True, organization__is_active=True
    )

    if org_slug:
        memberships = memberships.filter(organization__slug=org_slug)

    return memberships.exists()


def get_user_staff_memberships(user):
    """
    Get all VSO staff memberships for a user.

    Returns:
        QuerySet of OrganizationMembership objects where user is admin/caseworker
    """
    if not user.is_authenticated:
        return OrganizationMembership.objects.none()

    return user.memberships.filter(
        role__in=["admin", "caseworker"], is_active=True, organization__is_active=True
    ).select_related("organization")


def get_user_organization(user, org_slug=None, request=None):
    """
    Get the user's active organization with explicit selection for multi-org users.

    Security: When user belongs to multiple organizations, require explicit selection
    via org_slug parameter or session to prevent ambiguous data access.

    Args:
        user: User instance
        org_slug: Optional explicit organization slug (from URL or parameter)
        request: Optional request object to check/store session selection

    Returns:
        Organization instance or None
    """
    memberships = get_user_staff_memberships(user)

    if not memberships.exists():
        return None

    # If org_slug provided, validate and use it
    if org_slug:
        membership = memberships.filter(organization__slug=org_slug).first()
        if membership:
            # Store selection in session for future requests
            if request:
                request.session["selected_org_slug"] = org_slug
            return membership.organization
        return None  # Invalid org_slug

    # Check session for previously selected org
    if request:
        session_org_slug = request.session.get("selected_org_slug")
        if session_org_slug:
            membership = memberships.filter(organization__slug=session_org_slug).first()
            if membership:
                return membership.organization
            # Session org no longer valid, clear it
            del request.session["selected_org_slug"]

    # If only one organization, use it directly
    if memberships.count() == 1:
        org = memberships.first().organization
        if request:
            request.session["selected_org_slug"] = org.slug
        return org

    # Multiple organizations - require explicit selection
    # Return None to trigger org selection prompt
    return None


def requires_org_selection(user, request=None):
    """
    Check if user needs to select an organization.

    Returns:
        True if user has multiple orgs and none is selected
    """
    memberships = get_user_staff_memberships(user)

    if memberships.count() <= 1:
        return False

    # Check if valid org is already selected in session
    if request:
        session_org_slug = request.session.get("selected_org_slug")
        if (
            session_org_slug
            and memberships.filter(organization__slug=session_org_slug).exists()
        ):
            return False

    return True


def vso_required(view_func):
    """Decorator to require VSO staff access."""
    return vso_staff_required(view_func)


@vso_required
def select_organization(request):
    """
    Organization selection page for multi-org users.

    Allows users belonging to multiple organizations to explicitly choose
    which organization they want to work with.
    """
    memberships = get_user_staff_memberships(request.user)

    if not memberships.exists():
        messages.error(request, "No organization membership found.")
        return redirect("claims:document_list")

    # If only one org, redirect directly
    if memberships.count() == 1:
        org = memberships.first().organization
        request.session["selected_org_slug"] = org.slug
        return redirect("vso:dashboard")

    if request.method == "POST":
        org_slug = request.POST.get("organization")
        if org_slug:
            membership = memberships.filter(organization__slug=org_slug).first()
            if membership:
                request.session["selected_org_slug"] = org_slug
                messages.success(
                    request, f"Now working with {membership.organization.name}"
                )
                return redirect("vso:dashboard")

    context = {
        "memberships": memberships,
    }
    return render(request, "vso/select_organization.html", context)


@vso_required
def dashboard(request):
    """
    VSO Dashboard - Overview of all cases and metrics
    """
    # Check if user needs to select an organization
    if requires_org_selection(request.user, request):
        return redirect("vso:select_organization")

    org = get_user_organization(request.user, request=request)
    if not org:
        messages.error(request, "Please select an organization to continue.")
        return redirect("vso:select_organization")

    # Get all cases for this organization (least-privilege scoped)
    cases = scope_cases_for_member(
        request.user, org, VeteranCase.objects.filter(organization=org)
    )

    # Case counts by status
    status_counts = cases.values("status").annotate(count=Count("id"))
    status_dict = {item["status"]: item["count"] for item in status_counts}

    # Priority cases (urgent or overdue)
    priority_cases = (
        cases.filter(
            Q(priority="urgent") | Q(next_action_date__lt=timezone.now().date())
        )
        .filter(
            status__in=[
                "intake",
                "gathering_evidence",
                "claim_filed",
                "pending_decision",
                "appeal_in_progress",
            ]
        )
        .order_by("next_action_date", "-priority")[:10]
    )

    # Recent activity (notes and shared documents)
    recent_notes = (
        CaseNote.objects.filter(case__in=cases)
        .select_related("case", "author")
        .order_by("-created_at")[:10]
    )

    # Cases assigned to current user
    my_cases = (
        cases.filter(assigned_to=request.user)
        .exclude(status__startswith="closed")
        .order_by("next_action_date", "-priority")[:10]
    )

    # Outcome metrics (closed cases)
    closed_cases = cases.filter(status__startswith="closed")
    won_cases = closed_cases.filter(status="closed_won").count()
    total_closed = closed_cases.count()
    win_rate = (won_cases / total_closed * 100) if total_closed > 0 else 0

    # This month metrics
    now = timezone.now()
    first_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    cases_this_month = cases.filter(created_at__gte=first_of_month).count()
    closed_this_month = closed_cases.filter(closed_at__gte=first_of_month).count()
    won_this_month = closed_cases.filter(
        status="closed_won", closed_at__gte=first_of_month
    ).count()

    # Last month metrics for trend comparison
    if first_of_month.month == 1:
        first_of_last_month = first_of_month.replace(
            year=first_of_month.year - 1, month=12
        )
    else:
        first_of_last_month = first_of_month.replace(month=first_of_month.month - 1)

    closed_last_month = closed_cases.filter(
        closed_at__gte=first_of_last_month, closed_at__lt=first_of_month
    )
    won_last_month = closed_last_month.filter(status="closed_won").count()
    total_closed_last_month = closed_last_month.count()
    win_rate_last_month = (
        (won_last_month / total_closed_last_month * 100)
        if total_closed_last_month > 0
        else None
    )

    # Calculate trend direction
    if win_rate_last_month is not None and total_closed > 0:
        win_rate_trend = (
            "up"
            if win_rate > win_rate_last_month
            else ("down" if win_rate < win_rate_last_month else "flat")
        )
    else:
        win_rate_trend = None

    # Stale cases - no activity in 30+ days
    thirty_days_ago = now - timedelta(days=30)
    stale_cases = (
        cases.filter(last_activity_at__lt=thirty_days_ago, is_archived=False)
        .exclude(status__startswith="closed")
        .order_by("last_activity_at")[:10]
    )

    # Check if user is org admin
    membership = get_user_organization_membership(request.user, org)
    is_org_admin = membership and membership.role == "admin"

    context = {
        "organization": org,
        "total_cases": cases.count(),
        "open_cases": cases.exclude(status__startswith="closed").count(),
        "status_counts": status_dict,
        "priority_cases": priority_cases,
        "recent_notes": recent_notes,
        "my_cases": my_cases,
        "win_rate": win_rate,
        "won_cases": won_cases,
        "total_closed": total_closed,
        "stale_cases": stale_cases,
        "status_choices": VeteranCase.STATUS_CHOICES,
        # This month metrics
        "cases_this_month": cases_this_month,
        "closed_this_month": closed_this_month,
        "won_this_month": won_this_month,
        "win_rate_trend": win_rate_trend,
        "win_rate_last_month": win_rate_last_month,
        # Admin flag
        "is_org_admin": is_org_admin,
    }

    return render(request, "vso/dashboard.html", context)


@vso_required
def case_list(request):
    """
    List all cases with filtering and search
    """
    org = get_user_organization(request.user, request=request)
    if not org:
        return redirect("vso:dashboard")

    # Base queryset - exclude archived by default
    cases = (
        VeteranCase.objects.filter(organization=org, is_archived=False)
        .select_related("veteran", "assigned_to")
        .prefetch_related("case_conditions")
    )
    cases = scope_cases_for_member(request.user, org, cases)

    # Filtering
    status_filter = request.GET.get("status")
    priority_filter = request.GET.get("priority")
    assigned_filter = request.GET.get("assigned_to")
    triage_filter = request.GET.get("triage")
    search_query = request.GET.get("q")
    show_archived = request.GET.get("archived") == "1"

    # Allow showing archived cases
    if show_archived:
        cases = (
            VeteranCase.objects.filter(organization=org, is_archived=True)
            .select_related("veteran", "assigned_to")
            .prefetch_related("case_conditions")
        )
        # Rebuilt from scratch — must re-apply least-privilege scoping.
        cases = scope_cases_for_member(request.user, org, cases)

    if status_filter:
        cases = cases.filter(status=status_filter)

    if priority_filter:
        cases = cases.filter(priority=priority_filter)

    if assigned_filter:
        if assigned_filter == "me":
            cases = cases.filter(assigned_to=request.user)
        elif assigned_filter == "unassigned":
            cases = cases.filter(assigned_to__isnull=True)
        else:
            cases = cases.filter(assigned_to_id=assigned_filter)

    if search_query:
        cases = cases.filter(
            Q(title__icontains=search_query)
            | Q(veteran__email__icontains=search_query)
            | Q(veteran__first_name__icontains=search_query)
            | Q(veteran__last_name__icontains=search_query)
            # description is encrypted at rest — not searchable via icontains
        )

    # Ordering
    order_by = request.GET.get("order_by", "-created_at")
    cases = cases.order_by(order_by)

    # Add triage labels to cases and filter if needed
    cases_with_triage = []
    for case in cases:
        case.triage_label = GapCheckerService.get_triage_label(case)
        case.triage_color = GapCheckerService.get_triage_color(case.triage_label)
        case.triage_display = GapCheckerService.get_triage_display(case.triage_label)
        if not triage_filter or case.triage_label == triage_filter:
            cases_with_triage.append(case)

    # CSV Export
    if request.GET.get("export") == "csv":
        return _export_cases_csv(cases_with_triage, request=request, org=org)

    # Pagination
    paginator = Paginator(cases_with_triage, 25)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    # Get caseworkers for filter dropdown
    caseworkers = org.memberships.filter(
        role__in=["admin", "caseworker"], is_active=True
    ).select_related("user")

    # Triage choices for filter
    triage_choices = [
        (GapCheckerService.READY_TO_FILE, "Ready to File"),
        (GapCheckerService.NEEDS_EVIDENCE, "Needs Evidence"),
        (GapCheckerService.NEEDS_NEXUS, "Needs Nexus"),
        (GapCheckerService.NEEDS_REVIEW, "Needs Review"),
    ]

    context = {
        "organization": org,
        "page_obj": page_obj,
        "cases": page_obj,
        "status_choices": VeteranCase.STATUS_CHOICES,
        "priority_choices": VeteranCase.PRIORITY_CHOICES,
        "triage_choices": triage_choices,
        "caseworkers": caseworkers,
        "current_filters": {
            "status": status_filter,
            "priority": priority_filter,
            "assigned_to": assigned_filter,
            "triage": triage_filter,
            "q": search_query,
            "order_by": order_by,
            "archived": show_archived,
        },
    }

    return render(request, "vso/case_list.html", context)


def _export_cases_csv(cases, request=None, org=None):
    """
    Export cases to CSV format with audit logging.

    Bulk export is a privilege, not a default: org admins only,
    rate-limited, ops-alerted, and without veteran emails in the output.
    """
    from django_ratelimit.core import is_ratelimited

    if request is not None and org is not None:
        if not member_is_org_admin(request.user, org):
            messages.error(
                request, "Bulk export is limited to organization administrators."
            )
            return redirect("vso:case_list")

        if is_ratelimited(
            request,
            group="vso_case_export",
            key="user",
            rate="5/h",
            increment=True,
        ):
            messages.error(
                request, "Export limit reached (5 per hour). Please try again later."
            )
            return redirect("vso:case_list")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="cases_export.csv"'

    writer = csv.writer(response)
    writer.writerow(
        [
            "Case Title",
            "Veteran Name",
            "Status",
            "Priority",
            "Assigned To",
            "Triage Status",
            "Days Open",
            "Intake Date",
            "Initial Rating",
            "Final Rating",
            "Conditions Count",
        ]
    )

    case_ids = []
    for case in cases:
        case_ids.append(case.pk)
        writer.writerow(
            [
                case.title,
                case.veteran.get_full_name() or "",
                case.get_status_display(),
                case.get_priority_display(),
                case.assigned_to.email if case.assigned_to else "Unassigned",
                getattr(case, "triage_display", ""),
                case.days_open,
                case.intake_date.isoformat() if case.intake_date else "",
                case.initial_combined_rating or "",
                case.final_combined_rating or "",
                case.case_conditions.count(),
            ]
        )

    # Audit log the export
    if request and request.user.is_authenticated:
        # AuditLog.log (not objects.create) so the IP goes through
        # _get_client_ip: behind the App Platform load balancer REMOTE_ADDR is
        # the proxy, and a bulk pull of veteran data is the last event whose
        # source IP should be a constant.
        AuditLog.log(
            action="vso_case_export",
            request=request,
            resource_type="VeteranCase",
            details={
                "case_count": len(case_ids),
                "case_ids": case_ids[:100],  # Limit to first 100 for storage
                "organization": org.slug if org else None,
                "format": "csv",
            },
        )

        # Ops visibility: bulk pulls of veteran data should never be silent
        from core.alerting import AlertSeverity, send_alert

        send_alert(
            title="VSO Bulk Case Export",
            message=(
                f"User id={request.user.pk} exported {len(case_ids)} cases "
                f"from org '{org.slug if org else 'unknown'}'"
            ),
            severity=AlertSeverity.INFO,
            details={
                "user_id": request.user.pk,
                "case_count": len(case_ids),
                "organization": org.slug if org else None,
            },
        )

    return response


@vso_required
@require_POST
@ratelimit(key="user", rate="10/m", method="POST", block=True)
def bulk_case_action(request):
    """
    Handle bulk actions on multiple cases.
    Supports: status update, reassignment, archive, export.

    Rate limited to 10/min per user to prevent bulk operation abuse.
    """
    org = get_user_organization(request.user, request=request)
    if not org:
        return JsonResponse({"error": "No organization"}, status=403)

    case_ids = request.POST.getlist("case_ids")
    action = request.POST.get("action")

    if not case_ids:
        messages.error(request, "No cases selected.")
        return redirect("vso:case_list")

    # Get cases within organization, honoring least-privilege scoping so a
    # restricted caseworker cannot bulk-act on a colleague's case by id.
    cases = (
        scope_cases_for_member(
            request.user,
            org,
            VeteranCase.objects.filter(organization=org, is_archived=False),
        )
        .filter(pk__in=case_ids)
        .prefetch_related("case_conditions")
    )

    count = cases.count()
    if count == 0:
        messages.error(request, "No valid cases found.")
        return redirect("vso:case_list")

    if action == "update_status":
        new_status = request.POST.get("new_status")
        if new_status and new_status in dict(VeteranCase.STATUS_CHOICES):
            cases.update(status=new_status, last_activity_at=timezone.now())
            messages.success(request, f"Updated status for {count} case(s).")
        else:
            messages.error(request, "Invalid status selected.")

    elif action == "reassign":
        new_assignee_id = request.POST.get("new_assignee")
        if new_assignee_id == "unassigned":
            cases.update(assigned_to=None, last_activity_at=timezone.now())
            messages.success(request, f"Unassigned {count} case(s).")
        elif new_assignee_id:
            # Verify assignee is in the organization
            membership = org.memberships.filter(
                user_id=new_assignee_id,
                role__in=["admin", "caseworker"],
                is_active=True,
            ).first()
            if membership:
                cases.update(
                    assigned_to_id=new_assignee_id, last_activity_at=timezone.now()
                )
                messages.success(
                    request,
                    f"Reassigned {count} case(s) to {membership.user.get_full_name() or membership.user.email}.",
                )
            else:
                messages.error(request, "Invalid assignee selected.")
        else:
            messages.error(request, "No assignee selected.")

    elif action == "archive":
        # Only archive closed cases
        closed_cases = cases.filter(status__startswith="closed")
        archive_count = closed_cases.count()
        if archive_count > 0:
            closed_cases.update(is_archived=True, archived_at=timezone.now())
            messages.success(request, f"Archived {archive_count} closed case(s).")
            if archive_count < count:
                messages.warning(
                    request,
                    f"{count - archive_count} case(s) were not archived because they are not closed.",
                )
        else:
            messages.warning(
                request,
                "No closed cases to archive. Only closed cases can be archived.",
            )

    elif action == "update_priority":
        new_priority = request.POST.get("new_priority")
        if new_priority and new_priority in dict(VeteranCase.PRIORITY_CHOICES):
            cases.update(priority=new_priority, last_activity_at=timezone.now())
            messages.success(request, f"Updated priority for {count} case(s).")
        else:
            messages.error(request, "Invalid priority selected.")

    elif action == "export":
        # Export selected cases to CSV
        cases_list = list(cases)
        for case in cases_list:
            case.triage_label = GapCheckerService.get_triage_label(case)
            case.triage_display = GapCheckerService.get_triage_display(
                case.triage_label
            )
        return _export_cases_csv(cases_list, request=request, org=org)

    else:
        messages.error(request, "Invalid action.")

    return redirect("vso:case_list")


@vso_required
def case_detail(request, pk):
    """
    Detailed view of a single case
    """
    org = get_user_organization(request.user, request=request)
    if not org:
        return redirect("vso:dashboard")

    case = get_scoped_case_or_404(
        request.user,
        org,
        pk,
        queryset=VeteranCase.objects.select_related(
            "veteran", "assigned_to", "organization"
        ),
    )

    # Surfaced to the veteran on their data-activity page
    AuditLog.log(
        action="vso_case_view",
        request=request,
        resource_type="VeteranCase",
        resource_id=case.pk,
        details={"veteran_id": case.veteran_id, "organization_id": org.pk},
    )

    # Get related data
    notes = case.notes.select_related("author").order_by("-created_at")
    shared_docs = case.shared_documents.select_related("document", "shared_by")
    shared_analyses = case.shared_analyses.select_related("shared_by")
    checklists = case.checklists.prefetch_related("items")

    # Case conditions with evidence status
    case_conditions = case.case_conditions.all()

    # Group documents by type
    documents_by_type = {}
    for shared_doc in shared_docs:
        doc_type = getattr(shared_doc.document, "document_type", "other") or "other"
        if doc_type not in documents_by_type:
            documents_by_type[doc_type] = []
        documents_by_type[doc_type].append(shared_doc)

    # Triage label for the case
    triage_label = GapCheckerService.get_triage_label(case)
    triage_color = GapCheckerService.get_triage_color(triage_label)
    triage_display = GapCheckerService.get_triage_display(triage_label)

    # Action items (incomplete)
    action_items = case.notes.filter(
        is_action_item=True, action_completed=False
    ).order_by("action_due_date")

    # For C&P exam date display
    today = timezone.now().date()
    upcoming_threshold = today + timedelta(days=7)

    context = {
        "organization": org,
        "case": case,
        "notes": notes,
        "shared_documents": shared_docs,
        "shared_analyses": shared_analyses,
        "checklists": checklists,
        "action_items": action_items,
        "case_conditions": case_conditions,
        "documents_by_type": documents_by_type,
        "triage_label": triage_label,
        "triage_color": triage_color,
        "triage_display": triage_display,
        "status_choices": VeteranCase.STATUS_CHOICES,
        "priority_choices": VeteranCase.PRIORITY_CHOICES,
        "workflow_status_choices": CaseCondition.WORKFLOW_STATUS_CHOICES,
        "today": today,
        "upcoming_threshold": upcoming_threshold,
    }

    return render(request, "vso/case_detail.html", context)


@vso_required
@require_POST
def case_update_status(request, pk):
    """
    HTMX endpoint to update case status
    """
    org = get_user_organization(request.user, request=request)
    case = get_scoped_case_or_404(request.user, org, pk)

    # Archived cases are read-only
    if is_case_read_only(case):
        messages.error(request, "Archived cases cannot be modified.")
        return redirect("vso:case_detail", pk=pk)

    new_status = request.POST.get("status")
    if new_status and new_status in dict(VeteranCase.STATUS_CHOICES):
        old_status = case.status
        case.status = new_status

        # Handle closure
        if new_status.startswith("closed") and not old_status.startswith("closed"):
            case.closed_at = timezone.now()
            case.closed_by = request.user

        case.save()

        # Create note about status change
        CaseNote.objects.create(
            case=case,
            author=request.user,
            note_type="milestone",
            subject=f"Status changed to {case.get_status_display()}",
            content=f"Case status updated from {dict(VeteranCase.STATUS_CHOICES).get(old_status)} to {case.get_status_display()}",
            visible_to_veteran=True,
        )

        messages.success(request, f"Case status updated to {case.get_status_display()}")

    return redirect("vso:case_detail", pk=pk)


@vso_required
@require_POST
def case_archive(request, pk):
    """
    Archive a closed case.

    Only closed cases can be archived. Archived cases are hidden from
    the default case list but can still be accessed.
    """
    org = get_user_organization(request.user, request=request)
    case = get_scoped_case_or_404(request.user, org, pk)

    if case.status.startswith("closed"):
        case.is_archived = True
        case.archived_at = timezone.now()
        case.save()

        # Create audit note
        CaseNote.objects.create(
            case=case,
            author=request.user,
            note_type="milestone",
            subject="Case archived",
            content="Case was archived.",
            visible_to_veteran=False,
        )

        # Audit log
        AuditLog.log(
            action="vso_case_archive",
            request=request,
            resource_type="VeteranCase",
            resource_id=case.pk,
            details={
                "organization_id": org.pk,
                "organization_name": org.name,
                "case_title": case.title,
            },
            success=True,
        )

        messages.success(request, f'Case "{case.title}" has been archived.')
    else:
        messages.error(request, "Only closed cases can be archived.")

    return redirect("vso:case_list")


@vso_required
@require_POST
def add_case_note(request, pk):
    """
    Add a note to a case
    """
    org = get_user_organization(request.user, request=request)
    case = get_scoped_case_or_404(request.user, org, pk)

    # Archived cases are read-only
    if is_case_read_only(case):
        messages.error(request, "Archived cases cannot be modified.")
        return redirect("vso:case_detail", pk=pk)

    note_type = request.POST.get("note_type", "general")
    subject = request.POST.get("subject", "").strip()
    content = request.POST.get("content", "").strip()
    is_action_item = request.POST.get("is_action_item") == "on"
    action_due_date = request.POST.get("action_due_date") or None
    visible_to_veteran = request.POST.get("visible_to_veteran") == "on"

    if subject and content:
        CaseNote.objects.create(
            case=case,
            author=request.user,
            note_type=note_type,
            subject=subject,
            content=content,
            is_action_item=is_action_item,
            action_due_date=action_due_date,
            visible_to_veteran=visible_to_veteran,
        )
        messages.success(request, "Note added successfully.")
    else:
        messages.error(request, "Subject and content are required.")

    return redirect("vso:case_detail", pk=pk)


@vso_required
@require_POST
def complete_action_item(request, pk, note_pk):
    """
    Mark an action item as complete
    """
    org = get_user_organization(request.user, request=request)
    case = get_scoped_case_or_404(request.user, org, pk)

    # Archived cases are read-only
    if is_case_read_only(case):
        messages.error(request, "Archived cases cannot be modified.")
        return redirect("vso:case_detail", pk=pk)

    note = get_object_or_404(CaseNote, pk=note_pk, case=case, is_action_item=True)

    note.mark_complete(completed_by=request.user)
    messages.success(request, "Action item marked as complete.")

    return redirect("vso:case_detail", pk=pk)


@vso_required
def case_create(request):
    """
    Create a new case (invite a veteran or create from existing user)
    """
    org = get_user_organization(request.user, request=request)
    if not org:
        return redirect("vso:dashboard")

    if request.method == "POST":
        # Get form data
        title = request.POST.get("title", "").strip()
        description = request.POST.get("description", "").strip()
        veteran_email = request.POST.get("veteran_email", "").strip()
        priority = request.POST.get("priority", "normal")

        if not title or not veteran_email:
            messages.error(request, "Title and veteran email are required.")
            return render(request, "vso/case_create.html", {"organization": org})

        # Find or placeholder for veteran
        from django.contrib.auth import get_user_model

        User = get_user_model()

        veteran = User.objects.filter(email=veteran_email).first()

        if not veteran:
            # Create placeholder user (they'll need to accept invitation)
            # For now, require existing user
            messages.error(
                request,
                "Veteran not found. They must create an account first, "
                "or use the invitation system.",
            )
            return render(request, "vso/case_create.html", {"organization": org})

        # Create the case
        case = VeteranCase.objects.create(
            organization=org,
            veteran=veteran,
            assigned_to=request.user,
            title=title,
            description=description,
            priority=priority,
            status="intake",
            intake_date=timezone.now().date(),
        )

        # Create initial note
        CaseNote.objects.create(
            case=case,
            author=request.user,
            note_type="milestone",
            subject="Case created",
            content=f"New case created for {veteran.email}",
            visible_to_veteran=True,
        )

        # Audit log: VSO case creation
        AuditLog.log(
            action="vso_case_create",
            request=request,
            resource_type="VeteranCase",
            resource_id=case.pk,
            details={
                "organization_id": org.pk,
                "organization_name": org.name,
                "veteran_id": veteran.pk,
            },
            success=True,
        )

        messages.success(request, f'Case "{title}" created successfully.')
        return redirect("vso:case_detail", pk=case.pk)

    context = {
        "organization": org,
        "priority_choices": VeteranCase.PRIORITY_CHOICES,
    }
    return render(request, "vso/case_create.html", context)


@vso_required
def shared_document_review(request, pk, doc_pk):
    """
    Review a shared document with comprehensive AI analysis for VSO prep.
    """
    org = get_user_organization(request.user, request=request)
    case = get_scoped_case_or_404(request.user, org, pk)
    shared_doc = get_object_or_404(SharedDocument, pk=doc_pk, case=case)

    # Surfaced to the veteran on their data-activity page
    AuditLog.log(
        action="vso_document_review",
        request=request,
        resource_type="Document",
        resource_id=shared_doc.document_id,
        details={
            "event": "review_saved" if request.method == "POST" else "viewed",
            "case_id": case.pk,
            "veteran_id": case.veteran_id,
            "organization_id": org.pk,
            "include_ai_analysis": shared_doc.include_ai_analysis,
        },
    )

    if request.method == "POST":
        # Archived cases are read-only
        if is_case_read_only(case):
            messages.error(request, "Archived cases cannot be modified.")
            return redirect("vso:case_detail", pk=pk)

        status = request.POST.get("status", "reviewed")
        notes = request.POST.get("review_notes", "").strip()

        shared_doc.status = status
        shared_doc.review_notes = notes
        shared_doc.reviewed_by = request.user
        shared_doc.reviewed_at = timezone.now()
        shared_doc.save()

        # Create a note about the review
        CaseNote.objects.create(
            case=case,
            author=request.user,
            note_type="document_review",
            subject=f"Reviewed: {shared_doc.document.file_name}",
            content=notes if notes else "Document reviewed.",
            visible_to_veteran=False,
        )

        messages.success(request, "Document review saved.")
        return redirect("vso:case_detail", pk=pk)

    # Get the document and all available analyses
    document = shared_doc.document
    analysis_data = {}

    if shared_doc.include_ai_analysis:
        from agents.models import RatingAnalysis, DecisionLetterAnalysis, DenialDecoding

        # Defense-in-depth: verify the document belongs to the case veteran
        # before querying analyses, preventing cross-org data leakage
        if document.user_id == case.veteran_id:
            # Get rating analysis if available
            rating_analysis = RatingAnalysis.objects.filter(
                document=document, user=case.veteran
            ).first()
            if rating_analysis:
                analysis_data["rating"] = rating_analysis

            # Get decision letter analysis
            decision_analysis = DecisionLetterAnalysis.objects.filter(
                document=document, user=case.veteran
            ).first()
            if decision_analysis:
                analysis_data["decision"] = decision_analysis

            # Get denial decoding
            if decision_analysis:
                denial_decoding = DenialDecoding.objects.filter(
                    analysis=decision_analysis
                ).first()
                if denial_decoding:
                    analysis_data["denial"] = denial_decoding

    context = {
        "organization": org,
        "case": case,
        "shared_document": shared_doc,
        "document": document,
        "analysis_data": analysis_data,
        "status_choices": SharedDocument.SHARE_STATUS_CHOICES,
    }

    return render(request, "vso/shared_document_review.html", context)


# HTMX partial views


@vso_required
def case_notes_partial(request, pk):
    """
    HTMX partial for case notes list
    """
    org = get_user_organization(request.user, request=request)
    case = get_scoped_case_or_404(request.user, org, pk)
    notes = case.notes.select_related("author").order_by("-created_at")

    return render(
        request,
        "vso/partials/case_notes.html",
        {
            "case": case,
            "notes": notes,
        },
    )


@vso_required
def case_documents_partial(request, pk):
    """
    HTMX partial for shared documents list
    """
    org = get_user_organization(request.user, request=request)
    case = get_scoped_case_or_404(request.user, org, pk)
    shared_docs = case.shared_documents.select_related("document", "shared_by")

    return render(
        request,
        "vso/partials/case_documents.html",
        {
            "case": case,
            "shared_documents": shared_docs,
        },
    )


# ============================================================================
# Veteran Invitation System
# ============================================================================


@vso_required
def invite_veteran(request):
    """
    Invite a veteran to the organization's caseload.
    Creates an invitation and optionally a case.
    """
    from accounts.models import OrganizationInvitation

    org = get_user_organization(request.user, request=request)
    if not org:
        messages.error(request, "No active organization found.")
        return redirect("vso:dashboard")

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        case_title = request.POST.get("case_title", "").strip()
        case_description = request.POST.get("case_description", "").strip()
        priority = request.POST.get("priority", "normal")

        if not email:
            messages.error(request, "Email address is required.")
            return render(request, "vso/invite_veteran.html", {"organization": org})

        # Check if already invited (pending)
        existing_invite = OrganizationInvitation.objects.filter(
            organization=org,
            email=email,
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).first()

        if existing_invite:
            messages.warning(
                request,
                f"An invitation is already pending for {email}. "
                f'It expires on {existing_invite.expires_at.strftime("%B %d, %Y")}.',
            )
            return redirect("vso:invitations")

        # Check if veteran already has a case with this org
        from django.contrib.auth import get_user_model

        User = get_user_model()
        existing_user = User.objects.filter(email=email).first()

        if existing_user:
            existing_case = (
                VeteranCase.objects.filter(organization=org, veteran=existing_user)
                .exclude(status__startswith="closed")
                .first()
            )

            if existing_case:
                messages.warning(
                    request,
                    f'This veteran already has an active case: "{existing_case.title}". '
                    f'<a href="{existing_case.get_absolute_url()}" class="underline">View case</a>',
                )
                return redirect("vso:invitations")

        # Create the invitation
        invitation = OrganizationInvitation.objects.create(
            organization=org, email=email, role="veteran", invited_by=request.user
        )

        # Store case details in session for when invitation is accepted
        if case_title:
            request.session[f"pending_case_{invitation.token}"] = {
                "title": case_title,
                "description": case_description,
                "priority": priority,
                "invited_by_id": request.user.id,
            }

        # Send invitation email
        _send_veteran_invitation_email(invitation, case_title)

        messages.success(
            request,
            f"Invitation sent to {email}. They will receive an email with instructions.",
        )

        return redirect("vso:invitations")

    context = {
        "organization": org,
        "priority_choices": VeteranCase.PRIORITY_CHOICES,
    }
    return render(request, "vso/invite_veteran.html", context)


def _send_veteran_invitation_email(invitation, case_title=None):
    """
    Send invitation email to veteran.
    """
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.conf import settings
    from django.urls import reverse

    accept_url = f"{settings.SITE_URL}{reverse('vso:accept_invitation', args=[invitation.token])}"

    subject = f"You've been invited to work with {invitation.organization.name}"

    context = {
        "invitation": invitation,
        "accept_url": accept_url,
        "case_title": case_title,
        "expires_days": 7,
    }

    html_message = render_to_string("vso/emails/veteran_invitation.html", context)
    plain_message = render_to_string("vso/emails/veteran_invitation.txt", context)

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            html_message=html_message,
            fail_silently=False,
        )
    except Exception as e:
        # Log but don't fail - invitation is still created
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to send invitation email: {e}")


@vso_required
def invitations_list(request):
    """
    List all pending and recent invitations for the organization.
    """
    from accounts.models import OrganizationInvitation

    org = get_user_organization(request.user, request=request)
    if not org:
        return redirect("vso:dashboard")

    # Get pending invitations
    pending = OrganizationInvitation.objects.filter(
        organization=org, accepted_at__isnull=True, expires_at__gt=timezone.now()
    ).order_by("-created_at")

    # Get recent (last 30 days) accepted/expired
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    recent = (
        OrganizationInvitation.objects.filter(
            organization=org, created_at__gte=thirty_days_ago
        )
        .exclude(id__in=pending.values_list("id", flat=True))
        .order_by("-created_at")
    )

    context = {
        "organization": org,
        "pending_invitations": pending,
        "recent_invitations": recent,
    }

    return render(request, "vso/invitations_list.html", context)


@vso_required
@require_POST
def resend_invitation(request, token):
    """
    Resend an invitation email.
    """
    from accounts.models import OrganizationInvitation

    org = get_user_organization(request.user, request=request)
    invitation = get_object_or_404(
        OrganizationInvitation, token=token, organization=org, accepted_at__isnull=True
    )

    if invitation.is_expired:
        # Extend expiration
        invitation.expires_at = timezone.now() + timezone.timedelta(days=7)
        invitation.save()

    # Get case title from session if exists
    case_info = request.session.get(f"pending_case_{token}", {})
    case_title = case_info.get("title")

    _send_veteran_invitation_email(invitation, case_title)

    messages.success(request, f"Invitation resent to {invitation.email}.")
    return redirect("vso:invitations")


@vso_required
@require_POST
def cancel_invitation(request, token):
    """
    Cancel a pending invitation.
    """
    from accounts.models import OrganizationInvitation

    org = get_user_organization(request.user, request=request)
    invitation = get_object_or_404(
        OrganizationInvitation, token=token, organization=org, accepted_at__isnull=True
    )

    # Clean up session data
    if f"pending_case_{token}" in request.session:
        del request.session[f"pending_case_{token}"]

    invitation.delete()
    messages.success(request, f"Invitation to {invitation.email} has been cancelled.")
    return redirect("vso:invitations")


@login_required
def accept_invitation(request, token):
    """
    Accept a veteran invitation.
    This view is accessible to any logged-in user.
    """
    from accounts.models import OrganizationInvitation

    invitation = get_object_or_404(OrganizationInvitation, token=token)

    # Check if invitation is valid
    if invitation.accepted_at:
        messages.info(request, "This invitation has already been accepted.")
        # Check if they have a case
        case = VeteranCase.objects.filter(
            organization=invitation.organization, veteran=request.user
        ).first()
        if case:
            return redirect("claims:document_list")
        return redirect("claims:document_list")

    if invitation.is_expired:
        messages.error(
            request,
            "This invitation has expired. Please contact the organization for a new invitation.",
        )
        return redirect("home")

    # Verify email matches (or allow any authenticated user)
    if invitation.email.lower() != request.user.email.lower():
        messages.warning(
            request,
            f"This invitation was sent to {invitation.email}. "
            f"You are logged in as {request.user.email}. "
            f"Please log in with the correct account or contact the organization.",
        )
        return redirect("account_login")

    if request.method == "POST":
        try:
            # Accept the invitation, create the case, and log the milestone
            # note as one unit — a failure partway through must not leave an
            # accepted invitation with no case, or a case with no note.
            with transaction.atomic():
                invitation.accept(request.user)

                # Create case if details were stored
                case_info = request.session.get(f"pending_case_{token}", {})
                if case_info:
                    from django.contrib.auth import get_user_model

                    User = get_user_model()

                    invited_by = User.objects.filter(
                        id=case_info.get("invited_by_id")
                    ).first()

                    case = VeteranCase.objects.create(
                        organization=invitation.organization,
                        veteran=request.user,
                        assigned_to=invited_by,
                        title=case_info.get("title", f"Case for {request.user.email}"),
                        description=case_info.get("description", ""),
                        priority=case_info.get("priority", "normal"),
                        status="intake",
                        intake_date=timezone.now().date(),
                        veteran_consent_date=timezone.now(),
                    )

                    # Create initial note
                    CaseNote.objects.create(
                        case=case,
                        author=invited_by,
                        note_type="milestone",
                        subject="Veteran accepted invitation",
                        content=f"{request.user.email} accepted the invitation and joined the case.",
                        visible_to_veteran=True,
                    )

            # Clean up session (outside the DB transaction — session storage
            # isn't part of it, and this should only happen once the writes
            # above have actually committed).
            if case_info:
                del request.session[f"pending_case_{token}"]

            messages.success(
                request,
                f"Welcome! You are now connected with {invitation.organization.name}. "
                f"You can now share documents with your caseworker.",
            )

            return redirect("claims:document_list")

        except ValueError as e:
            messages.error(request, str(e))
            return redirect("home")

    context = {
        "invitation": invitation,
    }
    return render(request, "vso/accept_invitation.html", context)


# =============================================================================
# APPEAL INTEGRATION
# =============================================================================


@vso_required
@require_POST
def start_appeal_from_case(request, pk):
    """
    Start a new appeal linked to a VSO case.
    Pre-populates appeal with case information.
    """
    if requires_org_selection(request.user, request):
        return redirect("vso:select_organization")

    org = get_user_organization(request.user, request=request)
    if not org:
        messages.error(request, "Please select an organization to continue.")
        return redirect("vso:select_organization")

    case = get_scoped_case_or_404(request.user, org, pk)

    # Only allow starting appeals for denied cases or cases in appeal status
    if case.status not in ["closed_denied", "appeal_in_progress"]:
        messages.error(
            request,
            "Appeals can only be started for denied cases or cases already in appeal.",
        )
        return redirect("vso:case_detail", pk=pk)

    # Check if an appeal already exists for this case
    existing_appeal = Appeal.objects.filter(veteran_case=case).first()
    if existing_appeal:
        messages.info(
            request,
            "An appeal already exists for this case. Redirecting to the existing appeal.",
        )
        return redirect("appeals:appeal_detail", pk=existing_appeal.pk)

    # Create new appeal linked to the case
    appeal = Appeal.objects.create(
        user=case.veteran,
        veteran_case=case,
        status="deciding",
        original_decision_date=case.decision_date,
        conditions_appealed=(
            ", ".join([c.condition_name for c in case.conditions.all()])
            if case.conditions.exists()
            else ""
        ),
    )

    # Update case status if not already in appeal
    if case.status == "closed_denied":
        case.status = "appeal_in_progress"
        case.save(update_fields=["status"])

    # Add case note
    CaseNote.objects.create(
        case=case,
        author=request.user,
        note_type="milestone",
        subject="Appeal started",
        content=f"Appeal process initiated. Appeal ID: {appeal.pk}",
        visible_to_veteran=True,
    )

    messages.success(request, "Appeal started successfully.")
    return redirect("appeals:appeal_detail", pk=appeal.pk)


# =============================================================================
# REPORTING
# =============================================================================


@vso_required
def reports(request):
    """
    VSO Reporting page - Cases by status, time to close, caseworker workload
    """
    if requires_org_selection(request.user, request):
        return redirect("vso:select_organization")

    org = get_user_organization(request.user, request=request)
    if not org:
        messages.error(request, "Please select an organization to continue.")
        return redirect("vso:select_organization")

    # Get all cases for this organization (excluding archived, least-privilege scoped)
    cases = scope_cases_for_member(
        request.user,
        org,
        VeteranCase.objects.filter(organization=org, is_archived=False),
    )

    # --- Cases by Status ---
    status_breakdown = list(
        cases.values("status").annotate(count=Count("id")).order_by("status")
    )
    # Map to display labels
    status_labels = dict(VeteranCase.STATUS_CHOICES)
    for item in status_breakdown:
        item["label"] = status_labels.get(item["status"], item["status"])

    # --- Time to Close (for closed cases) ---
    closed_cases = cases.filter(status__startswith="closed", closed_at__isnull=False)

    # Calculate average days to close
    avg_days_to_close = None
    if closed_cases.exists():
        # Use database aggregation where possible
        # For SQLite, we need to calculate in Python
        days_list = []
        for case in closed_cases:
            if case.closed_at and case.intake_date:
                days = (case.closed_at.date() - case.intake_date).days
                days_list.append(days)
        if days_list:
            avg_days_to_close = sum(days_list) / len(days_list)

    # Time to close by month (last 6 months)
    monthly_closures = []
    for i in range(6):
        month_start = (timezone.now() - timedelta(days=30 * (5 - i))).replace(day=1)
        if i < 5:
            next_month = (month_start + timedelta(days=32)).replace(day=1)
        else:
            next_month = timezone.now() + timedelta(days=1)

        month_cases = closed_cases.filter(
            closed_at__gte=month_start, closed_at__lt=next_month
        )
        count = month_cases.count()
        monthly_closures.append(
            {
                "month": month_start.strftime("%b %Y"),
                "count": count,
            }
        )

    # --- Caseworker Workload ---
    # Urgent/overdue counts are computed as conditional aggregates in the same
    # query as open_cases, instead of a separate pair of .count() queries per
    # caseworker (that scaled as O(caseworkers) query count).
    caseworker_workload = list(
        cases.exclude(status__startswith="closed")
        .values(
            "assigned_to__email", "assigned_to__first_name", "assigned_to__last_name"
        )
        .annotate(
            open_cases=Count("id"),
            urgent_count=Count("id", filter=Q(priority="urgent")),
            overdue_count=Count(
                "id", filter=Q(next_action_date__lt=timezone.now().date())
            ),
        )
        .order_by("-open_cases")
    )
    # Add display name
    for item in caseworker_workload:
        if item["assigned_to__first_name"] and item["assigned_to__last_name"]:
            item["name"] = (
                f"{item['assigned_to__first_name']} {item['assigned_to__last_name']}"
            )
        elif item["assigned_to__email"]:
            item["name"] = item["assigned_to__email"]
        else:
            item["name"] = "Unassigned"

    # --- Win Rate by Month ---
    win_rate_by_month = []
    for i in range(6):
        month_start = (timezone.now() - timedelta(days=30 * (5 - i))).replace(day=1)
        if i < 5:
            next_month = (month_start + timedelta(days=32)).replace(day=1)
        else:
            next_month = timezone.now() + timedelta(days=1)

        month_closed = closed_cases.filter(
            closed_at__gte=month_start, closed_at__lt=next_month
        )
        total = month_closed.count()
        won = month_closed.filter(status="closed_won").count()
        rate = (won / total * 100) if total > 0 else 0

        win_rate_by_month.append(
            {
                "month": month_start.strftime("%b %Y"),
                "total": total,
                "won": won,
                "rate": round(rate, 1),
            }
        )

    # --- Summary Stats ---
    total_open = cases.exclude(status__startswith="closed").count()
    total_closed_all_time = closed_cases.count()
    total_won = closed_cases.filter(status="closed_won").count()
    overall_win_rate = (
        (total_won / total_closed_all_time * 100) if total_closed_all_time > 0 else 0
    )

    context = {
        "organization": org,
        "status_breakdown": status_breakdown,
        "avg_days_to_close": round(avg_days_to_close, 1) if avg_days_to_close else None,
        "monthly_closures": monthly_closures,
        "caseworker_workload": caseworker_workload,
        "win_rate_by_month": win_rate_by_month,
        "total_open": total_open,
        "total_closed": total_closed_all_time,
        "total_won": total_won,
        "overall_win_rate": round(overall_win_rate, 1),
    }

    # Handle exports
    export_format = request.GET.get("export")
    if export_format == "csv":
        return _export_reports_csv(org, context, request=request)
    elif export_format == "pdf":
        return _export_reports_pdf(org, context, request=request)

    return render(request, "vso/reports.html", context)


def _export_reports_csv(org, data, request=None):
    """Export reports data to CSV (Excel-compatible) format with audit logging."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="{org.slug}_report_{timezone.now().strftime("%Y%m%d")}.csv"'
    )

    # Audit log the export
    if request and request.user.is_authenticated:
        AuditLog.log(
            action="vso_report_export",
            request=request,
            resource_type="Organization",
            resource_id=org.pk,
            details={
                "organization": org.slug,
                "format": "csv",
                "total_open": data.get("total_open"),
                "total_closed": data.get("total_closed"),
            },
        )

    writer = csv.writer(response)

    # Summary Stats
    writer.writerow(["ORGANIZATION REPORT"])
    writer.writerow(
        [org.name, f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M")}']
    )
    writer.writerow([])

    writer.writerow(["SUMMARY STATISTICS"])
    writer.writerow(["Metric", "Value"])
    writer.writerow(["Open Cases", data["total_open"]])
    writer.writerow(["Total Closed", data["total_closed"]])
    writer.writerow(["Cases Won", data["total_won"]])
    writer.writerow(["Overall Win Rate", f"{data['overall_win_rate']}%"])
    if data["avg_days_to_close"]:
        writer.writerow(["Avg Days to Close", data["avg_days_to_close"]])
    writer.writerow([])

    # Cases by Status
    writer.writerow(["CASES BY STATUS"])
    writer.writerow(["Status", "Count"])
    for item in data["status_breakdown"]:
        writer.writerow([item["label"], item["count"]])
    writer.writerow([])

    # Monthly Closures
    writer.writerow(["CLOSURES BY MONTH"])
    writer.writerow(["Month", "Count"])
    for item in data["monthly_closures"]:
        writer.writerow([item["month"], item["count"]])
    writer.writerow([])

    # Win Rate by Month
    writer.writerow(["WIN RATE BY MONTH"])
    writer.writerow(["Month", "Won", "Total", "Win Rate"])
    for item in data["win_rate_by_month"]:
        writer.writerow([item["month"], item["won"], item["total"], f"{item['rate']}%"])
    writer.writerow([])

    # Caseworker Workload
    writer.writerow(["CASEWORKER WORKLOAD"])
    writer.writerow(["Caseworker", "Open Cases", "Urgent", "Overdue"])
    for item in data["caseworker_workload"]:
        writer.writerow(
            [
                item["name"],
                item["open_cases"],
                item["urgent_count"],
                item["overdue_count"],
            ]
        )

    return response


def _export_reports_pdf(org, data, request=None):
    """Export reports data to PDF format for board presentations with audit logging."""
    # Audit log the export
    if request and request.user.is_authenticated:
        AuditLog.log(
            action="vso_report_export",
            request=request,
            resource_type="Organization",
            resource_id=org.pk,
            details={
                "organization": org.slug,
                "format": "pdf",
                "total_open": data.get("total_open"),
                "total_closed": data.get("total_closed"),
            },
        )

    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate,
        Paragraph,
        Spacer,
        Table,
        TableStyle,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, topMargin=0.75 * inch, bottomMargin=0.75 * inch
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=20,
    )
    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        spaceBefore=20,
        spaceAfter=10,
    )

    elements = []

    # Title
    elements.append(Paragraph(f"{org.name} - Performance Report", title_style))
    elements.append(
        Paragraph(
            f"Generated: {timezone.now().strftime('%B %d, %Y')}", styles["Normal"]
        )
    )
    elements.append(Spacer(1, 20))

    # Summary Statistics Table
    elements.append(Paragraph("Summary Statistics", heading_style))
    summary_data = [
        ["Metric", "Value"],
        ["Open Cases", str(data["total_open"])],
        ["Total Closed", str(data["total_closed"])],
        ["Cases Won", str(data["total_won"])],
        ["Overall Win Rate", f"{data['overall_win_rate']}%"],
    ]
    if data["avg_days_to_close"]:
        summary_data.append(["Avg Days to Close", str(data["avg_days_to_close"])])

    summary_table = Table(summary_data, colWidths=[3 * inch, 2 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 11),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
                ("FONTSIZE", (0, 1), (-1, -1), 10),
                ("TOPPADDING", (0, 1), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
            ]
        )
    )
    elements.append(summary_table)
    elements.append(Spacer(1, 20))

    # Cases by Status
    if data["status_breakdown"]:
        elements.append(Paragraph("Cases by Status", heading_style))
        status_data = [["Status", "Count"]]
        for item in data["status_breakdown"]:
            status_data.append([item["label"], str(item["count"])])

        status_table = Table(status_data, colWidths=[3 * inch, 1.5 * inch])
        status_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (1, 0), (1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                    ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("TOPPADDING", (0, 1), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
                ]
            )
        )
        elements.append(status_table)
        elements.append(Spacer(1, 20))

    # Win Rate by Month
    if data["win_rate_by_month"]:
        elements.append(Paragraph("Win Rate Trend (Last 6 Months)", heading_style))
        win_data = [["Month", "Won", "Total", "Win Rate"]]
        for item in data["win_rate_by_month"]:
            win_data.append(
                [
                    item["month"],
                    str(item["won"]),
                    str(item["total"]),
                    f"{item['rate']}%",
                ]
            )

        win_table = Table(
            win_data, colWidths=[1.5 * inch, 1 * inch, 1 * inch, 1.5 * inch]
        )
        win_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                    ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("TOPPADDING", (0, 1), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
                ]
            )
        )
        elements.append(win_table)
        elements.append(Spacer(1, 20))

    # Caseworker Workload
    if data["caseworker_workload"]:
        elements.append(Paragraph("Caseworker Workload", heading_style))
        workload_data = [["Caseworker", "Open Cases", "Urgent", "Overdue"]]
        for item in data["caseworker_workload"]:
            workload_data.append(
                [
                    item["name"],
                    str(item["open_cases"]),
                    str(item["urgent_count"]),
                    str(item["overdue_count"]),
                ]
            )

        workload_table = Table(
            workload_data, colWidths=[2.5 * inch, 1.2 * inch, 1 * inch, 1 * inch]
        )
        workload_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e40af")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("ALIGN", (1, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, 0), 11),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
                    ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                    ("GRID", (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
                    ("FONTSIZE", (0, 1), (-1, -1), 10),
                    ("TOPPADDING", (0, 1), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 1), (-1, -1), 8),
                ]
            )
        )
        elements.append(workload_table)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    response = HttpResponse(buffer, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="{org.slug}_report_{timezone.now().strftime("%Y%m%d")}.pdf"'
    )
    return response


# =============================================================================
# ORGANIZATION ADMIN
# =============================================================================


def org_admin_required(view_func):
    """Decorator that requires user to be an org admin."""
    from functools import wraps

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("account_login")

        org = get_user_organization(request.user, request=request)
        if not org:
            messages.error(request, "Please select an organization.")
            return redirect("vso:select_organization")

        membership = get_user_organization_membership(request.user, org)
        if not membership or membership.role != "admin":
            messages.error(
                request,
                "You must be an organization administrator to access this page.",
            )
            return redirect("vso:dashboard")

        return view_func(request, *args, **kwargs)

    return wrapper


@org_admin_required
def org_admin_dashboard(request):
    """
    Organization admin dashboard - member management and usage analytics.
    """
    org = get_user_organization(request.user, request=request)

    # Get all memberships for this org
    memberships = (
        OrganizationMembership.objects.filter(organization=org)
        .select_related("user", "invited_by")
        .order_by("role", "user__email")
    )

    active_members = memberships.filter(is_active=True)
    inactive_members = memberships.filter(is_active=False)

    # Pending invitations
    pending_invitations = OrganizationInvitation.objects.filter(
        organization=org, accepted_at__isnull=True, expires_at__gt=timezone.now()
    ).order_by("-created_at")

    # Usage analytics
    cases = VeteranCase.objects.filter(organization=org)
    total_cases = cases.count()
    cases_this_month = cases.filter(
        created_at__gte=timezone.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    ).count()

    # Shared documents count
    shared_docs = SharedDocument.objects.filter(case__organization=org)
    total_shared_docs = shared_docs.count()
    docs_this_month = shared_docs.filter(
        shared_at__gte=timezone.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    ).count()

    # Shared analyses count
    shared_analyses = SharedAnalysis.objects.filter(case__organization=org)
    total_analyses = shared_analyses.count()
    analyses_this_month = shared_analyses.filter(
        shared_at__gte=timezone.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
    ).count()

    # Member counts by role
    role_counts = {
        "admin": active_members.filter(role="admin").count(),
        "caseworker": active_members.filter(role="caseworker").count(),
        "veteran": active_members.filter(role="veteran").count(),
    }

    context = {
        "organization": org,
        "active_members": active_members,
        "inactive_members": inactive_members,
        "pending_invitations": pending_invitations,
        "role_counts": role_counts,
        "total_cases": total_cases,
        "cases_this_month": cases_this_month,
        "total_shared_docs": total_shared_docs,
        "docs_this_month": docs_this_month,
        "total_analyses": total_analyses,
        "analyses_this_month": analyses_this_month,
        "seats_used": org.seats_used,
        "seats_total": org.seats,
        "seats_remaining": org.seats_remaining,
    }

    return render(request, "vso/org_admin.html", context)


@org_admin_required
@require_POST
def org_admin_change_role(request, membership_id):
    """Change a member's role."""
    org = get_user_organization(request.user, request=request)

    membership = get_object_or_404(
        OrganizationMembership, pk=membership_id, organization=org
    )

    # Can't change own role
    if membership.user == request.user:
        messages.error(request, "You cannot change your own role.")
        return redirect("vso:org_admin")

    new_role = request.POST.get("role")
    if new_role not in ["admin", "caseworker", "veteran"]:
        messages.error(request, "Invalid role specified.")
        return redirect("vso:org_admin")

    old_role = membership.role
    membership.role = new_role
    membership.save(update_fields=["role", "updated_at"])

    messages.success(
        request,
        f"Changed {membership.user.email}'s role from {old_role} to {new_role}.",
    )
    return redirect("vso:org_admin")


@org_admin_required
@require_POST
def org_admin_deactivate_member(request, membership_id):
    """Deactivate a member."""
    org = get_user_organization(request.user, request=request)

    membership = get_object_or_404(
        OrganizationMembership, pk=membership_id, organization=org
    )

    # Can't deactivate self
    if membership.user == request.user:
        messages.error(request, "You cannot deactivate yourself.")
        return redirect("vso:org_admin")

    membership.deactivate(deactivated_by=request.user)

    messages.success(request, f"Deactivated {membership.user.email}'s membership.")
    return redirect("vso:org_admin")


@org_admin_required
@require_POST
def org_admin_reactivate_member(request, membership_id):
    """Reactivate a member."""
    org = get_user_organization(request.user, request=request)

    membership = get_object_or_404(
        OrganizationMembership, pk=membership_id, organization=org, is_active=False
    )

    try:
        membership.reactivate()
        messages.success(request, f"Reactivated {membership.user.email}'s membership.")
    except ValueError as e:
        messages.error(request, str(e))

    return redirect("vso:org_admin")


@org_admin_required
def org_admin_invite_staff(request):
    """Invite a new staff member (admin or caseworker)."""
    org = get_user_organization(request.user, request=request)

    if request.method == "POST":
        email = request.POST.get("email", "").strip().lower()
        role = request.POST.get("role", "caseworker")

        if not email:
            messages.error(request, "Email is required.")
            return redirect("vso:org_admin_invite_staff")

        if role not in ["admin", "caseworker"]:
            messages.error(request, "Invalid role. Staff must be admin or caseworker.")
            return redirect("vso:org_admin_invite_staff")

        # Check if already a member
        existing = OrganizationMembership.objects.filter(
            organization=org, user__email=email
        ).first()
        if existing:
            messages.error(
                request, f"{email} is already a member of this organization."
            )
            return redirect("vso:org_admin")

        # Check seat limit
        if org.is_at_seat_limit:
            messages.error(request, "Organization has reached its seat limit.")
            return redirect("vso:org_admin")

        # Check for existing pending invitation
        existing_invite = OrganizationInvitation.objects.filter(
            organization=org,
            email=email,
            accepted_at__isnull=True,
            expires_at__gt=timezone.now(),
        ).first()

        if existing_invite:
            messages.warning(
                request, f"A pending invitation already exists for {email}."
            )
            return redirect("vso:org_admin")

        # Create invitation
        OrganizationInvitation.objects.create(
            organization=org,
            email=email,
            role=role,
            invited_by=request.user,
            expires_at=timezone.now() + timedelta(days=7),
        )

        # TODO: Send email notification
        messages.success(
            request,
            f"Invitation sent to {email} as {role}. They have 7 days to accept.",
        )
        return redirect("vso:org_admin")

    context = {
        "organization": org,
    }
    return render(request, "vso/org_admin_invite_staff.html", context)


# =============================================================================
# EVIDENCE PACKET BUILDER
# =============================================================================


@vso_required
def evidence_packet_builder(request, pk):
    """
    Evidence packet builder - organize documents by condition for VA submission.
    """
    org = get_user_organization(request.user, request=request)
    if not org:
        return redirect("vso:dashboard")

    case = get_scoped_case_or_404(
        request.user,
        org,
        pk,
        queryset=VeteranCase.objects.select_related("veteran", "organization"),
    )

    # Get case conditions
    conditions = case.case_conditions.all()

    # Get shared documents
    shared_docs = case.shared_documents.select_related("document").order_by(
        "document__document_type"
    )

    # Organize documents by condition based on tags/notes
    # For now, we'll let users manually assign documents to conditions
    documents_list = []
    for sd in shared_docs:
        doc_data = {
            "id": sd.id,
            "document": sd.document,
            "title": sd.document.title if sd.document else "Untitled",
            "document_type": sd.document.document_type if sd.document else "other",
            "uploaded_at": sd.document.uploaded_at if sd.document else sd.shared_at,
            "shared_at": sd.shared_at,
            "vso_notes": sd.vso_notes,
            "review_status": sd.review_status,
            # Which conditions this document supports (stored in vso_notes as JSON or comma-separated)
            "assigned_conditions": [],
        }
        documents_list.append(doc_data)

    # Build evidence checklist per condition
    evidence_checklist = []
    for condition in conditions:
        checklist_item = {
            "condition": condition,
            "has_diagnosis": condition.has_diagnosis,
            "has_nexus": condition.has_nexus,
            "has_in_service_event": condition.has_in_service_event,
            "is_complete": condition.is_evidence_complete,
            "gap_count": condition.gap_count,
        }
        evidence_checklist.append(checklist_item)

    # Calculate completion stats
    conditions_complete = sum(1 for item in evidence_checklist if item["is_complete"])
    conditions_total = len(evidence_checklist)
    completion_percentage = (
        (conditions_complete / conditions_total * 100) if conditions_total > 0 else 0
    )

    context = {
        "organization": org,
        "case": case,
        "conditions": conditions,
        "documents": documents_list,
        "evidence_checklist": evidence_checklist,
        "document_types": SharedDocument.REVIEW_STATUS_CHOICES,
        "conditions_complete": conditions_complete,
        "conditions_total": conditions_total,
        "completion_percentage": round(completion_percentage),
    }

    return render(request, "vso/evidence_packet_builder.html", context)
