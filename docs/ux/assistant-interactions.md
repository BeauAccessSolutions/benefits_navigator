# Assistant Interactions — UX/Interaction Design

**App:** VA Benefits Navigator (Django + HTMX + Anthropic Claude)
**Surface:** The conversational AI assistant (streaming chat over VA benefits, M21-1 guidance, decision-letter Q&A).
**Status:** Design spec — implementation-oriented. Companion to the engineering docs in [`docs/architecture.md`](../architecture.md), [`docs/PHI_DATA_FLOW.md`](../PHI_DATA_FLOW.md), [`docs/security-invariants.md`](../security-invariants.md), and [`docs/adr/002-ai-consent-model.md`](../adr/002-ai-consent-model.md).

> **Inheritance.** This doc implements the platform standard at
> `bas-platform/docs/design-principles.md` for the *AI-assistant shape*. It tailors three sections:
> **§3.1** (send / optimistic UI), **§3.4** (empty & error states), and **§4** (accessibility spine — dynamic status).
> Where the platform doc says *what every app must feel like*, this says *how the Navigator assistant builds it* on Django + HTMX + a token-streaming Claude backend.
>
> **Governing principle (inherited):** the highest a11y bar forges the best design. Every pattern below is authored to pass WCAG 2.2 AA + axe before it ships; accessibility is threaded through, not appended.

---

## 0. The one state machine everything hangs off

Every assistant turn moves through explicit, nameable states. Color and motion are **never** the sole carrier of any of them (§4). This machine is the contract shared by the view, the template, the JS controller, and the tests.

```
                ┌─────────────── user edits prompt ───────────────┐
                ▼                                                  │
  ┌──────┐  submit   ┌─────────┐  first token  ┌───────────┐  done   ┌──────┐
  │ idle │ ────────▶ │ queued  │ ────────────▶ │ streaming │ ──────▶ │ done │
  └──────┘           └─────────┘               └───────────┘         └──────┘
     ▲                    │                          │                   │
     │                    │ connect/consent error    │ stop / net error  │ feedback
     │                    ▼                          ▼                   │
     │               ┌────────┐  retry (prompt kept) │                   │
     └─────────────  │ failed │ ◀────────────────────┘                   │
                     └────────┘                                          │
                          ▲──────────────── stopped (partial kept) ──────┘
```

| State | User sees | ARIA | Persisted? |
|---|---|---|---|
| `idle` | Composer ready; empty state on first run | — | — |
| `queued` | User bubble rendered optimistically; assistant "Thinking…" placeholder | `aria-busy="true"` on region, polite "Assistant is thinking" | user turn: yes (optimistic id) |
| `streaming` | Tokens appending; **Stop generating** button live | `aria-busy="true"`; region **not** re-announced per token | assistant turn: buffered, flushed on `done` |
| `done` | Full answer, sources, feedback controls | polite "Response complete" (debounced, once) | yes |
| `stopped` | Partial answer + "Stopped — [Continue] / [Ask again]" | polite "Response stopped" | partial kept |
| `failed` | Calm error card + **Try again**; **prompt preserved in composer** | `role="alert"` assertive | error event only (no content) |

**Focus management on each transition** (a status announcement is not enough — focus must land somewhere sensible or a keyboard/SR user is stranded on a control that just disappeared):

| Transition | Where focus goes |
|---|---|
| `→ done` | The completed response region (`#assistant-response`, `tabindex="-1"`) — SR user reads from the top of the new answer. |
| `→ stopped` | The **Continue / Ask again** control group. |
| `→ failed` | The **Try again** button in the error card (the card is `tabindex="-1"` as a fallback). Focus never stays on the now-removed **Stop generating** button. |

The single source of truth for these strings is the **copy deck (§7)**. Do not inline status text in templates.

---

## 1. First-run empty state — starter chips (§3.4)

> Platform rule: *"The first empty screen is onboarding — coach, don't leave it blank. Every empty thread: one-line explanation + a single primary CTA (or 3–4 starter chips on first run)."*

The first time a veteran opens the assistant (no prior turns in this thread), show a warm, low-anxiety launcher with **3–4 tappable starter-prompt chips that demonstrate range** — Gemini-style. The chips are the onboarding; they teach what the assistant is good at without a tour.

### Content — chips that show range

Pick chips that span the assistant's real capabilities so the veteran learns the surface by reading four examples. Keep each ≤ ~48 characters so it fits one line on mobile.

