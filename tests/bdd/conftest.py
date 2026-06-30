"""
BDD Test Configuration

Provides step definitions and fixtures for pytest-bdd tests.
"""

import os
import pytest
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "benefits_navigator.settings")
django.setup()

from django.test import Client
from django.contrib.auth import get_user_model
from pytest_bdd import given, when, then, parsers

User = get_user_model()


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def user_data():
    """Default user data for tests."""
    return {
        "email": "bdd_test@example.com",
        "password": "BDDTestPassword123!",
        "first_name": "BDD",
        "last_name": "Tester",
    }


@pytest.fixture
def context():
    """Shared context for BDD steps."""
    return {}


# =============================================================================
# GIVEN STEPS - Setup
# =============================================================================


@given("I am an anonymous user")
def anonymous_user(client, db, context):
    """Ensure the user is not logged in. Requires db for views that query database."""
    client.logout()
    context["client"] = client
    context["authenticated"] = False


@given("I am a registered user")
def registered_user(db, user_data, context):
    """Create a registered user."""
    user, created = User.objects.get_or_create(
        email=user_data["email"],
        defaults={
            "first_name": user_data["first_name"],
            "last_name": user_data["last_name"],
        },
    )
    if created:
        user.set_password(user_data["password"])
        user.save()
    context["user"] = user
    context["password"] = user_data["password"]


@given("I am logged in")
def logged_in_user(client, db, user_data, context):
    """Create and log in a user."""
    user, created = User.objects.get_or_create(
        email=user_data["email"],
        defaults={
            "first_name": user_data["first_name"],
            "last_name": user_data["last_name"],
        },
    )
    if created:
        user.set_password(user_data["password"])
        user.save()

    client.login(email=user_data["email"], password=user_data["password"])
    context["client"] = client
    context["user"] = user
    context["authenticated"] = True


@given("I have granted AI consent")
def grant_ai_consent(context):
    """Grant AI processing consent for the logged-in user."""
    user = context.get("user")
    if user and hasattr(user, "profile"):
        user.profile.ai_processing_consent = True
        user.profile.save()


@given("I am a premium user")
def premium_user(client, db, context):
    """Create and log in a premium user."""
    from accounts.models import Subscription
    from datetime import datetime, timedelta

    user, created = User.objects.get_or_create(
        email="bdd_premium@example.com",
        defaults={
            "first_name": "Premium",
            "last_name": "User",
        },
    )
    if created:
        user.set_password("PremiumPassword123!")
        user.save()

    Subscription.objects.get_or_create(
        user=user,
        defaults={
            "plan_type": "premium",
            "status": "active",
            "current_period_end": datetime.now() + timedelta(days=365),
        },
    )

    client.login(email="bdd_premium@example.com", password="PremiumPassword123!")
    context["client"] = client
    context["user"] = user
    context["is_premium"] = True


@given(parsers.parse('a glossary term "{term}" exists'))
def glossary_term_exists(db, context, term):
    """Create a glossary term."""
    from examprep.models import GlossaryTerm

    glossary, created = GlossaryTerm.objects.get_or_create(
        term=term,
        defaults={
            "plain_language": f"Definition of {term}",
            "context": "Test context",
        },
    )
    context["glossary_term"] = glossary


@given(parsers.parse('an exam guide "{title}" exists'))
def exam_guide_exists(db, context, title):
    """Create an exam guide."""
    from examprep.models import ExamGuidance
    from django.utils.text import slugify

    guide, created = ExamGuidance.objects.get_or_create(
        slug=slugify(title),
        defaults={
            "title": title,
            "category": "general",
            "introduction": "Test guide introduction",
            "is_published": True,
        },
    )
    context["exam_guide"] = guide


@given(parsers.parse('an appeal guidance for "{appeal_type}" exists'))
def appeal_guidance_exists(db, context, appeal_type):
    """Create appeal guidance."""
    from appeals.models import AppealGuidance
    from django.utils.text import slugify

    guidance, created = AppealGuidance.objects.get_or_create(
        slug=slugify(appeal_type),
        defaults={
            "title": appeal_type,
            "appeal_type": "hlr",
            "overview": "Test overview",
            "is_published": True,
        },
    )
    context["appeal_guidance"] = guidance


