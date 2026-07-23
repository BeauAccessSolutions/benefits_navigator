"""
Custom authentication views with rate limiting and data management
"""

import json
import logging

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.utils import timezone
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from allauth.account.views import LoginView, SignupView, PasswordResetView

from core.models import AuditLog
from .models import Subscription, UsageTracking

logger = logging.getLogger(__name__)


class RateLimitedLoginView(LoginView):
    """
    Login view with rate limiting to prevent brute force attacks.
    Limits: 5 attempts per minute per IP, 20 per hour
    """

    @method_decorator(ratelimit(key="ip", rate="5/m", method="POST", block=True))
    @method_decorator(ratelimit(key="ip", rate="20/h", method="POST", block=True))
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class RateLimitedSignupView(SignupView):
    """
    Signup view with rate limiting to prevent abuse.
    Limits: 3 signups per hour per IP
    """

    @method_decorator(ratelimit(key="ip", rate="3/h", method="POST", block=True))
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


class RateLimitedPasswordResetView(PasswordResetView):
    """
    Password reset view with rate limiting to prevent email bombing.
    Limits: 3 resets per hour per IP
    """

    @method_decorator(ratelimit(key="ip", rate="3/h", method="POST", block=True))
    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


# =============================================================================
# DATA EXPORT / PRIVACY VIEWS
# =============================================================================


@login_required
def data_export(request):
    """
    Request export of all user data (GDPR compliance).
    """
    if request.method == "POST":
        # Log the export request
        AuditLog.log(
            action="pii_export",
            request=request,
            details={"export_type": "full_data"},
        )

        # Generate export immediately (for small datasets)
        # For larger systems, this would be queued as a Celery task
        export_data = _generate_user_export(request.user)

        # Return as downloadable JSON file
        response = HttpResponse(
            json.dumps(export_data, indent=2, default=str),
            content_type="application/json",
        )
        response["Content-Disposition"] = (
            f'attachment; filename="va_navigator_export_{request.user.id}.json"'
        )
        return response

    context = {
        "page_title": "Export My Data",
    }
    return render(request, "accounts/data_export.html", context)


