"""
Copy deck for the streaming AI assistant surface.

Single source of truth for all user-facing strings on the assistant page, so
Content/Legal can revise voice without touching templates, and tests can assert
against these keys. See docs/ux/assistant-interactions.md §7.

NOTE: nothing here is PHI. User prompts/answers never live in this module.
"""

# First-run empty state (docs/ux §1) — chips demonstrate range.
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

# Dynamic-status announcements routed through the aria-live spine (docs/ux §6).
STATUS = {
    "thinking": "Assistant is thinking.",
    "complete": "Response complete.",
    "stopped": "Response stopped.",
    "offline": "You're offline. I'll send this when you reconnect.",
    "online": "You're back online.",
}

DISCLAIMER = "Guidance only — not legal advice or an official VA decision."

# Calm, blame-free error copy keyed by a public_code (docs/ux §4.2). The raw
# exception never reaches the client — only one of these codes crosses the wire.
ERRORS = {
    "stream_interrupted": {
        "message": "Something interrupted my answer — that's on me, not you. Want me to try again?",
        "action": "Try again",
    },
    "timeout": {
        "message": "This is taking longer than it should. You can wait a moment or try again.",
        "action": "Try again",
    },
    "rate_limited": {
        "message": "A lot of people are asking right now. Give it a few seconds and try again.",
        "action": "Try again",
    },
    "consent_required": {
        "message": "Before I can help with this, I'll need your OK to use AI on your documents.",
        "action": "Review AI consent",
    },
    "generic": {
        "message": "Something went wrong on my end. Let's try that again.",
        "action": "Try again",
    },
}

# System prompt for the assistant turn. Prompts the model to surface uncertainty
# rather than guess on regulatory specifics (docs/ux §4.1).
SYSTEM_PROMPT = (
    "You are the VA Benefits Navigator assistant. You help U.S. veterans understand "
    "VA disability benefits, decision letters, evidence, and claim processes in plain, "
    "calm language.\n\n"
    "Rules:\n"
    "- Be concise and use plain language (aim for an 8th-grade reading level).\n"
    "- When VA rules are specific (rating percentages, deadlines, eligibility edges) "
    "and you are not certain, SAY you are not certain and point the veteran to the "
    "relevant M21-1 section or to a VSO. Never guess with false confidence.\n"
    "- You provide guidance only. You are not a lawyer and you do not issue official "
    "VA determinations. Do not tell a veteran what the VA 'will' decide.\n"
    "- Be warm and respectful. These are people mid-claim; the stakes are real."
)

# Canned demo answer streamed when no ANTHROPIC_API_KEY is configured, so the
# UX is fully playable locally without a key or token spend. NOT shown when a
# real key is present.
DEMO_RESPONSE = (
    "Here's a plain-language walkthrough. A VA decision letter has three parts that "
    "matter most:\n\n"
    "1. **What was granted or denied** — each claimed condition is listed with a decision "
    "and, if granted, a disability rating (a percentage).\n"
    "2. **Why** — the letter cites the evidence it relied on and the rating criteria it "
    "applied.\n"
    "3. **Your options** — if you disagree, you generally have three review paths: a "
    "Supplemental Claim, a Higher-Level Review, or an appeal to the Board.\n\n"
    "I'm not certain about the exact deadline in your specific case — those depend on your "
    "decision date and review path, so I'd confirm that against your letter or with a VSO "
    "before relying on it.\n\n"
    "_(This is a local demo response — no live model was called. Set ANTHROPIC_API_KEY to "
    "get real answers.)_"
)
