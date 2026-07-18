# Benefits Navigator — iOS wrapper (Capacitor)

A thin Capacitor/WKWebView shell around the **hosted** Django app, same pattern
as the Access Atlas and KindredAccess TestFlight apps (see
`bas-platform/docs/mobile-and-testflight.md`). The app loads
`capacitor.config.ts → server.url` at runtime; `www/` is only a tiny offline
fallback page.

**Consequence:** server-side deploys reach testers with no rebuild (force-quit
to clear the WKWebView cache). A new TestFlight build is only needed when the
*native shell* changes: this config, icons, splash, plugins, or a version bump.

## Current state (2026-07-18)

- Capacitor 8 (SPM, no CocoaPods), iOS platform added, unsigned simulator
  build passes.
- `server.url` points at **staging** — deliberately. BN has no prod deployment
  yet, and while it's Candidate under ADR-005, internal testers should hit
  staging. When prod exists: edit `server.url`, `npx cap sync ios`, new build.
- `allowNavigation` already targets the neutral Keycloak host
  (`id.beauaccesssolutions.com`) — staging's live issuer — so in-app OIDC
  login stays in the webview. This is the config the other three apps are
  currently rebuilding to fix; BN starts correct.
- `ios/` is committed (its `.gitignore` keeps build products out).

## Build & run

```bash
# Machine quirks (this Mac): xcodebuild needs Xcode, not the bare CLT
export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer

npm install
npx cap sync ios
npx cap open ios     # → Xcode → pick a simulator → Run
```

## Still needed for TestFlight

- App Store Connect app record (`com.beauaccess.benefitsnavigator`), signing.
- Real app icon + splash (currently Capacitor defaults).
- **External TestFlight warning:** a bare webview wrapper is rejected under
  App Store Guideline 4.2 (see the Access Atlas experience). Internal
  TestFlight (≤100 testers) is fine. Also: BN's Candidate status under
  ADR-005 (sensitive claims data) should be resolved before any external
  distribution.
