/*
 * Accessibility contract tests for static/js/assistant.js (docs/ux §6.1).
 *
 * These assert the DOM state a screen-reader user actually experiences. The
 * central one — "the polite region is written once on completion, never per
 * token" — is recorded with a MutationObserver over the live region, because
 * counting announce() calls would stay green on exactly the refactor that
 * breaks it (a per-delta `statusLive.textContent = …` machine-guns the reader).
 *
 * Run: node --test tests/js/    (npm run test:js)
 */

import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const STATUS = { thinking: "Thinking…", complete: "Response complete", stopped: "Stopped" };
const ERRORS = {
  generic: { message: "Something went wrong.", action: "Try again" },
  stream_interrupted: { message: "The connection dropped.", action: "Retry" },
  rate_limited: { message: "Too many requests.", action: "Wait and retry" },
};

const PAGE = `<!doctype html><html><body>
  <div id="assistant-app" data-stream-url="/agents/stream/" data-stop-url="/agents/stop/">
    <div id="assistant-status" role="status" aria-live="polite" aria-atomic="true"></div>
    <div id="assistant-error-live" role="alert" aria-live="assertive"></div>
    <div id="assistant-thread"></div>
    <form id="composer-form">
      <input type="hidden" name="csrfmiddlewaretoken" value="tok">
      <textarea id="composer-input" name="prompt"></textarea>
      <button id="send-btn" type="submit" disabled aria-disabled="true">Send</button>
      <button id="stop-btn" type="button" hidden>Stop generating</button>
    </form>
  </div>
  <script id="assistant-status-copy" type="application/json">${JSON.stringify(STATUS)}</script>
  <script id="assistant-errors-copy" type="application/json">${JSON.stringify(ERRORS)}</script>
</body></html>`;

/**
 * An SSE body whose frames are released under test control.
 *
 * It honours the AbortSignal the client passes to fetch: real fetch rejects an
 * in-flight read with AbortError when the stream is aborted, and the client
 * relies on that (a stub that keeps reading after stop() falls through to the
 * "stream closed without done" path and reports a spurious error).
 */
function scriptedStream() {
  const queue = [];
  let notify = null;
  let closed = false;
  let signal = null;
  const encoder = new TextEncoder();
  const wake = () => {
    if (notify) { const n = notify; notify = null; n(); }
  };

  return {
    useSignal(s) {
      signal = s;
      if (s) s.addEventListener("abort", wake);
    },
    push(event, data) {
      queue.push(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      wake();
    },
    close() {
      closed = true;
      wake();
    },
    body: {
      getReader() {
        return {
          async read() {
            while (queue.length === 0 && !closed && !(signal && signal.aborted)) {
              await new Promise((r) => (notify = r));
            }
            if (signal && signal.aborted) {
              const err = new Error("aborted");
              err.name = "AbortError";
              throw err;
            }
            if (queue.length) return { value: queue.shift(), done: false };
            return { value: undefined, done: true };
          },
        };
      },
    },
  };
}

function setup() {
  // No pretendToBeVisual: it starts a requestAnimationFrame loop that keeps the
  // Node event loop alive and hangs the test run. Nothing here needs rAF.
  const dom = new JSDOM(PAGE, { url: "https://bn.example/agents/assistant/" });
  const { window } = dom;

  // jsdom implements neither of these; both are incidental to the contract.
  window.Element.prototype.scrollIntoView = function () {};
  window.HTMLFormElement.prototype.requestSubmit = function () {
    this.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  };

  const stream = scriptedStream();
  const fetchCalls = [];
  window.fetch = async (url, opts) => {
    fetchCalls.push({ url, opts });
    if (url === "/agents/stop/") return { ok: true };
    stream.useSignal(opts && opts.signal);
    return { ok: true, body: stream.body };
  };
  // The client calls bare `fetch` / `AbortController`, resolved from the module
  // scope — which under CommonJS is Node's global, not the jsdom window.
  globalThis.fetch = window.fetch;

  // The module is UMD; require it and init against this document explicitly.
  delete require.cache[require.resolve("../../static/js/assistant.js")];
  const prevSelf = globalThis.self;
  const prevDocument = globalThis.document;
  globalThis.self = window;
  globalThis.document = undefined; // suppress auto-boot; we init explicitly
  const mod = require("../../static/js/assistant.js");
  globalThis.self = prevSelf;
  globalThis.document = prevDocument;

  const root = window.document.getElementById("assistant-app");
  const api = mod.initAssistant(root);

  const statusLive = window.document.getElementById("assistant-status");
  const errorLive = window.document.getElementById("assistant-error-live");

  // Record every value the polite region ever holds, in order.
  const announcements = [];
  new window.MutationObserver(() => {
    const t = statusLive.textContent;
    if (t && announcements[announcements.length - 1] !== t) announcements.push(t);
  }).observe(statusLive, { childList: true, characterData: true, subtree: true });

  const tick = () => new Promise((r) => setTimeout(r, 0));

  // Draining the client's read loop takes an indeterminate number of microtask
  // hops, so wait on the observable condition rather than a fixed tick count.
  async function waitFor(predicate, what = "condition", timeoutMs = 1000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      if (predicate()) return;
      await tick();
    }
    throw new Error(`timed out waiting for ${what}`);
  }

  return {
    window, doc: window.document, api, stream, dom,
    statusLive, errorLive, announcements, fetchCalls, tick, waitFor,
    close: () => dom.window.close(),
  };
}

