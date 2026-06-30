"""
URL configuration for core app
"""

from django.urls import path
from . import views

app_name = "core"

urlpatterns = [
    # Claim Progress Dashboard
    path("progress/", views.claim_progress, name="claim_progress"),
    # Journey Dashboard
    path("journey/", views.journey_dashboard, name="journey_dashboard"),
    path("journey/timeline/", views.journey_timeline_partial, name="journey_timeline"),
    # Milestones
    path("journey/milestone/add/", views.add_milestone, name="add_milestone"),
    path(
        "journey/milestone/<int:pk>/delete/",
        views.delete_milestone,
        name="delete_milestone",
    ),
    # Deadlines
    path("journey/deadline/add/", views.add_deadline, name="add_deadline"),
    path(
        "journey/deadline/<int:pk>/toggle/",
        views.toggle_deadline,
        name="toggle_deadline",
    ),
    path(
        "journey/deadline/<int:pk>/delete/",
        views.delete_deadline,
        name="delete_deadline",
    ),
    # Feedback
    path("feedback/submit/", views.submit_feedback, name="submit_feedback"),
    path("feedback/form/", views.feedback_form, name="feedback_form"),
    # Support/Contact
    path("contact/", views.contact, name="contact"),
    path("contact/success/", views.contact_success, name="contact_success"),
    # Admin Stats Dashboard (staff only)
    path("admin/stats/", views.admin_stats_dashboard, name="admin_stats"),
]
