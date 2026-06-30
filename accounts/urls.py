"""
URL configuration for accounts app.
"""

from django.urls import path
from . import views

app_name = "accounts"

urlpatterns = [
    # Privacy & Data Management
    path("privacy/", views.privacy_settings, name="privacy_settings"),
    path("privacy/ai-consent/", views.toggle_ai_consent, name="toggle_ai_consent"),
    path("export/", views.data_export, name="data_export"),
    path("delete/", views.account_deletion, name="account_deletion"),
    # Subscription & Upgrade
    path("upgrade/", views.upgrade, name="upgrade"),
    path("checkout/", views.create_checkout_session, name="checkout"),
    path(
        "subscription/success/", views.subscription_success, name="subscription_success"
    ),
    path("subscription/portal/", views.customer_portal, name="customer_portal"),
    # Stripe Webhook (no CSRF, signature verified)
    path("webhook/stripe/", views.stripe_webhook, name="stripe_webhook"),
    # Organization Management (Path B - VSO Platform)
    path("organizations/", views.org_list, name="org_list"),
    path("organizations/create/", views.org_create, name="org_create"),
    path("organizations/<slug:slug>/", views.org_dashboard, name="org_dashboard"),
    # Organization Invitations
    path("organizations/<slug:slug>/invite/", views.org_invite, name="org_invite"),
    path(
        "organizations/<slug:slug>/invitations/",
        views.org_invitations,
        name="org_invitations",
    ),
    path(
        "organizations/<slug:slug>/invitations/<str:token>/resend/",
        views.org_invite_resend,
        name="org_invite_resend",
    ),
    path(
        "organizations/<slug:slug>/invitations/<str:token>/cancel/",
        views.org_invite_cancel,
        name="org_invite_cancel",
    ),
    path("invitation/<str:token>/", views.org_invite_accept, name="org_invite_accept"),
]