def _generate_user_export(user):
    """
    Generate a complete export of user data.

    PII fields (date_of_birth, va_file_number) are redacted for security.
    Users can view these in their profile settings if needed.

    Query limits applied to prevent memory exhaustion on large datasets.
    """
    # Maximum records per category to prevent memory exhaustion
    MAX_EXPORT_RECORDS = 1000

    export = {
        "export_date": timezone.now().isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone_number": user.phone_number,
            "date_joined": user.date_joined.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None,
        },
    }

    # Profile data - PII fields redacted for security
    if hasattr(user, "profile"):
        profile = user.profile
        export["profile"] = {
            "branch_of_service": profile.branch_of_service,
            "date_of_birth": "[REDACTED]" if profile.date_of_birth else None,
            "va_file_number": "[REDACTED]" if profile.va_file_number else None,
            "disability_rating": profile.disability_rating,
            "bio": profile.bio,
        }

    # Documents (limited to prevent memory exhaustion)
    if hasattr(user, "documents"):
        docs = user.documents.filter(is_deleted=False).order_by("-created_at")[
            :MAX_EXPORT_RECORDS
        ]
        export["documents"] = [
            {
                "id": doc.id,
                "file_name": doc.file_name,
                "document_type": doc.document_type,
                "uploaded_at": doc.created_at.isoformat(),
            }
            for doc in docs
        ]

    # Claims (limited to prevent memory exhaustion)
    if hasattr(user, "claims"):
        claims = user.claims.filter(is_deleted=False).order_by("-created_at")[
            :MAX_EXPORT_RECORDS
        ]
        export["claims"] = [
            {
                "id": claim.id,
                "title": claim.title,
                "claim_type": claim.claim_type,
                "status": claim.status,
                "submission_date": (
                    claim.submission_date.isoformat() if claim.submission_date else None
                ),
                "created_at": claim.created_at.isoformat(),
            }
            for claim in claims
        ]

    # Appeals (limited to prevent memory exhaustion)
    if hasattr(user, "appeals"):
        appeals = user.appeals.all().order_by("-created_at")[:MAX_EXPORT_RECORDS]
        export["appeals"] = [
            {
                "id": appeal.id,
                "conditions_appealed": appeal.conditions_appealed,
                "appeal_type": appeal.appeal_type,
                "status": appeal.status,
                "created_at": appeal.created_at.isoformat(),
            }
            for appeal in appeals
        ]

    # Exam checklists (limited to prevent memory exhaustion)
    if hasattr(user, "exam_checklists"):
        checklists = user.exam_checklists.all().order_by("-created_at")[
            :MAX_EXPORT_RECORDS
        ]
        export["exam_checklists"] = [
            {
                "id": checklist.id,
                "condition": checklist.condition,
                "exam_date": (
                    checklist.exam_date.isoformat() if checklist.exam_date else None
                ),
                "created_at": checklist.created_at.isoformat(),
            }
            for checklist in checklists
        ]

    # Evidence checklists (limited to prevent memory exhaustion)
    if hasattr(user, "evidence_checklists"):
        evidence = user.evidence_checklists.all().order_by("-created_at")[
            :MAX_EXPORT_RECORDS
        ]
        export["evidence_checklists"] = [
            {
                "id": checklist.id,
                "condition": checklist.condition,
                "claim_type": checklist.claim_type,
                "completion_percentage": checklist.completion_percentage,
                "created_at": checklist.created_at.isoformat(),
            }
            for checklist in evidence
        ]

    # Rating calculations (limited to prevent memory exhaustion)
    if hasattr(user, "rating_calculations"):
        calcs = user.rating_calculations.all().order_by("-created_at")[
            :MAX_EXPORT_RECORDS
        ]
        export["rating_calculations"] = [
            {
                "id": calc.id,
                "name": calc.name,
                "combined_rounded": calc.combined_rounded,
                "created_at": calc.created_at.isoformat(),
            }
            for calc in calcs
        ]

    # Journey events (limited to prevent memory exhaustion)
    if hasattr(user, "journey_events"):
        events = user.journey_events.all().order_by("-event_date")[:MAX_EXPORT_RECORDS]
        export["journey_events"] = [
            {
                "id": event.id,
                "title": event.title,
                "event_date": event.event_date.isoformat(),
            }
            for event in events
        ]

    # Milestones (limited to prevent memory exhaustion)
    if hasattr(user, "journey_milestones"):
        milestones = user.journey_milestones.all().order_by("-date")[
            :MAX_EXPORT_RECORDS
        ]
        export["journey_milestones"] = [
            {
                "id": milestone.id,
                "title": milestone.title,
                "date": milestone.date.isoformat(),
                "milestone_type": milestone.milestone_type,
            }
            for milestone in milestones
        ]

    return export


@login_required
def account_deletion(request):
    """
    Request (or cancel) account deletion (GDPR compliance).

    Confirming sets ``User.deletion_requested_at``. The account stays usable
    during a 30-day grace period so the user can cancel by logging back in and
    returning here; a daily Celery Beat task
    (``core.tasks.process_scheduled_account_deletions``) permanently purges
    accounts whose grace period has elapsed.
    """
    user = request.user

    if request.method == "POST":
        intent = request.POST.get("intent", "delete")

        if intent == "cancel":
            if user.deletion_requested_at:
                user.deletion_requested_at = None
                user.save(update_fields=["deletion_requested_at"])
                AuditLog.log(action="account_delete_cancel", request=request)
                messages.success(
                    request,
                    "Your account deletion has been cancelled. Your account and "
                    "data will be kept.",
                )
            return redirect("accounts:account_deletion")

        confirm = request.POST.get("confirm")
        if confirm == "DELETE":
            # Idempotent: don't reset the clock if a request is already pending.
            if not user.deletion_requested_at:
                user.deletion_requested_at = timezone.now()
                user.save(update_fields=["deletion_requested_at"])

            AuditLog.log(
                action="account_delete",
                request=request,
                details={
                    "scheduled_for": user.scheduled_deletion_date.isoformat(),
                },
            )
            messages.success(
                request,
                "Your account deletion has been scheduled. Your account and all "
                "data will be permanently deleted in 30 days. You can cancel any "
                "time before then by logging in and returning to this page.",
            )
            return redirect("accounts:account_deletion")
        else:
            messages.error(request, "Please type DELETE to confirm account deletion.")

    context = {
        "page_title": "Delete My Account",
        "deletion_requested_at": user.deletion_requested_at,
        "scheduled_deletion_date": user.scheduled_deletion_date,
    }
    return render(request, "accounts/account_deletion.html", context)


