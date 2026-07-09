"""
URL configuration for the documentation app.
"""

from django.urls import path
from django.views.generic import TemplateView

from . import views

app_name = "documentation"

urlpatterns = [
    # About / One-Pager
    path(
        "about/",
        TemplateView.as_view(template_name="documentation/partials/one-pager.html"),
        name="about",
    ),
    # Main search
    path("", views.search_view, name="search"),
    # VA Forms
    path("forms/", views.form_list, name="form_list"),
    path("forms/<str:form_number>/", views.form_detail, name="form_detail"),
    # C&P Exam Guides
    path("exam-guides/", views.exam_guide_list, name="exam_guide_list"),
    path("exam-guides/<slug:slug>/", views.exam_guide_detail, name="exam_guide_detail"),
    # Legal References
    path("legal/", views.legal_reference_list, name="legal_reference_list"),
    path(
        "legal/<int:pk>/", views.legal_reference_detail, name="legal_reference_detail"
    ),
    # HTMX search endpoint
    path("search/results/", views.search_results_htmx, name="search_results_htmx"),
]
