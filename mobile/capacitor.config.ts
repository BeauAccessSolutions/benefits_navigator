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
    // ⚠️ STAGING, deliberately. BN has NO prod deployment (verified
    // 2026-07-18: the DO account's only BN app is benefits-navigator-staging,
    // and no custom domain resolves). While BN is Candidate under ADR-005
    // (bas-platform/docs/adr/005), internal TestFlight testers SHOULD hit
    // staging. When prod exists: point this at it and cut a new build —
    // the URL is baked into the binary, a web deploy won't move it.
    url: 'https://benefits-navigator-staging-3o4rq.ondigitalocean.app',
    // Never allow cleartext — BN handles sensitive claims data.
    cleartext: false,
    // Keep the Keycloak IdP IN the webview or the OIDC redirect gets kicked
    // out to Safari and the login round-trip breaks. Staging already runs on
    // the neutral issuer (KEYCLOAK_ISSUER=https://id.beauaccesssolutions.com/
    // realms/bas, verified in the DO app spec 2026-07-18) — the host the
    // other three BAS apps are currently migrating TO, so BN starts correct.
    // Everything NOT listed here opens in Safari (desired for external links,
    // e.g. va.gov).
    allowNavigation: ['id.beauaccesssolutions.com'],
  },
  ios: {
    // Match the web app's white surface so first paint isn't a jarring flash.
    backgroundColor: '#ffffff',
    contentInset: 'automatic',
  },
};

export default config;