@login_required
def privacy_settings(request):
    """
    Privacy settings page - central hub for data management.
    """
    user = request.user

    # Get counts for the summary
    document_count = (
        user.documents.filter(is_deleted=False).count()
        if hasattr(user, "documents")
        else 0
    )
    claim_count = (
        user.claims.filter(is_deleted=False).count() if hasattr(user, "claims") else 0
    )
    appeal_count = user.appeals.count() if hasattr(user, "appeals") else 0

    # Get recent audit logs for this user
    recent_activity = AuditLog.objects.filter(user=user).order_by("-timestamp")[:10]

    context = {
        "page_title": "Privacy Settings",
        "document_count": document_count,
        "claim_count": claim_count,
        "appeal_count": appeal_count,
        "recent_activity": recent_activity,
    }
    return render(request, "accounts/privacy_settings.html", context)


@login_required
@require_POST
def toggle_ai_consent(request):
    """
    Toggle AI processing consent for the user.
    """
    action = request.POST.get("action")
    profile = request.user.profile

    if action == "grant":
        profile.ai_processing_consent = True
        profile.ai_consent_date = timezone.now()
        profile.save()
        messages.success(
            request,
            "You have granted consent for AI document processing. "
            "Your uploaded documents can now be analyzed using AI.",
        )
    elif action == "revoke":
        profile.ai_processing_consent = False
        profile.ai_consent_date = None
        profile.save()
        messages.info(
            request,
            "You have revoked consent for AI document processing. "
            "New documents will not be processed by AI. Existing analysis results remain available.",
        )

    return redirect("accounts:privacy_settings")


# =============================================================================
# SUBSCRIPTION / STRIPE VIEWS
# =============================================================================


@login_required
def upgrade(request):
    """
    Display upgrade page with plan comparison and checkout options.
    """
    user = request.user

    # Get current usage
    usage, _ = UsageTracking.objects.get_or_create(user=user)
    usage_summary = usage.get_usage_summary()

    # Get current subscription
    subscription = None
    try:
        subscription = user.subscription
    except Subscription.DoesNotExist:
        pass

    # Pilot mode flags
    pilot_mode = getattr(settings, "PILOT_MODE", False)
    pilot_billing_disabled = getattr(settings, "PILOT_BILLING_DISABLED", False)
    is_pilot_user = getattr(user, "is_pilot_user", False)

    context = {
        "page_title": "Upgrade to Premium",
        "usage": usage_summary,
        "subscription": subscription,
        "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
        "price_id": settings.STRIPE_PRICE_ID,
        # Pilot mode context
        "pilot_mode": pilot_mode,
        "pilot_billing_disabled": pilot_billing_disabled,
        "is_pilot_user": is_pilot_user,
        # Feature comparison
        "free_features": [
            f"{settings.FREE_TIER_DOCUMENTS_PER_MONTH} document uploads/month",
            f"{settings.FREE_TIER_MAX_STORAGE_MB} MB storage",
            f"{getattr(settings, 'FREE_TIER_DENIAL_DECODES_PER_MONTH', 2)} denial decodes/month",
            f"{getattr(settings, 'FREE_TIER_AI_ANALYSES_PER_MONTH', 5)} AI analyses/month",
            "Basic exam prep guides",
            "Rating calculator",
        ],
        "premium_features": [
            "Unlimited document uploads",
            "Unlimited storage",
            "Unlimited denial decodes",
            "Unlimited AI analyses",
            "Advanced exam prep with checklists",
            "Save rating calculations",
            "Export reports to PDF",
            "Priority support",
        ],
    }
    return render(request, "accounts/upgrade.html", context)


