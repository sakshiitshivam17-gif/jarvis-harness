"""Computer-use agent loop (CUA): observe the desktop, decide, act, verify.

The loop follows the driver's own contract: reads are accessibility-tree
first, with OCR text as a second opinion, and every action is delivered to one
resolved window. The neural core only chooses the next step; the driver does
the delivery and the verification.
"""

from __future__ import annotations

import json
import re
import threading
import time
from typing import Callable

from . import config
from . import cua_driver as driver
from . import llm

MAX_STEPS = 8
OBSERVE_ELEMENTS = 130

SYSTEM = """You are J.A.R.V.I.S. operating a Linux desktop for the user.
You get the target window's accessibility tree, and OCR text of the screen.
Choose exactly ONE next action as JSON. No prose.

Action shapes:
{"action":"click","role":"button","name":"7"}        click an element from the tree (preferred)
{"action":"click","x":120,"y":340}                    pixel click; use the x,y of an [x,y] item when the list is pixel-grounded
{"action":"type","text":"hello"}
{"action":"key","key":"Return"}
{"action":"hotkey","keys":["ctrl","s"]}
{"action":"scroll","direction":"down","amount":3}
{"action":"launch","app":"gnome-calculator"}
{"action":"open","url":"https://example.com"}
{"action":"wait","seconds":1}
{"action":"ask","say":"what should I pick?"}
{"action":"done","say":"summary of what changed"}

Rules:
- If the list is "PIXEL-GROUNDED", click using the x,y of the closest item.
- Otherwise prefer role+name from the tree over pixels; use pixels only for canvases.
- One action per reply. To fill a field: click it, then type.
- The window to work in is already open — do not "launch" it again unless it is gone.
- If the tree already shows the goal is met, return "done".
- If the previous action failed or changed nothing, try a different approach.
- Never invent element names that are not in the tree.
- "say" is one short English sentence, spoken aloud.
"""


def _extract(text: str) -> dict | None:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip())
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except ValueError:
        return None
    if not isinstance(parsed, dict) or not parsed.get("action"):
        return None
    return parsed


