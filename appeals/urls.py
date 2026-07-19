"""
Appeals app URL configuration.
"""

from django.urls import path
from . import views

app_name = "appeals"

urlpatterns = [
    # Public guidance pages
    path("", views.appeals_home, name="home"),
    path("guide/<slug:slug>/", views.guidance_detail, name="guidance_detail"),
    path("find-your-path/", views.decision_tree, name="decision_tree"),
    # User appeal management (login required)
    path("my-appeals/", views.appeal_list, name="appeal_list"),
    path("start/", views.appeal_start, name="appeal_start"),
    path("<int:pk>/", views.appeal_detail, name="appeal_detail"),
    path("<int:pk>/decide/", views.appeal_decide, name="appeal_decide"),
    path("<int:pk>/set-type/", views.appeal_set_type, name="appeal_set_type"),
    path("<int:pk>/update/", views.appeal_update, name="appeal_update"),
    path(
        "<int:pk>/decision/",
        views.appeal_record_decision,
        name="appeal_record_decision",
    ),
    path("<int:pk>/toggle-step/", views.appeal_toggle_step, name="appeal_toggle_step"),
    # Documents
    path(
        "<int:pk>/documents/add/", views.appeal_add_document, name="appeal_add_document"
    ),
    path(
        "<int:pk>/documents/<int:doc_pk>/delete/",
        views.appeal_delete_document,
        name="appeal_delete_document",
    ),
    # Protected media access (authentication + ownership required)
    path(
        "<int:pk>/documents/<int:doc_pk>/view/",
        views.appeal_document_view,
        name="appeal_document_view",
    ),
    path(
        "<int:pk>/documents/<int:doc_pk>/download/",
        views.appeal_document_download,
        name="appeal_document_download",
    ),
    # Notes
    path("<int:pk>/notes/add/", views.appeal_add_note, name="appeal_add_note"),
]
