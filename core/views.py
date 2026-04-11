"""
Core views - Home page and shared views
"""

from datetime import date

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django_ratelimit.decorators import ratelimit

from .models import UserJourneyEvent, JourneyMilestone, Deadline
from .journey import TimelineBuilder


def home(request):
    """
    Home page view - landing page for the VA Benefits Navigator
    """
    context = {
        'page_title': 'Welcome to VA Benefits Navigator',
    }
    return render(request, 'core/home.html', context)


@login_required
def dashboard(request):
    """
    User dashboard - central hub showing all user activity
    """
    user = request.user

    # Get user's documents (most recent 5)
    documents = []
    if hasattr(user, 'documents'):
        documents = user.documents.filter(is_deleted=False).order_by('-created_at')[:5]

    # Get user's exam checklists
    checklists = []
    if hasattr(user, 'exam_checklists'):
        checklists = user.exam_checklists.all().order_by('-created_at')[:5]

    # Get user's appeals
    appeals = []
    if hasattr(user, 'appeals'):
        appeals = user.appeals.all().order_by('-created_at')[:5]

    # Calculate stats
    total_documents = user.documents.filter(is_deleted=False).count() if hasattr(user, 'documents') else 0
    total_checklists = user.exam_checklists.count() if hasattr(user, 'exam_checklists') else 0
    total_appeals = user.appeals.count() if hasattr(user, 'appeals') else 0

    # Get upcoming exams (checklists with exam dates in the future)
    from datetime import date
    upcoming_exams = []
    if hasattr(user, 'exam_checklists'):
        upcoming_exams = user.exam_checklists.filter(
            exam_date__gte=date.today(),
            exam_completed=False
        ).order_by('exam_date')[:3]

    # Get pending appeals
    pending_appeals = []
    if hasattr(user, 'appeals'):
        pending_appeals = user.appeals.exclude(
            status__in=['decided', 'closed']
        ).order_by('-created_at')[:3]

    context = {
        'page_title': 'My Dashboard',
        'documents': documents,
        'checklists': checklists,
        'appeals': appeals,
        'total_documents': total_documents,
        'total_checklists': total_checklists,
        'total_appeals': total_appeals,
        'upcoming_exams': upcoming_exams,
        'pending_appeals': pending_appeals,
    }
    return render(request, 'core/dashboard.html', context)


# =============================================================================
# JOURNEY DASHBOARD VIEWS
# =============================================================================

@login_required
def journey_dashboard(request):
    """
    Claims journey dashboard - visual timeline and progress tracking.
    """
    builder = TimelineBuilder(request.user)

    # Get timeline (limit to recent 20 events)
    timeline = builder.build_timeline(limit=20)

    # Get current stage
    current_stage = builder.get_current_stage()

    # Get upcoming deadlines (next 90 days)
    deadlines = builder.get_upcoming_deadlines(days=90)

    # Get stats
    stats = builder.get_stats()

    # Get milestones for display
    milestones = JourneyMilestone.objects.filter(
        user=request.user
    ).order_by('-date')[:5]

    context = {
        'page_title': 'My Claims Journey',
        'timeline': timeline,
        'current_stage': current_stage,
        'deadlines': deadlines,
        'stats': stats,
        'milestones': milestones,
    }
    return render(request, 'core/journey_dashboard.html', context)


@login_required
def journey_timeline_partial(request):
    """
    HTMX endpoint for refreshing the timeline.
    """
    builder = TimelineBuilder(request.user)
    timeline = builder.build_timeline(limit=20)

    return render(request, 'core/partials/journey_timeline.html', {
        'timeline': timeline,
    })


