/*
 * Mobile navigation toggle for the header in templates/base.html.
 *
 * Extracted to a static file rather than an inline <script>, for the same
 * reason as static/js/assistant.js: the page carries no inline script, so it
 * keeps working if 'unsafe-inline' is dropped from CSP_SCRIPT_SRC.
 *
 * The accessibility contract this file must uphold:
 *   - The toggle is a real <button> whose aria-expanded always reflects the
 *     panel's actual visibility, with aria-controls pointing at the panel.
 *   - Escape closes the panel AND returns focus to the toggle. Closing a menu
 *     while focus sits on a link inside it strands keyboard users on an
 *     element that is now display:none.
 *   - Crossing up to the desktop breakpoint collapses the panel, so
 *     aria-expanded never advertises "true" for a panel the CSS has hidden.
 *   - The button's accessible name flips between "Open"/"Close main menu";
 *     a toggle whose name never changes gives no feedback that it worked.
 *
 * tests/js/nav.a11y.test.mjs asserts all of the above against the DOM.
 */
(function (global, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    global.BNNav = factory();
  }
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  // Keep in step with the `xl:` breakpoint used on the header in base.html.
  // Below it the horizontal bar is display:none and this panel is the only nav.
  var DESKTOP_QUERY = "(min-width: 1280px)";

  function initNav(root) {
    if (!root) return null;
    var doc = root.ownerDocument;
    var win = doc.defaultView;
    var toggle = root.querySelector("[data-nav-toggle]");
    var panel = root.querySelector("[data-nav-panel]");
    if (!toggle || !panel) return null;

    var openIcon = toggle.querySelector("[data-nav-icon-open]");
    var closeIcon = toggle.querySelector("[data-nav-icon-close]");
    var label = toggle.querySelector("[data-nav-label]");
    var openLabel = toggle.getAttribute("data-label-open") || "Open main menu";
    var closeLabel = toggle.getAttribute("data-label-close") || "Close main menu";

    function isOpen() {
      return toggle.getAttribute("aria-expanded") === "true";
    }

    function setOpen(open) {
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      panel.classList.toggle("hidden", !open);
      if (openIcon) openIcon.classList.toggle("hidden", open);
      if (closeIcon) closeIcon.classList.toggle("hidden", !open);
      if (label) label.textContent = open ? closeLabel : openLabel;
    }

    function close(returnFocus) {
      if (!isOpen()) return;
      setOpen(false);
      // Only pull focus back for dismissals the user drove from the keyboard;
      // stealing it on a resize or a link click would be a surprise.
      if (returnFocus && typeof toggle.focus === "function") toggle.focus();
    }

    toggle.addEventListener("click", function () {
      setOpen(!isOpen());
    });

    doc.addEventListener("keydown", function (event) {
      if (event.key === "Escape") close(true);
    });

    // Collapse on navigation so the panel is never restored open by a
    // back/forward cache hit.
    panel.addEventListener("click", function (event) {
      if (event.target && event.target.closest && event.target.closest("a")) {
        close(false);
      }
    });

    var mql = win && win.matchMedia ? win.matchMedia(DESKTOP_QUERY) : null;
    if (mql) {
      var onBreakpoint = function (event) {
        if (event.matches) close(false);
      };
      if (mql.addEventListener) mql.addEventListener("change", onBreakpoint);
      else if (mql.addListener) mql.addListener(onBreakpoint);
    }

    // Normalise whatever the server rendered so icons, label and
    // aria-expanded agree before the first interaction.
    setOpen(false);

    return { isOpen: isOpen, setOpen: setOpen, close: close };
  }

  function autoInit(doc) {
    if (!doc) return null;
    return initNav(doc.querySelector("[data-nav-root]"));
  }

  if (typeof document !== "undefined") {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", function () {
        autoInit(document);
      });
    } else {
      autoInit(document);
    }
  }

  return { initNav: initNav, autoInit: autoInit };
});
