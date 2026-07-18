/*
 * Assistant composer + streaming client.
 *
 * Extracted from templates/agents/assistant.html so it can be unit-tested and
 * so the page carries no inline <script> (one less reason to need
 * 'unsafe-inline' in the CSP).
 *
 * The accessibility contract this file must uphold (docs/ux §6.1):
 *   - The polite live region is written ONCE per state transition — never per
 *     token. Re-announcing a streaming region on every delta machine-guns a
 *     screen reader into uselessness.
 *   - The streaming region stays aria-busy="true" while it fills.
 *   - Every state transition moves focus somewhere sensible: the Stop button
 *     while busy, the finished answer on done, the recovery control on error.
 *     An announcement is not focus management — firing an assertive error while
 *     leaving focus on the now-removed Stop button strands keyboard/AT users.
 *
 * tests/js/assistant.a11y.test.mjs asserts all of the above against the DOM.
 */
(function (global, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    global.BNAssistant = factory();
  }
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  function initAssistant(root) {
    const doc = root.ownerDocument;
    const win = doc.defaultView;

    // matchMedia is absent in non-browser DOMs; absent means "no preference",
    // which is the same answer a browser gives when the query doesn't match.
    const media = (q) => (typeof win.matchMedia === "function" ? win.matchMedia(q).matches : false);

    const STATUS = JSON.parse(doc.getElementById("assistant-status-copy").textContent);
    const ERRORS = JSON.parse(doc.getElementById("assistant-errors-copy").textContent);

    const form = doc.getElementById("composer-form");
    const input = doc.getElementById("composer-input");
    const sendBtn = doc.getElementById("send-btn");
    const stopBtn = doc.getElementById("stop-btn");
    const thread = doc.getElementById("assistant-thread");
    const emptyState = doc.getElementById("assistant-empty");
    const statusLive = doc.getElementById("assistant-status");
    const errorLive = doc.getElementById("assistant-error-live");
    const csrf = form.querySelector("[name=csrfmiddlewaretoken]").value;
    // Endpoints arrive as data-* so this file needs no template rendering.
    const streamUrl = root.dataset.streamUrl;
    const stopUrl = root.dataset.stopUrl;

    let controller = null; // AbortController for the in-flight stream
    let lastPrompt = ""; // preserved for retry / failure restore
    let answerEl = null; // current assistant answer container
    let buffer = ""; // accumulated partial (survives 'stopped')
    let currentTurnId = null; // id from the 'open' event; used to stop server-side

    function announce(region, msg) {
      region.textContent = "";
      region.textContent = msg;
    }

    function setComposerBusy(busy) {
      sendBtn.hidden = busy;
      stopBtn.hidden = !busy;
      input.disabled = busy;
      if (busy) {
        stopBtn.focus();
      }
    }

    function updateSendEnabled() {
      const has = input.value.trim().length > 0;
      sendBtn.disabled = !has;
      sendBtn.setAttribute("aria-disabled", String(!has));
    }

    function autogrow() {
      input.style.height = "auto";
      input.style.height = Math.min(input.scrollHeight, 160) + "px";
    }

    function addUserBubble(text) {
      if (emptyState) {
        emptyState.remove();
      }
      const el = doc.createElement("div");
      el.className = "ml-auto max-w-[85%] rounded-2xl bg-blue-600 text-white px-4 py-2";
      el.textContent = text;
      thread.appendChild(el);
    }

    function addAssistantContainer() {
      const wrap = doc.createElement("div");
      wrap.className = "mr-auto max-w-[90%] rounded-2xl bg-white border border-gray-200 px-4 py-3";
      wrap.innerHTML =
        '<div class="assistant-answer text-gray-900" tabindex="-1" aria-label="Assistant response" aria-busy="true">' +
        '<span class="thinking-dots text-gray-500">Thinking</span>' +
        '<span class="assistant-caret" aria-hidden="true"></span></div>';
      thread.appendChild(wrap);
      answerEl = wrap.querySelector(".assistant-answer");
      return answerEl;
    }

    function firstToken() {
      // Clear the "Thinking" placeholder on first delta, keep the caret.
      const dots = answerEl.querySelector(".thinking-dots");
      if (dots) {
        dots.remove();
      }
      answerEl.classList.add("is-streaming");
    }

    function appendDelta(t) {
      const caret = answerEl.querySelector(".assistant-caret");
      const node = doc.createTextNode(t);
      answerEl.insertBefore(node, caret);
      if (typeof answerEl.scrollIntoView === "function") {
        answerEl.scrollIntoView({ block: "nearest" });
      }
    }

    function finishStreaming(kind) {
      // kind: 'done' | 'stopped'
      answerEl.classList.remove("is-streaming");
      answerEl.setAttribute("aria-busy", "false");
      const caret = answerEl.querySelector(".assistant-caret");
      if (caret) {
        caret.remove();
      }
      setComposerBusy(false);

      if (kind === "stopped") {
        const label = doc.createElement("div");
        label.className = "mt-2 text-sm text-gray-500";
        label.textContent = "Stopped.";
        answerEl.after(label);
        announce(statusLive, STATUS.stopped);
      } else {
        announce(statusLive, STATUS.complete);
      }
      answerEl.focus(); // land the reader at the start of the completed answer
      input.value = "";
      autogrow();
      updateSendEnabled();
    }

    function showError(code) {
      const info = ERRORS[code] || ERRORS.generic;
      setComposerBusy(false);
      if (answerEl) {
        const caret = answerEl.querySelector(".assistant-caret");
        if (caret) {
          caret.remove();
        }
        // Replace any half-rendered ghost text with the calm error card.
        const wrap = answerEl.closest("div");
        wrap.className = "mr-auto max-w-[90%] rounded-2xl bg-amber-50 border border-amber-300 px-4 py-3";
        wrap.innerHTML = "";
        const msg = doc.createElement("p");
        msg.className = "text-amber-900";
        msg.textContent = info.message;
        const action = doc.createElement("button");
        action.type = "button";
        action.className =
          "mt-3 min-h-[44px] rounded-xl bg-amber-700 px-4 text-white font-medium " +
          "hover:bg-amber-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-amber-600";
        action.textContent = info.action;
        action.addEventListener("click", () => submit(lastPrompt, { retry: true }));
        wrap.append(msg, action);
        wrap.setAttribute("tabindex", "-1");
        answerEl = null;
        action.focus(); // focus the recovery control, never the removed Stop button
      }
      // The prompt is sacred: restore it so the veteran never retypes (docs/ux §4.2).
      input.value = lastPrompt;
      autogrow();
      updateSendEnabled();
      announce(errorLive, info.message);
    }

    async function submit(text, opts) {
      opts = opts || {};
      lastPrompt = text;
      currentTurnId = null;
      if (!opts.retry) {
        addUserBubble(text);
      }
      buffer = "";
      addAssistantContainer();
      announce(statusLive, STATUS.thinking);
      input.value = "";
      autogrow();
      updateSendEnabled();
      setComposerBusy(true);

      controller = new AbortController();
      try {
        const body = new URLSearchParams();
        body.set("prompt", text);
        const resp = await fetch(streamUrl, {
          method: "POST",
          headers: { "X-CSRFToken": csrf, "Content-Type": "application/x-www-form-urlencoded" },
          body: body.toString(),
          signal: controller.signal,
        });
        if (!resp.ok || !resp.body) {
          showError("generic");
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let sse = "";
        let started = false;
        while (true) {
          const { value, done } = await reader.read();
          if (done) {
            break;
          }
          sse += decoder.decode(value, { stream: true });
          const frames = sse.split("\n\n");
          sse = frames.pop(); // keep incomplete trailing frame
          for (const frame of frames) {
            const evLine = frame.match(/^event: (.+)$/m);
            const dataLine = frame.match(/^data: (.+)$/m);
            if (!evLine) {
              continue;
            }
            const ev = evLine[1];
            const data = dataLine ? JSON.parse(dataLine[1]) : {};
            if (ev === "open") {
              currentTurnId = data.turn_id; // enables server-side stop
            } else if (ev === "delta") {
              if (!started) {
                firstToken();
                started = true;
              }
              buffer += data.t;
              appendDelta(data.t);
            } else if (ev === "done") {
              finishStreaming("done");
              return;
            } else if (ev === "stopped") {
              // Server acknowledged a stop (partial persisted). Usually the client
              // has already aborted and transitioned; this covers the race where
              // the server frame arrives first.
              if (answerEl) {
                finishStreaming("stopped");
              }
              return;
            } else if (ev === "error") {
              showError(data.code);
              return;
            }
          }
        }
        // Stream closed without an explicit done → treat as interrupted.
        if (answerEl) {
          showError("stream_interrupted");
        }
      } catch (err) {
        if (err && err.name === "AbortError") {
          return;
        } // handled by stop()
        showError("stream_interrupted");
      }
    }

    function stop() {
      // Tell the server to close the Anthropic stream (stops token spend) and
      // persist the partial. Fire-and-forget: the UI transitions immediately and
      // must not wait on the network. keepalive lets it complete after we abort.
      if (currentTurnId != null) {
        const body = new URLSearchParams();
        body.set("turn_id", currentTurnId);
        fetch(stopUrl, {
          method: "POST",
          headers: { "X-CSRFToken": csrf, "Content-Type": "application/x-www-form-urlencoded" },
          body: body.toString(),
          keepalive: true,
        }).catch(() => {}); // best-effort; client-side stop still happens below
      }
      if (controller) {
        controller.abort();
      }
      if (answerEl) {
        finishStreaming("stopped");
      } // keep the partial
    }

    // ---- wiring ----
    input.addEventListener("input", () => {
      updateSendEnabled();
      autogrow();
    });

    // Desktop: Enter sends, Shift+Enter newline. Mobile keeps Return as newline
    // (coarse pointer / no hover ⇒ send button is the only send affordance).
    const isTouch = media("(pointer: coarse)");
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !isTouch) {
        e.preventDefault();
        if (input.value.trim()) {
          form.requestSubmit();
        }
      }
      if (e.key === "Escape" && !stopBtn.hidden) {
        stop();
      }
    });

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const text = input.value.trim();
      if (!text) {
        return;
      }
      submit(text, {});
    });

    stopBtn.addEventListener("click", stop);

    doc.querySelectorAll(".chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        input.value = btn.dataset.chipPrompt;
        updateSendEnabled();
        autogrow();
        form.requestSubmit(); // chip = fill + send, visible in the user bubble
      });
    });

    updateSendEnabled();

    return { submit, stop };
  }

  // Auto-init in a real page. `defer` means the DOM is parsed by the time this
  // runs, but guard readyState anyway so load order can't break the page.
  if (typeof document !== "undefined") {
    const boot = () => {
      const root = document.getElementById("assistant-app");
      if (root && !root.dataset.bnInit) {
        root.dataset.bnInit = "1";
        initAssistant(root);
      }
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", boot);
    } else {
      boot();
    }
  }

  return { initAssistant };
});
