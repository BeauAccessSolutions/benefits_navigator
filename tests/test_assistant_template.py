"""Render-time guards for the assistant page.

The assistant's JS lives in static/js/assistant.js (unit-tested under tests/js/).
Extracting it introduced a class of failure the JS tests cannot see: the page
must still *render*. `{% static %}` needs `{% load static %}` in this template —
tag libraries are NOT inherited from base.html — and getting that wrong is a
TemplateSyntaxError on a page whose JS suite is entirely green.

These assert the contract between the template and the script: the script is
referenced, and the endpoints it reads from data-* are actually emitted.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

pytestmark = pytest.mark.django_db


@pytest.fixture
def veteran(client):
    user = get_user_model().objects.create_user(
        username="render_probe",
        email="render_probe@example.com",
        password="RenderProbe123!",
    )
    client.force_login(user)
    return user


def test_assistant_page_renders(client, veteran):
    """The page must render — a missing {% load static %} 500s here."""
    response = client.get(reverse("agents:assistant"))
    assert response.status_code == 200


def test_assistant_page_loads_the_external_script_and_no_inline_one(client, veteran):
    html = client.get(reverse("agents:assistant")).content.decode()

    assert (
        "js/assistant.js" in html
    ), "the extracted assistant script must be referenced"
    assert "defer" in html, "the script must be deferred so the DOM exists at boot"

    # The assistant's own logic must no longer be inline — that is the piece
    # this page contributes to the CSP's need for 'unsafe-inline'. (base.html
    # still has inline scripts of its own; those are a separate cleanup, so
    # this asserts about the assistant's code specifically rather than the
    # whole document.)
    # JS-only identifiers: the .assistant-caret CSS class legitimately remains
    # in the inline <style> block, so it is not a usable marker here.
    for marker in ("addAssistantContainer", "finishStreaming", "setComposerBusy"):
        assert marker not in html, (
            f"{marker!r} is still inline in the rendered page — the assistant "
            "logic belongs in static/js/assistant.js"
        )


def test_assistant_page_emits_the_endpoints_the_script_reads(client, veteran):
    """static/js/assistant.js reads these from root.dataset — if the template
    stops emitting them, the script silently POSTs to `undefined`."""
    html = client.get(reverse("agents:assistant")).content.decode()

    assert 'id="assistant-app"' in html
    assert f'data-stream-url="{reverse("agents:assistant_stream")}"' in html
    assert f'data-stop-url="{reverse("agents:assistant_stop")}"' in html


def test_assistant_page_keeps_both_live_regions(client, veteran):
    """The §6.1 spine: one polite region for status, one assertive for errors."""
    html = client.get(reverse("agents:assistant")).content.decode()

    assert 'id="assistant-status"' in html and 'aria-live="polite"' in html
    assert 'id="assistant-error-live"' in html and 'aria-live="assertive"' in html
