"""Optional DeepSeek neural core: intent fallback and conversation."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime

from . import config

ENDPOINT = "https://api.deepseek.com/chat/completions"

ACTION_SPEC = """
Available actions and args (use exactly these names):
open {target}                                  // app or website by name, e.g. "chrome", "youtube"
open_app {app}                                 // launch a desktop application
open_url {url, label?}                         // a full URL
open_path {path}                               // filesystem path
close_app {app}
search {query}                                 // web search
youtube {query}
music {}
volume {mode: up|down|set|mute|unmute|status, value?}
brightness {mode: up|down|set|status, value?}
media {mode: play|pause|next|previous|stop}
lock {}
suspend {}
shutdown {}
restart {}
logout {}
screenshot {}
empty_trash {}
wifi {state: on|off|status}
bluetooth {state: on|off|status}
dnd {state: on|off}
night_light {state: on|off}
timer {seconds, label?}
note {text}
read_notes {}
clear_notes {}
calculate {expression}                         // arithmetic only
shell {command}                                // raw bash, only when explicitly asked
status {}
system_metric {metric: cpu|memory|disk|battery|temperature|network|volume|uptime}
weather {location?}
now_playing {}
time {}
date {}
help {}
standby {}
wake {}
quiet {}
chat {message}                                 // general answer, not a machine action
"""

SYSTEM = f"""You are J.A.R.V.I.S., the dry, impeccably polite AI harness running on the user's Arch Linux machine.
Address the user as "sir". Be concise (1-2 sentences) unless asked for detail. Never invent system state.

LANGUAGE: Reply in clear, natural English unless the user explicitly asks for another language.

The fast local router handles most commands. It missed this one, so classify it.
Return ONLY a JSON object: {{"action": "...", "args": {{...}}, "say": "..."}}
- Use a machine action when the user asks to control or query the computer.
- Use "chat" for questions, small talk, and explanations. Put the complete answer in "say".
- For chat, also include args.message with the user text.
- If a command is ambiguous, choose the most useful machine action rather than chat.
- "say" must be the spoken response, in character. Do not mention JSON, intent, or routers.

Current local time: {datetime.now():%A %d %B %Y, %H:%M}.
{ACTION_SPEC}
"""

ALLOWED = set(ACTION_SPEC_ACTIONS := {
    m.group(1) for m in re.finditer(r"^([a-z_]+)\s*\{", ACTION_SPEC, re.MULTILINE)
})


def available() -> bool:
    return bool(config.deepseek_key()) and bool(config.SETTINGS.get("llm_enabled", True))


def _call(messages: list[dict], max_tokens: int = 220, json_mode: bool = True) -> str | None:
    key = config.deepseek_key()
    if not key:
        return None
    payload = {
        "model": config.SETTINGS.get("llm_model", "deepseek-chat"),
        "messages": messages,
        "temperature": 0.25,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=18) as response:
            body = json.loads(response.read().decode("utf-8", errors="replace"))
        return body["choices"][0]["message"]["content"]
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError, OSError):
        return None


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except ValueError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except ValueError:
            return None


def raw_call(messages: list[dict], max_tokens: int = 400, json_mode: bool = False) -> str | None:
    """Plain completion for callers that parse the answer themselves."""
    if not available():
        return None
    return _call(messages, max_tokens=max_tokens, json_mode=json_mode)


def interpret(text: str, history: list[dict] | None = None, system_note: str = "",
              screen_text: str = "") -> dict | None:
    if not available():
        return None
    context = f"\nLocal context: {system_note}" if system_note else ""
    if screen_text:
        context += (
            "\nThe user is looking at this screen. Visible text extracted by OCR:\n"
            + screen_text[:6500]
            + "\nWhen the request refers to 'this', 'here', 'my code', or 'the error', use the screen text."
        )
    messages = [{"role": "system", "content": SYSTEM + context}]
    for item in (history or [])[-6:]:
        role = item.get("role")
        if role in ("user", "assistant") and item.get("content"):
            messages.append({"role": role, "content": str(item["content"])[:800]})
    messages.append({"role": "user", "content": text})
    raw = _call(messages)
    if not raw:
        return None
    parsed = _extract_json(raw)
    if not parsed:
        return None
    action = str(parsed.get("action") or "").strip()
    if action not in ALLOWED:
        return None
    args = parsed.get("args")
    if not isinstance(args, dict):
        args = {}
    say = str(parsed.get("say") or "").strip()
    return {"action": action, "args": args, "say": say, "source": "neural"}


SCREEN_SYSTEM = """You are J.A.R.V.I.S., a dry, precise coding companion running on the user's Arch Linux machine.
You can read the text on the user's screen (provided below). Help them build, debug and understand what is in front of them.
Reply in clear English. Keep code, filenames and technical terms in English.
Rules:
- Answer the actual request directly.
- When fixing code, give the smallest correct change and a short explanation.
- Use Markdown fenced code blocks for code.
- Never invent on-screen content that is not in the OCR text. If something is unclear, say so.
- Keep the opening sentence short because it will be spoken aloud.
"""


def screen_answer(question: str, screen_text: str, history: list[dict] | None = None) -> str | None:
    if not available():
        return None
    user = f"Request: {question}\n\nScreen OCR text:\n{screen_text[:8000] if screen_text else '(no readable text detected)'}"
    messages = [{"role": "system", "content": SCREEN_SYSTEM}]
    for item in (history or [])[-4:]:
        if item.get("role") in ("user", "assistant") and item.get("content"):
            messages.append({"role": item["role"], "content": str(item["content"])[:600]})
    messages.append({"role": "user", "content": user})
    return _call(messages, max_tokens=760, json_mode=False)
