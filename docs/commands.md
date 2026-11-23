# Command reference

Prefix with **“Jarvis”**, or speak within 45 seconds of the last exchange.
Quotes are examples, not strict syntax — the router is tolerant.

## Apps, files, web

| Say | Result |
| --- | --- |
| `open chrome` / `open terminal` / `open calculator` | Launches the app |
| `open project Harness 2.0` | Finds the project and opens it in VS Code |
| `open notes.md` | Finds the file anywhere in your usual folders |
| `open downloads` | Opens a standard folder |
| `open github.com` | Opens the site |
| `open my bookmark name` | Matching Chrome bookmark |
| `close spotify` | Terminates the app |
| `search the web for quantum tunnelling` | Google search |

Unknown names fall through to a web search rather than failing.

## Playback

| Say | Result |
| --- | --- |
| `play believer on youtube` | Resolves the first match and plays the video |
| `play lo-fi beats` | Same, bare form |
| `open youtube and play jazz` | Same |
| `pause` / `resume` / `next` / `previous` | Media transport |
| `what is playing` | Current track |
| `music` | Plays, or opens YouTube Music |

## System

| Say | Result |
| --- | --- |
| `volume up` / `set volume to 40` / `mute` | PipeWire default sink |
| `brightness down` / `set brightness to 30` | Backlight |
| `lock the screen` | Session lock |
| `take a screenshot` | Saves a PNG under `data/` |
| `system status` / `battery` / `cpu usage` / `what's my ip` | Telemetry, spoken |
| `turn off wifi` / `bluetooth on` | Radios |
| `do not disturb` / `night light` | GNOME settings |
| `suspend` / `restart` / `shut down` / `log out` | Machine control, all confirmed |
| `empty trash` | Empties it |
| `run command neofetch` | Shell, confirmed, output in the transcript |

## Screen

| Say | Result |
| --- | --- |
| `what's on my screen` | Describes the display from the live OCR buffer |
| `look at my screen` | Same, plus what you appear to be doing |
| `fix this error` / `review my code` | Reads the visible code or error and answers with a patch |
| `vibe coding` | Broad coding help against the screen |

Screen text is only sent to the neural core when you ask for screen help.

## Agent (acts for you)

| Say | Result |
| --- | --- |
| `click 7 in the calculator` | Clicks the named control |
| `type hello in the search box` | Clicks, then types |
| `press ctrl+s` | Key chord |
| `go to github.com and search cua` | Navigates and searches |
| `stop the agent` | Halts the loop |

A run is capped at eight steps; each appears in the AGENT strip.

## Utility

| Say | Result |
| --- | --- |
| `set a timer for 5 minutes to stretch` | Timer; announces when it fires |
| `remember that the drive is in drawer two` | Appends a note |
| `read my notes` / `clear my notes` | Reads or wipes them |
| `calculate 128 times 4` | Arithmetic |
| `what's the weather in Mumbai` | Forecast |
| `what time is it` / `what's the date` | Clock |

## Control

| Say | Result |
| --- | --- |
| `Jarvis` (alone) | “Yes, sir?” and opens the attentive window |
| `quiet` | Stops speech |
| `stop listening` | Pauses the mic, speech and agent |
| `stop the agent` | Halts only the agent |
| `help` | Command matrix |
| `clear the screen` | Clears the transcript |

## Hinglish

Understood while replies stay English:

`chrome kholo` · `volume badha do` · `awaaz kam karo` · `battery kitni hai` ·
`kitne baje hain` · `screen dekho` · `is error ko fix karo` · `screenshot lo` ·
`pc band karo` · `system so jao` · `wifi band karo` · `yaad rakho …` ·
`notes padho` · `believer chalao` · `haan` / `nahi` (confirmations)

Devanagari input works too.
