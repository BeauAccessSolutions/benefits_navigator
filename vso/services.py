"""
VSO Services - Business logic for condition derivation and gap checking.

This module provides services for:
- Deriving conditions from AI analyses (rating analysis, decision analysis)
- Checking evidence gaps for conditions
- Determining triage labels for cases
"""

import logging
from typing import List, Optional

from django.db import transaction

from .models import CaseCondition, SharedAnalysis, VeteranCase

logger = logging.getLogger(__name__)


class ConditionDerivationService:
    """
    Service for automatically deriving CaseCondition records from AI analyses.

    When a SharedAnalysis is created, this service extracts condition information
    and creates corresponding CaseCondition records.
    """

    @staticmethod
    @transaction.atomic
    def derive_conditions_from_analysis(
        shared_analysis: SharedAnalysis,
    ) -> List[CaseCondition]:
        """
        Extract conditions from a SharedAnalysis and create CaseCondition records.

        Args:
            shared_analysis: The SharedAnalysis instance to extract conditions from

        Returns:
            List of created or updated CaseCondition records
        """
        conditions_created = []
        case = shared_analysis.case

        try:
            if (
                shared_analysis.analysis_type == "rating_analysis"
                and shared_analysis.rating_analysis
            ):
                conditions_created = (
                    ConditionDerivationService._derive_from_rating_analysis(
                        case, shared_analysis
                    )
                )
            elif (
                shared_analysis.analysis_type == "decision_analysis"
                and shared_analysis.decision_analysis
            ):
                conditions_created = (
                    ConditionDerivationService._derive_from_decision_analysis(
                        case, shared_analysis
                    )
                )
        except Exception as e:
            logger.error(
                f"Error deriving conditions from analysis {shared_analysis.pk}: {e}"
            )

        return conditions_created

    @staticmethod
    def _derive_from_rating_analysis(
        case: VeteranCase, shared_analysis: SharedAnalysis
    ) -> List[CaseCondition]:
        """Extract conditions from a rating analysis."""
        conditions_created = []
        rating_analysis = shared_analysis.rating_analysis

        # Get conditions from the analysis
        # Rating analysis stores conditions in a 'conditions' field
        if hasattr(rating_analysis, "conditions") and rating_analysis.conditions:
            analysis_conditions = rating_analysis.conditions
            if isinstance(analysis_conditions, list):
                for cond in analysis_conditions:
                    if isinstance(cond, dict) and cond.get("condition"):
                        condition, created = CaseCondition.objects.update_or_create(
                            case=case,
                            condition_name=cond["condition"],
                            defaults={
                                "diagnostic_code": cond.get("diagnostic_code", ""),
                                "current_rating": cond.get("current_rating"),
                                "workflow_status": ConditionDerivationService._map_rating_to_workflow_status(
                                    cond.get("current_rating")
                                ),
                                "source": "rating_analysis",
                                "source_analysis": shared_analysis,
                            },
                        )
                        conditions_created.append(condition)

        return conditions_created

    @staticmethod
    def _derive_from_decision_analysis(
        case: VeteranCase, shared_analysis: SharedAnalysis
    ) -> List[CaseCondition]:
        """Extract conditions from a decision letter analysis."""
        conditions_created = []
        decision_analysis = shared_analysis.decision_analysis

        # Process granted conditions
        if (
            hasattr(decision_analysis, "conditions_granted")
            and decision_analysis.conditions_granted
        ):
            granted = decision_analysis.conditions_granted
            if isinstance(granted, list):
                for cond in granted:
                    if isinstance(cond, dict) and cond.get("condition"):
                        condition, _ = CaseCondition.objects.update_or_create(
                            case=case,
                            condition_name=cond["condition"],
                            defaults={
                                "diagnostic_code": cond.get("diagnostic_code", ""),
                                "current_rating": cond.get("rating"),
                                "workflow_status": "granted",
                                "source": "decision_analysis",
                                "source_analysis": shared_analysis,
                                "has_diagnosis": True,
                                "has_in_service_event": True,
                                "has_nexus": True,
                            },
                        )
                        conditions_created.append(condition)

        # Process denied conditions
        if (
            hasattr(decision_analysis, "conditions_denied")
            and decision_analysis.conditions_denied
        ):
            denied = decision_analysis.conditions_denied
            if isinstance(denied, list):
                for cond in denied:
                    if isinstance(cond, dict) and cond.get("condition"):
                        condition, _ = CaseCondition.objects.update_or_create(
                            case=case,
                            condition_name=cond["condition"],
                            defaults={
                                "diagnostic_code": cond.get("diagnostic_code", ""),
                                "workflow_status": "denied",
                                "source": "decision_analysis",
                                "source_analysis": shared_analysis,
                                "notes": cond.get("denial_reason", ""),
                            },
                        )
                        conditions_created.append(condition)

        return conditions_created

    @staticmethod
    def _map_rating_to_workflow_status(rating: Optional[int]) -> str:
        """Map a rating percentage to a workflow status."""
        if rating is None:
            return "identified"
        elif rating > 0:
            return "granted"
        else:
            return "pending_decision"