@login_required
def create_checkout_session(request):
    """
    Create a Stripe Checkout session for subscription.
    Blocked when PILOT_BILLING_DISABLED is True.
    """
    import stripe

    # Check if billing is disabled for pilot mode
    if getattr(settings, "PILOT_BILLING_DISABLED", False):
        logger.info(
            f"Checkout blocked for user {request.user.id} - pilot billing disabled"
        )
        messages.info(
            request,
            "Billing is disabled during the pilot program. "
            "You already have access to all premium features for testing!",
        )
        return redirect("accounts:upgrade")

    stripe.api_key = settings.STRIPE_SECRET_KEY

    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PRICE_ID:
        messages.error(
            request, "Payment system is not configured. Please contact support."
        )
        return redirect("accounts:upgrade")

    user = request.user

    try:
        # Get or create Stripe customer
        if not user.stripe_customer_id:
            customer = stripe.Customer.create(
                email=user.email, name=user.full_name, metadata={"user_id": user.id}
            )
            user.stripe_customer_id = customer.id
            user.save()

        # Create checkout session
        checkout_session = stripe.checkout.Session.create(
            customer=user.stripe_customer_id,
            payment_method_types=["card"],
            line_items=[
                {
                    "price": settings.STRIPE_PRICE_ID,
                    "quantity": 1,
                }
            ],
            mode="subscription",
            success_url=request.build_absolute_uri("/accounts/subscription/success/"),
            cancel_url=request.build_absolute_uri("/accounts/upgrade/"),
            metadata={"user_id": user.id},
        )

        return redirect(checkout_session.url)

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating checkout session: {e}")
        messages.error(request, "Unable to create checkout session. Please try again.")
        return redirect("accounts:upgrade")


@login_required
def subscription_success(request):
    """
    Handle successful subscription checkout.
    """
    messages.success(
        request, "Thank you for upgrading to Premium! Your subscription is now active."
    )
    return redirect("dashboard")


@login_required
def customer_portal(request):
    """
    Redirect to Stripe Customer Portal for subscription management.
    """
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY

    user = request.user

    if not user.stripe_customer_id:
        messages.error(request, "No subscription found.")
        return redirect("accounts:upgrade")

    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=request.build_absolute_uri("/accounts/upgrade/"),
        )
        return redirect(portal_session.url)

    except stripe.error.StripeError as e:
        logger.error(f"Stripe error creating portal session: {e}")
        messages.error(
            request, "Unable to access subscription management. Please try again."
        )
        return redirect("accounts:upgrade")


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """
    Handle Stripe webhook events for subscription management.

    Events handled:
    - checkout.session.completed: New subscription created
    - customer.subscription.updated: Subscription changed (upgrade/downgrade)
    - customer.subscription.deleted: Subscription cancelled
    - invoice.payment_failed: Payment failed
    """
    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY

    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE")
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET

    if not webhook_secret:
        logger.error("Stripe webhook secret not configured")
        return HttpResponse(status=400)

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError as e:
        logger.error(f"Invalid Stripe webhook payload: {e}")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid Stripe webhook signature: {e}")
        return HttpResponse(status=400)

    # Handle the event
    event_type = event["type"]
    data = event["data"]["object"]

    logger.info(f"Received Stripe webhook: {event_type}")

    try:
        if event_type == "checkout.session.completed":
            _handle_checkout_completed(data)
        elif event_type == "customer.subscription.updated":
            _handle_subscription_updated(data)
        elif event_type == "customer.subscription.deleted":
            _handle_subscription_deleted(data)
        elif event_type == "invoice.payment_failed":
            _handle_payment_failed(data)
        else:
            logger.info(f"Unhandled Stripe event type: {event_type}")

    except Exception as e:
        logger.error(f"Error handling Stripe webhook {event_type}: {e}")
        return HttpResponse(status=500)

    return HttpResponse(status=200)


