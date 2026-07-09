"""
GraphQL Schema for Benefits Navigator
Uses Strawberry GraphQL with Django integration
"""

import re
import strawberry
from strawberry.types import Info
from strawberry.permission import BasePermission
from typing import Optional, List
from datetime import date, datetime

from django.contrib.auth import get_user_model

User = get_user_model()


# =============================================================================
# PII REDACTION UTILITIES
# =============================================================================

# Maximum text length for GraphQL responses (prevents exfiltration)
MAX_OCR_TEXT_LENGTH = 50000  # ~50KB
MAX_AI_SUMMARY_LENGTH = 10000  # ~10KB

# Patterns for PII redaction
PII_PATTERNS = [
    # SSN patterns: 123-45-6789, 123 45 6789, 123456789
    (r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b", "[REDACTED:SSN]"),
    # VA file number patterns (typically 8-9 digits, sometimes with C prefix)
    (r"\b[Cc]?\d{8,9}\b", "[REDACTED:VA_FILE]"),
    # VA file number with letters/dashes: C12 345 678
    (r"\b[Cc]\s?\d{2}\s?\d{3}\s?\d{3}\b", "[REDACTED:VA_FILE]"),
    # Credit card patterns (just in case)
    (r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b", "[REDACTED:CC]"),
    # Date of birth in common formats (when clearly labeled)
    (
        r"(?i)(date\s*of\s*birth|dob|born)[\s:]*(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"\1: [REDACTED:DOB]",
    ),
    # Phone numbers: (123) 456-7890, 123-456-7890, 123.456.7890
    (r"\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b", "[REDACTED:PHONE]"),
]

# Compile patterns for performance
_COMPILED_PII_PATTERNS = [(re.compile(p), r) for p, r in PII_PATTERNS]


def redact_pii(text: str) -> str:
    """
    Redact PII patterns from text.

    Removes SSNs, VA file numbers, credit cards, phone numbers, and labeled DOBs.
    """
    if not text:
        return text

    for pattern, replacement in _COMPILED_PII_PATTERNS:
        text = pattern.sub(replacement, text)

    return text


def truncate_text(text: str, max_length: int) -> str:
    """
    Truncate text to max length with indicator.
    """
    if not text or len(text) <= max_length:
        return text

    return (
        text[:max_length]
        + f"\n\n[TRUNCATED: {len(text) - max_length} characters omitted]"
    )


def sanitize_graphql_text(text: str, max_length: int) -> str:
    """
    Sanitize text for GraphQL response: redact PII and truncate.
    """
    if not text:
        return text

    # First redact PII
    sanitized = redact_pii(text)

    # Then truncate if needed
    return truncate_text(sanitized, max_length)


# =============================================================================
# PERMISSIONS
# =============================================================================


class IsAuthenticated(BasePermission):
    """Require authenticated user for queries/mutations."""

    message = "User is not authenticated"

    def has_permission(self, source, info: Info, **kwargs) -> bool:
        request = info.context.request
        return request.user.is_authenticated


class IsOwner(BasePermission):
    """Require user owns the resource."""

    message = "You do not have permission to access this resource"

    def has_permission(self, source, info: Info, **kwargs) -> bool:
        request = info.context.request
        if not request.user.is_authenticated:
            return False
        # Ownership check is done at resolver level
        return True


# =============================================================================
# TYPES - User & Profile
# =============================================================================


@strawberry.type
class UserProfileType:
    """User profile information."""

    branch_of_service: Optional[str]
    disability_rating: Optional[int]
    date_of_birth: Optional[date]

    @strawberry.field
    def age(self) -> Optional[int]:
        if self.date_of_birth:
            today = date.today()
            return (
                today.year
                - self.date_of_birth.year
                - (
                    (today.month, today.day)
                    < (self.date_of_birth.month, self.date_of_birth.day)
                )
            )
        return None


@strawberry.type
class SubscriptionType:
    """User subscription details."""

    plan_type: str
    status: str
    is_active: bool
    current_period_end: Optional[datetime]
    cancel_at_period_end: bool


@strawberry.type
class UserType:
    """Current user information."""

    id: strawberry.ID
    email: str
    first_name: str
    last_name: str
    is_premium: bool
    date_joined: datetime

    @strawberry.field
    def full_name(self) -> str:
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email


# =============================================================================
# TYPES - Documents & Claims
# =============================================================================


@strawberry.type
class DocumentType:
    """Uploaded document with OCR and AI analysis."""

    id: strawberry.ID
    file_name: str
    file_size: int
    mime_type: str
    document_type: str
    status: str
    ocr_confidence: Optional[float]
    page_count: int
    ai_model_used: str
    ai_tokens_used: int
    created_at: datetime
    processed_at: Optional[datetime]

    @strawberry.field
    def file_size_mb(self) -> float:
        return round(self.file_size / (1024 * 1024), 2)

    @strawberry.field
    def is_processing(self) -> bool:
        return self.status in ["uploading", "processing", "analyzing"]

    @strawberry.field
    def is_complete(self) -> bool:
        return self.status == "completed"


@strawberry.type
class DocumentAnalysisType:
    """AI analysis results for a document."""

    document_id: strawberry.ID
    # ocr_text removed for PHI protection - raw text is no longer persisted
    ocr_status: str  # 'pending', 'completed', or 'failed'
    ocr_length: int  # Character count of extracted text (metadata only)
    ai_summary: Optional[str]  # JSON string


@strawberry.type
class ClaimType:
    """VA claim with associated documents."""

    id: strawberry.ID
    title: str
    description: str
    claim_type: str
    status: str
    submission_date: Optional[date]
    decision_date: Optional[date]
    created_at: datetime
    document_count: int

    @strawberry.field
    def days_since_submission(self) -> Optional[int]:
        if self.submission_date:
            delta = date.today() - self.submission_date
            return delta.days
        return None


# =============================================================================
# TYPES - Journey
# =============================================================================


@strawberry.type
class JourneyStageType:
    """Stage in the VA claims journey."""

    id: strawberry.ID
    code: str
    name: str
    description: str
    order: int
    typical_duration_days: Optional[int]
    icon: str
    color: str


@strawberry.type
class JourneyEventType:
    """User event in their claims journey."""

    id: strawberry.ID
    title: str
    description: str
    event_date: date
    event_type: str
    is_completed: bool
    stage: JourneyStageType

    @strawberry.field
    def is_future(self) -> bool:
        return self.event_date > date.today()

    @strawberry.field
    def is_overdue(self) -> bool:
        return not self.is_completed and self.event_date < date.today()


@strawberry.type
class DeadlineType:
    """Important deadline for claims/appeals."""

    id: strawberry.ID
    title: str
    description: str
    deadline_date: date
    priority: str
    is_completed: bool

    @strawberry.field
    def days_remaining(self) -> Optional[int]:
        if self.is_completed:
            return None
        delta = self.deadline_date - date.today()
        return delta.days

    @strawberry.field
    def is_overdue(self) -> bool:
        return not self.is_completed and self.deadline_date < date.today()

    @strawberry.field
    def urgency_class(self) -> str:
        days = self.days_remaining
        if days is None:
            return "completed"
        if days < 0:
            return "overdue"
        if days <= 7:
            return "urgent"
        if days <= 30:
            return "soon"
        return "normal"


@strawberry.type
class MilestoneType:
    """Major milestone in user's journey."""

    id: strawberry.ID
    milestone_type: str
    title: str
    date: date
    notes: str


# =============================================================================
# TYPES - Stats & Summary
# =============================================================================


@strawberry.type
class DashboardStatsType:
    """Dashboard statistics for the user."""

    total_documents: int
    documents_this_month: int
    active_claims: int
    pending_deadlines: int
    completed_milestones: int
    current_rating: Optional[int]
    uploads_remaining: Optional[int]  # For free tier users


@strawberry.type
class UsageType:
    """User's current usage information."""

    documents_this_month: int
    documents_limit: Optional[int]
    storage_used_mb: float
    storage_limit_mb: Optional[float]
    is_premium: bool


# =============================================================================
# QUERIES
# =============================================================================


@strawberry.type
class Query:
    @strawberry.field(permission_classes=[IsAuthenticated])
    def me(self, info: Info) -> UserType:
        """Get current authenticated user."""
        user = info.context.request.user
        return UserType(
            id=strawberry.ID(str(user.id)),
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            is_premium=user.is_premium,
            date_joined=user.date_joined,
        )

    @strawberry.field(permission_classes=[IsAuthenticated])
    def my_profile(self, info: Info) -> Optional[UserProfileType]:
        """Get current user's profile."""
        user = info.context.request.user
        if hasattr(user, "profile"):
            profile = user.profile
            return UserProfileType(
                branch_of_service=profile.branch_of_service,
                disability_rating=profile.disability_rating,
                date_of_birth=profile.date_of_birth,
            )
        return None

    @strawberry.field(permission_classes=[IsAuthenticated])
    def my_subscription(self, info: Info) -> Optional[SubscriptionType]:
        """Get current user's subscription."""
        user = info.context.request.user
        try:
            sub = user.subscription
            return SubscriptionType(
                plan_type=sub.plan_type,
                status=sub.status,
                is_active=sub.is_active,
                current_period_end=sub.current_period_end,
                cancel_at_period_end=sub.cancel_at_period_end,
            )
        except Exception:
            return None

    @strawberry.field(permission_classes=[IsAuthenticated])
    def my_documents(
        self,
        info: Info,
        status: Optional[str] = None,
        document_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[DocumentType]:
        """Get current user's documents with optional filters."""
        from claims.models import Document

        user = info.context.request.user
        queryset = Document.objects.filter(user=user)

        if status:
            queryset = queryset.filter(status=status)
        if document_type:
            queryset = queryset.filter(document_type=document_type)

        docs = queryset[offset : offset + limit]
        return [
            DocumentType(
                id=strawberry.ID(str(d.id)),
                file_name=d.file_name,
                file_size=d.file_size,
                mime_type=d.mime_type,
                document_type=d.document_type,
                status=d.status,
                ocr_confidence=d.ocr_confidence,
                page_count=d.page_count,
                ai_model_used=d.ai_model_used,
                ai_tokens_used=d.ai_tokens_used,
                created_at=d.created_at,
                processed_at=d.processed_at,
            )
            for d in docs
        ]

    @strawberry.field(permission_classes=[IsAuthenticated])
    def document(self, info: Info, id: strawberry.ID) -> Optional[DocumentType]:
        """Get a specific document by ID (must be owned by user)."""
        from claims.models import Document

        user = info.context.request.user
        try:
            d = Document.objects.get(id=id, user=user)
            return DocumentType(
                id=strawberry.ID(str(d.id)),
                file_name=d.file_name,
                file_size=d.file_size,
                mime_type=d.mime_type,
                document_type=d.document_type,
                status=d.status,
                ocr_confidence=d.ocr_confidence,
                page_count=d.page_count,
                ai_model_used=d.ai_model_used,
                ai_tokens_used=d.ai_tokens_used,
                created_at=d.created_at,
                processed_at=d.processed_at,
            )
        except Document.DoesNotExist:
            return None

    @strawberry.field(permission_classes=[IsAuthenticated])
    def document_analysis(
        self, info: Info, id: strawberry.ID
    ) -> Optional[DocumentAnalysisType]:
        """
        Get OCR text and AI analysis for a document.

        Security: PII (SSNs, VA file numbers, phone numbers) is redacted.
        Response is truncated to prevent large data exfiltration.
        """
        from claims.models import Document
        import json

        user = info.context.request.user
        try:
            d = Document.objects.get(id=id, user=user)

            # Sanitize AI summary: redact PII and truncate
            ai_summary_str = json.dumps(d.ai_summary) if d.ai_summary else None
            sanitized_summary = (
                sanitize_graphql_text(ai_summary_str, MAX_AI_SUMMARY_LENGTH)
                if ai_summary_str
                else None
            )

            # Return OCR metadata (not raw text) for PHI protection
            return DocumentAnalysisType(
                document_id=strawberry.ID(str(d.id)),
                ocr_status=d.ocr_status or "pending",
                ocr_length=d.ocr_length or 0,
                ai_summary=sanitized_summary,
            )
        except Document.DoesNotExist:
            return None

    @strawberry.field(permission_classes=[IsAuthenticated])
    def my_claims(
        self,
        info: Info,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ClaimType]:
        """Get current user's claims."""
        from claims.models import Claim

        user = info.context.request.user
        queryset = Claim.objects.filter(user=user)

        if status:
            queryset = queryset.filter(status=status)

        claims = queryset[offset : offset + limit]
        return [
            ClaimType(
                id=strawberry.ID(str(c.id)),
                title=c.title,
                description=c.description,
                claim_type=c.claim_type,
                status=c.status,
                submission_date=c.submission_date,
                decision_date=c.decision_date,
                created_at=c.created_at,
                document_count=c.document_count,
            )
            for c in claims
        ]

    @strawberry.field(permission_classes=[IsAuthenticated])
    def my_deadlines(
        self,
        info: Info,
        include_completed: bool = False,
        limit: int = 20,
    ) -> List[DeadlineType]:
        """Get current user's deadlines."""
        from core.models import Deadline

        user = info.context.request.user
        queryset = Deadline.objects.filter(user=user)

        if not include_completed:
            queryset = queryset.filter(is_completed=False)

        deadlines = queryset[:limit]
        return [
            DeadlineType(
                id=strawberry.ID(str(d.id)),
                title=d.title,
                description=d.description,
                deadline_date=d.deadline_date,
                priority=d.priority,
                is_completed=d.is_completed,
            )
            for d in deadlines
        ]

    @strawberry.field(permission_classes=[IsAuthenticated])
    def my_journey_events(
        self,
        info: Info,
        limit: int = 50,
    ) -> List[JourneyEventType]:
        """Get current user's journey events."""
        from core.models import UserJourneyEvent

        user = info.context.request.user
        events = UserJourneyEvent.objects.filter(user=user).select_related("stage")[
            :limit
        ]

        return [
            JourneyEventType(
                id=strawberry.ID(str(e.id)),
                title=e.title,
                description=e.description,
                event_date=e.event_date,
                event_type=e.event_type,
                is_completed=e.is_completed,
                stage=JourneyStageType(
                    id=strawberry.ID(str(e.stage.id)),
                    code=e.stage.code,
                    name=e.stage.name,
                    description=e.stage.description,
                    order=e.stage.order,
                    typical_duration_days=e.stage.typical_duration_days,
                    icon=e.stage.icon,
                    color=e.stage.color,
                ),
            )
            for e in events
        ]

    @strawberry.field(permission_classes=[IsAuthenticated])
    def my_milestones(self, info: Info, limit: int = 20) -> List[MilestoneType]:
        """Get current user's journey milestones."""
        from core.models import JourneyMilestone

        user = info.context.request.user
        milestones = JourneyMilestone.objects.filter(user=user)[:limit]

        return [
            MilestoneType(
                id=strawberry.ID(str(m.id)),
                milestone_type=m.milestone_type,
                title=m.title,
                date=m.date,
                notes=m.notes,
            )
            for m in milestones
        ]

    @strawberry.field(permission_classes=[IsAuthenticated])
    def dashboard_stats(self, info: Info) -> DashboardStatsType:
        """Get dashboard statistics for current user."""
        from claims.models import Document, Claim
        from core.models import Deadline, JourneyMilestone
        from django.utils import timezone
        from django.conf import settings

        user = info.context.request.user

        # Get current month's document count
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        docs_this_month = Document.objects.filter(
            user=user, created_at__gte=month_start
        ).count()

        # Calculate uploads remaining for free tier
        uploads_remaining = None
        if not user.is_premium:
            limit = getattr(settings, "FREE_TIER_DOCUMENTS_PER_MONTH", 3)
            uploads_remaining = max(0, limit - docs_this_month)

        # Get current rating from profile
        current_rating = None
        if hasattr(user, "profile") and user.profile.disability_rating:
            current_rating = user.profile.disability_rating

        return DashboardStatsType(
            total_documents=Document.objects.filter(user=user).count(),
            documents_this_month=docs_this_month,
            active_claims=Claim.objects.filter(
                user=user,
                status__in=["draft", "gathering_evidence", "submitted", "pending"],
            ).count(),
            pending_deadlines=Deadline.objects.filter(
                user=user, is_completed=False
            ).count(),
            completed_milestones=JourneyMilestone.objects.filter(user=user).count(),
            current_rating=current_rating,
            uploads_remaining=uploads_remaining,
        )

    @strawberry.field(permission_classes=[IsAuthenticated])
    def my_usage(self, info: Info) -> UsageType:
        """Get current user's usage statistics."""
        from claims.models import Document
        from django.utils import timezone
        from django.db.models import Sum
        from django.conf import settings

        user = info.context.request.user

        # Get current month's document count
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        docs_this_month = Document.objects.filter(
            user=user, created_at__gte=month_start
        ).count()

        # Calculate storage used
        storage_bytes = (
            Document.objects.filter(user=user).aggregate(total=Sum("file_size"))[
                "total"
            ]
            or 0
        )
        storage_mb = storage_bytes / (1024 * 1024)

        # Get limits based on tier
        is_premium = user.is_premium
        docs_limit = (
            None
            if is_premium
            else getattr(settings, "FREE_TIER_DOCUMENTS_PER_MONTH", 3)
        )
        storage_limit = (
            None if is_premium else getattr(settings, "FREE_TIER_MAX_STORAGE_MB", 100)
        )

        return UsageType(
            documents_this_month=docs_this_month,
            documents_limit=docs_limit,
            storage_used_mb=round(storage_mb, 2),
            storage_limit_mb=float(storage_limit) if storage_limit else None,
            is_premium=is_premium,
        )

    @strawberry.field
    def journey_stages(self) -> List[JourneyStageType]:
        """Get all journey stages (public)."""
        from core.models import JourneyStage

        stages = JourneyStage.objects.all()
        return [
            JourneyStageType(
                id=strawberry.ID(str(s.id)),
                code=s.code,
                name=s.name,
                description=s.description,
                order=s.order,
                typical_duration_days=s.typical_duration_days,
                icon=s.icon,
                color=s.color,
            )
            for s in stages
        ]


# =============================================================================
# MUTATIONS
# =============================================================================


@strawberry.type
class Mutation:
    @strawberry.mutation(permission_classes=[IsAuthenticated])
    def complete_deadline(
        self, info: Info, id: strawberry.ID
    ) -> Optional[DeadlineType]:
        """Mark a deadline as completed."""
        from core.models import Deadline

        user = info.context.request.user
        try:
            deadline = Deadline.objects.get(id=id, user=user)
            deadline.mark_complete()
            return DeadlineType(
                id=strawberry.ID(str(deadline.id)),
                title=deadline.title,
                description=deadline.description,
                deadline_date=deadline.deadline_date,
                priority=deadline.priority,
                is_completed=deadline.is_completed,
            )
        except Deadline.DoesNotExist:
            return None

    @strawberry.mutation(permission_classes=[IsAuthenticated])
    def update_profile(
        self,
        info: Info,
        branch_of_service: Optional[str] = None,
        disability_rating: Optional[int] = None,
    ) -> Optional[UserProfileType]:
        """Update user profile."""
        user = info.context.request.user
        if not hasattr(user, "profile"):
            return None

        profile = user.profile
        if branch_of_service is not None:
            profile.branch_of_service = branch_of_service
        if disability_rating is not None:
            profile.disability_rating = disability_rating
        profile.save()

        return UserProfileType(
            branch_of_service=profile.branch_of_service,
            disability_rating=profile.disability_rating,
            date_of_birth=profile.date_of_birth,
        )


# =============================================================================
# SCHEMA
# =============================================================================

schema = strawberry.Schema(query=Query, mutation=Mutation)
