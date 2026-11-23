# Architecture

JARVIS is a two-part system: a browser HUD and a local Python harness. All
capability lives in the harness; the page is presentation and microphone.

```
┌──────────────── browser ────────────────┐        ┌──────── harness ────────┐
│ HUD · wake gate · speech in/out         │  HTTP  │ app.py  (stdlib server) │
│ Web Speech API · AudioContext meter     │◀──────▶│ SSE bus · REST · TTS    │
└─────────────────────────────────────────┘        └───────────┬────────────┘
                                                               │
        ┌──────────────────────────────────────────────────────┼─────────────┐
        │                                                      │             │
   intent router                                        engine ──────┐  screen module
        │ unknown                                              │      │      │
        ▼                                                      ▼      ▼      ▼
   neural core (DeepSeek)  ── chat / screen answer ──▶ reply    agent   CUA driver
                                        └─ machine action ─────┘
                                                               actions  (windows, AX,
                                                                        input)
```

## Files

| Path | Role |
| --- | --- |
| `app.py` | HTTP server: REST, SSE stream, streaming TTS, static files. Localhost only. |
| `jarvis/config.py` | Settings, paths, capability probe, spoken phrase pools. |
| `jarvis/bus.py` | Thread-safe event fan-out plus a bounded log ring. |
| `jarvis/intent.py` | Deterministic command router (English + Hinglish + Devanagari). |
| `jarvis/actions.py` | Action adapters: launcher, YouTube resolver, PipeWire, MPRIS, logind, NetworkManager, timers, notes. |
| `jarvis/engine.py` | Confirmation state, routing, conversation memory, screen orchestration. |
| `jarvis/llm.py` | DeepSeek client: intent fallback, chat, screen answers, raw completions. |
| `jarvis/screen.py` | Portal capture, background OCR watcher, OCR box extraction, optional local vision. |
| `jarvis/cua_driver.py` | Adapter for the bundled CUA driver. |
| `jarvis/cua_agent.py` | Bounded observe → decide → act loop with trace and recovery. |
| `jarvis/system.py` | `/proc` and `sysfs` telemetry, weather, spoken status text. |
| `jarvis/tts.py` | Piper synthesis with cache and streaming; Edge fallback. |
| `web/` | HUD: HTML, CSS, JS, vendored fonts. No build step. |
| `tests/` | Router unit tests. |
| `scripts/` | Asset fetch, plus developer probes under `tools/`. |

## Request flow

1. The page runs continuous `SpeechRecognition`. Utterances are gated on a wake
   word (or an active 45-second attentive window) and posted to `/api/command`.
2. `engine.handle` checks for a pending confirmation, then routes with
   `intent.parse`.
3. Known actions execute immediately. `unknown` goes to `llm.interpret`, which may
   return a machine action or a chat answer. Actions flagged destructive are held
   for a spoken yes/no.
4. The result is returned as JSON; the page narrates it, speaks it, and renders
   any structured data (command matrix, agent trace, code blocks).

Progress that outlives one request — agent steps, timers, telemetry — is pushed
over `GET /api/events` (server-sent events), not polled.

## Design decisions

- **Rules before models.** Voice round-trips are dominated by latency, so the
  frequent commands never touch an LLM. The neural core is a fallback, not the path.
- **Stdlib server.** Zero deployment story: `python app.py`. The load is one user
  on localhost, so a framework would only add dependencies.
- **Streaming over blocking.** TTS streams as it synthesises; audio starts
  ~0.9 s in instead of after a complete file.
- **Live screen buffer.** Capture-on-demand made every screen question slow and
  littered `~/Pictures`. A watcher keeps OCR warm and cleans up after itself.
- **Bounded agency.** Eight steps, one visible action each, accessibility-tree
  grounding first and pixel OCR only as a fallback.

## Platform notes

- Speech recognition is Chrome's; the API is absent from Firefox.
- Wayland blocks global input. The CUA driver uses XWayland for addressable
  windows, and JARVIS launches apps with an X11 hint when it can. GNOME 50 cannot
  yet load the driver's Shell geometry helper, so native-Wayland windows are
  screen-readable but not clickable.
- Brightness goes through logind, which needs no root.
