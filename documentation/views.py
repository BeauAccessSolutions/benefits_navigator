"""
Views for the documentation app.

Provides searchable documentation for VA forms, C&P exam guides, and legal references.
"""

from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.paginator import Paginator
from django.conf import settings

from .models import DocumentCategory, VAForm, CPExamGuideCondition, LegalReference


def feature_required(view_func):
    """Decorator to check if doc_search feature is enabled."""

    def wrapper(request, *args, **kwargs):
        if not settings.FEATURES.get("doc_search", True):
            from django.http import Http404

            raise Http404("Documentation feature is not enabled")
        return view_func(request, *args, **kwargs)

    return wrapper


# =============================================================================
# SEARCH VIEWS
# =============================================================================


@feature_required
def search_view(request):
    """Main documentation search page."""
    query = request.GET.get("q", "").strip()
    category_filter = request.GET.get("category", "")

    categories = DocumentCategory.objects.filter(is_active=True)

    context = {
        "query": query,
        "categories": categories,
        "category_filter": category_filter,
    }

    if query:
        # Perform search across all content types
        context["forms"] = search_forms(query)[:5]
        context["exam_guides"] = search_exam_guides(query)[:5]
        context["legal_refs"] = search_legal_references(query)[:5]
        context["has_results"] = (
            context["forms"].exists()
            or context["exam_guides"].exists()
            or context["legal_refs"].exists()
        )

    return render(request, "documentation/search.html", context)


@feature_required
def search_results_htmx(request):
    """HTMX endpoint for live search results."""
    query = request.GET.get("q", "").strip()
    content_type = request.GET.get("type", "all")

    results = {
        "query": query,
        "forms": [],
        "exam_guides": [],
        "legal_refs": [],
    }

    if query and len(query) >= 2:
        if content_type in ["all", "forms"]:
            results["forms"] = search_forms(query)[:10]
        if content_type in ["all", "exam_guides"]:
            results["exam_guides"] = search_exam_guides(query)[:10]
        if content_type in ["all", "legal"]:
            results["legal_refs"] = search_legal_references(query)[:10]

    return render(request, "documentation/partials/search_results.html", results)


def search_forms(query):
    """Search VA forms. Uses PostgreSQL full-text search if available, falls back to icontains."""
    from django.db import connection

    # Fall back to simple search for SQLite (tests) or if query has special chars
    if connection.vendor != "postgresql" or not query.replace(" ", "").isalnum():
        return (
            VAForm.objects.filter(is_active=True)
            .filter(
                Q(form_number__icontains=query)
                | Q(title__icontains=query)
                | Q(description__icontains=query)
            )
            .order_by("form_number")
        )

    # PostgreSQL full-text search
    search_query = SearchQuery(query)
    return (
        VAForm.objects.filter(is_active=True)
        .annotate(rank=SearchRank("search_vector", search_query))
        .filter(
            Q(search_vector=search_query)
            | Q(form_number__icontains=query)
            | Q(title__icontains=query)
        )
        .order_by("-rank")
    )


def search_exam_guides(query):
    """Search C&P exam guides. Uses PostgreSQL full-text search if available."""
    from django.db import connection

    if connection.vendor != "postgresql" or not query.replace(" ", "").isalnum():
        return (
            CPExamGuideCondition.objects.filter(is_published=True)
            .filter(
                Q(condition_name__icontains=query) | Q(what_to_expect__icontains=query)
            )
            .order_by("condition_name")
        )

    search_query = SearchQuery(query)
    return (
        CPExamGuideCondition.objects.filter(is_published=True)
        .annotate(rank=SearchRank("search_vector", search_query))
        .filter(Q(search_vector=search_query) | Q(condition_name__icontains=query))
        .order_by("-rank")
    )


def search_legal_references(query):
    """Search legal references. Uses PostgreSQL full-text search if available."""
    from django.db import connection

    if connection.vendor != "postgresql" or not query.replace(" ", "").isalnum():
        return (
            LegalReference.objects.filter(is_active=True)
            .filter(
                Q(citation__icontains=query)
                | Q(short_name__icontains=query)
                | Q(summary__icontains=query)
            )
            .order_by("citation")
        )

    search_query = SearchQuery(query)
    return (
        LegalReference.objects.filter(is_active=True)
        .annotate(rank=SearchRank("search_vector", search_query))
        .filter(
            Q(search_vector=search_query)
            | Q(citation__icontains=query)
            | Q(short_name__icontains=query)
        )
        .order_by("-rank")
    )


