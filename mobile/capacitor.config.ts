import type { CapacitorConfig } from '@capacitor/cli';

// iOS TestFlight wrapper config — same pattern as Access Atlas
// (access-directory/capacitor.config.ts): a thin Capacitor/WKWebView shell
// that loads the HOSTED Django app at runtime. The "app" is the live site;
// server-side deploys reach testers with no rebuild. Only native-shell
// changes (this file, icons, splash, plugins) need a new TestFlight build.
//
// Self-contained under mobile/ because the repo root is a Django project,
// not an npm package.
const config: CapacitorConfig = {
  appId: 'com.beauaccess.benefitsnavigator',
  appName: 'Benefits Navigator',
  // Offline fallback assets only (mobile/www). NOT the app itself.
  webDir: 'www',
  server: {
    // The PRIMARY domain on the DO app (despite the app being named
    // "benefits-navigator-staging", it serves the real site — TRACKER §2
    // documents this trap). Do NOT point this at the ondigitalocean.app URL:
    // the Keycloak client registers only this domain's OIDC callback, so
    // login CANNOT complete there — build 1.0 (1) shipped that mistake and
    // was superseded same-day by 1.0 (2) on this URL. The URL is baked into
    // the binary; moving it requires a new build, a web deploy won't do it.
    url: 'https://vabenefitsnavigator.org',
    // Never allow cleartext — BN handles sensitive claims data.
    cleartext: false,
    // Keep the Keycloak IdP IN the webview or the OIDC redirect gets kicked
    // out to Safari and the login round-trip breaks. Staging already runs on
    // the neutral issuer (KEYCLOAK_ISSUER=https://id.beauaccesssolutions.com/
    // realms/bas, verified in the DO app spec 2026-07-18) — the host the
    // other three BAS apps are currently migrating TO, so BN starts correct.
    // Everything NOT listed here opens in Safari (desired for external links,
    // e.g. va.gov).
    // www serves the site DIRECTLY (no redirect to apex — verified 2026-07-18),
    // so any absolute www URL or server-side redirect mid-flow would kick the
    // webview to Safari without this entry. Proper fix is also a server-side
    // www→apex canonical redirect (tracked separately) — cookies are scoped
    // per-host, so an in-app hop onto www can still drop the session.
    allowNavigation: ['id.beauaccesssolutions.com', 'www.vabenefitsnavigator.org'],
  },
  ios: {
    // Match the web app's white surface so first paint isn't a jarring flash.
    backgroundColor: '#ffffff',
    contentInset: 'automatic',
  },
};

export default config;
