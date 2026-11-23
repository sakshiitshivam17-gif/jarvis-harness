# The agent

The agent is the part that acts. Say *“Jarvis, click 7 in the calculator”* and it
drives the window; you keep working and watch the steps.

It is built on [trycua/cua](https://github.com/trycua/cua)'s driver, which
delivers input to a named window without stealing focus.

## The loop

```
resolve window → observe → decide → act → verify → repeat (≤ 8 steps) → done
```

1. **Resolve.** Pick the window from the app you named, else the best title match,
   else a browser if the order mentions a URL. App keywords win over recency.
2. **Observe.** One script reads the window's accessibility tree *and* a
   screenshot in the same driver session, so element handles and pixels stay valid.
3. **Decide.** The neural core gets the tree, the OCR text, the window title, the
   current URL and the last actions, and answers with exactly one action.
4. **Act.** One driver script performs it: `click`, `type`, `key`, `hotkey`,
   `scroll`, `launch`, `open`, `wait`.
5. **Verify.** The script's observation comes back; failures are retried once with
   the nearest matching element, or in the foreground when an app ignores
   background input.

The loop ends on `done`, on cancellation, or when the budget is spent.

## Grounding order

Accessibility first, pixels second:

1. **Accessibility tree** — roles, names, values, actions. Precise, works on
   unfocused and covered windows.
2. **Pixel OCR** — when an app publishes no tree (browser page content in the
   Flatpak sandbox), the screenshot is OCR'd into `[x, y] "text"` targets. The
   click happens in the same session as the read, so the coordinates are always
   the ones the model saw.

URLs short-circuit both: if the order contains a domain, the address bar is
driven directly instead of hunting for a field.

## Safety

- Hard cap of 8 steps and a 40 s timeout per action.
- Window-scoped: it touches the resolved window, not the whole desktop.
- Only `click`/`type`/`key`/`scroll` fire without asking; the body text of
  destructive commands still needs spoken confirmation in the main engine.
- **STOP** in the trace, the footer button, or *“stop the agent”* halts it between
  steps.
- Every action is logged and rendered; nothing is hidden.

## Recovery

| Failure | Handling |
| --- | --- |
| Element name misspelled | Retried with the driver's nearest label |
| App ignores background input | Retried with foreground delivery |
| AT-SPI dropped its bus | Daemon recycled, action replayed once |
| Navigation failed | Replayed once after a short delay |
| Same action twice | Prompt tells the model to change tactic |

## Limits

- GNOME 50 cannot load the driver's Shell geometry helper, so native-Wayland
  windows are readable but not addressable. JARVIS launches apps with an X11 hint.
- No multi-window choreography: one window per run.
- The model is text-only, so it never sees the image itself — only OCR text and
  the accessibility tree.

## Watching it

The AGENT strip under the transcript shows step, verb, target and outcome, with
failures in red. It clears four seconds after the run ends.
