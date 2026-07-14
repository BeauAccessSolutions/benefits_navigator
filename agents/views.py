"""
Views for AI Agents
"""

from functools import wraps

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from decimal import Decimal
import logging

from core.models import AuditLog
from .models import (
    AgentInteraction,
    DecisionLetterAnalysis,
    EvidenceGapAnalysis,
    PersonalStatement,
)
from .services import (
    DecisionLetterAnalyzer,
    EvidenceGapAnalyzer,
    PersonalStatementGenerator,
)

logger = logging.getLogger(__name__)


# =============================================================================
# AI CONSENT ENFORCEMENT
# =============================================================================


def check_ai_consent(user):
    """
    Check if user has consented to AI processing.

    Args:
        user: User instance to check

    Returns:
        bool: True if user has AI processing consent
    """
    try:
        return bool(user.profile.ai_processing_consent)
    except Exception as e:
        logger.warning(
            "AI consent check failed for user %s: %s", user.pk, type(e).__name__
        )
        return False


def require_ai_consent_view(view_func):
    """
    Decorator for views that require AI processing consent.

    Redirects to privacy settings if consent not granted.
    Use this on any view that will trigger OpenAI API calls.
    """

    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not check_ai_consent(request.user):
            messages.warning(
                request,
                "AI processing consent is required to use this feature. "
                "Please grant consent in your privacy settings to continue.",
            )
            return redirect("accounts:privacy_settings")
        return view_func(request, *args, **kwargs)

    return _wrapped_view


def agents_home(request):
    """Landing page for AI agents"""
    context = {
        "agents": [
            {
                "name": "Decision Letter Analyzer",
                "slug": "decision_analyzer",
                "description": "Upload or paste your VA decision letter and get a plain-English breakdown of what was granted, denied, and your next steps.",
                "icon": "document-text",
                "color": "blue",
            },
            {
                "name": "Evidence Gap Analyzer",
                "slug": "evidence_gap",
                "description": "Find out what evidence you need to strengthen your claim before filing.",
                "icon": "search",
                "color": "purple",
            },
            {
                "name": "Personal Statement Generator",
                "slug": "statement_generator",
                "description": "Create a compelling personal statement for your VA claim with guided prompts.",
                "icon": "pencil",
                "color": "green",
            },
            {
                "name": "Condition Discovery",
                "slug": "condition_discovery",
                "description": "Identify conditions you may be able to claim based on your service history and existing ratings.",
                "icon": "search",
                "color": "yellow",
            },
        ]
    }
    return render(request, "agents/home.html", context)


# =============================================================================
# DECISION LETTER ANALYZER
# =============================================================================


@login_required
def decision_analyzer(request):
    """Decision Letter Analyzer - input form"""
    # Get user's past analyses with related data to avoid N+1 queries
    past_analyses = (
        DecisionLetterAnalysis.objects.filter(user=request.user)
        .select_related("interaction", "document")
        .order_by("-created_at")[:5]
    )

    context = {
        "past_analyses": past_analyses,
    }
    return render(request, "agents/decision_analyzer.html", context)