@login_required
@ratelimit(key='user', rate='60/m', method='GET', block=True)
def claim_progress(request):
    """
    Claim progress dashboard - shows readiness score and next steps.
    Helps veterans understand where they are in the claims process.

    Rate limited to 60/min per user to prevent resource exhaustion.
    """
    user = request.user

    # Get counts for progress calculation — single annotated query (6 COUNTs → 1 DB round-trip)
    from django.db.models import Count, Q
    from claims.models import Document
    from agents.models import (
        DecisionLetterAnalysis, EvidenceGapAnalysis,
        PersonalStatement, RatingAnalysis
    )

    user_data = (
        type(user).objects
        .filter(pk=user.pk)
        .annotate(
            doc_count=Count('documents', filter=Q(documents__is_deleted=False), distinct=True),
            decision_count=Count('decision_analyses', distinct=True),
            rating_count=Count('rating_analyses', distinct=True),
            evidence_count=Count('evidence_analyses', distinct=True),
            statement_count=Count('personal_statements', distinct=True),
            exam_count=Count('exam_checklists', distinct=True),
        )
        .first()
    )
    total_documents = user_data.doc_count
    decision_analyses = user_data.decision_count
    rating_analyses = user_data.rating_count
    evidence_analyses = user_data.evidence_count
    statements_generated = user_data.statement_count
    exam_checklists = user_data.exam_count

    # Recent documents for activity feed (separate query — fetches full rows for template)
    recent_documents = Document.objects.filter(
        user=user, is_deleted=False
    ).order_by('-created_at')[:5]

    # Most recent evidence gap analysis for recommendations
    latest_evidence_gap = EvidenceGapAnalysis.objects.filter(user=user).order_by('-created_at').first()
    evidence_readiness_score = latest_evidence_gap.readiness_score if latest_evidence_gap else None
    evidence_gaps = []
    if latest_evidence_gap and latest_evidence_gap.evidence_gaps:
        evidence_gaps = latest_evidence_gap.evidence_gaps[:5]  # Top 5 gaps

    # Calculate overall readiness score (0-100)
    # Weights: documents (20), decision analysis (20), rating analysis (15),
    #          evidence analysis (25), statements (10), exam prep (10)
    score_components = []

    # Documents: 0-20 points (5 docs = 20 points)
    doc_score = min(total_documents * 4, 20)
    score_components.append({'name': 'Documents Uploaded', 'score': doc_score, 'max': 20,
                             'complete': total_documents >= 5})

    # Decision analysis: 0-20 points
    decision_score = min(decision_analyses * 20, 20)
    score_components.append({'name': 'Decision Letter Analyzed', 'score': decision_score, 'max': 20,
                             'complete': decision_analyses >= 1})

    # Rating analysis: 0-15 points
    rating_score = min(rating_analyses * 15, 15)
    score_components.append({'name': 'Rating Analysis Complete', 'score': rating_score, 'max': 15,
                             'complete': rating_analyses >= 1})

    # Evidence analysis: 0-25 points (use the readiness score if available)
    if evidence_readiness_score:
        evidence_score = int(evidence_readiness_score * 0.25)  # Scale to 25
    else:
        evidence_score = 0
    score_components.append({'name': 'Evidence Gaps Analyzed', 'score': evidence_score, 'max': 25,
                             'complete': evidence_analyses >= 1 and evidence_readiness_score and evidence_readiness_score >= 70})

    # Statements: 0-10 points
    statement_score = min(statements_generated * 10, 10)
    score_components.append({'name': 'Personal Statement Drafted', 'score': statement_score, 'max': 10,
                             'complete': statements_generated >= 1})

    # Exam prep: 0-10 points
    exam_score = min(exam_checklists * 10, 10)
    score_components.append({'name': 'C&P Exam Prepared', 'score': exam_score, 'max': 10,
                             'complete': exam_checklists >= 1})

    total_score = sum(c['score'] for c in score_components)
    max_score = sum(c['max'] for c in score_components)
    readiness_percentage = int((total_score / max_score) * 100) if max_score > 0 else 0

    # Generate next steps recommendations
    next_steps = []

    if total_documents == 0:
        next_steps.append({
            'priority': 'high',
            'action': 'Upload your VA documents',
            'description': 'Start by uploading your DD-214, medical records, or decision letters.',
            'url_name': 'claims:upload',
            'url_label': 'Upload Documents'
        })

    if decision_analyses == 0:
        next_steps.append({
            'priority': 'high',
            'action': 'Analyze your decision letter',
            'description': 'Upload and analyze your VA decision letter to understand your current status.',
            'url_name': 'agents:decision_analyzer',
            'url_label': 'Analyze Decision'
        })

    if rating_analyses == 0 and decision_analyses > 0:
        next_steps.append({
            'priority': 'medium',
            'action': 'Get a rating analysis',
            'description': 'Upload your rating decision to identify potential increases.',
            'url_name': 'agents:rating_analyzer',
            'url_label': 'Analyze Rating'
        })

    if evidence_analyses == 0:
        next_steps.append({
            'priority': 'high',
            'action': 'Check your evidence gaps',
            'description': 'Identify what evidence you need before filing your claim.',
            'url_name': 'agents:evidence_gap',
            'url_label': 'Check Evidence'
        })
    elif evidence_gaps:
        next_steps.append({
            'priority': 'medium',
            'action': 'Address evidence gaps',
            'description': f'You have {len(evidence_gaps)} evidence gaps to address.',
            'url_name': 'agents:evidence_gap',
            'url_label': 'View Gaps'
        })

    if statements_generated == 0 and (decision_analyses > 0 or evidence_analyses > 0):
        next_steps.append({
            'priority': 'medium',
            'action': 'Draft a personal statement',
            'description': 'Create a personal statement to support your claim.',
            'url_name': 'agents:statement_generator',
            'url_label': 'Generate Statement'
        })

    if exam_checklists == 0:
        next_steps.append({
            'priority': 'low',
            'action': 'Prepare for your C&P exam',
            'description': 'Review exam guides to know what to expect.',
            'url_name': 'examprep:guide_list',
            'url_label': 'View Exam Guides'
        })

    # Limit to top 4 next steps
    next_steps = next_steps[:4]

    # Readiness level
    if readiness_percentage >= 80:
        readiness_level = 'ready'
        readiness_message = "You're well-prepared to file your claim!"
    elif readiness_percentage >= 50:
        readiness_level = 'almost'
        readiness_message = "You're making good progress. Complete a few more steps."
    elif readiness_percentage >= 25:
        readiness_level = 'progressing'
        readiness_message = "You've started your journey. Keep building your evidence."
    else:
        readiness_level = 'starting'
        readiness_message = "Let's get started on your VA claim journey."

    context = {
        'page_title': 'Claim Progress',
        'readiness_percentage': readiness_percentage,
        'readiness_level': readiness_level,
        'readiness_message': readiness_message,
        'score_components': score_components,
        'next_steps': next_steps,
        'total_documents': total_documents,
        'recent_documents': recent_documents,
        'decision_analyses': decision_analyses,
        'rating_analyses': rating_analyses,
        'evidence_analyses': evidence_analyses,
        'statements_generated': statements_generated,
        'evidence_readiness_score': evidence_readiness_score,
        'evidence_gaps': evidence_gaps,
    }

    return render(request, 'core/claim_progress.html', context)


