## Summary
<!-- what changed and why -->

## Design & accessibility checklist
<!-- BAS UX/a11y standard — canonical: bas-platform/docs/design-principles.md -->
- [ ] Back/escape works on every new screen; browser-back preserves place (web)
- [ ] Inputs: right keyboard, autofill tokens, paste allowed, 16px+ font, validate on blur/submit
- [ ] Every async action has loading / empty / error / success states
- [ ] Touch targets ≥ 44/48px hit area; primary action in thumb zone (mobile)
- [ ] Animations < 300ms AND have a prefers-reduced-motion path
- [ ] Dynamic status (streaming / send / connectivity) is text/shape, not color/animation alone
- [ ] Status routed through the shared aria-live utility; failures=alert, rest=polite, debounced
- [ ] Contrast ≥ 4.5:1 text / 3:1 large & UI — verified in BOTH light and dark
- [ ] Visible focus everywhere; no cognitive auth puzzle (SC 3.3.8)
- [ ] Empty states coach (starter-prompt chips on first run); errors blame-free + recoverable, prompt preserved
- [ ] Streaming responses optimistic + interruptible; explicit in-flight → done → failed states
- [ ] No telemetry on sensitive/PHI content (platform invariant)

## Testing
<!-- how you verified -->