class Agent:
    def __init__(self, bus, screen) -> None:
        self.bus = bus
        self.screen = screen
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self.running = False

    # --------------------------------------------------------------- control
    def stop(self) -> None:
        self._cancel.set()

    def start(self, task: str, on_event: Callable[[str, dict], None] | None = None) -> threading.Thread:
        if self.running:
            self.stop()
            time.sleep(0.4)
        self._cancel.clear()
        self.running = True
        self._thread = threading.Thread(
            target=self._run, args=(task, on_event), daemon=True, name="cua-agent"
        )
        self._thread.start()
        return self._thread

    # ----------------------------------------------------------------- loop
    def _run(self, task: str, on_event: Callable[[str, dict], None] | None) -> None:
        trace: list[dict] = []
        history: list[str] = []

        def emit(kind: str, payload: dict) -> None:
            self.bus.publish("agent", {"kind": kind, **payload})
            if on_event:
                on_event(kind, payload)

        try:
            if not driver.available():
                emit("error", {"say": "The computer-use driver isn't installed, sir."})
                return
            if not driver.ensure_daemon():
                emit("error", {"say": "The computer-use driver won't start, sir."})
                return

            target: dict | None = None
            emit("start", {"task": task, "max_steps": MAX_STEPS})
            self.bus.log("CUA", f"Task: {task}")

            self._current_url = ""
            seed = self._seed_url(task)
            if seed:
                target = driver.resolve_window(self._guess_app(task) or "") or self._pick_window(task)
                if not target:
                    driver.launch("google-chrome")
                    target = driver.wait_for_window("chrome", 15)
                if target:
                    emit("observe", {"step": 0, "app": target.get("app_name", ""), "title": "navigating", "tree": "", "say": "opening"})
                    opened = self._exec(
                        self._open_script(int(target["pid"]), int(target["window_id"]), seed),
                        f"open {seed}",
                    )
                    self.bus.log("CUA", f"open {seed}: {'ok' if opened.get('ok') else opened.get('error')}",
                                 "ok" if opened.get("ok") else "warn")
                    emit("act", {"step": 0, "action": "open", "label": seed, "ok": bool(opened.get("ok")),
                                 "error": opened.get("error", "")})
                    if opened.get("ok"):
                        self._current_url = seed
                    time.sleep(1.5)

            for step in range(1, MAX_STEPS + 1):
                if self._cancel.is_set():
                    emit("done", {"say": "Stopped, sir.", "cancelled": True, "steps": step - 1})
                    return

                observation = self._observe(task, target)
                if target is None:
                    target = observation["window"]
                if not observation["window"]:
                    emit("error", {"say": "I can't find a window to work with, sir."})
                    return

                emit("observe", {
                    "step": step,
                    "app": observation["app"],
                    "title": observation["title"],
                    "tree": observation["tree"][:1200],
                    "ocr": observation["ocr"][:400],
                })

                decision = self._decide(task, observation, history)
                if not decision:
                    emit("error", {"say": "I lost my train of thought, sir.", "steps": step})
                    return

                action = decision.get("action", "")
                if action in ("done", "ask"):
                    say = str(decision.get("say") or ("Done, sir." if action == "done" else "Which one, sir?"))
                    emit("done", {"say": say, "steps": step, "trace": trace})
                    self.bus.log("CUA", f"Finished after {step} steps", "ok")
                    return

                result = self._act(action, decision, observation, target)
                trace.append({"step": step, "action": action, "args": _brief(decision), "result": _brief(result)})
                history.append(f"{step}. {action} {_brief(decision)} -> {_brief(result)}")
                self.bus.log("CUA", f"{action}: {result.get('label') or result.get('error') or 'ok'}",
                             "ok" if result.get("ok") else "warn")
                emit("act", {
                    "step": step,
                    "action": action,
                    "label": result.get("label") or "",
                    "ok": bool(result.get("ok")),
                    "error": result.get("error") or "",
                    "say": str(decision.get("say") or ""),
                })
                if not result.get("ok"):
                    history.append(f"   reason: {result.get('error')}")
                if result.get("launched"):
                    window = driver.wait_for_window(str(result["launched"]))
                    if window:
                        target = window

            emit("done", {"say": "That's my step budget, sir. Carry on from here?", "steps": MAX_STEPS, "trace": trace})
        except Exception as exc:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            self.bus.log("CUA", f"Fault: {exc}", "warn")
            emit("error", {"say": f"The agent faulted, sir: {exc}"})
        finally:
            self.running = False

    # ------------------------------------------------------------- observing
    def _observe(self, task: str, target: dict | None) -> dict:
        if target:
            found = driver.resolve_window(str(target.get("app_name", "")), int(target.get("pid", 0)))
            target = found or target
        else:
            guess = self._guess_app(task)
            target = driver.resolve_window(guess) if guess else None
            if target is None:
                target = self._pick_window(task)

        blank = {"window": None, "app": "", "title": "", "tree": "", "pixel": False, "ocr": ""}
        if not target:
            return blank
        pid, window_id = int(target["pid"]), int(target["window_id"])
        query = self._focus(task)
        body = (
            f"const app = await cua.getApp({{pid:{pid}, windowId:{window_id}}});\n"
            f"const s = await app.getState({{max_elements:{OBSERVE_ELEMENTS}"
            + (f", query: {json.dumps(query)}" if query else "")
            + "});\n"
            "return {tree: s.tree_markdown || '', degraded: !!s.degraded};"
        )
        read = driver.script(body, timeout_ms=30000)
        tree = ""
        degraded = True
        if read.get("ok") and isinstance(read.get("value"), dict):
            tree = str(read["value"].get("tree") or "")
            degraded = bool(read["value"].get("degraded"))
        if not degraded and len(tree.splitlines()) < 3 and query:
            wide = body.replace(f", query: {json.dumps(query)}", "")
            retry = driver.script(wide, timeout_ms=30000)
            if retry.get("ok") and isinstance(retry.get("value"), dict):
                wider = str(retry["value"].get("tree") or "")
                if len(wider.splitlines()) >= 3:
                    tree, read = wider, retry
        pixel = False
        if degraded or len(tree.splitlines()) < 3:
            grounded = self._pixel_tree(read.get("screenshot"))
            if grounded:
                tree, pixel = grounded, True
        if pixel:
            tree = ("The browser toolbar is at the top of the window (about y=80px).\n"
                    "Prefer 'open' with a full url over clicking the address bar.\n" + tree)
        if not tree and self.screen:
            captured = self.screen.capture()
            tree = self.screen.read(captured) if captured else ""
        return {
            "window": target,
            "app": str(target.get("app_name", "")),
            "title": str(target.get("window_title") or target.get("title") or ""),
            "bounds": target,
            "tree": tree,
            "pixel": pixel,
            "ocr": "" if pixel else (self.screen.last_text if self.screen else "")[:1200],
        }

    def _pixel_tree(self, png_b64: str | None) -> str:
        """OCR a window screenshot into x,y click targets when the tree is empty."""
        if not self.screen or not png_b64:
            return ""
        import base64
        path = config.DATA_DIR / "screen" / "window.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_bytes(base64.b64decode(png_b64))
        except (ValueError, OSError):
            return ""
        boxes = self.screen.read_boxes(path)
        if not boxes:
            return ""
        lines = ["PIXEL-GROUNDED list — click with the x,y of the matching item:"]
        for cx, cy, text in boxes[:90]:
            lines.append(f'- [{cx},{cy}] "{text}"')
        return "\n".join(lines)

    # -------------------------------------------------------------- deciding
    @staticmethod
    def _guess_app(task: str) -> str:
        lowered = task.casefold()
        if re.search(r"\b(browser|tab|web|site|page|url)\b|\.[a-z]{2,4}\b", lowered):
            for candidate in ("chrome", "chromium", "firefox"):
                if candidate in lowered:
                    return candidate
        for word in re.findall(r"[a-z0-9+.-]{3,}", lowered):
            if word in {"chrome", "firefox", "code", "calculator", "nautilus", "terminal",
                        "libreoffice", "writer", "calc", "slack", "discord", "spotify"}:
                return word
        return ""

    @staticmethod
    def _pick_window(task: str) -> dict | None:
        candidates = driver.windows()
        if not candidates:
            return None
        if re.search(r"\b(browser|tab|web|site|page|url)\b|\.[a-z]{2,4}\b", task.casefold()):
            for window in candidates:
                if re.search(r"chrome|chromium|firefox", str(window.get("app_name", "")), re.I):
                    return window
        words = set(re.findall(r"[a-z]{4,}", task.casefold()))
        def score(window: dict) -> float:
            hay = (str(window.get("app_name", "")) + " " + str(window.get("title", ""))).casefold()
            hits = len(words & set(re.findall(r"[a-z]{4,}", hay)))
            if re.search(r"about:blank|new tab", hay):
                hits -= 2
            z = window.get("z_index")
            return hits + (0.1 * z if isinstance(z, int) else 0)
        return max(candidates, key=score)

    @staticmethod
    def _seed_url(task: str) -> str:
        """Use the URL straight from the wording; more reliable than hunting a box."""
        match = re.search(r"\b((?:[a-z0-9-]+\.)+(?:com|org|net|io|dev|ai|co|in|gov|edu)(?:/[\w\-./?=%&]*)?)", task, re.I)
        if match:
            host = match.group(1)
            return host if re.match(r"^[a-z]+://", host, re.I) else "https://" + host
        match = re.search(r"\b(?:go to|open|visit|navigate to)\s+(?:the\s+)?([a-z0-9-]{3,})\s+(?:site|website|page)\b", task, re.I)
        if match and match.group(1).casefold() not in {"its", "this", "that", "their", "his", "her"}:
            return "https://" + match.group(1) + ".com"
        return ""

    @staticmethod
    def _focus(task: str) -> str:
        words = [w for w in re.findall(r"[A-Za-z]{4,}", task) if w.casefold() not in
                 {"open", "click", "type", "with", "that", "then", "into", "from", "please", "window", "search"}]
        return " ".join(words[:3]) or ""

    def _decide(self, task: str, observation: dict, history: list[str]) -> dict | None:
        if not llm.available():
            return None
        page = observation.get("title") or ""
        current = getattr(self, "_current_url", "")
        where = ""
        if page:
            where = f"\nWindow title: {page}"
        if current:
            where += f"\nCurrent url: {current}"
        where += "\n"
        payload = (
            f"Task: {task}\n"
            f"Window: {observation['app']} — {observation['title']}"
            f"{' (pixel-grounded list)' if observation.get('pixel') else ''}"
            f"{where}\n"
            f"Accessibility tree:\n{observation['tree'][:6000]}\n\n"
        )
        if observation["ocr"]:
            payload += f"OCR text on screen:\n{observation['ocr'][:800]}\n\n"
        if history:
            payload += "Steps so far:\n" + "\n".join(history[-6:]) + "\n\n"
            if len(history) > 1 and _signature(history[-1]) == _signature(history[-2]):
                payload += ("The last two steps were identical and changed nothing. Do something different — "
                            "for a search, open the site's search url such as "
                            "https://github.com/search?q=TERM.\n\n")
        payload += "Next action JSON:"
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": payload},
        ]
        raw = llm.raw_call(messages, max_tokens=220, json_mode=False)
        return _extract(raw) if raw else None

    # --------------------------------------------------------------- acting
    def _act(self, action: str, decision: dict, observation: dict, target: dict) -> dict:
        window = observation["window"] or target
        pid = int(window["pid"])
        window_id = int(window["window_id"])

        if action == "launch":
            app = str(decision.get("app") or "").strip()
            if not app:
                return {"ok": False, "error": "no app given"}
            result = driver.launch(app)
            if result.get("ok"):
                result["launched"] = app
            return result

        if action == "open":
            url = str(decision.get("url") or "").strip()
            if not url:
                return {"ok": False, "error": "no url given"}
            if not re.match(r"^[a-z]+://", url):
                url = "https://" + url
            result = self._exec(self._open_script(pid, window_id, url), f"open {url}")
            if result.get("ok"):
                self._current_url = url
            return result

        if action == "wait":
            time.sleep(min(float(decision.get("seconds", 1)), 5))
            return {"ok": True, "label": "waited"}

        head = f"const app = await cua.getApp({{pid:{pid}, windowId:{window_id}}});\n"
        body = None
        label = action

        if action == "click" and decision.get("role"):
            name = str(decision.get("name", ""))
            body = head + "try { await app.click({role:" + json.dumps(str(decision["role"])) + ", name:" + json.dumps(name) + "}); } catch (e) { " \
                "await cua.call('click', {pid:" + str(pid) + ", window_id:" + str(window_id) + \
                ", role:" + json.dumps(str(decision["role"])) + ", name:" + json.dumps(name) + ", delivery_mode:'foreground'}); }"
            label = f"click {name or decision['role']}"
        elif action == "click" and decision.get("x") is not None:
            x, y = int(decision["x"]), int(decision["y"])
            body = head + "await app.getState({max_elements:5});\n" + \
                f"try {{ await app.click([{x}, {y}]); }} catch (e) {{ " \
                f"await cua.call('click', {{pid:{pid}, window_id:{window_id}, x:{x}, y:{y}, delivery_mode:'foreground'}}); }}"
            label = f"click {x},{y}"
        elif action == "type":
            text = str(decision.get("text", ""))
            body = head + "try { await app.typeText(" + json.dumps(text) + "); } catch (e) { " \
                "await cua.call('type_text', {pid:" + str(pid) + ", window_id:" + str(window_id) + \
                ", text:" + json.dumps(text) + ", delivery_mode:'foreground'}); }"
            label = f'type "{text[:40]}"'
        elif action == "key":
            key = str(decision.get("key", "Return"))
            body = head + "try { await app.pressKey(" + json.dumps(key) + "); } catch (e) { " \
                "await cua.call('press_key', {pid:" + str(pid) + ", window_id:" + str(window_id) + \
                ", key:" + json.dumps(key) + ", delivery_mode:'foreground'}); }"
            label = f"press {key}"
        elif action == "hotkey":
            keys = decision.get("keys") or []
            body = head + "try { await app.hotkey(" + json.dumps(keys) + "); } catch (e) { " \
                "await cua.call('hotkey', {pid:" + str(pid) + ", window_id:" + str(window_id) + \
                ", keys:" + json.dumps(keys) + ", delivery_mode:'foreground'}); }"
            label = "hotkey " + "+".join(str(k) for k in keys)
        elif action == "scroll":
            bounds = observation.get("bounds") or {}
            cx = int(bounds.get("x", 0) + bounds.get("width", 200) / 2)
            cy = int(bounds.get("y", 0) + bounds.get("height", 200) / 2)
            direction = str(decision.get("direction", "down"))
            amount = int(decision.get("amount", 3))
            body = head + f"await app.scroll([{abs(cx)},{abs(cy)}], {json.dumps(direction)}, {amount});"
            label = f"scroll {direction}"
        else:
            return {"ok": False, "error": f"unknown action {action}"}

        result = self._exec(body, label)
        if not result.get("ok") and action == "click" and decision.get("role"):
            nearest = _nearest(result)
            if nearest and nearest.casefold() != str(decision.get("name", "")).casefold():
                retry_body = head + f"await app.click({{role:{json.dumps(str(decision['role']))}, name:{json.dumps(nearest)}}});"
                retry = self._exec(retry_body, f"click {nearest}")
                if retry.get("ok"):
                    retry["substituted"] = nearest
                    return retry
        return result

    def _exec(self, body: str, label: str) -> dict:
        result = driver.script(body, timeout_ms=40000)
        if result.get("ok"):
            return {"ok": True, "label": label}
        message = str(result.get("error") or "action refused")
        if "screenshot" in message.lower() or "at-spi" in message.lower():
            driver.recycle()
            result = driver.script(body, timeout_ms=40000)
            if result.get("ok"):
                return {"ok": True, "label": label}
            message = str(result.get("error") or message)
        if label.startswith("open "):
            time.sleep(0.6)
            result = driver.script(body, timeout_ms=40000)
            if result.get("ok"):
                return {"ok": True, "label": label}
        return {"ok": False, "error": message, "label": label}

    @staticmethod
    def _open_script(pid: int, window_id: int, url: str) -> str:
        args = f'{{"pid":{pid},"window_id":{window_id}'
        return "\n".join([
            f"const app = await cua.getApp({{pid:{pid}, windowId:{window_id}}});",
            "await app.getState({max_elements:5});",
            f"await cua.call('hotkey', {args},\"keys\":[\"ctrl\",\"l\"],\"delivery_mode\":\"foreground\"}});",
            f"await cua.call('type_text', {args},\"text\":{json.dumps(url)},\"delivery_mode\":\"foreground\"}});",
            f"await cua.call('press_key', {args},\"key\":\"Return\",\"delivery_mode\":\"foreground\"}});",
            "return 'ok';",
        ])


def _signature(line: str) -> str:
    parts = line.split(" -> ")
    return parts[0].split(". ", 1)[-1]


def _nearest(result: dict) -> str | None:
    """Pull the closest element name out of a 'no button "X"' refusal."""
    text = json.dumps(result)
    match = re.search(r'nearest:\s*\[\d+\]\s*\w+\s+"([^"]+)"', text)
    return match.group(1) if match else None


def _brief(data: dict) -> str:
    keep = {k: v for k, v in data.items() if k in ("role", "name", "text", "key", "app", "x", "y", "label", "ok", "error", "direction", "amount")}
    return json.dumps(keep, ensure_ascii=False)[:200]
