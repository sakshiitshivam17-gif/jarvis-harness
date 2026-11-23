# Contributing

Small, focused, tested. That's the whole policy.

## Setup

```bash
git clone https://github.com/<you>/jarvis-harness.git
cd jarvis-harness
./scripts/setup-assets.sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

## Before a PR

```bash
.venv/bin/python -m unittest discover -s tests -v
python3 -m py_compile app.py jarvis/*.py
node --check web/js/app.js
```

Add a router test for every new command. If it needs hardware, say so in the PR
and describe what you ran.

## Conventions

- **Router first.** New commands belong in `jarvis/intent.py` with a unit test.
  Only genuinely open-ended requests should reach the model.
- **Speak plainly.** Replies are short, in character, and readable by the voice.
  No markdown in `say`.
- **Confirm the irreversible.** Anything that costs data or a session goes into
  `CONFIRM_REQUIRED`.
- **No new runtime deps** without a note in the PR. The stdlib server and the
  no-build frontend are deliberate.
- **Latency is a feature.** Keep the fast path fast; never block the render thread.
- Match the existing style: 4-space Python, `"use strict"` JS, no semicolon
  soup, HUD colours via CSS variables.

## Scope

Good fits: new adapters for common desktops and apps, better grounding for the
agent, accessibility (halo, focus, contrast), voice variants, Hinglish coverage.

Out of scope for now: Windows and macOS, multi-user servers, and anything needing
a build step.

## Commits

`area: what changed` — e.g. `intent: route “play X” to the video, not results`.
Squash noise; describe the behaviour you changed and why.

## Reporting bugs

Include the spoken order, what happened, the SYSTEM LOG tail, and your session
type (`echo $XDG_SESSION_TYPE`). Redact anything personal first.
