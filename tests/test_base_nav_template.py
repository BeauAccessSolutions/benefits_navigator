"""Render-time guards for the responsive header nav in templates/base.html.

The nav collapses behind a hamburger below the xl breakpoint. Its toggle logic
lives in static/js/nav.js (unit-tested under tests/js/), but the JS suite cannot
see two failure modes that only exist at render time:

  1. The script must actually be referenced, with defer, or the button is inert.
  2. The link list is rendered twice — the desktop bar and the mobile panel —
     from core/partials/nav_links.html. The whole point of the shared partial is
     that a new nav item cannot appear in one and not the other, so these assert
     both copies stay in step. Hand-duplicating the list is exactly the drift
     this guards against.
"""

import re

import pytest

pytestmark = pytest.mark.django_db


def _nav_sections(html):
    """Return (desktop_bar_html, mobile_panel_html) from a rendered page."""
    panel = re.search(r"<nav[^>]*data-nav-panel[^>]*>(.*?)</nav>", html, re.S)
    bar = re.search(
        r'<nav[^>]*aria-label="Main navigation"(?![^>]*data-nav-panel)[^>]*>(.*?)</nav>',
        html,
        re.S,
    )
    assert bar, "the desktop nav bar must render"
    assert panel, "the mobile nav panel must render"
    return bar.group(1), panel.group(1)


def _hrefs(section_html):
    return re.findall(r'href="([^"]+)"', section_html)


def test_home_page_renders(client):
    """A malformed {% include %} in the header 500s every page on the site."""
    assert client.get("/").status_code == 200


def test_nav_script_is_external_and_deferred(client):
    html = client.get("/").content.decode()

    assert "js/nav.js" in html, "the nav toggle script must be referenced"
    assert re.search(
        r"<script[^>]+js/nav\.js[^>]*\sdefer", html
    ), "the script must be deferred so the header exists when it boots"


def test_toggle_button_exposes_the_panel_it_controls(client):
    html = client.get("/").content.decode()

    button = re.search(r"<button[^>]*data-nav-toggle[^>]*>", html)
    assert button, "the hamburger toggle must render"
    button = button.group(0)

    assert 'aria-expanded="false"' in button, "collapsed state must be announced"
    controls = re.search(r'aria-controls="([^"]+)"', button)
    assert controls, "the toggle must point at the panel it controls"
    assert (
        f'id="{controls.group(1)}"' in html
    ), "aria-controls must reference an element that exists"


def test_anonymous_nav_matches_across_bar_and_panel(client):
    bar, panel = _nav_sections(client.get("/").content.decode())

    assert _hrefs(bar) == _hrefs(panel), (
        "the desktop bar and mobile panel render the same partial, so their "
        "links must match — a mismatch means the list was duplicated by hand"
    )
    assert "/accounts/login/" in _hrefs(bar)
    assert "/accounts/signup/" in _hrefs(bar)


def test_authenticated_nav_matches_across_bar_and_panel(client, user):
    client.force_login(user)
    bar, panel = _nav_sections(client.get("/").content.decode())

    hrefs = _hrefs(bar)
    assert hrefs == _hrefs(panel)
    # The signed-in links must reach the mobile panel too: on a phone it is the
    # only nav there is.
    assert "/dashboard/" in hrefs
    assert "/journey/" in hrefs
    assert "/accounts/logout/" in hrefs
    assert "/accounts/login/" not in hrefs
