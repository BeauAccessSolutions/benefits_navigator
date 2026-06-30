"""
URL configuration for agents app
"""

from django.urls import path
from . import views

app_name = "agents"

urlpatterns = [
    # Home
    path("", views.agents_home, name="home"),
    path("history/", views.agent_history, name="history"),
    # Decision Letter Analyzer
    path("decision-analyzer/", views.decision_analyzer, name="decision_analyzer"),
    path(
        "decision-analyzer/analyze/",
        views.decision_analyzer_submit,
        name="decision_analyzer_submit",
    ),
    path(
        "decision-analyzer/result/<int:pk>/",
        views.decision_analyzer_result,
        name="decision_analyzer_result",
    ),
    # Evidence Gap Analyzer
    path("evidence-gap/", views.evidence_gap_analyzer, name="evidence_gap"),
    path(
        "evidence-gap/analyze/", views.evidence_gap_submit, name="evidence_gap_submit"
    ),
    path(
        "evidence-gap/result/<int:pk>/",
        views.evidence_gap_result,
        name="evidence_gap_result",
    ),
    # Personal Statement Generator
    path("statement-generator/", views.statement_generator, name="statement_generator"),
    path(
        "statement-generator/generate/",
        views.statement_generator_submit,
        name="statement_generator_submit",
    ),
    path(
        "statement-generator/result/<int:pk>/",
        views.statement_result,
        name="statement_result",
    ),
    path(
        "statement-generator/result/<int:pk>/save/",
        views.statement_save_final,
        name="statement_save_final",
    ),
    # Condition Discovery Tool
    path("condition-discovery/", views.condition_discovery, name="condition_discovery"),
]
