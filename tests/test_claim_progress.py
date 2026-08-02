"""
Render tests for the claim progress dashboard (/progress/).

Regression (2026-08-02 experience audit, P0-5): the view emitted next-step
entries with URL names that don't exist — "claims:upload" (real name:
"claims:document_upload") and "agents:rating_analyzer" (real name:
"claims:rating_analyzer"). templates/core/claim_progress.html reverses each
step with {% url step.url_name %}, so /progress/ 500'd with NoReverseMatch
for every user with zero documents. No test rendered this template before.
"""

import pytest
from django.urls import reverse


@pytest.mark.django_db
class TestClaimProgressRendering:
    def test_renders_for_fresh_user(self, authenticated_client):
        """A user with no documents gets the 'upload documents' next step —
        the exact state that crashed with NoReverseMatch on claims:upload."""
        response = authenticated_client.get(reverse("core:claim_progress"))
        assert response.status_code == 200
        assert reverse("claims:document_upload").encode() in response.content

    def test_renders_with_decision_analysis(self, authenticated_client, user):
        """A decision analysis without a rating analysis surfaces the rating
        next step, which crashed on the nonexistent agents:rating_analyzer."""
        from agents.models import AgentInteraction, DecisionLetterAnalysis

        interaction = AgentInteraction.objects.create(
            user=user, agent_type="decision_analyzer", status="completed"
        )
        DecisionLetterAnalysis.objects.create(interaction=interaction, user=user)

        response = authenticated_client.get(reverse("core:claim_progress"))
        assert response.status_code == 200
        assert reverse("claims:rating_analyzer").encode() in response.content

    def test_every_next_step_url_name_reverses(self, authenticated_client, user):
        """Belt-and-braces: every url_name the view can emit must reverse,
        whatever combination of steps the user's state produces."""
        from agents.models import AgentInteraction, DecisionLetterAnalysis

        interaction = AgentInteraction.objects.create(
            user=user, agent_type="decision_analyzer", status="completed"
        )
        DecisionLetterAnalysis.objects.create(interaction=interaction, user=user)

        response = authenticated_client.get(reverse("core:claim_progress"))
        assert response.status_code == 200
        for step in response.context["next_steps"]:
            reverse(step["url_name"])  # raises NoReverseMatch on regression
