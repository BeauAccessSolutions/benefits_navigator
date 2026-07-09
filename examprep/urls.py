"""
URL configuration for examprep app
"""

from django.urls import path
from . import views

app_name = "examprep"

urlpatterns = [
    # Guide list and detail pages
    path("", views.guide_list, name="guide_list"),
    path("guide/<slug:slug>/", views.guide_detail, name="guide_detail"),
    # Glossary
    path("glossary/", views.glossary_list, name="glossary_list"),
    path("glossary/<int:pk>/", views.glossary_detail, name="glossary_detail"),
    # User's personal exam checklists
    path("my-checklists/", views.checklist_list, name="checklist_list"),
    path("my-checklists/create/", views.checklist_create, name="checklist_create"),
    path("my-checklists/<int:pk>/", views.checklist_detail, name="checklist_detail"),
    path(
        "my-checklists/<int:pk>/update/",
        views.checklist_update,
        name="checklist_update",
    ),
    path(
        "my-checklists/<int:pk>/delete/",
        views.checklist_delete,
        name="checklist_delete",
    ),
    # HTMX endpoints for interactive features
    path(
        "my-checklists/<int:pk>/toggle-task/",
        views.checklist_toggle_task,
        name="checklist_toggle_task",
    ),
    # Rating Calculator
    path("rating-calculator/", views.rating_calculator, name="rating_calculator"),
    path(
        "rating-calculator/calculate/",
        views.calculate_rating_htmx,
        name="calculate_rating",
    ),
    path(
        "rating-calculator/calculate-json/",
        views.calculate_rating_json,
        name="calculate_rating_json",
    ),
    path("rating-calculator/save/", views.save_calculation, name="save_calculation"),
    path(
        "rating-calculator/saved/", views.saved_calculations, name="saved_calculations"
    ),
    path(
        "rating-calculator/saved/<int:pk>/delete/",
        views.delete_calculation,
        name="delete_calculation",
    ),
    path(
        "rating-calculator/saved/<int:pk>/load/",
        views.load_calculation,
        name="load_calculation",
    ),
    path(
        "rating-calculator/export-pdf/",
        views.export_rating_pdf,
        name="export_rating_pdf",
    ),
    path(
        "rating-calculator/saved/<int:pk>/export-pdf/",
        views.export_saved_rating_pdf,
        name="export_saved_rating_pdf",
    ),
    # Evidence Checklists
    path(
        "evidence-checklist/",
        views.evidence_checklist_list,
        name="evidence_checklist_list",
    ),
    path(
        "evidence-checklist/new/",
        views.evidence_checklist_create,
        name="evidence_checklist_create",
    ),
    path(
        "evidence-checklist/<int:pk>/",
        views.evidence_checklist_detail,
        name="evidence_checklist_detail",
    ),
    path(
        "evidence-checklist/<int:pk>/toggle/",
        views.evidence_checklist_toggle,
        name="evidence_checklist_toggle",
    ),
    path(
        "evidence-checklist/<int:pk>/delete/",
        views.evidence_checklist_delete,
        name="evidence_checklist_delete",
    ),
    path(
        "evidence-checklist/from-denial/<int:analysis_id>/",
        views.evidence_checklist_from_denial,
        name="evidence_checklist_from_denial",
    ),
    # SMC Calculator
    path("smc-calculator/", views.smc_calculator, name="smc_calculator"),
    path("smc-calculator/calculate/", views.calculate_smc_htmx, name="calculate_smc"),
    # TDIU Calculator
    path("tdiu-calculator/", views.tdiu_calculator, name="tdiu_calculator"),
    path(
        "tdiu-calculator/calculate/", views.calculate_tdiu_htmx, name="calculate_tdiu"
    ),
    # Secondary Conditions Hub
    path(
        "secondary-conditions/",
        views.secondary_conditions_hub,
        name="secondary_conditions_hub",
    ),
    path(
        "secondary-conditions/search/",
        views.secondary_conditions_search,
        name="secondary_conditions_search",
    ),
    path(
        "secondary-conditions/<slug:condition_slug>/",
        views.secondary_condition_detail,
        name="secondary_condition_detail",
    ),
    # Share Calculation
    path("rating-calculator/share/", views.share_calculation, name="share_calculation"),
    path(
        "rating-calculator/saved/<int:pk>/share/",
        views.share_saved_calculation,
        name="share_saved_calculation",
    ),
    path(
        "shared/<str:token>/", views.view_shared_calculation, name="shared_calculation"
    ),
    # Import ratings from analysis
    path(
        "rating-calculator/import/<int:analysis_id>/",
        views.import_ratings_from_analysis,
        name="import_ratings",
    ),
]
