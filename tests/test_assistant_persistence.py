"""
Tests for the streaming assistant's persistence + server-side stop.

Covers the second slice of docs/ux/assistant-interactions.md:
  1. Persistence — user turn + assistant answer are saved so the thread survives
     reload; a *stopped* partial is kept; nothing persists without consent.
  2. Server-side stop — POST /agents/assistant/stop/ closes the stream and is
     scoped to the requesting user.
  3. PHI — the prompt/answer text never reaches the logs.
  4. GET rendering — persisted thread renders; empty state only at zero turns.

Run with: .auditvenv/bin/python -m pytest tests/test_assistant_persistence.py -v
"""

import json
import logging

import pytest
from django.core.cache import cache
from django.urls import reverse

from agents.models import AssistantThread, AssistantTurn
from agents.views import _stop_key

# A small, deterministic, sleep-free delta stream so tests are fast and the
# persisted content is predictable. It is a real generator so `.close()` works
# exactly as it does for the gateway/demo generators in production.
DELTAS = ["Hello ", "world ", "foo ", "bar ", "baz "]


def _fake_deltas(_text):
    for token in DELTAS:
        yield token


@pytest.fixture
def force_demo(monkeypatch):
    """Force the demo path with controlled, fast deltas (no API key, no sleeps)."""
    monkeypatch.setattr("agents.views._has_live_key", lambda: False)
    monkeypatch.setattr("agents.views._demo_deltas", _fake_deltas)


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _consume(response):
    """Drain a StreamingHttpResponse into a list of parsed SSE frames.

    Consuming ``streaming_content`` is what actually runs the view's generator
    (and therefore its DB writes).
    """
    frames = []
    for raw in response.streaming_content:
        text = raw.decode() if isinstance(raw, bytes) else raw
        ev = None
        data = {}
        for line in text.strip().splitlines():
            if line.startswith("event: "):
                ev = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        if ev:
            frames.append((ev, data))
    return frames


@pytest.mark.django_db
class TestAssistantPersistence:
    def test_done_persists_user_and_assistant_turns(
        self, authenticated_client, force_demo
    ):
        resp = authenticated_client.post(
            reverse("agents:assistant_stream"), {"prompt": "How do I appeal?"}
        )
        events = _consume(resp)

        # State machine: open → delta* → done
        assert events[0][0] == "open"
        assert "turn_id" in events[0][1]
        assert events[-1][0] == "done"
        assert [e for e, _ in events].count("delta") == len(DELTAS)

        turns = list(AssistantTurn.objects.order_by("id"))
        assert [t.role for t in turns] == ["user", "assistant"]
        assert turns[0].content == "How do I appeal?"
        assert turns[1].content == "".join(DELTAS)
        assert turns[1].stopped is False
        # One thread, owned by the requesting user.
        assert AssistantThread.objects.count() == 1
        assert turns[0].thread == turns[1].thread

    def test_second_turn_reuses_same_thread(self, authenticated_client, force_demo):
        url = reverse("agents:assistant_stream")
        _consume(authenticated_client.post(url, {"prompt": "first"}))
        _consume(authenticated_client.post(url, {"prompt": "second"}))

        assert AssistantThread.objects.count() == 1
        assert AssistantTurn.objects.count() == 4  # 2 user + 2 assistant

    def test_stopped_keeps_partial_answer(self, authenticated_client, force_demo):
        """A mid-stream stop persists the partial answer, flagged stopped."""
        resp = authenticated_client.post(
            reverse("agents:assistant_stream"), {"prompt": "explain my letter"}
        )

        turn_id = None
        deltas_seen = 0
        got_stopped = False
        for raw in resp.streaming_content:
            text = raw.decode() if isinstance(raw, bytes) else raw
            if "event: open" in text:
                turn_id = json.loads(text.split("data: ", 1)[1])["turn_id"]
            elif "event: delta" in text:
                deltas_seen += 1
                if deltas_seen == 2:
                    # Simulate the /stop endpoint firing after two tokens.
                    cache.set(_stop_key(turn_id), True, 300)
            elif "event: stopped" in text:
                got_stopped = True
                break

        assert got_stopped, "stream should emit a stopped event once flagged"
        assistant_turn = AssistantTurn.objects.get(role="assistant")
        assert assistant_turn.stopped is True
        # Exactly the deltas streamed before the stop were kept (never more).
        assert assistant_turn.content == "".join(DELTAS[:2])

    def test_no_consent_persists_nothing(self, authenticated_client, user, force_demo):
        user.profile.ai_processing_consent = False
        user.profile.save()

        resp = authenticated_client.post(
            reverse("agents:assistant_stream"), {"prompt": "sensitive question"}
        )
        events = _consume(resp)

        assert events == [("error", {"code": "consent_required"})]
        assert AssistantTurn.objects.count() == 0
        assert AssistantThread.objects.count() == 0

    def test_empty_prompt_persists_nothing(self, authenticated_client, force_demo):
        resp = authenticated_client.post(
            reverse("agents:assistant_stream"), {"prompt": "   "}
        )
        events = _consume(resp)
        assert events == [("error", {"code": "generic"})]
        assert AssistantTurn.objects.count() == 0