@login_required
def add_milestone(request):
    """
    Add a new journey milestone.
    """
    if request.method == 'POST':
        milestone_type = request.POST.get('milestone_type', 'custom')
        title = request.POST.get('title', '').strip()
        milestone_date = request.POST.get('date')
        notes = request.POST.get('notes', '').strip()

        if not title:
            messages.error(request, "Title is required.")
            return redirect('core:journey_dashboard')

        if not milestone_date:
            milestone_date = date.today()

        JourneyMilestone.objects.create(
            user=request.user,
            milestone_type=milestone_type,
            title=title,
            date=milestone_date,
            notes=notes,
        )

        messages.success(request, f"Milestone '{title}' added to your journey!")
        return redirect('core:journey_dashboard')

    # GET - show form
    context = {
        'milestone_types': JourneyMilestone.MILESTONE_TYPE_CHOICES,
    }
    return render(request, 'core/add_milestone.html', context)


@login_required
def add_deadline(request):
    """
    Add a new deadline.
    """
    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        deadline_date = request.POST.get('deadline_date')
        priority = request.POST.get('priority', 'medium')
        description = request.POST.get('description', '').strip()

        if not title or not deadline_date:
            messages.error(request, "Title and date are required.")
            return redirect('core:journey_dashboard')

        Deadline.objects.create(
            user=request.user,
            title=title,
            deadline_date=deadline_date,
            priority=priority,
            description=description,
        )

        messages.success(request, f"Deadline '{title}' added!")
        return redirect('core:journey_dashboard')

    # GET - show form
    context = {
        'priority_choices': Deadline.PRIORITY_CHOICES,
    }
    return render(request, 'core/add_deadline.html', context)