class GapCheckerService:
    """
    Service for checking evidence gaps and determining case triage status.

    Analyzes shared documents and conditions to determine what evidence
    is missing and how ready a case is for filing.
    """

    # Triage label constants
    READY_TO_FILE = "ready_to_file"
    NEEDS_EVIDENCE = "needs_evidence"
    NEEDS_NEXUS = "needs_nexus"
    NEEDS_REVIEW = "needs_review"

    @staticmethod
    def get_triage_label(case: VeteranCase) -> str:
        """
        Determine the triage label for a case based on evidence completeness.

        Returns:
            One of: 'ready_to_file', 'needs_evidence', 'needs_nexus', 'needs_review'
        """
        conditions = case.case_conditions.exclude(
            workflow_status__in=["granted", "denied", "claim_filed", "pending_decision"]
        )

        if not conditions.exists():
            return GapCheckerService.NEEDS_REVIEW

        # Check evidence completeness across all active conditions
        all_complete = True
        missing_nexus_only = True
        missing_any_evidence = False

        for condition in conditions:
            if not condition.is_evidence_complete:
                all_complete = False

                if not condition.has_diagnosis or not condition.has_in_service_event:
                    missing_nexus_only = False
                    missing_any_evidence = True
                elif not condition.has_nexus:
                    # Only missing nexus
                    pass

        if all_complete:
            return GapCheckerService.READY_TO_FILE
        elif missing_any_evidence:
            return GapCheckerService.NEEDS_EVIDENCE
        elif not missing_nexus_only:
            return GapCheckerService.NEEDS_EVIDENCE
        else:
            return GapCheckerService.NEEDS_NEXUS

    @staticmethod
    def update_condition_gaps(case: VeteranCase) -> None:
        """
        Update gap fields on conditions based on shared document types.

        Examines shared documents to automatically mark evidence as present.
        """

        shared_docs = case.shared_documents.select_related("document").all()

        # Map document types to evidence types
        diagnosis_types = ["medical_record", "diagnosis", "treatment_record"]
        in_service_types = ["service_record", "str", "incident_report", "dd214"]
        nexus_types = ["nexus_letter", "dbe_report", "imo", "medical_opinion"]

        has_diagnosis_doc = any(
            sd.document.document_type in diagnosis_types
            for sd in shared_docs
            if hasattr(sd.document, "document_type")
        )
        has_in_service_doc = any(
            sd.document.document_type in in_service_types
            for sd in shared_docs
            if hasattr(sd.document, "document_type")
        )
        has_nexus_doc = any(
            sd.document.document_type in nexus_types
            for sd in shared_docs
            if hasattr(sd.document, "document_type")
        )

        # Update conditions that don't already have evidence marked
        conditions = case.case_conditions.all()
        for condition in conditions:
            updated = False

            if has_diagnosis_doc and not condition.has_diagnosis:
                condition.has_diagnosis = True
                updated = True

            if has_in_service_doc and not condition.has_in_service_event:
                condition.has_in_service_event = True
                updated = True

            if has_nexus_doc and not condition.has_nexus:
                condition.has_nexus = True
                updated = True

            if updated:
                condition.save()

    @staticmethod
    def get_triage_color(label: str) -> str:
        """Get the color class for a triage label."""
        colors = {
            GapCheckerService.READY_TO_FILE: "green",
            GapCheckerService.NEEDS_EVIDENCE: "red",
            GapCheckerService.NEEDS_NEXUS: "yellow",
            GapCheckerService.NEEDS_REVIEW: "gray",
        }
        return colors.get(label, "gray")

    @staticmethod
    def get_triage_display(label: str) -> str:
        """Get the display text for a triage label."""
        displays = {
            GapCheckerService.READY_TO_FILE: "Ready to File",
            GapCheckerService.NEEDS_EVIDENCE: "Needs Evidence",
            GapCheckerService.NEEDS_NEXUS: "Needs Nexus",
            GapCheckerService.NEEDS_REVIEW: "Needs Review",
        }
        return displays.get(label, "Unknown")