def _handle_checkout_completed(session):
    """Handle successful checkout - create/update subscription."""
    from .models import User

    customer_id = session.get("customer")
    subscription_id = session.get("subscription")

    if not customer_id or not subscription_id:
        logger.warning("Checkout session missing customer or subscription ID")
        return

    # Find user by Stripe customer ID
    try:
        user = User.objects.get(stripe_customer_id=customer_id)
    except User.DoesNotExist:
        # Try to find by metadata
        user_id = session.get("metadata", {}).get("user_id")
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                user.stripe_customer_id = customer_id
                user.save()
            except User.DoesNotExist:
                logger.error(
                    f"User not found for checkout session: {session.get('id')}"
                )
                return
        else:
            logger.error(f"Cannot find user for customer: {customer_id}")
            return

    # Get subscription details from Stripe
    import stripe

    stripe_sub = stripe.Subscription.retrieve(subscription_id)

    # Create or update subscription record
    subscription, created = Subscription.objects.get_or_create(user=user)
    subscription.stripe_subscription_id = subscription_id
    subscription.stripe_customer_id = customer_id
    subscription.plan_type = "premium"
    subscription.status = "active"
    subscription.current_period_end = timezone.datetime.fromtimestamp(
        stripe_sub.current_period_end, tz=timezone.utc
    )
    subscription.save()

    logger.info(f"Subscription created/updated for user_id={user.id}")


def _handle_subscription_updated(subscription_data):
    """Handle subscription update (status change, renewal, etc.)."""
    subscription_id = subscription_data.get("id")
    status = subscription_data.get("status")
    cancel_at_period_end = subscription_data.get("cancel_at_period_end", False)

    try:
        subscription = Subscription.objects.get(stripe_subscription_id=subscription_id)

        # Map Stripe status to our status
        status_map = {
            "active": "active",
            "past_due": "past_due",
            "unpaid": "unpaid",
            "canceled": "canceled",
            "incomplete": "incomplete",
            "incomplete_expired": "canceled",
            "trialing": "trialing",
        }

        subscription.status = status_map.get(status, status)
        subscription.cancel_at_period_end = cancel_at_period_end

        if subscription_data.get("current_period_end"):
            subscription.current_period_end = timezone.datetime.fromtimestamp(
                subscription_data["current_period_end"], tz=timezone.utc
            )

        subscription.save()
        logger.info(f"Subscription {subscription_id} updated to status: {status}")

    except Subscription.DoesNotExist:
        logger.warning(f"Subscription not found for update: {subscription_id}")


def _handle_subscription_deleted(subscription_data):
    """Handle subscription cancellation."""
    subscription_id = subscription_data.get("id")

    try:
        subscription = Subscription.objects.get(stripe_subscription_id=subscription_id)
        subscription.status = "canceled"
        subscription.plan_type = "free"
        subscription.save()

        logger.info(f"Subscription {subscription_id} cancelled")

    except Subscription.DoesNotExist:
        logger.warning(f"Subscription not found for deletion: {subscription_id}")


def _handle_payment_failed(invoice_data):
    """Handle failed payment - notify user and update status."""
    subscription_id = invoice_data.get("subscription")

    if subscription_id:
        try:
            subscription = Subscription.objects.get(
                stripe_subscription_id=subscription_id
            )
            subscription.status = "past_due"
            subscription.save()

            # TODO: Send email notification to user about failed payment
            logger.info(f"Payment failed for subscription {subscription_id}")

        except Subscription.DoesNotExist:
            logger.warning(
                f"Subscription not found for failed payment: {subscription_id}"
            )


# =============================================================================
# ORGANIZATION VIEWS (Path B - VSO Platform)
# =============================================================================

from django.shortcuts import get_object_or_404
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from core.features import require_feature
from .models import Organization, OrganizationMembership, OrganizationInvitation
from .forms import OrganizationForm, OrganizationInviteForm


@login_required
@require_feature("organizations", redirect_url="home")
def org_list(request):
    """
    List all organizations the user is a member of.
    """
    memberships = (
        OrganizationMembership.objects.filter(
            user=request.user,
            is_active=True,
        )
        .select_related("organization")
        .order_by("-organization__created_at")
    )

    context = {
        "memberships": memberships,
        "page_title": "My Organizations",
    }
    return render(request, "accounts/org_list.html", context)


