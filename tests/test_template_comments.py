"""Static guard: ``{# ... #}`` comments must not span lines.

Django's ``{# #}`` comment syntax is **single-line only**. The lexer matches it
with a non-greedy pattern anchored inside one line, so a comment opened on one
line and closed on another is never recognised as a comment — the raw text is
emitted into the rendered page instead. It looks correct in the editor and
fails silently in the browser.

This shipped twice. ``templates/base.html`` leaked a five-line note about the
iOS home-screen label into the ``<head>`` of *every* page on the site, and
``templates/agents/assistant.html`` leaked two more into the assistant page.
``claims.tests.TestDocumentFileAffordances.test_no_template_comment_leaks_into_page``
caught the base.html one only because that page happened to be rendered by an
unrelated test; nothing was watching the rest of the template tree.

So the check is a scan over every template rather than an assertion about one
rendered page: any multi-line comment fails here, wherever it lives. Use
``{% comment %} ... {% endcomment %}`` for anything longer than a line.
"""

from pathlib import Path

import pytest

from django.conf import settings

TEMPLATE_ROOT = Path(settings.BASE_DIR) / "templates"


def _template_files():
    return sorted(TEMPLATE_ROOT.rglob("*.html"))


def _unclosed_comment_lines(text):
    """Return (line_number, line) for every ``{#`` not closed on its own line."""
    offenders = []
    for number, line in enumerate(text.splitlines(), start=1):
        # Walk each opener on the line; the closer must appear after it.
        position = 0
        while True:
            opened = line.find("{#", position)
            if opened == -1:
                break
            closed = line.find("#}", opened + 2)
            if closed == -1:
                offenders.append((number, line.strip()))
                break
            position = closed + 2
    return offenders


def test_templates_exist_to_scan():
    """Guard the guard: an empty glob would make this suite vacuously green."""
    assert len(_template_files()) > 50


@pytest.mark.parametrize(
    "template_path", _template_files(), ids=lambda p: str(p.relative_to(TEMPLATE_ROOT))
)
def test_no_multiline_django_comment(template_path):
    offenders = _unclosed_comment_lines(
        template_path.read_text(encoding="utf-8", errors="replace")
    )

    assert not offenders, (
        f"{template_path.relative_to(TEMPLATE_ROOT)} opens a `{{#` that is not "
        f"closed on the same line, so the comment text renders into the page. "
        f"Use {{% comment %}}...{{% endcomment %}} instead. "
        f"Offending lines: {offenders}"
    )
