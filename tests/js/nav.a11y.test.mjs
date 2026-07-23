/*
 * Accessibility contract tests for static/js/nav.js.
 *
 * The header nav collapses behind a hamburger below the xl breakpoint. These
 * assert the DOM state a keyboard and screen-reader user actually experiences:
 * that aria-expanded never disagrees with what is on screen, that the button's
 * accessible name reports the action, and — the one most easily regressed —
 * that Escape returns focus to the toggle instead of leaving it inside a panel
 * that just became display:none.
 *
 * Run: node --test tests/js/    (npm run test:js)
 */

import test from "node:test";
import assert from "node:assert/strict";
import { JSDOM } from "jsdom";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

const PAGE = `<!doctype html><html><body>
  <header data-nav-root>
    <nav class="hidden xl:block"><ul><li><a href="/claims/">Claims Assistant</a></li></ul></nav>
    <button type="button"
            aria-controls="mobile-menu"
            aria-expanded="false"
            data-nav-toggle
            data-label-open="Open main menu"
            data-label-close="Close main menu">
      <span class="sr-only" data-nav-label>Open main menu</span>
      <svg data-nav-icon-open></svg>
      <svg class="hidden" data-nav-icon-close></svg>
    </button>
    <nav id="mobile-menu" class="hidden xl:hidden" data-nav-panel>
      <ul>
        <li><a href="/claims/" id="first-link">Claims Assistant</a></li>
        <li><a href="/docs/">Documentation</a></li>
      </ul>
    </nav>
  </header>
</body></html>`;

/**
 * jsdom ships no window.matchMedia, and nav.js uses it to collapse the panel
 * when the viewport crosses up to desktop. Stub one we can drive by hand so
 * that path is actually exercised rather than silently skipped.
 */
function installMatchMedia(win) {
  const listeners = [];
  win.matchMedia = (query) => ({
    media: query,
    matches: false,
    addEventListener: (_type, fn) => listeners.push(fn),
    removeEventListener: (_type, fn) => {
      const i = listeners.indexOf(fn);
      if (i >= 0) listeners.splice(i, 1);
    },
  });
  return { crossToDesktop: () => listeners.forEach((fn) => fn({ matches: true })) };
}

function setup() {
  const dom = new JSDOM(PAGE, { url: "https://bn.example/" });
  const { window } = dom;
  const media = installMatchMedia(window);

  const prev = {
    window: global.window,
    document: global.document,
    self: global.self,
  };
  global.window = window;
  global.document = window.document;
  global.self = window;

  const mod = require("../../static/js/nav.js");
  const doc = window.document;
  const api = mod.initNav(doc.querySelector("[data-nav-root]"));

  global.window = prev.window;
  global.document = prev.document;
  global.self = prev.self;

  return {
    api,
    doc,
    media,
    toggle: doc.querySelector("[data-nav-toggle]"),
    panel: doc.querySelector("[data-nav-panel]"),
    label: doc.querySelector("[data-nav-label]"),
    openIcon: doc.querySelector("[data-nav-icon-open]"),
    closeIcon: doc.querySelector("[data-nav-icon-close]"),
    press: (key) => {
      const ev = new window.KeyboardEvent("keydown", { key, bubbles: true });
      doc.dispatchEvent(ev);
    },
  };
}

test("the panel starts collapsed and the toggle says so", () => {
  const t = setup();
  assert.equal(t.toggle.getAttribute("aria-expanded"), "false");
  assert.ok(t.panel.classList.contains("hidden"), "panel is hidden on load");
  assert.equal(t.toggle.getAttribute("aria-controls"), t.panel.id);
  assert.equal(t.label.textContent, "Open main menu");
});

test("clicking the toggle opens the panel and flips the accessible name", () => {
  const t = setup();
  t.toggle.click();

  assert.equal(t.toggle.getAttribute("aria-expanded"), "true");
  assert.ok(!t.panel.classList.contains("hidden"), "panel is visible");
  assert.equal(t.label.textContent, "Close main menu");
  // The icon swap is decorative, but a stuck hamburger next to an open panel
  // reads as "nothing happened".
  assert.ok(t.openIcon.classList.contains("hidden"), "hamburger icon hidden");
  assert.ok(!t.closeIcon.classList.contains("hidden"), "close icon shown");
});

test("clicking the toggle again collapses it", () => {
  const t = setup();
  t.toggle.click();
  t.toggle.click();

  assert.equal(t.toggle.getAttribute("aria-expanded"), "false");
  assert.ok(t.panel.classList.contains("hidden"));
  assert.equal(t.label.textContent, "Open main menu");
});

test("Escape closes the panel AND returns focus to the toggle", () => {
  const t = setup();
  t.toggle.click();
  t.doc.getElementById("first-link").focus();
  assert.equal(t.doc.activeElement.id, "first-link", "focus starts inside the panel");

  t.press("Escape");

  assert.equal(t.toggle.getAttribute("aria-expanded"), "false");
  assert.ok(t.panel.classList.contains("hidden"));
  // Without this, focus is left on a link inside a display:none panel.
  assert.equal(
    t.doc.activeElement,
    t.toggle,
    "focus returns to the toggle rather than being stranded in the closed panel",
  );
});

test("Escape on an already-closed panel does not steal focus", () => {
  const t = setup();
  const link = t.doc.getElementById("first-link");
  link.focus();

  t.press("Escape");

  assert.notEqual(t.doc.activeElement, t.toggle, "no focus grab when nothing was open");
});

test("following a link collapses the panel without grabbing focus", () => {
  const t = setup();
  t.toggle.click();
  const link = t.doc.getElementById("first-link");
  link.focus();

  link.click();

  assert.equal(t.toggle.getAttribute("aria-expanded"), "false");
  assert.ok(t.panel.classList.contains("hidden"));
  assert.notEqual(t.doc.activeElement, t.toggle, "focus is not yanked mid-navigation");
});

test("crossing up to the desktop breakpoint collapses the panel", () => {
  const t = setup();
  t.toggle.click();
  assert.equal(t.toggle.getAttribute("aria-expanded"), "true");

  t.media.crossToDesktop();

  // The desktop bar takes over and CSS hides this panel; aria-expanded must not
  // keep claiming an expanded panel that nobody can see.
  assert.equal(t.toggle.getAttribute("aria-expanded"), "false");
  assert.ok(t.panel.classList.contains("hidden"));
});