| # | Chip label | Demonstrates |
|---|---|---|
| 1 | "Explain my decision letter in plain language" | Document comprehension |
| 2 | "What evidence strengthens a PTSD claim?" | Benefits knowledge / guidance |
| 3 | "How do I file a Supplemental Claim?" | Process / how-to |
| 4 | "Help me draft a personal statement" | Generative assistance |

Copy is owned by the copy deck (§7), not hard-coded in the template, so Legal/Content can revise chips without a template change.

### Layout & behavior

- Heading (one line): **"Ask about your VA benefits."** Sub-line: **"I can explain letters, point to evidence, and walk you through next steps."** Then the chip row.
- Tapping a chip = the same code path as typing that text and hitting send (§3.1). It does **not** auto-send silently in a way the user can't see: the chip's text lands in the composer *and* submits, so the optimistic user bubble shows exactly what was asked. (This keeps the "what did I just send" model honest and is screen-reader legible.)
- Chips disappear once the thread has any turn; they are first-run only. Returning to an empty thread later shows the same launcher (empty ≠ error — never a dead end).
- Below the chips, one muted line sets expectations honestly: **"I can be wrong. I'll tell you when I'm unsure, and I'll show where answers come from."** This primes the uncertainty framing in §4 *before* the first mistake, which is where trust is actually won.

### Markup (Django template + Tailwind)

```html
{# templates/assistant/_empty_state.html — rendered when thread has 0 turns #}
<section class="assistant-empty" aria-labelledby="assistant-empty-heading">
  <h2 id="assistant-empty-heading" class="text-xl font-semibold">
    {{ copy.empty.heading }}
  </h2>
  <p class="text-gray-600 dark:text-gray-300 mt-1">{{ copy.empty.subheading }}</p>

  <ul class="starter-chips mt-4 grid gap-2 sm:grid-cols-2" role="list">
    {% for chip in copy.empty.chips %}
    <li>
      {# A chip is a real <button>: keyboard/AT operable, 44px min target (§1 platform) #}
      <button type="button"
              class="chip w-full min-h-[44px] text-left rounded-xl border px-4 py-3
                     hover:bg-gray-50 dark:hover:bg-gray-800 focus-visible:ring-2"
              data-chip-prompt="{{ chip.text }}">
        {{ chip.text }}
      </button>
    </li>
    {% endfor %}
  </ul>

  <p class="text-sm text-gray-500 dark:text-gray-400 mt-4">{{ copy.empty.expectation }}</p>
</section>
```

```js
// Chip → composer → submit. Same path as manual send; nothing hidden from the user.
document.querySelectorAll('.chip').forEach((btn) => {
  btn.addEventListener('click', () => {
    const input = document.querySelector('#composer-input');
    input.value = btn.dataset.chipPrompt;
    input.focus();
    document.querySelector('#composer-form').requestSubmit();
  });
});
```

---

## 2. Send behavior & optimistic UI (§3.1)

> Platform rule: *"Desktop: Enter sends, Shift+Enter newline (ship a preference toggle, default Enter-sends). Mobile: never send on Return; a dedicated send button is the only send affordance. Render optimistically. Failed messages persist with inline Retry — never silently dropped, never retyped."*

### Send affordance