/*
 * Returns the in-flight submit promise WRAPPED in an object.
 *
 * Returning it bare would deadlock: `await startStream(t)` on an async function
 * that returns a promise adopts that promise, so the test would wait for the
 * stream to finish before it could push the frame that finishes it.
 */
async function startStream(t) {
  const { api, stream, waitFor } = t;
  const p = api.submit("How do I file a claim?", {});
  p.catch(() => {}); // asserted via DOM; never let a rejection go unhandled
  await waitFor(() => t.fetchCalls.length > 0, "the stream request");
  stream.push("open", { turn_id: 42 });
  return { p };
}

test("streaming announces once on completion — never per token", async () => {
  const t = setup();
  const { p } = await startStream(t);

  // 200 deltas: a per-token announce would produce ~200 announcements.
  for (let i = 0; i < 200; i++) {
    t.stream.push("delta", { t: `word${i} ` });
  }
  const answerEl0 = () => t.doc.querySelector(".assistant-answer");
  await t.waitFor(() => /word199/.test(answerEl0().textContent), "all 200 deltas to render");

  const duringStream = [...t.announcements];
  assert.deepEqual(
    duringStream,
    [STATUS.thinking],
    `the polite region must hold only the initial "thinking" state while tokens stream; got ${JSON.stringify(duringStream)}`
  );

  const answer = t.doc.querySelector(".assistant-answer");
  assert.equal(answer.getAttribute("aria-busy"), "true", "the region must stay aria-busy while filling");
  assert.match(answer.textContent, /word199/, "deltas must actually be rendering (anti-vacuity)");

  t.stream.push("done", {});
  await p;
  await t.waitFor(() => t.announcements.length >= 2, "the completion announcement");

  assert.deepEqual(
    t.announcements,
    [STATUS.thinking, STATUS.complete],
    "exactly one completion announcement, after exactly one thinking announcement"
  );
  assert.equal(answer.getAttribute("aria-busy"), "false", "aria-busy must clear on done");
});

test("focus lands on the finished answer when the stream completes", async () => {
  const t = setup();
  const { p } = await startStream(t);

  assert.equal(
    t.doc.activeElement.id,
    "stop-btn",
    "while busy, focus belongs on Stop generating"
  );

  t.stream.push("delta", { t: "hello" });
  await t.waitFor(() => /hello/.test(t.doc.querySelector(".assistant-answer").textContent), "the delta");
  t.stream.push("done", {});
  await p;

  const answer = t.doc.querySelector(".assistant-answer");
  assert.equal(
    t.doc.activeElement,
    answer,
    "on done, focus must move to the completed answer — the Stop button it was on is now hidden"
  );
});

test("an error announces assertively AND moves focus to the recovery control", async () => {
  const t = setup();
  const { p } = await startStream(t);
  t.stream.push("delta", { t: "partial" });
  await t.waitFor(() => /partial/.test(t.doc.querySelector(".assistant-answer").textContent), "the delta");

  t.stream.push("error", { code: "rate_limited" });
  await p;
  await t.waitFor(() => t.errorLive.textContent !== "", "the assertive announcement");

  assert.equal(
    t.errorLive.textContent,
    ERRORS.rate_limited.message,
    "errors route to the assertive region"
  );
  assert.ok(
    !t.announcements.includes(ERRORS.rate_limited.message),
    "an error must not also be announced politely (double-read)"
  );

  const focused = t.doc.activeElement;
  assert.equal(focused.tagName, "BUTTON", "focus must land on a control, not be stranded");
  assert.equal(
    focused.textContent,
    ERRORS.rate_limited.action,
    "focus must move to the recovery control, never the removed Stop button"
  );
  assert.notEqual(focused.id, "stop-btn", "the Stop button is hidden — focus there is a trap");
});

test("stopping announces once and keeps the partial answer, with focus on it", async () => {
  const t = setup();
  const { p } = await startStream(t);
  t.stream.push("delta", { t: "partial answer" });
  await t.waitFor(() => /partial answer/.test(t.doc.querySelector(".assistant-answer").textContent), "the delta");

  t.api.stop();
  await p;
  await t.waitFor(() => t.announcements.length >= 2, "the stopped announcement");

  assert.deepEqual(
    t.announcements,
    [STATUS.thinking, STATUS.stopped],
    "stopping announces exactly once, politely — a user-initiated stop is not an error"
  );
  assert.equal(t.errorLive.textContent, "", "a deliberate stop must not fire the alert region");

  const answer = t.doc.querySelector(".assistant-answer");
  assert.match(answer.textContent, /partial answer/, "the partial answer is preserved");
  assert.equal(t.doc.activeElement, answer, "focus moves to the preserved partial");
});

test("the prompt is restored after an error so it is never retyped", async () => {
  const t = setup();
  const { p } = await startStream(t);
  t.stream.push("error", { code: "generic" });
  await p;
  await t.waitFor(() => t.errorLive.textContent !== "", "the error to render");

  assert.equal(
    t.doc.getElementById("composer-input").value,
    "How do I file a claim?",
    "the prompt must be restored into the composer (docs/ux §4.2)"
  );
});
