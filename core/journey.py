"""
Journey timeline building logic.
Aggregates claims, appeals, events, and milestones into a unified timeline.
"""

from datetime import date, timedelta
from typing import List, Dict, Any, Optional


from .models import JourneyStage, UserJourneyEvent, JourneyMilestone, Deadline


class TimelineBuilder:
    """
    Builds a unified timeline from user's claims journey data.
    """

    def __init__(self, user):
        self.user = user

    def build_timeline(
        self,
        include_claims: bool = True,
        include_appeals: bool = True,
        include_events: bool = True,
        include_milestones: bool = True,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build a unified timeline of all journey events.

        Returns list of timeline items sorted by date (most recent first).
        Each item has: type, date, title, description, metadata, icon, color
        """
        timeline = []

        if include_claims:
            timeline.extend(self._get_claim_events())

        if include_appeals:
            timeline.extend(self._get_appeal_events())

        if include_events:
            timeline.extend(self._get_journey_events())

        if include_milestones:
            timeline.extend(self._get_milestones())

        # Sort by date (most recent first)
        timeline.sort(key=lambda x: x["date"], reverse=True)

        if limit:
            timeline = timeline[:limit]

        return timeline

    def _get_claim_events(self) -> List[Dict[str, Any]]:
        """Get timeline items from claims."""
        from claims.models import Claim

        items = []
        claims = Claim.objects.filter(user=self.user, is_deleted=False)

        for claim in claims:
            # Claim filed event
            items.append(
                {
                    "type": "claim",
                    "subtype": "filed",
                    "date": claim.created_at.date(),
                    "title": f"Claim Filed: {claim.title}",
                    "description": f"{claim.get_claim_type_display()} claim submitted",
                    "icon": "document",
                    "color": "blue",
                    "metadata": {
                        "claim_id": claim.id,
                        "status": claim.status,
                    },
                }
            )

            # Status change events (if we had status history)
            if claim.status == "decided":
                items.append(
                    {
                        "type": "claim",
                        "subtype": "decision",
                        "date": claim.updated_at.date(),
                        "title": f"Decision Received: {claim.title}",
                        "description": "Decision received",
                        "icon": "mail",
                        "color": "green",
                        "metadata": {
                            "claim_id": claim.id,
                        },
                    }
                )

        return items

    def _get_appeal_events(self) -> List[Dict[str, Any]]:
        """Get timeline items from appeals."""
        from appeals.models import Appeal

        items = []
        appeals = Appeal.objects.filter(user=self.user)

        for appeal in appeals:
            # Appeal filed
            # Use conditions_appealed if available, otherwise use appeal type display
            appeal_title = (
                appeal.conditions_appealed[:50]
                if appeal.conditions_appealed
                else appeal.get_appeal_type_display()
            )
            items.append(
                {
                    "type": "appeal",
                    "subtype": "filed",
                    "date": appeal.created_at.date(),
                    "title": f"Appeal Filed: {appeal_title}",
                    "description": appeal.get_appeal_type_display(),
                    "icon": "flag",
                    "color": "purple",
                    "metadata": {
                        "appeal_id": appeal.id,
                        "appeal_type": appeal.appeal_type,
                    },
                }
            )

        return items

    def _get_journey_events(self) -> List[Dict[str, Any]]:
        """Get user-created journey events."""
        events = UserJourneyEvent.objects.filter(user=self.user).select_related("stage")

        items = []
        for event in events:
            items.append(
                {
                    "type": "event",
                    "subtype": event.event_type,
                    "date": event.event_date,
                    "title": event.title,
                    "description": event.description,
                    "icon": event.stage.icon if event.stage else "calendar",
                    "color": event.stage.color if event.stage else "gray",
                    "metadata": {
                        "event_id": event.id,
                        "stage": event.stage.code if event.stage else None,
                        "is_completed": event.is_completed,
                    },
                }
            )

        return items

    def _get_milestones(self) -> List[Dict[str, Any]]:
        """Get journey milestones."""
        milestones = JourneyMilestone.objects.filter(user=self.user)

        items = []
        for milestone in milestones:
            # Determine icon and color based on milestone type
            icon, color = self._get_milestone_display(milestone.milestone_type)

            items.append(
                {
                    "type": "milestone",
                    "subtype": milestone.milestone_type,
                    "date": milestone.date,
                    "title": milestone.title,
                    "description": milestone.notes,
                    "icon": icon,
                    "color": color,
                    "metadata": {
                        "milestone_id": milestone.id,
                        "details": milestone.details,
                    },
                }
            )

        return items

    def _get_milestone_display(self, milestone_type: str) -> tuple:
        """Get icon and color for milestone type."""
        display_map = {
            "claim_filed": ("document", "blue"),
            "exam_scheduled": ("calendar", "yellow"),
            "exam_completed": ("check", "green"),
            "decision_received": ("mail", "blue"),
            "rating_assigned": ("check", "green"),
            "appeal_filed": ("flag", "purple"),
            "appeal_won": ("check", "green"),
            "increase_granted": ("check", "green"),
            "100_percent": ("check", "green"),
            "tdiu_granted": ("check", "green"),
            "custom": ("flag", "gray"),
        }
        return display_map.get(milestone_type, ("document", "gray"))

    def get_current_stage(self) -> Optional[Dict[str, Any]]:
        """
        Determine user's current stage in the journey.
        Based on most recent incomplete activity.
        """
        # Check for pending appeals
        from appeals.models import Appeal

        pending_appeals = Appeal.objects.filter(
            user=self.user,
            status__in=["submitted", "acknowledged", "in_review", "decision_pending"],
        ).first()

        if pending_appeals:
            return {
                "code": "appeal_pending",
                "name": "Appeal In Progress",
                "description": f"Waiting on {pending_appeals.get_appeal_type_display()}",
                "color": "purple",
            }

        # Check for pending claims
        from claims.models import Claim

        pending_claims = Claim.objects.filter(
            user=self.user, is_deleted=False, status__in=["submitted", "pending"]
        ).first()

        if pending_claims:
            status_map = {
                "submitted": (
                    "claim_submitted",
                    "Claim Submitted",
                    "Waiting for VA to process your claim",
                ),
                "pending": (
                    "claim_pending",
                    "Claim Pending",
                    "VA is reviewing your claim",
                ),
            }
            code, name, desc = status_map.get(
                pending_claims.status,
                ("claim_pending", "Claim Pending", "Waiting for VA"),
            )
            return {
                "code": code,
                "name": name,
                "description": desc,
                "color": "blue",
            }

        # Check for upcoming deadlines
        upcoming_deadline = Deadline.objects.filter(
            user=self.user, is_completed=False, deadline_date__gte=date.today()
        ).first()

        if upcoming_deadline:
            return {
                "code": "deadline_pending",
                "name": "Action Required",
                "description": f"{upcoming_deadline.title} due {upcoming_deadline.deadline_date}",
                "color": "yellow" if upcoming_deadline.days_remaining > 7 else "red",
            }

        # Default - gathering evidence
        return {
            "code": "preparing",
            "name": "Preparing Claims",
            "description": "Gathering evidence and preparing your case",
            "color": "gray",
        }

    def get_upcoming_deadlines(self, days: int = 90) -> List[Deadline]:
        """Get upcoming deadlines within the specified number of days."""
        today = date.today()
        cutoff = today + timedelta(days=days)
        return Deadline.objects.filter(
            user=self.user,
            is_completed=False,
            deadline_date__gte=today,  # Only future deadlines
            deadline_date__lte=cutoff,
        ).order_by("deadline_date")

    def get_stats(self) -> Dict[str, Any]:
        """Get summary statistics for the user's journey."""
        from claims.models import Claim
        from appeals.models import Appeal

        claims = Claim.objects.filter(user=self.user, is_deleted=False)
        appeals = Appeal.objects.filter(user=self.user)

        total_claims = claims.count()
        decided_claims = claims.filter(status="decided").count()
        pending_claims = claims.filter(status__in=["submitted", "pending"]).count()

        total_appeals = appeals.count()
        # Appeal.decision_outcome tracks the result: 'granted', 'partial', 'denied', 'remanded'
        won_appeals = appeals.filter(decision_outcome="granted").count()
        # Active appeals are those submitted but not yet decided
        pending_appeals = appeals.filter(
            status__in=["submitted", "acknowledged", "in_review", "decision_pending"]
        ).count()

        milestone_count = JourneyMilestone.objects.filter(user=self.user).count()
        deadline_count = Deadline.objects.filter(
            user=self.user, is_completed=False
        ).count()

        return {
            "total_claims": total_claims,
            "decided_claims": decided_claims,
            "pending_claims": pending_claims,
            "in_progress_claims": total_claims - decided_claims - pending_claims,
            "total_appeals": total_appeals,
            "won_appeals": won_appeals,
            "pending_appeals": pending_appeals,
            "milestone_count": milestone_count,
            "deadline_count": deadline_count,
        }


def create_default_stages():
    """
    Create default journey stages.
    Call this from a migration or management command.
    """
    stages = [
        {
            "code": "preparing",
            "name": "Preparing Your Case",
            "description": "Gathering evidence, medical records, and supporting documentation",
            "order": 10,
            "typical_duration_days": None,
            "icon": "clipboard",
            "color": "gray",
        },
        {
            "code": "claim_filed",
            "name": "Claim Filed",
            "description": "Your claim has been submitted to the VA",
            "order": 20,
            "typical_duration_days": 0,
            "icon": "document",
            "color": "blue",
        },
        {
            "code": "claim_received",
            "name": "Claim Received",
            "description": "VA has received and acknowledged your claim",
            "order": 30,
            "typical_duration_days": 7,
            "icon": "check",
            "color": "blue",
        },
        {
            "code": "evidence_gathering",
            "name": "Evidence Gathering",
            "description": "VA is collecting evidence for your claim",
            "order": 40,
            "typical_duration_days": 30,
            "icon": "clipboard",
            "color": "blue",
        },
        {
            "code": "exam_scheduled",
            "name": "C&P Exam Scheduled",
            "description": "Your Compensation & Pension exam has been scheduled",
            "order": 50,
            "typical_duration_days": 14,
            "icon": "calendar",
            "color": "yellow",
        },
        {
            "code": "exam_completed",
            "name": "C&P Exam Completed",
            "description": "You have completed your C&P examination",
            "order": 60,
            "typical_duration_days": 0,
            "icon": "check",
            "color": "green",
        },
        {
            "code": "rating_review",
            "name": "Rating Review",
            "description": "VA rater is reviewing your evidence and exam results",
            "order": 70,
            "typical_duration_days": 30,
            "icon": "clock",
            "color": "blue",
        },
        {
            "code": "decision_pending",
            "name": "Decision Pending",
            "description": "Your claim decision is being finalized",
            "order": 80,
            "typical_duration_days": 14,
            "icon": "clock",
            "color": "yellow",
        },
        {
            "code": "decision_received",
            "name": "Decision Received",
            "description": "You have received your claim decision",
            "order": 90,
            "typical_duration_days": 0,
            "icon": "mail",
            "color": "green",
        },
        {
            "code": "appeal_filed",
            "name": "Appeal Filed",
            "description": "You have filed an appeal",
            "order": 100,
            "typical_duration_days": 0,
            "icon": "flag",
            "color": "purple",
        },
    ]

    for stage_data in stages:
        JourneyStage.objects.update_or_create(
            code=stage_data["code"], defaults=stage_data
        )
