"""Command orchestration: confirmation, routing, execution, memory."""

from __future__ import annotations

import random
import re
import threading
import time
from collections import deque

from . import config, intent, llm
from .actions import Actions
from .bus import EventBus
from .system import Sampler

CONFIRM_REQUIRED = {"shutdown", "restart", "suspend", "shell"}

CONFIRM_PROMPTS = {
    "shutdown": "Power down the reactor, sir?",
    "restart": "Restart the system, sir?",
    "suspend": "Put the machine to sleep, sir?",
    "shell": "Run that command, sir?",
}


class Engine:
    def __init__(self, bus: EventBus, sampler: Sampler, actions: Actions, screen=None, agent=None) -> None:
        self.bus = bus
        self.sampler = sampler
        self.actions = actions
        self.screen = screen
        self.agent = agent
        self.pending: dict | None = None
        self.history: deque[dict] = deque(maxlen=12)
        self._lock = threading.Lock()
        self._last_command = ""

    def _context(self) -> str:
        stats = self.sampler.snapshot()
        return (
            f"CPU {stats.get('cpu', 0):.0f}%, memory {stats.get('mem', 0):.0f}%, "
            f"battery {stats.get('battery')}, volume {stats.get('volume')}%. "
            f"Neural core available. Time {time.strftime('%H:%M')}."
        )

    def _remember(self, role: str, content: str) -> None:
        if content:
            self.history.append({"role": role, "content": content})

    def _set_pending(self, parsed: dict) -> dict:
        action = parsed["action"]
        prompt = CONFIRM_PROMPTS.get(action, "Proceed, sir?")
        if action == "shell":
            prompt = f"Run `{parsed['args'].get('command', 'that command')}`, sir?"
        with self._lock:
            self.pending = {
                "action": action,
                "args": parsed.get("args", {}),
                "created": time.time(),
                "prompt": prompt,
            }
        self.bus.log("WAIT", prompt, "warn")
        return {
            "ok": True,
            "action": action,
            "say": prompt,
            "detail": "Awaiting voice confirmation",
            "data": {"confirmation": {"action": action, "args": parsed.get("args", {})}},
            "pending": True,
            "source": parsed.get("source", "local"),
        }

    def _expire_pending(self) -> None:
        with self._lock:
            if self.pending and time.time() - self.pending["created"] > config.SETTINGS["confirm_seconds"]:
                self.pending = None

    def handle(self, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            return {"ok": False, "action": "empty", "say": "", "detail": "", "data": {}}

        self._last_command = text
        self.bus.log("YOU", text)
        self._expire_pending()

        parsed = intent.parse(text)
        with self._lock:
            pending = self.pending

        if pending:
            if parsed["action"] == "confirm":
                with self._lock:
                    self.pending = None
                result = self.actions.execute(pending["action"], pending["args"])
                self.bus.log("CONF", "Confirmed", "info")
                self._remember("assistant", result.get("say", ""))
                result["source"] = "confirmation"
                return result
            if parsed["action"] == "cancel":
                with self._lock:
                    self.pending = None
                self.bus.log("CONF", "Cancelled", "info")
                result = self.actions.execute("cancel", {})
                self._remember("assistant", result.get("say", ""))
                return result
            # A fresh command supersedes the pending one.
            with self._lock:
                self.pending = None

        if parsed["action"] == "screen_look":
            return self._screen_look(text)

        if parsed["action"] in ("cua_task", "cua_stop"):
            return self._agent_action(parsed["action"], text)

        if parsed["action"] == "unknown":
            parsed = self._neural_fallback(text) or parsed

        action = parsed.get("action", "")
        args = parsed.get("args", {})
        source = parsed.get("source", "local")
        self._remember("user", text)

        if action in ("empty", "unknown", "confirm", "cancel"):
            say = parsed.get("say") or ""
            if not say:
                say = random.choice(config.VOICE_LINES["unknown"])
            result = {"ok": False, "action": action or "unknown", "say": say, "detail": "", "data": {}, "source": source}
            self._remember("assistant", say)
            return result

        if action == "chat":
            say = parsed.get("say") or "I'm not certain, sir."
            result = {"ok": True, "action": "chat", "say": say, "detail": "", "data": {}, "source": "neural"}
            self._remember("assistant", say)
            return result

        if action in CONFIRM_REQUIRED:
            return self._set_pending(parsed)

        result = self.actions.execute(action, args)
        if not result.get("say"):
            result["say"] = parsed.get("say") or "Done, sir."
        elif parsed.get("say") and source == "neural":
            result["say"] = parsed["say"]
        result["source"] = source
        self._remember("assistant", result.get("say", ""))
        return result

    @staticmethod
    def _wants_screen(text: str) -> bool:
        return bool(re.search(
            r"\b(screen|code|error|bug|exception|terminal|stack|trace|compile|build|"
            r"function|this|here|look|see|read|review|fix|wrong|debug)\b",
            text.casefold(),
        ))

    def _neural_fallback(self, text: str) -> dict | None:
        if not llm.available():
            return None
        screen_text = ""
        screen_seen = False
        if self.screen and self._wants_screen(text):
            screen_text = self.screen.fresh()
            if not screen_text:
                path = self.screen.capture()
                if path:
                    screen_text = self.screen.read(path)
            if screen_text:
                screen_seen = True
                self.bus.log("SCREEN", f"Used {len(screen_text)} characters of screen text", "info")
        result = llm.interpret(text, list(self.history), self._context(), screen_text=screen_text)
        if result:
            self.bus.log("NEURAL", f"Routed to {result['action']}", "info")
            if screen_seen and result.get("action") == "chat":
                result.setdefault("data", {})
                result["data"]["full"] = result.get("say", "")
        return result

    def _screen_look(self, question: str) -> dict:
        if not self.screen:
            return {"ok": False, "action": "screen_look", "say": "Screen vision isn't fitted, sir.", "detail": "", "data": {}}
        self._remember("user", question)
        screen_text = self.screen.fresh()
        if screen_text:
            self.bus.log("SCREEN", f"Using live screen read ({len(screen_text)} chars)", "ok")
        else:
            self.bus.log("SCREEN", "Refreshing screen read", "info")
            path = self.screen.capture()
            screen_text = self.screen.read(path) if path else ""
        if not screen_text:
            return {"ok": False, "action": "screen_look", "say": "The screen read came back empty, sir.", "detail": "", "data": {}}
        prompt = question
        if re.fullmatch(r"(?:look at|see|read|check|scan|analy[sz]e)(?: my| the)? screen[.!?]*", question.casefold().strip()):
            prompt = ("Describe what is on the screen and what the user is working on. "
                      "If there is code, an error, a terminal or a design, explain what matters.")
        answer = None
        if screen_text and llm.available():
            answer = llm.screen_answer(prompt, screen_text, list(self.history))
        if not answer:
            answer = self.screen.describe(prompt) or ""
        if not answer and screen_text:
            answer = "I can read the screen, sir. The visible text begins: " + screen_text[:500]
        if not answer:
            return {
                "ok": False,
                "action": "screen_look",
                "say": "I can see the screen but nothing readable is on it, sir.",
                "detail": "empty OCR",
                "data": {},
            }
        spoken = self._speakable(answer)
        self._remember("assistant", answer[:1600])
        return {
            "ok": True,
            "action": "screen_look",
            "say": spoken,
            "detail": f"Screen read · {len(screen_text):,} characters",
            "data": {"full": answer, "ocr_chars": len(screen_text)},
            "source": "screen+neural" if llm.available() else "screen",
        }

    @staticmethod
    def _speakable(text: str, limit: int = 260) -> str:
        text = re.sub(r"```.*?```", " The code is on screen. ", text, flags=re.DOTALL)
        text = re.sub(r"[*_#>`]+", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) <= limit:
            return text
        cut = text[:limit]
        stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        return (cut[: stop + 1] if stop > 120 else cut).strip()

    def _agent_action(self, action: str, text: str) -> dict:
        if not self.agent:
            return {"ok": False, "action": action, "say": "The computer-use agent isn't fitted, sir.", "detail": "", "data": {}}
        if action == "cua_stop":
            self.agent.stop()
            return {"ok": True, "action": "cua_stop", "say": "Stopping the agent, sir.", "detail": "", "data": {}}
        task = intent.parse(text).get("args", {}).get("task") or text
        self.agent.start(task)
        self._remember("user", text)
        return {
            "ok": True,
            "action": "cua_task",
            "say": "On it, sir. Working the screen now.",
            "detail": f"Agent task: {task}",
            "data": {"task": task},
        }

    def status(self) -> dict:
        with self._lock:
            pending = dict(self.pending) if self.pending else None
        return {
            "pending": pending,
            "last_command": self._last_command,
            "history_size": len(self.history),
        }
