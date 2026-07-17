"""
Streaming Assistant Tripwires — fast, deterministic invariant tests.

These guard the three contracts that keep the streaming AI assistant honest as
the code evolves (docs/ux/assistant-interactions.md §9):

1. Telemetry / no-PHI:   a full turn leaks ZERO prompt/answer text into logs or
                         the analytics (AuditLog) sink — only metadata crosses.
                         Enforces docs/security-invariants.md §3.
2. State machine:        `assistant_stream` emits ``open → delta* → done`` for a
                         normal turn, and a mid-stream ``GatewayStreamError``
                         yields a single ``error`` event carrying only the mapped
                         ``public_code`` — never the raw provider message.
3. Consent:              no consent → a lone ``consent_required`` event, and the
                         gateway stream is never opened (ADR-002 Layer-1 gate).

They run under pytest without Playwright/BDD. A fake gateway drives the stream so
no API key or token spend is involved.

Run with: .auditvenv/bin/python -m pytest tests/test_assistant_streaming_tripwires.py -v

NOTE: the Django test Client needs a host in ALLOWED_HOSTS, which this project
sets explicitly (no auto-added "testserver"). Every request below passes
``SERVER_NAME="localhost"`` or it 400s.
"""

import json
import logging
import re

import pytest
from django.urls import reverse

from agents import views
from agents.ai_gateway import GatewayStreamError
from core.models import AuditLog

# =============================================================================
# Fakes & helpers
# =============================================================================

SERVER = {"SERVER_NAME": "localhost"}  # host must be in ALLOWED_HOSTS


class _FakeGateway:
    """Stand-in for the AI gateway. ``stream()`` yields canned deltas, then
    optionally raises — modeling a mid-stream provider failure without a key."""

    def __init__(self, deltas=None, error=None):
        self._deltas = list(deltas or [])
        self._error = error

    def stream(self, system_prompt, user_prompt, **kwargs):
        for delta in self._deltas:
            yield delta
        if self._error is not None:
            raise self._error


def _use_fake_gateway(monkeypatch, gateway):
    """Force the live-key streaming path and swap in a fake gateway."""
    monkeypatch.setattr(views, "_has_live_key", lambda: True)
    monkeypatch.setattr(views, "get_gateway", lambda: gateway)


def _drive_turn(client, prompt):
    """POST one assistant turn and return the raw SSE body (fully consumed).

    Consuming ``streaming_content`` is what actually runs the generator (and its
    logging), so callers read logs/AuditLog only after this returns.
    """
    response = client.post(
        reverse("agents:assistant_stream"), {"prompt": prompt}, **SERVER
    )
    return b"".join(response.streaming_content).decode("utf-8")


def _parse_sse(raw):
    """Parse an SSE body into an ordered list of ``(event, data_dict)`` frames."""
    frames = []
    for block in raw.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event, data = None, None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data = json.loads(line[len("data:") :].strip())
        frames.append((event, data))
    return frames


def _content_tokens(*texts):
    """Distinctive alphanumeric tokens (len ≥ 4) from prompt/answer text.

    Length-gating avoids false positives against metadata words that legitimately
    appear in logs ("start", "user", "demo", "assistant_stream"); the sentinels
    baked into the fixtures below are all well over the threshold.
    """
    tokens = set()
    for text in texts:
        tokens.update(re.findall(r"[A-Za-z0-9]{4,}", text))
    return tokens


# =============================================================================
# 1. Telemetry / no-PHI tripwire (docs/ux §5, security-invariants §3)
# =============================================================================


@pytest.mark.django_db
class TestAssistantTelemetryNoPHI:
    """A full turn must never surface prompt or answer text to any observer sink."""

    def test_no_prompt_or_answer_text_in_logs_or_analytics(
        self, authenticated_client, monkeypatch, caplog
    ):
        # PHI-shaped prompt + a model answer, each carrying a unique sentinel so
        # the assertion is meaningful even if wording drifts.
        prompt = (
            "PTSD nightmares after Fallujah, my knee gives out; "
            "file number ptsdSENTINEL42"
        )
        answer_deltas = [
            "The evidence ",
            "you want is ",
            "a nexus letter answerSENTINEL99 ",
            "from your doctor.",
        ]
        answer = "".join(answer_deltas)

        _use_fake_gateway(monkeypatch, _FakeGateway(deltas=answer_deltas))
        AuditLog.objects.all().delete()
        caplog.set_level(logging.DEBUG)

        raw = _drive_turn(authenticated_client, prompt)
        events = _parse_sse(raw)

        # Sanity: the turn actually ran end-to-end and streamed the whole answer.
        assert events[0][0] == "open"
        assert ("done", {}) in events
        streamed = "".join(d["t"] for e, d in events if e == "delta")
        assert streamed == answer

        # --- Log sink: zero prompt/answer substrings, metadata only ------------
        log_blob = (
            "\n".join(r.getMessage() for r in caplog.records)
            + "\n"
            + "\n".join(str(r.args) for r in caplog.records)
        )

        for token in _content_tokens(prompt, answer):
            assert token not in log_blob, f"PHI token {token!r} leaked into logs"
        assert prompt not in log_blob
        assert answer not in log_blob
        # The allowed metadata log line MUST be present — proves the tripwire
        # isn't passing merely because logging was silently skipped, and that the
        # PHI-free "start" line (turn/user id, length) is what actually emits.
        assert any("assistant_stream start" in r.getMessage() for r in caplog.records)

        # --- Analytics sink (AuditLog): zero prompt/answer substrings ----------
        for entry in AuditLog.objects.all():
            blob = json.dumps(entry.details) + " " + (entry.error_message or "")
            for token in _content_tokens(prompt, answer):
                assert (
                    token not in blob
                ), f"PHI token {token!r} leaked into an AuditLog record"