@pytest.mark.django_db
class TestAssistantStopEndpoint:
    def test_stop_sets_flag_for_own_turn(self, authenticated_client, user):
        thread = AssistantThread.objects.create(user=user)
        turn = AssistantTurn.objects.create(
            thread=thread, user=user, role="user", content="hi"
        )

        resp = authenticated_client.post(
            reverse("agents:assistant_stop"), {"turn_id": turn.pk}
        )
        assert resp.status_code == 204
        assert cache.get(_stop_key(turn.pk)) is True

    def test_stop_scoped_to_user(self, client, user, other_user, user_password):
        """A user cannot stop another user's stream (ownership via the turn row)."""
        thread = AssistantThread.objects.create(user=user)
        turn = AssistantTurn.objects.create(
            thread=thread, user=user, role="user", content="hi"
        )

        client.login(email=other_user.email, password=user_password)
        resp = client.post(reverse("agents:assistant_stop"), {"turn_id": turn.pk})

        assert resp.status_code == 404
        assert cache.get(_stop_key(turn.pk)) is None  # no cross-user flag set

    def test_stop_missing_turn_id(self, authenticated_client):
        resp = authenticated_client.post(reverse("agents:assistant_stop"), {})
        assert resp.status_code == 400


@pytest.mark.django_db
class TestAssistantNoPHIInLogs:
    def test_prompt_never_logged(self, authenticated_client, force_demo, caplog):
        secret = "UNIQUEPHITOKEN_lumbar_strain_9F3X"
        with caplog.at_level(logging.DEBUG):
            _consume(
                authenticated_client.post(
                    reverse("agents:assistant_stream"), {"prompt": secret}
                )
            )
        # The prompt (PHI) must not appear in any log record.
        for record in caplog.records:
            assert secret not in record.getMessage()


@pytest.mark.django_db
class TestAssistantGetRendering:
    def test_empty_state_when_no_turns(self, authenticated_client):
        resp = authenticated_client.get(reverse("agents:assistant"))
        html = resp.content.decode()
        assert resp.status_code == 200
        assert 'id="assistant-empty"' in html
        assert "Ask about your VA benefits." in html

    def test_renders_persisted_thread(self, authenticated_client, user):
        thread = AssistantThread.objects.create(user=user)
        AssistantTurn.objects.create(
            thread=thread, user=user, role="user", content="What is a nexus letter?"
        )
        AssistantTurn.objects.create(
            thread=thread,
            user=user,
            role="assistant",
            content="A nexus letter links your condition to service.",
            stopped=True,
        )

        resp = authenticated_client.get(reverse("agents:assistant"))
        html = resp.content.decode()

        assert 'id="assistant-empty"' not in html  # empty state suppressed
        assert "What is a nexus letter?" in html
        assert "A nexus letter links your condition to service." in html
        assert "Stopped." in html  # stopped partial labeled on reload

    def test_thread_scoped_to_user(self, client, user, other_user, user_password):
        thread = AssistantThread.objects.create(user=other_user)
        AssistantTurn.objects.create(
            thread=thread, user=other_user, role="user", content="OTHER_USER_SECRET"
        )

        client.login(email=user.email, password=user_password)
        resp = client.get(reverse("agents:assistant"))

        # user sees their own (empty) thread, never other_user's content.
        assert "OTHER_USER_SECRET" not in resp.content.decode()
        assert 'id="assistant-empty"' in resp.content.decode()