@login_required
def toggle_deadline(request, pk):
    """
    HTMX endpoint to toggle deadline completion.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    deadline = get_object_or_404(Deadline, pk=pk, user=request.user)

    if deadline.is_completed:
        deadline.is_completed = False
        deadline.completed_at = None
        deadline.save(update_fields=['is_completed', 'completed_at', 'updated_at'])
    else:
        deadline.mark_complete()

    return render(request, 'core/partials/deadline_item.html', {
        'deadline': deadline,
    })


@login_required
def delete_deadline(request, pk):
    """
    Delete a deadline.
    """
    deadline = get_object_or_404(Deadline, pk=pk, user=request.user)

    if request.method == 'POST':
        title = deadline.title
        deadline.delete()
        messages.success(request, f"Deadline '{title}' deleted.")
        return redirect('core:journey_dashboard')

    return render(request, 'core/delete_deadline.html', {
        'deadline': deadline,
    })


@login_required
def delete_milestone(request, pk):
    """
    Delete a milestone.
    """
    milestone = get_object_or_404(JourneyMilestone, pk=pk, user=request.user)

    if request.method == 'POST':
        title = milestone.title
        milestone.delete()
        messages.success(request, f"Milestone '{title}' deleted.")
        return redirect('core:journey_dashboard')

    return render(request, 'core/delete_milestone.html', {
        'milestone': milestone,
    })


# =============================================================================
# FEEDBACK VIEWS
# =============================================================================

from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.core.mail import send_mail
from django.conf import settings as django_settings
from .models import Feedback, SupportRequest


def submit_feedback(request):
    """
    Submit feedback via HTMX.
    Accepts both authenticated and anonymous users.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    rating = request.POST.get('rating')
    if rating not in ['positive', 'negative', 'neutral']:
        return HttpResponse('Invalid rating', status=400)

    # Create feedback
    feedback = Feedback.objects.create(
        user=request.user if request.user.is_authenticated else None,
        page_url=request.POST.get('page_url', request.META.get('HTTP_REFERER', '')),
        page_title=request.POST.get('page_title', ''),
        rating=rating,
        category=request.POST.get('category', 'general'),
        comment=request.POST.get('comment', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        session_key=request.session.session_key or '',
    )

    return render(request, 'core/partials/feedback_thanks.html', {
        'feedback': feedback,
    })


def feedback_form(request):
    """
    Return the expanded feedback form for adding a comment.
    Used by HTMX when user clicks thumbs down or wants to add details.
    """
    return render(request, 'core/partials/feedback_form.html', {
        'page_url': request.GET.get('page_url', ''),
        'page_title': request.GET.get('page_title', ''),
        'initial_rating': request.GET.get('rating', ''),
    })


# =============================================================================
# SUPPORT / CONTACT VIEWS
# =============================================================================

def contact(request):
    """
    Contact/support form for users to submit questions or issues.
    """
    context = {
        'page_title': 'Contact Support',
        'categories': SupportRequest.CATEGORY_CHOICES,
    }

    # Pre-fill user info if authenticated
    if request.user.is_authenticated:
        context['user_email'] = request.user.email
        context['user_name'] = request.user.get_full_name() or request.user.email

    if request.method == 'POST':
        # Validate required fields
        email = request.POST.get('email', '').strip()
        name = request.POST.get('name', '').strip()
        subject = request.POST.get('subject', '').strip()
        message = request.POST.get('message', '').strip()
        category = request.POST.get('category', 'general')

        errors = []
        if not email:
            errors.append('Email is required')
        if not name:
            errors.append('Name is required')
        if not subject:
            errors.append('Subject is required')
        if not message:
            errors.append('Message is required')

        if errors:
            context['errors'] = errors
            context['form_data'] = request.POST
            return render(request, 'core/contact.html', context)

        # Create support request
        support_request = SupportRequest.objects.create(
            user=request.user if request.user.is_authenticated else None,
            email=email,
            name=name,
            category=category,
            subject=subject,
            message=message,
            page_url=request.META.get('HTTP_REFERER', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        )

        # Send notification email to support team (optional)
        try:
            send_mail(
                subject=f'[Support] {category}: {subject}',
                message=f'New support request from {name} ({email}):\n\n{message}',
                from_email=django_settings.DEFAULT_FROM_EMAIL,
                recipient_list=[django_settings.SUPPORT_EMAIL],
                fail_silently=True,
            )
        except Exception:
            pass  # Don't fail if email doesn't send

        messages.success(
            request,
            'Your message has been sent. We\'ll get back to you as soon as possible.'
        )
        return redirect('core:contact_success')

    return render(request, 'core/contact.html', context)


def contact_success(request):
    """Success page after submitting contact form."""
    return render(request, 'core/contact_success.html', {
        'page_title': 'Message Sent',
    })


# =============================================================================
# ADMIN STATS DASHBOARD
# =============================================================================

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from datetime import timedelta
from django.utils import timezone


@staff_member_required
def admin_stats_dashboard(request):
    """
    Admin dashboard showing system statistics and pilot program metrics.

    Requires staff status to access.
    """
    from accounts.models import User, Subscription, UsageTracking
    from claims.models import Document

    now = timezone.now()
    today = now.date()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # ==========================================================================
    # USER STATS
    # ==========================================================================
    total_users = User.objects.count()

    # Count premium users (with active subscription)
    premium_users = Subscription.objects.filter(
        status='active',
        plan_type='premium'
    ).count()

    # Count pilot users
    pilot_user_count = 0
    pilot_premium_access = getattr(django_settings, 'PILOT_PREMIUM_ACCESS', False)
    pilot_emails = getattr(django_settings, 'PILOT_PREMIUM_EMAILS', [])
    pilot_domains = getattr(django_settings, 'PILOT_PREMIUM_DOMAINS', [])

    if pilot_premium_access:
        # All users are pilot users
        pilot_user_count = total_users
    else:
        # Count users matching pilot emails
        if pilot_emails:
            pilot_user_count += User.objects.filter(
                email__in=[e.lower() for e in pilot_emails]
            ).count()

        # Count users matching pilot domains
        if pilot_domains:
            for domain in pilot_domains:
                pilot_user_count += User.objects.filter(
                    email__iendswith=f'@{domain.lower()}'
                ).count()

    free_users = total_users - premium_users - pilot_user_count

    # New users
    new_users_today = User.objects.filter(date_joined__date=today).count()
    new_users_week = User.objects.filter(date_joined__gte=week_ago).count()
    new_users_month = User.objects.filter(date_joined__gte=month_ago).count()

    # ==========================================================================
    # DOCUMENT STATS
    # ==========================================================================
    total_documents = Document.objects.filter(is_deleted=False).count()
    docs_today = Document.objects.filter(created_at__date=today, is_deleted=False).count()
    docs_week = Document.objects.filter(created_at__gte=week_ago, is_deleted=False).count()
    docs_month = Document.objects.filter(created_at__gte=month_ago, is_deleted=False).count()

    # Document processing stats
    docs_by_status = Document.objects.filter(is_deleted=False).values('status').annotate(
        count=Count('id')
    ).order_by('status')

    # ==========================================================================
    # AI ANALYSIS STATS
    # ==========================================================================
    ai_stats = {}
    try:
        from agents.models import AgentInteraction, DecisionLetterAnalysis, EvidenceGapAnalysis, PersonalStatement

        ai_stats = {
            'total_interactions': AgentInteraction.objects.count(),
            'interactions_today': AgentInteraction.objects.filter(created_at__date=today).count(),
            'interactions_week': AgentInteraction.objects.filter(created_at__gte=week_ago).count(),
            'decision_analyses': DecisionLetterAnalysis.objects.count(),
            'evidence_analyses': EvidenceGapAnalysis.objects.count(),
            'statements_generated': PersonalStatement.objects.count(),
        }
    except ImportError:
        ai_stats = {'error': 'agents app not available'}

    # ==========================================================================
    # STORAGE STATS
    # ==========================================================================
    storage_stats = UsageTracking.objects.aggregate(
        total_storage_bytes=Sum('total_storage_bytes'),
        total_documents=Sum('total_documents_uploaded'),
    )

    total_storage_mb = (storage_stats['total_storage_bytes'] or 0) / (1024 * 1024)
    total_storage_gb = total_storage_mb / 1024

    # ==========================================================================
    # RECENT ACTIVITY
    # ==========================================================================
    recent_users = User.objects.order_by('-date_joined')[:10]
    recent_documents = Document.objects.filter(is_deleted=False).select_related('user').order_by('-created_at')[:10]

    # Recent feedback
    recent_feedback = []
    try:
        from .models import Feedback
        recent_feedback = Feedback.objects.select_related('user').order_by('-created_at')[:10]
    except Exception:
        pass

    # Recent support requests
    recent_support = []
    try:
        from .models import SupportRequest
        recent_support = SupportRequest.objects.order_by('-created_at')[:10]
    except Exception:
        pass

    # ==========================================================================
    # PILOT MODE INFO
    # ==========================================================================
    pilot_mode = getattr(django_settings, 'PILOT_MODE', False)
    pilot_billing_disabled = getattr(django_settings, 'PILOT_BILLING_DISABLED', False)
    pilot_retention_days = getattr(django_settings, 'PILOT_DATA_RETENTION_DAYS', 30)

    context = {
        'page_title': 'Admin Stats Dashboard',

        # User stats
        'total_users': total_users,
        'premium_users': premium_users,
        'pilot_users': pilot_user_count,
        'free_users': max(0, free_users),
        'new_users_today': new_users_today,
        'new_users_week': new_users_week,
        'new_users_month': new_users_month,

        # Document stats
        'total_documents': total_documents,
        'docs_today': docs_today,
        'docs_week': docs_week,
        'docs_month': docs_month,
        'docs_by_status': list(docs_by_status),

        # AI stats
        'ai_stats': ai_stats,

        # Storage stats
        'total_storage_mb': round(total_storage_mb, 2),
        'total_storage_gb': round(total_storage_gb, 2),
        'total_docs_uploaded': storage_stats['total_documents'] or 0,

        # Recent activity
        'recent_users': recent_users,
        'recent_documents': recent_documents,
        'recent_feedback': recent_feedback,
        'recent_support': recent_support,

        # Pilot mode info
        'pilot_mode': pilot_mode,
        'pilot_billing_disabled': pilot_billing_disabled,
        'pilot_retention_days': pilot_retention_days,
        'pilot_emails': pilot_emails,
        'pilot_domains': pilot_domains,
    }

    return render(request, 'core/admin_stats.html', context)