- **Desktop:** Enter sends, Shift+Enter inserts a newline. Ship the Slack-style preference toggle (default Enter-sends) — reuse the platform `packages/ui` behavior; do not re-invent.
- **Mobile:** Return is a newline only. The **Send** button is the *only* way to send. This structurally prevents the accidental-send class of errors — which matters more here than in chat, because a half-typed medical question sent early is both a bad answer and a needless PHI round-trip.
- Composer is a `<textarea>` with `inputmode="text"`, **16px minimum font** (below that, mobile Safari zooms on focus — platform §1), auto-growing, with a visible character affordance only if a real limit exists.
- **Send is disabled until the composer holds non-whitespace content** (chip-fill satisfies this). This structurally blocks the empty/whitespace-only turn — a wasted PHI round-trip and a confusing empty bubble — without a mid-typing validation error (platform §1: don't validate mid-first-entry). The disabled state is conveyed by more than color (dimmed + `aria-disabled`/`disabled`), per §4.

### Optimistic render

On submit, **before the network responds**:

1. Render the user's turn immediately as a bubble with a client-generated `data-optimistic-id`.
2. Render an assistant placeholder in `queued` state ("Thinking…", `aria-busy`).
3. Disable the send button; swap it for **Stop generating** (see §3) once streaming opens.
4. Clear the composer — **but keep the sent text in memory** so a `failed` turn can restore it (see §3.4 recovery). Never lose the user's words.

The user turn is optimistic but **truthful**: if the request never reaches the server (offline, consent gate, 5xx on open), the user bubble flips to `failed` with an inline **Try again**, and the exact text is restored to the composer. It is never silently dropped and never made the user's job to retype.

### Offline

Per platform §3.4: a persistent, non-modal banner — **"You're offline. Your message will send when you reconnect."** — plus local queue-and-flush. The assistant is a request/stream, not fire-and-forget, so "queue" here means: hold the composed prompt and show the banner. On reconnect, **re-enable Send and announce "Back online — ready to send" rather than firing automatically** — a silent auto-send after the veteran has looked away is a consent-of-attention surprise, and a streamed answer nobody is watching is wasted PHI processing. (If usability testing shows the extra tap frustrates users, revisit — but default to explicit.) Never a dead-end error.

---

## 3. Streaming AI responses — optimistic, interruptible, reduced-motion aware

This is the interaction that defines the app. It must feel alive, be stoppable, and never lie about its state.

### 3.1 Transport: SSE over `StreamingHttpResponse` (fits the existing stack)

The assistant streams tokens via **Server-Sent Events** from a Django `StreamingHttpResponse`, driven by the Anthropic SDK's streaming API in the existing `agents/ai_gateway.py` layer. This fits the current stack (HTMX + sync Django views) without pulling in Channels/ASGI the way KindredAccess does — the Navigator's assistant is a single-user request/stream, not multi-party presence, so websockets would be over-engineering.

> **Add a streaming method to the gateway** rather than calling the Anthropic client from the view. The gateway is where sanitization, consent-aware model selection, token accounting, and the `Result` error contract already live (see `security-invariants.md` §2 — *AI outputs schema-validated*). Streaming is chat prose, not a structured object, so it uses a **new** `stream()` method that yields text deltas; it does **not** go through `complete_structured()`.

```python
# agents/ai_gateway.py — new streaming entry point (sketch)
def stream(self, system_prompt: str, user_prompt: str, *, sanitize: bool = True):
    """Yield text deltas for a chat turn. Raises GatewayError on open failure.

    Caller is responsible for the SSE envelope. This method NEVER logs
    user_prompt or deltas (PHI) — see PHI section below.
    """
    if sanitize:
        user_prompt = sanitize_input(user_prompt)
    client = self.client  # lazy Anthropic() from settings
    with client.messages.stream(
        model=self.config.model,                 # ANTHROPIC_MODEL, default claude-sonnet-5
        max_tokens=self.config.max_tokens,
        system=[{"type": "text", "text": system_prompt,
                 "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text
        # final message (stop_reason, usage) available via stream.get_final_message()
```

```python
# agents/views.py — SSE view (sketch). Dual consent check per ADR-002 still applies.
from django.http import StreamingHttpResponse
import json

@login_required
def assistant_stream(request):
    require_ai_consent(request.user)          # Layer-1 check (ADR-002); Layer-2 lives in gateway path
    prompt = sanitize_input(request.POST["prompt"])
    turn = AssistantTurn.objects.create(user=request.user, role="user", ...)  # optimistic id reconciliation

    def event_stream():
        buf = []
        try:
            yield sse("open", {"turn_id": turn.id})
            for delta in gateway.stream(SYSTEM_PROMPT, prompt):
                buf.append(delta)
                yield sse("delta", {"t": delta})          # token(s)
            yield sse("done", {"turn_id": turn.id})
        except GatewayError as e:
            # calm, mapped error — NEVER the raw exception text to the client
            yield sse("error", {"code": e.public_code})   # see §4 copy mapping
        finally:
            # Persist the ASSISTANT answer text (allowed — it's model output, not OCR/PHI source).
            # If interrupted, buf holds the partial; save it so "stopped" state survives reload.
            persist_assistant_turn(turn.thread, "".join(buf))

    resp = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"          # disable proxy buffering so tokens flush live
    return resp

def sse(event, data):  # helper
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
```

> **Note on assistant text vs. PHI.** Persisting the *assistant's answer* is fine — it is model output the veteran asked to see. What must never be persisted is **OCR-extracted source text** (`security-invariants.md` §1). The streaming path carries chat prose, not raw document OCR, and the assistant turn is saved on `done`/`stopped` so the thread survives reload.

### 3.2 In-flight → done → failed, made visible

Each state has a **text/shape** signal, never color-only (§4):

- **`queued`:** assistant placeholder reads "Thinking…" with a non-spinning-only indicator (a labeled shape + text; the dots animation is decorative and reduced-motion-gated).
- **`streaming`:** tokens append into the assistant bubble; the **Stop generating** button is present; the bubble carries `aria-busy="true"`.
- **`done`:** `aria-busy` removed; a subtle "✓ Response complete" affordance (icon **+ text**); source citations and feedback controls (👍/👎, Copy) appear.
- **`failed`:** the streaming bubble is replaced by the error card (§4). No half-rendered ghost text left implying success.

### 3.3 Interruptible — "Stop generating"

- While `streaming`, the send button is replaced by a **Stop generating** button (visible text, not icon-only), keyboard-focusable, `min-h-[44px]`.
- Clicking it (a) aborts the client `EventSource`/fetch, (b) fires a lightweight `POST /assistant/stop` so the server can close the Anthropic stream and stop spending tokens, and (c) transitions the turn to **`stopped`**, keeping the partial answer.
- `stopped` shows the partial text plus **[Continue] / [Ask again]** — the partial is never thrown away, and the user is never forced to re-read a truncated answer wondering if it crashed.
- Escape key while focus is in the response region also stops generation (documented shortcut, mirrors "every dynamic action has an escape hatch," platform §1).

### 3.4 Token streaming that respects reduced-motion

The default streaming feel is tokens flowing in with a soft cursor and a gentle fade — the "alive" signal. But **`prefers-reduced-motion` is a gate, not a nicety** (platform §2 rule 4, §4).

Two rendering modes, chosen at runtime:

| | **Motion OK (default)** | **`prefers-reduced-motion: reduce`** |
|---|---|---|
| Token arrival | Append per delta; soft fade-in; blinking caret | **Append per delta with no fade, no caret animation.** Text still streams (content is not motion) but nothing pulses/blinks/slides. |
| "Thinking…" | Animated dots | Static "Thinking…" text |
| Completion | Subtle settle | Instant, no transition |

Text appearing *is not itself "motion"* in the WCAG sense — reduced-motion users still get live streaming, which they may rely on to know the system is working. What we remove is the *decorative* layer: the blink, the fade, the pulse. Detect in both CSS and JS:

```css
/* Decorative streaming motion — gated */
@media (prefers-reduced-motion: no-preference) {
  .assistant-caret { animation: blink 1s step-end infinite; }
  .assistant-delta { animation: fade-in 120ms ease-out; }
  .thinking-dots::after { animation: dots 1.2s infinite; }
}
@media (prefers-reduced-motion: reduce) {
  .assistant-caret { display: none; }
  .assistant-delta { animation: none; }
  .thinking-dots::after { content: '…'; }   /* static */
}
```

```js
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
// e.g. skip caret insertion and fade class when reduceMotion is true
```

All decorative animations stay under ~300ms and use natural easing (platform §2 rule 2). No animation may be the *only* way a state is conveyed (§4).

---

## 4. Uncertainty & hallucination framing

An assistant that answers VA-benefits questions **will** sometimes be wrong, and its users are often navigating stressful, high-stakes claims. The design job is to make being-wrong *calm, honest, and recoverable* — never alarming, never blaming the user, never pretending confidence it doesn't have.

### 4.1 Say when it's unsure — before it's wrong

- The assistant is prompted (system prompt) to **surface uncertainty explicitly** and to prefer "I'm not certain — here's how to verify" over a confident guess on regulatory specifics (ratings %, deadlines, eligibility edges).
- When the model signals low confidence or declines, render a distinct, **calm** treatment — not an error, an *honesty affordance*:

  > **I'm not fully sure about this one.** VA rules here are specific and I don't want to steer you wrong. Here's what I'd check: [link to the M21-1 section / "Talk to a VSO"].

- **Always show provenance.** Where an answer draws on scraped M21-1 / KnowVA content, attach source citations (title + link) under the `done` state. "Show where this comes from" is the single most effective anti-hallucination affordance we have — it lets the veteran verify rather than trust blindly. This is also why the first-run expectation line (§1) promises it.
- Never present generated prose as an official VA determination. A persistent, quiet disclaimer sits under the composer: **"Guidance only — not legal advice or an official VA decision."**

### 4.2 Error copy: calm, blame-free, recovery attached, prompt preserved (§3.4)

> Platform rule: *"Error copy: plain-language, no blame, recovery action attached, user input preserved. No raw stack traces."*

Every failure the veteran can hit maps to a **pre-written, calm** message with a recovery action. The raw `GatewayError` / stack trace never reaches the client (it goes to Sentry with `send_default_pii=False`, per `security-invariants.md` §4). Mapping lives server-side; the client only ever receives a `public_code`.

| Situation | What the veteran sees (calm, blame-free) | Recovery | Prompt kept? |
|---|---|---|---|
| Model/network failed mid-stream | "Something interrupted my answer — that's on me, not you. Want me to try again?" | **Try again** (re-streams same prompt) | ✅ restored to composer |
| Timeout / slow upstream | "This is taking longer than it should. You can wait a moment or try again." | **Keep waiting** / **Try again** | ✅ |
| Rate limited / busy | "A lot of people are asking right now. Give it a few seconds and try again." | **Try again** (with backoff) | ✅ |
| Consent not granted (ADR-002) | "Before I can help with this, I'll need your OK to use AI on your documents." | **Review AI consent** → consent flow | ✅ |
| Model declined / safety | "I can't help with that one, but I can point you to a VSO who can." | **Find a VSO** | ✅ |
| Offline | (banner, §2) "You're offline. I'll send this when you reconnect." | auto-retry on reconnect | ✅ queued |

Rules that make these *feel* right:

- **No blame.** "That's on me" / "Something interrupted" — never "Invalid input" or "You did X."
- **No jargon, no codes** in the user-facing string. (The `public_code` is for logs and tests, not eyes.)
- **Recovery is one tap and always present.** A dead-end error is a bug.
- **The prompt is sacred.** On any `failed`/`stopped`, the veteran's exact words return to the composer (or the retry re-uses them). They never retype a hard-won description of their condition.
- **Partial answers survive** (`stopped`) — shown with a clear "Stopped" label so no one mistakes a truncated answer for a complete one.

---

## 5. Sensitive data — treat everything as PHI (platform invariants)

> Platform mapping (`design-principles.md` §5): *"Sensitive data → same PHI treatment as CIT."* Assistant prompts and answers routinely contain conditions, ratings, and file-number-adjacent detail. Treat the **entire assistant transcript as PHI**, identical to the CIT posture and to this repo's existing OCR handling.

Binding invariants for this surface (these are not new — they extend `PHI_DATA_FLOW.md` and `security-invariants.md` to the streaming assistant):

1. **No telemetry on sensitive content.** Analytics/metrics may record *that* a turn happened, latency, token counts, error `public_code`, and thumbs-up/down — **never** the prompt text, the answer text, chip choice as free text, or any delta. No content in event payloads, ever.
2. **No PHI in logs** (`security-invariants.md` §3). The `stream()` method and SSE view must never `logger.*` the `user_prompt`, the deltas, or the assembled answer. Structured log fields are `turn_id`, `user_id`, `latency_ms`, `token_count`, `public_code` only. The static check `scripts/check_security_invariants.py` should be extended to flag `logger.*` calls touching the prompt/delta variables in `agents/views.py` and `ai_gateway.py`.
3. **No PHI in URLs / query strings.** The prompt goes in the POST body, never the query string (platform Privacy rule). SSE endpoint takes no content in the path.
4. **Sentry stays PII-free.** `send_default_pii=False` already; the mapped `GatewayError.public_code` — not the message — is what's safe to attach as a tag. Do not add the prompt to Sentry breadcrumbs.
5. **Consent gates the stream, both ends** (ADR-002 dual-check). Layer-1 in the view before opening the stream; the gateway path re-verifies before the external call. `AIConsentError` is non-retryable and surfaces the calm "Review AI consent" recovery (§4.2), not a stack trace.
6. **Assistant answer persistence is allowed and bounded.** Saving the assistant turn (for thread continuity + `stopped` survival) is fine — it's model output, not OCR source text. It inherits the same at-rest protections as other user-scoped records and is deletable with the account. Raw document OCR text remains ephemeral and unpersisted (`security-invariants.md` §1) — the assistant does not change that.

> **Telemetry acceptance test:** a fixture that runs a full turn and asserts the analytics/log sink received *zero* substrings of the prompt/answer. This is the tripwire that keeps "no telemetry on sensitive content" honest as the code evolves — mirror the style of `tests/test_regression_tripwires.py`.

---

## 6. Accessibility spine — dynamic status (§4)

> The assistant is *all four* of the platform's riskiest dynamic-status spots at once: "typing" (streaming), send status, "presence" (thinking), and connectivity. Each is naturally built as a color-only or animation-only cue — which fails **SC 4.1.3 (Status Messages)**, **1.4.1 (Use of Color)**, and reduced-motion *simultaneously*. So the spine is non-negotiable here.

**Route every status through one live-region utility** (inherit `packages/ui`'s live-region + reduced-motion helper; `base.html` already ships a `role="status" aria-live="polite" aria-atomic="true"` region — reuse that pattern, don't spawn ad-hoc ones).

### 6.1 Announcements (SC 4.1.3)

| Event | Region | Politeness | Announced text | Debounce |
|---|---|---|---|---|
| Turn queued | status | `polite` | "Assistant is thinking." | once |
| **Streaming in progress** | — | — | **Not announced per token** — silence during stream (region is `aria-busy`) | n/a |
| **Streaming complete** | status | `polite` | "Response complete." | **once, on `done` only** |
| Stopped | status | `polite` | "Response stopped." | once |
| **Error** | alert | `assertive` (`role="alert"`) | the calm §4.2 string | once |
| Offline / online | status | `polite` | "You're offline / back online." | once each edge |

The **critical** rule (this is where naive streaming UIs fail screen-reader users): **do not** re-announce the response region on every token. That produces a machine-gun of interruptions that makes the assistant unusable with a screen reader. Instead:

- During `streaming`, the response container is `aria-busy="true"` and the live region is silent.
- On `done`, flip `aria-busy="false"` and announce **once**: "Response complete." The user then navigates into the now-complete answer at their own pace.
- Failures use `role="alert"` (assertive) so they *do* interrupt — an error is worth interrupting for; a token is not.

```html
{# One polite region for progress, one assertive region for errors. Reuse base.html's pattern. #}
<div id="assistant-status" role="status" aria-live="polite" aria-atomic="true" class="sr-only"></div>
<div id="assistant-error"  role="alert"  aria-live="assertive" class="sr-only"></div>

<div id="assistant-response" aria-busy="false" tabindex="-1" aria-label="Assistant response">
  {# streamed answer renders here #}
</div>
```

```js
// Announce once on done — never per delta.
function onDone() {
  const region = document.querySelector('#assistant-response');
  region.setAttribute('aria-busy', 'false');
  announce('#assistant-status', COPY.status.complete);   // "Response complete."
  region.focus();  // move focus to the completed answer so SR users can read it
}
function onError(publicCode) {
  announce('#assistant-error', COPY.errors[publicCode].message);  // assertive
}
```

### 6.2 Navigable response region (screen readers)

- The completed answer lives in a labeled container (`aria-label="Assistant response"`, `tabindex="-1"`) that receives focus on `done` — the reader lands *at the start of the new answer*, not lost at the bottom of the composer.
- Source citations are a real list of links, keyboard-reachable, in DOM order after the answer.
- Feedback controls (👍/👎, Copy, Try again) are real `<button>`s with text labels (or `aria-label`), each ≥ 44×44px hit area (platform §1), in a logical tab order.
- Headings/structure within long answers use real heading levels so screen-reader users can navigate by heading.

### 6.3 Color, shape, motion (SC 1.4.1 + reduced-motion)

- Every state is carried by **text or shape**, never color alone: `queued`/`streaming`/`done`/`failed` each have a word and/or an icon-with-label, not just a hue.
- Contrast ≥ 4.5:1 text / 3:1 UI components, verified in **both** light and dark (platform §4). The "unsure", error, **and `stopped`** treatments must clear contrast in both themes — check all three explicitly since they use accent colors that are easy to leave un-audited.
- Reduced-motion path (§3.4) removes caret blink, token fade, and thinking-dot animation while **keeping** the live text stream. Motion is never the sole state signal.
- Visible focus on every interactive element — chips, Send, Stop, feedback, citations (SC 2.4.11 / 2.4.13).

### 6.4 WCAG 2.2 success criteria this surface must pass

| SC | Where it bites | How we satisfy it |
|---|---|---|
| **4.1.3** Status Messages | streaming/thinking/error/offline | single live-region utility; announce-once-on-done; assertive only for errors; **never per-token** |
| **1.4.1** Use of Color | in-flight/done/failed indicators | text + shape for every state; no color-only status |
| **2.5.8** Target Size / **1** hit areas | chips, Send, Stop, feedback | ≥ 44×44px hit area; ~8px spacing |
| **2.4.11 / 2.4.13** Focus | all controls; response region | visible focus; focus moves to completed answer |
| Reduced-motion (2.3.3 pattern) | token stream, caret, dots | `prefers-reduced-motion` gate in CSS + JS; content still streams |
| **1.4.3** Contrast | unsure/error/citations, both themes | ≥ 4.5:1 / 3:1 verified light **and** dark |

---

## 7. Copy deck (single source of truth)

All user-facing strings live here (server-rendered `copy` context or a `copy.py` constants module), **not** inline in templates — so Content/Legal revise voice without a template diff, and tests assert against these keys.

```python
# assistant/copy.py  (illustrative)
EMPTY = {
    "heading": "Ask about your VA benefits.",
    "subheading": "I can explain letters, point to evidence, and walk you through next steps.",
    "chips": [
        {"text": "Explain my decision letter in plain language"},
        {"text": "What evidence strengthens a PTSD claim?"},
        {"text": "How do I file a Supplemental Claim?"},
        {"text": "Help me draft a personal statement"},
    ],
    "expectation": "I can be wrong. I'll tell you when I'm unsure, and I'll show where answers come from.",
}
STATUS = {
    "thinking": "Assistant is thinking.",
    "complete": "Response complete.",
    "stopped":  "Response stopped.",
    "offline":  "You're offline. I'll send this when you reconnect.",
    "online":   "You're back online.",
}
DISCLAIMER = "Guidance only — not legal advice or an official VA decision."
UNSURE = "I'm not fully sure about this one. VA rules here are specific and I don't want to steer you wrong. Here's what I'd check:"
ERRORS = {  # keyed by public_code; message is what the veteran sees
    "stream_interrupted": {"message": "Something interrupted my answer — that's on me, not you. Want me to try again?", "action": "Try again"},
    "timeout":            {"message": "This is taking longer than it should. You can wait a moment or try again.",       "action": "Keep waiting"},
    "rate_limited":       {"message": "A lot of people are asking right now. Give it a few seconds and try again.",       "action": "Try again"},
    "consent_required":   {"message": "Before I can help with this, I'll need your OK to use AI on your documents.",      "action": "Review AI consent"},
    "declined":           {"message": "I can't help with that one, but I can point you to a VSO who can.",                "action": "Find a VSO"},
    "generic":            {"message": "Something went wrong on my end. Let's try that again.",                            "action": "Try again"},
}
```

**Voice guardrails:** plain language (aim ≤ 8th-grade reading level), no VA/legal jargon in status/error copy, no blame, no exclamation-point urgency. Warm but not saccharine. These are veterans mid-claim — respect the stakes by being calm.

---

## 8. Implementation checklist (acceptance criteria)

Ship-gates. A PR touching the assistant surface should be able to check each box.

**Empty state (§1)**
- [ ] First-run shows heading + subheading + 3–4 starter chips + expectation line.
- [ ] Chips are real `<button>`s, ≥44px, keyboard-operable; tapping fills composer *and* submits (visible user bubble).
- [ ] Chips are first-run only; empty thread later re-shows the launcher (never blank, never an error).
- [ ] Chip/heading/expectation copy comes from the copy deck, not the template.

**Send + optimistic (§2)**
- [ ] Desktop Enter-sends w/ Shift+Enter newline + preference toggle; mobile Return = newline, Send button only.
- [ ] User turn renders optimistically with a client id; composer clears but text is retained for recovery.
- [ ] Send is disabled (dimmed + `aria-disabled`, not color-only) until the composer holds non-whitespace content.
- [ ] Composer inputs are ≥16px; textarea auto-grows; paste never blocked.
- [ ] Offline shows the persistent banner + queue-and-flush on reconnect.

**Streaming (§3)**
- [ ] Tokens stream via SSE `StreamingHttpResponse`; `X-Accel-Buffering: no` set; proxy buffering off.
- [ ] Streaming goes through a new gateway `stream()` (not `complete_structured()`); consent checked before open.
- [ ] Visible, focusable **Stop generating** while streaming; stop aborts client + server stream; Escape also stops.
- [ ] `queued → streaming → done` and `→ stopped` / `→ failed` all render distinct **text/shape** states.
- [ ] `prefers-reduced-motion` removes caret blink, token fade, thinking-dots — **content still streams**.
- [ ] Partial answer survives `stopped` and page reload.

**Uncertainty & errors (§4)**
- [ ] "Unsure" answers render the calm honesty treatment (not an error) with a verify link.
- [ ] Source citations render under `done` when the answer used scraped content.
- [ ] Persistent "Guidance only…" disclaimer under composer.
- [ ] Every error path maps to a calm, blame-free, coded string with a one-tap recovery; **prompt is restored**.
- [ ] Raw exceptions/stack traces never reach the client; only `public_code` crosses the wire.

**PHI / sensitive data (§5)**
- [ ] No prompt/answer/delta text in any analytics or telemetry payload (test-asserted).
- [ ] No prompt/answer/delta in logs; log fields limited to `turn_id`/`user_id`/`latency_ms`/`token_count`/`public_code`.
- [ ] No content in URLs/query strings; POST body only.
- [ ] Sentry stays `send_default_pii=False`; only `public_code` tagged, never the prompt.
- [ ] Dual-check consent enforced (view + gateway path); `AIConsentError` non-retryable → calm recovery.
- [ ] `scripts/check_security_invariants.py` extended to flag prompt/delta logging in the new files.

**Accessibility spine (§6)**
- [ ] One polite `role="status"` region + one assertive `role="alert"` region; reused, not ad-hoc per component.
- [ ] Streaming does **not** re-announce per token; single "Response complete." on `done`; focus moves to the answer.
- [ ] Focus lands sensibly on every exit: answer region on `done`, Continue/Ask-again on `stopped`, Try again on `failed` (never the removed Stop button).
- [ ] Errors announced assertively once; offline/online announced on the edge.
- [ ] Response region labeled + focusable; citations a real link list; feedback controls real labeled buttons.
- [ ] Every state readable without color; contrast ≥4.5:1 / 3:1 verified in light **and** dark.
- [ ] axe + keyboard-only pass on the assistant page; screen-reader smoke test of a full streamed turn.

---

## 9. Test hooks

Mirror the repo's existing tripwire style (`tests/test_regression_tripwires.py`) so these become CI gates, not aspirations:

- **Telemetry/no-PHI tripwire:** run a full turn against a fake gateway; assert the analytics + log sinks contain zero substrings of the prompt/answer. (Extends `security-invariants.md` §3.)
- **State-machine test:** assert SSE emits `open → delta* → done`, and that a mid-stream `GatewayError` emits `error` with a mapped `public_code` and **no** raw message.
- **Prompt-preservation test:** on a simulated `failed`/`stopped`, assert the composed prompt is returned to the client for restore.
- **Consent test:** revoking consent between view and gateway raises non-retryable `AIConsentError` → `consent_required` public code (reuses ADR-002 fixtures).
- **A11y assertions:** template/DOM tests that the response region carries `aria-busy` during stream and flips on `done`; that error uses `role="alert"`; that status is announced once, not per delta.
- **Reduced-motion:** with `prefers-reduced-motion: reduce`, assert caret/fade classes are absent while deltas still render.

---

## Sources & cross-refs

- Platform standard: `bas-platform/docs/design-principles.md` — §3.1 (send/optimistic), §3.4 (empty & error), §4 (a11y spine), §5 (per-app mapping: Navigator → PHI-as-CIT).
- Platform invariants: `bas-platform/INVARIANTS.md`; this repo's `docs/security-invariants.md`, `docs/PHI_DATA_FLOW.md`, `docs/adr/002-ai-consent-model.md`.
- Stack references: `agents/ai_gateway.py` (Anthropic gateway, `Result` contract), `templates/base.html` (HTMX 1.9.10, existing live-region), Django `StreamingHttpResponse` for SSE.
- WCAG 2.2: SC 4.1.3, 1.4.1, 1.4.3, 2.4.11, 2.4.13, 2.5.8, and the reduced-motion expectation (2.3.3 pattern). Anthropic streaming API (`messages.stream()`).
