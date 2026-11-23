# Troubleshooting

## The microphone

**Nothing happens when I speak.**
Chrome owns the mic permission. Open `chrome://settings/content/microphone`, add
`http://127.0.0.1:8765` to *Allowed*, then reload. The first load always needs a
click on **ENGAGE VOICE LINK** — Chrome will not run continuous recognition
without it.

**The footer says PAUSED.**
The link is muted. Press **RESUME** in the footer, or the header toggle.

**It hears the wake word but not the order.**
Order and wake word must be in one breath, or the order must follow within 45
seconds. Watch for the `AWAKE · 30s` countdown in the footer: while it runs you can
speak normally.

**The built-in mic is quiet.**
Detection is level-driven. Use a headset, or move closer. The microphone meter
under the waveform shows what Chrome is hearing.

**“Speech service unreachable”.**
Recognition uses Chrome's online service. Check connectivity; JARVIS retries on
its own.

## The screen

**“The screen read came back empty”.**
The link was paused (no watcher) and the on-demand capture failed. Resume, or
grant the screenshot dialog if the portal asked once.

**Vision is slow.**
OCR is CPU-only. Close heavy apps, or pause the link when you're not using vision.

**Screenshots land in my Pictures folder.**
They shouldn't — the watcher deletes the portal's temporary file after each read.
Only the explicit "take a screenshot" command saves anything, under `data/`.

## The agent

**“I can't find a window, sir.”**
Start the app through JARVIS (*“open calculator”*), not from the dock: it adds an
X11 hint so the driver can address it on Wayland.

**It clicks the wrong thing.**
Be literal: name the app and the control — *“click 7 in the calculator”*. Pixel
OCR is a fallback and weaker than real accessibility.

**Nothing happens in a browser page.**
Browser content exposes no accessibility tree in the Flatpak sandbox, so the agent
uses OCR on the window. Prefer navigation orders (*“go to … and search …”*) over
hunting for a text box.

**It won't stop.**
**STOP** in the agent strip, the footer button, or *“stop the agent”*. It halts
between steps.

## The machine

**Port 8765 is busy.**

```bash
JARVIS_PORT=8766 ./start.sh
```

**Brightness does nothing.**
Needs logind's `SetBrightness`. On desktops without it, install `brightnessctl`.

**`run command` fails.**
It runs `/bin/bash -lc` with your privileges and a 30-second cap. Long tasks need
a background-friendly command.

**The server won't start.**
Check `data/server.log`. A stale process can hold the port: `pkill -f app.py`.

## Resetting

```bash
pkill -f app.py            # stop the harness
pkill -f cua-driver        # stop the driver daemon
rm -rf data/               # notes, cache, settings, screenshots
./start.sh
```

Asset problems (missing voices or driver) are repaired by re-running
`./scripts/setup-assets.sh`.

## Logs

- `data/server.log` — harness, one line per start
- In-app SYSTEM LOG panel — live event tail
- `JARVIS_VERBOSE=1 ./start.sh` — HTTP request logging