# =============================================================================
# 2. State-machine tripwire (docs/ux §0, §3.1, §4.2)
# =============================================================================


@pytest.mark.django_db
class TestAssistantStateMachine:
    """SSE event ordering is the contract shared by view, JS controller, and tests."""

    def test_normal_turn_emits_open_delta_done(self, authenticated_client, monkeypatch):
        _use_fake_gateway(
            monkeypatch, _FakeGateway(deltas=["Hello ", "there ", "veteran."])
        )

        events = _parse_sse(
            _drive_turn(authenticated_client, "How do I file a Supplemental Claim?")
        )
        names = [e for e, _ in events]

        assert names[0] == "open"
        assert names[-1] == "done"
        assert names.count("open") == 1
        assert names.count("done") == 1
        assert "error" not in names
        # Everything between open and done is a delta — open → delta* → done.
        assert names[1:-1] == ["delta", "delta", "delta"]
        # `open` carries the turn id (for client stop/reconcile); `done` is bare.
        assert "turn_id" in events[0][1]
        assert events[-1][1] == {}

    def test_midstream_gateway_error_emits_mapped_public_code_only(
        self, authenticated_client, monkeypatch
    ):
        # A raw provider message that must NEVER cross the wire (or hit logs).
        raw_provider_msg = (
            "anthropic.InternalServerError: overloaded_error "
            "request_id=req_LEAKYSECRET123"
        )
        err = GatewayStreamError("rate_limited")
        err.__cause__ = RuntimeError(raw_provider_msg)  # chained for Sentry, not client

        _use_fake_gateway(
            monkeypatch,
            _FakeGateway(deltas=["partial ", "answer "], error=err),
        )

        raw = _drive_turn(authenticated_client, "Explain my disability rating")
        events = _parse_sse(raw)
        names = [e for e, _ in events]

        # Stream opened and delivered partial tokens before failing.
        assert names[0] == "open"
        assert "delta" in names
        # Terminates on error, never a done, and exactly one error frame.
        assert names[-1] == "error"
        assert "done" not in names
        assert names.count("error") == 1

        # Only the mapped public_code crosses the wire — nothing else.
        assert events[-1][1] == {"code": "rate_limited"}

        # The raw provider message / request id never appear in the SSE body.
        assert "overloaded_error" not in raw
        assert "req_LEAKYSECRET123" not in raw
        assert "InternalServerError" not in raw

    def test_public_code_maps_to_calm_copy(self):
        """Every code the stream can emit must resolve to calm, coded error copy
        (docs/ux §4.2 / §7) — a code with no copy would surface a blank error."""
        from agents import assistant_copy

        for code in (
            "rate_limited",
            "timeout",
            "stream_interrupted",
            "consent_required",
            "generic",
        ):
            assert code in assistant_copy.ERRORS
            assert assistant_copy.ERRORS[code]["message"]


# =============================================================================
# 3. Consent tripwire (ADR-002 Layer-1 gate, docs/ux §4.2)
# =============================================================================


@pytest.fixture
def no_consent_client(client, db, user_password):
    """A logged-in client whose profile has NOT granted AI processing consent.

    Uses the same consent mechanism the ADR-002 fixtures rely on
    (``profile.ai_processing_consent`` read by ``check_ai_consent``).
    """
    from django.contrib.auth import get_user_model
    from accounts.models import UserProfile

    User = get_user_model()
    user = User.objects.create_user(
        email="noconsent@example.com",
        password=user_password,
        first_name="No",
        last_name="Consent",
    )
    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.ai_processing_consent = False
    profile.save()
    # Precondition: the canonical helper agrees consent is absent.
    assert views.check_ai_consent(user) is False
    client.login(email=user.email, password=user_password)
    return client


@pytest.mark.django_db
class TestAssistantConsentGate:
    """No consent must short-circuit to consent_required before any stream opens."""

    def test_no_consent_yields_consent_required_and_never_streams(
        self, no_consent_client, monkeypatch
    ):
        # A gateway that records if it is ever asked to stream. It must not be.
        opened = {"stream": False}

        class _GuardGateway:
            def stream(self, *args, **kwargs):
                opened["stream"] = True
                yield "SHOULD-NOT-STREAM"

        # Even with a live key available, the consent gate wins first.
        _use_fake_gateway(monkeypatch, _GuardGateway())

        raw = _drive_turn(no_consent_client, "Explain my decision letter")
        events = _parse_sse(raw)

        assert [e for e, _ in events] == ["error"]
        assert events[0][1] == {"code": "consent_required"}
        assert opened["stream"] is False
        assert "SHOULD-NOT-STREAM" not in raw