# =============================================================================
# VA FORM VIEWS
# =============================================================================


@feature_required
def form_list(request):
    """List all VA forms, optionally filtered by workflow stage."""
    from django.db import connection

    workflow_stage = request.GET.get("stage", "")

    forms = VAForm.objects.filter(is_active=True)

    if workflow_stage:
        # JSON contains lookup not supported in SQLite
        if connection.vendor == "postgresql":
            forms = forms.filter(workflow_stages__contains=[workflow_stage])
        else:
            # Fallback: filter in Python for SQLite (tests)
            form_ids = [
                f.pk for f in forms if workflow_stage in (f.workflow_stages or [])
            ]
            forms = forms.filter(pk__in=form_ids)

    # Group by category
    categories = (
        DocumentCategory.objects.filter(is_active=True, forms__in=forms)
        .distinct()
        .prefetch_related("forms")
    )

    # Get uncategorized forms
    uncategorized = forms.filter(category__isnull=True)

    context = {
        "categories": categories,
        "uncategorized_forms": uncategorized,
        "workflow_stage": workflow_stage,
        "workflow_choices": VAForm.WORKFLOW_STAGES,
    }

    return render(request, "documentation/form_list.html", context)


@feature_required
def form_detail(request, form_number):
    """Display details for a specific VA form."""
    form = get_object_or_404(VAForm, form_number=form_number, is_active=True)

    context = {
        "form": form,
        "related_forms": form.related_forms.filter(is_active=True),
        "exam_guides": form.exam_guides.filter(is_published=True),
    }

    return render(request, "documentation/form_detail.html", context)


# =============================================================================
# C&P EXAM GUIDE VIEWS
# =============================================================================


@feature_required
def exam_guide_list(request):
    """List all C&P exam guides, optionally filtered by category."""
    category = request.GET.get("category", "")

    guides = CPExamGuideCondition.objects.filter(is_published=True)

    if category:
        guides = guides.filter(category=category)

    # Group by category
    grouped_guides = {}
    for guide in guides:
        cat_display = guide.get_category_display()
        if cat_display not in grouped_guides:
            grouped_guides[cat_display] = []
        grouped_guides[cat_display].append(guide)

    context = {
        "grouped_guides": grouped_guides,
        "category_filter": category,
        "category_choices": CPExamGuideCondition.CONDITION_CATEGORIES,
    }

    return render(request, "documentation/exam_guide_list.html", context)


@feature_required
def exam_guide_detail(request, slug):
    """Display details for a specific C&P exam guide."""
    guide = get_object_or_404(CPExamGuideCondition, slug=slug, is_published=True)

    context = {
        "guide": guide,
        "related_conditions": guide.related_conditions.filter(is_published=True),
        "related_form": guide.related_form,
    }

    return render(request, "documentation/exam_guide_detail.html", context)


# =============================================================================
# LEGAL REFERENCE VIEWS
# =============================================================================


@feature_required
def legal_reference_list(request):
    """List all legal references with disclaimer."""
    ref_type = request.GET.get("type", "")

    references = LegalReference.objects.filter(is_active=True)

    if ref_type:
        references = references.filter(reference_type=ref_type)

    paginator = Paginator(references, 20)
    page = request.GET.get("page", 1)
    references_page = paginator.get_page(page)

    context = {
        "references": references_page,
        "type_filter": ref_type,
        "type_choices": LegalReference.REFERENCE_TYPES,
        "disclaimer": LegalReference().disclaimer,
    }

    return render(request, "documentation/legal_reference_list.html", context)


@feature_required
def legal_reference_detail(request, pk):
    """Display details for a specific legal reference with disclaimer."""
    reference = get_object_or_404(LegalReference, pk=pk, is_active=True)

    context = {
        "reference": reference,
        "supersedes": reference.supersedes.all(),
    }

    return render(request, "documentation/legal_reference_detail.html", context)