@login_required
@require_feature("organizations", redirect_url="home")
@ratelimit(key="user", rate="10/h", method="POST", block=True)
def org_create(request):
    """
    Create a new organization.
    The creator automatically becomes the admin of the organization.
    """
    if request.method == "POST":
        form = OrganizationForm(request.POST)
        if form.is_valid():
            # Create the organization
            organization = form.save()

            # Create membership for creator as admin
            OrganizationMembership.objects.create(
                user=request.user,
                organization=organization,
                role="admin",
                invited_by=request.user,
                accepted_at=timezone.now(),
                is_active=True,
            )

            # Update seat count
            organization.seats_used = 1
            organization.save(update_fields=["seats_used", "updated_at"])

            # Log the action
            AuditLog.log(
                action="other",
                request=request,
                resource_type="Organization",
                resource_id=organization.id,
                details={
                    "action": "organization_created",
                    "org_name": organization.name,
                    "org_slug": organization.slug,
                    "org_type": organization.org_type,
                },
            )

            messages.success(
                request,
                f'Organization "{organization.name}" created successfully! '
                f"You are now the administrator.",
            )

            return redirect("accounts:org_dashboard", slug=organization.slug)
    else:
        form = OrganizationForm()

    # Count user's existing admin orgs
    user_org_count = OrganizationMembership.objects.filter(
        user=request.user, role="admin", is_active=True
    ).count()

    context = {
        "form": form,
        "user_org_count": user_org_count,
        "page_title": "Create Organization",
    }
    return render(request, "accounts/org_create.html", context)