@login_required
@require_POST
@require_ai_consent_view
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def decision_analyzer_submit(request):
    """
    Process decision letter analysis.

    Rate limited to 20/hr per user to prevent API cost abuse and prompt injection probing.
    """
    letter_text = request.POST.get("letter_text", "").strip()
    decision_date_str = request.POST.get("decision_date", "")

    if not letter_text:
        messages.error(request, "Please paste your decision letter text.")
        return redirect("agents:decision_analyzer")

    if len(letter_text) < 100:
        messages.error(
            request, "The text seems too short. Please paste the full decision letter."
        )
        return redirect("agents:decision_analyzer")

    # Parse decision date if provided
    decision_date = None
    if decision_date_str:
        try:
            from datetime import datetime

            decision_date = datetime.strptime(decision_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    try:
        # Create interaction record
        interaction = AgentInteraction.objects.create(
            user=request.user, agent_type="decision_analyzer", status="processing"
        )

        # Run analysis
        analyzer = DecisionLetterAnalyzer()
        result = analyzer.analyze(letter_text, decision_date)

        # Update interaction
        interaction.tokens_used = result.get("_tokens_used", 0)
        interaction.cost_estimate = Decimal(str(result.get("_cost_estimate", 0)))
        interaction.status = "completed"
        interaction.save()

        # Parse appeal deadline
        appeal_deadline = None
        if result.get("appeal_deadline"):
            try:
                from datetime import datetime

                appeal_deadline = datetime.strptime(
                    result["appeal_deadline"], "%Y-%m-%d"
                ).date()
            except (ValueError, TypeError):
                pass

        # Save analysis (raw_text removed for PHI protection)
        analysis = DecisionLetterAnalysis.objects.create(
            interaction=interaction,
            user=request.user,
            decision_date=decision_date,
            conditions_granted=result.get("conditions_granted", []),
            conditions_denied=result.get("conditions_denied", []),
            conditions_deferred=result.get("conditions_deferred", []),
            summary=result.get("summary", ""),
            appeal_options=result.get("appeal_options", []),
            evidence_issues=result.get("evidence_issues", []),
            action_items=result.get("action_items", []),
            appeal_deadline=appeal_deadline,
        )

        # Audit log: AI decision analyzer run
        AuditLog.log(
            action="ai_decision_analyzer",
            request=request,
            resource_type="DecisionLetterAnalysis",
            resource_id=analysis.pk,
            details={
                "tokens_used": interaction.tokens_used,
                "conditions_granted_count": len(result.get("conditions_granted", [])),
                "conditions_denied_count": len(result.get("conditions_denied", [])),
            },
            success=True,
        )

        return redirect("agents:decision_analyzer_result", pk=analysis.pk)

    except Exception as e:
        logger.error(f"Decision analysis error: {str(e)}")
        if "interaction" in locals():
            interaction.status = "failed"
            interaction.error_message = str(e)
            interaction.save()

        # Audit log: AI decision analyzer failure
        AuditLog.log(
            action="ai_decision_analyzer",
            request=request,
            resource_type="DecisionLetterAnalysis",
            details={"error_type": type(e).__name__},
            success=False,
            error_message=str(e)[:500],
        )

        messages.error(request, f"Analysis failed: {str(e)}")
        return redirect("agents:decision_analyzer")


@login_required
def decision_analyzer_result(request, pk):
    """Display decision letter analysis results"""
    analysis = get_object_or_404(DecisionLetterAnalysis, pk=pk, user=request.user)

    context = {
        "analysis": analysis,
    }
    return render(request, "agents/decision_analyzer_result.html", context)


# =============================================================================
# EVIDENCE GAP ANALYZER
# =============================================================================


@login_required
def evidence_gap_analyzer(request):
    """Evidence Gap Analyzer - input form"""
    # Get user's past analyses with related data to avoid N+1 queries
    past_analyses = (
        EvidenceGapAnalysis.objects.filter(user=request.user)
        .select_related("interaction")
        .order_by("-created_at")[:5]
    )

    # Common conditions for quick select
    common_conditions = [
        "PTSD",
        "Anxiety",
        "Depression",
        "Tinnitus",
        "Hearing Loss",
        "Back Pain / Lumbar Strain",
        "Knee Condition",
        "Shoulder Condition",
        "Sleep Apnea",
        "Migraines",
        "TBI",
        "GERD",
        "Hypertension",
        "Radiculopathy",
        "Plantar Fasciitis",
        "Carpal Tunnel",
    ]

    evidence_types = [
        "Service Treatment Records (STRs)",
        "VA Medical Records",
        "Private Medical Records",
        "Nexus Letter / Medical Opinion",
        "Buddy Statement(s)",
        "Personal Statement",
        "DBQ (Disability Benefits Questionnaire)",
        "DD-214",
        "Personnel Records",
        "Incident Reports",
    ]

    context = {
        "past_analyses": past_analyses,
        "common_conditions": common_conditions,
        "evidence_types": evidence_types,
    }
    return render(request, "agents/evidence_gap.html", context)


@login_required
@require_POST
@require_ai_consent_view
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def evidence_gap_submit(request):
    """
    Process evidence gap analysis.

    Rate limited to 20/hr per user to prevent API cost abuse.
    """
    # Get conditions (could be multiple)
    conditions = request.POST.getlist("conditions")
    custom_conditions = request.POST.get("custom_conditions", "").strip()

    if custom_conditions:
        conditions.extend(
            [c.strip() for c in custom_conditions.split(",") if c.strip()]
        )

    if not conditions:
        messages.error(request, "Please select or enter at least one condition.")
        return redirect("agents:evidence_gap")

    # Get existing evidence
    evidence = request.POST.getlist("evidence")
    custom_evidence = request.POST.get("custom_evidence", "").strip()

    if custom_evidence:
        evidence.extend([e.strip() for e in custom_evidence.split(",") if e.strip()])

    service_dates = request.POST.get("service_dates", "")
    service_branch = request.POST.get("service_branch", "")

    try:
        # Create interaction
        interaction = AgentInteraction.objects.create(
            user=request.user, agent_type="evidence_gap", status="processing"
        )

        # Run analysis
        analyzer = EvidenceGapAnalyzer()
        result = analyzer.analyze(conditions, evidence, service_dates, service_branch)

        # Update interaction
        interaction.tokens_used = result.get("_tokens_used", 0)
        interaction.cost_estimate = Decimal(str(result.get("_cost_estimate", 0)))
        interaction.status = "completed"
        interaction.save()

        # Save analysis
        analysis = EvidenceGapAnalysis.objects.create(
            interaction=interaction,
            user=request.user,
            claimed_conditions=conditions,
            existing_evidence=evidence,
            service_dates=service_dates,
            service_branch=service_branch,
            evidence_gaps=result.get("evidence_gaps", []),
            strength_assessment=result.get("strength_assessment", {}),
            recommendations=result.get("recommendations", []),
            templates_suggested=result.get("templates_suggested", []),
            readiness_score=result.get("readiness_score", 0),
        )

        # Audit log: AI evidence gap analyzer run
        AuditLog.log(
            action="ai_evidence_gap",
            request=request,
            resource_type="EvidenceGapAnalysis",
            resource_id=analysis.pk,
            details={
                "tokens_used": interaction.tokens_used,
                "conditions_count": len(conditions),
                "readiness_score": result.get("readiness_score", 0),
            },
            success=True,
        )

        return redirect("agents:evidence_gap_result", pk=analysis.pk)

    except Exception as e:
        logger.error(f"Evidence gap analysis error: {str(e)}")
        if "interaction" in locals():
            interaction.status = "failed"
            interaction.error_message = str(e)
            interaction.save()

        # Audit log: AI evidence gap analyzer failure
        AuditLog.log(
            action="ai_evidence_gap",
            request=request,
            resource_type="EvidenceGapAnalysis",
            details={
                "error_type": type(e).__name__,
                "conditions_count": len(conditions),
            },
            success=False,
            error_message=str(e)[:500],
        )

        messages.error(request, f"Analysis failed: {str(e)}")
        return redirect("agents:evidence_gap")


@login_required
def evidence_gap_result(request, pk):
    """Display evidence gap analysis results"""
    analysis = get_object_or_404(EvidenceGapAnalysis, pk=pk, user=request.user)

    context = {
        "analysis": analysis,
    }
    return render(request, "agents/evidence_gap_result.html", context)


# =============================================================================
# PERSONAL STATEMENT GENERATOR
# =============================================================================


@login_required
def statement_generator(request):
    """Personal Statement Generator - input form"""
    # Get user's past statements with related data to avoid N+1 queries
    past_statements = (
        PersonalStatement.objects.filter(user=request.user)
        .select_related("interaction")
        .order_by("-created_at")[:5]
    )

    context = {
        "past_statements": past_statements,
        "statement_types": [
            ("initial", "Initial Claim", "First time claiming this condition"),
            ("increase", "Rating Increase", "Condition has gotten worse"),
            (
                "secondary",
                "Secondary Condition",
                "Caused by another service-connected condition",
            ),
            ("appeal", "Appeal Statement", "Supporting a denied claim appeal"),
        ],
    }
    return render(request, "agents/statement_generator.html", context)


@login_required
@require_POST
@require_ai_consent_view
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def statement_generator_submit(request):
    """
    Process personal statement generation.

    Rate limited to 20/hr per user to prevent API cost abuse.
    """
    condition = request.POST.get("condition", "").strip()
    statement_type = request.POST.get("statement_type", "initial")
    in_service_event = request.POST.get("in_service_event", "").strip()
    current_symptoms = request.POST.get("current_symptoms", "").strip()
    daily_impact = request.POST.get("daily_impact", "").strip()
    work_impact = request.POST.get("work_impact", "").strip()
    treatment_history = request.POST.get("treatment_history", "").strip()
    worst_days = request.POST.get("worst_days", "").strip()

    # Validation
    errors = []
    if not condition:
        errors.append("Condition is required")
    if not in_service_event:
        errors.append("In-service event description is required")
    if not current_symptoms:
        errors.append("Current symptoms description is required")
    if not daily_impact:
        errors.append("Daily life impact description is required")

    if errors:
        for error in errors:
            messages.error(request, error)
        return redirect("agents:statement_generator")

    try:
        # Create interaction
        interaction = AgentInteraction.objects.create(
            user=request.user, agent_type="statement_generator", status="processing"
        )

        # Generate statement
        generator = PersonalStatementGenerator()
        result = generator.generate(
            condition=condition,
            in_service_event=in_service_event,
            current_symptoms=current_symptoms,
            daily_impact=daily_impact,
            work_impact=work_impact,
            treatment_history=treatment_history,
            worst_days=worst_days,
            statement_type=statement_type,
        )

        # Update interaction
        interaction.tokens_used = result.get("_tokens_used", 0)
        interaction.cost_estimate = Decimal(str(result.get("_cost_estimate", 0)))
        interaction.status = "completed"
        interaction.save()

        # Save statement
        statement = PersonalStatement.objects.create(
            interaction=interaction,
            user=request.user,
            condition=condition,
            statement_type=statement_type,
            in_service_event=in_service_event,
            current_symptoms=current_symptoms,
            daily_impact=daily_impact,
            work_impact=work_impact,
            treatment_history=treatment_history,
            worst_days=worst_days,
            generated_statement=result.get("statement", ""),
        )

        # Audit log: AI statement generator run
        AuditLog.log(
            action="ai_statement_generator",
            request=request,
            resource_type="PersonalStatement",
            resource_id=statement.pk,
            details={
                "tokens_used": interaction.tokens_used,
                "condition": condition,
                "statement_type": statement_type,
            },
            success=True,
        )

        return redirect("agents:statement_result", pk=statement.pk)

    except Exception as e:
        logger.error(f"Statement generation error: {str(e)}")
        if "interaction" in locals():
            interaction.status = "failed"
            interaction.error_message = str(e)
            interaction.save()

        # Audit log: AI statement generator failure
        AuditLog.log(
            action="ai_statement_generator",
            request=request,
            resource_type="PersonalStatement",
            details={"error_type": type(e).__name__, "condition": condition},
            success=False,
            error_message=str(e)[:500],
        )

        messages.error(request, f"Generation failed: {str(e)}")
        return redirect("agents:statement_generator")


@login_required
def statement_result(request, pk):
    """Display generated personal statement"""
    statement = get_object_or_404(PersonalStatement, pk=pk, user=request.user)

    context = {
        "statement": statement,
    }
    return render(request, "agents/statement_result.html", context)


@login_required
@require_POST
def statement_save_final(request, pk):
    """Save user's edited final statement"""
    statement = get_object_or_404(PersonalStatement, pk=pk, user=request.user)

    final_text = request.POST.get("final_statement", "").strip()

    if final_text:
        statement.final_statement = final_text
        statement.is_finalized = True
        statement.save()
        messages.success(request, "Your personal statement has been saved.")
    else:
        messages.error(request, "Please enter your statement text.")

    return redirect("agents:statement_result", pk=pk)


# =============================================================================
# HISTORY VIEWS
# =============================================================================


@login_required
def agent_history(request):
    """View all agent interaction history"""
    interactions = (
        AgentInteraction.objects.filter(user=request.user)
        .select_related("decision_analysis", "evidence_analysis", "personal_statement")
        .order_by("-created_at")[:50]
    )

    context = {
        "interactions": interactions,
    }
    return render(request, "agents/history.html", context)


# =============================================================================
# CONDITION DISCOVERY TOOL
# =============================================================================

# Common conditions by service era and branch
CONDITION_DATABASE = {
    "hearing_loss": {
        "name": "Hearing Loss / Tinnitus",
        "description": "Noise-induced hearing damage common in military service",
        "common_for": ["army", "marines", "navy", "air_force"],
        "service_eras": ["vietnam", "gulf", "oef_oif", "peacetime"],
        "risk_factors": [
            "artillery",
            "aviation",
            "infantry",
            "vehicle crew",
            "shipboard",
        ],
        "secondary_to": [],
        "avg_rating": "10-50%",
    },
    "ptsd": {
        "name": "PTSD / Anxiety / Depression",
        "description": "Mental health conditions from combat or military stress",
        "common_for": ["army", "marines", "navy", "air_force"],
        "service_eras": ["vietnam", "gulf", "oef_oif"],
        "risk_factors": ["combat", "mst", "deployment", "trauma exposure"],
        "secondary_to": [],
        "avg_rating": "30-100%",
    },
    "back_conditions": {
        "name": "Back / Spine Conditions",
        "description": "Degenerative disc disease, herniated discs, chronic pain",
        "common_for": ["army", "marines", "navy", "air_force"],
        "service_eras": ["all"],
        "risk_factors": ["infantry", "parachute", "heavy lifting", "vehicle accidents"],
        "secondary_to": [],
        "avg_rating": "10-40%",
    },
    "knee_conditions": {
        "name": "Knee Conditions",
        "description": "Patellofemoral syndrome, meniscus tears, arthritis",
        "common_for": ["army", "marines"],
        "service_eras": ["all"],
        "risk_factors": ["infantry", "parachute", "running", "ruck marches"],
        "secondary_to": ["back_conditions"],
        "avg_rating": "10-30%",
    },
    "sleep_apnea": {
        "name": "Sleep Apnea",
        "description": "Obstructive sleep apnea, often secondary to PTSD or weight gain",
        "common_for": ["army", "marines", "navy", "air_force"],
        "service_eras": ["all"],
        "risk_factors": ["ptsd", "weight gain", "neck injury"],
        "secondary_to": ["ptsd"],
        "avg_rating": "50%",
    },
    "migraines": {
        "name": "Migraines / Headaches",
        "description": "Chronic headaches, often secondary to TBI or PTSD",
        "common_for": ["army", "marines", "navy", "air_force"],
        "service_eras": ["oef_oif", "gulf"],
        "risk_factors": ["tbi", "blast exposure", "ptsd"],
        "secondary_to": ["ptsd", "tbi"],
        "avg_rating": "10-50%",
    },
    "tbi": {
        "name": "Traumatic Brain Injury (TBI)",
        "description": "Brain injury from blast exposure, accidents, or combat",
        "common_for": ["army", "marines"],
        "service_eras": ["oef_oif", "gulf"],
        "risk_factors": ["blast exposure", "vehicle accidents", "combat"],
        "secondary_to": [],
        "avg_rating": "10-100%",
    },
    "gerd": {
        "name": "GERD / Acid Reflux",
        "description": "Gastroesophageal reflux disease, common secondary condition",
        "common_for": ["army", "marines", "navy", "air_force"],
        "service_eras": ["all"],
        "risk_factors": ["stress", "medication use", "ptsd"],
        "secondary_to": ["ptsd"],
        "avg_rating": "10-30%",
    },
    "radiculopathy": {
        "name": "Radiculopathy (Nerve Pain)",
        "description": "Nerve pain radiating from spine to extremities",
        "common_for": ["army", "marines", "navy", "air_force"],
        "service_eras": ["all"],
        "risk_factors": ["back injury", "neck injury"],
        "secondary_to": ["back_conditions"],
        "avg_rating": "10-40%",
    },
    "erectile_dysfunction": {
        "name": "Erectile Dysfunction",
        "description": "Sexual dysfunction, often secondary to PTSD or medication",
        "common_for": ["army", "marines", "navy", "air_force"],
        "service_eras": ["all"],
        "risk_factors": ["ptsd", "medication", "diabetes"],
        "secondary_to": ["ptsd", "diabetes"],
        "avg_rating": "SMC-K",
    },
}

SERVICE_ERA_LABELS = {
    "vietnam": "Vietnam Era (1964-1975)",
    "gulf": "Gulf War Era (1990-2001)",
    "oef_oif": "OEF/OIF/OND (2001-Present)",
    "peacetime": "Peacetime Service",
}


@login_required
def condition_discovery(request):
    """
    Condition discovery tool - help veterans identify potentially claimable conditions.
    """
    context = {
        "service_eras": SERVICE_ERA_LABELS,
        "branches": [
            ("army", "Army"),
            ("marines", "Marines"),
            ("navy", "Navy"),
            ("air_force", "Air Force"),
            ("coast_guard", "Coast Guard"),
        ],
        "risk_factors": [
            ("combat", "Combat/Direct Fire"),
            ("blast_exposure", "Blast Exposure/IEDs"),
            ("artillery", "Artillery/Heavy Weapons"),
            ("aviation", "Aviation/Flight Line"),
            ("infantry", "Infantry/Ground Forces"),
            ("vehicle_crew", "Vehicle Crew/Driver"),
            ("parachute", "Airborne/Parachute"),
            ("mst", "Military Sexual Trauma"),
            ("deployment", "Multiple Deployments"),
            ("tbi", "Head Injury/Concussion"),
        ],
    }

    if request.method == "POST":
        branch = request.POST.get("branch", "")
        service_era = request.POST.get("service_era", "")
        selected_factors = request.POST.getlist("risk_factors")
        existing_conditions = request.POST.get("existing_conditions", "").lower()

        # Find matching conditions
        matched_conditions = []
        secondary_conditions = []

        for key, condition in CONDITION_DATABASE.items():
            score = 0
            reasons = []

            # Check branch match
            if branch in condition["common_for"]:
                score += 2
                reasons.append(f"Common in {branch.replace('_', ' ').title()}")

            # Check service era
            if (
                "all" in condition["service_eras"]
                or service_era in condition["service_eras"]
            ):
                score += 2
                reasons.append(
                    f"Associated with {SERVICE_ERA_LABELS.get(service_era, service_era)}"
                )

            # Check risk factors (normalize underscores to spaces for comparison)
            for factor in selected_factors:
                factor_normalized = factor.replace("_", " ").lower()
                if any(
                    factor_normalized in rf.lower() or rf.lower() in factor_normalized
                    for rf in condition["risk_factors"]
                ):
                    score += 3
                    reasons.append(f"Related to {factor.replace('_', ' ')}")

            if score >= 4:
                matched_conditions.append(
                    {
                        "key": key,
                        "condition": condition,
                        "score": score,
                        "reasons": reasons,
                    }
                )

            # Check for secondary conditions
            if condition["secondary_to"]:
                for primary in condition["secondary_to"]:
                    if primary in existing_conditions or any(
                        mc["key"] == primary for mc in matched_conditions
                    ):
                        secondary_conditions.append(
                            {
                                "key": key,
                                "condition": condition,
                                "secondary_to": CONDITION_DATABASE.get(primary, {}).get(
                                    "name", primary
                                ),
                            }
                        )

        # Sort by score
        matched_conditions.sort(key=lambda x: x["score"], reverse=True)

        context["results"] = True
        context["matched_conditions"] = matched_conditions[:8]
        context["secondary_conditions"] = secondary_conditions[:5]
        context["selected_branch"] = branch
        context["selected_era"] = service_era
        context["selected_factors"] = selected_factors

    return render(request, "agents/condition_discovery.html", context)


# =============================================================================
# STREAMING ASSISTANT (docs/ux/assistant-interactions.md)
# =============================================================================

import json  # noqa: E402
import time  # noqa: E402

from django.conf import settings  # noqa: E402
from django.core.cache import cache  # noqa: E402
from django.http import HttpResponse, StreamingHttpResponse  # noqa: E402

from . import assistant_copy as copy  # noqa: E402
from .ai_gateway import GatewayStreamError, get_gateway  # noqa: E402
from .models import AssistantThread, AssistantTurn  # noqa: E402

# Server-side stop: the /stop endpoint sets this cache flag; the running stream
# checks it each delta and closes the Anthropic stream (stops token spend). The
# key is the *user turn id*, so ownership is verified via the DB row before the
# flag is ever set. In prod the shared Redis cache carries this across worker
# processes; dev's threaded runserver shares LocMemCache within one process.
_STOP_KEY = "assistant_stop:{turn_id}"
_STOP_TTL_SECONDS = 300  # a stream can't outlive this; avoids leaking stale flags


def _stop_key(turn_id: int) -> str:
    return _STOP_KEY.format(turn_id=turn_id)


def _sse(event: str, data: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _demo_deltas(text: str):
    """Stream a canned response word-by-word (local play, no API key/tokens)."""
    for token in text.split(" "):
        yield token + " "
        time.sleep(0.02)


def _has_live_key() -> bool:
    key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    return bool(key) and key != "your-anthropic-api-key-here"


@login_required
def assistant(request):
    """Render the streaming assistant page.

    Renders the veteran's persisted thread so the conversation survives reload;
    the first-run empty state shows only when the thread has zero turns
    (docs/ux/assistant-interactions.md §1). The transcript is PHI — it is fetched
    scoped to ``request.user`` and never logged.
    """
    thread = (
        AssistantThread.objects.filter(user=request.user)
        .order_by("-created_at")
        .first()
    )
    turns = list(thread.turns.all()) if thread else []
    return render(
        request,
        "agents/assistant.html",
        {
            "empty": copy.EMPTY,
            "status": copy.STATUS,
            "errors": copy.ERRORS,
            "disclaimer": copy.DISCLAIMER,
            "turns": turns,
        },
    )


@login_required
@require_POST
def assistant_stream(request):
    """SSE endpoint that streams one assistant turn.

    Emits: ``open`` (with ``turn_id``) → ``delta``* → ``done``/``stopped`` (or
    ``error`` with a public_code). The user prompt is persisted immediately; the
    assistant answer is persisted on ``done`` (full) or ``stopped`` (partial kept),
    so the thread survives reload. PHI: neither the prompt nor the deltas are ever
    logged — only turn metadata. See docs/ux/assistant-interactions.md §3, §5.
    """
    prompt = (request.POST.get("prompt") or "").strip()
    if not prompt:
        # Should be prevented client-side (Send disabled until non-empty), but
        # never trust the client. No content is logged.
        return StreamingHttpResponse(
            iter([_sse("error", {"code": "generic"})]),
            content_type="text/event-stream",
        )

    # ADR-002 dual-check, Layer 1: consent must be present before we open a stream.
    # Reuses the app's canonical consent helper (checks profile.ai_processing_consent).
    consented = check_ai_consent(request.user)
    user = request.user

    def event_stream():
        # Structured, PHI-free log — turn metadata only (no prompt text).
        logger.info(
            "assistant_stream start user=%s len=%s demo=%s",
            user.id,
            len(prompt),
            not _has_live_key(),
        )
        if not consented:
            # No consent → no external call and nothing persisted (the prompt is
            # PHI we have no reason to store on a rejected turn).
            yield _sse("error", {"code": "consent_required"})
            return

        # Persist the user turn up front so it survives reload even if the answer
        # fails. get_or_create keeps one rolling thread per user for now.
        thread, _ = AssistantThread.objects.get_or_create(user=user)
        user_turn = AssistantTurn.objects.create(
            thread=thread, user=user, role="user", content=prompt
        )
        stop_key = _stop_key(user_turn.pk)

        buf = []
        stopped = False
        deltas = None
        try:
            yield _sse("open", {"turn_id": user_turn.pk})
            if _has_live_key():
                deltas = get_gateway().stream(copy.SYSTEM_PROMPT, prompt)
            else:
                deltas = _demo_deltas(copy.DEMO_RESPONSE)
            for delta in deltas:
                if cache.get(stop_key):
                    stopped = True
                    break
                buf.append(delta)
                yield _sse("delta", {"t": delta})

            if stopped:
                # Promptly close the provider stream so we stop spending tokens.
                deltas.close()
                AssistantTurn.objects.create(
                    thread=thread,
                    user=user,
                    role="assistant",
                    content="".join(buf),
                    stopped=True,
                )
                yield _sse("stopped", {})
                return

            AssistantTurn.objects.create(
                thread=thread,
                user=user,
                role="assistant",
                content="".join(buf),
            )
            yield _sse("done", {})
        except GatewayStreamError as e:
            # Only the mapped public_code crosses the wire — never the raw cause.
            # No assistant turn is persisted on failure; the user turn (prompt)
            # remains so the veteran never retypes.
            logger.warning(
                "assistant_stream error user=%s code=%s", user.id, e.public_code
            )
            yield _sse("error", {"code": e.public_code})
        except Exception:  # noqa: BLE001
            logger.exception("assistant_stream unexpected user=%s", user.id)
            yield _sse("error", {"code": "generic"})
        finally:
            if deltas is not None:
                deltas.close()  # idempotent; ensures the provider stream is closed
            cache.delete(stop_key)

    resp = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"  # disable proxy buffering so tokens flush live
    return resp


@login_required
@require_POST
def assistant_stop(request):
    """Signal a running stream to stop (server-side abort, stops token spend).

    The client posts the ``turn_id`` from the ``open`` event. We verify the turn
    belongs to the requesting user (a user can never stop another user's stream),
    then set a short-lived cache flag the streaming generator polls. The generator
    closes the Anthropic stream and persists the partial answer as ``stopped``.
    """
    turn_id = request.POST.get("turn_id")
    if not turn_id:
        return HttpResponse(status=400)
    turn = get_object_or_404(AssistantTurn, pk=turn_id, user=request.user, role="user")
    cache.set(_stop_key(turn.pk), True, timeout=_STOP_TTL_SECONDS)
    return HttpResponse(status=204)
