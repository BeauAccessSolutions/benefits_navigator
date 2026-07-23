"""Render-level guard: {% static %} must resolve without a collectstatic manifest.

Whitenoise's CompressedManifestStaticFilesStorage resolves {% static %} through
a manifest that `collectstatic` writes. Configuring it unconditionally broke
every test that renders a page — not just static-file tests — with:

    ValueError: Missing staticfiles manifest entry for 'css/tailwind.min.css'

because neither pytest nor runserver produces a manifest. The suite went red at
the first template render (core.tests.TestHomeView.test_home_page_loads), which
made a settings problem look like a broken home page.

core.tests.TestStorageConfiguration asserts the backend *selection*; these
assert the behaviour that selection exists to protect, so the failure is caught
as "pages do not render" rather than only as "a setting changed".
"""

import pytest
from django.template import Context, Template


def test_static_tag_renders_without_a_collectstatic_manifest():
    """The exact regression: this raised ValueError for every page render."""
    rendered = Template("{% load static %}{% static 'css/tailwind.min.css' %}").render(
        Context({})
    )

    assert "css/tailwind.min.css" in rendered


@pytest.mark.django_db
def test_a_real_page_renders(client):
    """End to end over the render path that took the whole suite down."""
    assert client.get("/").status_code == 200