@login_required
@require_feature("organizations", redirect_url="home")
def org_dashboard(request, slug):
    """
    Organization dashboard - overview for organization members.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Check if user is a member
    try:
        membership = OrganizationMembership.objects.get(
            user=request.user,
            organization=organization,
            is_active=True,
        )
    except OrganizationMembership.DoesNotExist:
        messages.error(request, "You are not a member of this organization.")
        return redirect("accounts:org_list")

    # Get organization stats
    total_members = organization.memberships.filter(is_active=True).count()
    pending_invitations = organization.invitations.filter(
        accepted_at__isnull=True, expires_at__gt=timezone.now()
    ).count()

    # Get members list (for admins)
    members = []
    if membership.is_admin:
        members = (
            organization.memberships.filter(is_active=True)
            .select_related("user")
            .order_by("role", "user__email")
        )

    context = {
        "organization": organization,
        "membership": membership,
        "total_members": total_members,
        "pending_invitations": pending_invitations,
        "members": members,
        "page_title": organization.name,
    }
    return render(request, "accounts/org_dashboard.html", context)


# =============================================================================
# ORGANIZATION INVITATION VIEWS
# =============================================================================


@login_required
@require_feature("org_invitations", redirect_url="home")
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def org_invite(request, slug):
    """
    Send an invitation to join an organization.
    Only admins can invite new members.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Check if user is an admin
    try:
        membership = OrganizationMembership.objects.get(
            user=request.user,
            organization=organization,
            is_active=True,
        )
        if not membership.is_admin:
            messages.error(request, "Only administrators can invite members.")
            return redirect("accounts:org_dashboard", slug=slug)
    except OrganizationMembership.DoesNotExist:
        messages.error(request, "You are not a member of this organization.")
        return redirect("accounts:org_list")

    if request.method == "POST":
        form = OrganizationInviteForm(organization, request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            role = form.cleaned_data["role"]

            # Create invitation
            invitation = OrganizationInvitation.objects.create(
                organization=organization,
                email=email,
                role=role,
                invited_by=request.user,
            )

            # Send invitation email
            _send_invitation_email(request, invitation)

            # Audit log
            AuditLog.log(
                action="other",
                request=request,
                resource_type="OrganizationInvitation",
                resource_id=invitation.id,
                details={
                    "action": "invitation_sent",
                    "org_slug": organization.slug,
                    "invited_email": email,
                    "role": role,
                },
            )

            messages.success(
                request,
                f"Invitation sent to {email}. They will receive an email with instructions to join.",
            )
            return redirect("accounts:org_invitations", slug=slug)
    else:
        form = OrganizationInviteForm(organization)

    context = {
        "form": form,
        "organization": organization,
        "membership": membership,
        "page_title": f"Invite Member - {organization.name}",
    }
    return render(request, "accounts/org_invite.html", context)


@login_required
@require_feature("org_invitations", redirect_url="home")
def org_invitations(request, slug):
    """
    List pending invitations for an organization.
    Only admins can view this page.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Check if user is an admin
    try:
        membership = OrganizationMembership.objects.get(
            user=request.user,
            organization=organization,
            is_active=True,
        )
        if not membership.is_admin:
            messages.error(request, "Only administrators can manage invitations.")
            return redirect("accounts:org_dashboard", slug=slug)
    except OrganizationMembership.DoesNotExist:
        messages.error(request, "You are not a member of this organization.")
        return redirect("accounts:org_list")

    # Get pending invitations
    pending_invitations = (
        organization.invitations.filter(
            accepted_at__isnull=True, expires_at__gt=timezone.now()
        )
        .select_related("invited_by")
        .order_by("-created_at")
    )

    # Get expired invitations (last 30 days)
    expired_invitations = (
        organization.invitations.filter(
            accepted_at__isnull=True,
            expires_at__lte=timezone.now(),
            created_at__gte=timezone.now() - timezone.timedelta(days=30),
        )
        .select_related("invited_by")
        .order_by("-created_at")[:10]
    )

    context = {
        "organization": organization,
        "membership": membership,
        "pending_invitations": pending_invitations,
        "expired_invitations": expired_invitations,
        "page_title": f"Pending Invitations - {organization.name}",
    }
    return render(request, "accounts/org_invitations.html", context)


@login_required
@require_feature("org_invitations", redirect_url="home")
@ratelimit(key="user", rate="10/h", method="POST", block=True)
def org_invite_resend(request, slug, token):
    """
    Resend an invitation email and extend expiry.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Check if user is an admin
    try:
        OrganizationMembership.objects.get(
            user=request.user,
            organization=organization,
            is_active=True,
            role="admin",
        )
    except OrganizationMembership.DoesNotExist:
        messages.error(request, "You do not have permission to resend invitations.")
        return redirect("accounts:org_dashboard", slug=slug)

    invitation = get_object_or_404(
        OrganizationInvitation,
        organization=organization,
        token=token,
        accepted_at__isnull=True,
    )

    if request.method == "POST":
        # Reset expiration
        invitation.expires_at = timezone.now() + timezone.timedelta(days=7)
        invitation.save(update_fields=["expires_at", "updated_at"])

        # Resend email
        _send_invitation_email(request, invitation)

        # Audit log
        AuditLog.log(
            action="other",
            request=request,
            resource_type="OrganizationInvitation",
            resource_id=invitation.id,
            details={
                "action": "invitation_resent",
                "org_slug": organization.slug,
                "invited_email": invitation.email,
            },
        )

        messages.success(request, f"Invitation resent to {invitation.email}.")

    return redirect("accounts:org_invitations", slug=slug)


@login_required
@require_feature("org_invitations", redirect_url="home")
def org_invite_cancel(request, slug, token):
    """
    Cancel a pending invitation.
    """
    organization = get_object_or_404(Organization, slug=slug, is_active=True)

    # Check if user is an admin
    try:
        OrganizationMembership.objects.get(
            user=request.user,
            organization=organization,
            is_active=True,
            role="admin",
        )
    except OrganizationMembership.DoesNotExist:
        messages.error(request, "You do not have permission to cancel invitations.")
        return redirect("accounts:org_dashboard", slug=slug)

    invitation = get_object_or_404(
        OrganizationInvitation,
        organization=organization,
        token=token,
        accepted_at__isnull=True,
    )

    if request.method == "POST":
        email = invitation.email

        # Expire the invitation immediately
        invitation.expires_at = timezone.now() - timezone.timedelta(seconds=1)
        invitation.save(update_fields=["expires_at", "updated_at"])

        # Audit log
        AuditLog.log(
            action="other",
            request=request,
            resource_type="OrganizationInvitation",
            resource_id=invitation.id,
            details={
                "action": "invitation_cancelled",
                "org_slug": organization.slug,
                "invited_email": email,
            },
        )

        messages.success(request, f"Invitation to {email} has been cancelled.")

    return redirect("accounts:org_invitations", slug=slug)


def org_invite_accept(request, token):
    """
    Accept an organization invitation.
    Public view - handles both logged-in and anonymous users.
    """
    invitation = get_object_or_404(OrganizationInvitation, token=token)

    # Check if already accepted
    if invitation.accepted_at:
        messages.info(request, "This invitation has already been accepted.")
        if request.user.is_authenticated:
            return redirect("accounts:org_dashboard", slug=invitation.organization.slug)
        return redirect("account_login")

    # Check if expired
    if invitation.is_expired:
        messages.error(
            request,
            "This invitation has expired. Please ask the organization administrator "
            "to send a new invitation.",
        )
        return redirect("home")

    # Check seat limit
    if invitation.organization.is_at_seat_limit:
        messages.error(
            request,
            "This organization has reached its member limit. "
            "Please contact the organization administrator.",
        )
        return redirect("home")

    # If user is not logged in, redirect to login/signup
    if not request.user.is_authenticated:
        # Store invitation token in session for after login
        request.session["pending_invitation_token"] = token
        messages.info(
            request,
            f"You have been invited to join {invitation.organization.name}. "
            "Please log in or create an account to accept.",
        )
        # Redirect to signup with email prefilled
        signup_url = reverse("account_signup")
        return redirect(f"{signup_url}?email={invitation.email}")

    # User is logged in - check if email matches
    email_mismatch = request.user.email.lower() != invitation.email.lower()

    if email_mismatch and request.method != "POST":
        # Show mismatch warning, let user decide
        context = {
            "invitation": invitation,
            "email_mismatch": True,
            "page_title": f"Join {invitation.organization.name}",
        }
        return render(request, "accounts/org_invite_accept.html", context)

    # Process acceptance
    if request.method == "POST":
        try:
            membership = invitation.accept(request.user)

            # Audit log
            AuditLog.log(
                action="other",
                request=request,
                resource_type="OrganizationInvitation",
                resource_id=invitation.id,
                details={
                    "action": "invitation_accepted",
                    "org_slug": invitation.organization.slug,
                    "role": invitation.role,
                },
            )

            messages.success(
                request,
                f"Welcome to {invitation.organization.name}! "
                f"You have joined as a {membership.get_role_display()}.",
            )
            return redirect("accounts:org_dashboard", slug=invitation.organization.slug)

        except ValueError as e:
            messages.error(request, str(e))
            return redirect("home")

    context = {
        "invitation": invitation,
        "email_mismatch": False,
        "page_title": f"Join {invitation.organization.name}",
    }
    return render(request, "accounts/org_invite_accept.html", context)


def _send_invitation_email(request, invitation):
    """
    Send invitation email to the invitee.
    """
    # Build accept URL
    accept_url = request.build_absolute_uri(
        reverse("accounts:org_invite_accept", kwargs={"token": invitation.token})
    )

    context = {
        "invitation": invitation,
        "organization": invitation.organization,
        "invited_by": invitation.invited_by,
        "accept_url": accept_url,
        "expires_at": invitation.expires_at,
        "site_name": getattr(settings, "SITE_NAME", "Benefits Navigator"),
        "site_url": request.build_absolute_uri("/").rstrip("/"),
    }

    # Render email templates
    subject = f"You're invited to join {invitation.organization.name}"
    text_content = render_to_string("emails/organization_invitation.txt", context)
    html_content = render_to_string("emails/organization_invitation.html", context)

    # Send email
    try:
        send_mail(
            subject=subject,
            message=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            html_message=html_content,
            fail_silently=False,
        )
        logger.info(f"Invitation email sent for invitation_id={invitation.id}")
    except Exception as e:
        logger.error(
            f"Failed to send invitation email for invitation_id={invitation.id}: {e}"
        )