# =============================================================================
# WHEN STEPS - Actions
# =============================================================================


@when(parsers.parse('I visit "{url}"'))
def visit_url(client, context, url):
    """Visit a URL."""
    response = client.get(url)
    context["response"] = response


@when(
    parsers.parse(
        'I submit the login form with email "{email}" and password "{password}"'
    )
)
def submit_login(client, context, email, password):
    """Submit the login form."""
    response = client.post(
        "/accounts/login/",
        {
            "login": email,
            "password": password,
        },
    )
    context["response"] = response


@when("I submit an empty form")
def submit_empty_form(client, context):
    """Submit an empty form."""
    url = context.get("current_url", "/accounts/login/")
    response = client.post(url, {})
    context["response"] = response


@when(parsers.parse('I search for "{query}"'))
def search_for(client, context, query):
    """Perform a search."""
    response = client.get("/exam-prep/glossary/", {"q": query})
    context["response"] = response


@when(parsers.parse('I add a disability rating of {percentage:d}% for "{condition}"'))
def add_disability_rating(client, context, percentage, condition):
    """Add a disability rating."""
    response = client.post(
        "/exam-prep/rating-calculator/calculate/",
        {
            "percentage": percentage,
            "description": condition,
        },
    )
    context["response"] = response


@when("I click the logout button")
def click_logout(client, context):
    """Log out the user."""
    response = client.post("/accounts/logout/")
    context["response"] = response
    context["authenticated"] = False


# =============================================================================
# THEN STEPS - Assertions
# =============================================================================


@then(parsers.parse("I should see a {status_code:d} status"))
def check_status_code(context, status_code):
    """Check response status code."""
    assert context["response"].status_code == status_code


@then("I should be redirected to the login page")
def redirected_to_login(context):
    """Check redirection to login."""
    response = context["response"]
    assert response.status_code in [301, 302]
    assert "/accounts/login/" in response.url


@then("I should be redirected to the dashboard")
def redirected_to_dashboard(context):
    """Check redirection to dashboard."""
    response = context["response"]
    assert response.status_code in [301, 302]
    assert "/dashboard/" in response.url


@then(parsers.parse('I should see "{text}" on the page'))
def see_text_on_page(context, text):
    """Check for text in response."""
    content = context["response"].content.decode("utf-8")
    assert text in content


@then(parsers.parse('I should not see "{text}" on the page'))
def not_see_text_on_page(context, text):
    """Check text is not in response."""
    content = context["response"].content.decode("utf-8")
    assert text not in content


@then("I should see form errors")
def see_form_errors(context):
    """Check for form errors."""
    content = context["response"].content.decode("utf-8")
    assert any(
        x in content
        for x in ["error", "Error", "invalid", "Invalid", "required", "Required"]
    )


@then("I should be logged in")
def should_be_logged_in(context):
    """Check user is logged in."""
    assert (
        context.get("authenticated")
        or context["response"].wsgi_request.user.is_authenticated
    )


@then("I should be logged out")
def should_be_logged_out(context):
    """Check user is logged out."""
    assert not context.get("authenticated")


@then(parsers.parse('the page title should contain "{text}"'))
def page_title_contains(context, text):
    """Check page title."""
    content = context["response"].content.decode("utf-8")
    assert "<title>" in content.lower()
    # Extract title and check
    import re

    title_match = re.search(r"<title>(.*?)</title>", content, re.IGNORECASE)
    if title_match:
        assert text.lower() in title_match.group(1).lower()


@then("the response should be valid HTML")
def valid_html_response(context):
    """Check response is valid HTML."""
    content = context["response"].content.decode("utf-8")
    assert "<html" in content.lower()
    assert "</html>" in content.lower()


@then("the page should have a main content area")
def has_main_content(context):
    """Check for main content area."""
    content = context["response"].content.decode("utf-8")
    assert "<main" in content.lower() or 'role="main"' in content.lower()


@then("the page should have navigation")
def has_navigation(context):
    """Check for navigation."""
    content = context["response"].content.decode("utf-8")
    assert "<nav" in content.lower() or 'role="navigation"' in content.lower()
