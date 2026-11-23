# Privacy and safety

## What stays local

- The HTTP server binds to `127.0.0.1` only.
- Speech synthesis runs on the CPU with a bundled voice model.
- Screen OCR runs on-device; screenshots exist only as a rolling file under
  `data/screen/` and are overwritten.
- Notes, cached audio, settings and timers live in `data/` on your disk.
- No analytics, accounts, or database. Nothing is uploaded behind your back.

## What leaves the machine

| Path | Destination | When |
| --- | --- | --- |
| Speech recognition | Chrome's speech service | Whenever the link is live |
| Intent fallback, chat, screen answers | DeepSeek API | Only when the router can't place the order, or you ask a question |
| OCR text | DeepSeek API | Only when you explicitly ask for screen help |
| Weather | `wttr.in` | Only when you ask for weather |
| YouTube search | `youtube.com` | Only when you ask to play something |

Turn the neural core off entirely with `"llm_enabled": false` in
`data/settings.json`; local commands keep working and chat replies are skipped.

## Confirmations

These wait for a spoken *yes* (or *haan*), and time out after 45 seconds:

- `shut down`, `restart`, `suspend`
- `run command …` (arbitrary shell)

`log out`, `lock` and file-affecting actions run immediately — they are cheap to
undo. The agent's clicks and typing are immediate too; stop it with the STOP
button.

## The agent's blast radius

The agent only drives the window it resolved. It cannot read your files or run
shell — that stays with the rules engine. Eight steps, one action at a time,
every action visible.

## Ports and origins

`POST` endpoints reject requests whose `Origin` header is not the local page, so a
visited site can't drive your machine through the browser. Bind elsewhere with
`JARVIS_HOST=0.0.0.0` only if you add your own origin to `ALLOWED_ORIGINS` in
`app.py`.

## Shell commands

`run command …` executes through `/bin/bash -lc` as your user, with a 30-second
timeout and the tail of the output shown. Same privileges as a terminal.

## Data you can delete

```bash
rm -rf data/            # notes, cache, screenshots, settings
```

Nothing else is written outside the repo.
